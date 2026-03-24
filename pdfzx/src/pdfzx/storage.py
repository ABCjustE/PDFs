"""Persistence layer — JSON read/write behind a Storage Protocol."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol
from typing import runtime_checkable

from pydantic import ValidationError

from pdfzx.models import Registry

logger = logging.getLogger(__name__)


@runtime_checkable
class Storage(Protocol):
    """Minimal persistence contract — load and save a Registry."""

    def load(self) -> Registry:
        """Load Registry from storage."""
        ...

    def save(self, registry: Registry) -> None:
        """Persist Registry to storage."""
        ...


class JsonStorage:
    """Registry persistence backed by a single JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Registry:
        """Load and validate Registry from JSON; return empty Registry if file absent.

        Raises:
            ValueError: If the file exists but contains invalid JSON or schema errors.
        """
        if not self._path.exists():
            logger.debug("db not found, starting empty", extra={"path": str(self._path)})
            return Registry()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            msg = f"Corrupt JSON at {self._path}: {exc}"
            logger.exception(msg)
            raise ValueError(msg) from exc
        try:
            registry = Registry.model_validate(data)
        except ValidationError as exc:
            msg = f"Schema validation failed for {self._path}: {exc}"
            logger.exception(msg)
            raise ValueError(msg) from exc
        logger.debug("loaded db", extra={"path": str(self._path), "docs": len(registry.documents)})
        return registry

    def save(self, registry: Registry) -> None:
        """Serialise Registry to JSON (pretty-printed, UTF-8).

        Raises:
            OSError: If the file cannot be written.
        """
        self._path.write_text(registry.model_dump_json(indent=2), encoding="utf-8")
        logger.debug("saved db", extra={"path": str(self._path), "docs": len(registry.documents)})
