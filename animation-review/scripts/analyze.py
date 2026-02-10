#!/usr/bin/env python3
"""Analyze screen recordings using the Gemini or Kimi video understanding APIs."""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime

MAX_FPS = 24
RESULTS_DIR = ".animation-review"
CLEANUP_AGE_DAYS = 14

# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

PROVIDERS = {
    "gemini": {"env_key": "GEMINI_API_KEY"},
    "kimi": {"env_key": "KIMI_API_KEY", "base_url": "https://api.moonshot.ai/v1"},
}

# Maps Gemini model tiers to Kimi thinking/instant modes
# Flash-tier modes → instant (no thinking), Pro-tier modes → thinking enabled
KIMI_MODEL_MAP = {
    "gemini-2.5-flash": {"model": "kimi-k2.5", "thinking": False},
    "gemini-2.5-pro": {"model": "kimi-k2.5", "thinking": True},
}

# ---------------------------------------------------------------------------
# Modes — each defines FPS, default model, system prompt, and output schema
# ---------------------------------------------------------------------------

TEMPORAL_PREAMBLE = """\
TEMPORAL PRECISION: This video is sampled at {fps} frames per second. Each \
frame represents a {interval_ms}ms window. Your temporal resolution is limited \
to {interval_ms}ms increments — you cannot observe events between frames.

When reporting timestamps and durations:
- State durations in terms of frame count AND estimated milliseconds \
(e.g. "~3 frames / ~{example_duration}ms")
- If an event happens between frames, say so \
(e.g. "between {example_t1}s and {example_t2}s")
- Do not report sub-frame precision you cannot actually observe

"""

TEMPORAL_PREAMBLE_KIMI = """\
TEMPORAL PRECISION: This video has been pre-processed to {fps} frames per \
second. Each frame represents a {interval_ms}ms window. Your temporal \
resolution is limited to {interval_ms}ms increments — you cannot observe \
events between frames.

When reporting timestamps and durations:
- State durations in terms of frame count AND estimated milliseconds \
(e.g. "~3 frames / ~{example_duration}ms")
- If an event happens between frames, say so \
(e.g. "between {example_t1}s and {example_t2}s")
- Do not report sub-frame precision you cannot actually observe

"""

JSON_SCHEMA_INSTRUCTION = """

OUTPUT FORMAT: You MUST respond with valid JSON matching this schema exactly. \
Do not include any text before or after the JSON object. Do not wrap it in \
markdown code fences.

Schema:
{schema_json}"""

SYSTEM_PROMPTS = {
    "check": """\
You are reviewing a screen recording of a web animation for basic functionality.

Focus on:
- Does each animation trigger correctly?
- Does it run to completion without breaking?
- Are there obvious visual breaks, layout shifts, or missing elements?

Keep your analysis brief and pass/fail oriented for each animation you observe. \
Score 1-10 where 5+ means functionally working. Do not provide implementation \
advice — the developer has full codebase context that you lack.""",

    "review": """\
You are reviewing a screen recording of a web animation for design quality and \
polish.

For each animation, evaluate:
- Easing curve quality — does it feel natural or mechanical?
- Timing and duration — too fast, too slow, or just right?
- Choreography — how do multiple animated elements relate in time? Is staggering \
and sequencing intentional and pleasing?
- Visual consistency and overall polish

Score 1-10 against professional production standards. Your observations about \
what you see are the primary value. Keep implementation suggestions general and \
brief — the developer has full codebase context that you lack.""",

    "diagnose": """\
You are analyzing a screen recording of a web animation that has a reported bug \
or visual issue.

Provide an extremely detailed, frame-by-frame analysis. For each animation, \
report precise timestamps, approximate pixel positions, and the exact moment \
any glitch or unexpected behavior occurs. Describe what happens vs what should \
happen based on the provided context.

Structure your response in two distinct sections:

## Observations
Precise descriptions of what you see — timestamps, pixel positions, frame-by-frame \
changes. This is the reliable part.

## Hypotheses
Possible root causes based only on visual evidence. You cannot see the code. An agent \
with full codebase access will use your visual observations to locate the actual bug. \
For each hypothesis, list alternative explanations that could produce the same visual \
result (e.g. a sudden opacity change could be a compositing issue, a conditional render, \
or a filter effect). Include specific debugging steps (what to log, where to set \
breakpoints, what values to compare) that would confirm or rule out each possibility.

Prioritize precise descriptions of what you see over prescriptive fixes.""",

    "inspire": """\
You are analyzing a screen recording that shows a desired animation effect the \
developer wants to recreate.

Your job is to decompose what you see into a precise, technical description \
that serves as an animation specification.

For each animation or effect, describe:
- What visual properties are changing (position, scale, rotation, opacity, \
blur, clip-path, color, border-radius, etc.)
- The timing curve — is it linear, ease-out, spring-like, bouncy, stepped? \
Describe the character of the motion.
- Duration and any delays between stages
- How multiple elements coordinate — staggering, sequencing, overlapping
- Layer ordering and z-index behavior during the animation
- Any 3D perspective or spatial depth effects
- Subtle details that make it feel polished (micro-interactions, overshoot, \
settle, anticipation)

Describe everything in terms of visual properties and behavior, NOT in terms \
of any specific library or CSS framework. Do not write implementation code. \
Your analysis should read like an animation specification that could be \
implemented in any technology.""",
}


