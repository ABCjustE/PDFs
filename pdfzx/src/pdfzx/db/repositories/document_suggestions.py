from __future__ import annotations

from datetime import UTC
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from pdfzx.db.models import LlmDocumentSuggestion
from pdfzx.db.models import Prompt
from pdfzx.prompts.llm_document_suggestion import LlmDocumentSuggestionResponse


class DocumentSuggestionRepository:
    """CRUD helpers for LLM document suggestions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_document_and_prompt(
        self, *, sha256: str, prompt_id: int
    ) -> LlmDocumentSuggestion | None:
        """Return the stored suggestion for a document/prompt pair, if present."""
        stmt = select(LlmDocumentSuggestion).where(
            LlmDocumentSuggestion.sha256 == sha256, LlmDocumentSuggestion.prompt_id == prompt_id
        )
        return self._session.scalar(stmt)

    def create_or_update(
        self,
        *,
        sha256: str,
        prompt: Prompt,
        response: LlmDocumentSuggestionResponse,
        status: str = "pending",
    ) -> LlmDocumentSuggestion:
        """Upsert the structured suggestion payload for a document and prompt."""
        now = datetime.now(tz=UTC).replace(tzinfo=None)
        suggestion = self.get_by_document_and_prompt(sha256=sha256, prompt_id=prompt.id)
        payload = response.model_dump(mode="json")

        if suggestion is None:
            suggestion = LlmDocumentSuggestion(
                sha256=sha256,
                prompt_id=prompt.id,
                suggested_file_name=payload["suggested_file_name"],
                suggested_author=payload["suggested_author"],
                suggested_publisher=payload["suggested_publisher"],
                suggested_edition=payload["suggested_edition"],
                suggested_labels_json=payload["suggested_labels"],
                reasoning_summary=payload["reasoning_summary"],
                status=status,
                applied=False,
                created_at=now,
                updated_at=now,
            )
            self._session.add(suggestion)
            self._session.flush()
            return suggestion

        suggestion.suggested_file_name = payload["suggested_file_name"]
        suggestion.suggested_author = payload["suggested_author"]
        suggestion.suggested_publisher = payload["suggested_publisher"]
        suggestion.suggested_edition = payload["suggested_edition"]
        suggestion.suggested_labels_json = payload["suggested_labels"]
        suggestion.reasoning_summary = payload["reasoning_summary"]
        suggestion.status = status
        suggestion.updated_at = now
        self._session.flush()
        return suggestion
