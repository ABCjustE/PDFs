"""Shared fixtures for pdfzx tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pymupdf
import pytest


@pytest.fixture
def make_pdf(tmp_path: Path) -> Callable[[str, list[str]], Path]:
    """Factory: create a PDF with per-page text content (empty string = blank page)."""

    def _make(name: str, page_texts: list[str]) -> Path:
        path = tmp_path / name
        doc = pymupdf.open()
        for text in page_texts:
            page = doc.new_page()
            if text:
                page.insert_text((72, 72), text)
        doc.save(str(path))
        doc.close()
        return path

    return _make


@pytest.fixture
def make_toc_pdf(tmp_path: Path) -> Callable[[str, list[tuple[int, str, int]]], Path]:
    """Factory: create a PDF with a table of contents."""

    def _make(name: str, toc: list[tuple[int, str, int]]) -> Path:
        path = tmp_path / name
        doc = pymupdf.open()
        # Create enough pages for all ToC entries
        max_page = max((p for _, _, p in toc), default=1)
        for _ in range(max_page):
            doc.new_page()
        doc.set_toc(toc)
        doc.save(str(path))
        doc.close()
        return path

    return _make


@pytest.fixture
def pdf_root(tmp_path: Path) -> Path:
    """A temporary directory acting as the scan root."""
    root = tmp_path / "pdf_root"
    root.mkdir()
    return root
