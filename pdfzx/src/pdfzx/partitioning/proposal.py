"""Loop-1 prompt runner for taxonomy partition proposals."""

from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI

from pdfzx.prompts.taxonomy_partition_proposal import TAXONOMY_PARTITION_PROPOSAL_SYSTEM_PROMPT
from pdfzx.prompts.taxonomy_partition_proposal import SampledDocumentSummary
from pdfzx.prompts.taxonomy_partition_proposal import TaxonomyPartitionProposalPromptInput
from pdfzx.prompts.taxonomy_partition_proposal import TaxonomyPartitionProposalResponse
from pdfzx.prompts.taxonomy_partition_proposal import build_taxonomy_partition_proposal_user_prompt


@dataclass(slots=True)
class PartitionProposalResult:
    """Result payload for one partition proposal prompt call."""

    prompt_input: dict[str, object]
    parsed_response: dict[str, object]


def _filter_ancestor_names(
    response: TaxonomyPartitionProposalResponse, *, ancestor_names: list[str]
) -> TaxonomyPartitionProposalResponse:
    blocked = {name.strip().lower() for name in ancestor_names if name.strip()}
    if not blocked:
        return response
    return TaxonomyPartitionProposalResponse(
        categories=[
            category for category in response.categories if category.strip().lower() not in blocked
        ],
        supporting=[
            group.model_copy(
                update={
                    "topics": [
                        topic for topic in group.topics if topic.strip().lower() not in blocked
                    ]
                }
            )
            for group in response.supporting
            if group.category.strip().lower() not in blocked
        ],
    )


def propose_taxonomy_bags(  # noqa: PLR0913
    *,
    batch_index: int,
    chunk_documents: list[SampledDocumentSummary],
    category_limit: int = 10,
    ancestor_names: list[str] | None = None,
    online_features: bool,
    openai_api_key: str | None,
    openai_model: str,
    client: OpenAI | None = None,
) -> PartitionProposalResult:
    """Call the loop-1 taxonomy partition proposal prompt for one node chunk."""
    if not online_features:
        msg = "PDFZX_ONLINE_FEATURES is disabled"
        raise ValueError(msg)
    if not openai_api_key:
        msg = "PDFZX_OPENAI_API_KEY is required for taxonomy partition proposal"
        raise ValueError(msg)
    prompt_input = TaxonomyPartitionProposalPromptInput(
        batch_index=batch_index,
        category_limit=category_limit,
        ancestor_names=ancestor_names or [],
        chunk_documents=chunk_documents,
    )
    response = (client or OpenAI(api_key=openai_api_key, max_retries=0)).responses.parse(
        model=openai_model,
        instructions=TAXONOMY_PARTITION_PROPOSAL_SYSTEM_PROMPT,
        input=build_taxonomy_partition_proposal_user_prompt(prompt_input),
        text_format=TaxonomyPartitionProposalResponse,
    )
    parsed = response.output_parsed
    if parsed is None:
        msg = "LLM response did not contain a parsed partition proposal payload"
        raise ValueError(msg)
    parsed = _filter_ancestor_names(parsed, ancestor_names=prompt_input.ancestor_names)
    return PartitionProposalResult(
        prompt_input=prompt_input.model_dump(mode="json"),
        parsed_response=parsed.model_dump(mode="json"),
    )
