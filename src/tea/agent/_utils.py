from __future__ import annotations


def _esc(text: str) -> str:
    """Escape a string for embedding in a double-quoted shell argument."""
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
