#!/usr/bin/env bash
# macOS only — uses avfoundation for screen capture. For cross-platform recording, use record_browser.py instead.
set -euo pipefail

# Defaults
DURATION=10
FPS=15
REGION=""
OUTPUT="/tmp/animation-review.mp4"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Record screen using ffmpeg + avfoundation.

Options:
  -d, --duration SEC    Recording duration in seconds (default: 10)
  -f, --fps N           Frame rate (default: 5)
  -r, --region WxH+X+Y  Crop region (e.g. 800x600+100+200)
  -o, --output PATH     Output file (default: /tmp/animation-review.mp4)
  -h, --help            Show this help
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--duration) DURATION="$2"; shift 2 ;;
    -f|--fps)      FPS="$2"; shift 2 ;;
    -r|--region)   REGION="$2"; shift 2 ;;
    -o|--output)   OUTPUT="$2"; shift 2 ;;
    -h|--help)     usage ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if ! command -v ffmpeg &>/dev/null; then
  echo "Error: ffmpeg not found. Install with: brew install ffmpeg" >&2
  exit 1
fi

# Build filter chain
FILTERS=""
if [[ -n "$REGION" ]]; then
  # Parse WxH+X+Y
  if [[ "$REGION" =~ ^([0-9]+)x([0-9]+)\+([0-9]+)\+([0-9]+)$ ]]; then
    W="${BASH_REMATCH[1]}"
    H="${BASH_REMATCH[2]}"
    X="${BASH_REMATCH[3]}"
    Y="${BASH_REMATCH[4]}"
    FILTERS="-vf crop=${W}:${H}:${X}:${Y}"
  else
    echo "Error: Invalid region format. Use WxH+X+Y (e.g. 800x600+100+200)" >&2
    exit 1
  fi
fi

# Countdown
echo "Recording ${DURATION}s at ${FPS}fps → ${OUTPUT}"
[[ -n "$REGION" ]] && echo "Crop region: ${REGION}"
for i in 3 2 1; do
  echo "$i..."
  sleep 1
done
echo "Recording!"

# Record
ffmpeg -y \
  -f avfoundation \
  -r "$FPS" \
  -i "1" \
  -t "$DURATION" \
  $FILTERS \
  -vcodec libx264 -crf 23 -preset fast -pix_fmt yuv420p \
  "$OUTPUT" \
  2>/dev/null

# Summary
SIZE=$(du -h "$OUTPUT" | cut -f1 | xargs)
echo "Done — ${SIZE} → ${OUTPUT}"
