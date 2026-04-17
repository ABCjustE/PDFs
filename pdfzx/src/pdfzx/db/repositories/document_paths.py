from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete
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
        removed_scan_state = (
            self._session.execute(
                delete(ScannedFileInJob).where(ScannedFileInJob.rel_path == rel_path)
            ).rowcount
            > 0
        )
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
