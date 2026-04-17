"""Normalized watcher event models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RawWatchEvent:
    """One normalized raw filesystem event under the watched root."""

    event_class: str
    event_type: str
    src_rel_path: str | None
    dest_rel_path: str | None
    is_synthetic: bool


@dataclass(frozen=True, slots=True)
class CanonicalWatchOperation:
    """One canonical project operation chosen from a raw watch event."""

    operation: str
    src_rel_path: str | None
    dest_rel_path: str | None
    reason: str
