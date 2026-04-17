"""Foreground watchdog runner for PDF path events."""

from __future__ import annotations

import logging
import time

from watchdog.events import FileSystemEvent
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from pdfzx import configure_logging
from pdfzx.config import ScanConfig
from pdfzx.watch.service import WatchService

logger = logging.getLogger(__name__)


class _WatchHandler(FileSystemEventHandler):
    """Forward raw watchdog file events into the watch service."""

    def __init__(self, *, service: WatchService) -> None:
        self._service = service

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Forward one watchdog event."""
        self._service.handle_event(event)


def run_watch_process(*, config: ScanConfig, log_level: str) -> int:
    """Start a watchdog observer and log PDF file events until interrupted."""
    configure_logging(log_level)
    service = WatchService(root=config.root_path, logger=logging.getLogger("pdfzx.watch"))
    observer = Observer()
    observer.schedule(_WatchHandler(service=service), str(config.root_path), recursive=True)
    observer.start()
    logger.info("watchdog started", extra={"root": str(config.root_path)})
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("watchdog stopping", extra={"root": str(config.root_path)})
        observer.stop()
    finally:
        observer.join()
    return 0
