"""Tests for pdfzx.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdfzx.config import ScanConfig
from pdfzx.config import get_config


def test_scan_config_resolves_existing_paths(tmp_path: Path) -> None:
    db_path = tmp_path / "db.json"

    config = ScanConfig(root_path=tmp_path, db_path=db_path)

    assert config.root_path == tmp_path.resolve()
    assert config.db_path == db_path.resolve()


def test_scan_config_rejects_missing_root(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing-root"

    with pytest.raises(ValueError, match="PDFZX_PDF_ROOT does not exist"):
        ScanConfig(root_path=missing_root, db_path=tmp_path / "db.json")


def test_scan_config_rejects_non_directory_root(tmp_path: Path) -> None:
    root_file = tmp_path / "root.txt"
    root_file.write_text("not a directory")

    with pytest.raises(ValueError, match="PDFZX_PDF_ROOT is not a directory"):
        ScanConfig(root_path=root_file, db_path=tmp_path / "db.json")


def test_scan_config_rejects_missing_db_parent(tmp_path: Path) -> None:
    db_path = tmp_path / "missing-parent" / "db.json"

    with pytest.raises(ValueError, match="PDFZX_JSON_DB parent directory does not exist"):
        ScanConfig(root_path=tmp_path, db_path=db_path)


def test_scan_config_rejects_non_directory_db_parent(tmp_path: Path) -> None:
    parent_file = tmp_path / "parent-file"
    parent_file.write_text("not a directory")
    db_path = parent_file / "db.json"

    with pytest.raises(ValueError, match="PDFZX_JSON_DB parent path is not a directory"):
        ScanConfig(root_path=tmp_path, db_path=db_path)


def test_get_config_requires_pdfzx_pdf_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PDFZX_PDF_ROOT", raising=False)
    monkeypatch.delenv("PDFZX_JSON_DB", raising=False)

    with pytest.raises(ValueError, match="PDFZX_PDF_ROOT environment variable is required"):
        get_config()


def test_get_config_reads_environment_each_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_root = tmp_path / "root-one"
    second_root = tmp_path / "root-two"
    first_root.mkdir()
    second_root.mkdir()

    first_db = tmp_path / "first.json"
    second_db = tmp_path / "second.json"

    monkeypatch.setenv("PDFZX_PDF_ROOT", str(first_root))
    monkeypatch.setenv("PDFZX_JSON_DB", str(first_db))
    first_config = get_config()

    monkeypatch.setenv("PDFZX_PDF_ROOT", str(second_root))
    monkeypatch.setenv("PDFZX_JSON_DB", str(second_db))
    second_config = get_config()

    assert first_config.root_path == first_root.resolve()
    assert second_config.root_path == second_root.resolve()
    assert first_config.db_path == first_db.resolve()
    assert second_config.db_path == second_db.resolve()


def test_get_config_reads_name_normalization_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PDFZX_PDF_ROOT", str(tmp_path))
    monkeypatch.setenv("PDFZX_JSON_DB", str(tmp_path / "db.json"))
    monkeypatch.setenv("PDFZX_ENABLE_NAME_NORMALIZATION", "false")

    config = get_config()

    assert config.normalize_document_name is False


def test_get_config_reads_fulltext_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custom_dir = tmp_path / "my_fulltext"
    monkeypatch.setenv("PDFZX_PDF_ROOT", str(tmp_path))
    monkeypatch.setenv("PDFZX_JSON_DB", str(tmp_path / "db.json"))
    monkeypatch.setenv("PDFZX_FULLTEXT_DIR", str(custom_dir))

    config = get_config()

    assert config.fulltext_dir == custom_dir


def test_get_config_extract_text_default_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PDFZX_PDF_ROOT", str(tmp_path))
    monkeypatch.setenv("PDFZX_JSON_DB", str(tmp_path / "db.json"))
    monkeypatch.delenv("PDFZX_EXTRACT_TEXT", raising=False)

    config = get_config()

    assert config.extract_text is True


def test_get_config_extract_text_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PDFZX_PDF_ROOT", str(tmp_path))
    monkeypatch.setenv("PDFZX_JSON_DB", str(tmp_path / "db.json"))
    monkeypatch.setenv("PDFZX_EXTRACT_TEXT", "false")

    config = get_config()

    assert config.extract_text is False


def test_get_config_online_features_default_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PDFZX_PDF_ROOT", str(tmp_path))
    monkeypatch.setenv("PDFZX_JSON_DB", str(tmp_path / "db.json"))
    monkeypatch.delenv("PDFZX_ONLINE_FEATURES", raising=False)

    config = get_config()

    assert config.online_features is False


def test_get_config_reads_online_features_and_openai_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PDFZX_PDF_ROOT", str(tmp_path))
    monkeypatch.setenv("PDFZX_JSON_DB", str(tmp_path / "db.json"))
    monkeypatch.setenv("PDFZX_ONLINE_FEATURES", "true")
    monkeypatch.setenv("PDFZX_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("PDFZX_OPENAI_MODEL", "gpt-4o-mini")

    config = get_config()

    assert config.online_features is True
    assert config.openai_api_key == "test-key"
    assert config.openai_model == "gpt-4o-mini"


def test_get_config_reads_sqlite_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sqlite_path = tmp_path / "db.sqlite3"
    monkeypatch.setenv("PDFZX_PDF_ROOT", str(tmp_path))
    monkeypatch.setenv("PDFZX_JSON_DB", str(tmp_path / "db.json"))
    monkeypatch.setenv("PDFZX_SQLITE3_DB_PATH", str(sqlite_path))

    config = get_config()

    assert config.sqlite3_db_path == sqlite_path.resolve()
