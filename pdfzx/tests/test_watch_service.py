from __future__ import annotations

import logging
from pathlib import Path

from watchdog.events import FileCreatedEvent
from watchdog.events import FileDeletedEvent
from watchdog.events import FileModifiedEvent
from watchdog.events import FileMovedEvent

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
