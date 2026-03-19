# Design Review — Learnings

Observations from past reviews. Read this before running a review to apply lessons learned. Update it after reviews based on outcomes.

## Mode Effectiveness
<!-- Which modes work well for which situations. Example:
- creative mode on dashboard UIs tends to flag "template feel" — useful early, less so after 2+ iterations
- qa mode misses hierarchy issues — pair with creative for first pass
-->

## Context That Helped
<!-- What description/context combinations produced useful results. Example:
- Parity mode: including design token file caught 3 spacing mismatches that were invisible without it
- Creative mode: describing the target audience ("senior engineers") got much better vibe feedback than just describing the product
-->

## Context That Didn't Help
<!-- What was noise or caused worse results. Example:
- Passing full page source (500+ lines) to qa mode — Gemini suggestions got generic. Focused component file worked better.
- Including unrelated component files diluted parity findings
-->

## Gemini Blind Spots
- Creative mode flagged an in-context editing toolbar as "visual density/clutter" — didn't recognize it as contextual UI that only appears when editing. Gemini treats visible controls as permanent, misses conditional states.

## Recurring Fixes
<!-- Patterns in what keeps coming up. Example:
- Border radius inconsistency between cards and buttons — keep appearing across projects
- Line-height on headings: Gemini flags this every time, usually correct
-->

## Workflow Notes
<!-- What review sequences work well. Example:
- For new pages: creative → fix direction → qa → fix details → compare to verify
- For bug fixes: compare mode alone is usually sufficient
- Parity mode works best when Figma frame is cropped to match implementation viewport
-->
