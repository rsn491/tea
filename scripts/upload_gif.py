#!/usr/bin/env python3
"""Upload a GIF to catbox.moe and print the hosted URL.

Usage:
    python scripts/upload_gif.py <gif-path>
    python scripts/record_demo.py <name> | xargs python scripts/upload_gif.py

No account or credentials needed. Prints the URL on stdout.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path


def _die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def upload(gif: Path) -> str:
    boundary = "----FormBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="reqtype"\r\n\r\n'
        f"fileupload\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="fileToUpload"; filename="{gif.name}"\r\n'
        f"Content-Type: image/gif\r\n\r\n"
    ).encode() + gif.read_bytes() + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        "https://catbox.moe/user/api.php",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        url = resp.read().decode().strip()

    if not url.startswith("https://"):
        _die(f"catbox upload failed: {url}")

    return url


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
