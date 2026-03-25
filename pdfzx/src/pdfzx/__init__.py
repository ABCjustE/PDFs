"""pdfzx public API — inventory job orchestration and JSON logging setup."""

from __future__ import annotations

import logging
import logging.config
from collections.abc import Callable
from pathlib import Path

from pdfzx.config import ScanConfig
from pdfzx.inventory import process_pdf
from pdfzx.models import DocumentRecord
from pdfzx.models import JobRecord
from pdfzx.normalizer import normalize
from pdfzx.registry import run as registry_run
from pdfzx.storage import JsonStorage

__all__ = ["InventoryJob", "configure_logging"]


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger to emit structured JSON lines.

    Args:
        level: Root log level string, e.g. ``"DEBUG"``, ``"INFO"``.
    """
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": "logging.Formatter",
                    "fmt": (
                        '{"time":"%(asctime)s","level":"%(levelname)s",'
                        '"logger":"%(name)s","msg":"%(message)s"}'
                    ),
                    "datefmt": "%Y-%m-%dT%H:%M:%S",
                }
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {"level": level, "handlers": ["stdout"]},
        }
    )


def _process_one(path: Path, root: Path, config: ScanConfig) -> DocumentRecord | None:
    """Process one PDF, returning ``None`` when the file should be skipped."""
    logger = logging.getLogger(__name__)

    try:
        record = process_pdf(path, root, config)
    except Exception:
        logger.exception("skipping file due to error", extra={"path": str(path)})
        return None

    record.normalised_name = normalize(record.metadata.title or record.file_name)
    return record


class InventoryJob:
    """Resolve selected targets and run the Phase 1 inventory pipeline."""
    def __init__(self, root: Path, config: ScanConfig) -> None:
        self.root = root.resolve()
        self.config = config
        self._storage = JsonStorage(config.db_path)
        self._logger = logging.getLogger(__name__)

    def resolve(self, targets: list[Path]) -> list[Path]:
        """Expand directory targets into a deduplicated, sorted PDF file list."""
        resolved_targets: set[Path] = set()

        for target in targets:
            candidate = target.resolve(strict=False)
            try:
                relative = candidate.relative_to(self.root)
                within_root = self.root / relative
            except ValueError as exc:
                msg = f"Path escapes configured root: {candidate}"
                raise ValueError(msg) from exc

            if not within_root.exists():
                if within_root.suffix.lower() == ".pdf":
                    resolved_targets.add(within_root)
                continue

            if within_root.is_dir():
                resolved_targets.update(
                    path.resolve() for path in within_root.rglob("*.pdf") if path.is_file()
                )
                continue

            if within_root.is_file() and within_root.suffix.lower() == ".pdf":
                resolved_targets.add(within_root.resolve())

        return sorted(resolved_targets)

    def run(
        self,
        targets: list[Path],
        on_progress: Callable[[Path], None] | None = None,
    ) -> JobRecord:
        """Resolve selected targets, process PDFs, then merge them into the registry."""
        pdf_paths = self.resolve(targets)
        self._logger.info("scan started", extra={"root": str(self.root), "count": len(pdf_paths)})

        records: list[DocumentRecord] = []
        successful_paths: list[Path] = []

        for path in pdf_paths:
            record = _process_one(path, self.root, self.config)
            if record is not None:
                records.append(record)
                successful_paths.append(path)
            if on_progress is not None:
                on_progress(path)

        job = registry_run(self._storage, records, successful_paths, self.root)
        self._logger.info("scan complete", extra={"job_id": job.job_id, "stats": job.stats.model_dump()})
        return job
