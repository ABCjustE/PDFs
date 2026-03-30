from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from pdfzx.db.migration import migrate_json_to_sqlite
from pdfzx.db.models import Document
from pdfzx.db.models import DocumentPath
from pdfzx.db.models import DocumentTocEntry
from pdfzx.db.models import FileStat
from pdfzx.db.models import Job


def test_migrate_json_to_sqlite_imports_registry(tmp_path: Path) -> None:
    source_json = tmp_path / "db.json"
    target_sqlite = tmp_path / "db.sqlite3"
    source_json.write_text(
        """
{
  "documents": {
    "abc": {
      "sha256": "abc",
      "md5": "def",
      "paths": ["books/sample.pdf", "alt/sample.pdf"],
      "file_name": "sample.pdf",
      "normalised_name": "Sample.pdf",
      "metadata": {
        "title": "Sample",
        "author": "Author",
        "creator": "Creator",
        "created": "2024",
        "modified": "2025",
        "extra": {"publisher": "Pub"}
      },
      "toc": [{"level": 1, "title": "Chapter 1", "page": 1}],
      "languages": ["en"],
      "is_digital": true,
      "toc_valid": null,
      "toc_invalid_reason": null,
      "extraction_status": null,
      "force_extracted": false,
      "first_seen_job": "job-1",
      "last_seen_job": "job-1"
    }
  },
  "file_stats": {
    "books/sample.pdf": {
      "rel_path": "books/sample.pdf",
      "sha256": "abc",
      "size_bytes": 123,
      "mtime": 1.5,
      "last_scanned_job": "job-1"
    }
  },
  "jobs": [
    {
      "job_id": "job-1",
      "run_at": "2026-03-29T10:00:00",
      "root_path": "/tmp/root",
      "stats": {"added": 1, "updated": 0, "removed": 0, "duplicates": 0, "skipped": 0}
    }
  ]
}
        """.strip(),
        encoding="utf-8",
    )

    summary = migrate_json_to_sqlite(source_json=source_json, target_sqlite=target_sqlite)

    assert summary["documents"] == 1
    assert summary["paths"] == 2
    assert summary["toc_entries"] == 1
    assert summary["file_stats"] == 1
    assert summary["jobs"] == 1
    assert target_sqlite.exists()

    engine = create_engine(f"sqlite:///{target_sqlite}")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 1
        assert session.scalar(select(func.count()).select_from(DocumentPath)) == 2
        assert session.scalar(select(func.count()).select_from(DocumentTocEntry)) == 1
        assert session.scalar(select(func.count()).select_from(FileStat)) == 1
        assert session.scalar(select(func.count()).select_from(Job)) == 1
    engine.dispose()


def test_migrate_json_to_sqlite_requires_replace_for_existing_target(tmp_path: Path) -> None:
    source_json = tmp_path / "db.json"
    target_sqlite = tmp_path / "db.sqlite3"
    source_json.write_text('{"documents": {}, "file_stats": {}, "jobs": []}', encoding="utf-8")
    target_sqlite.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        migrate_json_to_sqlite(source_json=source_json, target_sqlite=target_sqlite)
