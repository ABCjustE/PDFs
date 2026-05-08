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
from pdfzx.models import Registry
from pdfzx.storage import SqliteStorage
from pdfzx.utils import compute_hashes

CLIENT_PATH = Path(__file__).resolve().parents[2] / "client.py"
CLIENT_SPEC = importlib.util.spec_from_file_location("pdfzx_client", CLIENT_PATH)
assert CLIENT_SPEC is not None
assert CLIENT_SPEC.loader is not None
client = importlib.util.module_from_spec(CLIENT_SPEC)
sys.modules[CLIENT_SPEC.name] = client
CLIENT_SPEC.loader.exec_module(client)


def test_run_taxonomy_assignments_persists_stay_status(monkeypatch, tmp_path) -> None:
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

    assert result["persisted"] == 1
    assert result["failed"] == 0
    assert result["results"][0]["persisted"] is True
    assert result["results"][0]["parsed_response"]["assignment_action"] == "stay"

    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            repo = TaxonomyTreeRepository(session)
            root = repo.get_node_by_path(path="Root")
            assert root is not None
            assignments = repo.list_assignments(node_id=root.id)
            assert len(assignments) == 1
            assert assignments[0].assigned_child_id is None
            assert assignments[0].status == "stay"
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


def test_show_document_path_drift_reports_unsynced_paths(tmp_path: Path) -> None:
    pdf_root = tmp_path / "pdf_root"
    pdf_root.mkdir()
    db_path = tmp_path / "db.sqlite3"

    only_db = DocumentRecord(
        sha256="a" * 64,
        md5="b" * 32,
        file_name="only-db.pdf",
        paths=["Books/only-db.pdf"],
    )
    mismatch_db = DocumentRecord(
        sha256="c" * 64,
        md5="d" * 32,
        file_name="mismatch.pdf",
        paths=["Books/mismatch.pdf"],
    )
    SqliteStorage(db_path).save(
        Registry(documents={only_db.sha256: only_db, mismatch_db.sha256: mismatch_db})
    )

    only_fs_path = pdf_root / "Books" / "only-fs.pdf"
    only_fs_path.parent.mkdir(parents=True)
    only_fs_path.write_bytes(b"only fs")

    mismatch_path = pdf_root / "Books" / "mismatch.pdf"
    mismatch_path.write_bytes(b"actual mismatch")

    config = ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json", sqlite3_db_path=db_path)

    result = client._show_document_path_drift(config)  # noqa: SLF001

    assert result["db_path_count"] == 2
    assert result["filesystem_path_count"] == 2
    assert result["known_hash_missing_path"] == []
    assert result["missing_hash"] == [
        {
            "rel_path": "Books/only-fs.pdf",
            "sha256": compute_hashes(only_fs_path)["sha256"],
        }
    ]
    assert result["missing_on_disk"] == [
        {
            "rel_path": "Books/only-db.pdf",
            "sha256": "a" * 64,
            "file_name": "only-db.pdf",
        }
    ]
    assert len(result["hash_mismatch"]) == 1
    assert result["hash_mismatch"][0]["rel_path"] == "Books/mismatch.pdf"
    assert result["hash_mismatch"][0]["db_sha256"] == "c" * 64


def test_show_document_path_drift_reports_known_hash_missing_path(tmp_path: Path) -> None:
    pdf_root = tmp_path / "pdf_root"
    pdf_root.mkdir()
    db_path = tmp_path / "db.sqlite3"
    existing_path = pdf_root / "Books" / "known.pdf"
    existing_path.parent.mkdir(parents=True)
    existing_path.write_bytes(b"known")
    known_sha256 = compute_hashes(existing_path)["sha256"]
    SqliteStorage(db_path).save(
        Registry(
            documents={
                known_sha256: DocumentRecord(
                    sha256=known_sha256,
                    md5="b" * 32,
                    file_name="known.pdf",
                    paths=["Books/known.pdf"],
                )
            }
        )
    )
    copied_path = pdf_root / "Books" / "renamed-known.pdf"
    copied_path.write_bytes(existing_path.read_bytes())
    config = ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json", sqlite3_db_path=db_path)

    result = client._show_document_path_drift(config)  # noqa: SLF001

    assert result["missing_hash"] == []
    assert result["known_hash_missing_path"] == [
        {
            "rel_path": "Books/renamed-known.pdf",
            "sha256": known_sha256,
            "known_rel_paths": ["Books/known.pdf"],
        }
    ]


def test_reconcile_document_paths_applies_known_hash_and_stale_path(
    make_pdf, pdf_root: Path, tmp_path: Path
) -> None:
    db_path = tmp_path / "db.sqlite3"
    old_path = pdf_root / "Books" / "Apple Training.pdf"
    old_path.parent.mkdir(parents=True)
    original = make_pdf("original.pdf", ["apple"])
    original.rename(old_path)
    original_bytes = old_path.read_bytes()
    known_sha256 = compute_hashes(old_path)["sha256"]
    SqliteStorage(db_path).save(
        Registry(
            documents={
                known_sha256: DocumentRecord(
                    sha256=known_sha256,
                    md5="b" * 32,
                    file_name="Apple Training.pdf",
                    paths=["Books/Apple Training.pdf"],
                )
            }
        )
    )
    old_path.unlink()
    new_path = pdf_root / "Books" / "macOS Support Essentials 10.14.pdf"
    new_path.write_bytes(original_bytes)
    config = ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json", sqlite3_db_path=db_path)

    result = client._reconcile_document_paths(config)  # noqa: SLF001

    assert result["discovered_rel_paths"] == ["Books/macOS Support Essentials 10.14.pdf"]
    assert result["removed_rel_paths"] == ["Books/Apple Training.pdf"]
    storage = SqliteStorage(db_path)
    registry = storage.load()
    document = registry.documents[known_sha256]
    assert document.file_name == "macOS Support Essentials 10.14.pdf"
    assert document.paths == ["Books/macOS Support Essentials 10.14.pdf"]


def test_reconcile_document_paths_continues_after_discovery_failure(
    make_pdf, tmp_path: Path
) -> None:
    pdf_root = tmp_path / "pdf_root"
    pdf_root.mkdir()
    db_path = tmp_path / "db.sqlite3"
    broken_path = pdf_root / "Books" / "broken.pdf"
    ok_path = pdf_root / "Books" / "ok.pdf"
    broken_path.parent.mkdir(parents=True)
    broken_path.write_bytes(b"")
    valid_pdf = make_pdf("ok.pdf", ["ok"])
    valid_pdf.rename(ok_path)
    config = ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json", sqlite3_db_path=db_path)

    result = client._reconcile_document_paths(config)  # noqa: SLF001

    assert result["discovered_rel_paths"] == ["Books/ok.pdf"]
    assert result["failed_count"] == 1
    assert result["failed"][0]["rel_path"] == "Books/broken.pdf"
    assert result["failed"][0]["error_type"] == "EmptyFileError"


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
