#!/usr/bin/env python3
"""Record a tea demo to GIF.

Usage:
    python scripts/record_demo.py <demo-name>

Reads the shell script at /tmp/tea-demo-<demo-name>.sh, records it with
asciinema, converts to GIF, and prints the GIF path on stdout.
All working files stay in /tmp — nothing is written to the repo.

Pipe into upload_gif.py to get a hosted URL:
    python scripts/record_demo.py <name> | xargs python scripts/upload_gif.py

The shell script must already exist at /tmp/tea-demo-<name>.sh.
Use /record-demo to have an agent generate it from a demo description.

Dependencies:
    asciinema  — pip install asciinema --break-system-packages
    agg        — https://github.com/asciinema/agg/releases
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_COLS = 220
_ROWS = 50
_FONT_SIZE = 14
_IDLE_TIME_LIMIT = 1
_LAST_FRAME_DURATION = 10
_TMP = Path("/tmp")


def _die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def _check_deps() -> None:
    missing = [t for t in ("asciinema", "agg") if not shutil.which(t)]
    if not missing:
        return
    lines = ["missing required tools:"]
    for t in missing:
        if t == "asciinema":
            lines.append("  asciinema — pip install asciinema --break-system-packages")
        elif t == "agg":
            lines.append("  agg       — https://github.com/asciinema/agg/releases")
    _die("\n".join(lines))


def record(name: str) -> Path:
    script = _TMP / f"tea-demo-{name}.sh"
    cast = _TMP / f"tea-demo-{name}.cast"
    gif = _TMP / f"tea-demo-{name}.gif"

    if not script.exists():
        _die(
            f"shell script not found: {script}\n"
            "Write it first — see /record-demo for instructions."
        )

    print(f"recording {name} …", file=sys.stderr)
    subprocess.run(
        [
            "asciinema",
            "rec",
            "--overwrite",
            "--cols",
            str(_COLS),
            "--rows",
            str(_ROWS),
            "-c",
            f"bash {script}",
            str(cast),
        ],
        check=True,
    )

    print("converting to GIF …", file=sys.stderr)
    subprocess.run(
        [
            "agg",
            "--font-size",
            str(_FONT_SIZE),
            "--cols",
            str(_COLS),
            "--idle-time-limit",
            str(_IDLE_TIME_LIMIT),
            "--last-frame-duration",
            str(_LAST_FRAME_DURATION),
            str(cast),
            str(gif),
        ],
        check=True,
    )

    size_kb = gif.stat().st_size // 1024
    print(f"done — {size_kb}K", file=sys.stderr)
    return gif


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if sys.argv[1:] and sys.argv[1] in ("-h", "--help") else 1)

    _check_deps()
    gif = record(sys.argv[1])
    print(gif)  # stdout: path for piping


if __name__ == "__main__":
    main()
