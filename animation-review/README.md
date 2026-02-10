<p align="center">
  <img src="animation-review_thumb.png" alt="animation-review" width="100%">
</p>

# Animation Review

Get detailed, frame-level feedback for your web animations to massively simplify the process of tweaking and debugging. 

What this skill does:
- Records a specific interaction in the browser using Playwright (or you can point it at an existing video file)
- Chooses the best mode for the task (see below)
- Automatically trims the video to save time and tokens, then sends it to Gemini with relevant context + a mode-specific instructions
- Gemini provides structured analysis, from a quick sanity check to frame-by-frame bug diagnosis.

Agents can also use **escalation**: they can choose to start with a quick 5fps check, then target specific time ranges at 24fps when something needs closer inspection. No re-recording needed, Gemini clips it to the refined time range server-side.

Tested with Claude Code, but it should also work with any agent that supports skills, the installation process might just need a bit of tweaking for your specific IDE/Agent. It's also usable standalone via CLI.

**👉 Preview before you install:** A full workflow (user prompt, recorded clip, prompt sent to Gemini, and the diagnose-style response) is in the repo: [Examples/animation-review_workflow-example.md](https://github.com/jaaaaaaaaaaack/custom-skills/blob/main/Examples/animation-review_workflow-example.md).

## Modes

The skill automatically handles selecting the right level of analysis, and adjusts the instructions and context it passes to Gemini accordingly. If you prefer, you can specify a mode explicitly.

| Mode | FPS | Model | |
|------|-----|-------|-|
| **check** | 5 | Gemini 2.5 Flash | *"Does it work?"* — Quick pass/fail. Animations fire, complete, nothing visually breaks. |
| **review** | 12 | Gemini 2.5 Flash | *"How does it feel?"* — Easing, timing, choreography, overall polish. Scored 1–10 against production standards. |
| **diagnose** | 24 | Gemini 2.5 Pro | *"What's going wrong?"* — Frame-by-frame bug analysis with timestamps, pixel positions, and visual evidence for debugging. |
| **inspire** | 24 | Gemini 2.5 Pro | *"How do I recreate this?"* — Decompose a reference video into a technology-agnostic animation spec. |


## Setup

### 1. Install the skill

```bash
npx skills add jaaaaaaaaaaack/custom-skills
```

### 2. Install dependencies

The skill needs Python packages and a Chromium browser for headless recording. The easiest way is to ask your agent to do it — **start a new session**, then say:

> Install the requirements and set up the animation-review skill

Your agent will find the right paths and install everything for you.

<details>
<summary>Or install manually</summary>

```bash
pip3 install -r ~/.claude/skills/animation-review/requirements.txt
python3 -m playwright install chromium
```

You'll also need [ffmpeg](https://ffmpeg.org/) for macOS screen recording (browser recording works without it):

```bash
brew install ffmpeg   # macOS
```

If the `pip3` command fails with "No such file or directory", the skill may have installed to `~/.agents/skills/` instead — check there.

</details>

---

### 3. Gemini API key

Add your API key to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.):

```bash
export GEMINI_API_KEY=your-key-here
```

<details>
<summary>How to generate a Gemini API key</summary>

Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

</details>

### 4. Restart your agent

Start a **new session** / reload your IDE for the skill to appear. It won't show up in an existing session.

---

## CLI usage (optional)

When installed as a skill, your agent handles recording and analysis automatically — just ask it to review an animation. **The commands below are only needed if you want to run the scripts directly.**

### 1. Record

#### Automated (recommended)

Use `record_browser.py` to drive a headless browser. Playwright records internally — no screen recording permissions needed.

```bash
# Record a page load animation
python3 scripts/record_browser.py http://localhost:3000

# Click a button, wait for animation
python3 scripts/record_browser.py http://localhost:3000 \
  -a 'click:.play-btn' -a 'wait:2000'

# Custom viewport size
python3 scripts/record_browser.py http://localhost:3000 -W 375 -H 812
```

#### Manual (macOS only)

Use `record.sh` when you need to interact with the browser yourself:

```bash
bash scripts/record.sh -d 10
```

#### Existing video

Already have a recording? Skip straight to analysis — pass any `.mp4`, `.mov`, or `.webm` file to `analyze.py`.

### 2. Analyze

```bash
# Review design quality
python3 scripts/analyze.py -t review -p "Cards should stagger in with a spring ease"

# Diagnose a bug at full precision
python3 scripts/analyze.py -t diagnose \
  -p "The carousel jumps unexpectedly at the end of the rotation"

# Zoom into a specific time range (saves tokens, improves accuracy)
python3 scripts/analyze.py -t diagnose --start 2s --end 5s \
  -p "Card jumps position at ~3s during close animation"
```

Use `--json` or `--raw` to override the default output format (structured JSON for check/review, raw text for diagnose/inspire).

### Compare providers

Swap the LLM backend with `--provider` to benchmark Gemini against [Kimi K2.5](https://platform.moonshot.ai). Same video, prompts, and schemas — only the API path changes. Requires `KIMI_API_KEY` and `ffmpeg`.

```bash
python3 scripts/analyze.py -t review -v recording.mp4 --provider kimi
```

See the [SKILL.md](animation-review/SKILL.md) provider comparison section for details.

## Interpreting results

Gemini's visual observations (what changed between frames, timing, positions) are reliable. Its theories about *why* something happens are hypotheses — it can't see your code, DOM structure, or CSS. The `diagnose` output separates these into distinct **Observations** and **Hypotheses** sections for this reason.

Treat observations as evidence. Treat hypotheses as leads to investigate.

## Troubleshooting

- **`ffmpeg not found`**: Ensure ffmpeg is installed and in your PATH.
- **`playwright not found`**: Run `pip3 install playwright`.
- **Browser doesn't launch**: Run `playwright install chromium`.
- **Screen recording fails** (`record.sh`): Grant Screen Recording permission to your terminal app / IDE in macOS System Settings.

## License

MIT
