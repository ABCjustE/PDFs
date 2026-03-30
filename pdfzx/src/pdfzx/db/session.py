from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from pdfzx.db.base import Base


def sqlite_url(path: Path) -> str:
    """Build a SQLAlchemy SQLite URL from a filesystem path."""
    return f"sqlite:///{path.resolve()}"


def create_sqlite_engine(path: Path) -> Engine:
    """Create a SQLAlchemy engine for the configured SQLite database."""
    return create_engine(sqlite_url(path), future=True)


def init_sqlite_db(path: Path) -> None:
    """Create all known tables in the target SQLite database if missing."""
    engine = create_sqlite_engine(path)
    Base.metadata.create_all(engine)
    engine.dispose()