def build_system_prompt(mode_name, fps, provider="gemini", schema=None):
    """Build the full system prompt with temporal precision context."""
    interval_ms = round(1000 / fps)
    preamble_template = TEMPORAL_PREAMBLE_KIMI if provider == "kimi" else TEMPORAL_PREAMBLE
    preamble = preamble_template.format(
        fps=fps,
        interval_ms=interval_ms,
        example_duration=interval_ms * 3,
        example_t1=f"{1.0:.1f}",
        example_t2=f"{1.0 + interval_ms / 1000:.3f}".rstrip("0").rstrip("."),
    )
    prompt = preamble + SYSTEM_PROMPTS[mode_name]

    # For Kimi structured output, inject schema into system prompt
    if provider == "kimi" and schema is not None:
        prompt += JSON_SCHEMA_INSTRUCTION.format(
            schema_json=json.dumps(schema, indent=2)
        )

    return prompt


MODES = {
    "check":    {"fps": 5,  "model": "gemini-2.5-flash"},
    "review":   {"fps": 12, "model": "gemini-2.5-flash"},
    "diagnose": {"fps": 24, "model": "gemini-2.5-pro"},
    "inspire":  {"fps": 24, "model": "gemini-2.5-pro"},
}

# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "animations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "element": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "slide", "fade", "scale", "rotate",
                            "color", "morph", "scroll", "other",
                        ],
                    },
                    "timestamp": {"type": "string"},
                    "duration_ms": {"type": "integer"},
                    "easing": {"type": "string"},
                    "quality": {
                        "type": "string",
                        "enum": ["smooth", "acceptable", "janky", "broken"],
                    },
                },
                "required": [
                    "element", "type", "timestamp",
                    "duration_ms", "easing", "quality",
                ],
            },
        },
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "timestamp": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "description": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": [
                    "timestamp", "severity",
                    "description", "suggestion",
                ],
            },
        },
        "score": {"type": "integer"},
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "animations", "issues", "score", "recommendations"],
}

INSPIRE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "effects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "element": {"type": "string"},
                    "trigger": {"type": "string"},
                    "properties": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "from_state": {"type": "string"},
                    "to_state": {"type": "string"},
                    "duration_ms": {"type": "integer"},
                    "delay_ms": {"type": "integer"},
                    "easing": {"type": "string"},
                    "timestamp": {"type": "string"},
                },
                "required": [
                    "element", "trigger", "properties",
                    "from_state", "to_state", "duration_ms",
                    "easing", "timestamp",
                ],
            },
        },
        "choreography": {"type": "string"},
        "notable_details": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["summary", "effects", "choreography", "notable_details"],
}

DIAGNOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "timestamp": {"type": "string"},
                    "description": {"type": "string"},
                    "expected": {"type": "string"},
                    "actual": {"type": "string"},
                },
                "required": ["timestamp", "description", "expected", "actual"],
            },
        },
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cause": {"type": "string"},
                    "evidence": {"type": "string"},
                    "debugging_steps": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["cause", "evidence", "debugging_steps"],
            },
        },
    },
    "required": ["summary", "observations", "hypotheses"],
}

MODE_SCHEMAS = {
    "check": REVIEW_SCHEMA,
    "review": REVIEW_SCHEMA,
    "diagnose": DIAGNOSE_SCHEMA,
    "inspire": INSPIRE_SCHEMA,
}

# Modes where raw output is preferred by default (narrative detail matters more)
RAW_DEFAULT_MODES = {"diagnose", "inspire"}

# ---------------------------------------------------------------------------
# Video pre-processing (Kimi)
# ---------------------------------------------------------------------------


