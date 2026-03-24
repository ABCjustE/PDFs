"""Filename normaliser — Tier 1 regex rules, Tier 2 LLM stub (Phase 2)."""

from __future__ import annotations

import re
import unicodedata

_MAX_LEN = 120
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")
_LEADING_DOTS = re.compile(r"^\.+")


def _is_cjk(char: str) -> bool:
    return (
        (unicodedata.category(char) in {"Lo"} and "\u4e00" <= char <= "\u9fff")
        or "\u3400" <= char <= "\u4dbf"
        or "\uf900" <= char <= "\ufaff"
    )


def _truncate(name: str, max_len: int) -> str:
    """Truncate at a CJK character boundary when possible."""
    if len(name) <= max_len:
        return name
    # try to cut at a non-CJK boundary near max_len
    cut = name[:max_len]
    # walk back to last space or ASCII boundary
    for i in range(max_len - 1, max(0, max_len - 20), -1):
        if name[i] in (" ", "-", "_") or not _is_cjk(name[i]):
            return name[:i].rstrip()
    return cut


def normalize(name: str) -> str:
    """Return a sanitised string suitable for use as a display name.

    Strips illegal filesystem characters, collapses whitespace, removes
    leading dots, and truncates to _MAX_LEN. Does not strip file extensions
    or path components — callers are responsible for that.

    Tier 1 — offline regex rules only.

    Args:
        name: Raw filename or title string.

    Returns:
        Sanitised string, empty string if nothing survives.
    """
    if not name or not name.strip():
        return ""
    result = _ILLEGAL.sub("", name)
    result = _WHITESPACE.sub(" ", result).strip()
    result = _LEADING_DOTS.sub("", result).strip()
    return _truncate(result, _MAX_LEN)


def normalize_llm(name: str, context: str = "") -> str:
    """Tier 2 LLM-assisted normalisation — Phase 2 only.

    Args:
        name: Raw filename or title string.
        context: Extracted text excerpt for LLM context.

    Raises:
        NotImplementedError: Always — implemented in Phase 2.
    """
    raise NotImplementedError("LLM normalisation is a Phase 2 feature")  # noqa: EM101
