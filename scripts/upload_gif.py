#!/usr/bin/env python3
"""Upload a GIF to Imgur and print the hosted URL.

Usage:
    python scripts/upload_gif.py <gif-path>
    python scripts/record_demo.py <name> | xargs python scripts/upload_gif.py

Requires an Imgur client ID in the IMGUR_CLIENT_ID environment variable.
Get one (free, 2 minutes) at https://api.imgur.com/oauth2/addclient —
choose "OAuth 2 authorization without a callback URL". No approval needed.

Prints the Imgur URL on stdout, suitable for embedding in PR descriptions.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def _die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def upload(gif: Path, client_id: str) -> str:
    encoded = base64.b64encode(gif.read_bytes()).decode()
    payload = f"image={urllib.parse.quote(encoded)}&type=base64".encode()

    req = urllib.request.Request(
        "https://api.imgur.com/3/image",
        data=payload,
        headers={
            "Authorization": f"Client-ID {client_id}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())

    if not result.get("success"):
        _die(f"imgur upload failed: {result}")

    return result["data"]["link"]


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if sys.argv[1:] and sys.argv[1] in ("-h", "--help") else 1)

    client_id = os.environ.get("IMGUR_CLIENT_ID")
    if not client_id:
        _die(
            "IMGUR_CLIENT_ID not set.\n"
            "Get a free client ID at https://api.imgur.com/oauth2/addclient\n"
            "(choose 'OAuth 2 authorization without a callback URL')"
        )

    gif = Path(sys.argv[1])
    if not gif.exists():
        _die(f"file not found: {gif}")

    print(f"uploading {gif.name} to imgur …", file=sys.stderr)
    url = upload(gif, client_id)
    print(url)  # stdout: URL for piping


if __name__ == "__main__":
    main()
