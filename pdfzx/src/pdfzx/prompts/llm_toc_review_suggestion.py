from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator

from pdfzx.config import DEFAULT_LLM_MAX_TOC_ENTRIES
from pdfzx.models import DocumentRecord

LLM_TOC_REVIEW_SUGGESTION_WORKFLOW = "llm_toc_review_suggestion"
LLM_TOC_REVIEW_SUGGESTION_PROMPT_VERSION = "v1"

LLM_TOC_REVIEW_SUGGESTION_SYSTEM_PROMPT = """
You are reviewing extracted PDF table-of-contents data.

You will receive only structured document facts and an ordered ToC slice.
Do not use or infer any hidden full text.

Goals:
- judge whether the ToC appears relevant to the document topic, no need structurally perfect
- explain likely failure modes when the ToC is invalid or off-topic
- identify a likely preface or front-matter page when possible
- provide a confidence score

Evidence priority:
- file name
- normalised name
- metadata
- current relative path
- ordered ToC entries

Rules:
- `toc_is_valid` is about and trustworthiness of the extracted ToC
- `toc_matches_document` is about semantic relevance to the document topic
- if `toc_is_valid` is false, `toc_invalid_reason` must be a short non-empty explanation
- if the ToC appears valid but semantically mismatched, keep `toc_is_valid=true` and
  `toc_matches_document=false`
- set `preface_page` and `preface_label` only when a likely front-matter anchor is present
- likely front-matter labels include Preface, Foreword, Introduction, Editor's Note,
  About This Book, or close variants
- if `preface_page` is null, `preface_label` must also be null
- keep output strictly as JSON matching the requested schema
- `confidence` must be between 0 and 1
- `reasoning_summary` should be concise and evidence-based
""".strip()


class LlmTocReviewSuggestionPromptInput(BaseModel):
    """Document facts allowed into the ToC-review prompt."""

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
    toc: list[dict[str, Any]] = Field(default_factory=list)


class LlmTocReviewSuggestionResponse(BaseModel):
    """Strict structured output contract for ToC-review suggestions."""

    toc_is_valid: bool
    toc_matches_document: bool
    toc_invalid_reason: str | None = None
    preface_page: int | None = None
    preface_label: str | None = None
    confidence: float
    reasoning_summary: str | None = None

    @model_validator(mode="after")
    def validate_consistency(self) -> LlmTocReviewSuggestionResponse:
        """Enforce basic response consistency constraints."""
        if not self.toc_is_valid and not self.toc_invalid_reason:
            msg = "toc_invalid_reason is required when toc_is_valid is false"
            raise ValueError(msg)
        if self.preface_page is None and self.preface_label is not None:
            msg = "preface_label must be null when preface_page is null"
            raise ValueError(msg)
        if not 0 <= self.confidence <= 1:
            msg = "confidence must be between 0 and 1"
            raise ValueError(msg)
        return self


def build_toc_review_suggestion_prompt_input(
    record: DocumentRecord,
    *,
    max_toc_entries: int = DEFAULT_LLM_MAX_TOC_ENTRIES,
) -> LlmTocReviewSuggestionPromptInput:
    """Build the allowed prompt payload from a document record."""
    return LlmTocReviewSuggestionPromptInput(
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
        toc=[
            {"level": entry.level, "title": entry.title, "page": entry.page}
            for entry in record.toc[:max_toc_entries]
        ],
    )


def build_toc_review_suggestion_user_prompt(
    prompt_input: LlmTocReviewSuggestionPromptInput,
) -> str:
    """Serialize prompt input for the LLM user message."""
    return json.dumps(prompt_input.model_dump(mode="json"), ensure_ascii=False, indent=2)
