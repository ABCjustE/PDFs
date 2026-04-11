"""Deterministic ordering helpers for taxonomy partitioning."""

from __future__ import annotations

import hashlib


def seeded_shuffle(items: list[str], *, seed: str) -> list[str]:
    """Return a stable seeded shuffle of strings.

    This is the effective shuffle step: sort first, then sort again by a
    seeded hash-derived key.
    """
    sorted_items = sorted(items)
    return sorted(
        sorted_items,
        key=lambda item: _seeded_hash_order_key(item, seed),
    )


def chunk_items(items: list[str], *, chunk_size: int) -> list[list[str]]:
    """Split a list of strings into fixed-size chunks."""
    if chunk_size <= 0:
        msg = "chunk_size must be greater than 0"
        raise ValueError(msg)
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _seeded_hash_order_key(item: object, seed: str) -> str:
    seed_material = f"{seed}:{item}".encode()
    return hashlib.sha256(seed_material).hexdigest()
