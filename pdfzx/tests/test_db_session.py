from __future__ import annotations

import sqlite3
from pathlib import Path

from pdfzx.db.session import init_sqlite_db


def test_init_sqlite_db_creates_current_llm_document_suggestion_columns(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "fresh.sqlite3"

    init_sqlite_db(db_path)

    connection = sqlite3.connect(db_path)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(llm_document_suggestions)")
        }
        assert "suggested_file_name" in columns
        assert "reasoning_summary" in columns
        assert "status" in columns
        assert "applied" in columns
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "taxonomy_nodes" in tables
        assert "taxonomy_node_documents" in tables
        assert "taxonomy_assignments" in tables
        assert "taxonomy_node_topic_terms" in tables
    finally:
        connection.close()
