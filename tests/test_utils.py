"""Tests for pdfzx.utils — stream_hash, is_digital, detect_languages."""


import fitz

from pdfzx.utils import detect_languages, is_digital, stream_hash

# ── stream_hash ───────────────────────────────────────────────────────────────


def test_stream_hash_returns_hex_strings(digital_pdf):
    sha256, md5 = stream_hash(digital_pdf)
    assert len(sha256) == 64
    assert len(md5) == 32
    assert all(c in "0123456789abcdef" for c in sha256 + md5)


def test_stream_hash_deterministic(digital_pdf):
    assert stream_hash(digital_pdf) == stream_hash(digital_pdf)


def test_stream_hash_differs_for_different_files(digital_pdf, scanned_pdf):
    assert stream_hash(digital_pdf) != stream_hash(scanned_pdf)


def test_stream_hash_empty_file(tmp_path):
    empty = tmp_path / "empty.bin"
    empty.write_bytes(b"")
    sha256, md5 = stream_hash(empty)
    # Known hashes for zero-byte input
    assert sha256 == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert md5 == "d41d8cd98f00b204e9800998ecf8427e"


# ── is_digital ────────────────────────────────────────────────────────────────


def test_is_digital_true_for_text_pdf(digital_pdf):
    with fitz.open(digital_pdf) as doc:
        assert is_digital(doc) is True


def test_is_digital_false_for_blank_pdf(scanned_pdf):
    with fitz.open(scanned_pdf) as doc:
        assert is_digital(doc) is False


# ── detect_languages ─────────────────────────────────────────────────────────


def test_detect_languages_english(digital_pdf):
    with fitz.open(digital_pdf) as doc:
        langs = detect_languages(doc)
    assert "en" in langs


def test_detect_languages_empty_returns_empty_list(scanned_pdf):
    with fitz.open(scanned_pdf) as doc:
        assert detect_languages(doc) == []


def test_detect_languages_returns_sorted_list(digital_pdf):
    with fitz.open(digital_pdf) as doc:
        langs = detect_languages(doc)
    assert langs == sorted(langs)
