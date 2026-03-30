from __future__ import annotations

import json

import pytest

from pdfzx.config import DEFAULT_LLM_MAX_TOC_ENTRIES
from pdfzx.models import DocumentRecord
from pdfzx.models import PdfMetadata
from pdfzx.models import TocEntry
from pdfzx.prompts.llm_toc_review_suggestion import LLM_TOC_REVIEW_SUGGESTION_PROMPT_VERSION
from pdfzx.prompts.llm_toc_review_suggestion import LLM_TOC_REVIEW_SUGGESTION_SYSTEM_PROMPT
from pdfzx.prompts.llm_toc_review_suggestion import LlmTocReviewSuggestionResponse
from pdfzx.prompts.llm_toc_review_suggestion import build_toc_review_suggestion_prompt_input
from pdfzx.prompts.llm_toc_review_suggestion import build_toc_review_suggestion_user_prompt


def test_build_toc_review_prompt_input_includes_toc_and_metadata() -> None:
    record = DocumentRecord(
        sha256="abc",
        md5="def",
        file_name="signals.pdf",
        normalised_name="Signals.pdf",
        paths=["Books/Electrical/signals.pdf"],
        metadata=PdfMetadata(title="Signals and Systems", author="Jane Doe"),
        toc=[TocEntry(level=1, title="Preface", page=5)],
        languages=["en"],
        is_digital=True,
    )

    prompt_input = build_toc_review_suggestion_prompt_input(record).model_dump()

    assert prompt_input["file_name"] == "signals.pdf"
    assert prompt_input["metadata_title"] == "Signals and Systems"
    assert prompt_input["toc"][0]["title"] == "Preface"


def test_build_toc_review_user_prompt_is_json() -> None:
    record = DocumentRecord(sha256="abc", md5="def", file_name="sample.pdf", paths=["sample.pdf"])

    prompt = build_toc_review_suggestion_user_prompt(
        build_toc_review_suggestion_prompt_input(record)
    )

    payload = json.loads(prompt)
    assert payload["sha256"] == "abc"
    assert payload["file_name"] == "sample.pdf"


def test_toc_review_response_schema_accepts_expected_shape() -> None:
    response = LlmTocReviewSuggestionResponse.model_validate(
        {
            "toc_is_valid": True,
            "toc_matches_document": True,
            "toc_invalid_reason": None,
            "preface_page": 7,
            "preface_label": "Preface",
            "confidence": 0.83,
            "reasoning_summary": "The ToC is coherent and prefaced properly.",
        }
    )

    assert response.toc_is_valid is True
    assert response.toc_matches_document is True
    assert response.preface_page == 7


def test_toc_review_response_requires_reason_when_invalid() -> None:
    with pytest.raises(ValueError, match="toc_invalid_reason is required"):
        LlmTocReviewSuggestionResponse.model_validate(
            {
                "toc_is_valid": False,
                "toc_matches_document": False,
                "toc_invalid_reason": None,
                "preface_page": None,
                "preface_label": None,
                "confidence": 0.4,
                "reasoning_summary": "Invalid ToC.",
            }
        )


def test_build_toc_review_prompt_input_truncates_toc() -> None:
    record = DocumentRecord(
        sha256="abc",
        md5="def",
        file_name="long_toc.pdf",
        paths=["long_toc.pdf"],
        toc=[TocEntry(level=1, title=f"Chapter {index}", page=index) for index in range(50)],
    )

    prompt_input = build_toc_review_suggestion_prompt_input(record)

    assert len(prompt_input.toc) == DEFAULT_LLM_MAX_TOC_ENTRIES
    assert prompt_input.toc[-1]["title"] == f"Chapter {DEFAULT_LLM_MAX_TOC_ENTRIES - 1}"


def test_toc_review_prompt_constants_are_defined() -> None:
    assert LLM_TOC_REVIEW_SUGGESTION_PROMPT_VERSION == "v1"
    assert "table-of-contents data" in LLM_TOC_REVIEW_SUGGESTION_SYSTEM_PROMPT
    assert "toc_matches_document" in LLM_TOC_REVIEW_SUGGESTION_SYSTEM_PROMPT
