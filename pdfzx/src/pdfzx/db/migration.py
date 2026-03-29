from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from pdfzx.db.models import Document
from pdfzx.db.models import DocumentPath
from pdfzx.db.models import DocumentTocEntry
from pdfzx.db.models import FileStat
from pdfzx.db.models import Job
from pdfzx.db.session import init_sqlite_db
from pdfzx.models import Registry
from pdfzx.storage import JsonStorage


def migrate_json_to_sqlite(
    *,
    source_json: Path,
    target_sqlite: Path,
    replace: bool = False,
) -> dict[str, object]:
    registry = JsonStorage(source_json).load()
    summary = import_registry_to_sqlite(
        registry=registry, target_sqlite=target_sqlite, replace=replace
    )
    summary["source_json"] = str(source_json.resolve())
    return summary


def import_registry_to_sqlite(
    *, registry: Registry, target_sqlite: Path, replace: bool = False
) -> dict[str, object]:

    if target_sqlite.exists():
        if not replace:
            msg = f"SQLite DB already exists: {target_sqlite}"
            raise FileExistsError(msg)
        target_sqlite.unlink()

    init_sqlite_db(target_sqlite)
    engine = create_engine(f"sqlite:///{target_sqlite.resolve()}", future=True)
    session_factory = sessionmaker(bind=engine, future=True)
    with session_factory() as session:
        _insert_jobs(session, registry.jobs)
        _insert_documents(session, registry.documents)
        _insert_file_stats(session, registry.file_stats)
        session.commit()
    engine.dispose()

    return {
        "target_sqlite": str(target_sqlite.resolve()),
        "documents": len(registry.documents),
        "paths": sum(len(document.paths) for document in registry.documents.values()),
        "toc_entries": sum(len(document.toc) for document in registry.documents.values()),
        "file_stats": len(registry.file_stats),
        "jobs": len(registry.jobs),
    }


def _insert_jobs(session: Session, jobs: list[object]) -> None:
    for job in jobs:
        session.add(
            Job(
                job_id=job.job_id,
                run_at=job.run_at,
                root_path=job.root_path,
                added=job.stats.added,
                updated=job.stats.updated,
                removed=job.stats.removed,
                duplicates=job.stats.duplicates,
                skipped=job.stats.skipped,
            )
        )


def _insert_documents(session: Session, documents: dict[str, object]) -> None:
    for document in documents.values():
        session.add(
            Document(
                sha256=document.sha256,
                md5=document.md5,
                file_name=document.file_name,
                normalised_name=document.normalised_name,
                metadata_title=document.metadata.title,
                metadata_author=document.metadata.author,
                metadata_creator=document.metadata.creator,
                metadata_created=document.metadata.created,
                metadata_modified=document.metadata.modified,
                metadata_extra_json=document.metadata.extra,
                languages_json=document.languages,
                is_digital=document.is_digital,
                toc_valid=document.toc_valid,
                toc_invalid_reason=document.toc_invalid_reason,
                extraction_status=(
                    document.extraction_status.value if document.extraction_status else None
                ),
                force_extracted=document.force_extracted,
                first_seen_job=document.first_seen_job,
                last_seen_job=document.last_seen_job,
            )
        )
        for rel_path in document.paths:
            session.add(DocumentPath(sha256=document.sha256, rel_path=rel_path))
        for position, toc_entry in enumerate(document.toc):
            session.add(
                DocumentTocEntry(
                    sha256=document.sha256,
                    level=toc_entry.level,
                    title=toc_entry.title,
                    page=toc_entry.page,
                    position=position,
                )
            )


def _insert_file_stats(session: Session, file_stats: dict[str, object]) -> None:
    for record in file_stats.values():
        session.add(
            FileStat(
                rel_path=record.rel_path,
                sha256=record.sha256,
                size_bytes=record.size_bytes,
                mtime=record.mtime,
                last_scanned_job=record.last_scanned_job,
            )
        )
