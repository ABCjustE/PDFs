from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session
from watchdog.events import FileCreatedEvent
from watchdog.events import FileDeletedEvent
from watchdog.events import FileModifiedEvent
from watchdog.events import FileMovedEvent

from pdfzx.config import ScanConfig
from pdfzx.db.models import Document
from pdfzx.db.models import DocumentPath
from pdfzx.db.models import TaxonomyAssignment
from pdfzx.db.models import TaxonomyNode
from pdfzx.db.models import TaxonomyNodeDocument
from pdfzx.db.session import create_sqlite_engine
from pdfzx.watch.service import WatchService


def test_watch_service_routes_created_pdf_inside_root(tmp_path: Path) -> None:
    service = WatchService(root=tmp_path, logger=logging.getLogger("test.watch"))

    operation = service.handle_event(FileCreatedEvent(str(tmp_path / "Books" / "a.pdf")))

    assert operation is not None
    assert operation.operation == "path_discovered"
    assert operation.src_rel_path == "Books/a.pdf"
    assert operation.dest_rel_path is None


def test_watch_service_routes_moved_pdf_within_root(tmp_path: Path) -> None:
    service = WatchService(root=tmp_path, logger=logging.getLogger("test.watch"))

    operation = service.handle_event(
        FileMovedEvent(str(tmp_path / "Books" / "a.pdf"), str(tmp_path / "Physics" / "a.pdf"))
    )

    assert operation is not None
    assert operation.operation == "path_moved"
    assert operation.src_rel_path == "Books/a.pdf"
    assert operation.dest_rel_path == "Physics/a.pdf"


def test_watch_service_routes_deleted_pdf_inside_root(tmp_path: Path) -> None:
    service = WatchService(root=tmp_path, logger=logging.getLogger("test.watch"))

    operation = service.handle_event(FileDeletedEvent(str(tmp_path / "Books" / "a.pdf")))

    assert operation is not None
    assert operation.operation == "path_missing"
    assert operation.src_rel_path == "Books/a.pdf"


def test_watch_service_routes_modified_as_discovered_for_unknown_path(tmp_path: Path) -> None:
    service = WatchService(root=tmp_path, logger=logging.getLogger("test.watch"))

    operation = service.handle_event(FileModifiedEvent(str(tmp_path / "Books" / "a.pdf")))

    assert operation is not None
    assert operation.operation == "path_discovered"
    assert operation.src_rel_path == "Books/a.pdf"


def test_watch_service_ignores_modified_for_known_path(
    make_pdf, pdf_root: Path, tmp_path: Path
) -> None:
    path = make_pdf("known.pdf", ["known"])
    destination = pdf_root / "Books" / "known.pdf"
    destination.parent.mkdir(parents=True)
    path.rename(destination)
    db_path = tmp_path / "db.sqlite3"
    config = ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json", sqlite3_db_path=db_path)
    service = WatchService(root=pdf_root, config=config, logger=logging.getLogger("test.watch"))
    service.handle_event(FileCreatedEvent(str(destination)))

    operation = service.handle_event(FileModifiedEvent(str(destination)))

    assert operation is None
    service.close()


def test_watch_service_ignores_non_pdf_and_outside_root(tmp_path: Path) -> None:
    service = WatchService(root=tmp_path, logger=logging.getLogger("test.watch"))
    outside_root = tmp_path.parent / "outside.pdf"

    assert service.handle_event(FileCreatedEvent(str(tmp_path / "Books" / "a.txt"))) is None
    assert service.handle_event(FileCreatedEvent(str(outside_root))) is None


def test_watch_service_discovers_via_modified_event_for_copy(
    make_pdf, pdf_root: Path, tmp_path: Path
) -> None:
    path = make_pdf("copied.pdf", ["copied"])
    destination = pdf_root / "Books" / "copied.pdf"
    destination.parent.mkdir(parents=True)
    path.rename(destination)
    db_path = tmp_path / "db.sqlite3"
    config = ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json", sqlite3_db_path=db_path)
    service = WatchService(root=pdf_root, config=config, logger=logging.getLogger("test.watch"))

    service.handle_event(FileModifiedEvent(str(destination)))

    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            assert session.query(Document).count() == 1
            assert session.query(DocumentPath).filter_by(rel_path="Books/copied.pdf").count() == 1
    finally:
        engine.dispose()
        service.close()


def test_watch_service_persists_discovered_document(
    make_pdf, pdf_root: Path, tmp_path: Path
) -> None:
    path = make_pdf("watch.pdf", ["watch"])
    destination = pdf_root / "Books" / "watch.pdf"
    destination.parent.mkdir(parents=True)
    path.rename(destination)
    db_path = tmp_path / "db.sqlite3"
    config = ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json", sqlite3_db_path=db_path)
    service = WatchService(root=pdf_root, config=config, logger=logging.getLogger("test.watch"))

    service.handle_event(FileCreatedEvent(str(destination)))

    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            document = session.query(Document).one()
            assert document.file_name == "watch.pdf"
            assert (
                session.query(DocumentPath).filter_by(rel_path="Books/watch.pdf").one().sha256
                == document.sha256
            )
    finally:
        engine.dispose()
        service.close()


