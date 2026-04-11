from __future__ import annotations

import pytest

from pdfzx.partitioning.sampler import chunk_items
from pdfzx.partitioning.sampler import seeded_shuffle


def test_seeded_shuffle_is_stable_for_same_seed() -> None:
    first = seeded_shuffle(["d", "a", "c", "b"], seed="seed-1")
    second = seeded_shuffle(["b", "c", "d", "a"], seed="seed-1")

    assert first == second


def test_seeded_shuffle_changes_with_seed() -> None:
    first = seeded_shuffle(["a", "b", "c", "d"], seed="seed-1")
    second = seeded_shuffle(["a", "b", "c", "d"], seed="seed-2")

    assert first != second


def test_chunk_items_splits_fixed_size_batches() -> None:
    assert chunk_items(["a", "b", "c", "d", "e"], chunk_size=2) == [
        ["a", "b"],
        ["c", "d"],
        ["e"],
    ]


def test_chunk_items_rejects_non_positive_chunk_size() -> None:
    with pytest.raises(ValueError, match="chunk_size must be greater than 0"):
        chunk_items(["a"], chunk_size=0)
