"""Tests for storage.JsonStorage."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from pdfzx.db.models import LlmDocumentSuggestion
from pdfzx.db.models import Prompt
from pdfzx.db.session import create_sqlite_engine
from pdfzx.db.session import init_sqlite_db
from pdfzx.models import DocumentRecord
from pdfzx.models import Registry
from pdfzx.storage import JsonStorage
from pdfzx.storage import SqliteStorage
from pdfzx.storage import Storage


def _sample_registry() -> Registry:
    doc = DocumentRecord(sha256="abc123", md5="def456", file_name="test.pdf", paths=["test.pdf"])
    return Registry(documents={"abc123": doc})


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_json_storage_implements_protocol(tmp_path):
    assert isinstance(JsonStorage(tmp_path / "db.json"), Storage)


def test_sqlite_storage_implements_protocol(tmp_path):
    assert isinstance(SqliteStorage(tmp_path / "db.sqlite3"), Storage)


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


def test_load_missing_file_returns_empty(tmp_path):
    store = JsonStorage(tmp_path / "db.json")
    registry = store.load()
    assert registry.documents == {}
    assert registry.scan_jobs == []


def test_load_roundtrip(tmp_path):
    path = tmp_path / "db.json"
    original = _sample_registry()
    JsonStorage(path).save(original)
    loaded = JsonStorage(path).load()
    assert loaded.documents["abc123"].file_name == "test.pdf"


def test_load_corrupt_json_raises(tmp_path):
    path = tmp_path / "db.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="Corrupt JSON"):
        JsonStorage(path).load()


def test_load_invalid_schema_raises(tmp_path):
    path = tmp_path / "db.json"
    # missing required fields in DocumentRecord
    path.write_text(
        '{"documents": {"x": {"sha256": "x"}}, "scanned_files_in_job": {}, "jobs": []}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Schema validation"):
        JsonStorage(path).load()


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


def test_save_creates_file(tmp_path):
    path = tmp_path / "db.json"
    JsonStorage(path).save(Registry())
    assert path.exists()


def test_save_is_valid_json(tmp_path):
    import json

    path = tmp_path / "db.json"
    JsonStorage(path).save(_sample_registry())
    data = json.loads(path.read_text())
    assert "documents" in data


def test_save_utf8_cjk(tmp_path):
    path = tmp_path / "db.json"
    doc = DocumentRecord(sha256="aaa", md5="bbb", file_name="中文.pdf", paths=["中文.pdf"])
    JsonStorage(path).save(Registry(documents={"aaa": doc}))
    text = path.read_text(encoding="utf-8")
    assert "中文" in text


def test_sqlite_load_missing_file_returns_empty(tmp_path):
    store = SqliteStorage(tmp_path / "db.sqlite3")
    registry = store.load()
    assert registry.documents == {}
    assert registry.scan_jobs == []


def test_sqlite_roundtrip(tmp_path):
    path = tmp_path / "db.sqlite3"
    original = _sample_registry()
    SqliteStorage(path).save(original)
    loaded = SqliteStorage(path).load()
    assert loaded.documents["abc123"].file_name == "test.pdf"


def test_sqlite_save_creates_file(tmp_path):
    path = tmp_path / "db.sqlite3"
    SqliteStorage(path).save(Registry())
    assert path.exists()


def test_sqlite_save_preserves_prompt_workflow_tables(tmp_path):
    path = tmp_path / "db.sqlite3"
    init_sqlite_db(path)
    engine = create_sqlite_engine(path)
    try:
        with Session(engine) as session:
            prompt = Prompt(
                workflow_name="llm_document_suggestion",
                prompt_text="prompt",
                model_provider="openai",
                model="gpt-4o-mini",
                prompt_version="v1",
                active=True,
                created_at=_now(),
                updated_at=_now(),
            )
            session.add(prompt)
            session.flush()
            session.add(
                LlmDocumentSuggestion(
                    sha256="abc123",
                    prompt_id=prompt.id,
                    suggested_file_name="Suggested.pdf",
                    suggested_author=None,
                    suggested_publisher=None,
                    suggested_edition=None,
                    suggested_labels_json=[],
                    reasoning_summary="test",
                    status="pending",
                    applied=False,
                    created_at=_now(),
                    updated_at=_now(),
                )
            )
            session.commit()
    finally:
        engine.dispose()

    SqliteStorage(path).save(_sample_registry())

    engine = create_sqlite_engine(path)
    try:
        with Session(engine) as session:
            assert session.query(Prompt).count() == 1
            suggestions = session.query(LlmDocumentSuggestion).all()
            assert len(suggestions) == 1
            assert suggestions[0].suggested_file_name == "Suggested.pdf"
    finally:
        engine.dispose()


def _now() -> datetime:
    return datetime.now(tz=UTC).replace(tzinfo=None)