def test_watch_service_moves_known_path(make_pdf, pdf_root: Path, tmp_path: Path) -> None:
    source = make_pdf("move.pdf", ["move"])
    original = pdf_root / "Books" / "move.pdf"
    original.parent.mkdir(parents=True)
    source.rename(original)
    db_path = tmp_path / "db.sqlite3"
    config = ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json", sqlite3_db_path=db_path)
    service = WatchService(root=pdf_root, config=config, logger=logging.getLogger("test.watch"))
    service.handle_event(FileCreatedEvent(str(original)))
    moved = pdf_root / "Books" / "Moved" / "renamed.pdf"
    moved.parent.mkdir(parents=True)
    original.rename(moved)

    service.handle_event(FileMovedEvent(str(original), str(moved)))

    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            assert (
                session.query(DocumentPath).filter_by(rel_path="Books/move.pdf").one_or_none()
                is None
            )
            document_path = (
                session.query(DocumentPath).filter_by(rel_path="Books/Moved/renamed.pdf").one()
            )
            assert session.get(Document, document_path.sha256).file_name == "renamed.pdf"
    finally:
        engine.dispose()
        service.close()


def _make_service(pdf_root: Path, tmp_path: Path, taxonomy_root_name: str = "Root"):
    db_path = tmp_path / "db.sqlite3"
    config = ScanConfig(
        root_path=pdf_root,
        db_path=tmp_path / "db.json",
        sqlite3_db_path=db_path,
        taxonomy_root_name=taxonomy_root_name,
    )
    return WatchService(
        root=pdf_root, config=config, logger=logging.getLogger("test.watch")
    ), db_path


def test_watch_service_adds_to_root_node_on_discovery(
    make_pdf, pdf_root: Path, tmp_path: Path
) -> None:
    path = make_pdf("tax.pdf", ["tax"])
    destination = pdf_root / "Books" / "tax.pdf"
    destination.parent.mkdir(parents=True)
    path.rename(destination)
    service, db_path = _make_service(pdf_root, tmp_path)

    service.handle_event(FileCreatedEvent(str(destination)))

    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            doc = session.query(Document).one()
            root = session.query(TaxonomyNode).filter_by(path="Root").one()
            assert (
                session.get(TaxonomyNodeDocument, {"node_id": root.id, "sha256": doc.sha256})
                is not None
            )
    finally:
        engine.dispose()
        service.close()


def test_watch_service_removes_from_root_node_when_last_path_deleted(
    make_pdf, pdf_root: Path, tmp_path: Path
) -> None:
    path = make_pdf("gone.pdf", ["gone"])
    destination = pdf_root / "Books" / "gone.pdf"
    destination.parent.mkdir(parents=True)
    path.rename(destination)
    service, db_path = _make_service(pdf_root, tmp_path)
    service.handle_event(FileCreatedEvent(str(destination)))
    destination.unlink()

    service.handle_event(FileDeletedEvent(str(destination)))

    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            doc = session.query(Document).one()
            assert session.query(TaxonomyNodeDocument).filter_by(sha256=doc.sha256).count() == 0
    finally:
        engine.dispose()
        service.close()


def test_watch_service_adds_to_specific_node_on_discovery_inside_taxonomy_root(
    make_pdf, pdf_root: Path, tmp_path: Path
) -> None:
    path = make_pdf("math.pdf", ["math"])
    destination = pdf_root / "Root" / "Math" / "math.pdf"
    destination.parent.mkdir(parents=True)
    path.rename(destination)
    service, db_path = _make_service(pdf_root, tmp_path)

    service.handle_event(FileCreatedEvent(str(destination)))

    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            doc = session.query(Document).one()
            math_node = session.query(TaxonomyNode).filter_by(path="Root/Math").one()
            assert (
                session.get(TaxonomyNodeDocument, {"node_id": math_node.id, "sha256": doc.sha256})
                is not None
            )
    finally:
        engine.dispose()
        service.close()


def test_watch_service_ensures_node_chain_on_deep_discovery(
    make_pdf, pdf_root: Path, tmp_path: Path
) -> None:
    path = make_pdf("deep.pdf", ["deep"])
    destination = pdf_root / "Root" / "Science" / "Physics" / "deep.pdf"
    destination.parent.mkdir(parents=True)
    path.rename(destination)
    service, db_path = _make_service(pdf_root, tmp_path)

    service.handle_event(FileCreatedEvent(str(destination)))

    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            assert session.query(TaxonomyNode).filter_by(path="Root").count() == 1
            assert session.query(TaxonomyNode).filter_by(path="Root/Science").count() == 1
            assert session.query(TaxonomyNode).filter_by(path="Root/Science/Physics").count() == 1
            doc = session.query(Document).one()
            leaf = session.query(TaxonomyNode).filter_by(path="Root/Science/Physics").one()
            assert (
                session.get(TaxonomyNodeDocument, {"node_id": leaf.id, "sha256": doc.sha256})
                is not None
            )
    finally:
        engine.dispose()
        service.close()


