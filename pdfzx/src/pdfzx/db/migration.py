from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from pdfzx.db.models import Document
from pdfzx.db.models import DocumentPath
from pdfzx.db.models import DocumentTocEntry
from pdfzx.db.models import FileStat
from pdfzx.db.models import Job
from pdfzx.db.models import LlmDocumentSuggestion
from pdfzx.db.models import LlmTaxonomySuggestion
from pdfzx.db.models import LlmTocReviewSuggestion
from pdfzx.db.models import Prompt
from pdfzx.db.session import init_sqlite_db
from pdfzx.models import Registry


def migrate_json_to_sqlite(
    *, source_json: Path, target_sqlite: Path, replace: bool = False
) -> dict[str, object]:
    """Import a legacy JSON registry file into a SQLite database."""
    registry = Registry.model_validate_json(source_json.read_text(encoding="utf-8"))
    summary = import_registry_to_sqlite(
        registry=registry, target_sqlite=target_sqlite, replace=replace
    )
    summary["source_json"] = str(source_json.resolve())
    return summary


def import_registry_to_sqlite(
    *, registry: Registry, target_sqlite: Path, replace: bool = False
) -> dict[str, object]:
    """Rewrite a SQLite database from the canonical in-memory registry."""
    phase2_state = _capture_phase2_state(target_sqlite)
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
        _restore_phase2_state(
            session,
            phase2_state=phase2_state,
            known_sha256=set(registry.documents),
        )
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


def _capture_phase2_state(target_sqlite: Path) -> dict[str, list[dict[str, Any]]]:
    """Snapshot prompt-backed workflow rows before a replace-style rewrite."""
    if not target_sqlite.exists():
        return {"prompts": [], "document": [], "taxonomy": [], "toc_review": []}

    engine = create_engine(f"sqlite:///{target_sqlite.resolve()}", future=True)
    session_factory = sessionmaker(bind=engine, future=True)
    try:
        with session_factory() as session:
            return {
                "prompts": [_prompt_payload(row) for row in session.query(Prompt).all()],
                "document": [
                    _document_suggestion_payload(row)
                    for row in session.query(LlmDocumentSuggestion).all()
                ],
                "taxonomy": [
                    _taxonomy_suggestion_payload(row)
                    for row in session.query(LlmTaxonomySuggestion).all()
                ],
                "toc_review": [
                    _toc_review_suggestion_payload(row)
                    for row in session.query(LlmTocReviewSuggestion).all()
                ],
            }
    finally:
        engine.dispose()


def _restore_phase2_state(
    session: Session,
    *,
    phase2_state: dict[str, list[dict[str, Any]]],
    known_sha256: set[str],
) -> None:
    """Restore prompt-backed workflow rows after a replace-style rewrite."""
    for payload in phase2_state["prompts"]:
        session.add(Prompt(**payload))

    for payload in phase2_state["document"]:
        if payload["sha256"] in known_sha256:
            session.add(LlmDocumentSuggestion(**payload))
    for payload in phase2_state["taxonomy"]:
        if payload["sha256"] in known_sha256:
            session.add(LlmTaxonomySuggestion(**payload))
    for payload in phase2_state["toc_review"]:
        if payload["sha256"] in known_sha256:
            session.add(LlmTocReviewSuggestion(**payload))


def _prompt_payload(row: Prompt) -> dict[str, Any]:
    return {
        "id": row.id,
        "workflow_name": row.workflow_name,
        "prompt_text": row.prompt_text,
        "model_provider": row.model_provider,
        "model": row.model,
        "prompt_version": row.prompt_version,
        "active": row.active,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _document_suggestion_payload(row: LlmDocumentSuggestion) -> dict[str, Any]:
    return {
        "id": row.id,
        "sha256": row.sha256,
        "prompt_id": row.prompt_id,
        "suggested_file_name": row.suggested_file_name,
        "suggested_author": row.suggested_author,
        "suggested_publisher": row.suggested_publisher,
        "suggested_edition": row.suggested_edition,
        "suggested_labels_json": row.suggested_labels_json,
        "reasoning_summary": row.reasoning_summary,
        "status": row.status,
        "applied": row.applied,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _taxonomy_suggestion_payload(row: LlmTaxonomySuggestion) -> dict[str, Any]:
    return {
        "id": row.id,
        "sha256": row.sha256,
        "prompt_id": row.prompt_id,
        "suggested_taxonomy_path": row.suggested_taxonomy_path,
        "suggested_document_type": row.suggested_document_type,
        "suggested_new_subcategory": row.suggested_new_subcategory,
        "confidence": row.confidence,
        "reasoning_summary": row.reasoning_summary,
        "status": row.status,
        "applied": row.applied,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _toc_review_suggestion_payload(row: LlmTocReviewSuggestion) -> dict[str, Any]:
    return {
        "id": row.id,
        "sha256": row.sha256,
        "prompt_id": row.prompt_id,
        "toc_is_valid": row.toc_is_valid,
        "toc_matches_document": row.toc_matches_document,
        "toc_invalid_reason": row.toc_invalid_reason,
        "preface_page": row.preface_page,
        "preface_label": row.preface_label,
        "confidence": row.confidence,
        "reasoning_summary": row.reasoning_summary,
        "status": row.status,
        "applied": row.applied,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
