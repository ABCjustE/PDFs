from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from pdfzx.db.base import Base


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve()}"


def create_sqlite_engine(path: Path) -> Engine:
    return create_engine(sqlite_url(path), future=True)


def init_sqlite_db(path: Path) -> None:
    engine = create_sqlite_engine(path)
    Base.metadata.create_all(engine)
    engine.dispose()
