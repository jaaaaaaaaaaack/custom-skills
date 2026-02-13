# Design Review Skill — Design Document

## Problem

Claude is unreliable at visually assessing its own work. When it makes CSS/styling changes and takes a verification screenshot, it routinely gives false positives — claiming issues are fixed when clear visual defects remain. This applies across all categories: layout, spacing, colors, gradients, overlapping elements, icons, and general visual design quality.

The existing design-review skill (a first attempt) works as a manually-invoked tool but doesn't solve this problem because agents don't know to use it. They happily self-assess and move on.

## Solution

A new design-review skill built around **verification-first** philosophy. The skill's primary innovation is behavioral: its SKILL.md teaches agents that they cannot trust their own visual assessment and must delegate verification screenshots to Gemini.

### Core Rule

> **You cannot visually verify your own work.** Whenever you take a screenshot to verify visual changes, send it to Gemini using this skill instead of assessing it yourself.

The trigger is **the act of taking a verification screenshot**, not every CSS change. If the agent makes a color tweak and doesn't screenshot, no Gemini call. If it screenshots to check its work, that screenshot goes to Gemini.

### When to Skip Gemini

- Pure logic changes with no visual impact (API calls, state management, data processing)
- Text-only content changes where visual layout isn't affected
- When the user explicitly says to skip

## Modes

Four modes, each tied to a workflow stage:

### verify (the workhorse)

- **Question**: "Did my change actually fix it?"
- **Images**: 1 screenshot
- **Model**: gemini-2.5-flash (speed matters in the fix loop)
- **Temperature**: 0.2
- **Output**: Structured JSON with top-level `passed` boolean
- **Focus parameter**: Optional `--focus` for targeted verification of a specific change. Without it, falls back to general scan.

The verify prompt biases Gemini toward flagging rather than approving — a false pass is worse than a false flag. This directly counters Claude's tendency toward false positives.

