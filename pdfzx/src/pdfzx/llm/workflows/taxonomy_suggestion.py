from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from pdfzx.config import DEFAULT_LLM_MAX_TOC_ENTRIES
from pdfzx.db.services.llm_taxonomy_service import LlmTaxonomySuggestionService
from pdfzx.models import DocumentRecord
from pdfzx.prompts.llm_taxonomy_suggestion import LLM_TAXONOMY_SUGGESTION_SYSTEM_PROMPT
from pdfzx.prompts.llm_taxonomy_suggestion import LlmTaxonomySuggestionPromptInput
from pdfzx.prompts.llm_taxonomy_suggestion import LlmTaxonomySuggestionResponse
from pdfzx.prompts.llm_taxonomy_suggestion import build_taxonomy_suggestion_prompt_input
from pdfzx.prompts.llm_taxonomy_suggestion import build_taxonomy_suggestion_user_prompt


@dataclass(slots=True)
class TaxonomySuggestionWorkflow:
    """Workflow definition for the taxonomy suggestion task."""

    system_prompt: str = LLM_TAXONOMY_SUGGESTION_SYSTEM_PROMPT
    response_model: type[LlmTaxonomySuggestionResponse] = LlmTaxonomySuggestionResponse
    max_toc_entries: int = DEFAULT_LLM_MAX_TOC_ENTRIES

    def build_prompt_input(
        self, record: DocumentRecord
    ) -> LlmTaxonomySuggestionPromptInput:
        """Build the structured prompt input from a document record."""
        return build_taxonomy_suggestion_prompt_input(
            record, max_toc_entries=self.max_toc_entries
        )

    def build_user_prompt(self, prompt_input: LlmTaxonomySuggestionPromptInput) -> str:
        """Serialize the user prompt payload."""
        return build_taxonomy_suggestion_user_prompt(prompt_input)

    def create_service(
        self, session: Session, *, model_provider: str, model: str
    ) -> LlmTaxonomySuggestionService:
        """Create the taxonomy persistence/idempotency service."""
        return LlmTaxonomySuggestionService(session, model_provider=model_provider, model=model)
