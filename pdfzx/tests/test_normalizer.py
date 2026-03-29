"""Tests for normalizer.normalize."""

from __future__ import annotations

import pytest

from pdfzx.normalizer import clean_text
from pdfzx.normalizer import normalize
from pdfzx.normalizer import normalize_file_name
from pdfzx.normalizer import normalize_llm


def test_basic_ascii():
    assert normalize("Hello World") == "Hello World"


def test_replaces_non_alnum_runs_with_spaces():
    assert normalize('file<>:"/\\|?*name') == "File Name"


def test_collapses_whitespace():
    assert normalize("lots   of   spaces") == "Lots Of Spaces"


def test_strips_leading_dots():
    assert normalize("...hidden") == "Hidden"


def test_empty_string():
    assert normalize("") == ""


def test_whitespace_only():
    assert normalize("   ") == ""


def test_cjk_name_preserved():
    name = "机器学习基础教程"
    assert normalize(name) == name


def test_long_name_truncated():
    long_name = "A" * 200
    result = normalize(long_name)
    assert len(result) <= 120


def test_long_cjk_truncated():
    long_name = "机" * 200
    result = normalize(long_name)
    assert len(result) <= 120


def test_mixed_illegal_and_whitespace():
    assert normalize("  hello<world>  ") == "Hello World"


def test_strips_path_and_extension():
    assert normalize("nested/My-Book_v2.pdf") == "My Book V2"


def test_normalize_file_name_preserves_pdf_suffix():
    assert normalize_file_name("nested/My-Book_v2.pdf") == "My Book V2.pdf"


def test_clean_text_strips_nulls_and_control_chars():
    assert clean_text("Chap\u0000ter \n One\t") == "Chapter One"


def test_normalize_llm_raises():
    with pytest.raises(NotImplementedError):
        normalize_llm("anything")
