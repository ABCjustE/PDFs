from __future__ import annotations

from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.models import DocumentPath
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
                reasoning_summary="Broad physics fit.",
                status="pending",
            )
            assert assignment.assigned_child_id == child.id
            assert assignment.reasoning_summary == "Broad physics fit."
            updated = repo.upsert_assignment(
                node_id=root.id,
                sha256="b",
                assigned_child_id=child.id,
                confidence="medium",
                reasoning_summary="Still physics, lower confidence.",
                status="applied",
            )
            assert updated.confidence == "medium"
            assert updated.reasoning_summary == "Still physics, lower confidence."
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
                parent_id=root.id, parent_path=root.path, name="Physics"
            )
            same_physics = repo.ensure_child_node(
                parent_id=root.id, parent_path=root.path, name="Physics"
            )
            assert physics.id == same_physics.id
            assert physics.path == "Root/Physics"
            assert physics.depth == 1
            session.commit()
    finally:
        engine.dispose()


def test_taxonomy_tree_repository_replaces_topic_terms(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            repo = TaxonomyTreeRepository(session)
            root = repo.ensure_root_node()
            physics = repo.ensure_child_node(
                parent_id=root.id, parent_path=root.path, name="Physics"
            )
            assert (
                repo.replace_topic_terms(
                    node_id=physics.id,
                    terms=["Quantum Mechanics", " Electromagnetism ", "Quantum Mechanics", ""],
                )
                == 2
            )
            assert repo.list_topic_terms(node_id=physics.id) == [
                "Electromagnetism",
                "Quantum Mechanics",
            ]
            assert repo.replace_topic_terms(node_id=physics.id, terms=["Mechanics"]) == 1
            assert repo.list_topic_terms(node_id=physics.id) == ["Mechanics"]
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
                parent_id=root.id, parent_path=root.path, name="Physics"
            )
            quantum = repo.ensure_child_node(
                parent_id=physics.id, parent_path=physics.path, name="Quantum Mechanics"
            )
            repo.add_documents(node_id=quantum.id, sha256s=["a"])
            repo.upsert_assignment(
                node_id=root.id,
                sha256="a",
                assigned_child_id=physics.id,
                confidence="high",
                reasoning_summary="Physics child is the best fit.",
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


def test_taxonomy_tree_repository_applies_high_confidence_assignments(tmp_path) -> None:
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
            physics = repo.ensure_child_node(
                parent_id=root.id, parent_path=root.path, name="Physics"
            )
            repo.add_documents(node_id=root.id, sha256s=["a", "b"])
            repo.upsert_assignment(
                node_id=root.id,
                sha256="a",
                assigned_child_id=physics.id,
                confidence="high",
                reasoning_summary="Physics label is obvious.",
                status="pending",
            )
            repo.upsert_assignment(
                node_id=root.id,
                sha256="b",
                assigned_child_id=physics.id,
                confidence="low",
                reasoning_summary="Weak physics clue only.",
                status="pending",
            )
            summary = repo.apply_assignments(node_id=root.id, minimum_confidence="high")
            assert summary == {"applied": 1, "skipped": 1, "excluded": 0}
            assert repo.list_document_sha256s(node_id=physics.id) == ["a"]
            assert repo.list_document_sha256s(node_id=root.id) == ["b"]
            assignments = repo.list_assignments(node_id=root.id)
            assert assignments[0].status == "applied"
            assert assignments[1].status == "pending"
            session.commit()
    finally:
        engine.dispose()


def test_taxonomy_tree_repository_lists_assignment_views(tmp_path) -> None:
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
            session.add(DocumentPath(sha256="a", rel_path="Books/Physics/a.pdf"))
            repo = TaxonomyTreeRepository(session)
            root = repo.ensure_root_node()
            physics = repo.ensure_child_node(
                parent_id=root.id, parent_path=root.path, name="Physics"
            )
            repo.add_documents(node_id=root.id, sha256s=["a", "b"])
            repo.upsert_assignment(
                node_id=root.id,
                sha256="a",
                assigned_child_id=physics.id,
                confidence="high",
                reasoning_summary="Path strongly indicates physics.",
                status="pending",
            )
            rows = repo.list_assignment_views(node_id=root.id)
            assert len(rows) == 1
            assert rows[0].node_path == "Root"
            assert rows[0].document_path == "Books/Physics/a.pdf"
            assert rows[0].assigned_path == "Root/Physics"
            assert rows[0].confidence == "high"
            assert rows[0].status == "pending"
            assert rows[0].reasoning_summary == "Path strongly indicates physics."
            filtered_rows = repo.list_assignment_views(node_id=root.id, status="pending")
            assert len(filtered_rows) == 1
            assert repo.list_assignment_views(node_id=root.id, status="applied") == []
            session.commit()
    finally:
        engine.dispose()


def test_taxonomy_tree_repository_applies_with_path_keyword_exclusions(tmp_path) -> None:
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
            session.add_all(
                [
                    DocumentPath(sha256="a", rel_path="Books/Physics/a.pdf"),
                    DocumentPath(sha256="b", rel_path="archive/physics/b.pdf"),
                ]
            )
            repo = TaxonomyTreeRepository(session)
            root = repo.ensure_root_node()
            physics = repo.ensure_child_node(
                parent_id=root.id, parent_path=root.path, name="Physics"
            )
            repo.add_documents(node_id=root.id, sha256s=["a", "b"])
            repo.upsert_assignment(
                node_id=root.id,
                sha256="a",
                assigned_child_id=physics.id,
                confidence="high",
                reasoning_summary="Physics path is obvious.",
                status="pending",
            )
            repo.upsert_assignment(
                node_id=root.id,
                sha256="b",
                assigned_child_id=physics.id,
                confidence="high",
                reasoning_summary="Physics path is obvious.",
                status="pending",
            )
            summary = repo.apply_assignments(
                node_id=root.id, minimum_confidence="high", exclude_path_keywords=["archive"]
            )
            assert summary == {"applied": 1, "skipped": 0, "excluded": 1}
            assert repo.list_document_sha256s(node_id=physics.id) == ["a"]
            assert repo.list_document_sha256s(node_id=root.id) == ["b"]
            assignments = repo.list_assignments(node_id=root.id)
            assert assignments[0].status == "applied"
            assert assignments[1].status == "pending"
            session.commit()
    finally:
        engine.dispose()


def test_taxonomy_tree_repository_lists_node_stats(tmp_path) -> None:
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
            physics = repo.ensure_child_node(
                parent_id=root.id, parent_path=root.path, name="Physics"
            )
            repo.ensure_child_node(parent_id=root.id, parent_path=root.path, name="Mathematics")
            repo.add_documents(node_id=root.id, sha256s=["a", "b"])
            repo.add_documents(node_id=physics.id, sha256s=["a"])
            stats = repo.list_node_stats()
            assert stats[0].node_path == "Root"
            assert stats[0].document_count == 2
            assert stats[1].node_path == "Root/Physics"
            assert stats[1].document_count == 1
            assert stats[2].node_path == "Root/Mathematics"
            assert stats[2].document_count == 0
            depth_one = repo.list_node_stats(depth=1)
            assert [row.node_path for row in depth_one] == ["Root/Physics", "Root/Mathematics"]
            session.commit()
    finally:
        engine.dispose()


def test_taxonomy_tree_repository_lists_node_document_views(tmp_path) -> None:
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
            session.add(DocumentPath(sha256="a", rel_path="Books/Physics/a.pdf"))
            repo = TaxonomyTreeRepository(session)
            root = repo.ensure_root_node()
            physics = repo.ensure_child_node(
                parent_id=root.id, parent_path=root.path, name="Physics"
            )
            repo.add_documents(node_id=physics.id, sha256s=["a"])
            rows = repo.list_node_document_views(node_id=physics.id)
            assert len(rows) == 1
            assert rows[0].node_path == "Root/Physics"
            assert rows[0].sha256 == "a"
            assert rows[0].document_path == "Books/Physics/a.pdf"
            session.commit()
    finally:
        engine.dispose()


def test_taxonomy_tree_repository_lists_topic_terms(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            repo = TaxonomyTreeRepository(session)
            root = repo.ensure_root_node()
            physics = repo.ensure_child_node(
                parent_id=root.id, parent_path=root.path, name="Physics"
            )
            repo.replace_topic_terms(
                node_id=physics.id, terms=["Quantum Mechanics", "Electromagnetism"]
            )
            assert repo.list_topic_terms(node_id=physics.id) == [
                "Electromagnetism",
                "Quantum Mechanics",
            ]
            session.commit()
    finally:
        engine.dispose()


def test_taxonomy_tree_repository_lists_node_term_views(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            repo = TaxonomyTreeRepository(session)
            root = repo.ensure_root_node()
            physics = repo.ensure_child_node(
                parent_id=root.id, parent_path=root.path, name="Physics"
            )
            mathematics = repo.ensure_child_node(
                parent_id=root.id, parent_path=root.path, name="Mathematics"
            )
            repo.replace_topic_terms(node_id=physics.id, terms=["Quantum Mechanics"])
            repo.replace_topic_terms(node_id=mathematics.id, terms=["Linear Algebra"])
            assert [
                (row.node_id, row.node_path, row.term) for row in repo.list_node_term_views()
            ] == [
                (mathematics.id, "Root/Mathematics", "Linear Algebra"),
                (physics.id, "Root/Physics", "Quantum Mechanics"),
            ]
            assert [
                (row.node_id, row.node_path, row.term)
                for row in repo.list_node_term_views(node_id=physics.id)
            ] == [(physics.id, "Root/Physics", "Quantum Mechanics")]
            session.commit()
    finally:
        engine.dispose()
