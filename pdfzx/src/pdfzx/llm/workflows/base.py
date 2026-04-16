from __future__ import annotations

import json
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Generic
from typing import Protocol
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from pdfzx.db.models import Document
from pdfzx.db.models import DocumentTocEntry
from pdfzx.db.session import create_sqlite_engine
from pdfzx.models import DocumentRecord
from pdfzx.models import PdfMetadata
from pdfzx.models import TocEntry

PromptInputT = TypeVar("PromptInputT", bound=BaseModel)
ResponseT = TypeVar("ResponseT", bound=BaseModel)
_BATCH_MAX_RETRIES = 2
_BATCH_RETRY_DELAY_SECONDS = 2.0


class PromptWorkflowService(Protocol):
    """Prompt-backed service contract used by the generic LLM runner."""

    def should_request_for_document(self, *, sha256: str) -> Any:
        """Return the idempotency decision for the given document."""

    def store_response(self, *, sha256: str, response: object) -> object:
        """Persist a validated response for the given document."""


class PromptWorkflowDefinition(Protocol, Generic[PromptInputT, ResponseT]):
    """Workflow contract for one prompt-driven document task."""

    system_prompt: str
    response_model: type[ResponseT]

    def build_prompt_input(self, record: DocumentRecord) -> PromptInputT:
        """Build the structured prompt input from a document record."""

    def build_user_prompt(self, prompt_input: PromptInputT) -> str:
        """Serialize the user prompt payload."""

    def create_service(
        self, session: Session, *, model_provider: str, model: str
    ) -> PromptWorkflowService:
        """Create the prompt-backed persistence/idempotency service."""


@dataclass(slots=True)
class ProbeSuggestionResult:
    """Result payload for a one-document prompt probe."""

    should_request: bool
    reason: str
    prompt_id: int | None
    prompt_input: dict[str, object] | None
    parsed_response: dict[str, object] | None
    persisted: bool


@dataclass(slots=True)
class BatchSuggestionResult:
    """Result payload for a batch prompt workflow run."""

    workflow_name: str
    total_candidates: int
    requested: int
    persisted: int
    skipped_existing: int
    skipped_ineligible: int
    failed: int
    failures: list[dict[str, str]]


@dataclass(slots=True)
class _PendingBatchRequest(Generic[PromptInputT]):
    """Prepared batch request ready for concurrent API execution."""

    sha256: str
    prompt_input_model: PromptInputT


def probe_prompt_workflow(  # noqa: PLR0913
    *,
    workflow: PromptWorkflowDefinition[PromptInputT, ResponseT],
    sqlite_db_path: Path,
    sha256: str,
    online_features: bool,
    openai_api_key: str | None,
    openai_model: str,
    persist: bool = False,
    force: bool = False,
    client: OpenAI | None = None,
) -> ProbeSuggestionResult:
    """Probe a prompt workflow against one stored document."""
    if not online_features:
        msg = "PDFZX_ONLINE_FEATURES is disabled"
        raise ValueError(msg)
    if not openai_api_key:
        msg = "PDFZX_OPENAI_API_KEY is required for LLM probe"
        raise ValueError(msg)

    engine = create_sqlite_engine(sqlite_db_path)
    try:
        with Session(engine) as session:
            service = workflow.create_service(session, model_provider="openai", model=openai_model)
            decision = service.should_request_for_document(sha256=sha256)
            document = session.get(Document, sha256)
            if document is None:
                msg = f"Document not found: {sha256}"
                raise ValueError(msg)

            prompt_input_model = workflow.build_prompt_input(_document_record_from_orm(document))
            if not force and not decision.should_request:
                return ProbeSuggestionResult(
                    should_request=False,
                    reason=decision.reason,
                    prompt_id=decision.prompt_id,
                    prompt_input=prompt_input_model.model_dump(mode="json"),
                    parsed_response=None,
                    persisted=False,
                )

            response = (client or OpenAI(api_key=openai_api_key, max_retries=0)).responses.parse(
                model=openai_model,
                instructions=workflow.system_prompt,
                input=workflow.build_user_prompt(prompt_input_model),
                text_format=workflow.response_model,
            )
            parsed = response.output_parsed
            if parsed is None:
                msg = "LLM response did not contain a parsed structured payload"
                raise ValueError(msg)

            persisted = False
            if persist:
                service.store_response(sha256=sha256, response=parsed)
                session.commit()
                persisted = True

            return ProbeSuggestionResult(
                should_request=True,
                reason="probe request completed",
                prompt_id=decision.prompt_id,
                prompt_input=prompt_input_model.model_dump(mode="json"),
                parsed_response=parsed.model_dump(mode="json"),
                persisted=persisted,
            )
    finally:
        engine.dispose()