def test_watch_service_moves_taxonomy_membership_within_root(
    make_pdf, pdf_root: Path, tmp_path: Path
) -> None:
    path = make_pdf("refile.pdf", ["refile"])
    src = pdf_root / "Root" / "Math" / "refile.pdf"
    src.parent.mkdir(parents=True)
    path.rename(src)
    service, db_path = _make_service(pdf_root, tmp_path)
    service.handle_event(FileCreatedEvent(str(src)))
    dst = pdf_root / "Root" / "Science" / "refile.pdf"
    dst.parent.mkdir(parents=True)
    src.rename(dst)

    service.handle_event(FileMovedEvent(str(src), str(dst)))

    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            doc = session.query(Document).one()
            math_node = session.query(TaxonomyNode).filter_by(path="Root/Math").one()
            science_node = session.query(TaxonomyNode).filter_by(path="Root/Science").one()
            assert (
                session.get(TaxonomyNodeDocument, {"node_id": math_node.id, "sha256": doc.sha256})
                is None
            )
            assert (
                session.get(
                    TaxonomyNodeDocument, {"node_id": science_node.id, "sha256": doc.sha256}
                )
                is not None
            )
    finally:
        engine.dispose()
        service.close()


def test_watch_service_marks_assignments_manual_touched_on_move_within_root(
    make_pdf, pdf_root: Path, tmp_path: Path
) -> None:
    from datetime import UTC
    from datetime import datetime

    path = make_pdf("override.pdf", ["override"])
    src = pdf_root / "Root" / "Math" / "override.pdf"
    src.parent.mkdir(parents=True)
    path.rename(src)
    service, db_path = _make_service(pdf_root, tmp_path)
    service.handle_event(FileCreatedEvent(str(src)))

    engine = create_sqlite_engine(db_path)
    with Session(engine) as session:
        doc = session.query(Document).one()
        math_node = session.query(TaxonomyNode).filter_by(path="Root/Math").one()
        now = datetime.now(tz=UTC).replace(tzinfo=None)
        session.add(
            TaxonomyAssignment(
                node_id=math_node.id,
                sha256=doc.sha256,
                assigned_child_id=None,
                status="applied",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
    engine.dispose()

    dst = pdf_root / "Root" / "Science" / "override.pdf"
    dst.parent.mkdir(parents=True)
    src.rename(dst)
    service.handle_event(FileMovedEvent(str(src), str(dst)))

    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            doc = session.query(Document).one()
            assignment = session.query(TaxonomyAssignment).filter_by(sha256=doc.sha256).one()
            assert assignment.status == "manual_touched"
    finally:
        engine.dispose()
        service.close()


def test_watch_service_marks_assignments_manual_touched_on_move_into_root(
    make_pdf, pdf_root: Path, tmp_path: Path
) -> None:
    from datetime import UTC
    from datetime import datetime

    path = make_pdf("into-root.pdf", ["into-root"])
    src = pdf_root / "Books" / "into-root.pdf"
    src.parent.mkdir(parents=True)
    path.rename(src)
    service, db_path = _make_service(pdf_root, tmp_path)
    service.handle_event(FileCreatedEvent(str(src)))

    engine = create_sqlite_engine(db_path)
    with Session(engine) as session:
        doc = session.query(Document).one()
        root = session.query(TaxonomyNode).filter_by(path="Root").one()
        now = datetime.now(tz=UTC).replace(tzinfo=None)
        session.add(
            TaxonomyAssignment(
                node_id=root.id,
                sha256=doc.sha256,
                assigned_child_id=None,
                status="applied",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
    engine.dispose()

    dst = pdf_root / "Root" / "Science" / "into-root.pdf"
    dst.parent.mkdir(parents=True)
    src.rename(dst)
    service.handle_event(FileMovedEvent(str(src), str(dst)))

    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            doc = session.query(Document).one()
            assignment = session.query(TaxonomyAssignment).filter_by(sha256=doc.sha256).one()
            assert assignment.status == "manual_touched"
    finally:
        engine.dispose()
        service.close()


def test_watch_service_deletes_known_path_but_keeps_document(
    make_pdf, pdf_root: Path, tmp_path: Path
) -> None:
    source = make_pdf("delete.pdf", ["delete"])
    path = pdf_root / "Books" / "delete.pdf"
    path.parent.mkdir(parents=True)
    source.rename(path)
    db_path = tmp_path / "db.sqlite3"
    config = ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json", sqlite3_db_path=db_path)
    service = WatchService(root=pdf_root, config=config, logger=logging.getLogger("test.watch"))
    service.handle_event(FileCreatedEvent(str(path)))
    path.unlink()

    service.handle_event(FileDeletedEvent(str(path)))

    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            assert (
                session.query(DocumentPath).filter_by(rel_path="Books/delete.pdf").one_or_none()
                is None
            )
            assert session.query(Document).count() == 1
    finally:
        engine.dispose()
        service.close()
