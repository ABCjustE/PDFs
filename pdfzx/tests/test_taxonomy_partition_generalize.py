from __future__ import annotations

import json

from pdfzx.prompts.taxonomy_partition_generalize import TAXONOMY_PARTITION_GENERALIZE_PROMPT_VERSION
from pdfzx.prompts.taxonomy_partition_generalize import TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
from pdfzx.prompts.taxonomy_partition_generalize import TaxonomyPartitionGeneralizePromptInput
from pdfzx.prompts.taxonomy_partition_generalize import TaxonomyPartitionGeneralizeProposal
from pdfzx.prompts.taxonomy_partition_generalize import (
    build_taxonomy_partition_generalize_user_prompt,
)


def test_taxonomy_partition_generalize_prompt_user_payload_is_json() -> None:
    payload = build_taxonomy_partition_generalize_user_prompt(
        TaxonomyPartitionGeneralizePromptInput(
            category_limit=6,
            proposals=[
                TaxonomyPartitionGeneralizeProposal(
                    categories=["Computer Science", "Mathematics"],
                    supporting=[],
                )
            ],
        )
    )

    decoded = json.loads(payload)
    assert decoded["category_limit"] == 6
    assert decoded["proposals"][0]["categories"] == ["Computer Science", "Mathematics"]


def test_taxonomy_partition_generalize_prompt_constants_are_defined() -> None:
    assert TAXONOMY_PARTITION_GENERALIZE_PROMPT_VERSION == "v8"
    assert "merging multiple taxonomy JSON proposals" in (
        TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
    )
    assert "return JSON with `categories` and `supporting`" in (
        TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
    )
    assert "use supporting topics as evidence" in (
        TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
    )
    assert "if `category_limit` is smaller, choose broader categories" in (
        TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
    )
    assert "do not keep a weak standalone category" in (
        TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
    )
    assert "fold small hobby, maker, or miscellaneous edge pockets" in (
        TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
    )
