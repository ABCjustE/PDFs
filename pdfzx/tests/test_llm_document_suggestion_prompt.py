from __future__ import annotations

import json

from pdfzx.models import DocumentRecord
from pdfzx.models import PdfMetadata
from pdfzx.models import TocEntry
from pdfzx.prompts.llm_document_suggestion import LLM_DOCUMENT_SUGGESTION_PROMPT_VERSION
from pdfzx.prompts.llm_document_suggestion import LLM_DOCUMENT_SUGGESTION_SYSTEM_PROMPT
from pdfzx.prompts.llm_document_suggestion import LlmDocumentSuggestionResponse
from pdfzx.prompts.llm_document_suggestion import build_document_suggestion_prompt_input
from pdfzx.prompts.llm_document_suggestion import build_document_suggestion_user_prompt


def test_build_document_suggestion_prompt_input_excludes_toc() -> None:
    record = DocumentRecord(
        sha256="abc",
        md5="def",
        file_name="sample.pdf",
        normalised_name="Sample.pdf",
        paths=["sample.pdf"],
        metadata=PdfMetadata(title="Sample Title", author="Author", extra={"publisher": "Pub"}),
        toc=[TocEntry(level=1, title="Chapter 1", page=1)],
        languages=["en"],
        is_digital=True,
    )

    prompt_input = build_document_suggestion_prompt_input(record)
    dumped = prompt_input.model_dump()

    assert dumped["file_name"] == "sample.pdf"
    assert dumped["metadata_title"] == "Sample Title"
    assert "toc" not in dumped


def test_build_document_suggestion_user_prompt_is_json() -> None:
    record = DocumentRecord(sha256="abc", md5="def", file_name="sample.pdf", paths=["sample.pdf"])

    prompt = build_document_suggestion_user_prompt(
        build_document_suggestion_prompt_input(record)
    )

    payload = json.loads(prompt)
    assert payload["sha256"] == "abc"
    assert payload["file_name"] == "sample.pdf"


def test_document_suggestion_response_schema_accepts_expected_shape() -> None:
    response = LlmDocumentSuggestionResponse.model_validate(
        {
            "suggested_file_name": "Advanced Python Programming.pdf",
            "suggested_author": "John Smith",
            "suggested_publisher": "O'Reilly Media",
            "suggested_edition": "3rd edition",
            "suggested_labels": ["python", "programming"],
            "reasoning_summary": "Filename contains title and edition noise.",
        }
    )

    assert response.suggested_file_name == "Advanced Python Programming.pdf"
    assert response.suggested_labels == ["python", "programming"]


def test_prompt_constants_are_defined() -> None:
    assert LLM_DOCUMENT_SUGGESTION_PROMPT_VERSION == "v1"
    assert "Do not use or infer any hidden full text" in LLM_DOCUMENT_SUGGESTION_SYSTEM_PROMPT
