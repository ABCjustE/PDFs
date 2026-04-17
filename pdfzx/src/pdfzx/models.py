"""Pydantic V2 data models — stable contract for all pdfzx modules."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import AliasChoices
from pydantic import BaseModel
from pydantic import Field


class ExtractionStatus(StrEnum):
    """Phase 2.1 text-extraction lifecycle state."""

    pending = "pending"
    skipped = "skipped"
    gate_fail = "gate_fail"
    gate_pass = "gate_pass"
    forced = "forced"
    failed = "failed"


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
    toc_valid: bool | None = None  # None = not yet assessed by LLM
    toc_invalid_reason: str | None = None  # populated when toc_valid=False
    extraction_status: ExtractionStatus | None = None
    force_extracted: bool = False
    first_seen_job: str | None = None
    last_seen_job: str | None = None


class ScannedFileInJobRecord(BaseModel):
    """Per-path scan snapshot used by the registry merge algorithm."""

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


class ScanJobRecord(BaseModel):
    """
    Audit record for a single inventory scan run.

    TODO Consider in RDB, job record one to many (new/updated) document records.
    For tracking
    """

    job_id: str
    run_at: datetime
    root_path: str
    stats: JobStats = Field(default_factory=JobStats)


class Registry(BaseModel):
    """Compatibility registry shape used by the Phase 1 merge/storage bridge."""

    documents: dict[str, DocumentRecord] = Field(default_factory=dict)
    scanned_files_in_job: dict[str, ScannedFileInJobRecord] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("scanned_files_in_job", "file_stats"),
        serialization_alias="scanned_files_in_job",
    )
    scan_jobs: list[ScanJobRecord] = Field(
        default_factory=list,
        validation_alias=AliasChoices("scan_jobs", "jobs"),
        serialization_alias="scan_jobs",
    )
