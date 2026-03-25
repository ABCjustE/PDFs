"""PDF extraction — path → DocumentRecord (pure, no I/O beyond reading the PDF)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pymupdf

from pdfzx.config import ScanConfig
from pdfzx.models import DocumentRecord
from pdfzx.models import PdfMetadata
from pdfzx.models import TocEntry
from pdfzx.normalizer import clean_text
from pdfzx.utils import compute_hashes
from pdfzx.utils import detect_languages
from pdfzx.utils import is_digital
from pdfzx.utils import validate_path

logger = logging.getLogger(__name__)

_META_KEYS = ("title", "author", "creator", "creationDate", "modDate")


def _extract_metadata(doc: pymupdf.Document) -> PdfMetadata:
    raw: dict[str, Any] = doc.metadata or {}
    extra = {k: v for k, v in raw.items() if k not in _META_KEYS and v}
    return PdfMetadata(
        title=raw.get("title") or None,
        author=raw.get("author") or None,
        creator=raw.get("creator") or None,
        created=raw.get("creationDate") or None,
        modified=raw.get("modDate") or None,
        extra=extra,
    )


def _extract_toc(doc: pymupdf.Document) -> list[TocEntry]:
    return [
        TocEntry(level=lvl, title=clean_text(title), page=page) for lvl, title, page in doc.get_toc()
    ]


def process_pdf(path: Path, root: Path, config: ScanConfig) -> DocumentRecord:
    """Extract hashes, metadata, ToC, and classification from a single PDF.

    Args:
        path: Absolute path to the PDF file.
        root: Scan root used for path-traversal validation.
        config: Runtime scan configuration.

    Returns:
        DocumentRecord with first_seen_job/last_seen_job left as None;
        registry.py stamps those on merge.

    Raises:
        ValueError: If path escapes root.
        FileNotFoundError: If the file does not exist.
        Exception: Re-raised after logging for any pymupdf failure.
    """
    resolved = validate_path(path, root)
    logger.debug("processing", extra={"path": str(resolved)})

    hashes = compute_hashes(resolved)

    try:
        doc = pymupdf.open(str(resolved))  # type: ignore[no-untyped-call]
    except Exception:
        logger.exception("failed to open PDF", extra={"path": str(resolved)})
        raise

    try:
        metadata = _extract_metadata(doc)
        toc = _extract_toc(doc)
        digital = is_digital(doc, config.ocr_char_threshold, config.ocr_scan_pages)
        text = "".join(page.get_text() for page in doc) if digital else ""  # type: ignore[attr-defined]
        languages = detect_languages(text)
    finally:
        doc.close()  # type: ignore[no-untyped-call]

    rel_path = str(resolved.relative_to(root.resolve()))
    record = DocumentRecord(
        sha256=hashes["sha256"],
        md5=hashes["md5"],
        paths=[rel_path],
        file_name=resolved.name,
        metadata=metadata,
        toc=toc,
        languages=languages,
        is_digital=digital,
    )
    logger.info("processed", extra={"sha256": record.sha256, "path": rel_path})
    return record
