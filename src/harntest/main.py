from __future__ import annotations

import argparse

from harntest.runner import run
from harntest.tui import print_banner


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="harntest",
        description="Run agentic CLI tests against Claude Code or Codex in Docker.",
    )
    parser.add_argument("target", help="folder, file, or file::test_fn")
    parser.add_argument(
        "--iterations",
        "-n",
        type=int,
        default=1,
        metavar="N",
        help="number of times to run each test (default: 1)",
    )
    args = parser.parse_args()

    print_banner()
    run(args.target, args.iterations)
