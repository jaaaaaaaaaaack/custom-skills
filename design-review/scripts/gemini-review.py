#!/usr/bin/env python3
"""Send screenshots to Gemini for visual design analysis.

Usage:
    python gemini-review.py --mode {qa,compare,a11y,parity,creative} --image PATH [OPTIONS]

Modes:
    qa       - Visual quality audit (spacing, alignment, typography, color, polish)
    compare  - Before/after visual diff (requires --image2)
    a11y     - WCAG 2.1 AA accessibility audit
    parity   - Design-to-implementation fidelity check (requires --image2)
    creative - Creative director taste review (vibe, feel, emotional impact)

Options:
    --image PATH        Primary screenshot (required)
    --image2 PATH       Second image for compare/parity modes
    --context PATH      Source files to include (repeatable)
    --description TEXT   What the screenshot shows
    --model MODEL       Gemini model (default: gemini-2.5-flash)
    --temperature FLOAT  Generation temperature (default: 0.2)

Environment:
    GEMINI_API_KEY      Required. Google AI Studio API key.

Examples:
    # QA audit of a dashboard screenshot
    python gemini-review.py --mode qa --image /tmp/dashboard.png --description "Admin dashboard at 1440px"

    # Before/after comparison
    python gemini-review.py --mode compare --image /tmp/before.png --image2 /tmp/after.png

    # Accessibility audit with source context
    python gemini-review.py --mode a11y --image /tmp/form.png --context src/Form.tsx --context src/form.css

    # Design-to-implementation parity (image = implementation, image2 = design reference)
    python gemini-review.py --mode parity --image /tmp/impl.png --image2 /tmp/figma.png

    # Creative director review — taste and feel
    python gemini-review.py --mode creative --image /tmp/landing.png --description "SaaS landing page, intended vibe: premium and confident"
"""

import argparse
import base64
import json
import os
import sys
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# System prompts for each review mode
# ---------------------------------------------------------------------------

