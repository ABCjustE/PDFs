from __future__ import annotations

import json

from pdfzx.partitioning.generalize import generalize_taxonomy_bag
from pdfzx.prompts.taxonomy_partition_generalize import TAXONOMY_PARTITION_GENERALIZE_PROMPT_VERSION
from pdfzx.prompts.taxonomy_partition_generalize import TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
from pdfzx.prompts.taxonomy_partition_generalize import TaxonomyPartitionGeneralizePromptInput
from pdfzx.prompts.taxonomy_partition_generalize import TaxonomyPartitionGeneralizeProposal
from pdfzx.prompts.taxonomy_partition_generalize import TaxonomyPartitionGeneralizeResponse
from pdfzx.prompts.taxonomy_partition_generalize import (
    build_taxonomy_partition_generalize_user_prompt,
)
from pdfzx.prompts.taxonomy_partition_proposal import TaxonomyPartitionSupportingGroup


class _FakeParsedResponse:
    def __init__(self, parsed) -> None:
        self.output_parsed = parsed


class _FakeResponsesAPI:
    def __init__(self, parsed) -> None:
        self._parsed = parsed

    def parse(self, **_kwargs):
        return _FakeParsedResponse(self._parsed)


class _FakeClient:
    def __init__(self, parsed) -> None:
        self.responses = _FakeResponsesAPI(parsed)


def test_taxonomy_partition_generalize_prompt_user_payload_is_json() -> None:
    payload = build_taxonomy_partition_generalize_user_prompt(
        TaxonomyPartitionGeneralizePromptInput(
            category_limit=6,
            ancestor_names=["Computer Science"],
            proposals=[
                TaxonomyPartitionGeneralizeProposal(
                    categories=["Computer Science", "Mathematics"], supporting=[]
                )
            ],
        )
    )

    decoded = json.loads(payload)
    assert decoded["category_limit"] == 6
    assert decoded["ancestor_names"] == ["Computer Science"]
    assert decoded["proposals"][0]["categories"] == ["Computer Science", "Mathematics"]


def test_taxonomy_partition_generalize_prompt_constants_are_defined() -> None:
    assert TAXONOMY_PARTITION_GENERALIZE_PROMPT_VERSION == "v9"
    assert "merging multiple taxonomy JSON proposals" in (
        TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
    )
    assert "return JSON with `categories` and `supporting`" in (
        TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
    )
    assert "use supporting topics as evidence" in (TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT)
    assert "if `category_limit` is smaller, choose broader categories" in (
        TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
    )
    assert "do not keep a weak standalone category" in (TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT)
    assert "fold small hobby, maker, or miscellaneous edge pockets" in (
        TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
    )
    assert "do not return any name from `ancestor_names` as a final category" in (
        TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
    )


def test_generalize_taxonomy_bag_filters_categories_and_topics_in_ancestor_scope() -> None:
    fake_client = _FakeClient(
        TaxonomyPartitionGeneralizeResponse(
            categories=["Computer Science", "Systems"],
            supporting=[
                TaxonomyPartitionSupportingGroup(
                    category="Computer Science", topics=["Algorithms", "Computer Science"]
                ),
                TaxonomyPartitionSupportingGroup(
                    category="Systems", topics=["Computer Science", "Operating Systems"]
                ),
            ],
        )
    )

    result = generalize_taxonomy_bag(
        proposals=[
            TaxonomyPartitionGeneralizeProposal(
                categories=["Computer Science", "Systems"],
                supporting=[
                    TaxonomyPartitionSupportingGroup(
                        category="Systems", topics=["Operating Systems"]
                    )
                ],
            )
        ],
        ancestor_names=["Computer Science"],
        online_features=True,
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        client=fake_client,
    )

    assert result.parsed_response["categories"] == ["Systems"]
    assert result.parsed_response["supporting"] == [
        {"category": "Systems", "topics": ["Operating Systems"]}
    ]
