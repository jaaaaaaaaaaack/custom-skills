# Design Review Skill — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a verification-first design review skill that delegates screenshot analysis to Gemini, teaching agents they cannot trust their own visual assessment.

**Architecture:** Python CLI script using google-genai SDK with four modes (verify, compare, audit, parity). SKILL.md is the primary deliverable — it encodes the behavioral contract that agents must delegate verification screenshots to Gemini. Results persist to `.design-review/` with auto-cleanup.

**Tech Stack:** Python 3.10+, google-genai SDK, structured JSON output via Gemini API

**Design doc:** `docs/plans/2026-02-13-design-review-design.md`

**Reference implementation:** `animation-review/scripts/analyze.py` — follow its patterns for SDK usage, results persistence, CLI structure, and output format negotiation.

---

### Task 1: Project Scaffolding

**Files:**
- Create: `design-review/requirements.txt`
- Create: `design-review/scripts/review.py` (skeleton only)
- Create: `design-review/references/learnings.md`

**Step 1: Create directory structure**

```bash
mkdir -p design-review/scripts design-review/references
```

**Step 2: Create requirements.txt**

Create `design-review/requirements.txt`:
```
google-genai>=1.56.0
```

**Step 3: Create review.py skeleton with argument parsing**

Create `design-review/scripts/review.py`. This is the full CLI skeleton — all args, validation, no Gemini logic yet:

```python
#!/usr/bin/env python3
"""Send screenshots to Gemini for visual design review.

Usage:
    python review.py --mode {verify,compare,audit,parity} --image PATH [OPTIONS]

Modes:
    verify   - Verify a visual fix landed correctly (fast, gatekeeper)
    compare  - Before/after visual diff (requires --image2)
    audit    - Comprehensive visual quality audit
    parity   - Design-to-implementation fidelity check (requires --image2)
"""

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime

RESULTS_DIR = ".design-review"
CLEANUP_AGE_DAYS = 14

MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

MODES = {
    "verify":  {"model": "gemini-2.5-flash", "temperature": 0.2},
    "compare": {"model": "gemini-2.5-flash", "temperature": 0.2},
    "audit":   {"model": "gemini-2.5-pro",   "temperature": 0.3},
    "parity":  {"model": "gemini-2.5-pro",   "temperature": 0.2},
}


def parse_args():
    p = argparse.ArgumentParser(
        description="Send screenshots to Gemini for visual design review.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--mode", required=True,
        choices=list(MODES.keys()),
        help="Review mode",
    )
    p.add_argument(
        "--image", required=True,
        help="Path to primary screenshot (png, jpg, or webp)",
    )
    p.add_argument(
        "--image2",
        help="Path to second image (required for compare and parity modes)",
    )
    p.add_argument(
        "--focus",
        help="What to verify — describe the expected visual result (verify mode)",
    )
    p.add_argument(
        "--context", action="append",
        help="Source file to include for context (repeatable)",
    )
    p.add_argument(
        "--description",
        help="What the screenshot shows (e.g., 'Dashboard at 1440px')",
    )
    p.add_argument(
        "--model", default=None,
        help="Gemini model override",
    )
    p.add_argument(
        "--raw", action="store_true", default=None,
        help="Force raw markdown output instead of structured JSON",
    )
    p.add_argument(
        "--json", action="store_true",
        help="Force structured JSON output",
    )
    p.add_argument(
        "--no-save", action="store_true",
        help="Don't save results to .design-review/",
    )
    return p.parse_args()


def validate_args(args):
    """Validate mode-specific argument requirements."""
    if args.mode in ("compare", "parity") and not args.image2:
        print(f"Error: --image2 is required for {args.mode} mode", file=sys.stderr)
        sys.exit(1)
    if args.focus and args.mode != "verify":
        print("Warning: --focus is only used in verify mode, ignoring", file=sys.stderr)


def detect_mime(path):
    """Return MIME type for an image path, or exit on unsupported format."""
    ext = os.path.splitext(path)[1].lower()
    mime = MIME_TYPES.get(ext)
    if not mime:
        print(f"Error: Unsupported image format '{ext}'. Use png, jpg, or webp.", file=sys.stderr)
        sys.exit(1)
    return mime


def main():
    args = parse_args()
    validate_args(args)

    # Validate image exists
    if not os.path.isfile(args.image):
        print(f"Error: Image not found: {args.image}", file=sys.stderr)
        sys.exit(1)
    if args.image2 and not os.path.isfile(args.image2):
        print(f"Error: Image not found: {args.image2}", file=sys.stderr)
        sys.exit(1)

    # Check API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set.", file=sys.stderr)
        print("  Get a key at https://aistudio.google.com/apikey", file=sys.stderr)
        sys.exit(1)

    print(f"[{args.mode}] review.py skeleton — not yet implemented", file=sys.stderr)


if __name__ == "__main__":
    main()
```

