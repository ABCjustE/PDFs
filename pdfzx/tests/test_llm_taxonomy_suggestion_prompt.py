from __future__ import annotations

import json

from pdfzx.config import DEFAULT_LLM_MAX_TOC_ENTRIES
from pdfzx.models import DocumentRecord
from pdfzx.models import PdfMetadata
from pdfzx.models import TocEntry
from pdfzx.prompts.llm_taxonomy_suggestion import ALLOWED_DOCUMENT_TYPES
from pdfzx.prompts.llm_taxonomy_suggestion import DEFAULT_TAXONOMY_TREE
from pdfzx.prompts.llm_taxonomy_suggestion import LLM_TAXONOMY_SUGGESTION_PROMPT_VERSION
from pdfzx.prompts.llm_taxonomy_suggestion import LLM_TAXONOMY_SUGGESTION_SYSTEM_PROMPT
from pdfzx.prompts.llm_taxonomy_suggestion import LlmTaxonomySuggestionResponse
from pdfzx.prompts.llm_taxonomy_suggestion import build_taxonomy_suggestion_prompt_input
from pdfzx.prompts.llm_taxonomy_suggestion import build_taxonomy_suggestion_user_prompt
from pdfzx.prompts.llm_taxonomy_suggestion import flatten_taxonomy_tree


def test_build_taxonomy_suggestion_prompt_input_includes_toc_and_taxonomy() -> None:
    record = DocumentRecord(
        sha256="abc",
        md5="def",
        file_name="bayesian_methods.pdf",
        normalised_name="Bayesian Methods.pdf",
        paths=["Books/AI/bayesian_methods.pdf"],
        metadata=PdfMetadata(title="Bayesian Methods", author="Jane Doe"),
        toc=[TocEntry(level=1, title="Probability Foundations", page=1)],
        languages=["en"],
        is_digital=True,
    )

    prompt_input = build_taxonomy_suggestion_prompt_input(record)
    dumped = prompt_input.model_dump()

    assert dumped["file_name"] == "bayesian_methods.pdf"
    assert dumped["toc"][0]["title"] == "Probability Foundations"
    assert dumped["taxonomy_tree"] == DEFAULT_TAXONOMY_TREE
    assert dumped["allowed_document_types"] == ALLOWED_DOCUMENT_TYPES


def test_build_taxonomy_suggestion_user_prompt_is_json() -> None:
    record = DocumentRecord(sha256="abc", md5="def", file_name="sample.pdf", paths=["sample.pdf"])
    taxonomy_tree = {"Mathematics": {"Linear Algebra": {}}}

    prompt = build_taxonomy_suggestion_user_prompt(
        build_taxonomy_suggestion_prompt_input(record, taxonomy_tree=taxonomy_tree)
    )

    payload = json.loads(prompt)
    assert payload["sha256"] == "abc"
    assert payload["taxonomy_tree"] == taxonomy_tree
    assert payload["allowed_document_types"] == ALLOWED_DOCUMENT_TYPES


def test_taxonomy_suggestion_response_schema_accepts_expected_shape() -> None:
    response = LlmTaxonomySuggestionResponse.model_validate(
        {
            "suggested_taxonomy_path": "Computer Science/Software Engineering",
            "suggested_document_type": "book",
            "suggested_new_subcategory": "Python",
            "confidence": 0.81,
            "reasoning_summary": "Filename and existing path suggest software engineering.",
        }
    )

    assert (
        response.suggested_taxonomy_path
        == "Computer Science/Software Engineering"
    )
    assert response.suggested_document_type == "book"
    assert response.suggested_new_subcategory == "Python"
    assert response.confidence == 0.81


def test_taxonomy_prompt_constants_are_defined() -> None:
    assert LLM_TAXONOMY_SUGGESTION_PROMPT_VERSION == "v1"
    assert "Do not use or infer any hidden full text" in LLM_TAXONOMY_SUGGESTION_SYSTEM_PROMPT
    assert "allowed_document_types" in LLM_TAXONOMY_SUGGESTION_SYSTEM_PROMPT


def test_build_taxonomy_suggestion_prompt_input_truncates_toc() -> None:
    record = DocumentRecord(
        sha256="abc",
        md5="def",
        file_name="long_toc.pdf",
        paths=["long_toc.pdf"],
        toc=[TocEntry(level=1, title=f"Chapter {index}", page=index) for index in range(50)],
    )

    prompt_input = build_taxonomy_suggestion_prompt_input(record)

    assert len(prompt_input.toc) == DEFAULT_LLM_MAX_TOC_ENTRIES
    assert prompt_input.toc[0]["title"] == "Chapter 0"
    assert (
        prompt_input.toc[-1]["title"]
        == f"Chapter {DEFAULT_LLM_MAX_TOC_ENTRIES - 1}"
    )


def test_build_taxonomy_suggestion_prompt_input_uses_custom_toc_limit() -> None:
    record = DocumentRecord(
        sha256="abc",
        md5="def",
        file_name="custom_toc.pdf",
        paths=["custom_toc.pdf"],
        toc=[TocEntry(level=1, title=f"Section {index}", page=index) for index in range(10)],
    )

    prompt_input = build_taxonomy_suggestion_prompt_input(record, max_toc_entries=3)

    assert len(prompt_input.toc) == 3
    assert prompt_input.toc[-1]["title"] == "Section 2"


def test_flatten_taxonomy_tree_flattens_nested_paths() -> None:
    tree = {"A": {"B": {"C": {}}, "D": {}}}

    assert flatten_taxonomy_tree(tree) == ["A", "A/B", "A/B/C", "A/D"]
