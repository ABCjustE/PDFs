"""Prompt contract for final taxonomy-partition generalization."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic import Field

from pdfzx.prompts._shared import build_system_prompt
from pdfzx.prompts._shared import dump_prompt_input

TAXONOMY_PARTITION_GENERALIZE_WORKFLOW = "taxonomy_partition_generalize"
TAXONOMY_PARTITION_GENERALIZE_PROMPT_VERSION = "v2"

TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT = build_system_prompt(
    role="You are consolidating accumulated taxonomy candidates into a final parent-layer bag.",
    input_scope=(
        "an accumulated taxonomy bag gathered from multiple batches, plus optional "
        "candidate counts and the current bag size limit"
    ),
    goals=[
        "collapse overlapping or duplicate categories into a compact final bag",
        "generalize narrow labels upward when a broader parent category is more stable",
        "produce parent-layer categories that can cover future batches, not just one local chunk",
        "produce sibling categories that are as non-overlapping as reasonably possible",
    ],
    evidence_priority=[
        "repeated category names across accumulated candidates",
        "category counts if provided",
        "broader subject umbrellas over narrow subtopics or file types",
    ],
    rules=[
        "return at most `bag_size_limit` taxonomy bags",
        "prefer broad stable umbrellas over narrow descendants",
        "merge near-duplicates and sibling categories whenever a reasonable parent exists",
        (
            "do not return both a broad parent and its narrow descendant in the same bag, "
            "for example Physics together with Quantum Mechanics or Electromagnetics"
        ),
        (
            "if two labels would cover heavily overlapping documents, keep only the broader "
            "or more stable parent label"
        ),
        (
            "the final bag should contain sibling categories, not mixed hierarchy levels or "
            "specialized subtopics beside their parent"
        ),
        "use fewer than `bag_size_limit` items when a smaller broad set is cleaner",
        (
            "avoid file-type labels such as Solutions, Homework, and Exams "
            "unless document type is the main organizing principle"
        ),
        "include Others when a few minority items do not justify their own stable parent category",
        "each taxonomy bag item must be a short folder-safe label in title case with spaces only",
        "keep output strictly as JSON matching the requested schema",
    ],
)


class TaxonomyPartitionGeneralizePromptInput(BaseModel):
    """Prompt input for final taxonomy-partition generalization."""

    bag_size_limit: int = 10
    taxonomy_bag_before: list[str] = Field(default_factory=list)
    candidate_counts: dict[str, int] = Field(default_factory=dict)


class TaxonomyPartitionGeneralizeResponse(BaseModel):
    """Structured output for final taxonomy-partition generalization."""

    taxonomy_bag_after: list[str] = Field(default_factory=list, max_length=10)


def build_taxonomy_partition_generalize_user_prompt(
    prompt_input: TaxonomyPartitionGeneralizePromptInput,
) -> str:
    """Serialize structured input for the taxonomy generalization prompt."""
    return dump_prompt_input(prompt_input)
