"""SKILL.md metadata helpers."""

from __future__ import annotations

import re
from pathlib import Path

_VERSION_RE = re.compile(r'''^version:\s*(?:"([^"]+)"|'([^']+)'|(\S+))\s*$''', re.MULTILINE)


def read_skill_version(skill_md_path: Path) -> str:
    """Return a SKILL.md frontmatter version, or an empty string when absent."""
    try:
        text = skill_md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    match = _VERSION_RE.search(text)
    if not match:
        return ""
    return match.group(1) or match.group(2) or match.group(3) or ""
