"""Small read-only query helpers for common SQLite access patterns."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.models import DocumentTocEntry
from pdfzx.db.session import create_sqlite_engine


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


def _run_sha256_query(sqlite_db_path: Path, stmt) -> list[str]:
    """Execute a scalar sha256 query with managed engine/session lifecycle."""
    engine = create_sqlite_engine(sqlite_db_path)
    try:
        with Session(engine) as session:
            return list(session.scalars(stmt))
    finally:
        engine.dispose()
