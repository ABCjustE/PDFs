"""Logging-first watcher service for normalized PDF filesystem events."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from watchdog.events import FileSystemEvent
from watchdog.events import FileSystemMovedEvent

from pdfzx.watch.events import CanonicalWatchOperation
from pdfzx.watch.events import RawWatchEvent


class WatchService:
    """Normalize raw watchdog events and log canonical routing decisions."""

    def __init__(self, *, root: Path, logger: logging.Logger | None = None) -> None:
        self._root = root.resolve()
        self._logger = logger or logging.getLogger(__name__)

    @property
    def root(self) -> Path:
        """Return the watched root path."""
        return self._root

    def handle_event(self, event: FileSystemEvent) -> CanonicalWatchOperation | None:
        """Normalize one watchdog event and log the chosen canonical operation."""
        raw_event = self.normalize_event(event)
        if raw_event is None:
            return None
        self._logger.info(
            "watch.raw",
            extra={
                "event": raw_event.event_class,
                "etype": raw_event.event_type,
                "src": raw_event.src_rel_path,
                "dst": raw_event.dest_rel_path,
                "synthetic": raw_event.is_synthetic,
            },
        )
        operation = self.choose_operation(raw_event)
        if operation is None:
            return None
        self._logger.info(
            "watch.route",
            extra={
                "op": operation.operation,
                "src": operation.src_rel_path,
                "dst": operation.dest_rel_path,
                "why": operation.reason,
            },
        )
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

    def choose_operation(  # noqa: PLR0911
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
        if raw_event.event_class in {"FileModifiedEvent", "FileClosedEvent"}:
            return CanonicalWatchOperation(
                operation="path_reconcile",
                src_rel_path=raw_event.src_rel_path,
                dest_rel_path=None,
                reason="ambiguous activity requires reconciliation",
            )
        return None

    def _to_rel_path(self, raw_path: str | bytes | None) -> str | None:
        if raw_path is None:
            return None
        candidate = Path(os.fsdecode(raw_path)).resolve(strict=False)
        try:
            rel_path = candidate.relative_to(self._root)
        except ValueError:
            return None
        return rel_path.as_posix() if rel_path.suffix.lower() == ".pdf" else None