def batch_prompt_workflow(  # noqa: C901,PLR0913,PLR0915
    *,
    workflow: PromptWorkflowDefinition[PromptInputT, ResponseT],
    workflow_name: str,
    sqlite_db_path: Path,
    online_features: bool,
    openai_api_key: str | None,
    openai_model: str,
    require_digital: bool = False,
    require_toc: bool = False,
    limit: int | None = None,
    force: bool = False,
    max_concurrency: int = 1,
    output_ndjson: Path | None = None,
    client: OpenAI | None = None,
) -> BatchSuggestionResult:
    """Run one prompt workflow over a filtered batch of stored documents."""
    if not online_features:
        msg = "PDFZX_ONLINE_FEATURES is disabled"
        raise ValueError(msg)
    if not openai_api_key:
        msg = "PDFZX_OPENAI_API_KEY is required for LLM batch"
        raise ValueError(msg)

    engine = create_sqlite_engine(sqlite_db_path)
    try:
        with Session(engine) as session:
            service = workflow.create_service(session, model_provider="openai", model=openai_model)
            query = (
                select(Document)
                .options(selectinload(Document.paths), selectinload(Document.toc_entries))
                .order_by(Document.sha256)
            )
            if require_digital:
                query = query.where(Document.is_digital.is_(True))
            if require_toc:
                query = query.join(DocumentTocEntry).distinct()
            if limit is not None:
                query = query.limit(limit)

            documents = list(session.scalars(query))
            result = BatchSuggestionResult(
                workflow_name=workflow_name,
                total_candidates=len(documents),
                requested=0,
                persisted=0,
                skipped_existing=0,
                skipped_ineligible=0,
                failed=0,
                failures=[],
            )

            openai_client = client or OpenAI(api_key=openai_api_key, max_retries=0)
            pending_requests: list[_PendingBatchRequest[PromptInputT]] = []
            for document in documents:
                record = _document_record_from_orm(document)
                try:
                    prompt_input_model = workflow.build_prompt_input(record)
                except ValueError as exc:
                    result.skipped_ineligible += 1
                    result.failures.append({"sha256": record.sha256, "error": str(exc)})
                    _append_ndjson(
                        output_ndjson,
                        {
                            "workflow": workflow_name,
                            "sha256": record.sha256,
                            "status": "skipped_ineligible",
                            "reason": str(exc),
                            "prompt_input": None,
                            "parsed_response": None,
                            "persisted": False,
                        },
                    )
                    continue

                decision = service.should_request_for_document(sha256=record.sha256)
                if not force and not decision.should_request:
                    result.skipped_existing += 1
                    _append_ndjson(
                        output_ndjson,
                        {
                            "workflow": workflow_name,
                            "sha256": record.sha256,
                            "status": "skipped_existing",
                            "reason": decision.reason,
                            "prompt_input": prompt_input_model.model_dump(mode="json"),
                            "parsed_response": None,
                            "persisted": False,
                        },
                    )
                    continue

                pending_requests.append(
                    _PendingBatchRequest(
                        sha256=record.sha256, prompt_input_model=prompt_input_model
                    )
                )

            for sha256, prompt_input_model, parsed, error in _execute_batch_requests(
                pending_requests=pending_requests,
                workflow=workflow,
                openai_client=openai_client,
                openai_model=openai_model,
                max_concurrency=max_concurrency,
            ):
                if error is None and parsed is not None:
                    try:
                        service.store_response(sha256=sha256, response=parsed)
                        session.commit()
                        result.requested += 1
                        result.persisted += 1
                        _append_ndjson(
                            output_ndjson,
                            {
                                "workflow": workflow_name,
                                "sha256": sha256,
                                "status": "persisted",
                                "reason": "batch request completed",
                                "prompt_input": prompt_input_model.model_dump(mode="json"),
                                "parsed_response": parsed.model_dump(mode="json"),
                                "persisted": True,
                            },
                        )
                    except Exception as exc:
                        session.rollback()
                        result.failed += 1
                        result.failures.append({"sha256": sha256, "error": str(exc)})
                        _append_ndjson(
                            output_ndjson,
                            {
                                "workflow": workflow_name,
                                "sha256": sha256,
                                "status": "failed",
                                "reason": str(exc),
                                "prompt_input": prompt_input_model.model_dump(mode="json"),
                                "parsed_response": None,
                                "persisted": False,
                            },
                        )
                    continue

                session.rollback()
                result.failed += 1
                result.failures.append({"sha256": sha256, "error": error or "unknown error"})
                _append_ndjson(
                    output_ndjson,
                    {
                        "workflow": workflow_name,
                        "sha256": sha256,
                        "status": "failed",
                        "reason": error or "unknown error",
                        "prompt_input": prompt_input_model.model_dump(mode="json"),
                        "parsed_response": None,
                        "persisted": False,
                    },
                )

            return result
    finally:
        engine.dispose()


