from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from tea.infra import Docker
from tea.runner import run
from tea.tui import print_banner
from tea.tui.theme import set_mode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tea",
        description="Run agentic CLI tests against Claude Code or Pi in Docker.",
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
    parser.add_argument(
        "--summary-export",
        metavar="PATH",
        help="write per-test metrics to a JSON baseline after the run",
    )
    parser.add_argument(
        "--baseline",
        metavar="PATH",
        help="compare this run against a stored baseline and report regressions "
        "(warn-only; does not affect exit code)",
    )
    parser.add_argument(
        "--runtime",
        choices=("docker", "colima"),
        default="docker",
        help="container runtime: the default Docker socket or a running Colima "
        "instance (default: docker)",
    )
    parser.add_argument(
        "--theme",
        choices=("dark", "light"),
        default=None,
        help="color theme for a dark or light terminal "
        "(default: dark; also via TEA_THEME)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.target is None:
        parser.print_help()
        return 0

    set_mode(args.theme)
    if args.runtime == "colima":
        try:
            Docker.use_colima()
        except RuntimeError as e:
            print(f"tea: {e}")
            return 1
    print_banner()
    try:
        ok = run(
            args.target,
            args.iterations,
            workers=args.workers,
            summary_export=args.summary_export,
            baseline=args.baseline,
        )
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    return 0 if ok else 1
