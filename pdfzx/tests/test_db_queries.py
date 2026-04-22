from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.models import DocumentTocEntry
from pdfzx.db.queries import list_candidate_document_sha256s
from pdfzx.db.queries import list_document_sha256s
from pdfzx.db.queries import list_duplicate_documents
from pdfzx.db.session import create_sqlite_engine
from pdfzx.db.session import init_sqlite_db
from pdfzx.models import DocumentRecord
from pdfzx.models import Registry
from pdfzx.storage import SqliteStorage


def test_list_document_sha256s_returns_stable_sorted_hashes(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    Document(
                        sha256="c",
                        md5="c" * 32,
                        file_name="c.pdf",
                        metadata_extra_json={},
                        languages_json=[],
                        is_digital=True,
                        force_extracted=False,
                    ),
                    Document(
                        sha256="a",
                        md5="a" * 32,
                        file_name="a.pdf",
                        metadata_extra_json={},
                        languages_json=[],
                        is_digital=True,
                        force_extracted=False,
                    ),
                    Document(
                        sha256="b",
                        md5="b" * 32,
                        file_name="b.pdf",
                        metadata_extra_json={},
                        languages_json=[],
                        is_digital=False,
                        force_extracted=False,
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()

    assert list_document_sha256s(db_path) == ["a", "b", "c"]


def test_list_candidate_document_sha256s_filters_digital_and_toc(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    Document(
                        sha256="digital-with-toc",
                        md5="a" * 32,
                        file_name="a.pdf",
                        metadata_extra_json={},
                        languages_json=[],
                        is_digital=True,
                        force_extracted=False,
                    ),
                    Document(
                        sha256="digital-no-toc",
                        md5="b" * 32,
                        file_name="b.pdf",
                        metadata_extra_json={},
                        languages_json=[],
                        is_digital=True,
                        force_extracted=False,
                    ),
                    Document(
                        sha256="scan-with-toc",
                        md5="c" * 32,
                        file_name="c.pdf",
                        metadata_extra_json={},
                        languages_json=[],
                        is_digital=False,
                        force_extracted=False,
                    ),
                ]
            )
            session.add_all(
                [
                    DocumentTocEntry(
                        sha256="digital-with-toc",
                        level=1,
                        title="Intro",
                        page=1,
                        position=0,
                    ),
                    DocumentTocEntry(
                        sha256="scan-with-toc",
                        level=1,
                        title="Intro",
                        page=1,
                        position=0,
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()

    assert list_candidate_document_sha256s(db_path) == [
        "digital-no-toc",
        "digital-with-toc",
        "scan-with-toc",
    ]
    assert list_candidate_document_sha256s(db_path, require_digital=True) == [
        "digital-no-toc",
        "digital-with-toc",
    ]
    assert list_candidate_document_sha256s(db_path, require_toc=True) == [
        "digital-with-toc",
        "scan-with-toc",
    ]
    assert list_candidate_document_sha256s(
        db_path,
        require_digital=True,
        require_toc=True,
    ) == ["digital-with-toc"]


def test_list_duplicate_documents_returns_documents_with_multiple_paths(
    tmp_path: Path,
) -> None:
    sqlite_db = tmp_path / "db.sqlite3"
    registry = Registry(
        documents={
            "dup": DocumentRecord(
                sha256="dup",
                md5="m" * 32,
                file_name="dup.pdf",
                paths=["a/dup.pdf", "b/dup.pdf"],
            ),
            "single": DocumentRecord(
                sha256="single",
                md5="n" * 32,
                file_name="single.pdf",
                paths=["single.pdf"],
            ),
        }
    )
    SqliteStorage(sqlite_db).save(registry)

    result = list_duplicate_documents(sqlite_db)

    assert result.total == 1
    assert result.limit is None
    assert result.offset == 0
    assert len(result.rows) == 1
    assert result.rows[0].sha256 == "dup"
    assert result.rows[0].file_name == "dup.pdf"
    assert result.rows[0].path_count == 2
    assert result.rows[0].rel_paths == ["a/dup.pdf", "b/dup.pdf"]


def test_list_duplicate_documents_respects_limit_and_offset(tmp_path: Path) -> None:
    sqlite_db = tmp_path / "db.sqlite3"
    registry = Registry(
        documents={
            "a" * 64: DocumentRecord(
                sha256="a" * 64,
                md5="1" * 32,
                file_name="a.pdf",
                paths=["a1.pdf", "a2.pdf"],
            ),
            "b" * 64: DocumentRecord(
                sha256="b" * 64,
                md5="2" * 32,
                file_name="b.pdf",
                paths=["b1.pdf", "b2.pdf"],
            ),
        }
    )
    SqliteStorage(sqlite_db).save(registry)

    result = list_duplicate_documents(sqlite_db, limit=1, offset=1)

    assert result.total == 2
    assert result.limit == 1
    assert result.offset == 1
    assert len(result.rows) == 1
    assert result.rows[0].sha256 == "b" * 64
