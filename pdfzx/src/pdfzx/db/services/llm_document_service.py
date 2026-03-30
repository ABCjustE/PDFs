from __future__ import annotations

from sqlalchemy.orm import Session

from pdfzx.db.repositories.document_suggestions import DocumentSuggestionRepository
from pdfzx.db.services.prompt_backed_suggestion import PromptBackedSuggestionService
from pdfzx.prompts.llm_document_suggestion import LLM_DOCUMENT_SUGGESTION_PROMPT_VERSION
from pdfzx.prompts.llm_document_suggestion import LLM_DOCUMENT_SUGGESTION_SYSTEM_PROMPT
from pdfzx.prompts.llm_document_suggestion import LLM_DOCUMENT_SUGGESTION_WORKFLOW
from pdfzx.prompts.llm_document_suggestion import LlmDocumentSuggestionResponse


class LlmDocumentSuggestionService(PromptBackedSuggestionService):
    """Prompt registration and idempotency gate for document suggestions."""

    def __init__(self, session: Session, *, model_provider: str, model: str) -> None:
        super().__init__(
            session,
            repository=DocumentSuggestionRepository(session),
            workflow_name=LLM_DOCUMENT_SUGGESTION_WORKFLOW,
            prompt_text=LLM_DOCUMENT_SUGGESTION_SYSTEM_PROMPT,
            prompt_version=LLM_DOCUMENT_SUGGESTION_PROMPT_VERSION,
            model_provider=model_provider,
            model=model,
        )

    def store_response(
        self, *, sha256: str, response: LlmDocumentSuggestionResponse
    ) -> object:
        """Persist a validated LLM suggestion for an existing document."""
        return super().store_response(sha256=sha256, response=response)