def preprocess_video_for_kimi(video_path, fps, start=None, end=None):
    """Re-encode video at target FPS with optional time clipping for Kimi.

    Returns (base64_string, mime_type) of the processed video.
    """
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if start:
        cmd += ["-ss", start]
    if end:
        cmd += ["-to", end]
    cmd += ["-i", video_path]
    cmd += ["-r", str(fps)]
    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]
    cmd += ["-an"]  # strip audio

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp_path = tmp.name
    tmp.close()
    cmd.append(tmp_path)

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        with open(tmp_path, "rb") as f:
            video_bytes = f.read()
        size_mb = len(video_bytes) / (1024 * 1024)
        print(f"Pre-processed video: {size_mb:.1f}MB at {fps}fps", file=sys.stderr)
        return base64.b64encode(video_bytes).decode(), "video/mp4"
    except subprocess.CalledProcessError as e:
        print(f"Error: ffmpeg pre-processing failed: {e.stderr.decode()}", file=sys.stderr)
        sys.exit(1)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# JSON extraction (for providers without native schema enforcement)
# ---------------------------------------------------------------------------


def extract_json_from_response(text):
    """Extract JSON from a response that may contain markdown fencing or text.

    Returns (parsed_dict, was_clean) where was_clean indicates the response
    was valid JSON without needing extraction.
    """
    stripped = text.strip()

    # Try direct parse first
    try:
        return json.loads(stripped), True
    except json.JSONDecodeError:
        pass

    # Try stripping markdown code fences
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", stripped, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1)), False
        except json.JSONDecodeError:
            pass

    # Try finding the outermost { ... } block
    brace_start = stripped.find("{")
    brace_end = stripped.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(stripped[brace_start:brace_end + 1]), False
        except json.JSONDecodeError:
            pass

    return None, False


# ---------------------------------------------------------------------------
# Provider API calls
# ---------------------------------------------------------------------------


def call_gemini(api_key, video_path, user_prompt, system_prompt, model, schema, fps, start, end, use_raw):
    """Call Gemini API with video. Returns (output_text, use_raw, metadata)."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print(
            "Error: google-genai package not installed. Run: pip install google-genai",
            file=sys.stderr,
        )
        sys.exit(1)

    ext = os.path.splitext(video_path)[1].lower()
    mime_types = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}
    mime_type = mime_types.get(ext)
    if mime_type is None:
        print(
            f"Error: Unsupported video format '{ext}'. Use .mp4, .mov, or .webm",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    video_meta_kwargs = {"fps": fps}
    if start:
        video_meta_kwargs["start_offset"] = start
    if end:
        video_meta_kwargs["end_offset"] = end

    client = genai.Client(api_key=api_key)
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part(
                    inline_data=types.Blob(data=video_bytes, mime_type=mime_type),
                    video_metadata=types.VideoMetadata(**video_meta_kwargs),
                ),
                types.Part.from_text(text=user_prompt),
            ],
        )
    ]

    output_text = None
    metadata = {}
    response = None
    t0 = time.time()

    if not use_raw:
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            result = json.loads(response.text)
            output_text = json.dumps(result, indent=2)
        except Exception as e:
            print(f"Structured output failed ({e}), falling back to raw text...", file=sys.stderr)
            use_raw = True

    if use_raw:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
        )
        output_text = response.text

    metadata["latency_s"] = round(time.time() - t0, 1)
    if response and hasattr(response, "usage_metadata") and response.usage_metadata:
        um = response.usage_metadata
        metadata["prompt_tokens"] = getattr(um, "prompt_token_count", None)
        metadata["output_tokens"] = getattr(um, "candidates_token_count", None)

    return output_text, use_raw, metadata


def call_kimi(api_key, video_path, user_prompt, system_prompt, model, fps, start, end, use_raw):
    """Call Kimi API with video. Returns (output_text, use_raw, metadata)."""
    try:
        import openai
    except ImportError:
        print(
            "Error: openai package not installed. Run: pip install openai",
            file=sys.stderr,
        )
        sys.exit(1)

    kimi_config = KIMI_MODEL_MAP.get(model)
    if kimi_config is None:
        print(
            f"Error: No Kimi mapping for model '{model}'. "
            f"Known mappings: {', '.join(KIMI_MODEL_MAP.keys())}",
            file=sys.stderr,
        )
        sys.exit(1)

    video_b64, mime_type = preprocess_video_for_kimi(video_path, fps, start, end)

    client = openai.OpenAI(
        api_key=api_key,
        base_url=PROVIDERS["kimi"]["base_url"],
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {
                    "type": "video_url",
                    "video_url": {"url": f"data:{mime_type};base64,{video_b64}"},
                },
                {"type": "text", "text": user_prompt},
            ],
        },
    ]

    kwargs = {
        "model": kimi_config["model"],
        "messages": messages,
        "max_tokens": 16384,
    }
    if kimi_config["thinking"]:
        kwargs["temperature"] = 1.0
    else:
        kwargs["temperature"] = 0.6
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    metadata = {}
    t0 = time.time()
    response = client.chat.completions.create(**kwargs)
    metadata["latency_s"] = round(time.time() - t0, 1)

    if response.usage:
        metadata["prompt_tokens"] = response.usage.prompt_tokens
        metadata["output_tokens"] = response.usage.completion_tokens

    thinking_mode = "thinking" if kimi_config["thinking"] else "instant"
    metadata["kimi_mode"] = thinking_mode

    raw_text = response.choices[0].message.content
    output_text = raw_text

    if not use_raw:
        parsed, was_clean = extract_json_from_response(raw_text)
        if parsed:
            output_text = json.dumps(parsed, indent=2)
            if not was_clean:
                print("Note: Extracted JSON from non-clean response", file=sys.stderr)
        else:
            print("Warning: Could not extract JSON, returning raw text", file=sys.stderr)
            use_raw = True
            output_text = raw_text

    return output_text, use_raw, metadata


# ---------------------------------------------------------------------------
# Results persistence & cleanup
# ---------------------------------------------------------------------------


def ensure_results_dir():
    """Create the results directory and ensure it's gitignored."""
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Add to .gitignore if we're in a git repo and it's not already ignored
    gitignore_path = ".gitignore"
    entry = RESULTS_DIR + "/"
    if os.path.isdir(".git"):
        lines = []
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r") as f:
                lines = f.read().splitlines()
        if entry not in lines and RESULTS_DIR not in lines:
            with open(gitignore_path, "a") as f:
                if lines and lines[-1] != "":
                    f.write("\n")
                f.write(entry + "\n")
            print(f"Added {entry} to .gitignore", file=sys.stderr)


