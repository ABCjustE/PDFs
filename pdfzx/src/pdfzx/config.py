"""Configuration — reads PDFZX_ROOT and PDFZX_DB from environment."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel
from pydantic import field_validator


class ScanConfig(BaseModel):
    """Validated runtime configuration for a scan."""

    root_path: Path
    db_path: Path
    ocr_char_threshold: int = 100
    ocr_scan_pages: int = 3

    @field_validator("root_path")
    @classmethod
    def root_must_exist(cls, v: Path) -> Path:
        """Ensure root_path resolves to an accessible directory."""
        resolved = v.resolve()
        if not resolved.exists():
            msg = f"PDFZX_ROOT does not exist: {resolved}"
            raise ValueError(msg)
        if not resolved.is_dir():
            msg = f"PDFZX_ROOT is not a directory: {resolved}"
            raise ValueError(msg)
        return resolved

    @field_validator("db_path")
    @classmethod
    def db_parent_must_exist(cls, v: Path) -> Path:
        """Ensure the parent directory of db_path already exists."""
        resolved = v.resolve()
        if not resolved.parent.exists():
            msg = f"PDFZX_DB parent directory does not exist: {resolved.parent}"
            raise ValueError(msg)
        if not resolved.parent.is_dir():
            msg = f"PDFZX_DB parent path is not a directory: {resolved.parent}"
            raise ValueError(msg)
        return resolved


def get_config() -> ScanConfig:
    """Load config from environment variables.

    Returns:
        ScanConfig: validated configuration instance.

    Raises:
        ValueError: if PDFZX_ROOT is missing or invalid.
    """
    root = os.environ.get("PDFZX_ROOT")
    if not root:
        msg = "PDFZX_ROOT environment variable is required"
        raise ValueError(msg)
    db = os.environ.get("PDFZX_DB", "./db.json")
    return ScanConfig(root_path=Path(root), db_path=Path(db))
