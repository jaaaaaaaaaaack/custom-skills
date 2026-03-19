# System Prompts Reference

This documents the system prompts used by `gemini-review.py`. Read this when you need to understand what Gemini is being asked to do, or to customize prompts for a specific project.

All prompts are hardcoded in the script — this file is for reference only.

---

## `qa` — Visual Quality Audit

**Goal**: Catch spacing, alignment, typography, color, and polish issues in a single screenshot.

**Design rationale**: Groups output by severity (critical/major/minor) so Claude can prioritize fixes. Asks for specific CSS suggestions and on-screen locations so fixes can be applied without ambiguity.

**Six check categories**:
1. Spacing & Alignment
2. Typography
3. Color & Contrast
4. Layout & Composition
5. Interactive Elements
6. Polish & Details

**Output sections**: Critical Issues, Major Issues, Minor Issues, Summary. Each issue includes What, Where, and Fix fields.

---

## `compare` — Before/After Visual Diff

**Goal**: Given two screenshots (before/after), identify every difference and classify it.

**Design rationale**: The three-way classification (improvement/regression/neutral) prevents false alarms when intentional changes are flagged. Separates structural, styling, content, and state changes.

**Image mapping**: Image 1 = BEFORE, Image 2 = AFTER.

**Output sections**: Improvements, Regressions, Neutral Changes, Summary.

---

## `a11y` — WCAG 2.1 AA Accessibility Audit

**Goal**: Visual-only accessibility review referencing specific WCAG criteria.

**Design rationale**: Scoped to what's visually detectable — contrast ratios, target sizes, text sizing, color-only information. Explicitly notes that programmatic testing is also needed for full compliance.

**Seven check areas**:
1. Color Contrast (WCAG 1.4.3, 1.4.11)
2. Text Readability (WCAG 1.4.12, 1.4.8)
3. Touch/Click Targets (WCAG 2.5.5)
4. Visual Structure
5. Information Conveyed by Color (WCAG 1.4.1)
6. Focus Indicators
7. Motion & Animation

**Output sections**: Critical (Must Fix), Serious (Should Fix), Advisory (Consider), Passes, Summary.

---

## `parity` — Design-to-Implementation Fidelity

**Goal**: Compare a built UI against its design reference (typically a Figma export) and report every discrepancy.

**Design rationale**: Provides a fidelity score percentage as a concrete metric. Categorizes discrepancies so teams can triage. The score bands (95-100%, 85-94%, 70-84%, <70%) align with common QA acceptance thresholds.

**Image mapping**: Image 1 = IMPLEMENTATION, Image 2 = DESIGN REFERENCE.

**Six comparison dimensions**:
1. Spacing
2. Typography
3. Colors
4. Layout
5. Visual Details
6. Content

**Output sections**: Discrepancies (Critical/Notable/Minor), Matches, Fidelity Score, Summary.

---

## `creative` — Creative Director Taste Review

**Goal**: Subjective "is this actually good?" feedback that catches what rule-based reviews miss — lifeless layouts, template vibes, lack of personality, weak hierarchy.

**Design rationale**: The other modes are analytical (measuring against rules). This mode is editorial — it asks Gemini to react with taste and instinct, the way a creative director would in a design critique. Uses higher temperature (0.7 vs 0.2) to get more opinionated, less hedged output.

**When to use over `qa`**: Early in development, during vibe-coding without a Figma reference, or whenever you need to know "does this feel right?" rather than "is this pixel-correct?" The `qa` mode will tell you the padding is inconsistent; `creative` will tell you the design has no soul.

**Six evaluation areas**:
1. First Impression (emotional response, point of view)
2. Visual Hierarchy & Flow (eye movement, story, priorities)
3. Personality & Distinctiveness (voice, memorability, character)
4. Craft & Confidence (intentionality, typography, color curation)
5. Emotional Tone (mood, appropriateness for intended vibe)
6. The "Would I Ship This?" Test (the single highest-leverage change)

**Output sections**: Gut Reaction, What's Working, What's Holding It Back (with Issue/Why it matters/Direction), The One Thing, Vibe Check.

**Key difference from `qa`**: Suggestions are creative directions ("explore warmer tones to feel more approachable") not CSS fixes ("change color to #ff6b35"). Claude translates these directions into implementation.

---

## Customization

To modify prompts for a project, edit the `SYSTEM_PROMPTS` dict in `gemini-review.py`. Common customizations:

- **Add brand guidelines**: Append color palette / typography rules to the `qa` prompt
- **Stricter accessibility**: Change `a11y` to target WCAG AAA instead of AA
- **Custom scoring**: Adjust parity score bands to match your team's thresholds
- **Output format**: Change markdown structure if your tooling expects different formatting
