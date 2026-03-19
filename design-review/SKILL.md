---
name: design-review
description: Delegate visual design analysis to Gemini. Use when reviewing screenshots for quality (qa), taste (creative), accessibility (a11y), before/after comparison (compare), or design-to-implementation fidelity (parity). Invoke with "/design-review".
---

# Design Review — Gemini Visual Analysis

Delegate screenshot analysis to Gemini for a second pair of eyes on visual design issues.

## When to Use

Use this skill when you have a screenshot and need visual analysis that benefits from strong spatial reasoning — spacing alignment, design fidelity, accessibility, or before/after regression checking.

## Prerequisites

- `GEMINI_API_KEY` environment variable set (get one at https://aistudio.google.com/apikey)
- Python 3.10+ available
- Screenshots as png, jpg, or webp files

## Mode Selection

| Situation | Mode | Images needed |
|-----------|------|---------------|
| "Does this look good?" (technical) | `qa` | 1 screenshot |
| "Does this *feel* good?" (taste) | `creative` | 1 screenshot |
| "Did my changes break anything?" | `compare` | before + after |
| "Is this accessible?" | `a11y` | 1 screenshot |
| "Does this match the design?" | `parity` | implementation + design reference |

**`qa` vs `creative`**: Use `qa` when you need to catch spacing/alignment/consistency bugs. Use `creative` when you need the "is this actually good?" gut check — especially early in development, during vibe-coding, or when there's no polished Figma reference to compare against. `creative` gives design direction; `qa` gives CSS fixes.

## Usage

```bash
# Visual quality audit
python ~/.claude/skills/design-review/scripts/gemini-review.py \
  --mode qa --image /tmp/screenshot.png

# Before/after comparison
python ~/.claude/skills/design-review/scripts/gemini-review.py \
  --mode compare --image /tmp/before.png --image2 /tmp/after.png

# Accessibility audit with source context
python ~/.claude/skills/design-review/scripts/gemini-review.py \
  --mode a11y --image /tmp/page.png --context src/Page.tsx

# Design-to-implementation parity
python ~/.claude/skills/design-review/scripts/gemini-review.py \
  --mode parity --image /tmp/implementation.png --image2 /tmp/figma-export.png

# Creative director review — taste, feel, vibe
python ~/.claude/skills/design-review/scripts/gemini-review.py \
  --mode creative --image /tmp/landing.png --description "SaaS landing page, intended vibe: premium and confident"

# Add description for better context
python ~/.claude/skills/design-review/scripts/gemini-review.py \
  --mode qa --image /tmp/dashboard.png --description "Admin dashboard at 1440px width"
```

## What Context to Pass (Per Mode)

Each mode needs different context from you. Don't just dump the same files every time.

| Mode | `--description` | `--context` files | Notes |
|------|----------------|-------------------|-------|
| `qa` | What the page/component is, viewport width | Component TSX/CSS that produced the screenshot | Source helps Gemini map visual issues to specific CSS properties. Keep it focused — the file(s) that own the layout, not the whole app. |
| `creative` | **Critical.** The intended vibe, audience, product type, comparable products ("Linear meets Stripe", "playful fintech for millennials") | Skip source files — they're noise for taste feedback. If there's a brand doc or moodboard reference, mention it in description instead. | The description *is* the context. Without it, Gemini has no idea what "good" means for your product. |
| `compare` | What changed and why ("added hero section", "fixed card layout") | Only if a code change caused a regression you want diagnosed | Gemini can see the diff visually — description helps it understand intent so it can judge whether changes are improvements. |
| `a11y` | Page type and primary user action ("checkout form", "settings panel") | HTML-producing components (JSX/templates) — Gemini can infer DOM structure and missing semantics | Semantic structure matters more than styling here. |
| `parity` | Which part of the design system this implements | The component source, plus any design token/theme files | Helps Gemini distinguish "wrong value" from "hasn't been tokenized yet." |

### `--description` tips for creative mode

Bad: `"Homepage screenshot"`
Good: `"SaaS landing page for a developer tool. Intended vibe: technical but warm, like Vercel or Railway. Target audience: senior engineers evaluating tools."`

The more specific you are about intent, the more useful the taste feedback. If the user hasn't stated a vibe, ask them before running creative mode.

## The Review-Fix-Verify Loop

This is the core workflow. Follow it whenever fixing visual issues:

0. **Check learnings** — Read `references/learnings.md` for relevant past observations before choosing mode/context
1. **Capture** — Take a screenshot (Playwright, Figma MCP, or manual)
2. **Review** — Run gemini-review.py in the appropriate mode
3. **Fix** — Apply fixes for critical and major issues found
4. **Re-capture** — Take a new screenshot after fixes
5. **Verify** — Run `compare` mode with before/after screenshots to confirm fixes and check for regressions
6. **Repeat** — If critical/major issues remain, loop back to step 3

Stop when: no critical or major issues remain. Minor issues are optional polish.

## Figma Context Pipeline

When a Figma design is involved, gather context from figma-console MCP **before** calling gemini-review. What to pull depends on the mode.

### For `parity` mode (implementation vs design)

1. **Capture the design reference** — `figma_capture_screenshot` or `figma_take_screenshot` of the target component/frame. Save as the `--image2` path.
2. **Get component specs** — `figma_get_component_for_development` on the target component. This returns spacing, typography, color values — write it to a temp file and pass as `--context`.
3. **Get design tokens** — `figma_get_token_values` for the relevant collection. Pass as `--context` so Gemini can distinguish "wrong value" from "value not tokenized yet."
4. **Capture implementation** — Playwright screenshot → `--image`.

```bash
# After gathering Figma context into /tmp/figma-specs.txt and screenshots
python ~/.claude/skills/design-review/scripts/gemini-review.py \
  --mode parity \
  --image /tmp/implementation.png \
  --image2 /tmp/figma-capture.png \
  --context /tmp/figma-specs.txt \
  --description "ProfileCard component, part of user-settings design system page"
```

### For `qa` mode (with Figma as source of truth)

1. **Get design token values** — `figma_get_token_values` for the relevant tokens (spacing, colors, typography). Write to a temp file.
2. **Get component details** — `figma_get_component_details` if reviewing a specific component. Include sizing/padding constraints.
3. Pass both as `--context`. This lets Gemini flag not just "this spacing looks off" but "this is 16px but should be 24px per your spacing scale."

### For `creative` mode (Figma as mood reference)

Don't pass specs — they'll anchor Gemini in measurement mode. Instead:
1. **Get the design system summary** — `figma_get_design_system_summary` for a high-level sense of the brand.
2. Summarize it in `--description`: "Design system uses Inter/600 headings, muted blue palette, 8px grid, minimal borders — going for a calm, professional feel."
3. If there's a reference screen in Figma that nails the intended vibe, capture it as `--image2` and use `compare` mode instead — "does the implementation carry the same energy as this reference?"

### For `a11y` mode

1. **Get component details** — `figma_get_component_for_development` to check if the design specifies focus states, ARIA roles, or interaction patterns.
2. Pass as `--context` — helps Gemini distinguish "missing from implementation" vs "missing from design."

## Integration with Other Skills

### webapp-testing → design-review
After taking a Playwright screenshot, pipe the path to gemini-review:
```bash
python ~/.claude/skills/design-review/scripts/gemini-review.py --mode qa --image /tmp/screenshot.png
```

### frontend-design → design-review
After building UI with the frontend-design skill, run a QA review. For vibe-coding without a Figma reference, use creative mode first, then qa for polish:
```bash
# First pass — is the direction right?
python ~/.claude/skills/design-review/scripts/gemini-review.py \
  --mode creative --image /tmp/built-ui.png \
  --description "Developer dashboard, intended vibe: technical but approachable, like Linear"

# Second pass — catch technical issues
python ~/.claude/skills/design-review/scripts/gemini-review.py \
  --mode qa --image /tmp/built-ui.png --context src/components/Card.tsx
```

### figma → design-review (full parity workflow)
```bash
# 1. Claude captures Figma reference via figma_capture_screenshot → /tmp/figma.png
# 2. Claude gets specs via figma_get_component_for_development → /tmp/specs.txt
# 3. Claude captures implementation via Playwright → /tmp/impl.png
# 4. Run parity check with full context
python ~/.claude/skills/design-review/scripts/gemini-review.py \
  --mode parity --image /tmp/impl.png --image2 /tmp/figma.png \
  --context /tmp/specs.txt
```

### Self-verification loop
Use compare mode to verify your own fixes didn't regress anything:
```bash
python ~/.claude/skills/design-review/scripts/gemini-review.py \
  --mode compare --image /tmp/before-fix.png --image2 /tmp/after-fix.png
```

## Learning from Results

Read `~/.claude/skills/design-review/references/learnings.md` before each review to apply past lessons.

### Timing — when to write learnings

**Do NOT update learnings immediately after Gemini responds.** Gemini's output is not the outcome — the user's reaction is. Wait for signal from the user before writing anything.

Signals that indicate an outcome:
- **User says "looks good" / accepts fixes / moves on** → successful review, consider logging what worked
- **User disagrees with a finding** ("that's intentional", "no, that's fine") → log the disagreement and what Gemini got wrong
- **User asks to re-run with different settings** → log what didn't work about the first attempt
- **You had to re-run the review yourself** (compare mode found regressions from your fixes) → log what the first pass missed
- **User ignores Gemini's output entirely** → probably not useful feedback, don't log

If there's no clear signal either way, don't write a learning. Silence is not a signal.

### What to log

**After a successful review** (user accepts findings, fixes work on first pass):
- Note what mode + context combination worked well
- Note if the `--description` framing was particularly effective

**After a failed or repeated review** (user pushes back, findings were off-base, had to re-run):
- What went wrong? Wrong mode? Missing context? Gemini hallucinated an issue?
- What did you change on the retry that fixed it?

**When user explicitly disagrees with Gemini's feedback**:
- Was Gemini wrong, or was it a taste difference? Both are worth recording.
- If wrong: log it as a blind spot (e.g., "Gemini flags dark-on-dark as contrast issue when it's intentional")
- If taste difference: log the user's actual preference for future calibration

**When you notice a pattern across reviews**:
- Same issue keeps appearing (e.g., "border-radius inconsistency" in every review)
- A certain mode consistently under/over-performs for a type of UI
- Certain context files are always needed or always noise

### What NOT to log

- Don't log every review — only when there's a genuine insight
- Don't log raw Gemini output — summarize the lesson
- Don't log project-specific details that won't generalize
- Don't log anything before the user has reacted

### Format

Keep entries concise. Add them under the appropriate section heading in `learnings.md`. One or two sentences per observation. Include the mode used when relevant.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `GEMINI_API_KEY not set` | Export the key: `export GEMINI_API_KEY=your-key` |
| Rate limit errors (429) | Wait 60s and retry, or switch to a different model with `--model` |
| Large image errors | Resize to under 4MB before sending. Crop to the relevant area. |
| Timeout (120s) | Image may be too large, or try `--model gemini-2.5-flash` for faster response |
| Unexpected format | Check `references/system-prompts.md` and adjust prompts in the script if needed |

## Prompt Customization

System prompts are hardcoded in `gemini-review.py`. See `references/system-prompts.md` for documentation on each prompt and common customizations (brand guidelines, stricter a11y, custom scoring).