**Focus parameter guidance**: Agents describe the expected result in visual terms Gemini can evaluate from a screenshot. Visual language, not code language:
- Good: "Cards should have equal gaps between them"
- Good: "Modal should be vertically centered with no content overflowing"
- Good: "Navigation items should be evenly spaced and horizontally aligned"
- Bad: "gap should be 16px" (Gemini can't measure pixels precisely)
- Bad: "button should be cyan-400" (token names are meaningless to Gemini)

**With focus**: Gemini primarily evaluates the specific concern, plus a quick regression scan of the surrounding area. `passed` answers "did this fix land?"

**Without focus**: Gemini does a general visual scan (audit-lite). `passed` answers "are there any obvious defects?"

### compare

- **Question**: "Did I improve things or introduce regressions?"
- **Images**: before + after screenshots
- **Model**: gemini-2.5-flash
- **Temperature**: 0.2
- **Output**: Structured JSON (improvements, regressions, unchanged issues)

### audit

- **Question**: "What's wrong with this page?"
- **Images**: 1 screenshot
- **Model**: gemini-2.5-pro (thoroughness over speed)
- **Temperature**: 0.3
- **Output**: Structured JSON (issues grouped by severity, plus strengths)

For initial assessment of a page, not for the fix loop. Comprehensive six-category review: spacing & alignment, typography, color & contrast, layout & composition, interactive elements, polish & details.

### parity

- **Question**: "Does this match the design?"
- **Images**: implementation + design reference
- **Model**: gemini-2.5-pro
- **Temperature**: 0.2
- **Output**: Structured JSON (discrepancies + fidelity score 0-100%)

## Output Schemas

All modes return structured JSON by default (overridable to raw markdown with `--raw`).

### verify

```json
{
  "passed": false,
  "summary": "Two spacing issues in the card grid",
  "issues": [
    {
      "severity": "critical | major | minor",
      "category": "spacing | layout | color | typography | visual | content",
      "description": "Cards in second row have noticeably larger gaps than first row",
      "location": "Card grid, second row",
      "suggestion": "Check gap/margin on the grid container"
    }
  ]
}
```

### compare

```json
{
  "summary": "Fix resolved the spacing issue, no regressions detected",
  "improvements": [
    { "description": "...", "location": "..." }
  ],
  "regressions": [
    { "description": "...", "location": "...", "severity": "critical | major | minor" }
  ],
  "unchanged_issues": [
    { "description": "...", "location": "..." }
  ]
}
```

### audit

```json
{
  "summary": "Overall assessment paragraph",
  "critical": [
    { "category": "...", "description": "...", "location": "...", "suggestion": "..." }
  ],
  "major": [ "..." ],
  "minor": [ "..." ],
  "strengths": ["What looks good"]
}
```

### parity

```json
{
  "summary": "Overall fidelity assessment",
  "fidelity_score": 82,
  "discrepancies": [
    {
      "severity": "critical | notable | minor",
      "element": "Header navigation",
      "expected": "What the design shows",
      "actual": "What the implementation shows",
      "suggestion": "..."
    }
  ],
  "matches": ["Aspects that match well"]
}
```

## System Prompts

### Shared Preamble (all modes)

> You are reviewing a static screenshot of a web interface. You can observe spatial relationships, colors, typography, alignment, and visual hierarchy. You cannot see the code, interact with the page, or observe hover/focus/animation states.
>
> The developer has full codebase context that you lack. Your observations about what you see are reliable. Your suggestions about specific CSS properties or implementation details are informed guesses — label them as such.
>
> Be precise about locations. Reference visible text labels, element types, and positions (e.g., "the third card in the top row," "the submit button below the email field"). Vague locations like "some elements" are not useful.

### Mode-Specific Prompt Philosophy

- **verify**: Terse and binary. "Look for anything visually wrong. Be harsh — a false pass is worse than a false flag. If something looks even slightly off, report it." When `--focus` is provided, primary evaluation targets the specific concern with a quick regression scan of surrounding area.
- **compare**: Forensic. "Identify every visual difference. Classify each as improvement, regression, or neutral. Pay special attention to areas adjacent to the change — regressions often appear in nearby elements."
- **audit**: Comprehensive. Six categories (spacing, typography, color, layout, interactive elements, polish). Thorough rather than fast.
- **parity**: Measurement-oriented. "Compare every visual detail against the reference. Report discrepancies with what you see in each image."

## CLI Interface

```bash
# Verify after a fix (the common case)
python review.py --mode verify --image /tmp/screenshot.png

# Targeted verify with focus
python review.py --mode verify --image /tmp/screenshot.png \
  --focus "Cards should have equal gaps and align to the grid"

# Before/after comparison
python review.py --mode compare --image /tmp/before.png --image2 /tmp/after.png

# Full audit
python review.py --mode audit --image /tmp/page.png --description "Dashboard at 1440px"

# Design parity
python review.py --mode parity --image /tmp/impl.png --image2 /tmp/figma.png

# Common optional flags
--context src/Card.tsx        # Source file for richer suggestions (repeatable)
--description "..."           # What the screenshot shows
--model gemini-2.5-pro        # Override model default
--raw                         # Force raw markdown output instead of JSON
```

## Architecture

### File Structure

```
design-review/
├── SKILL.md                  # Agent-facing behavioral contract + usage guide
├── README.md                 # User-facing setup & CLI reference
├── requirements.txt          # google-genai
├── scripts/
│   └── review.py             # Main analysis engine
└── references/
    └── learnings.md          # Accumulated observations from past reviews
```

### Technical Details

- **SDK**: google-genai (matches animation-review)
- **Structured output**: `response_mime_type="application/json"` + `response_schema` for all modes
- **System instruction**: Shared preamble + mode-specific prompt, passed via `system_instruction` parameter
- **Image handling**: `Part.from_bytes()` with correct MIME type detection (png/jpg/webp)
- **Fallback**: If structured output fails, retry with raw text

### Results Persistence

Directory: `.design-review/`

```
.design-review/
  2026-02-13_143200_verify.json
  2026-02-13_143200_verify.png
  2026-02-13_144500_compare.json
  2026-02-13_144500_compare_before.png
  2026-02-13_144500_compare_after.png
```

- Auto-creates directory on first run
- Auto-adds to `.gitignore`
- Auto-cleans files older than 14 days
- Screenshots copied (not moved) since agent may reference them again

### Deployment

Global via symlink (same pattern as animation-review):
```
~/.claude/skills/design-review → /Users/jack/Projects/custom-skills/design-review
```

Replaces the existing design-review skill at `~/.claude/skills/design-review/`.

## Relationship to Other Skills

### vs animation-review

No conflict. Different inputs (screenshot vs video), different concerns (static visual quality vs temporal behavior). Frontmatter descriptions make the distinction clear. An agent working on something with both static and animated aspects would use both skills sequentially.

### vs the old design-review

Full replacement. The old skill's modes (qa, compare, a11y, parity, creative) are replaced by the new mode set. The old skill's learnings.md carries over. a11y and creative modes are excluded from initial scope — can be added later.

## Design Principles

1. **Gemini is eyes, not hands** — Observations are reliable, implementation suggestions are hypotheses from an observer without code context.
2. **False pass is the worst outcome** — verify mode biases toward flagging. Better to investigate a false flag than miss a real defect.
3. **Visual language, not code language** — Focus descriptions and Gemini's output use what's visible, not what's in the source.
4. **Speed in the loop, depth on demand** — verify/compare use flash for fast iteration. audit/parity use pro for thoroughness.
5. **The SKILL.md is the product** — The script is plumbing. The behavioral contract that teaches agents to distrust their own eyes is the real value.

## Verify-Fix Loop

The core workflow the SKILL.md teaches:

1. Agent makes visual changes
2. Agent takes a verification screenshot (its existing behavior)
3. Instead of self-assessing, agent runs `verify` mode with the screenshot
4. If `passed: false` → agent fixes reported issues → go to step 2
5. If `passed: true` → done

Stop condition: no critical or major issues. Minor issues are optional polish unless the user wants perfection.
