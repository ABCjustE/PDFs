"""Shared utilities: streaming hash, language detection, digital classification."""

import hashlib
import logging
from pathlib import Path

import fitz  # pymupdf
from langdetect import detect_langs

logger = logging.getLogger(__name__)

_CHUNK = 65536  # 64 KB read chunks — constant-memory streaming
_LANG_THRESHOLD = 0.10  # minimum probability to include a language
_SAMPLE_PAGES = 10  # pages to sample for language / digital detection


def stream_hash(path: Path) -> tuple[str, str]:
    """Compute SHA-256 and MD5 of *path* via constant-memory streaming.

    Both digests are computed in a single pass.
    MD5 is included for legacy deduplication compatibility only — not for
    security purposes; SHA-256 is the authoritative unique key.

    Args:
        path: Path to the file.

    Returns:
        ``(sha256_hex, md5_hex)``
    """
    sha256, md5 = hashlib.sha256(), hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            sha256.update(chunk)
            md5.update(chunk)
    return sha256.hexdigest(), md5.hexdigest()


def is_digital(doc: fitz.Document) -> bool:
    """Return ``True`` if *doc* has a selectable text layer.

    Samples up to :data:`_SAMPLE_PAGES` pages; any non-empty text means digital.

    Args:
        doc: Open :class:`fitz.Document`.
    """
    return any(
        doc[i].get_text("text").strip()
        for i in range(min(_SAMPLE_PAGES, doc.page_count))
    )


def detect_languages(doc: fitz.Document) -> list[str]:
    """Detect languages present in *doc* text.

    Concatenates text from up to :data:`_SAMPLE_PAGES` pages, runs
    ``langdetect``, and returns ISO 639-1 codes with probability ≥
    :data:`_LANG_THRESHOLD`.

    Args:
        doc: Open :class:`fitz.Document`.

    Returns:
        Sorted list of language codes, e.g. ``["en", "zh-cn"]``.
        Empty list when no text is present or detection fails.
    """
    text = " ".join(
        doc[i].get_text("text") for i in range(min(_SAMPLE_PAGES, doc.page_count))
    ).strip()
    if not text:
        return []
    try:
        return sorted(
            lang.lang for lang in detect_langs(text) if lang.prob >= _LANG_THRESHOLD
        )
    except Exception as exc:  # langdetect raises LangDetectException on edge cases
        logger.warning("Language detection failed: %s", exc)
        return []
