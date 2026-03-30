from __future__ import annotations

from datetime import UTC
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from pdfzx.db.models import LlmTaxonomySuggestion
from pdfzx.db.models import Prompt
from pdfzx.prompts.llm_taxonomy_suggestion import LlmTaxonomySuggestionResponse


class TaxonomySuggestionRepository:
    """CRUD helpers for LLM taxonomy suggestions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_document_and_prompt(
        self, *, sha256: str, prompt_id: int
    ) -> LlmTaxonomySuggestion | None:
        """Return the stored taxonomy suggestion for a document/prompt pair, if present."""
        stmt = select(LlmTaxonomySuggestion).where(
            LlmTaxonomySuggestion.sha256 == sha256,
            LlmTaxonomySuggestion.prompt_id == prompt_id,
        )
        return self._session.scalar(stmt)

    def create_or_update(
        self,
        *,
        sha256: str,
        prompt: Prompt,
        response: LlmTaxonomySuggestionResponse,
        status: str = "pending",
    ) -> LlmTaxonomySuggestion:
        """Upsert the structured taxonomy payload for a document and prompt."""
        now = datetime.now(tz=UTC).replace(tzinfo=None)
        suggestion = self.get_by_document_and_prompt(sha256=sha256, prompt_id=prompt.id)
        payload = response.model_dump(mode="json")

        if suggestion is None:
            suggestion = LlmTaxonomySuggestion(
                sha256=sha256,
                prompt_id=prompt.id,
                suggested_taxonomy_path=payload["suggested_taxonomy_path"],
                suggested_document_type=payload["suggested_document_type"],
                suggested_new_subcategory=payload["suggested_new_subcategory"],
                confidence=payload["confidence"],
                reasoning_summary=payload["reasoning_summary"],
                status=status,
                applied=False,
                created_at=now,
                updated_at=now,
            )
            self._session.add(suggestion)
            self._session.flush()
            return suggestion

        suggestion.suggested_taxonomy_path = payload["suggested_taxonomy_path"]
        suggestion.suggested_document_type = payload["suggested_document_type"]
        suggestion.suggested_new_subcategory = payload["suggested_new_subcategory"]
        suggestion.confidence = payload["confidence"]
        suggestion.reasoning_summary = payload["reasoning_summary"]
        suggestion.status = status
        suggestion.updated_at = now
        self._session.flush()
        return suggestion
