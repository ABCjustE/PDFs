"""Phase 1: PDF inventory — hash, metadata, ToC, language, digital classification."""

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

import fitz  # pymupdf

from pdfzx.utils import detect_languages, is_digital, stream_hash

logger = logging.getLogger(__name__)


@dataclass
class TocEntry:
    """One line from a PDF table of contents."""

    level: int
    title: str
    page: int


@dataclass
class PdfMetadata:
    """Core document metadata extracted from the PDF info dictionary."""

    title: str = ""
    author: str = ""
    creator: str = ""
    created: str = ""
    modified: str = ""


@dataclass
class InventoryRecord:
    """Full Phase 1 record for a single PDF file."""

    file_name: str
    sha256: str
    md5: str
    size_bytes: int
    page_count: int
    is_digital: bool
    languages: list[str]
    metadata: PdfMetadata
    toc: list[TocEntry] = field(default_factory=list)
    needs_ocr: bool = True
    phase2_status: str = "pending"
    error: str | None = None


# ── internal helpers ──────────────────────────────────────────────────────────


def _meta(doc: fitz.Document) -> PdfMetadata:
    m = doc.metadata or {}
    return PdfMetadata(
        title=m.get("title", ""),
        author=m.get("author", ""),
        creator=m.get("creator", ""),
        created=m.get("creationDate", ""),
        modified=m.get("modDate", ""),
    )


def _toc(doc: fitz.Document) -> list[TocEntry]:
    return [TocEntry(level=lvl, title=t, page=pg) for lvl, t, pg in doc.get_toc()]


def _safe_resolve(path: Path, pdf_dir: Path) -> Path:
    """Resolve *path* and guard against traversal outside *pdf_dir*."""
    resolved = path.resolve()
    if not resolved.is_relative_to(pdf_dir.resolve()):
        raise ValueError(f"Path traversal blocked: {path!r} outside {pdf_dir!r}")
    return resolved


# ── public API ────────────────────────────────────────────────────────────────


def process_pdf(path: Path, pdf_dir: Path) -> InventoryRecord:
    """Process a single PDF file and return its :class:`InventoryRecord`.

    Path-traversal is validated against *pdf_dir* before any I/O.
    Parsing errors are caught, logged, and stored in ``record.error``
    rather than raised — the caller always gets a usable record.

    Args:
        path: Absolute path to the PDF file.
        pdf_dir: Root input directory (traversal guard).

    Returns:
        Populated :class:`InventoryRecord`.
    """
    path = _safe_resolve(path, pdf_dir)
    sha256, md5 = stream_hash(path)
    record = InventoryRecord(
        file_name=path.name,
        sha256=sha256,
        md5=md5,
        size_bytes=path.stat().st_size,
        page_count=0,
        is_digital=False,
        languages=[],
        metadata=PdfMetadata(),
    )
    try:
        with fitz.open(path) as doc:
            digital = is_digital(doc)
            record.page_count = doc.page_count
            record.is_digital = digital
            record.needs_ocr = not digital
            record.languages = detect_languages(doc)
            record.metadata = _meta(doc)
            record.toc = _toc(doc)
    except Exception as exc:
        logger.error("Failed to parse %s: %s", path.name, exc)
        record.error = str(exc)
    return record


def run_inventory(pdf_dir: Path, output_dir: Path) -> dict[str, dict]:
    """Process every ``*.pdf`` in *pdf_dir* and write ``manifest.json``.

    Files are processed in sorted order for deterministic output.
    The manifest is keyed by SHA-256 to support O(1) deduplication lookups.

    Args:
        pdf_dir: Directory containing input PDF files.
        output_dir: Destination for ``manifest.json`` (created if absent).

    Returns:
        Manifest dict keyed by SHA-256.
    """
    pdf_dir, output_dir = pdf_dir.resolve(), output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}

    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        logger.info("Processing %s", pdf_path.name)
        record = process_pdf(pdf_path, pdf_dir)
        manifest[record.sha256] = asdict(record)

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    logger.info("Manifest → %s  (%d entries)", manifest_path, len(manifest))
    return manifest
