from __future__ import annotations

import functools
import os
import re
import subprocess
import uuid


@functools.lru_cache(maxsize=None)
def resolve_cli_version(cli_cmd: str, package: str, env_var: str) -> str:
    """Resolve the version of a CLI tool at runtime.

    Resolution order:
    1. ``env_var`` environment variable (explicit override)
    2. ``cli_cmd --version`` (e.g. ``claude --version``)
    3. ``npm list -g --depth=0 <package>`` (fallback when CLI is not on PATH)
    4. ``latest-<uuid4>`` — forces a fresh image build, never raises

    The result is cached per ``(cli_cmd, package, env_var)`` tuple so that
    subprocess calls run at most once per process.  Tests that monkeypatch the
    environment variable should call ``resolve_cli_version.cache_clear()``
    before and after the test to avoid cache poisoning.
    """
    # 1. Explicit env override
    if v := os.environ.get(env_var):
        return v

    # 2. Ask the CLI directly (e.g. "claude --version" → "1.2.3")
    try:
        out = subprocess.run(
            [cli_cmd, "--version"], capture_output=True, text=True
        ).stdout.strip()
        m = re.search(r"(\d+\.\d+\.\d+)", out)
        if m:
            return m.group(1)
    except FileNotFoundError:
        pass

    # 3. npm list fallback (handles cases where the CLI is not on PATH)
    try:
        result = subprocess.run(
            ["npm", "list", "-g", "--depth=0", package],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if package in line:
                # line: "└── @anthropic-ai/claude-code@1.2.3" or "pi@1.0.0"
                version = line.strip().split("@")[-1]
                if version:
                    return version
    except FileNotFoundError:
        pass

    # 4. Last resort — unique tag forces a fresh build, avoids stale :latest
    return f"latest-{uuid.uuid4()}"