def cleanup_old_results():
    """Remove files in the results directory older than CLEANUP_AGE_DAYS."""
    if not os.path.isdir(RESULTS_DIR):
        return
    cutoff = time.time() - (CLEANUP_AGE_DAYS * 86400)
    removed = 0
    for name in os.listdir(RESULTS_DIR):
        path = os.path.join(RESULTS_DIR, name)
        if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
            os.remove(path)
            removed += 1
    if removed:
        print(f"Cleaned up {removed} file(s) older than {CLEANUP_AGE_DAYS} days", file=sys.stderr)


def save_results(video_path, mode_name, provider, output_text, use_raw):
    """Save the video and analysis output to the results directory."""
    ensure_results_dir()
    cleanup_old_results()

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    suffix = f"_{provider}" if provider != "gemini" else ""
    base = f"{stamp}_{mode_name}{suffix}"

    # Save analysis
    ext = ".md" if use_raw else ".json"
    analysis_path = os.path.join(RESULTS_DIR, base + ext)
    with open(analysis_path, "w") as f:
        f.write(output_text)

    # Save video — skip if already in results dir, move from /tmp, copy otherwise
    video_ext = os.path.splitext(video_path)[1].lower()
    video_dest = os.path.join(RESULTS_DIR, base + video_ext)
    video_abs = os.path.abspath(video_path)
    results_abs = os.path.abspath(RESULTS_DIR)

    if os.path.dirname(video_abs) == results_abs:
        # Already in results dir (agent pre-moved it) — just note the existing path
        video_dest = video_path
    elif video_abs.startswith("/tmp/"):
        shutil.move(video_path, video_dest)
    else:
        shutil.copy2(video_path, video_dest)

    print(f"Saved → {os.path.abspath(analysis_path)}, {os.path.abspath(video_dest)}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args():
    p = argparse.ArgumentParser(
        description="Analyze animation recordings via Gemini or Kimi",
        epilog="""
Modes:
  check      5fps, Flash  — "Does it work?" Basic functionality sanity check.
  review    12fps, Flash  — "How does it feel?" Design quality and polish.
  diagnose  24fps, Pro    — "What's going wrong?" Frame-level bug analysis.
  inspire   24fps, Pro    — "What's happening here?" Decompose a reference effect.

Providers:
  gemini     Default. Uses Gemini API with native FPS control and schema enforcement.
  kimi       Uses Kimi K2.5 via OpenAI-compatible API. Video pre-processed with ffmpeg.
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "-v", "--video",
        default="/tmp/animation-review.mp4",
        help="Video file path (default: /tmp/animation-review.mp4)",
    )
    p.add_argument(
        "-t", "--mode",
        choices=list(MODES.keys()),
        default=None,
        help="Analysis mode (sets FPS, model, and system prompt)",
    )
    p.add_argument(
        "-f", "--fps", type=int, default=None,
        help="Explicit FPS override (max 24)",
    )
    p.add_argument(
        "--start", default=None,
        help="Start offset for video clip (e.g. '3s', '1.5s', '90s')",
    )
    p.add_argument(
        "--end", default=None,
        help="End offset for video clip (e.g. '5s', '8.2s', '120s')",
    )
    p.add_argument(
        "-p", "--prompt", default="",
        help="Additional context about the animation",
    )
    p.add_argument(
        "-m", "--model", default=None,
        help="Gemini model override (default depends on mode)",
    )
    p.add_argument(
        "--provider",
        choices=list(PROVIDERS.keys()),
        default="gemini",
        help="LLM provider (default: gemini)",
    )
    p.add_argument(
        "--raw", action="store_true", default=None,
        help="Force raw text output instead of structured JSON",
    )
    p.add_argument(
        "--json", action="store_true",
        help="Force structured JSON output",
    )
    p.add_argument(
        "--no-save", action="store_true",
        help="Don't save results to .animation-review/",
    )
    return p.parse_args()


def resolve_mode(args):
    """Resolve mode, FPS, model, system prompt, and schema from args."""
    mode_name = args.mode or "review"
    mode = MODES[mode_name]

    fps = args.fps if args.fps is not None else mode["fps"]
    if fps > MAX_FPS:
        print(f"Warning: FPS {fps} exceeds max ({MAX_FPS}), capping", file=sys.stderr)
        fps = MAX_FPS

    model = args.model if args.model is not None else mode["model"]
    schema = MODE_SCHEMAS[mode_name]

    # Determine output format: explicit flags > mode default
    if args.json:
        use_raw = False
    elif args.raw:
        use_raw = True
    else:
        use_raw = mode_name in RAW_DEFAULT_MODES

    # Build system prompt with provider-specific preamble and optional schema injection
    schema_for_prompt = None if use_raw else schema
    system_prompt = build_system_prompt(mode_name, fps, args.provider, schema_for_prompt)

    return fps, model, system_prompt, schema, use_raw, mode_name


def main():
    args = parse_args()
    fps, model, system_prompt, schema, use_raw, mode_name = resolve_mode(args)
    provider = args.provider

    # Resolve API key
    env_key = PROVIDERS[provider]["env_key"]
    api_key = os.environ.get(env_key)
    if not api_key:
        print(f"Error: {env_key} environment variable not set", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.video):
        print(f"Error: Video file not found: {args.video}", file=sys.stderr)
        sys.exit(1)

    # Log what we're doing
    size_mb = os.path.getsize(args.video) / (1024 * 1024)
    range_str = ""
    if args.start or args.end:
        range_str = f" [{args.start or '0s'}–{args.end or 'end'}]"

    provider_label = provider
    if provider == "kimi":
        kimi_cfg = KIMI_MODEL_MAP.get(model, {})
        thinking = "thinking" if kimi_cfg.get("thinking") else "instant"
        provider_label = f"kimi ({thinking})"

    print(
        f"[{mode_name}] Analyzing {args.video} ({size_mb:.1f}MB){range_str} "
        f"at {fps}fps with {provider_label}...",
        file=sys.stderr,
    )

    user_prompt = "Analyze the animations in this screen recording."
    if args.prompt:
        user_prompt += f"\n\nContext: {args.prompt}"

    # Dispatch to provider
    if provider == "gemini":
        output_text, use_raw, metadata = call_gemini(
            api_key, args.video, user_prompt, system_prompt,
            model, schema, fps, args.start, args.end, use_raw,
        )
    elif provider == "kimi":
        output_text, use_raw, metadata = call_kimi(
            api_key, args.video, user_prompt, system_prompt,
            model, fps, args.start, args.end, use_raw,
        )

    print(output_text)

    # Print metadata summary
    meta_parts = [f"provider={provider}"]
    if "latency_s" in metadata:
        meta_parts.append(f"latency={metadata['latency_s']}s")
    if "prompt_tokens" in metadata and metadata["prompt_tokens"] is not None:
        meta_parts.append(f"prompt_tokens={metadata['prompt_tokens']}")
    if "output_tokens" in metadata and metadata["output_tokens"] is not None:
        meta_parts.append(f"output_tokens={metadata['output_tokens']}")
    if "kimi_mode" in metadata:
        meta_parts.append(f"kimi_mode={metadata['kimi_mode']}")
    print(f"[metadata] {', '.join(meta_parts)}", file=sys.stderr)

    # Save results
    if not args.no_save and output_text:
        save_results(args.video, mode_name, provider, output_text, use_raw)


if __name__ == "__main__":
    main()
