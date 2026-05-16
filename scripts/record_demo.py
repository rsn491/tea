#!/usr/bin/env python3
"""Record a harntest demo to GIF.

Usage:
    python scripts/record_demo.py <demo-name>

Reads the shell script at docs/demos/<demo-name>.sh, records it with asciinema,
converts to GIF with agg, and prints a ready-to-paste markdown snippet.

The shell script is expected to already exist. Use the agent command /record-demo
(or follow AGENTS.md) to have an agent generate it from the demo spec first.

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


def _die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def _check_deps() -> None:
    missing = [tool for tool in ("asciinema", "agg") if not shutil.which(tool)]
    if not missing:
        return
    lines = ["missing required tools:"]
    for tool in missing:
        if tool == "asciinema":
            lines.append("  asciinema — pip install asciinema --break-system-packages")
        elif tool == "agg":
            lines.append("  agg       — https://github.com/asciinema/agg/releases")
    _die("\n".join(lines))


def record(name: str, repo_root: Path) -> None:
    demo_dir = repo_root / "docs" / "demos"
    script = demo_dir / f"{name}.sh"
    cast = demo_dir / f"{name}.cast"
    gif = demo_dir / f"{name}.gif"

    if not script.exists():
        _die(
            f"shell script not found: {script}\n"
            "Generate it first by following the agent instructions in AGENTS.md."
        )

    demo_dir.mkdir(parents=True, exist_ok=True)

    print(f"recording {name} …")
    subprocess.run(
        [
            "asciinema", "rec",
            "--overwrite",
            "--cols", str(_COLS),
            "--rows", str(_ROWS),
            "-c", f"bash {script}",
            str(cast),
        ],
        check=True,
    )

    print("converting to GIF …")
    subprocess.run(
        [
            "agg",
            "--font-size", str(_FONT_SIZE),
            "--cols", str(_COLS),
            "--idle-time-limit", str(_IDLE_TIME_LIMIT),
            "--last-frame-duration", str(_LAST_FRAME_DURATION),
            str(cast),
            str(gif),
        ],
        check=True,
    )

    size_kb = gif.stat().st_size // 1024
    print(f"\ndone — {gif.relative_to(repo_root)} ({size_kb}K)\n")
    print(f"![Demo](docs/demos/{name}.gif)")


def _repo_root() -> Path:
    path = Path(__file__).resolve().parent
    while path != path.parent:
        if (path / ".git").exists():
            return path
        path = path.parent
    _die("not inside a git repository")
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if "-h" in sys.argv or "--help" in sys.argv else 1)

    _check_deps()
    record(sys.argv[1], _repo_root())


if __name__ == "__main__":
    main()
