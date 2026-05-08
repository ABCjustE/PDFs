from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from pdfzx.db.models import DocumentPath
from pdfzx.db.models import ScannedFileInJob


@dataclass(frozen=True, slots=True)
class DeletedDocumentPath:
    """Summary of one deleted document path mutation."""

    rel_path: str
    sha256: str
    removed_scan_state: bool
    remaining_paths: int


class DocumentPathRepository:
    """CRUD helpers for canonical document paths and related scan-state rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_sha256_by_rel_path(self, *, rel_path: str) -> str | None:
        """Return the owning document hash for one canonical relative path."""
        return self._session.scalar(
            select(DocumentPath.sha256).where(DocumentPath.rel_path == rel_path)
        )

    def delete_by_rel_path(self, *, rel_path: str) -> DeletedDocumentPath | None:
        """Delete one document path row and its matching scan-state row if present."""
        path_row = self._session.scalar(
            select(DocumentPath).where(DocumentPath.rel_path == rel_path)
        )
        if path_row is None:
            return None
        sha256 = path_row.sha256
        scan_row = self._session.get(ScannedFileInJob, rel_path)
        removed_scan_state = scan_row is not None
        if scan_row is not None:
            self._session.delete(scan_row)
        self._session.delete(path_row)
        self._session.flush()
        remaining_paths = self._session.scalar(
            select(func.count())
            .select_from(DocumentPath)
            .where(DocumentPath.sha256 == sha256)
        )
        return DeletedDocumentPath(
            rel_path=rel_path,
            sha256=sha256,
            removed_scan_state=removed_scan_state,
            remaining_paths=int(remaining_paths or 0),
        )

    def upsert(self, *, sha256: str, rel_path: str) -> DocumentPath:
        """Create one canonical path row when it does not already exist."""
        existing = self._session.scalar(
            select(DocumentPath).where(DocumentPath.rel_path == rel_path)
        )
        if existing is not None:
            return existing
        row = self._session.scalar(
            select(DocumentPath).where(
                DocumentPath.sha256 == sha256,
                DocumentPath.rel_path == rel_path,
            )
        )
        if row is not None:
            return row
        row = DocumentPath(sha256=sha256, rel_path=rel_path)
        self._session.add(row)
        self._session.flush()
        return row

    def move(self, *, old_rel_path: str, new_rel_path: str) -> str | None:
        """Move one known path row to a new relative path."""
        row = self._session.scalar(
            select(DocumentPath).where(DocumentPath.rel_path == old_rel_path)
        )
        if row is None:
            return None
        existing_dest = self._session.scalar(
            select(DocumentPath).where(DocumentPath.rel_path == new_rel_path)
        )
        if existing_dest is not None:
            if existing_dest.sha256 == row.sha256:
                self._session.delete(row)
                self._session.flush()
                return row.sha256
            return None
        scan_row = self._session.get(ScannedFileInJob, old_rel_path)
        row.rel_path = new_rel_path
        row.document.file_name = Path(new_rel_path).name
        if scan_row is not None:
            scan_row.rel_path = new_rel_path
        self._session.flush()
        return row.sha256
