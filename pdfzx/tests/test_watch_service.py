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
from pdfzx.db.session import create_sqlite_engine
from pdfzx.watch.service import WatchService


def test_watch_service_routes_created_pdf_inside_root(tmp_path: Path) -> None:
    service = WatchService(root=tmp_path, logger=logging.getLogger("test.watch"))

    operation = service.handle_event(
        FileCreatedEvent(str(tmp_path / "Books" / "a.pdf"))
    )

    assert operation is not None
    assert operation.operation == "path_discovered"
    assert operation.src_rel_path == "Books/a.pdf"
    assert operation.dest_rel_path is None


def test_watch_service_routes_moved_pdf_within_root(tmp_path: Path) -> None:
    service = WatchService(root=tmp_path, logger=logging.getLogger("test.watch"))

    operation = service.handle_event(
        FileMovedEvent(
            str(tmp_path / "Books" / "a.pdf"),
            str(tmp_path / "Physics" / "a.pdf"),
        )
    )

    assert operation is not None
    assert operation.operation == "path_moved"
    assert operation.src_rel_path == "Books/a.pdf"
    assert operation.dest_rel_path == "Physics/a.pdf"


def test_watch_service_routes_deleted_pdf_inside_root(tmp_path: Path) -> None:
    service = WatchService(root=tmp_path, logger=logging.getLogger("test.watch"))

    operation = service.handle_event(
        FileDeletedEvent(str(tmp_path / "Books" / "a.pdf"))
    )

    assert operation is not None
    assert operation.operation == "path_missing"
    assert operation.src_rel_path == "Books/a.pdf"


def test_watch_service_ignores_modified_pdf(tmp_path: Path) -> None:
    service = WatchService(root=tmp_path, logger=logging.getLogger("test.watch"))

    operation = service.handle_event(FileModifiedEvent(str(tmp_path / "Books" / "a.pdf")))

    assert operation is None


def test_watch_service_ignores_non_pdf_and_outside_root(tmp_path: Path) -> None:
    service = WatchService(root=tmp_path, logger=logging.getLogger("test.watch"))
    outside_root = tmp_path.parent / "outside.pdf"

    assert service.handle_event(FileCreatedEvent(str(tmp_path / "Books" / "a.txt"))) is None
    assert service.handle_event(FileCreatedEvent(str(outside_root))) is None


def test_watch_service_persists_discovered_document(make_pdf, pdf_root: Path, tmp_path: Path) -> None:
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
            assert session.query(DocumentPath).filter_by(rel_path="Books/watch.pdf").one().sha256 == document.sha256
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
            assert session.query(DocumentPath).filter_by(rel_path="Books/move.pdf").one_or_none() is None
            document_path = session.query(DocumentPath).filter_by(rel_path="Books/Moved/renamed.pdf").one()
            assert session.get(Document, document_path.sha256).file_name == "renamed.pdf"
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
            assert session.query(DocumentPath).filter_by(rel_path="Books/delete.pdf").one_or_none() is None
            assert session.query(Document).count() == 1
    finally:
        engine.dispose()
        service.close()