SYSTEM_PROMPTS = {
    "qa": """You are an expert visual design reviewer. Analyze the provided screenshot for design quality issues.

Check these categories:
1. **Spacing & Alignment** — Inconsistent margins/padding, misaligned elements, uneven gaps
2. **Typography** — Font size hierarchy, line height, letter spacing, font weight consistency, truncation
3. **Color & Contrast** — Color consistency, sufficient contrast, proper use of color palette
4. **Layout & Composition** — Visual balance, content hierarchy, responsive behavior clues, whitespace usage
5. **Interactive Elements** — Button sizing, clickable area adequacy, hover/focus state hints, form field styling
6. **Polish & Details** — Border radius consistency, shadow consistency, icon sizing, image quality, pixel-level issues

Output format — group findings by severity:

## Critical Issues
Issues that break usability or look clearly wrong. Each entry:
- **What**: Description of the issue
- **Where**: On-screen location (e.g., "top-right card, second row")
- **Fix**: Specific CSS/styling fix suggestion

## Major Issues
Noticeable design inconsistencies. Same format as above.

## Minor Issues
Polish items and nitpicks. Same format as above.

## Summary
One-paragraph overall assessment. Note what looks good too.

If a category has no issues, omit it. Be specific about locations — reference visible text labels, positions, and element types. Suggest concrete CSS property changes where possible.""",

    "compare": """You are an expert visual design reviewer performing a before/after comparison.

Image 1 = BEFORE state. Image 2 = AFTER state.

Identify every visual difference between the two images and classify each as:
- **Intentional Improvement** — A deliberate positive change
- **Regression** — Something that got worse or broke
- **Neutral Change** — Different but neither better nor worse

Check for:
1. **Structural Changes** — Added/removed/moved elements, layout shifts
2. **Styling Changes** — Colors, fonts, spacing, borders, shadows, sizing
3. **Content Changes** — Text differences, image changes, icon changes
4. **State Changes** — Loading states, selections, hover effects, scroll position

Output format:

## Improvements
- **What changed**: Description
- **Where**: Location in the UI
- **Assessment**: Why this is better

## Regressions
- **What changed**: Description
- **Where**: Location in the UI
- **Impact**: What's worse and why
- **Fix**: How to address it

## Neutral Changes
- Brief list of other differences noted

## Summary
Overall assessment — did the AFTER state improve on the BEFORE state? Any regressions that need attention?""",

    "a11y": """You are a WCAG 2.1 AA accessibility auditor performing a visual accessibility review of a screenshot.

Check these areas:
1. **Color Contrast** — Text/background contrast ratios (4.5:1 for normal text, 3:1 for large text per WCAG 1.4.3). Non-text contrast for UI components (3:1 per WCAG 1.4.11).
2. **Text Readability** — Font sizes (minimum 16px body recommended), line height (1.5x minimum per WCAG 1.4.12), paragraph width (80 characters max per WCAG 1.4.8)
3. **Touch/Click Targets** — Minimum 44x44px for touch targets (WCAG 2.5.5), adequate spacing between interactive elements
4. **Visual Structure** — Heading hierarchy visible in design, logical reading order, content grouping, landmark regions
5. **Information Conveyed by Color** — Any information conveyed by color alone without secondary indicator (WCAG 1.4.1)
6. **Focus Indicators** — Visible focus styles if interactive states are shown
7. **Motion & Animation** — Any auto-playing content, animation that could trigger vestibular issues

Output format:

## Critical (Must Fix)
- **Issue**: Description
- **WCAG Criterion**: e.g., "1.4.3 Contrast (Minimum)"
- **Where**: Location in the UI
- **Remediation**: Specific fix

## Serious (Should Fix)
Same format as above.

## Advisory (Consider)
Same format as above.

## Passes
Brief list of accessibility aspects that look correct.

## Summary
Overall accessibility posture. Estimated percentage of WCAG 2.1 AA criteria that appear to be met based on visual inspection alone. Note that this is a visual-only audit — programmatic checks (screen reader, DOM) are also needed for full compliance.""",

    "parity": """You are a design QA engineer checking implementation fidelity against a design reference.

Image 1 = IMPLEMENTATION (what was built). Image 2 = DESIGN REFERENCE (the intended design, e.g., from Figma).

Compare every visual detail and report discrepancies:

1. **Spacing** — Margins, padding, gaps between elements
2. **Typography** — Font family, size, weight, line height, letter spacing, color
3. **Colors** — Background colors, text colors, border colors, shadow colors
4. **Layout** — Element positioning, sizing, proportions, alignment
5. **Visual Details** — Border radius, shadows, opacity, icons, images, decorative elements
6. **Content** — Text content differences, placeholder text, missing/extra elements

Output format:

## Discrepancies

### Critical (Clearly Wrong)
- **Element**: What element is affected
- **Expected** (from design): What it should look like
- **Actual** (in implementation): What it looks like
- **Fix**: CSS/code change needed

### Notable (Visible Difference)
Same format.

### Minor (Subtle)
Same format.

## Matches
List aspects where implementation matches the design well.

## Fidelity Score
Rate the implementation fidelity as a percentage (0-100%) with brief justification.
- 95-100%: Pixel-perfect or near-perfect
- 85-94%: Very close, minor differences
- 70-84%: Good but noticeable gaps
- Below 70%: Significant deviations

## Summary
Overall assessment and prioritized list of fixes to achieve higher fidelity.""",

    "creative": """You are a senior creative director reviewing a UI design. You have 20+ years of experience shaping the visual identity of beloved products. You care about taste, feel, and emotional resonance — not pixel-level QA.

Do NOT act like a QA engineer. Do not measure spacing or check alignment grids. Instead, react to this design the way a creative director would in a critique: with gut instinct backed by deep experience.

Evaluate:

1. **First Impression** — What do you feel in the first 2 seconds? What's the emotional response? Does the design have a clear point of view or does it feel committee-designed?

2. **Visual Hierarchy & Flow** — Does your eye move naturally through the content? Is there a clear story being told? Does the most important thing feel like the most important thing, or does everything compete for attention?

3. **Personality & Distinctiveness** — Does this have a voice, or could it be any product? Would you remember this design tomorrow? What specific choices give it character (or what's missing)?

4. **Craft & Confidence** — Does the design feel intentional and considered, or tentative and template-driven? Are typographic choices doing real work or just filling space? Do the colors feel curated or default?

5. **Emotional Tone** — What mood does this create? Is that mood appropriate for what it's trying to be? If the user provided a description of the intended vibe, does the execution deliver it?

6. **The "Would I Ship This?" Test** — If this landed on your desk, what would you push back on before it goes live? What's the one change that would elevate this the most?

Output format:

## Gut Reaction
2-3 sentences. Your honest first impression — how it makes you feel and what it communicates.

## What's Working
Things that show real design thinking. Be specific about what choices are strong and why.

## What's Holding It Back
The subjective issues — things that make it feel generic, uncertain, flat, or off-tone. For each:
- **Issue**: What you're reacting to
- **Why it matters**: The effect on the overall feel
- **Direction**: A creative direction to explore (not a CSS fix — a design idea)

## The One Thing
If you could only change one thing to meaningfully elevate this design, what would it be? Be opinionated.

## Vibe Check
One sentence: does this feel like a finished product someone would be proud to put their name on, or does it feel like a work in progress?

Be honest and direct. Great creative direction is specific, opinionated, and actionable — not vague praise or generic criticism. Reference what you actually see. If it's genuinely good, say so and explain why. If it feels like a template, say that too.""",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def detect_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    mime = MIME_TYPES.get(ext)
    if not mime:
        print(f"Error: Unsupported image format '{ext}'. Use png, jpg, or webp.", file=sys.stderr)
        sys.exit(1)
    return mime


def encode_image(path: str) -> tuple[str, str]:
    """Return (base64_data, mime_type) for an image file."""
    if not os.path.isfile(path):
        print(f"Error: Image not found: {path}", file=sys.stderr)
        sys.exit(1)
    mime = detect_mime(path)
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("ascii")
    return data, mime


def read_context_file(path: str) -> str | None:
    """Read a source file and return its contents, or None on failure."""
    try:
        with open(path, "r") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"Warning: Could not read context file '{path}': {e}", file=sys.stderr)
        return None


