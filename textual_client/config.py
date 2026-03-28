from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from pdfzx.config import ScanConfig


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_env() -> None:
    load_dotenv(project_root() / ".env")


def default_root() -> Path:
    return Path(os.environ.get("PDFZX_PDF_ROOT", project_root() / "pdf_root"))


def default_db() -> Path:
    return Path(os.environ.get("PDFZX_JSON_DB", project_root() / "db.json"))


def default_config() -> ScanConfig:
    return ScanConfig(
        root_path=default_root(),
        db_path=default_db(),
        ocr_char_threshold=int(os.environ.get("PDFZX_OCR_CHAR_THRESHOLD", "100")),
        ocr_scan_pages=int(os.environ.get("PDFZX_OCR_SCAN_PAGES", "3")),
    )


def default_log_level() -> str:
    return os.environ.get("PDFZX_LOG_LEVEL", "DEBUG")


def default_workers() -> int:
    return int(os.environ.get("PDFZX_WORKERS", "1"))


def default_choice_file() -> Path:
    return Path(os.environ.get("PDFZX_CHOICE_FILE", Path.cwd() / "yazi-choice.txt"))


def default_textual_debug_log() -> Path:
    return Path(os.environ.get("PDFZX_TEXTUAL_DEBUG_LOG", "/tmp/textual_cli.log"))


def default_textual_app_log() -> Path:
    return Path(os.environ.get("PDFZX_TEXTUAL_APP_LOG", "/tmp/textual_cli.app.log"))


def default_client_script() -> Path:
    return Path(os.environ.get("PDFZX_CLIENT_SCRIPT", project_root() / "client.py"))


def default_client_cwd() -> Path:
    return Path(os.environ.get("PDFZX_CLIENT_CWD", project_root()))
