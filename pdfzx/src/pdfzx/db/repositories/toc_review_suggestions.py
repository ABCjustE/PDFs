from __future__ import annotations

from datetime import UTC
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from pdfzx.db.models import LlmTocReviewSuggestion
from pdfzx.db.models import Prompt
from pdfzx.prompts.llm_toc_review_suggestion import LlmTocReviewSuggestionResponse


class TocReviewSuggestionRepository:
    """CRUD helpers for LLM ToC-review suggestions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_document_and_prompt(
        self, *, sha256: str, prompt_id: int
    ) -> LlmTocReviewSuggestion | None:
        """Return the stored ToC-review suggestion for a document/prompt pair, if present."""
        stmt = select(LlmTocReviewSuggestion).where(
            LlmTocReviewSuggestion.sha256 == sha256,
            LlmTocReviewSuggestion.prompt_id == prompt_id,
        )
        return self._session.scalar(stmt)

    def create_or_update(
        self,
        *,
        sha256: str,
        prompt: Prompt,
        response: LlmTocReviewSuggestionResponse,
        status: str = "pending",
    ) -> LlmTocReviewSuggestion:
        """Upsert the structured ToC-review payload for a document and prompt."""
        now = datetime.now(tz=UTC).replace(tzinfo=None)
        suggestion = self.get_by_document_and_prompt(sha256=sha256, prompt_id=prompt.id)
        payload = response.model_dump(mode="json")

        if suggestion is None:
            suggestion = LlmTocReviewSuggestion(
                sha256=sha256,
                prompt_id=prompt.id,
                toc_is_valid=payload["toc_is_valid"],
                toc_matches_document=payload["toc_matches_document"],
                toc_invalid_reason=payload["toc_invalid_reason"],
                preface_page=payload["preface_page"],
                preface_label=payload["preface_label"],
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

        suggestion.toc_is_valid = payload["toc_is_valid"]
        suggestion.toc_matches_document = payload["toc_matches_document"]
        suggestion.toc_invalid_reason = payload["toc_invalid_reason"]
        suggestion.preface_page = payload["preface_page"]
        suggestion.preface_label = payload["preface_label"]
        suggestion.confidence = payload["confidence"]
        suggestion.reasoning_summary = payload["reasoning_summary"]
        suggestion.status = status
        suggestion.updated_at = now
        self._session.flush()
        return suggestion
