from __future__ import annotations


def _sanitize_env_value(text: str) -> str:
    """Make ``text`` safe to pass as an environment variable value.

    Environment variables (like argv) are null-terminated C strings, so a null
    byte cannot survive the env/exec boundary — Docker rejects values containing
    one outright. Text arriving from diffs can include binary content (e.g. a
    ``.pyc`` file), so replace null bytes with the Unicode replacement character.
    That mirrors what ``decode(errors="replace")`` does for undecodable bytes:
    the substitution stays visible rather than silently dropping content.

    No shell escaping is needed: the value is consumed via parameter expansion
    (``"$VAR"``), which does not re-parse ``$``, backticks, or quotes inside it.
    """
    return text.replace("\x00", "�")
