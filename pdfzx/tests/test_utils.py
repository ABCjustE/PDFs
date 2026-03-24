"""Tests for pdfzx.utils."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pymupdf
import pytest

from pdfzx.utils import compute_hashes
from pdfzx.utils import detect_languages
from pdfzx.utils import is_digital
from pdfzx.utils import validate_path

# ── compute_hashes ────────────────────────────────────────────────────────────


def test_compute_hashes_matches_hashlib(tmp_path: Path) -> None:
    payload = (b"pdfzx-test-data-" * 10_000) + b"end"
    f = tmp_path / "sample.bin"
    f.write_bytes(payload)

    hashes = compute_hashes(f)

    assert hashes["sha256"] == hashlib.sha256(payload).hexdigest()
    assert hashes["md5"] == hashlib.md5(payload, usedforsecurity=False).hexdigest()


# ── is_digital ────────────────────────────────────────────────────────────────


def test_is_digital_detects_text_pdf(make_pdf: Callable[[str, list[str]], Path]) -> None:
    path = make_pdf("digital.pdf", ["This page contains extractable text."])
    with pymupdf.open(path) as doc:
        assert is_digital(doc, threshold=10) is True


def test_is_digital_rejects_blank_pages(make_pdf: Callable[[str, list[str]], Path]) -> None:
    path = make_pdf("scanned.pdf", ["", "", ""])
    with pymupdf.open(path) as doc:
        assert is_digital(doc, threshold=1) is False


def test_is_digital_only_checks_first_three_pages(
    make_pdf: Callable[[str, list[str]], Path]
) -> None:
    path = make_pdf("late_text.pdf", ["", "", "", "Text appears too late."])
    with pymupdf.open(path) as doc:
        assert is_digital(doc, threshold=1) is False


# ── detect_languages ──────────────────────────────────────────────────────────


def test_detect_languages_empty_returns_empty() -> None:
    assert detect_languages("   ") == []


def test_detect_languages_english() -> None:
    result = detect_languages(
        "This is an English document about contracts, invoices, and payments."
    )
    assert "en" in result


def test_detect_languages_chinese() -> None:
    result = detect_languages("這是一份中文文件，包含發票、合約與付款資訊。" * 5)
    assert any(lang.startswith("zh") for lang in result)


# ── validate_path ─────────────────────────────────────────────────────────────


def test_validate_path_accepts_nested_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    path = root / "sub" / "doc.pdf"

    assert validate_path(path, root) == path.resolve()


def test_validate_path_rejects_traversal(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError, match="Path escapes root"):
        validate_path(root / ".." / "escape.pdf", root)
