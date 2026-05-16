#!/usr/bin/env python3
"""Record a harntest demo to GIF, and optionally upload it to GitHub.

Usage:
    python scripts/record_demo.py <demo-name> [--upload]

Reads the shell script at docs/demos/<demo-name>.sh, records it with asciinema,
and converts to GIF with agg.

Without --upload: prints a local markdown snippet using the repo-relative path.
With    --upload: uploads the GIF to a persistent GitHub draft release and prints
                  a hosted URL suitable for PR descriptions.

The shell script must already exist. Use /record-demo to have an agent generate
it from the spec at docs/demos/<demo-name>.md.

Dependencies:
    asciinema  — pip install asciinema --break-system-packages
    agg        — https://github.com/asciinema/agg/releases
    gh         — https://cli.github.com  (only needed for --upload)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

_COLS = 220
_ROWS = 50
_FONT_SIZE = 14
_IDLE_TIME_LIMIT = 1
_LAST_FRAME_DURATION = 10

_RELEASE_TAG = "demo-assets"
_RELEASE_NAME = "Demo Assets"
_RELEASE_BODY = "Persistent store for demo GIFs embedded in PR descriptions. Do not delete."


def _die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def _check_deps(upload: bool) -> None:
    tools = ["asciinema", "agg"] + (["gh"] if upload else [])
    missing = [t for t in tools if not shutil.which(t)]
    if not missing:
        return
    lines = ["missing required tools:"]
    for tool in missing:
        if tool == "asciinema":
            lines.append("  asciinema — pip install asciinema --break-system-packages")
        elif tool == "agg":
            lines.append("  agg       — https://github.com/asciinema/agg/releases")
        elif tool == "gh":
            lines.append("  gh        — https://cli.github.com")
    _die("\n".join(lines))


# ── recording ──────────────────────────────────────────────────────────────────

def _record(name: str, repo_root: Path) -> Path:
    demo_dir = repo_root / "docs" / "demos"
    script = demo_dir / f"{name}.sh"
    cast = demo_dir / f"{name}.cast"
    gif = demo_dir / f"{name}.gif"

    if not script.exists():
        _die(
            f"shell script not found: {script}\n"
            "Generate it first via /record-demo or by following the spec at "
            f"docs/demos/{name}.md."
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
    print(f"converted — {gif.relative_to(repo_root)} ({size_kb}K)")
    return gif


# ── GitHub upload ──────────────────────────────────────────────────────────────

def _gh(*args: str) -> dict | list:
    result = subprocess.run(
        ["gh", "api", *args],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def _gh_token() -> str:
    result = subprocess.run(
        ["gh", "auth", "token"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _repo_slug() -> str:
    """Return 'owner/repo' from the git remote."""
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _get_or_create_release(slug: str) -> int:
    """Return the release ID of the demo-assets draft release, creating it if needed."""
    releases = _gh(f"/repos/{slug}/releases")
    for r in releases:
        if r.get("tag_name") == _RELEASE_TAG:
            return r["id"]

    new = _gh(
        f"/repos/{slug}/releases",
        "--method", "POST",
        "--field", f"tag_name={_RELEASE_TAG}",
        "--field", f"name={_RELEASE_NAME}",
        "--field", f"body={_RELEASE_BODY}",
        "--field", "draft=true",
    )
    return new["id"]


def _delete_existing_asset(slug: str, release_id: int, filename: str) -> None:
    assets = _gh(f"/repos/{slug}/releases/{release_id}/assets")
    for asset in assets:
        if asset["name"] == filename:
            subprocess.run(
                ["gh", "api", f"/repos/{slug}/releases/assets/{asset['id']}",
                 "--method", "DELETE"],
                check=True, capture_output=True,
            )


def _upload_asset(slug: str, release_id: int, gif: Path) -> str:
    """Upload gif to the release and return the browser_download_url."""
    filename = gif.name
    _delete_existing_asset(slug, release_id, filename)

    token = _gh_token()
    url = f"https://uploads.github.com/repos/{slug}/releases/{release_id}/assets?name={filename}"

    data = gif.read_bytes()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "image/gif",
            "Accept": "application/vnd.github+json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())

    return result["browser_download_url"]


def upload(gif: Path) -> str:
    print("uploading to GitHub …")
    slug = _repo_slug()
    release_id = _get_or_create_release(slug)
    hosted_url = _upload_asset(slug, release_id, gif)
    print(f"uploaded — {hosted_url}")
    return hosted_url


# ── entry point ────────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    path = Path(__file__).resolve().parent
    while path != path.parent:
        if (path / ".git").exists():
            return path
        path = path.parent
    _die("not inside a git repository")
    raise SystemExit(1)


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if args else 1)

    do_upload = "--upload" in args
    positional = [a for a in args if not a.startswith("--")]
    if len(positional) != 1:
        print(__doc__)
        sys.exit(1)

    name = positional[0]
    _check_deps(do_upload)
    root = _repo_root()

    gif = _record(name, root)

    if do_upload:
        url = upload(gif)
        print(f"\n![Demo]({url})")
    else:
        print(f"\n![Demo](docs/demos/{name}.gif)")


if __name__ == "__main__":
    main()
