from __future__ import annotations

from sqlalchemy.orm import Session

from pdfzx.db.repositories.taxonomy_suggestions import TaxonomySuggestionRepository
from pdfzx.db.services.prompt_backed_suggestion import PromptBackedSuggestionService
from pdfzx.prompts.llm_taxonomy_suggestion import LLM_TAXONOMY_SUGGESTION_PROMPT_VERSION
from pdfzx.prompts.llm_taxonomy_suggestion import LLM_TAXONOMY_SUGGESTION_SYSTEM_PROMPT
from pdfzx.prompts.llm_taxonomy_suggestion import LLM_TAXONOMY_SUGGESTION_WORKFLOW
from pdfzx.prompts.llm_taxonomy_suggestion import LlmTaxonomySuggestionResponse


class LlmTaxonomySuggestionService(PromptBackedSuggestionService):
    """Prompt registration and idempotency gate for taxonomy suggestions."""

    def __init__(self, session: Session, *, model_provider: str, model: str) -> None:
        super().__init__(
            session,
            repository=TaxonomySuggestionRepository(session),
            workflow_name=LLM_TAXONOMY_SUGGESTION_WORKFLOW,
            prompt_text=LLM_TAXONOMY_SUGGESTION_SYSTEM_PROMPT,
            prompt_version=LLM_TAXONOMY_SUGGESTION_PROMPT_VERSION,
            model_provider=model_provider,
            model=model,
        )

    def store_response(
        self, *, sha256: str, response: LlmTaxonomySuggestionResponse
    ) -> object:
        """Persist a validated LLM taxonomy suggestion for an existing document."""
        return super().store_response(sha256=sha256, response=response)
