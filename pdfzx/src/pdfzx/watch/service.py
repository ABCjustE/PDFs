"""Logging-first watcher service for normalized PDF filesystem events."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from watchdog.events import FileSystemEvent
from watchdog.events import FileSystemMovedEvent

from pdfzx.config import ScanConfig
from pdfzx.db.repositories import DocumentPathRepository
from pdfzx.db.repositories import DocumentRepository
from pdfzx.db.session import create_sqlite_engine
from pdfzx.db.session import init_sqlite_db
from pdfzx.inventory import process_pdf
from pdfzx.watch.events import CanonicalWatchOperation
from pdfzx.watch.events import RawWatchEvent


class WatchService:
    """Normalize raw watchdog events and log canonical routing decisions."""

    def __init__(
        self,
        *,
        root: Path,
        config: ScanConfig | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._root = root.resolve()
        self._config = config
        self._logger = logger or logging.getLogger(__name__)
        self._engine: Engine | None = None
        if config is not None:
            init_sqlite_db(config.sqlite3_db_path)
            self._engine = create_sqlite_engine(config.sqlite3_db_path)

    @property
    def root(self) -> Path:
        """Return the watched root path."""
        return self._root

    def handle_event(self, event: FileSystemEvent) -> CanonicalWatchOperation | None:
        """Normalize one watchdog event and log the chosen canonical operation."""
        raw_event = self.normalize_event(event)
        if raw_event is None:
            return None
        self.log_raw_event(raw_event)
        operation = self.route_raw_event(raw_event)
        if operation is None:
            return None
        self.apply_operation(operation)
        return operation

    def normalize_event(self, event: FileSystemEvent) -> RawWatchEvent | None:
        """Convert one watchdog event into a normalized raw watch event."""
        if event.is_directory:
            return None
        src_rel_path = self._to_rel_path(event.src_path)
        dest_rel_path = self._to_rel_path(
            event.dest_path if isinstance(event, FileSystemMovedEvent) else None
        )
        if src_rel_path is None and dest_rel_path is None:
            return None
        return RawWatchEvent(
            event_class=type(event).__name__,
            event_type=event.event_type,
            src_rel_path=src_rel_path,
            dest_rel_path=dest_rel_path,
            is_synthetic=getattr(event, "is_synthetic", False),
        )

    def choose_operation(
        self, raw_event: RawWatchEvent
    ) -> CanonicalWatchOperation | None:
        """Choose one canonical project operation from a normalized raw event."""
        if raw_event.event_class == "FileMovedEvent":
            if raw_event.src_rel_path is not None and raw_event.dest_rel_path is not None:
                return CanonicalWatchOperation(
                    operation="path_moved",
                    src_rel_path=raw_event.src_rel_path,
                    dest_rel_path=raw_event.dest_rel_path,
                    reason="trusted move event within watched root",
                )
            if raw_event.src_rel_path is not None:
                return CanonicalWatchOperation(
                    operation="path_missing",
                    src_rel_path=raw_event.src_rel_path,
                    dest_rel_path=None,
                    reason="move event leaving watched root",
                )
            if raw_event.dest_rel_path is not None:
                return CanonicalWatchOperation(
                    operation="path_discovered",
                    src_rel_path=None,
                    dest_rel_path=raw_event.dest_rel_path,
                    reason="move event entering watched root",
                )
        if raw_event.event_class == "FileDeletedEvent":
            return CanonicalWatchOperation(
                operation="path_missing",
                src_rel_path=raw_event.src_rel_path,
                dest_rel_path=None,
                reason="delete event under watched root",
            )
        if raw_event.event_class == "FileCreatedEvent":
            return CanonicalWatchOperation(
                operation="path_discovered",
                src_rel_path=raw_event.src_rel_path,
                dest_rel_path=None,
                reason="create event under watched root",
            )
        return None

    def log_raw_event(self, raw_event: RawWatchEvent) -> None:
        """Log one normalized raw watcher event."""
        self._logger.debug(
            "watch.raw",
            extra={
                "event": raw_event.event_class,
                "etype": raw_event.event_type,
                "src": raw_event.src_rel_path,
                "dst": raw_event.dest_rel_path,
                "synthetic": raw_event.is_synthetic,
            },
        )

    def log_route(self, operation: CanonicalWatchOperation) -> None:
        """Log one canonical routed watcher operation."""
        self._logger.info(
            "watch.route",
            extra={
                "op": operation.operation,
                "src": operation.src_rel_path,
                "dst": operation.dest_rel_path,
                "why": operation.reason,
            },
        )

    def route_raw_event(self, raw_event: RawWatchEvent) -> CanonicalWatchOperation | None:
        """Choose and log one canonical operation from a normalized raw event."""
        operation = self.choose_operation(raw_event)
        if operation is None:
            return None
        self.log_route(operation)
        return operation

    def apply_operation(self, operation: CanonicalWatchOperation) -> None:
        """Apply one routed watcher operation to SQLite state when configured."""
        if self._config is None or self._engine is None:
            return
        if operation.operation == "path_discovered":
            rel_path = operation.src_rel_path or operation.dest_rel_path
            if rel_path is None:
                return
            self._handle_path_discovered(rel_path=rel_path)
            return
        if operation.operation == "path_moved":
            if operation.src_rel_path is None or operation.dest_rel_path is None:
                return
            self._handle_path_moved(
                old_rel_path=operation.src_rel_path,
                new_rel_path=operation.dest_rel_path,
            )
            return
        if operation.operation == "path_missing" and operation.src_rel_path is not None:
            self._handle_path_missing(rel_path=operation.src_rel_path)

    def close(self) -> None:
        """Dispose the cached SQLite engine."""
        if self._engine is not None:
            self._engine.dispose()

    def _handle_path_discovered(self, *, rel_path: str) -> None:
        assert self._config is not None
        assert self._engine is not None
        record = process_pdf(self._root / rel_path, self._root, self._config)
        with Session(self._engine) as session:
            documents = DocumentRepository(session)
            paths = DocumentPathRepository(session)
            if documents.get_by_sha256(sha256=record.sha256) is None:
                documents.create_from_record(record=record)
                self._logger.info(
                    "watch.db",
                    extra={"op": "document_created", "sha256": record.sha256, "path": rel_path},
                )
            paths.upsert(sha256=record.sha256, rel_path=rel_path)
            session.commit()

    def _handle_path_moved(self, *, old_rel_path: str, new_rel_path: str) -> None:
        assert self._config is not None
        assert self._engine is not None
        with Session(self._engine) as session:
            paths = DocumentPathRepository(session)
            sha256 = paths.move(old_rel_path=old_rel_path, new_rel_path=new_rel_path)
            if sha256 is None:
                session.rollback()
                self._handle_path_discovered(rel_path=new_rel_path)
                return
            session.commit()
            self._logger.info(
                "watch.db",
                extra={
                    "op": "path_moved",
                    "sha256": sha256,
                    "src": old_rel_path,
                    "dst": new_rel_path,
                },
            )

    def _handle_path_missing(self, *, rel_path: str) -> None:
        assert self._config is not None
        assert self._engine is not None
        with Session(self._engine) as session:
            deleted = DocumentPathRepository(session).delete_by_rel_path(rel_path=rel_path)
            if deleted is None:
                session.rollback()
                return
            session.commit()
            self._logger.info(
                "watch.db",
                extra={
                    "op": "path_deleted",
                    "sha256": deleted.sha256,
                    "path": rel_path,
                    "remaining_paths": deleted.remaining_paths,
                },
            )

    def _to_rel_path(self, raw_path: str | bytes | None) -> str | None:
        if raw_path is None:
            return None
        candidate = Path(os.fsdecode(raw_path)).resolve(strict=False)
        try:
            rel_path = candidate.relative_to(self._root)
        except ValueError:
            return None
        return rel_path.as_posix() if rel_path.suffix.lower() == ".pdf" else None
