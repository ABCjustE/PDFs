"""Shared pytest fixtures — programmatically generated PDF test files."""

from pathlib import Path

import fitz
import pytest


def _write_pdf(path: Path, text: str | None = None, toc: list | None = None) -> Path:
    """Create a minimal PDF at *path*, optionally with text and a ToC."""
    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 72), text)
    if toc:
        doc.set_toc(toc)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture(scope="session")
def pdf_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("pdfs")


@pytest.fixture(scope="session")
def output_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("output")


@pytest.fixture(scope="session")
def digital_pdf(pdf_dir) -> Path:
    """Single-page PDF with a text layer and a two-entry ToC."""
    return _write_pdf(
        pdf_dir / "digital.pdf",
        text="Hello World. This is a test document in English.",
        toc=[[1, "Introduction", 1], [2, "Details", 1]],
    )


@pytest.fixture(scope="session")
def scanned_pdf(pdf_dir) -> Path:
    """Single blank page — simulates a scanned PDF with no text layer."""
    return _write_pdf(pdf_dir / "scanned.pdf")
