"""pdfzx public API — inventory job orchestration and JSON logging setup."""

from __future__ import annotations

import json
import logging
import logging.config
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import as_completed
from pathlib import Path

import pymupdf

from pdfzx.config import ScanConfig
from pdfzx.inventory import process_pdf
from pdfzx.models import DocumentRecord
from pdfzx.models import JobRecord
from pdfzx.normalizer import normalize
from pdfzx.registry import run as registry_run
from pdfzx.storage import JsonStorage

__all__ = ["InventoryJob", "configure_logging"]

# Fields always present on LogRecord — excluded from the "extra" passthrough.
_STDLIB_FIELDS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
}


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record, including all ``extra`` fields."""

    def format(self, record: logging.LogRecord) -> str:
        record.asctime = self.formatTime(record, self.datefmt)
        base = {
            "time": record.asctime,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in _STDLIB_FIELDS}
        return json.dumps({**base, **extras})


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger to emit structured JSON lines including all extra fields.

    Also redirects MuPDF's internal message() output into the ``pymupdf``
    stdlib logger, silencing the raw ``MuPDF error: ...`` stdout noise.
    File-level context is added separately in ``inventory.py`` via the
    ``JM_mupdf_warnings_store`` drain.

    Args:
        level: Root log level string, e.g. ``"DEBUG"``, ``"INFO"``.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    # Route all MuPDF message() calls (errors + warnings) through stdlib logging.
    # This silences the raw "MuPDF error: ..." / "MuPDF warning: ..." stdout prints.
    # The pymupdf logger is intentionally left at WARNING so noise is filtered.
    pymupdf.set_messages(  # type: ignore[no-untyped-call]
        pylogging=True, pylogging_name="pymupdf", pylogging_level=logging.WARNING
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

    def __init__(self, root: Path, config: ScanConfig, log_level: str = "INFO") -> None:
        self.root = root.resolve()
        self.config = config
        self._log_level = log_level
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
        workers: int = 1,
    ) -> JobRecord:
        """Resolve selected targets, process PDFs, then merge them into the registry.

        Args:
            targets: Files or directories to scan.
            on_progress: Optional callback invoked with each path after processing.
            workers: Number of parallel worker processes for extraction (default 1 = serial).
                     Merge is always serial — workers never touch db.json.
        """
        pdf_paths = self.resolve(targets)
        self._logger.info(
            "scan started",
            extra={"root": str(self.root), "count": len(pdf_paths), "workers": workers},
        )

        records: list[DocumentRecord] = []
        successful_paths: list[Path] = []

        if workers > 1:
            with ProcessPoolExecutor(
                max_workers=workers, initializer=configure_logging, initargs=(self._log_level,)
            ) as pool:
                future_to_path = {
                    pool.submit(_process_one, p, self.root, self.config): p for p in pdf_paths
                }
                for future in as_completed(future_to_path):
                    path = future_to_path[future]
                    record = future.result()
                    if record is not None:
                        records.append(record)
                        successful_paths.append(path)
                    if on_progress is not None:
                        on_progress(path)
        else:
            for path in pdf_paths:
                record = _process_one(path, self.root, self.config)
                if record is not None:
                    records.append(record)
                    successful_paths.append(path)
                if on_progress is not None:
                    on_progress(path)

        job = registry_run(self._storage, records, successful_paths, self.root)
        self._logger.info(
            "scan complete", extra={"job_id": job.job_id, "stats": job.stats.model_dump()}
        )
        return job
