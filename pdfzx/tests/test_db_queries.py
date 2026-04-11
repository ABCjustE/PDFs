from __future__ import annotations

from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.models import DocumentTocEntry
from pdfzx.db.queries import list_candidate_document_sha256s
from pdfzx.db.queries import list_document_sha256s
from pdfzx.db.session import create_sqlite_engine
from pdfzx.db.session import init_sqlite_db


def test_list_document_sha256s_returns_stable_sorted_hashes(tmp_path) -> None:
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


def test_list_candidate_document_sha256s_filters_digital_and_toc(tmp_path) -> None:
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
