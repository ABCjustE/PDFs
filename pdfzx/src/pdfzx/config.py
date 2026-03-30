"""Configuration — reads PDFZX_* environment variables into ScanConfig."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel
from pydantic import field_validator

DEFAULT_LLM_MAX_TOC_ENTRIES = 30


class ScanConfig(BaseModel):
    """Validated runtime configuration for a scan."""

    root_path: Path
    db_path: Path
    ocr_char_threshold: int = 100
    ocr_scan_pages: int = 3
    normalize_document_name: bool = True
    fulltext_dir: Path = Path("./pdf_fulltext")
    extract_text: bool = True
    online_features: bool = False
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    sqlite3_db_path: Path = Path("./db.sqlite3")
    llm_max_toc_entries: int = DEFAULT_LLM_MAX_TOC_ENTRIES

    @field_validator("root_path")
    @classmethod
    def root_must_exist(cls, v: Path) -> Path:
        """Ensure root_path resolves to an accessible directory."""
        resolved = v.resolve()
        if not resolved.exists():
            msg = f"PDFZX_PDF_ROOT does not exist: {resolved}"
            raise ValueError(msg)
        if not resolved.is_dir():
            msg = f"PDFZX_PDF_ROOT is not a directory: {resolved}"
            raise ValueError(msg)
        return resolved

    @field_validator("db_path")
    @classmethod
    def db_parent_must_exist(cls, v: Path) -> Path:
        """Ensure the parent directory of db_path already exists."""
        resolved = v.resolve()
        if not resolved.parent.exists():
            msg = f"PDFZX_JSON_DB parent directory does not exist: {resolved.parent}"
            raise ValueError(msg)
        if not resolved.parent.is_dir():
            msg = f"PDFZX_JSON_DB parent path is not a directory: {resolved.parent}"
            raise ValueError(msg)
        return resolved

    @field_validator("sqlite3_db_path")
    @classmethod
    def sqlite_parent_must_exist(cls, v: Path) -> Path:
        """Ensure the parent directory of sqlite3_db_path already exists."""
        resolved = v.resolve()
        if not resolved.parent.exists():
            msg = f"PDFZX_SQLITE3_DB_PATH parent directory does not exist: {resolved.parent}"
            raise ValueError(msg)
        if not resolved.parent.is_dir():
            msg = f"PDFZX_SQLITE3_DB_PATH parent path is not a directory: {resolved.parent}"
            raise ValueError(msg)
        return resolved


def get_config() -> ScanConfig:
    """Load config from environment variables.

    Returns:
        ScanConfig: validated configuration instance.

    Raises:
        ValueError: if PDFZX_PDF_ROOT is missing or invalid.
    """
    root = os.environ.get("PDFZX_PDF_ROOT")
    if not root:
        msg = "PDFZX_PDF_ROOT environment variable is required"
        raise ValueError(msg)
    db = os.environ.get("PDFZX_JSON_DB", "./db.json")
    normalize_document_name = os.environ.get(
        "PDFZX_ENABLE_NAME_NORMALIZATION", "true"
    ).strip().lower() not in {"0", "false", "no", "off"}
    fulltext = os.environ.get("PDFZX_FULLTEXT_DIR", "./pdf_fulltext")
    extract_text = os.environ.get("PDFZX_EXTRACT_TEXT", "true").strip().lower() not in (
        "false",
        "0",
        "no",
        "off",
    )
    online_features = os.environ.get("PDFZX_ONLINE_FEATURES", "false").strip().lower() in (
        "true",
        "1",
        "yes",
        "on",
    )
    openai_api_key = os.environ.get("PDFZX_OPENAI_API_KEY")
    openai_model = os.environ.get("PDFZX_OPENAI_MODEL", "gpt-4o-mini")
    sqlite3_db_path = os.environ.get("PDFZX_SQLITE3_DB_PATH", "./db.sqlite3")
    llm_max_toc_entries = int(
        os.environ.get(
            "PDFZX_LLM_MAX_TOC_ENTRIES", str(DEFAULT_LLM_MAX_TOC_ENTRIES)
        )
    )
    return ScanConfig(
        root_path=Path(root),
        db_path=Path(db),
        normalize_document_name=normalize_document_name,
        fulltext_dir=Path(fulltext),
        extract_text=extract_text,
        online_features=online_features,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        sqlite3_db_path=Path(sqlite3_db_path),
        llm_max_toc_entries=llm_max_toc_entries,
    )
