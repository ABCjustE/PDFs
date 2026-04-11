from __future__ import annotations

from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.repositories.taxonomy_tree import TaxonomyTreeRepository
from pdfzx.db.session import create_sqlite_engine
from pdfzx.db.session import init_sqlite_db


def test_taxonomy_tree_repository_crud_and_membership(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    Document(
                        sha256="a",
                        md5="a" * 32,
                        file_name="a.pdf",
                        metadata_extra_json={},
                        languages_json=[],
                        is_digital=True,
                        force_extracted=False,
                    ),
                    Document(
                        sha256="b",
                        md5="b" * 32,
                        file_name="b.pdf",
                        metadata_extra_json={},
                        languages_json=[],
                        is_digital=True,
                        force_extracted=False,
                    ),
                ]
            )
            repo = TaxonomyTreeRepository(session)
            root = repo.create_node(name="Root", path="Root")
            child = repo.create_node(
                name="Physics", path="Root/Physics", parent_id=root.id, depth=1
            )
            assert repo.get_node(node_id=root.id) is not None
            assert repo.get_node_by_path(path="Root/Physics") is not None
            assert [node.path for node in repo.list_nodes()] == ["Root"]
            assert [node.path for node in repo.list_nodes(parent_id=root.id)] == ["Root/Physics"]
            assert repo.add_documents(node_id=root.id, sha256s=["a", "a", "b", "missing"]) == 2
            assert repo.list_document_sha256s(node_id=root.id) == ["a", "b"]
            assert repo.replace_documents(node_id=root.id, sha256s=["b"]) == 1
            assert repo.list_document_sha256s(node_id=root.id) == ["b"]
            assignment = repo.upsert_assignment(
                node_id=root.id,
                sha256="b",
                assigned_child_id=child.id,
                confidence="high",
                status="pending",
            )
            assert assignment.assigned_child_id == child.id
            updated = repo.upsert_assignment(
                node_id=root.id,
                sha256="b",
                assigned_child_id=child.id,
                confidence="medium",
                status="applied",
            )
            assert updated.confidence == "medium"
            assert updated.status == "applied"
            assert len(repo.list_assignments(node_id=root.id)) == 1
            repo.update_node(node_id=child.id, name="Physics Updated")
            assert repo.get_node(node_id=child.id).name == "Physics Updated"
            repo.delete_node(node_id=child.id)
            assert repo.get_node(node_id=child.id) is None
            session.commit()
    finally:
        engine.dispose()


def test_taxonomy_tree_repository_bootstraps_root_membership(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    Document(
                        sha256="a",
                        md5="a" * 32,
                        file_name="a.pdf",
                        metadata_extra_json={},
                        languages_json=[],
                        is_digital=True,
                        force_extracted=False,
                    ),
                    Document(
                        sha256="b",
                        md5="b" * 32,
                        file_name="b.pdf",
                        metadata_extra_json={},
                        languages_json=[],
                        is_digital=True,
                        force_extracted=False,
                    ),
                ]
            )
            repo = TaxonomyTreeRepository(session)
            root = repo.ensure_root_node()
            same_root = repo.ensure_root_node()
            assert same_root.id == root.id
            assert root.parent_id is None
            assert root.depth == 0
            assert repo.sync_root_documents(root_node_id=root.id) == 2
            assert repo.list_document_sha256s(node_id=root.id) == ["a", "b"]
            session.commit()
    finally:
        engine.dispose()


def test_taxonomy_tree_repository_ensures_child_node(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            repo = TaxonomyTreeRepository(session)
            root = repo.ensure_root_node()
            physics = repo.ensure_child_node(
                parent_id=root.id,
                parent_path=root.path,
                name="Physics",
            )
            same_physics = repo.ensure_child_node(
                parent_id=root.id,
                parent_path=root.path,
                name="Physics",
            )
            assert physics.id == same_physics.id
            assert physics.path == "Root/Physics"
            assert physics.depth == 1
            session.commit()
    finally:
        engine.dispose()


def test_taxonomy_tree_repository_replaces_child_subtree(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            session.add(
                Document(
                    sha256="a",
                    md5="a" * 32,
                    file_name="a.pdf",
                    metadata_extra_json={},
                    languages_json=[],
                    is_digital=True,
                    force_extracted=False,
                )
            )
            repo = TaxonomyTreeRepository(session)
            root = repo.ensure_root_node()
            physics = repo.ensure_child_node(
                parent_id=root.id,
                parent_path=root.path,
                name="Physics",
            )
            quantum = repo.ensure_child_node(
                parent_id=physics.id,
                parent_path=physics.path,
                name="Quantum Mechanics",
            )
            repo.add_documents(node_id=quantum.id, sha256s=["a"])
            repo.upsert_assignment(
                node_id=root.id,
                sha256="a",
                assigned_child_id=physics.id,
                confidence="high",
                status="pending",
            )
            deleted_count = repo.replace_child_subtree(parent_id=root.id)
            assert deleted_count == 2
            assert repo.get_node(node_id=physics.id) is None
            assert repo.get_node(node_id=quantum.id) is None
            assert repo.list_nodes(parent_id=root.id) == []
            assert repo.list_assignments(node_id=root.id) == []
            session.commit()
    finally:
        engine.dispose()
