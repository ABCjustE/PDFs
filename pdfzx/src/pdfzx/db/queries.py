"""Small read-only query helpers for common SQLite access patterns."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from pdfzx.db.models import Document
from pdfzx.db.models import DocumentPath
from pdfzx.db.models import DocumentTocEntry
from pdfzx.db.session import create_sqlite_engine


@dataclass(frozen=True, slots=True)
class DuplicateDocumentView:
    """Readable duplicate-document row keyed by sha256."""

    sha256: str
    file_name: str
    path_count: int
    rel_paths: list[str]


def list_document_sha256s(sqlite_db_path: Path) -> list[str]:
    """Return all document hashes in stable order."""
    return _run_sha256_query(sqlite_db_path, select(Document.sha256).order_by(Document.sha256))


def list_candidate_document_sha256s(
    sqlite_db_path: Path,
    *,
    require_digital: bool = False,
    require_toc: bool = False,
) -> list[str]:
    """Return document hashes filtered by common partitioning criteria."""
    stmt = select(Document.sha256).order_by(Document.sha256)
    if require_digital:
        stmt = stmt.where(Document.is_digital.is_(True))
    if require_toc:
        stmt = stmt.join(DocumentTocEntry).distinct()
    return _run_sha256_query(sqlite_db_path, stmt)


def list_duplicate_documents(
    sqlite_db_path: Path,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[DuplicateDocumentView]:
    """Return documents that currently have more than one path."""
    engine = create_sqlite_engine(sqlite_db_path)
    try:
        with Session(engine) as session:
            duplicate_sha256s = list(
                session.scalars(
                    select(Document.sha256)
                    .join(DocumentPath)
                    .group_by(Document.sha256)
                    .having(func.count(DocumentPath.id) > 1)
                    .order_by(Document.sha256)
                    .offset(offset)
                    .limit(limit)
                )
            )
            if not duplicate_sha256s:
                return []
            documents = list(
                session.scalars(
                    select(Document)
                    .options(selectinload(Document.paths))
                    .where(Document.sha256.in_(duplicate_sha256s))
                    .order_by(Document.sha256)
                )
            )
    finally:
        engine.dispose()
    return [
        DuplicateDocumentView(
            sha256=document.sha256,
            file_name=document.file_name,
            path_count=len(document.paths),
            rel_paths=sorted(path.rel_path for path in document.paths),
        )
        for document in documents
    ]


def _run_sha256_query(sqlite_db_path: Path, stmt) -> list[str]:
    """Execute a scalar sha256 query with managed engine/session lifecycle."""
    engine = create_sqlite_engine(sqlite_db_path)
    try:
        with Session(engine) as session:
            return list(session.scalars(stmt))
    finally:
        engine.dispose()