def build_request(args, system_prompt: str) -> dict:
    """Build the Gemini API request payload."""
    # User content parts
    parts = []

    # Description text
    if args.description:
        parts.append({"text": f"Description: {args.description}"})

    # Primary image
    img_data, img_mime = encode_image(args.image)
    parts.append({
        "inlineData": {
            "mimeType": img_mime,
            "data": img_data,
        }
    })

    # Second image (compare / parity)
    if args.image2:
        img2_data, img2_mime = encode_image(args.image2)
        if args.mode == "compare":
            parts.append({"text": "Second image (AFTER state):"})
        elif args.mode == "parity":
            parts.append({"text": "Second image (DESIGN REFERENCE):"})
        parts.append({
            "inlineData": {
                "mimeType": img2_mime,
                "data": img2_data,
            }
        })

    # Source context files
    if args.context:
        for ctx_path in args.context:
            content = read_context_file(ctx_path)
            if content:
                parts.append({"text": f"Source file `{ctx_path}`:\n```\n{content}\n```"})

    # Mode-specific user instruction
    mode_instructions = {
        "qa": "Perform a visual quality audit of this screenshot.",
        "compare": "Compare these two screenshots (before/after) and identify all differences.",
        "a11y": "Perform a WCAG 2.1 AA visual accessibility audit of this screenshot.",
        "parity": "Compare the implementation screenshot against the design reference and report all discrepancies.",
        "creative": "Give me your creative director's take on this design. Be honest and opinionated.",
    }
    parts.append({"text": mode_instructions[args.mode]})

    return {
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": [
            {
                "role": "user",
                "parts": parts,
            }
        ],
        "generationConfig": {
            "temperature": args.temperature,
            "maxOutputTokens": 8192,
        },
    }


def call_gemini(payload: dict, model: str, api_key: str) -> str:
    """Send request to Gemini REST API and return the text response."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"Error: Gemini API returned HTTP {e.code}", file=sys.stderr)
        try:
            err = json.loads(error_body)
            msg = err.get("error", {}).get("message", error_body)
            print(f"  {msg}", file=sys.stderr)
        except json.JSONDecodeError:
            print(f"  {error_body[:500]}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: Could not reach Gemini API: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except TimeoutError:
        print("Error: Gemini API request timed out (120s).", file=sys.stderr)
        sys.exit(1)

    # Extract text from response
    try:
        candidates = body.get("candidates", [])
        if not candidates:
            block_reason = body.get("promptFeedback", {}).get("blockReason", "unknown")
            print(f"Error: No response from Gemini. Block reason: {block_reason}", file=sys.stderr)
            sys.exit(1)
        text_parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in text_parts)
    except (KeyError, IndexError) as e:
        print(f"Error: Unexpected Gemini response format: {e}", file=sys.stderr)
        print(f"  Response: {json.dumps(body)[:500]}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Send screenshots to Gemini for visual design analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["qa", "compare", "a11y", "parity", "creative"],
        help="Review mode: qa (quality audit), compare (before/after diff), a11y (accessibility), parity (design fidelity), creative (taste/vibe review)",
    )
    parser.add_argument(
        "--image",
        required=True,
        help="Path to primary screenshot (png, jpg, or webp)",
    )
    parser.add_argument(
        "--image2",
        help="Path to second image (required for compare and parity modes)",
    )
    parser.add_argument(
        "--context",
        action="append",
        help="Source file to include for context (repeatable)",
    )
    parser.add_argument(
        "--description",
        help="What the screenshot shows (e.g., 'Dashboard at 1440px')",
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-flash",
        help="Gemini model to use (default: gemini-2.5-flash)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Generation temperature (default: 0.2)",
    )

    args = parser.parse_args()

    # Validate mode-specific requirements
    if args.mode in ("compare", "parity") and not args.image2:
        parser.error(f"--image2 is required for {args.mode} mode")

    # Creative mode uses higher temperature by default for more opinionated output
    if args.mode == "creative" and "--temperature" not in sys.argv:
        args.temperature = 0.7

    # Check API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set.", file=sys.stderr)
        print("  Get a key at https://aistudio.google.com/apikey", file=sys.stderr)
        sys.exit(1)

    # Build and send request
    system_prompt = SYSTEM_PROMPTS[args.mode]
    payload = build_request(args, system_prompt)
    result = call_gemini(payload, args.model, api_key)

    print(result)


if __name__ == "__main__":
    main()
