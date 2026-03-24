"""Offline utility functions for hashing, PDF inspection, and path validation."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf
from langdetect import DetectorFactory
from langdetect import detect_langs
from langdetect.lang_detect_exception import LangDetectException

_CHUNK_SIZE = 1024 * 1024  # 1 MB
_LANGDETECT_SEED = 0
_DIGITAL_PAGE_LIMIT = 3

DetectorFactory.seed = _LANGDETECT_SEED


def compute_hashes(path: Path) -> dict[str, str]:
    """Compute SHA-256 and MD5 hashes via streaming reads (constant memory).

    Args:
        path: Path to the file.

    Returns:
        Dict with keys ``sha256`` and ``md5``.
    """
    sha256, md5 = hashlib.sha256(), hashlib.md5(usedforsecurity=False)
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            sha256.update(chunk)
            md5.update(chunk)
    return {"sha256": sha256.hexdigest(), "md5": md5.hexdigest()}


def is_digital(doc: pymupdf.Document, threshold: int, pages: int = _DIGITAL_PAGE_LIMIT) -> bool:
    """Return whether the first pages contain enough extractable text."""
    total_chars = 0

    for page in doc[: min(pages, doc.page_count)]:
        total_chars += len(page.get_text().strip())  # type: ignore[no-untyped-call]
        if total_chars >= threshold:
            return True

    return False


def detect_languages(text: str) -> list[str]:
    """Detect likely languages from text, returning [] for empty or undetectable input."""
    cleaned = text.strip()
    if not cleaned:
        return []

    try:
        return [prediction.lang for prediction in detect_langs(cleaned)]
    except LangDetectException:
        return []


def validate_path(path: Path, root: Path) -> Path:
    """Resolve path and assert it remains within root (path traversal guard).

    Args:
        path: Candidate path to validate.
        root: Configured scan root.

    Returns:
        Resolved absolute path.

    Raises:
        ValueError: If path escapes root.
    """
    resolved_root = root.resolve()
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        msg = f"Path escapes root: {resolved}"
        raise ValueError(msg) from exc
    return resolved
