# Animation Review

A Claude Code skill that reviews web animations by recording the browser and sending video to Gemini for analysis.

Claude drives a headless browser with Playwright, captures video of your animations, then sends it to Gemini's video understanding API for structured feedback — frame-level timing analysis, easing evaluation, bug diagnosis, or effect decomposition for recreation.

## How it works

Four analysis modes, each tuned to a different question:

| Mode | FPS | Model | Question |
|------|-----|-------|----------|
| **check** | 5 | Flash | "Does it work?" |
| **review** | 12 | Flash | "How does it feel?" |
| **diagnose** | 24 | Pro | "What's going wrong?" |
| **inspire** | 24 | Pro | "What's happening here?" |

The core workflow is escalation: run `check` or `review` on a full recording, then zoom into a specific time range with `diagnose` at 24fps if something needs closer inspection. Gemini clips server-side — no re-recording needed.

## Setup

### Prerequisites

- Python 3.8+
- [ffmpeg](https://ffmpeg.org/) (`brew install ffmpeg` on macOS)
- A [Gemini API key](https://aistudio.google.com/apikey)

### Install

```bash
pip install -r requirements.txt
playwright install chromium
```

### API key

Set your Gemini API key as an environment variable:

```bash
export GEMINI_API_KEY=your-key-here
```

Add this to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.) to persist it.

### Install as a Claude Code skill

Symlink this directory into your Claude Code skills folder:

```bash
mkdir -p ~/.claude/skills
ln -s /path/to/animation-review ~/.claude/skills/animation-review
```

Claude will automatically discover SKILL.md and use it when animation review is relevant.

## Usage

Once installed as a skill, Claude handles recording and analysis automatically. You can also run the scripts directly:

```bash
# Record a page load animation
python3 scripts/record_browser.py http://localhost:3000

# Record specific interactions
python3 scripts/record_browser.py http://localhost:3000 \
  -a 'click:.play-btn' -a 'wait:2000'

# Analyze with review mode
python3 scripts/analyze.py -t review -p "Cards should fade in with stagger"

# Diagnose a specific time range at 24fps
python3 scripts/analyze.py -t diagnose --start 2s --end 5s \
  -p "Card jumps position at ~3s during close animation"
```

## Important: interpreting results

Gemini's visual observations (what changed between frames, timing, positions) are reliable. Its theories about *why* something happens are hypotheses — it can't see your code, DOM structure, or CSS. The `diagnose` output separates these into distinct **Observations** and **Hypotheses** sections for this reason.

Treat observations as evidence. Treat hypotheses as leads to investigate.

## License

MIT
