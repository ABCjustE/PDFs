"""Tests for inventory.process_pdf."""

from __future__ import annotations

import shutil
from pathlib import Path

import pymupdf
import pytest

from pdfzx.config import ScanConfig
from pdfzx.inventory import process_pdf


@pytest.fixture
def config(pdf_root: Path, tmp_path: Path) -> ScanConfig:
    return ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _place(src: Path, root: Path, name: str | None = None) -> Path:
    """Copy src into root and return new path."""
    dest = root / (name or src.name)
    shutil.copy(src, dest)
    return dest


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_digital_pdf_returns_record(make_pdf, pdf_root, config):
    src = make_pdf("doc.pdf", ["Hello world " * 20])
    path = _place(src, pdf_root)
    record = process_pdf(path, pdf_root, config)

    assert record.sha256
    assert record.md5
    assert record.file_name == "doc.pdf"
    assert record.paths == ["doc.pdf"]
    assert record.is_digital is True
    assert record.first_seen_job is None
    assert record.last_seen_job is None


def test_scanned_pdf_is_not_digital(make_pdf, pdf_root, config):
    src = make_pdf("scan.pdf", ["", "", ""])  # blank pages → no text
    path = _place(src, pdf_root)
    record = process_pdf(path, pdf_root, config)
    assert record.is_digital is False
    assert record.languages == []


def test_toc_extracted(make_toc_pdf, pdf_root, config):
    entries = [(1, "Chapter One", 1), (2, "Section 1.1", 2)]
    src = make_toc_pdf("toc.pdf", entries)
    path = _place(src, pdf_root)
    record = process_pdf(path, pdf_root, config)

    assert len(record.toc) == 2
    assert record.toc[0].title == "Chapter One"
    assert record.toc[0].level == 1
    assert record.toc[1].page == 2


def test_language_detected(make_pdf, pdf_root, config):
    # English text long enough for langdetect
    src = make_pdf("en.pdf", ["The quick brown fox jumps over the lazy dog. " * 10])
    path = _place(src, pdf_root)
    record = process_pdf(path, pdf_root, config)
    assert "en" in record.languages


def test_cjk_language_detected(make_pdf, pdf_root, config):
    cjk = "这是一段中文测试文本，用于验证中文语言检测功能是否正常工作。" * 10
    src = make_pdf("cjk.pdf", [cjk])
    path = _place(src, pdf_root)
    record = process_pdf(path, pdf_root, config)
    assert "zh-cn" in record.languages or "zh-tw" in record.languages


def test_metadata_extracted(tmp_path, pdf_root, config):
    """PDF with embedded title/author metadata is surfaced in DocumentRecord."""
    raw_path = tmp_path / "meta.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "content")
    doc.set_metadata({"title": "My Title", "author": "Alice"})
    doc.save(str(raw_path))
    doc.close()

    path = _place(raw_path, pdf_root)
    record = process_pdf(path, pdf_root, config)
    assert record.metadata.title == "My Title"
    assert record.metadata.author == "Alice"


def test_path_traversal_raises(make_pdf, pdf_root, config):
    src = make_pdf("evil.pdf", ["data"])
    # src lives in tmp_path, not inside pdf_root → should raise
    with pytest.raises(ValueError, match="escapes root"):
        process_pdf(src, pdf_root, config)


def test_missing_file_raises(pdf_root, config):
    missing = pdf_root / "ghost.pdf"
    with pytest.raises((FileNotFoundError, Exception)):
        process_pdf(missing, pdf_root, config)


def test_empty_toc(make_pdf, pdf_root, config):
    src = make_pdf("notoc.pdf", ["No ToC here"])
    path = _place(src, pdf_root)
    record = process_pdf(path, pdf_root, config)
    assert record.toc == []


def test_rel_path_nested(make_pdf, pdf_root, config):
    sub = pdf_root / "sub"
    sub.mkdir()
    src = make_pdf("nested.pdf", ["text"])
    dest = sub / "nested.pdf"
    shutil.copy(src, dest)
    record = process_pdf(dest, pdf_root, config)
    assert record.paths == ["sub/nested.pdf"]
