from __future__ import annotations

from sqlalchemy.orm import Session

from pdfzx.db.repositories.toc_review_suggestions import TocReviewSuggestionRepository
from pdfzx.db.services.prompt_backed_suggestion import PromptBackedSuggestionService
from pdfzx.prompts.llm_toc_review_suggestion import LLM_TOC_REVIEW_SUGGESTION_PROMPT_VERSION
from pdfzx.prompts.llm_toc_review_suggestion import LLM_TOC_REVIEW_SUGGESTION_SYSTEM_PROMPT
from pdfzx.prompts.llm_toc_review_suggestion import LLM_TOC_REVIEW_SUGGESTION_WORKFLOW
from pdfzx.prompts.llm_toc_review_suggestion import LlmTocReviewSuggestionResponse


class LlmTocReviewSuggestionService(PromptBackedSuggestionService):
    """Prompt registration and idempotency gate for ToC-review suggestions."""

    def __init__(self, session: Session, *, model_provider: str, model: str) -> None:
        super().__init__(
            session,
            repository=TocReviewSuggestionRepository(session),
            workflow_name=LLM_TOC_REVIEW_SUGGESTION_WORKFLOW,
            prompt_text=LLM_TOC_REVIEW_SUGGESTION_SYSTEM_PROMPT,
            prompt_version=LLM_TOC_REVIEW_SUGGESTION_PROMPT_VERSION,
            model_provider=model_provider,
            model=model,
        )

    def store_response(
        self, *, sha256: str, response: LlmTocReviewSuggestionResponse
    ) -> object:
        """Persist a validated LLM ToC-review suggestion for an existing document."""
        return super().store_response(sha256=sha256, response=response)
