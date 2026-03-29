"""Filename normaliser — Tier 1 regex rules, Tier 2 LLM stub (Phase 2)."""

from __future__ import annotations

import re
import unicodedata

_MAX_LEN = 120
_CONTROL_CHARS = re.compile(r"[\x00-\x1f]")
_NULL_ARTIFACTS = re.compile(r"[·\ufffd]")
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


def clean_text(text: str) -> str:
    """Remove control characters and normalize whitespace for extracted text fields."""
    if not text:
        return ""

    cleaned = _CONTROL_CHARS.sub("", text)
    cleaned = _NULL_ARTIFACTS.sub("", cleaned)
    return _WHITESPACE.sub(" ", cleaned).strip()


def _replace_non_alnum(text: str) -> str:
    return "".join(char if char.isalnum() else " " for char in text)


def _strip_trailing_ext(text: str) -> str:
    stripped = text.lstrip(".")
    if "." not in stripped:
        return text
    stem, ext = text.rsplit(".", maxsplit=1)
    return stem if 1 <= len(ext) <= 8 and ext.isalnum() else text


def normalize(name: str) -> str:
    """Return a deterministic display name for a document title or filename.

    Tier 1 — offline regex rules only:

    - strip path and trailing extension
    - replace non-alphanumeric runs with spaces
    - collapse repeated spaces
    - trim leading/trailing spaces
    - title-case each token
    - truncate to _MAX_LEN

    Args:
        name: Raw filename or title string.

    Returns:
        Normalized display name, empty string if nothing survives.
    """
    if not name or not name.strip():
        return ""
    result = name
    candidate = name.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    if candidate != name and _strip_trailing_ext(candidate) != candidate:
        result = candidate
    result = _strip_trailing_ext(result)
    result = clean_text(result)
    result = _LEADING_DOTS.sub("", result).strip()
    result = _replace_non_alnum(result)
    result = _WHITESPACE.sub(" ", result).strip()
    result = " ".join(part[:1].upper() + part[1:].lower() for part in result.split())
    return _truncate(result, _MAX_LEN)


def normalize_file_name(name: str) -> str:
    """Return a deterministic normalized PDF filename, preserving the suffix."""
    normalized = normalize(name)
    if not normalized:
        return ""
    if name.lower().endswith(".pdf"):
        return f"{normalized}.pdf"
    return normalized


def normalize_llm(name: str, context: str = "") -> str:
    """Tier 2 LLM-assisted normalisation — Phase 2 only.

    Args:
        name: Raw filename or title string.
        context: Extracted text excerpt for LLM context.

    Raises:
        NotImplementedError: Always — implemented in Phase 2.
    """
    raise NotImplementedError("LLM normalisation is a Phase 2 feature")  # noqa: EM101
