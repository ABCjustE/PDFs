"""Pydantic V2 data models — stable contract for all pdfzx modules."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PdfMetadata(BaseModel):
    """Raw metadata extracted from a PDF."""

    title: str | None = None
    author: str | None = None
    creator: str | None = None
    created: str | None = None
    modified: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class TocEntry(BaseModel):
    """Single table-of-contents entry."""

    level: int
    title: str
    page: int


class DocumentRecord(BaseModel):
    """Canonical record for a unique PDF document, keyed by SHA-256."""

    sha256: str
    md5: str
    paths: list[str] = Field(default_factory=list)
    file_name: str
    normalised_name: str | None = None
    metadata: PdfMetadata = Field(default_factory=PdfMetadata)
    toc: list[TocEntry] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    is_digital: bool = True
    first_seen_job: str
    last_seen_job: str


class FileStatRecord(BaseModel):
    """Per-path file stat for mtime-gated incremental scanning."""

    rel_path: str
    sha256: str
    size_bytes: int
    mtime: float
    last_scanned_job: str


class JobStats(BaseModel):
    """Counts of changes detected in a single scan run."""

    added: int = 0
    updated: int = 0
    removed: int = 0
    duplicates: int = 0
    skipped: int = 0


class JobRecord(BaseModel):
    """Audit record for a single inventory scan run."""

    job_id: str
    run_at: datetime
    root_path: str
    stats: JobStats = Field(default_factory=JobStats)


class Registry(BaseModel):
    """Top-level db.json structure."""

    documents: dict[str, DocumentRecord] = Field(default_factory=dict)
    file_stats: dict[str, FileStatRecord] = Field(default_factory=dict)
    jobs: list[JobRecord] = Field(default_factory=list)
