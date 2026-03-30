from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from pdfzx.config import DEFAULT_LLM_MAX_TOC_ENTRIES
from pdfzx.db.services.llm_toc_review_service import LlmTocReviewSuggestionService
from pdfzx.models import DocumentRecord
from pdfzx.prompts.llm_toc_review_suggestion import LLM_TOC_REVIEW_SUGGESTION_SYSTEM_PROMPT
from pdfzx.prompts.llm_toc_review_suggestion import LlmTocReviewSuggestionPromptInput
from pdfzx.prompts.llm_toc_review_suggestion import LlmTocReviewSuggestionResponse
from pdfzx.prompts.llm_toc_review_suggestion import build_toc_review_suggestion_prompt_input
from pdfzx.prompts.llm_toc_review_suggestion import build_toc_review_suggestion_user_prompt


@dataclass(slots=True)
class TocReviewSuggestionWorkflow:
    """Workflow definition for the ToC-review suggestion task."""

    system_prompt: str = LLM_TOC_REVIEW_SUGGESTION_SYSTEM_PROMPT
    response_model: type[LlmTocReviewSuggestionResponse] = LlmTocReviewSuggestionResponse
    max_toc_entries: int = DEFAULT_LLM_MAX_TOC_ENTRIES

    def build_prompt_input(
        self, record: DocumentRecord
    ) -> LlmTocReviewSuggestionPromptInput:
        """Build the structured prompt input from a document record."""
        if not record.toc:
            msg = f"Document does not have ToC entries to review: {record.sha256}"
            raise ValueError(msg)
        return build_toc_review_suggestion_prompt_input(
            record, max_toc_entries=self.max_toc_entries
        )

    def build_user_prompt(self, prompt_input: LlmTocReviewSuggestionPromptInput) -> str:
        """Serialize the user prompt payload."""
        return build_toc_review_suggestion_user_prompt(prompt_input)

    def create_service(
        self, session: Session, *, model_provider: str, model: str
    ) -> LlmTocReviewSuggestionService:
        """Create the ToC-review persistence/idempotency service."""
        return LlmTocReviewSuggestionService(
            session, model_provider=model_provider, model=model
        )
