from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI
from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.services.llm_document_service import LlmDocumentSuggestionService
from pdfzx.db.session import create_sqlite_engine
from pdfzx.models import DocumentRecord
from pdfzx.models import PdfMetadata
from pdfzx.prompts.llm_document_suggestion import LLM_DOCUMENT_SUGGESTION_SYSTEM_PROMPT
from pdfzx.prompts.llm_document_suggestion import LlmDocumentSuggestionResponse
from pdfzx.prompts.llm_document_suggestion import build_document_suggestion_prompt_input
from pdfzx.prompts.llm_document_suggestion import build_document_suggestion_user_prompt


@dataclass(slots=True)
class ProbeSuggestionResult:
    should_request: bool
    reason: str
    prompt_id: int | None
    prompt_input: dict[str, object] | None
    parsed_response: dict[str, object] | None
    persisted: bool


def probe_document_suggestion(
    *,
    sqlite_db_path,
    sha256: str,
    online_features: bool,
    openai_api_key: str | None,
    openai_model: str,
    persist: bool = False,
    force: bool = False,
    client: OpenAI | None = None,
) -> ProbeSuggestionResult:
    if not online_features:
        msg = "PDFZX_ONLINE_FEATURES is disabled"
        raise ValueError(msg)
    if not openai_api_key:
        msg = "PDFZX_OPENAI_API_KEY is required for probe-llm"
        raise ValueError(msg)

    engine = create_sqlite_engine(sqlite_db_path)
    try:
        with Session(engine) as session:
            service = LlmDocumentSuggestionService(
                session, model_provider="openai", model=openai_model
            )
            decision = service.should_request_for_document(sha256=sha256)
            document = session.get(Document, sha256)
            if document is None:
                msg = f"Document not found: {sha256}"
                raise ValueError(msg)

            prompt_input_model = build_document_suggestion_prompt_input(
                _document_record_from_orm(document)
            )
            if not force and not decision.should_request:
                return ProbeSuggestionResult(
                    should_request=False,
                    reason=decision.reason,
                    prompt_id=decision.prompt_id,
                    prompt_input=prompt_input_model.model_dump(mode="json"),
                    parsed_response=None,
                    persisted=False,
                )

            response = (client or OpenAI(api_key=openai_api_key)).responses.parse(
                model=openai_model,
                instructions=LLM_DOCUMENT_SUGGESTION_SYSTEM_PROMPT,
                input=build_document_suggestion_user_prompt(prompt_input_model),
                text_format=LlmDocumentSuggestionResponse,
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
        languages=document.languages_json,
        is_digital=document.is_digital,
    )
