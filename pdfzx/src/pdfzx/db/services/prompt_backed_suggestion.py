from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.models import Prompt
from pdfzx.db.repositories.prompts import PromptRepository


class SuggestionRepository(Protocol):
    """Repository contract for prompt-backed document suggestions."""

    def get_by_document_and_prompt(self, *, sha256: str, prompt_id: int) -> object | None:
        """Return the stored suggestion for a document/prompt pair, if present."""

    def create_or_update(
        self,
        *,
        sha256: str,
        prompt: Prompt,
        response: object,
        status: str = "pending",
    ) -> object:
        """Upsert a structured suggestion payload for a document and prompt."""


@dataclass(slots=True)
class SuggestionDecision:
    """Idempotency decision for whether an LLM request should be sent."""

    should_request: bool
    reason: str
    prompt_id: int | None = None


class PromptBackedSuggestionService:
    """Shared prompt registration and idempotency gate for document suggestions."""

    def __init__(  # noqa: PLR0913
        self,
        session: Session,
        *,
        repository: SuggestionRepository,
        workflow_name: str,
        prompt_text: str,
        prompt_version: str,
        model_provider: str,
        model: str,
    ) -> None:
        self._session = session
        self._repository = repository
        self._workflow_name = workflow_name
        self._prompt_text = prompt_text
        self._prompt_version = prompt_version
        self._model_provider = model_provider
        self._model = model
        self._prompts = PromptRepository(session)

    def ensure_prompt(self) -> Prompt:
        """Ensure the active prompt record exists for the current model identity."""
        return self._prompts.upsert(
            workflow_name=self._workflow_name,
            prompt_text=self._prompt_text,
            model_provider=self._model_provider,
            model=self._model,
            prompt_version=self._prompt_version,
            active=True,
        )

    def should_request_for_document(self, *, sha256: str) -> SuggestionDecision:
        """Return whether the current document still needs a suggestion request."""
        prompt = self.ensure_prompt()
        existing = self._repository.get_by_document_and_prompt(sha256=sha256, prompt_id=prompt.id)
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

    def store_response(self, *, sha256: str, response: object) -> object:
        """Persist a validated LLM suggestion for an existing document."""
        prompt = self.ensure_prompt()
        document = self._session.get(Document, sha256)
        if document is None:
            msg = f"Document not found: {sha256}"
            raise ValueError(msg)
        return self._repository.create_or_update(
            sha256=sha256, prompt=prompt, response=response, status="pending"
        )