**Step 4: Create learnings.md**

Create `design-review/references/learnings.md` — carry over the one existing observation from the old skill:

```markdown
# Design Review — Learnings

Observations from past reviews. Read this before running a review to apply lessons learned.

## Mode Effectiveness

## Context That Helped

## Context That Didn't Help

## Gemini Blind Spots
- Creative mode flagged an in-context editing toolbar as "visual density/clutter" — didn't recognize it as contextual UI that only appears when editing. Gemini treats visible controls as permanent, misses conditional states.

## Recurring Fixes

## Workflow Notes
```

**Step 5: Verify the skeleton runs**

Run: `python design-review/scripts/review.py --mode verify --image /dev/null`
Expected: Error about image not found (since /dev/null isn't an image file) — confirms arg parsing works.

Run: `python design-review/scripts/review.py --mode compare --image /tmp/test.png`
Expected: Error about --image2 required — confirms validation works.

**Step 6: Commit**

```bash
git add design-review/
git commit -m "feat(design-review): scaffold project structure and CLI skeleton"
```

---

### Task 2: System Prompts

**Files:**
- Modify: `design-review/scripts/review.py`

**Step 1: Add the shared preamble and all four mode prompts**

Add these constants after the `MODES` dict in `review.py`:

```python
SHARED_PREAMBLE = """\
You are reviewing a static screenshot of a web interface. You can observe \
spatial relationships, colors, typography, alignment, and visual hierarchy. \
You cannot see the code, interact with the page, or observe hover/focus/animation states.

The developer has full codebase context that you lack. Your observations about \
what you see are reliable. Your suggestions about specific CSS properties or \
implementation details are informed guesses — label them as such.

Be precise about locations. Reference visible text labels, element types, and \
positions (e.g., "the third card in the top row," "the submit button below the \
email field"). Vague locations like "some elements" are not useful.

"""

SYSTEM_PROMPTS = {
    "verify": """\
You are checking whether a developer's visual change was applied correctly.

{focus_section}\
Look for anything visually wrong — spacing issues, alignment problems, color \
mismatches, overlapping elements, broken layouts, incorrect visual hierarchy. \
A false pass is the worst outcome. If something looks even slightly off, report \
it. Err on the side of flagging.

Keep your response concise. Focus on what's wrong, not what's right.""",

    "compare": """\
You are comparing two screenshots: Image 1 is BEFORE, Image 2 is AFTER.

Identify every visual difference between the two images. Classify each as:
- **Improvement** — A positive change
- **Regression** — Something that got worse or broke
- **Neutral** — Different but neither better nor worse

Pay special attention to areas adjacent to obvious changes — regressions often \
appear in nearby elements that were affected by the same code change.

Also note any pre-existing issues visible in both images that remain unfixed \
(report these as unchanged_issues).""",

    "audit": """\
You are performing a comprehensive visual quality audit of a web interface screenshot.

Check these categories systematically:
1. **Spacing & Alignment** — Inconsistent margins/padding, misaligned elements, uneven gaps
2. **Typography** — Font size hierarchy, line height, letter spacing, weight consistency, truncation
3. **Color & Contrast** — Color consistency, sufficient contrast, proper palette usage
4. **Layout & Composition** — Visual balance, content hierarchy, whitespace usage, responsive clues
5. **Interactive Elements** — Button sizing, clickable area adequacy, form field styling
6. **Polish & Details** — Border radius consistency, shadow consistency, icon sizing, pixel-level issues

Group findings by severity. Be thorough — this is meant to catch everything.""",

    "parity": """\
You are comparing an implementation screenshot (Image 1) against a design \
reference (Image 2, typically from Figma).

Compare every visual detail and report discrepancies:
1. **Spacing** — Margins, padding, gaps between elements
2. **Typography** — Font family, size, weight, line height, letter spacing, color
3. **Colors** — Background colors, text colors, border colors, shadow colors
4. **Layout** — Element positioning, sizing, proportions, alignment
5. **Visual Details** — Border radius, shadows, opacity, icons, images, decorative elements
6. **Content** — Text content differences, placeholder text, missing/extra elements

Report what you see in each image, not what you think the code should be. \
Rate fidelity as a percentage (0-100%).""",
}


def build_system_prompt(mode_name, focus=None):
    """Build the full system prompt with shared preamble and mode-specific instructions."""
    mode_prompt = SYSTEM_PROMPTS[mode_name]

    # Inject focus section for verify mode
    if mode_name == "verify" and focus:
        focus_section = (
            f"The developer's stated change: \"{focus}\"\n"
            "Primary check: Is this specific change correctly applied? "
            "Secondary check: Quick scan of the surrounding area for regressions.\n\n"
        )
    else:
        focus_section = ""

    mode_prompt = mode_prompt.format(focus_section=focus_section)
    return SHARED_PREAMBLE + mode_prompt
```

**Step 2: Verify prompts build correctly**

Add a temporary test at the bottom of `main()`:

```python
    # Temporary — test prompt building
    prompt = build_system_prompt(args.mode, args.focus)
    print(prompt)
```

Run: `python design-review/scripts/review.py --mode verify --image /tmp/test.png --focus "Cards should have equal gaps"`
Expected: Prints the full system prompt with focus section injected.

Run: `python design-review/scripts/review.py --mode audit --image /tmp/test.png`
Expected: Prints audit prompt without focus section.

Remove the temporary test code after verifying.

**Step 3: Commit**

```bash
git add design-review/scripts/review.py
git commit -m "feat(design-review): add system prompts for all four modes"
```

---

### Task 3: Output Schemas

**Files:**
- Modify: `design-review/scripts/review.py`

**Step 1: Add structured output schemas for all four modes**

Add after the `build_system_prompt` function:

```python
VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "summary": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "major", "minor"],
                    },
                    "category": {
                        "type": "string",
                        "enum": ["spacing", "layout", "color", "typography", "visual", "content"],
                    },
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["severity", "category", "description", "location"],
            },
        },
    },
    "required": ["passed", "summary", "issues"],
}

COMPARE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "improvements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                },
                "required": ["description", "location"],
            },
        },
        "regressions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "major", "minor"],
                    },
                },
                "required": ["description", "location", "severity"],
            },
        },
        "unchanged_issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                },
                "required": ["description", "location"],
            },
        },
    },
    "required": ["summary", "improvements", "regressions", "unchanged_issues"],
}

AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "critical": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["category", "description", "location"],
            },
        },
        "major": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["category", "description", "location"],
            },
        },
        "minor": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["category", "description", "location"],
            },
        },
        "strengths": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["summary", "critical", "major", "minor", "strengths"],
}

PARITY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "fidelity_score": {"type": "integer"},
        "discrepancies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "notable", "minor"],
                    },
                    "element": {"type": "string"},
                    "expected": {"type": "string"},
                    "actual": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["severity", "element", "expected", "actual"],
            },
        },
        "matches": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["summary", "fidelity_score", "discrepancies", "matches"],
}

MODE_SCHEMAS = {
    "verify": VERIFY_SCHEMA,
    "compare": COMPARE_SCHEMA,
    "audit": AUDIT_SCHEMA,
    "parity": PARITY_SCHEMA,
}
```

**Step 2: Commit**

```bash
git add design-review/scripts/review.py
git commit -m "feat(design-review): add structured output schemas for all modes"
```

---

### Task 4: Gemini Integration

**Files:**
- Modify: `design-review/scripts/review.py`

This is the core — reading images, building the Gemini request, handling structured/raw output.

**Step 1: Add image reading and context file helpers**

Add after `detect_mime`:

```python
def read_image(path):
    """Read an image file and return (bytes, mime_type)."""
    mime = detect_mime(path)
    with open(path, "rb") as f:
        return f.read(), mime


def read_context_file(path):
    """Read a source file and return its contents, or None on failure."""
    try:
        with open(path, "r") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"Warning: Could not read context file '{path}': {e}", file=sys.stderr)
        return None
```

**Step 2: Add the Gemini call logic to main()**

Replace the placeholder in `main()` with the full implementation. Follow the animation-review pattern: lazy import of google-genai, build contents list with image parts + text parts, call with structured output, fall back to raw on failure.

```python
def main():
    args = parse_args()
    validate_args(args)

    if not os.path.isfile(args.image):
        print(f"Error: Image not found: {args.image}", file=sys.stderr)
        sys.exit(1)
    if args.image2 and not os.path.isfile(args.image2):
        print(f"Error: Image not found: {args.image2}", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set.", file=sys.stderr)
        print("  Get a key at https://aistudio.google.com/apikey", file=sys.stderr)
        sys.exit(1)

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print(
            "Error: google-genai package not installed. Run: pip install google-genai",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve mode settings
    mode = MODES[args.mode]
    model = args.model or mode["model"]
    temperature = mode["temperature"]
    system_prompt = build_system_prompt(args.mode, args.focus)
    schema = MODE_SCHEMAS[args.mode]

    # Determine output format
    if args.json:
        use_raw = False
    elif args.raw:
        use_raw = True
    else:
        use_raw = False  # All modes default to structured JSON

    # Build content parts
    parts = []

    # Description
    if args.description:
        parts.append(types.Part.from_text(text=f"Description: {args.description}"))

    # Primary image
    img_bytes, img_mime = read_image(args.image)
    parts.append(types.Part.from_bytes(data=img_bytes, mime_type=img_mime))

    # Second image (compare / parity)
    if args.image2:
        img2_bytes, img2_mime = read_image(args.image2)
        if args.mode == "compare":
            parts.append(types.Part.from_text(text="Second image (AFTER state):"))
        elif args.mode == "parity":
            parts.append(types.Part.from_text(text="Second image (DESIGN REFERENCE):"))
        parts.append(types.Part.from_bytes(data=img2_bytes, mime_type=img2_mime))

    # Context files
    if args.context:
        for ctx_path in args.context:
            content = read_context_file(ctx_path)
            if content:
                parts.append(types.Part.from_text(
                    text=f"Source file `{ctx_path}`:\n```\n{content}\n```"
                ))

    # User instruction
    mode_instructions = {
        "verify": "Check this screenshot for visual defects.",
        "compare": "Compare these two screenshots (before/after) and identify all differences.",
        "audit": "Perform a comprehensive visual quality audit of this screenshot.",
        "parity": "Compare the implementation against the design reference and report all discrepancies.",
    }
    parts.append(types.Part.from_text(text=mode_instructions[args.mode]))

    contents = [types.Content(role="user", parts=parts)]

    size_mb = len(img_bytes) / (1024 * 1024)
    print(f"[{args.mode}] Reviewing {args.image} ({size_mb:.1f}MB) with {model}...", file=sys.stderr)

    client = genai.Client(api_key=api_key)
    output_text = None

    # Structured JSON output
    if not use_raw:
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=temperature,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            result = json.loads(response.text)
            output_text = json.dumps(result, indent=2)
            print(output_text)
        except Exception as e:
            print(f"Structured output failed ({e}), falling back to raw text...", file=sys.stderr)
            use_raw = True

    # Raw text output (or fallback)
    if use_raw:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
            ),
        )
        output_text = response.text
        print(output_text)

    # Save results
    if not args.no_save and output_text:
        save_results(args.image, args.image2, args.mode, output_text, use_raw)
```

**Step 3: Test with a real screenshot**

Take any screenshot of a web page and run:

```bash
python design-review/scripts/review.py --mode verify --image /tmp/test-screenshot.png --no-save
```

Expected: Gemini returns structured JSON with `passed`, `summary`, and `issues` fields.

```bash
python design-review/scripts/review.py --mode verify --image /tmp/test-screenshot.png --focus "Navigation items should be evenly spaced" --no-save
```

Expected: Focused response targeting the navigation spacing.

**Step 4: Commit**

```bash
git add design-review/scripts/review.py
git commit -m "feat(design-review): add Gemini integration with structured output"
```

---

### Task 5: Results Persistence

**Files:**
- Modify: `design-review/scripts/review.py`

**Step 1: Add results persistence functions**

Add these functions (following the animation-review pattern) before `main()`:

```python
def ensure_results_dir():
    """Create the results directory and ensure it's gitignored."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
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


def save_results(image_path, image2_path, mode_name, output_text, use_raw):
    """Save screenshots and analysis output to the results directory."""
    ensure_results_dir()
    cleanup_old_results()

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    base = f"{stamp}_{mode_name}"

    # Save analysis
    ext = ".md" if use_raw else ".json"
    analysis_path = os.path.join(RESULTS_DIR, base + ext)
    with open(analysis_path, "w") as f:
        f.write(output_text)

    # Save primary screenshot (always copy — agent may reference it again)
    img_ext = os.path.splitext(image_path)[1].lower()
    img_dest = os.path.join(RESULTS_DIR, base + img_ext)
    img_abs = os.path.abspath(image_path)
    results_abs = os.path.abspath(RESULTS_DIR)

    if os.path.dirname(img_abs) == results_abs:
        img_dest = image_path  # Already in results dir
    else:
        shutil.copy2(image_path, img_dest)

    # Save second screenshot if present (compare/parity)
    if image2_path:
        img2_ext = os.path.splitext(image2_path)[1].lower()
        suffix = "_after" if mode_name == "compare" else "_reference"
        img2_dest = os.path.join(RESULTS_DIR, base + suffix + img2_ext)
        img2_abs = os.path.abspath(image2_path)
        if os.path.dirname(img2_abs) != results_abs:
            shutil.copy2(image2_path, img2_dest)

    print(f"Saved → {os.path.abspath(analysis_path)}", file=sys.stderr)
```

**Step 2: Test results saving**

Run a review with saving enabled (remove `--no-save`):

```bash
python design-review/scripts/review.py --mode verify --image /tmp/test-screenshot.png
ls -la .design-review/
```

Expected: `.design-review/` directory created with a `.json` and `.png` file. `.gitignore` updated.

**Step 3: Commit**

```bash
git add design-review/scripts/review.py
git commit -m "feat(design-review): add results persistence with auto-cleanup"
```

---

### Task 6: SKILL.md

**Files:**
- Create: `design-review/SKILL.md`

This is the most important file. It teaches agents the behavioral contract.

**Step 1: Write the full SKILL.md**

Create `design-review/SKILL.md`. The content must cover:

1. **Frontmatter** — name, description (triggers on visual verification work AND manual `/design-review` invocation)
2. **The core rule** — "You cannot visually verify your own work" — front and center, impossible to miss
3. **When to auto-delegate** — the trigger is taking a verification screenshot, not every CSS change
4. **When to skip** — non-visual changes, user says to skip
5. **Prerequisites** — GEMINI_API_KEY, Python, google-genai
6. **Mode selection guide** — table mapping situations to modes
7. **Usage examples** — CLI commands for each mode, with good `--focus` examples using visual language
8. **The verify-fix loop** — step-by-step workflow
9. **Focus parameter guidance** — visual language, not code language, with good/bad examples
10. **Context guidance per mode** — what `--description` and `--context` to pass
11. **Integration with other skills** — webapp-testing (Playwright screenshots), frontend-design, figma
12. **Learnings** — read `references/learnings.md` before reviews, when/how to update it
13. **Troubleshooting** — common errors and fixes

Key details for the frontmatter description — it should match on:
- Explicit `/design-review` invocation
- Visual verification work (taking screenshots to check changes)
- Design QA, visual quality checks

Write the full SKILL.md content. Use the animation-review SKILL.md as a reference for structure and tone (at `animation-review/SKILL.md`), but this is a distinct skill with its own behavioral contract.

**Step 2: Review the SKILL.md**

Read it back and verify:
- The core rule is in the first few lines, impossible to miss
- Focus examples use visual language, never code/token language
- The verify-fix loop is clear and actionable
- Mode selection is unambiguous

**Step 3: Commit**

```bash
git add design-review/SKILL.md
git commit -m "feat(design-review): add SKILL.md behavioral contract"
```

---

### Task 7: README.md

**Files:**
- Create: `design-review/README.md`

**Step 1: Write user-facing README**

Create `design-review/README.md` — user-facing setup and CLI reference. Cover:

1. What the skill does (one paragraph)
2. Setup (GEMINI_API_KEY, pip install, symlink)
3. Quick start (one command to run)
4. CLI reference (all flags with descriptions)
5. Modes (brief description of each)

Keep it concise. The SKILL.md is for agents; the README is for the human setting it up.

**Step 2: Commit**

```bash
git add design-review/README.md
git commit -m "feat(design-review): add user-facing README"
```

---

### Task 8: Deployment & Smoke Test

**Files:**
- Modify: symlink at `~/.claude/skills/design-review`

**Step 1: Remove old skill and create symlink**

The old design-review skill lives at `~/.claude/skills/design-review/` (not a symlink). Back it up and replace:

```bash
mv ~/.claude/skills/design-review ~/.claude/skills/design-review-old
ln -s /Users/jack/Projects/custom-skills/design-review ~/.claude/skills/design-review
```

**Step 2: Install dependencies**

```bash
pip install -r design-review/requirements.txt
```

(google-genai is likely already installed from animation-review, but confirm.)

**Step 3: Smoke test each mode**

Take a screenshot of any web page and test:

```bash
# Verify mode (the primary use case)
python ~/.claude/skills/design-review/scripts/review.py \
  --mode verify --image /tmp/test.png \
  --focus "Page content should be centered with consistent margins"

# Audit mode
python ~/.claude/skills/design-review/scripts/review.py \
  --mode audit --image /tmp/test.png \
  --description "Homepage at 1440px"

# Raw output
python ~/.claude/skills/design-review/scripts/review.py \
  --mode verify --image /tmp/test.png --raw
```

Expected: Each mode returns well-formed output. Verify mode returns JSON with `passed` boolean. Results saved to `.design-review/`.

**Step 4: Clean up old skill backup**

After confirming the new skill works:

```bash
rm -rf ~/.claude/skills/design-review-old
```

**Step 5: Commit any remaining changes**

```bash
git add -A
git commit -m "feat(design-review): deploy globally via symlink, smoke test passed"
```

---

### Task 9: Integration Verification

**Step 1: Test that the skill loads correctly in Claude Code**

Start a new Claude Code session and verify:
- The skill appears in the available skills list
- Invoking `/design-review` loads the SKILL.md
- The SKILL.md's behavioral guidance is clear about when to auto-delegate

**Step 2: Test the verification workflow end-to-end**

In a project with a web app, ask Claude to:
1. Make a visual CSS change
2. Take a verification screenshot
3. Verify it delegates to Gemini instead of self-assessing
4. Confirm the verify-fix loop works

This is a manual integration test — verify the SKILL.md guidance actually changes agent behavior.

**Step 3: Final commit if any adjustments needed**

Fix any issues found during integration testing and commit.
