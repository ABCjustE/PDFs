"""Tests for storage.JsonStorage."""

from __future__ import annotations

import pytest

from pdfzx.models import DocumentRecord
from pdfzx.models import Registry
from pdfzx.storage import JsonStorage
from pdfzx.storage import Storage


def _sample_registry() -> Registry:
    doc = DocumentRecord(sha256="abc123", md5="def456", file_name="test.pdf", paths=["test.pdf"])
    return Registry(documents={"abc123": doc})


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_json_storage_implements_protocol(tmp_path):
    assert isinstance(JsonStorage(tmp_path / "db.json"), Storage)


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


def test_load_missing_file_returns_empty(tmp_path):
    store = JsonStorage(tmp_path / "db.json")
    registry = store.load()
    assert registry.documents == {}
    assert registry.jobs == []


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
        '{"documents": {"x": {"sha256": "x"}}, "file_stats": {}, "jobs": []}', encoding="utf-8"
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
