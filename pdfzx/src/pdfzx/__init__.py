"""pdfzx public API — run_inventory() entrypoint and JSON logging setup."""

from __future__ import annotations

import logging
import logging.config

from pdfzx.config import ScanConfig
from pdfzx.inventory import process_pdf
from pdfzx.models import JobRecord
from pdfzx.normalizer import normalize
from pdfzx.registry import run as registry_run
from pdfzx.storage import JsonStorage

__all__ = ["configure_logging", "run_inventory"]


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


def run_inventory(config: ScanConfig) -> JobRecord:
    """Scan config.root_path, extract PDF metadata, and persist to db.json.

    Orchestrates: discover PDFs → process each → normalize names → registry merge.

    Args:
        config: Validated scan configuration.

    Returns:
        JobRecord summarising this scan run.
    """
    logger = logging.getLogger(__name__)
    root = config.root_path

    pdf_paths = sorted(root.rglob("*.pdf"))
    logger.info("scan started", extra={"root": str(root), "count": len(pdf_paths)})

    records, paths = [], []
    for path in pdf_paths:
        try:
            record = process_pdf(path, root, config)
            record.normalised_name = normalize(record.metadata.title or record.file_name)
            records.append(record)
            paths.append(path)
        except Exception:
            logger.exception("skipping file due to error", extra={"path": str(path)})

    job = registry_run(JsonStorage(config.db_path), records, paths, root)
    logger.info("scan complete", extra={"job_id": job.job_id, "stats": job.stats.model_dump()})
    return job
