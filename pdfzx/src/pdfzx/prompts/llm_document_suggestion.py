from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel
from pydantic import Field

from pdfzx.models import DocumentRecord

LLM_DOCUMENT_SUGGESTION_WORKFLOW = "llm_document_suggestion"
LLM_DOCUMENT_SUGGESTION_PROMPT_VERSION = "v1"

LLM_DOCUMENT_SUGGESTION_SYSTEM_PROMPT = """
You are assisting with PDF catalog cleanup and normalization.

You will receive only basic document facts. Do not use or infer any hidden full text.

Goals:
- identify the proper book/document title internally
- separate probable author, publisher, and edition information when present
- suggest a concise filename-oriented rename target
- assign a small set of useful labels

Rules:
- `suggested_file_name` must be a conservative rename target for the PDF file.
- keep the `.pdf` suffix.
- follow the same style as `normalised_name`:
  - use spaces between words, not underscores
  - use title-style capitalization
  - preserve the core title wording unless obvious filename noise is removed
- remove obvious filename noise when present:
  - prefixed or appended author names
  - publisher or source tags
  - edition or revision markers
  - bracketed upload or site junk
- do not aggressively rewrite the title into a different naming scheme
- use only the supplied fields
- do not invent missing facts
- keep output strictly as JSON matching the requested schema
- keep labels short and lowercase
- if a field is unknown, return null
""".strip()


class LlmDocumentSuggestionPromptInput(BaseModel):
    """Basic record facts allowed into the LLM prompt."""

    sha256: str
    file_name: str
    normalised_name: str | None = None
    paths: list[str] = Field(default_factory=list)
    metadata_title: str | None = None
    metadata_author: str | None = None
    metadata_creator: str | None = None
    metadata_created: str | None = None
    metadata_modified: str | None = None
    metadata_extra: dict[str, Any] = Field(default_factory=dict)
    languages: list[str] = Field(default_factory=list)
    is_digital: bool = True


class LlmDocumentSuggestionResponse(BaseModel):
    """Strict structured output contract for document suggestions."""

    suggested_file_name: str | None = None
    suggested_author: str | None = None
    suggested_publisher: str | None = None
    suggested_edition: str | None = None
    suggested_labels: list[str] = Field(default_factory=list)
    reasoning_summary: str | None = None


def build_document_suggestion_prompt_input(
    record: DocumentRecord,
) -> LlmDocumentSuggestionPromptInput:
    """Build the allowed prompt payload from a document record."""
    return LlmDocumentSuggestionPromptInput(
        sha256=record.sha256,
        file_name=record.file_name,
        normalised_name=record.normalised_name,
        paths=record.paths,
        metadata_title=record.metadata.title,
        metadata_author=record.metadata.author,
        metadata_creator=record.metadata.creator,
        metadata_created=record.metadata.created,
        metadata_modified=record.metadata.modified,
        metadata_extra=record.metadata.extra,
        languages=record.languages,
        is_digital=record.is_digital,
    )


def build_document_suggestion_user_prompt(prompt_input: LlmDocumentSuggestionPromptInput) -> str:
    """Serialize prompt input for the LLM user message."""
    return json.dumps(prompt_input.model_dump(mode="json"), ensure_ascii=False, indent=2)
