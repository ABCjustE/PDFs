"""Final taxonomy-partition generalization prompt runner."""

from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI

from pdfzx.prompts.taxonomy_partition_generalize import TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
from pdfzx.prompts.taxonomy_partition_generalize import TaxonomyPartitionGeneralizePromptInput
from pdfzx.prompts.taxonomy_partition_generalize import TaxonomyPartitionGeneralizeProposal
from pdfzx.prompts.taxonomy_partition_generalize import TaxonomyPartitionGeneralizeResponse
from pdfzx.prompts.taxonomy_partition_generalize import (
    build_taxonomy_partition_generalize_user_prompt,
)


@dataclass(slots=True)
class PartitionGeneralizeResult:
    """Result payload for one taxonomy-partition generalization prompt call."""

    prompt_input: dict[str, object]
    parsed_response: dict[str, object]


def generalize_taxonomy_bag(  # noqa: PLR0913
    *,
    proposals: list[TaxonomyPartitionGeneralizeProposal],
    category_limit: int = 10,
    online_features: bool,
    openai_api_key: str | None,
    openai_model: str,
    client: OpenAI | None = None,
) -> PartitionGeneralizeResult:
    """Call the final taxonomy-partition generalization prompt."""
    if not online_features:
        msg = "PDFZX_ONLINE_FEATURES is disabled"
        raise ValueError(msg)
    if not openai_api_key:
        msg = "PDFZX_OPENAI_API_KEY is required for taxonomy partition generalization"
        raise ValueError(msg)
    prompt_input = TaxonomyPartitionGeneralizePromptInput(
        category_limit=category_limit,
        proposals=proposals,
    )
    response = (client or OpenAI(api_key=openai_api_key)).responses.parse(
        model=openai_model,
        instructions=TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT,
        input=build_taxonomy_partition_generalize_user_prompt(prompt_input),
        text_format=TaxonomyPartitionGeneralizeResponse,
    )
    parsed = response.output_parsed
    if parsed is None:
        msg = "LLM response did not contain a parsed taxonomy generalization payload"
        raise ValueError(msg)
    return PartitionGeneralizeResult(
        prompt_input=prompt_input.model_dump(mode="json"),
        parsed_response=parsed.model_dump(mode="json"),
    )
