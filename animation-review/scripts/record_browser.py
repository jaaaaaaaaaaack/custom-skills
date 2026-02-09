#!/usr/bin/env python3
"""Record browser interactions with Playwright's built-in video capture."""

import argparse
import os
import subprocess
import sys
import tempfile
import time

RECORDING_FPS = 24


def parse_args():
    p = argparse.ArgumentParser(
        description="Record browser interactions with video capture",
        epilog="""
Action format (passed via -a/--action, executed in order):
  wait:MS              Wait N milliseconds
  click:SELECTOR       Click an element
  scroll:PIXELS        Scroll down (negative = up)
  hover:SELECTOR       Hover over an element
  press:KEY            Press a keyboard key (Enter, Tab, etc.)
  type:SELECTOR|TEXT   Type text into an element (pipe separates selector from text)

Examples:
  %(prog)s http://localhost:3000 -a 'click:.play-btn' -a 'wait:3000'
  %(prog)s http://localhost:5173 -a 'scroll:500' -a 'wait:2000'
  %(prog)s http://localhost:3000/carousel -a 'click:.next' -a 'wait:500' -a 'click:.next' -a 'wait:500'
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("url", help="URL to navigate to")
    p.add_argument(
        "-a",
        "--action",
        action="append",
        default=[],
        help="Action to perform (repeatable, executed in order)",
    )
    p.add_argument(
        "-o",
        "--output",
        default="/tmp/animation-review.mp4",
        help="Output file path (default: /tmp/animation-review.mp4)",
    )
    p.add_argument(
        "-W", "--width", type=int, default=1280, help="Viewport width (default: 1280)"
    )
    p.add_argument(
        "-H", "--height", type=int, default=720, help="Viewport height (default: 720)"
    )
    p.add_argument(
        "--headed", action="store_true", help="Run in headed mode (visible browser)"
    )
    p.add_argument(
        "--wait-before",
        type=int,
        default=500,
        help="Wait after page load before actions, in ms (default: 500)",
    )
    p.add_argument(
        "--wait-after",
        type=int,
        default=1000,
        help="Wait after last action before closing, in ms (default: 1000)",
    )
    return p.parse_args()


def execute_action(page, action_str):
    """Parse and execute a single action string."""
    parts = action_str.split(":", 1)
    cmd = parts[0]
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "wait":
        page.wait_for_timeout(int(arg))
    elif cmd == "click":
        page.click(arg)
    elif cmd == "scroll":
        page.mouse.wheel(0, int(arg))
    elif cmd == "hover":
        page.hover(arg)
    elif cmd == "press":
        page.keyboard.press(arg)
    elif cmd == "type":
        sel, text = arg.split("|", 1)
        page.fill(sel, text)
    else:
        print(f"Unknown action: {cmd}", file=sys.stderr)
        sys.exit(1)


def main():
    args = parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Error: playwright not installed. Run: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.action:
        print("Warning: no actions specified, recording page load only", file=sys.stderr)

    video_dir = tempfile.mkdtemp(prefix="animation-review-")

    print(f"Recording {args.url} → {args.output} (at {RECORDING_FPS}fps)", file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(
            viewport={"width": args.width, "height": args.height},
            record_video_dir=video_dir,
            record_video_size={"width": args.width, "height": args.height},
        )
        page = context.new_page()
        recording_start = time.monotonic()

        page.goto(args.url, wait_until="networkidle")
        page.wait_for_timeout(args.wait_before)

        actions_start = time.monotonic() - recording_start
        for action in args.action:
            t = time.monotonic() - recording_start
            print(f"  → {action} (at {t:.1f}s)", file=sys.stderr)
            execute_action(page, action)
        actions_end = time.monotonic() - recording_start

        page.wait_for_timeout(args.wait_after)

        video_path = page.video.path()
        total_duration = time.monotonic() - recording_start
        context.close()
        browser.close()

    # Print timeline summary for use with analyze.py --start/--end
    print(f"Timeline: actions {actions_start:.1f}s–{actions_end:.1f}s, total {total_duration:.1f}s", file=sys.stderr)

    # Transcode webm → mp4 at 24fps
    print(f"Transcoding to {RECORDING_FPS}fps mp4...", file=sys.stderr)
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-r", str(RECORDING_FPS),
            "-vcodec", "libx264", "-crf", "23", "-preset", "fast", "-pix_fmt", "yuv420p",
            args.output,
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"ffmpeg transcode failed: {result.stderr.decode()}", file=sys.stderr)
        sys.exit(1)

    # Cleanup temp webm
    try:
        os.remove(video_path)
        os.rmdir(video_dir)
    except OSError:
        pass

    size = os.path.getsize(args.output)
    size_str = f"{size / 1024:.0f}KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f}MB"
    print(f"Done — {size_str} → {args.output}", file=sys.stderr)
    # stdout: just the path, for piping into analyze.py
    print(args.output)


if __name__ == "__main__":
    main()
