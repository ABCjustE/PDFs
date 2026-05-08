from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.models import DocumentTocEntry
from pdfzx.models import DocumentRecord


class DocumentRepository:
    """CRUD helpers for canonical document rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_sha256(self, *, sha256: str) -> Document | None:
        """Return one document row by content hash."""
        return self._session.get(Document, sha256)

    def create_from_record(self, *, record: DocumentRecord) -> Document:
        """Create one document row and matching ToC rows from a scanned record."""
        row = Document(
            sha256=record.sha256,
            md5=record.md5,
            file_name=record.file_name,
            normalised_name=record.normalised_name,
            metadata_title=record.metadata.title,
            metadata_author=record.metadata.author,
            metadata_creator=record.metadata.creator,
            metadata_created=record.metadata.created,
            metadata_modified=record.metadata.modified,
            metadata_extra_json=record.metadata.extra,
            languages_json=record.languages,
            is_digital=record.is_digital,
            toc_valid=record.toc_valid,
            toc_invalid_reason=record.toc_invalid_reason,
            extraction_status=record.extraction_status,
            force_extracted=record.force_extracted,
            first_seen_job=record.first_seen_job,
            last_seen_job=record.last_seen_job,
        )
        self._session.add(row)
        self._session.flush()
        self._session.add_all(
            [
                DocumentTocEntry(
                    sha256=record.sha256,
                    level=entry.level,
                    title=entry.title,
                    page=entry.page,
                    position=index,
                )
                for index, entry in enumerate(record.toc)
            ]
        )
        return row

    def replace_from_record(self, *, record: DocumentRecord) -> Document:
        """Replace document metadata and ToC rows from a scanned record."""
        row = self.get_by_sha256(sha256=record.sha256)
        if row is None:
            return self.create_from_record(record=record)
        row.md5 = record.md5
        row.file_name = record.file_name
        row.normalised_name = record.normalised_name
        row.metadata_title = record.metadata.title
        row.metadata_author = record.metadata.author
        row.metadata_creator = record.metadata.creator
        row.metadata_created = record.metadata.created
        row.metadata_modified = record.metadata.modified
        row.metadata_extra_json = record.metadata.extra
        row.languages_json = record.languages
        row.is_digital = record.is_digital
        row.toc_valid = record.toc_valid
        row.toc_invalid_reason = record.toc_invalid_reason
        row.extraction_status = record.extraction_status
        row.force_extracted = record.force_extracted
        self._session.execute(
            delete(DocumentTocEntry).where(DocumentTocEntry.sha256 == record.sha256)
        )
        self._session.add_all(
            [
                DocumentTocEntry(
                    sha256=record.sha256,
                    level=entry.level,
                    title=entry.title,
                    page=entry.page,
                    position=index,
                )
                for index, entry in enumerate(record.toc)
            ]
        )
        return row
