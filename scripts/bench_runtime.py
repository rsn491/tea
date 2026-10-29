#!/usr/bin/env python3
"""Benchmark tea's per-run container cost on Docker vs Colima.

Usage:
    python scripts/bench_runtime.py [--runtime docker colima] [--runs 10]
                                    [--workers 1] [--files 200] [--image IMG]

Mimics what one tea agent run costs the container runtime, minus the LLM:
copy a workdir to a temp dir, start a fresh container with it bind-mounted at
/workspace, read every file, write new ones, collect logs, remove the
container. Goes through ``tea.infra.Docker`` so it measures tea's own path.
No API keys needed.

Run it on a Mac with both runtimes up (Docker Desktop on the default socket,
``colima start --vm-type vz --mount-type virtiofs``). A runtime that is not
available is reported and skipped. One warm-up run per runtime (image pull,
VM wake-up) is excluded from the stats.

Not wired into CI: GitHub's Apple Silicon macOS runners lack nested
virtualisation, so neither Docker Desktop nor Colima can start there.
"""

from __future__ import annotations

import argparse
import os
import shutil
import statistics
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tea.infra import Docker, DockerRunConfig
from tea.infra.docker import colima_socket

_DEFAULT_IMAGE = "alpine:3.20"
_WORKDIR = "/workspace"


def _make_fixture(root: Path, files: int) -> None:
    for i in range(files):
        sub = root / f"pkg{i % 10}"
        sub.mkdir(exist_ok=True)
        (sub / f"mod_{i}.py").write_text(f"def f_{i}():\n    return {i}\n" * 20)


def _command(files: int) -> list[str]:
    # Read the whole workdir through the bind mount, then write as many files
    # back — the I/O pattern of an agent exploring and editing a repo.
    script = (
        "find . -type f -exec cat {} + > /dev/null"
        f" && for i in $(seq 1 {files}); do echo edit > out_$i.txt; done"
        " && ls | wc -l"
    )
    return ["sh", "-c", script]


def _one_run(docker: Docker, fixture: Path, files: int, image: str) -> float:
    t0 = time.monotonic()
    tmp = tempfile.mkdtemp()
    try:
        shutil.copytree(fixture, tmp, dirs_exist_ok=True)
        result = docker.run(
            DockerRunConfig(
                image=image,
                command=_command(files),
                timeout=120,
                volumes={tmp: _WORKDIR},
                container_workdir=_WORKDIR,
            )
        )
        if result.exit_code != 0:
            raise RuntimeError(f"container exited {result.exit_code}: {result.stderr}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return time.monotonic() - t0


def _docker_for(runtime: str) -> Docker:
    if runtime == "colima":
        return Docker(base_url=colima_socket())
    return Docker()


def _bench(runtime: str, args: argparse.Namespace, fixture: Path) -> dict | None:
    try:
        docker = _docker_for(runtime)
        _one_run(docker, fixture, args.files, args.image)  # warm-up
    except Exception as e:
        print(f"  {runtime}: skipped ({e})", file=sys.stderr)
        return None
    endpoint = docker._base_url or os.environ.get("DOCKER_HOST", "default socket")
    print(f"  {runtime}: {endpoint}")

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        times = list(
            pool.map(
                lambda _: _one_run(docker, fixture, args.files, args.image),
                range(args.runs),
            )
        )
    wall = time.monotonic() - t0
    times.sort()
    return {
        "runtime": runtime,
        "mean": statistics.mean(times),
        "median": statistics.median(times),
        "p90": times[min(len(times) - 1, int(len(times) * 0.9))],
        "min": times[0],
        "max": times[-1],
        "wall": wall,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--runtime",
        nargs="+",
        choices=("docker", "colima"),
        default=["docker", "colima"],
    )
    parser.add_argument("--runs", type=int, default=10, help="timed runs per runtime")
    parser.add_argument("--workers", type=int, default=1, help="concurrent runs")
    parser.add_argument(
        "--files", type=int, default=200, help="files read and written per run"
    )
    parser.add_argument(
        "--image", default=_DEFAULT_IMAGE, help="any image with a POSIX sh"
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as d:
        fixture = Path(d)
        _make_fixture(fixture, args.files)
        print(
            f"{args.runs} runs × {args.files} files, {args.workers} worker(s), "
            f"image {args.image}"
        )
        rows = [r for rt in args.runtime if (r := _bench(rt, args, fixture))]

    if not rows:
        print("no runtime available", file=sys.stderr)
        return 1
    print()
    cols = ("mean", "median", "p90", "min", "max", "wall")
    print(f"{'runtime':<8}" + "".join(f"{c:>9}" for c in cols) + "   (seconds)")
    for r in rows:
        print(f"{r['runtime']:<8}" + "".join(f"{r[c]:>9.2f}" for c in cols))
    if len(rows) == 2:
        a, b = rows
        ratio = b["median"] / a["median"]
        print(f"\n{b['runtime']} / {a['runtime']} median: {ratio:.2f}×")
    return 0


if __name__ == "__main__":
    sys.exit(main())
