from __future__ import annotations

from datetime import UTC
from datetime import datetime

from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.models import DocumentPath
from pdfzx.db.models import ScanJob
from pdfzx.db.models import ScannedFileInJob
from pdfzx.db.repositories import DocumentPathRepository
from pdfzx.db.session import create_sqlite_engine
from pdfzx.db.session import init_sqlite_db


def test_document_path_repository_deletes_path_and_scan_state(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            session.add(
                ScanJob(
                    job_id="job-1",
                    run_at=datetime(2026, 4, 17, tzinfo=UTC).replace(tzinfo=None),
                    root_path=str(tmp_path / "root"),
                    added=1,
                    updated=0,
                    removed=0,
                    duplicates=0,
                    skipped=0,
                )
            )
            session.add(
                Document(
                    sha256="a",
                    md5="a" * 32,
                    file_name="a.pdf",
                    metadata_extra_json={},
                    languages_json=[],
                    is_digital=True,
                    force_extracted=False,
                    first_seen_job="job-1",
                    last_seen_job="job-1",
                )
            )
            session.add_all(
                [
                    DocumentPath(sha256="a", rel_path="a/a.pdf"),
                    DocumentPath(sha256="a", rel_path="b/a.pdf"),
                    ScannedFileInJob(
                        rel_path="a/a.pdf",
                        sha256="a",
                        size_bytes=1,
                        mtime=1.0,
                        last_scanned_job="job-1",
                    ),
                ]
            )
            session.flush()

            repo = DocumentPathRepository(session)
            deleted = repo.delete_by_rel_path(rel_path="a/a.pdf")

            assert deleted is not None
            assert deleted.rel_path == "a/a.pdf"
            assert deleted.sha256 == "a"
            assert deleted.removed_scan_state is True
            assert deleted.remaining_paths == 1
            assert session.get(ScannedFileInJob, "a/a.pdf") is None
            assert session.query(DocumentPath).filter_by(rel_path="a/a.pdf").one_or_none() is None
            session.commit()
    finally:
        engine.dispose()


def test_document_path_repository_returns_none_for_missing_path(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            repo = DocumentPathRepository(session)
            assert repo.get_sha256_by_rel_path(rel_path="missing.pdf") is None
            assert repo.delete_by_rel_path(rel_path="missing.pdf") is None
    finally:
        engine.dispose()


def test_document_path_repository_can_lookup_sha256_by_rel_path(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            session.add(
                Document(
                    sha256="a",
                    md5="a" * 32,
                    file_name="a.pdf",
                    metadata_extra_json={},
                    languages_json=[],
                    is_digital=True,
                    force_extracted=False,
                )
            )
            session.add(DocumentPath(sha256="a", rel_path="a/a.pdf"))
            session.commit()

            repo = DocumentPathRepository(session)
            assert repo.get_sha256_by_rel_path(rel_path="a/a.pdf") == "a"
    finally:
        engine.dispose()