def _document_record_from_orm(document: Document) -> DocumentRecord:
    return DocumentRecord(
        sha256=document.sha256,
        md5=document.md5,
        paths=[path.rel_path for path in sorted(document.paths, key=lambda item: item.rel_path)],
        file_name=document.file_name,
        normalised_name=document.normalised_name,
        metadata=PdfMetadata(
            title=document.metadata_title,
            author=document.metadata_author,
            creator=document.metadata_creator,
            created=document.metadata_created,
            modified=document.metadata_modified,
            extra=document.metadata_extra_json,
        ),
        toc=[
            TocEntry(level=entry.level, title=entry.title, page=entry.page)
            for entry in sorted(document.toc_entries, key=lambda item: item.position)
        ],
        languages=document.languages_json,
        is_digital=document.is_digital,
    )


def _require_parsed_response(parsed: ResponseT | None) -> ResponseT:
    """Return the parsed response or raise a clear error."""
    if parsed is None:
        msg = "LLM response did not contain a parsed structured payload"
        raise ValueError(msg)
    return parsed


def _execute_batch_requests(
    *,
    pending_requests: list[_PendingBatchRequest[PromptInputT]],
    workflow: PromptWorkflowDefinition[PromptInputT, ResponseT],
    openai_client: OpenAI,
    openai_model: str,
    max_concurrency: int,
) -> Iterator[tuple[str, PromptInputT, ResponseT | None, str | None]]:
    """Execute prompt requests serially or concurrently and yield results."""
    if max_concurrency <= 1:
        for request in pending_requests:
            yield _run_prompt_request(
                workflow=workflow,
                openai_client=openai_client,
                openai_model=openai_model,
                request=request,
            )
        return

    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        future_map = {
            executor.submit(
                _run_prompt_request,
                workflow=workflow,
                openai_client=openai_client,
                openai_model=openai_model,
                request=request,
            ): request
            for request in pending_requests
        }
        for future in as_completed(future_map):
            request = future_map[future]
            try:
                yield future.result()
            except Exception as exc:  # pragma: no cover - defensive fallback
                yield (request.sha256, request.prompt_input_model, None, str(exc))


def _run_prompt_request(
    *,
    workflow: PromptWorkflowDefinition[PromptInputT, ResponseT],
    openai_client: OpenAI,
    openai_model: str,
    request: _PendingBatchRequest[PromptInputT],
) -> tuple[str, PromptInputT, ResponseT | None, str | None]:
    """Execute one LLM request and return the parsed result or error string."""
    attempts = _BATCH_MAX_RETRIES + 1
    try:
        for attempt in range(attempts):
            try:
                response = openai_client.responses.parse(
                    model=openai_model,
                    instructions=workflow.system_prompt,
                    input=workflow.build_user_prompt(request.prompt_input_model),
                    text_format=workflow.response_model,
                )
                break
            except Exception:
                if attempt + 1 >= attempts:
                    raise
                time.sleep(_BATCH_RETRY_DELAY_SECONDS * (2**attempt))
        parsed = _require_parsed_response(response.output_parsed)
    except Exception as exc:
        return request.sha256, request.prompt_input_model, None, str(exc)
    return request.sha256, request.prompt_input_model, parsed, None


def _append_ndjson(path: Path | None, payload: dict[str, Any]) -> None:
    """Append one NDJSON record when a batch output path is configured."""
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{json.dumps(payload, ensure_ascii=False)}\n")
