from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.models import Prompt
from pdfzx.db.repositories.document_suggestions import DocumentSuggestionRepository
from pdfzx.db.repositories.prompts import PromptRepository
from pdfzx.prompts.llm_document_suggestion import LLM_DOCUMENT_SUGGESTION_PROMPT_VERSION
from pdfzx.prompts.llm_document_suggestion import LLM_DOCUMENT_SUGGESTION_SYSTEM_PROMPT
from pdfzx.prompts.llm_document_suggestion import LLM_DOCUMENT_SUGGESTION_WORKFLOW
from pdfzx.prompts.llm_document_suggestion import LlmDocumentSuggestionResponse


@dataclass(slots=True)
class SuggestionDecision:
    """Idempotency decision for whether an LLM request should be sent."""

    should_request: bool
    reason: str
    prompt_id: int | None = None


class LlmDocumentSuggestionService:
    """Prompt registration and idempotency gate for document suggestions."""

    def __init__(self, session: Session, *, model_provider: str, model: str) -> None:
        self._session = session
        self._model_provider = model_provider
        self._model = model
        self._prompts = PromptRepository(session)
        self._suggestions = DocumentSuggestionRepository(session)

    def ensure_prompt(self) -> Prompt:
        """Ensure the active prompt record exists for the current model identity."""
        return self._prompts.upsert(
            workflow_name=LLM_DOCUMENT_SUGGESTION_WORKFLOW,
            prompt_text=LLM_DOCUMENT_SUGGESTION_SYSTEM_PROMPT,
            model_provider=self._model_provider,
            model=self._model,
            prompt_version=LLM_DOCUMENT_SUGGESTION_PROMPT_VERSION,
            active=True,
        )

    def should_request_for_document(self, *, sha256: str) -> SuggestionDecision:
        """Return whether the current document still needs a suggestion request."""
        prompt = self.ensure_prompt()
        existing = self._suggestions.get_by_document_and_prompt(sha256=sha256, prompt_id=prompt.id)
        if existing is not None:
            return SuggestionDecision(
                should_request=False,
                reason="suggestion already exists for this document and prompt",
                prompt_id=prompt.id,
            )
        return SuggestionDecision(
            should_request=True,
            reason="no suggestion exists for this document and prompt",
            prompt_id=prompt.id,
        )

    def store_response(self, *, sha256: str, response: LlmDocumentSuggestionResponse):
        """Persist a validated LLM suggestion for an existing document."""
        prompt = self.ensure_prompt()
        document = self._session.get(Document, sha256)
        if document is None:
            msg = f"Document not found: {sha256}"
            raise ValueError(msg)
        return self._suggestions.create_or_update(
            sha256=sha256, prompt=prompt, response=response, status="pending"
        )
