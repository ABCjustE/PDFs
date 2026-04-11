"""Prompt contract for taxonomy-partition accumulation over one batch."""

from __future__ import annotations

import json

from pydantic import BaseModel
from pydantic import Field

from pdfzx.models import DocumentRecord
from pdfzx.prompts._shared import build_system_prompt

TAXONOMY_PARTITION_PROPOSAL_WORKFLOW = "taxonomy_partition_proposal"
TAXONOMY_PARTITION_PROPOSAL_PROMPT_VERSION = "v1"

TAXONOMY_PARTITION_PROPOSAL_SYSTEM_PROMPT = build_system_prompt(
    role="You are accumulating candidate taxonomy categories from one document batch.",
    input_scope=(
        "a parent node path, the current taxonomy bag, and one sampled chunk "
        "of document summaries"
    ),
    goals=[
        "accumulate a compact candidate taxonomy bag for this batch",
        "treat the current taxonomy bag as mutable working state rather than starting from scratch",
        "prefer broad stable umbrellas over narrow descendants at this stage",
        "keep category names compact and path-safe",
    ],
    evidence_priority=[
        "chunk document file names and normalised names",
        "current paths",
        "short metadata titles",
        "the current taxonomy bag",
    ],
    rules=[
        "return at most `bag_size_limit` taxonomy bags",
        "do not create near one-document-per-category output",
        (
            "this is an accumulation stage, not the final collapse stage, so keep "
            "useful broad candidates instead of over-optimizing the final hierarchy"
        ),
        (
            "if the batch is small or already coherent, return only a few broad "
            "categories, or an empty bag if no split is justified"
        ),
        (
            "prefer subject-level umbrellas such as Physics Coursework over "
            "narrow labels such as Quiz Solutions when both fit"
        ),
        "include Others when a few minority items do not justify their own category in this batch",
        "each taxonomy bag item must be a short folder-safe label in title case with spaces only",
        "do not return explanatory phrases as taxonomy names",
        "prefer semantically distinct taxonomy names with minimal overlap",
        "preserve and refine the current taxonomy bag when it is already useful",
        "avoid noisy storage words such as Books, NewBooks, Misc, Docs, and PDF in taxonomy names",
        "keep output strictly as JSON matching the requested schema",
    ],
)


class TaxonomyPartitionProposalPromptInput(BaseModel):
    """Loop-1 prompt input for one partitioning batch."""

    batch_index: int
    bag_size_limit: int = 10
    taxonomy_bag_before: list[str] = Field(default_factory=list)
    chunk_documents: list[SampledDocumentSummary] = Field(default_factory=list)


class TaxonomyPartitionProposalResponse(BaseModel):
    """Structured output for one partition proposal batch."""

    taxonomy_bag_after: list[str] = Field(default_factory=list, max_length=10)


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


def build_sampled_document_summary(record: DocumentRecord) -> SampledDocumentSummary:
    """Build a compact prompt-safe summary from a document record."""
    return SampledDocumentSummary(
        sha256=record.sha256,
        file_name=record.file_name,
        normalised_name=record.normalised_name,
        current_path=min(record.paths) if record.paths else None,
        metadata_title=record.metadata.title,
    )
