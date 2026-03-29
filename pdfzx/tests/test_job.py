"""Tests for pdfzx.InventoryJob."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pdfzx import InventoryJob
from pdfzx.config import ScanConfig


def _place(src: Path, root: Path, relative_path: str) -> Path:
    destination = root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, destination)
    return destination


@pytest.fixture
def config(pdf_root: Path, tmp_path: Path) -> ScanConfig:
    return ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json")


def test_resolve_expands_directories_and_deduplicates(
    make_pdf, pdf_root: Path, config: ScanConfig
) -> None:
    nested_dir = pdf_root / "nested"
    nested_dir.mkdir()
    first = _place(make_pdf("first.pdf", ["alpha"]), pdf_root, "first.pdf")
    second = _place(make_pdf("second.pdf", ["beta"]), pdf_root, "nested/second.pdf")
    _place(make_pdf("note.txt.pdf", ["gamma"]), pdf_root, "nested/note.txt.pdf")

    job = InventoryJob(root=pdf_root, config=config)
    resolved = job.resolve([pdf_root, nested_dir, first, second])

    assert resolved == sorted(
        {first.resolve(), second.resolve(), (nested_dir / "note.txt.pdf").resolve()}
    )


def test_resolve_rejects_path_outside_root(make_pdf, pdf_root: Path, config: ScanConfig) -> None:
    outside = make_pdf("outside.pdf", ["outside"])

    job = InventoryJob(root=pdf_root, config=config)

    with pytest.raises(ValueError, match="Path escapes configured root"):
        job.resolve([outside])


def test_run_processes_selected_targets(make_pdf, pdf_root: Path, config: ScanConfig) -> None:
    first = _place(make_pdf("first.pdf", ["hello world " * 10]), pdf_root, "first.pdf")
    _place(make_pdf("second.pdf", ["another document " * 10]), pdf_root, "sub/second.pdf")

    job = InventoryJob(root=pdf_root, config=config)
    result = job.run([first, pdf_root / "sub"])

    assert result.stats.added == 2


def test_run_calls_progress_once_per_resolved_file(
    make_pdf, pdf_root: Path, config: ScanConfig
) -> None:
    first = _place(make_pdf("first.pdf", ["hello world " * 10]), pdf_root, "first.pdf")
    second = _place(make_pdf("second.pdf", ["another document " * 10]), pdf_root, "sub/second.pdf")
    seen: list[Path] = []

    job = InventoryJob(root=pdf_root, config=config)
    job.run([pdf_root], on_progress=seen.append)

    assert seen == sorted([first.resolve(), second.resolve()])


def test_run_skips_invalid_pdf_and_continues(make_pdf, pdf_root: Path, config: ScanConfig) -> None:
    good_path = _place(make_pdf("good.pdf", ["valid pdf content " * 10]), pdf_root, "good.pdf")
    bad_path = pdf_root / "bad.pdf"
    bad_path.write_text("not a pdf", encoding="utf-8")

    job = InventoryJob(root=pdf_root, config=config)
    result = job.run([good_path, bad_path])

    assert result.stats.added == 1


def test_run_assigns_normalised_name(make_pdf, pdf_root: Path, config: ScanConfig) -> None:
    path = _place(make_pdf("advanced_python_3rd.pdf", ["hello world " * 10]), pdf_root, "advanced_python_3rd.pdf")

    job = InventoryJob(root=pdf_root, config=config)
    job.run([path])
    registry = job._storage.load()  # noqa: SLF001 - test inspects persisted result

    document = next(iter(registry.documents.values()))
    assert document.normalised_name == "Advanced Python 3rd.pdf"


def test_backfill_normalised_names_updates_existing_registry(
    pdf_root: Path, tmp_path: Path, config: ScanConfig
) -> None:
    config = ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json")
    config.db_path.write_text(
        """
{
  "documents": {
    "abc": {
      "sha256": "abc",
      "md5": "def",
      "paths": ["sample.pdf"],
      "file_name": "advanced_python_3rd.pdf",
      "normalised_name": null,
      "metadata": {},
      "toc": [],
      "languages": [],
      "is_digital": true,
      "first_seen_job": null,
      "last_seen_job": null
    }
  },
  "file_stats": {},
  "jobs": []
}
        """.strip(),
        encoding="utf-8",
    )

    job = InventoryJob(root=pdf_root, config=config)

    assert job.backfill_normalised_names() == 1
    assert job._storage.load().documents["abc"].normalised_name == "Advanced Python 3rd.pdf"  # noqa: SLF001


def test_backfill_uses_file_name_not_metadata_title(
    pdf_root: Path, tmp_path: Path
) -> None:
    config = ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json")
    config.db_path.write_text(
        """
{
  "documents": {
    "abc": {
      "sha256": "abc",
      "md5": "def",
      "paths": ["sample.pdf"],
      "file_name": "advanced_python_3rd.pdf",
      "normalised_name": null,
      "metadata": {"title": "Completely Different Metadata Title"},
      "toc": [],
      "languages": [],
      "is_digital": true,
      "first_seen_job": null,
      "last_seen_job": null
    }
  },
  "file_stats": {},
  "jobs": []
}
        """.strip(),
        encoding="utf-8",
    )

    job = InventoryJob(root=pdf_root, config=config)

    assert job.backfill_normalised_names() == 1
    assert job._storage.load().documents["abc"].normalised_name == "Advanced Python 3rd.pdf"  # noqa: SLF001
