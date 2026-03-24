"""Registry diff/merge — scan results → updated Registry + JobRecord."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC
from datetime import datetime
from pathlib import Path

from pdfzx.models import DocumentRecord
from pdfzx.models import FileStatRecord
from pdfzx.models import JobRecord
from pdfzx.models import JobStats
from pdfzx.models import Registry
from pdfzx.storage import Storage

logger = logging.getLogger(__name__)


def _job_id() -> str:
    return uuid.uuid4().hex


def _mtime(path: Path) -> float:
    return path.stat().st_mtime


def _size(path: Path) -> int:
    return path.stat().st_size


def merge(
    registry: Registry, records: list[DocumentRecord], paths: list[Path], root: Path, job_id: str
) -> tuple[Registry, JobRecord]:
    """Merge freshly scanned DocumentRecords into the existing Registry.

    Diff logic:
    - new sha256                  → add DocumentRecord, add FileStatRecord
    - known sha256, new path      → append path, count as duplicate
    - known sha256, mtime changed → update FileStatRecord, count as updated
    - known sha256, same mtime    → skip (count as skipped)
    - path in db but not in scan  → mark via last_seen_job (count as removed)

    Args:
        registry: The loaded Registry to merge into (mutated in place).
        records: DocumentRecords produced by inventory.process_pdf.
        paths: Absolute paths corresponding to each record (same order).
        root: Scan root for computing relative paths.
        job_id: Identifier for this scan run.

    Returns:
        Tuple of (updated Registry, JobRecord).
    """
    stats = JobStats()
    resolved_root = root.resolve()

    # index current file_stats by rel_path for O(1) lookup
    seen_rel_paths: set[str] = set()

    for record, path in zip(records, paths, strict=True):
        rel = str(path.resolve().relative_to(resolved_root))
        seen_rel_paths.add(rel)

        existing_doc = registry.documents.get(record.sha256)
        existing_stat = registry.file_stats.get(rel)

        current_mtime = _mtime(path)
        current_size = _size(path)

        if existing_doc is None:
            # content-change: old document loses this path
            if existing_stat and existing_stat.sha256 != record.sha256:
                old_doc = registry.documents.get(existing_stat.sha256)
                if old_doc and rel in old_doc.paths:
                    old_doc.paths.remove(rel)
                    logger.info(
                        "path moved",
                        extra={"old": existing_stat.sha256, "new": record.sha256, "path": rel},
                    )
            # brand-new document
            record.first_seen_job = job_id
            record.last_seen_job = job_id
            registry.documents[record.sha256] = record
            registry.file_stats[rel] = FileStatRecord(
                rel_path=rel,
                sha256=record.sha256,
                size_bytes=current_size,
                mtime=current_mtime,
                last_scanned_job=job_id,
            )
            stats.added += 1
            logger.info("added", extra={"sha256": record.sha256, "path": rel})
        else:
            # known document — check for new path (duplicate)
            if rel not in existing_doc.paths:
                existing_doc.paths.append(rel)
                stats.duplicates += 1
                logger.info("duplicate", extra={"sha256": record.sha256, "path": rel})

            existing_doc.last_seen_job = job_id

            if existing_stat is None or existing_stat.mtime != current_mtime:
                # file changed on disk (or stat record missing)
                registry.file_stats[rel] = FileStatRecord(
                    rel_path=rel,
                    sha256=record.sha256,
                    size_bytes=current_size,
                    mtime=current_mtime,
                    last_scanned_job=job_id,
                )
                stats.updated += 1
                logger.info("updated", extra={"sha256": record.sha256, "path": rel})
            else:
                registry.file_stats[rel].last_scanned_job = job_id
                stats.skipped += 1

    # flag removed paths (in db but not in this scan) — count per document, not per path
    removed_hashes: set[str] = set()
    for rel, stat in registry.file_stats.items():
        if rel not in seen_rel_paths and stat.sha256 not in removed_hashes:
            removed_hashes.add(stat.sha256)
            stats.removed += 1
            logger.info("removed", extra={"sha256": stat.sha256, "path": rel})

    job = JobRecord(
        job_id=job_id, run_at=datetime.now(tz=UTC), root_path=str(resolved_root), stats=stats
    )
    registry.jobs.append(job)
    return registry, job


def run(
    storage: Storage, records: list[DocumentRecord], paths: list[Path], root: Path
) -> JobRecord:
    """Load, merge, and persist the registry; return the JobRecord.

    Args:
        storage: Storage implementation to load/save the Registry.
        records: Fresh DocumentRecords from inventory.
        paths: Corresponding absolute paths (same order as records).
        root: Scan root path.

    Returns:
        The JobRecord created for this run.
    """
    job_id = _job_id()
    registry = storage.load()
    registry, job = merge(registry, records, paths, root, job_id)
    storage.save(registry)
    logger.info("registry run complete", extra={"job_id": job_id, "stats": job.stats.model_dump()})
    return job
