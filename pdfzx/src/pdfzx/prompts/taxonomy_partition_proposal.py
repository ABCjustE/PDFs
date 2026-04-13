"""Prompt contract for identifying broad subject categories from one sampled batch."""

from __future__ import annotations

import json

from pydantic import BaseModel
from pydantic import Field

from pdfzx.models import DocumentRecord
from pdfzx.prompts._shared import build_system_prompt

TAXONOMY_PARTITION_PROPOSAL_WORKFLOW = "taxonomy_partition_proposal"
TAXONOMY_PARTITION_PROPOSAL_PROMPT_VERSION = "v2"

TAXONOMY_PARTITION_PROPOSAL_SYSTEM_PROMPT = build_system_prompt(
    role="You are identifying the main subject clusters in this sampled list of documents.",
    input_scope=(
        "a sampled batch of document names, paths, short titles, and a maximum "
        "category count"
    ),
    goals=[
        "identify the main broad subject categories in this sampled list",
        "return category names that are useful as folder names",
    ],
    evidence_priority=[
        "document file names and normalised names",
        "current paths",
        "metadata titles",
    ],
    rules=[
        (
            "prefer Computer Science over narrower topics like Data Structures or Algorithm Design "
            "when both fit"
        ),
        "do not return narrow subtopics as categories",
        "use narrower topics only as supporting evidence",
        "return at most `category_limit` broad categories",
        "keep category names short and folder-safe",
        "keep output strictly as JSON matching the requested schema",
        (
            "the JSON must use `categories` for broad subject categories and `supporting` for "
            "supporting topic groups"
        ),
        (
            'example: {"categories": ["Computer Science", "Mathematics"], '
            '"supporting": [{"category": "Computer Science", '
            '"topics": ["Data Structures and Algorithms", "Networking"]}, '
            '{"category": "Mathematics", "topics": ["Linear Algebra", "Calculus"]}]}'
        ),
    ],
)


class TaxonomyPartitionProposalPromptInput(BaseModel):
    """Prompt input for one sampled partition batch."""

    batch_index: int
    category_limit: int = 10
    chunk_documents: list[SampledDocumentSummary] = Field(default_factory=list)


class TaxonomyPartitionProposalResponse(BaseModel):
    """Structured output for one partition proposal batch."""

    categories: list[str] = Field(default_factory=list, max_length=10)
    supporting: list[TaxonomyPartitionSupportingGroup] = Field(default_factory=list)


def build_taxonomy_partition_proposal_user_prompt(
    prompt_input: TaxonomyPartitionProposalPromptInput,
) -> str:
    """Serialize structured input for the partition proposal prompt."""
    payload = prompt_input.model_dump(mode="json")
    # Keep sha256 in Python-side summaries for traceability, but do not send it to the model.
    payload["chunk_documents"] = [
        {
            key: value
            for key, value in document.items()
            if key != "sha256"
        }
        for document in payload["chunk_documents"]
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


class SampledDocumentSummary(BaseModel):
    """Compact document facts suitable for taxonomy partition prompts."""

    sha256: str
    file_name: str
    normalised_name: str | None = None
    current_path: str | None = None
    metadata_title: str | None = None


class TaxonomyPartitionSupportingGroup(BaseModel):
    """Supporting narrower topics for one broad category."""

    category: str
    topics: list[str] = Field(default_factory=list)


def build_sampled_document_summary(record: DocumentRecord) -> SampledDocumentSummary:
    """Build a compact prompt-safe summary from a document record."""
    return SampledDocumentSummary(
        sha256=record.sha256,
        file_name=record.file_name,
        normalised_name=record.normalised_name,
        current_path=min(record.paths) if record.paths else None,
        metadata_title=record.metadata.title,
    )
