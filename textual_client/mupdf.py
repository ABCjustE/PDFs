from __future__ import annotations

import logging

import pymupdf


def silence_pymupdf_stdout() -> None:
    logger = logging.getLogger("pymupdf")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    pymupdf.set_messages(  # type: ignore[no-untyped-call]
        pylogging=True,
        pylogging_name="pymupdf",
        pylogging_level=logging.WARNING,
    )
