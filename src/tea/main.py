from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from tea.runner import run
from tea.tui import print_banner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tea",
        description="Run agentic CLI tests against Claude Code or Codex in Docker.",
        add_help=True,
    )
    parser.add_argument("target", nargs="?", help="folder, file, or file::test_fn")
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=1,
        metavar="N",
        help="number of times to run each test (default: 1)",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=1,
        metavar="N",
        help="number of tests to run concurrently (default: 1)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.target is None:
        parser.print_help()
        return

    print_banner()
    try:
        run(args.target, args.iterations, workers=args.workers)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
