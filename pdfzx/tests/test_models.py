"""Tests for pdfzx.models — validation, defaults, and serialisation."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime

import pytest
from pydantic import ValidationError

from pdfzx.models import DocumentRecord
from pdfzx.models import FileStatRecord
from pdfzx.models import JobRecord
from pdfzx.models import JobStats
from pdfzx.models import PdfMetadata
from pdfzx.models import Registry
from pdfzx.models import TocEntry

# ── PdfMetadata ──────────────────────────────────────────────────────────────


def test_pdf_metadata_all_optional():
    m = PdfMetadata()
    assert m.title is None
    assert m.extra == {}


def test_pdf_metadata_extra_fields():
    m = PdfMetadata(extra={"subject": "law"})
    assert m.extra["subject"] == "law"


# ── TocEntry ─────────────────────────────────────────────────────────────────


def test_toc_entry_required_fields():
    t = TocEntry(level=1, title="Chapter 1", page=3)
    assert t.level == 1 and t.title == "Chapter 1" and t.page == 3


def test_toc_entry_missing_field_raises():
    with pytest.raises(ValidationError):
        TocEntry(level=1, title="Chapter 1")  # page missing


# ── DocumentRecord ────────────────────────────────────────────────────────────


def test_document_record_defaults():
    doc = DocumentRecord(
        sha256="abc" * 20,
        md5="def" * 10,
        file_name="test.pdf",
        first_seen_job="job-1",
        last_seen_job="job-1",
    )
    assert doc.paths == []
    assert doc.toc == []
    assert doc.languages == []
    assert doc.is_digital is True
    assert doc.normalised_name is None


def test_document_record_missing_required_raises():
    with pytest.raises(ValidationError):
        DocumentRecord(sha256="abc", md5="def")  # file_name and jobs missing


def test_document_record_serialisation_roundtrip():
    doc = DocumentRecord(
        sha256="a" * 64,
        md5="b" * 32,
        file_name="book.pdf",
        paths=["subdir/book.pdf"],
        languages=["zh", "en"],
        is_digital=False,
        first_seen_job="job-1",
        last_seen_job="job-1",
    )
    restored = DocumentRecord.model_validate(doc.model_dump())
    assert restored == doc


# ── FileStatRecord ────────────────────────────────────────────────────────────


def test_file_stat_record_fields():
    fs = FileStatRecord(
        rel_path="subdir/book.pdf",
        sha256="a" * 64,
        size_bytes=1024,
        mtime=1_700_000_000.0,
        last_scanned_job="job-1",
    )
    assert fs.size_bytes == 1024
    assert fs.mtime == 1_700_000_000.0


# ── JobRecord ─────────────────────────────────────────────────────────────────


def test_job_record_stats_defaults():
    job = JobRecord(
        job_id="job-1", run_at=datetime(2024, 1, 1, tzinfo=UTC), root_path="/data/pdfs"
    )
    assert job.stats == JobStats()
    assert job.stats.added == 0


def test_job_record_serialisation_roundtrip():
    job = JobRecord(
        job_id="job-2",
        run_at=datetime(2024, 6, 1, tzinfo=UTC),
        root_path="/data/pdfs",
        stats=JobStats(added=3, duplicates=1),
    )
    restored = JobRecord.model_validate(job.model_dump())
    assert restored == job


# ── Registry ──────────────────────────────────────────────────────────────────


def test_registry_empty_defaults():
    r = Registry()
    assert r.documents == {}
    assert r.file_stats == {}
    assert r.jobs == []


def test_registry_roundtrip_with_document():
    doc = DocumentRecord(
        sha256="a" * 64,
        md5="b" * 32,
        file_name="test.pdf",
        first_seen_job="job-1",
        last_seen_job="job-1",
    )
    reg = Registry(documents={"a" * 64: doc})
    restored = Registry.model_validate(reg.model_dump())
    assert restored.documents["a" * 64].file_name == "test.pdf"
