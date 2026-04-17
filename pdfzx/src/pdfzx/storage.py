"""Persistence layer — JSON export and SQLite-backed primary storage."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol
from typing import runtime_checkable

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from pdfzx.db.migration import import_registry_to_sqlite
from pdfzx.db.models import Document
from pdfzx.db.models import ScanJob
from pdfzx.db.models import ScannedFileInJob
from pdfzx.db.session import create_sqlite_engine
from pdfzx.db.session import init_sqlite_db
from pdfzx.models import DocumentRecord
from pdfzx.models import JobStats
from pdfzx.models import PdfMetadata
from pdfzx.models import Registry
from pdfzx.models import ScanJobRecord
from pdfzx.models import ScannedFileInJobRecord
from pdfzx.models import TocEntry

logger = logging.getLogger(__name__)


@runtime_checkable
class Storage(Protocol):
    """Minimal persistence contract — load and save a Registry."""

    def load(self) -> Registry:
        """Load Registry from storage."""
        ...

    def save(self, registry: Registry) -> None:
        """Persist Registry to storage."""
        ...


class JsonStorage:
    """Registry persistence backed by a single JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Registry:
        """Load and validate Registry from JSON; return empty Registry if file absent.

        Raises:
            ValueError: If the file exists but contains invalid JSON or schema errors.
        """
        if not self._path.exists():
            logger.debug("db not found, starting empty", extra={"path": str(self._path)})
            return Registry()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            msg = f"Corrupt JSON at {self._path}: {exc}"
            logger.exception(msg)
            raise ValueError(msg) from exc
        try:
            registry = Registry.model_validate(data)
        except ValidationError as exc:
            msg = f"Schema validation failed for {self._path}: {exc}"
            logger.exception(msg)
            raise ValueError(msg) from exc
        logger.debug("loaded db", extra={"path": str(self._path), "docs": len(registry.documents)})
        return registry

    def save(self, registry: Registry) -> None:
        """Serialise Registry to JSON (pretty-printed, UTF-8).

        Raises:
            OSError: If the file cannot be written.
        """
        self._path.write_text(registry.model_dump_json(indent=2), encoding="utf-8")
        logger.debug("saved db", extra={"path": str(self._path), "docs": len(registry.documents)})


class SqliteStorage:
    """Registry persistence backed by a SQLite database."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Registry:
        """Load Registry from SQLite; return empty Registry if file absent."""
        if not self._path.exists():
            logger.debug("sqlite db not found, starting empty", extra={"path": str(self._path)})
            return Registry()

        init_sqlite_db(self._path)
        engine = create_sqlite_engine(self._path)
        try:
            with Session(engine) as session:
                scan_jobs = [
                    ScanJobRecord(
                        job_id=row.job_id,
                        run_at=row.run_at,
                        root_path=row.root_path,
                        stats=JobStats(
                            added=row.added,
                            updated=row.updated,
                            removed=row.removed,
                            duplicates=row.duplicates,
                            skipped=row.skipped,
                        ),
                    )
                    for row in session.scalars(
                        select(ScanJob).order_by(ScanJob.run_at, ScanJob.job_id)
                    ).all()
                ]

                documents: dict[str, DocumentRecord] = {}
                for row in session.scalars(select(Document).order_by(Document.sha256)).all():
                    documents[row.sha256] = DocumentRecord(
                        sha256=row.sha256,
                        md5=row.md5,
                        paths=[
                            path.rel_path
                            for path in sorted(row.paths, key=lambda item: item.rel_path)
                        ],
                        file_name=row.file_name,
                        normalised_name=row.normalised_name,
                        metadata=PdfMetadata(
                            title=row.metadata_title,
                            author=row.metadata_author,
                            creator=row.metadata_creator,
                            created=row.metadata_created,
                            modified=row.metadata_modified,
                            extra=row.metadata_extra_json,
                        ),
                        toc=[
                            TocEntry(level=toc.level, title=toc.title, page=toc.page)
                            for toc in sorted(row.toc_entries, key=lambda item: item.position)
                        ],
                        languages=row.languages_json,
                        is_digital=row.is_digital,
                        toc_valid=row.toc_valid,
                        toc_invalid_reason=row.toc_invalid_reason,
                        extraction_status=row.extraction_status,
                        force_extracted=row.force_extracted,
                        first_seen_job=row.first_seen_job,
                        last_seen_job=row.last_seen_job,
                    )

                scanned_files_in_job = {
                    row.rel_path: ScannedFileInJobRecord(
                        rel_path=row.rel_path,
                        sha256=row.sha256,
                        size_bytes=row.size_bytes,
                        mtime=row.mtime,
                        last_scanned_job=row.last_scanned_job,
                    )
                    for row in session.scalars(
                        select(ScannedFileInJob).order_by(ScannedFileInJob.rel_path)
                    ).all()
                }
        finally:
            engine.dispose()

        return Registry(
            documents=documents,
            scanned_files_in_job=scanned_files_in_job,
            scan_jobs=scan_jobs,
        )

    def save(self, registry: Registry) -> None:
        """Persist Registry by rewriting the SQLite file from the canonical Registry state."""
        import_registry_to_sqlite(registry=registry, target_sqlite=self._path, replace=True)
        logger.debug(
            "saved sqlite db", extra={"path": str(self._path), "docs": len(registry.documents)}
        )
