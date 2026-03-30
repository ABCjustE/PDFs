from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from pdfzx.db.services.llm_document_service import LlmDocumentSuggestionService
from pdfzx.models import DocumentRecord
from pdfzx.prompts.llm_document_suggestion import LLM_DOCUMENT_SUGGESTION_SYSTEM_PROMPT
from pdfzx.prompts.llm_document_suggestion import LlmDocumentSuggestionPromptInput
from pdfzx.prompts.llm_document_suggestion import LlmDocumentSuggestionResponse
from pdfzx.prompts.llm_document_suggestion import build_document_suggestion_prompt_input
from pdfzx.prompts.llm_document_suggestion import build_document_suggestion_user_prompt


@dataclass(slots=True)
class DocumentSuggestionWorkflow:
    """Workflow definition for the document-attribute suggestion task."""

    system_prompt: str = LLM_DOCUMENT_SUGGESTION_SYSTEM_PROMPT
    response_model: type[LlmDocumentSuggestionResponse] = LlmDocumentSuggestionResponse

    def build_prompt_input(
        self, record: DocumentRecord
    ) -> LlmDocumentSuggestionPromptInput:
        """Build the structured prompt input from a document record."""
        return build_document_suggestion_prompt_input(record)

    def build_user_prompt(self, prompt_input: LlmDocumentSuggestionPromptInput) -> str:
        """Serialize the user prompt payload."""
        return build_document_suggestion_user_prompt(prompt_input)

    def create_service(
        self, session: Session, *, model_provider: str, model: str
    ) -> LlmDocumentSuggestionService:
        """Create the document-suggestion persistence/idempotency service."""
        return LlmDocumentSuggestionService(session, model_provider=model_provider, model=model)
