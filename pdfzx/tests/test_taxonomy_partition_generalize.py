from __future__ import annotations

import json

from pdfzx.prompts.taxonomy_partition_generalize import TAXONOMY_PARTITION_GENERALIZE_PROMPT_VERSION
from pdfzx.prompts.taxonomy_partition_generalize import TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
from pdfzx.prompts.taxonomy_partition_generalize import TaxonomyPartitionGeneralizePromptInput
from pdfzx.prompts.taxonomy_partition_generalize import (
    build_taxonomy_partition_generalize_user_prompt,
)


def test_taxonomy_partition_generalize_prompt_user_payload_is_json() -> None:
    payload = build_taxonomy_partition_generalize_user_prompt(
        TaxonomyPartitionGeneralizePromptInput(
            bag_size_limit=6,
            taxonomy_bag_before=["Quantum Mechanics", "Mathematics Analysis"],
            candidate_counts={"Quantum Mechanics": 3, "Physics": 5},
        )
    )

    decoded = json.loads(payload)
    assert decoded["bag_size_limit"] == 6
    assert decoded["candidate_counts"]["Physics"] == 5


def test_taxonomy_partition_generalize_prompt_constants_are_defined() -> None:
    assert TAXONOMY_PARTITION_GENERALIZE_PROMPT_VERSION == "v1"
    assert "final parent-layer bag" in TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
    assert "include Others" in TAXONOMY_PARTITION_GENERALIZE_SYSTEM_PROMPT
