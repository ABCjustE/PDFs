from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from pdfzx.config import ScanConfig
from pdfzx.db.models import Document
from pdfzx.db.models import DocumentPath
from pdfzx.db.repositories.taxonomy_tree import TaxonomyTreeRepository
from pdfzx.db.session import create_sqlite_engine
from pdfzx.db.session import init_sqlite_db
from pdfzx.models import DocumentRecord

CLIENT_PATH = Path(__file__).resolve().parents[2] / "client.py"
CLIENT_SPEC = importlib.util.spec_from_file_location("pdfzx_client", CLIENT_PATH)
assert CLIENT_SPEC is not None
assert CLIENT_SPEC.loader is not None
client = importlib.util.module_from_spec(CLIENT_SPEC)
sys.modules[CLIENT_SPEC.name] = client
CLIENT_SPEC.loader.exec_module(client)


def test_run_taxonomy_assignments_does_not_persist_stay(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    pdf_root = tmp_path / "pdf_root"
    pdf_root.mkdir()
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            session.add(
                Document(
                    sha256="a" * 64,
                    md5="b" * 32,
                    file_name="overview.pdf",
                    metadata_extra_json={},
                    languages_json=[],
                    is_digital=True,
                    force_extracted=False,
                )
            )
            session.add(
                DocumentPath(sha256="a" * 64, rel_path="Books/Computer Science/overview.pdf")
            )
            repo = TaxonomyTreeRepository(session)
            root = repo.ensure_root_node()
            child = repo.ensure_child_node(
                parent_id=root.id, parent_path=root.path, name="Programming"
            )
            repo.replace_topic_terms(node_id=child.id, terms=["Python", "Java"])
            repo.add_documents(node_id=root.id, sha256s=["a" * 64])
            session.commit()
    finally:
        engine.dispose()

    config = ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json", sqlite3_db_path=db_path)
    registry = SimpleNamespace(
        documents={
            "a" * 64: DocumentRecord(
                sha256="a" * 64,
                md5="b" * 32,
                file_name="overview.pdf",
                normalised_name="overview.pdf",
                paths=["Books/Computer Science/overview.pdf", "Shelf/A/overview.pdf"],
                first_seen_job="job-1",
                last_seen_job="job-1",
            )
        }
    )

    monkeypatch.setattr(client, "SqliteStorage", lambda _: SimpleNamespace(load=lambda: registry))
    monkeypatch.setattr(client, "_append_ndjson", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(client._RequestThrottle, "wait_turn", lambda self: None)  # noqa: SLF001

    def fake_assign_taxonomy_child(**kwargs):
        prompt_input = kwargs["prompt_input"]
        assert prompt_input.child_options[0].label == "Programming"
        assert prompt_input.child_options[0].topic_terms == ["Java", "Python"]
        assert prompt_input.document.current_paths == [
            "Books/Computer Science/overview.pdf",
            "Shelf/A/overview.pdf",
        ]
        return SimpleNamespace(
            prompt_input=prompt_input.model_dump(mode="json"),
            parsed_response={
                "assignment_action": "stay",
                "assigned_child": None,
                "confidence": "medium",
                "reasoning_summary": "Broad overview should remain at the current node.",
            },
        )

    monkeypatch.setattr(client, "assign_taxonomy_child", fake_assign_taxonomy_child)

    result = client._run_taxonomy_assignments(  # noqa: SLF001
        config,
        node_path="Root",
        limit=10,
        offset=0,
        max_concurrency=1,
        require_digital=False,
        require_toc=False,
        exclude_path_keywords=[],
        force=False,
        output_ndjson=None,
    )

    assert result["persisted"] == 0
    assert result["failed"] == 0
    assert result["results"][0]["persisted"] is False
    assert result["results"][0]["parsed_response"]["assignment_action"] == "stay"

    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            repo = TaxonomyTreeRepository(session)
            root = repo.get_node_by_path(path="Root")
            assert root is not None
            assert repo.list_assignments(node_id=root.id) == []
    finally:
        engine.dispose()


def test_run_taxonomy_assignments_excludes_matching_paths(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    pdf_root = tmp_path / "pdf_root"
    pdf_root.mkdir()
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            session.add(
                Document(
                    sha256="a" * 64,
                    md5="b" * 32,
                    file_name="overview.pdf",
                    metadata_extra_json={},
                    languages_json=[],
                    is_digital=True,
                    force_extracted=False,
                )
            )
            session.add(DocumentPath(sha256="a" * 64, rel_path="Archive/overview.pdf"))
            repo = TaxonomyTreeRepository(session)
            root = repo.ensure_root_node()
            repo.ensure_child_node(parent_id=root.id, parent_path=root.path, name="Programming")
            repo.add_documents(node_id=root.id, sha256s=["a" * 64])
            session.commit()
    finally:
        engine.dispose()

    config = ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json", sqlite3_db_path=db_path)
    registry = SimpleNamespace(
        documents={
            "a" * 64: DocumentRecord(
                sha256="a" * 64,
                md5="b" * 32,
                file_name="overview.pdf",
                normalised_name="overview.pdf",
                paths=["Archive/overview.pdf"],
                first_seen_job="job-1",
                last_seen_job="job-1",
            )
        }
    )

    monkeypatch.setattr(client, "SqliteStorage", lambda _: SimpleNamespace(load=lambda: registry))
    monkeypatch.setattr(client, "_append_ndjson", lambda *_args, **_kwargs: None)

    def fake_assign_taxonomy_child(**kwargs):  # pragma: no cover
        msg = "excluded documents should not be assigned"
        raise AssertionError(msg)

    monkeypatch.setattr(client, "assign_taxonomy_child", fake_assign_taxonomy_child)

    result = client._run_taxonomy_assignments(  # noqa: SLF001
        config,
        node_path="Root",
        limit=10,
        offset=0,
        max_concurrency=1,
        require_digital=False,
        require_toc=False,
        exclude_path_keywords=["archive"],
        force=False,
        output_ndjson=None,
    )

    assert result["filtered_documents"] == 0
    assert result["exclude_path_keywords"] == ["archive"]
    assert result["persisted"] == 0
    assert result["results"] == []


def test_taxonomy_exclude_path_keywords_prefers_cli_over_config() -> None:
    config = ScanConfig(
        root_path=Path(),
        db_path=Path("./db.json"),
        sqlite3_db_path=Path("./db.sqlite3"),
        taxonomy_exclude_path_keywords=["archive", "private"],
    )

    assert client._taxonomy_exclude_path_keywords(config, ["PRIVATE", "notes"]) == [  # noqa: SLF001
        "PRIVATE",
        "notes",
    ]
    assert client._taxonomy_exclude_path_keywords(config, None) == [  # noqa: SLF001
        "archive",
        "private",
    ]


def test_main_probe_taxonomy_assign_uses_config_exclude_keywords(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "db.sqlite3"
    pdf_root = tmp_path / "pdf_root"
    pdf_root.mkdir()
    monkeypatch.setenv("PDFZX_PDF_ROOT", str(pdf_root))
    monkeypatch.setenv("PDFZX_JSON_DB", str(tmp_path / "db.json"))
    monkeypatch.setenv("PDFZX_SQLITE3_DB_PATH", str(db_path))
    monkeypatch.setenv("PDFZX_TAXONOMY_EXCLUDE_PATH_KEYWORDS", "private")
    monkeypatch.setattr(
        sys, "argv", ["client.py", "probe-taxonomy-assign", "--node-path", "Root", "--limit", "1"]
    )

    captured: dict[str, object] = {}

    monkeypatch.setattr(client, "configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        client,
        "_probe_taxonomy_assignments",
        lambda config, **kwargs: (
            captured.update(
                {
                    "config_keywords": config.taxonomy_exclude_path_keywords,
                    "kwargs_keywords": kwargs["exclude_path_keywords"],
                }
            )
            or {}
        ),
    )
    monkeypatch.setattr(client, "_emit_json", lambda *_args, **_kwargs: None)

    assert client.main() == 0
    assert captured == {"config_keywords": ["private"], "kwargs_keywords": ["private"]}
