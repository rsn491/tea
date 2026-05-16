#!/usr/bin/env python3
"""Upload a GIF to a persistent GitHub draft release and print the hosted URL.

Usage:
    python scripts/upload_gif.py <gif-path>
    python scripts/record_demo.py <name> | xargs python scripts/upload_gif.py

Uploads to a draft release tagged 'demo-assets' (created once, reused forever).
Re-uploading the same filename replaces the previous asset — safe to re-run.
Prints the browser_download_url on stdout.

Dependencies:
    gh  — https://cli.github.com  (must be authenticated)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

_RELEASE_TAG = "demo-assets"
_RELEASE_NAME = "Demo Assets"
_RELEASE_BODY = "Persistent store for demo GIFs embedded in PR descriptions. Do not delete."


def _die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def _gh(*args: str) -> dict | list:
    r = subprocess.run(["gh", "api", *args], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def _repo_slug() -> str:
    r = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        capture_output=True, text=True, check=True,
    )
    return r.stdout.strip()


def _gh_token() -> str:
    r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
    return r.stdout.strip()


def _get_or_create_release(slug: str) -> int:
    for r in _gh(f"/repos/{slug}/releases"):
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


def _delete_existing(slug: str, release_id: int, filename: str) -> None:
    for asset in _gh(f"/repos/{slug}/releases/{release_id}/assets"):
        if asset["name"] == filename:
            subprocess.run(
                ["gh", "api", f"/repos/{slug}/releases/assets/{asset['id']}",
                 "--method", "DELETE"],
                check=True, capture_output=True,
            )


def upload(gif: Path) -> str:
    if not shutil.which("gh"):
        _die("gh not found — install from https://cli.github.com")

    slug = _repo_slug()
    release_id = _get_or_create_release(slug)
    _delete_existing(slug, release_id, gif.name)

    token = _gh_token()
    url = f"https://uploads.github.com/repos/{slug}/releases/{release_id}/assets?name={gif.name}"
    req = urllib.request.Request(
        url, data=gif.read_bytes(),
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


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if sys.argv[1:] and sys.argv[1] in ("-h", "--help") else 1)

    gif = Path(sys.argv[1])
    if not gif.exists():
        _die(f"file not found: {gif}")

    print(f"uploading {gif.name} …", file=sys.stderr)
    url = upload(gif)
    print(url)  # stdout: URL for piping


if __name__ == "__main__":
    main()
