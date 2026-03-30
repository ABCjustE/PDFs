from __future__ import annotations

import sqlite3
from pathlib import Path

from pdfzx.db.session import init_sqlite_db


def test_init_sqlite_db_upgrades_legacy_llm_document_suggestion_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE llm_document_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sha256 TEXT NOT NULL,
                prompt_id INTEGER NOT NULL,
                suggested_name VARCHAR(512),
                suggested_title VARCHAR(512),
                suggested_author VARCHAR(512),
                suggested_publisher VARCHAR(512),
                suggested_edition VARCHAR(256),
                suggested_labels_json TEXT NOT NULL DEFAULT '[]',
                reasoning_summary TEXT,
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                applied BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO llm_document_suggestions (
                sha256,
                prompt_id,
                suggested_name,
                suggested_title,
                suggested_labels_json,
                status,
                applied,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "abc",
                1,
                "Sample Book.pdf",
                "Sample Book",
                "[]",
                "pending",
                0,
                "2026-03-30T10:00:00",
                "2026-03-30T10:00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    init_sqlite_db(db_path)

    upgraded = sqlite3.connect(db_path)
    try:
        columns = {
            row[1] for row in upgraded.execute("PRAGMA table_info(llm_document_suggestions)")
        }
        assert "suggested_file_name" in columns
        copied_value = upgraded.execute(
            "SELECT suggested_file_name FROM llm_document_suggestions WHERE sha256 = ?", ("abc",)
        ).fetchone()
        assert copied_value == ("Sample Book.pdf",)
    finally:
        upgraded.close()
