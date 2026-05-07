"""Tests for pdfzx.inventory — process_pdf, run_inventory."""

import json

import pytest

from pdfzx.inventory import InventoryRecord, process_pdf, run_inventory

# ── process_pdf ───────────────────────────────────────────────────────────────


def test_process_pdf_digital(digital_pdf, pdf_dir):
    record = process_pdf(digital_pdf, pdf_dir)
    assert isinstance(record, InventoryRecord)
    assert record.file_name == "digital.pdf"
    assert record.is_digital is True
    assert record.needs_ocr is False
    assert record.phase2_status == "pending"
    assert record.error is None
    assert len(record.sha256) == 64
    assert len(record.md5) == 32
    assert record.size_bytes > 0
    assert record.page_count == 1


def test_process_pdf_toc(digital_pdf, pdf_dir):
    record = process_pdf(digital_pdf, pdf_dir)
    assert len(record.toc) == 2
    assert record.toc[0].level == 1
    assert record.toc[0].title == "Introduction"
    assert record.toc[1].level == 2
    assert record.toc[1].title == "Details"


def test_process_pdf_scanned(scanned_pdf, pdf_dir):
    record = process_pdf(scanned_pdf, pdf_dir)
    assert record.is_digital is False
    assert record.needs_ocr is True
    assert record.languages == []
    assert record.toc == []
    assert record.error is None


def test_process_pdf_metadata_fields(digital_pdf, pdf_dir):
    record = process_pdf(digital_pdf, pdf_dir)
    m = record.metadata
    # Fields exist and are strings (may be empty for minimal test PDFs)
    assert isinstance(m.title, str)
    assert isinstance(m.author, str)
    assert isinstance(m.creator, str)
    assert isinstance(m.created, str)
    assert isinstance(m.modified, str)


def test_process_pdf_path_traversal_blocked(tmp_path, pdf_dir):
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4\n")
    with pytest.raises(ValueError, match="Path traversal blocked"):
        process_pdf(outside, pdf_dir)


def test_process_pdf_invalid_file_records_error(pdf_dir):
    bad = pdf_dir / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    record = process_pdf(bad, pdf_dir)
    assert record.error is not None
    assert record.page_count == 0


# ── run_inventory ─────────────────────────────────────────────────────────────


def test_run_inventory_writes_manifest(pdf_dir, output_dir):
    manifest = run_inventory(pdf_dir, output_dir)
    manifest_path = output_dir / "manifest.json"
    assert manifest_path.exists()
    on_disk = json.loads(manifest_path.read_text())
    assert on_disk == manifest


def test_run_inventory_keyed_by_sha256(pdf_dir, output_dir):
    manifest = run_inventory(pdf_dir, output_dir)
    for sha256, entry in manifest.items():
        assert entry["sha256"] == sha256
        assert len(sha256) == 64


def test_run_inventory_all_required_fields(pdf_dir, output_dir):
    manifest = run_inventory(pdf_dir, output_dir)
    required = {
        "file_name", "sha256", "md5", "size_bytes", "page_count",
        "is_digital", "languages", "metadata", "toc", "needs_ocr", "phase2_status",
    }
    for entry in manifest.values():
        assert required <= entry.keys()


def test_run_inventory_creates_output_dir(tmp_path, pdf_dir):
    new_out = tmp_path / "new_output"
    assert not new_out.exists()
    run_inventory(pdf_dir, new_out)
    assert (new_out / "manifest.json").exists()
