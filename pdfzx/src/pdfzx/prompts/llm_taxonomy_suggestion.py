from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import Field

from pdfzx.config import DEFAULT_LLM_MAX_TOC_ENTRIES
from pdfzx.models import DocumentRecord
from pdfzx.prompts._shared import build_system_prompt
from pdfzx.prompts._shared import dump_prompt_input

LLM_TAXONOMY_SUGGESTION_WORKFLOW = "llm_taxonomy_suggestion"
LLM_TAXONOMY_SUGGESTION_PROMPT_VERSION = "v1"
ALLOWED_DOCUMENT_TYPES = [
    "book",
    "lecture_note",
    "homework",
    "solution",
    "exam",
    "manual",
    "report",
    "article",
]

DEFAULT_TAXONOMY_TREE: dict[str, dict[str, object]] = {
    "Mathematics": {
        "Algebra": {},
        "Linear Algebra": {},
        "Combinatorics and Graph Theory": {},
        "Analysis and Topology": {},
        "Optimization": {},
        "Probability Foundations": {},
    },
    "Statistics Data Science": {
        "Statistical Inference": {},
        "Time Series and Forecasting": {},
        "Data Science": {},
        "Machine Learning": {},
        "Neural Networks": {},
        "Applied Analytics": {},
    },
    "Computer Science": {
        "Algorithms and Data Structures": {},
        "Systems and Operating Systems": {},
        "Programming Languages": {},
        "Software Engineering": {},
        "Cloud and Distributed Systems": {},
        "Debugging and Tooling": {},
    },
    "Artificial Intelligence": {
        "Core AI": {},
        "Search and Planning": {},
        "Computer Vision": {},
        "Bayesian Methods": {},
        "Robotics AI": {},
    },
    "Electrical Embedded Control": {
        "Circuits and Electronics": {},
        "Embedded Systems": {},
        "Signal Processing": {},
        "Communications and Sensors": {},
        "Control Systems": {},
    },
    "Mechanical Manufacturing": {
        "Manufacturing and CNC": {},
        "Machine Design": {},
        "Thermodynamics and Fluids": {},
        "Mechatronics": {},
        "Engineering Practice": {},
    },
    "Physics": {
        "Classical Mechanics": {},
        "Electromagnetism": {},
        "Quantum Mechanics": {},
        "Relativity": {},
        "Thermal and Statistical Physics": {},
        "Particle Physics": {},
    },
    "Finance Economics": {
        "Trading and Market Structure": {},
        "Technical Analysis": {},
        "Derivatives and Risk": {},
        "Investments": {},
        "Economics": {},
    },
    "Reference Miscellaneous": {
        "Arts and Drawing": {},
        "Manuals and Reference": {},
        "Biography and Social Topics": {},
        "Hobbies and Personal Interest": {},
        "Miscellaneous": {},
    },
}

LLM_TAXONOMY_SUGGESTION_SYSTEM_PROMPT = build_system_prompt(
    role="You are assisting with taxonomy classification for PDF catalog records.",
    input_scope="structured document facts and the allowed taxonomy tree",
    goals=[
        "choose the single best-fit taxonomy path from the provided tree",
        "classify the document type",
        "optionally suggest one missing subcategory if the existing tree feels too coarse",
        "provide a confidence score",
        "explain the decision briefly",
    ],
    evidence_priority=[
        "current relative path",
        "file name",
        "normalised name",
        "metadata",
        "ToC if present",
        "`is_digital` as context only",
    ],
    rules=[
        "choose exactly one taxonomy path from the provided `taxonomy_tree`",
        "do not invent a primary path outside the provided tree",
        "choose exactly one document type from the provided `allowed_document_types`",
        "prefer filename and path clues first, then metadata, then ToC",
        "ToC is helpful but not required",
        (
            "if the classification is weak or ambiguous, still choose the best-fit "
            "path and lower confidence"
        ),
        (
            "`suggested_new_subcategory` must be null unless the existing tree is "
            "clearly missing a useful finer-grained grouping"
        ),
        "keep output strictly as JSON matching the requested schema",
        "`confidence` must be between 0 and 1",
        "`reasoning_summary` should be concise and evidence-based",
    ],
)


class LlmTaxonomySuggestionPromptInput(BaseModel):
    """Document facts allowed into the taxonomy prompt."""

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
    taxonomy_tree: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_TAXONOMY_TREE))
    allowed_document_types: list[str] = Field(default_factory=lambda: list(ALLOWED_DOCUMENT_TYPES))


class LlmTaxonomySuggestionResponse(BaseModel):
    """Strict structured output contract for taxonomy suggestions."""

    suggested_taxonomy_path: str
    suggested_document_type: str
    suggested_new_subcategory: str | None = None
    confidence: float
    reasoning_summary: str | None = None


def build_taxonomy_suggestion_prompt_input(
    record: DocumentRecord,
    *,
    taxonomy_tree: dict[str, Any] | None = None,
    max_toc_entries: int = DEFAULT_LLM_MAX_TOC_ENTRIES,
) -> LlmTaxonomySuggestionPromptInput:
    """Build the allowed prompt payload from a document record."""
    chosen_tree = taxonomy_tree or dict(DEFAULT_TAXONOMY_TREE)
    return LlmTaxonomySuggestionPromptInput(
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
        taxonomy_tree=chosen_tree,
        allowed_document_types=list(ALLOWED_DOCUMENT_TYPES),
    )


def build_taxonomy_suggestion_user_prompt(
    prompt_input: LlmTaxonomySuggestionPromptInput,
) -> str:
    """Serialize prompt input for the LLM user message."""
    return dump_prompt_input(prompt_input)


def flatten_taxonomy_tree(
    taxonomy_tree: dict[str, Any],
    *,
    prefix: str = "",
) -> list[str]:
    """Flatten a nested taxonomy tree into slash-delimited allowed paths."""
    flattened: list[str] = []
    for name, child in taxonomy_tree.items():
        current = f"{prefix}/{name}" if prefix else name
        flattened.append(current)
        if isinstance(child, dict) and child:
            flattened.extend(flatten_taxonomy_tree(child, prefix=current))
    return flattened
