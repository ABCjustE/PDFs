"""Prompt contract for merging taxonomy proposal JSON results."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic import Field

from pdfzx.prompts._shared import build_system_prompt
from pdfzx.prompts._shared import dump_prompt_input
from pdfzx.prompts.taxonomy_partition_proposal import TaxonomyPartitionSupportingGroup

TAXONOMY_PARTITION_GENERALIZE_WORKFLOW = "taxonomy_partition_generalize"
TAXONOMY_PARTITION_GENERALIZE_PROMPT_VERSION = "v8"

TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT = build_system_prompt(
    role="You are summarizing and merging multiple taxonomy JSON proposals into one final result.",
    input_scope="proposal JSON results and a maximum category count",
    goals=[
        "merge similar broad subject categories sensibly",
        "return one final set of broad categories with supporting topics",
    ],
    evidence_priority=[
        "repeated broad categories across proposals",
        "supporting topics grouped under each category",
        "stable, recognizable subject areas over noisy wording differences",
    ],
    rules=[
        "return JSON with `categories` and `supporting`",
        "return broad categories only",
        "use supporting topics as evidence when merging similar categories",
        "do not return duplicate or near-duplicate categories",
        "if `category_limit` is smaller, choose broader categories",
        (
            "do not keep a weak standalone category when its evidence is sparse and it can be "
            "merged into a stronger neighboring category"
        ),
        (
            "fold small hobby, maker, or miscellaneous edge pockets into the nearest stronger "
            "technical category when that fit is reasonable"
        ),
        "return at most `category_limit` categories",
        "keep category names short and folder-safe",
        "keep output strictly as JSON matching the requested schema",
        (
            'example: {"categories": ["Computer Science", "Mathematics"], '
            '"supporting": [{"category": "Computer Science", '
            '"topics": ["Data Structures and Algorithms", "Networking"]}, '
            '{"category": "Mathematics", "topics": ["Linear Algebra", "Calculus"]}]}'
        ),
    ],
)


class TaxonomyPartitionGeneralizeProposal(BaseModel):
    """One proposal JSON result to be merged."""

    categories: list[str] = Field(default_factory=list)
    supporting: list[TaxonomyPartitionSupportingGroup] = Field(default_factory=list)


class TaxonomyPartitionGeneralizePromptInput(BaseModel):
    """Prompt input for final taxonomy-partition merging."""

    category_limit: int = 10
    proposals: list[TaxonomyPartitionGeneralizeProposal] = Field(default_factory=list)


class TaxonomyPartitionGeneralizeResponse(BaseModel):
    """Structured output for final taxonomy-partition merging."""

    categories: list[str] = Field(default_factory=list, max_length=10)
    supporting: list[TaxonomyPartitionSupportingGroup] = Field(default_factory=list)


def build_taxonomy_partition_generalize_user_prompt(
    prompt_input: TaxonomyPartitionGeneralizePromptInput,
) -> str:
    """Serialize structured input for the taxonomy generalization prompt."""
    return dump_prompt_input(prompt_input)
