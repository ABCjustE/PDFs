"""Tests for registry.merge and registry.run."""

from __future__ import annotations

import shutil
from pathlib import Path

from pdfzx.config import ScanConfig
from pdfzx.inventory import process_pdf
from pdfzx.models import Registry
from pdfzx.registry import merge
from pdfzx.registry import run
from pdfzx.storage import JsonStorage

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _place(src: Path, root: Path, name: str | None = None) -> Path:
    dest = root / (name or src.name)
    shutil.copy(src, dest)
    return dest


def _config(pdf_root: Path, tmp_path: Path) -> ScanConfig:
    return ScanConfig(root_path=pdf_root, db_path=tmp_path / "db.json")


def _scan(paths: list[Path], root: Path, config: ScanConfig) -> list:
    return [process_pdf(p, root, config) for p in paths]


# ---------------------------------------------------------------------------
# merge: first scan
# ---------------------------------------------------------------------------


def test_first_scan_adds_document(make_pdf, pdf_root, tmp_path):
    config = _config(pdf_root, tmp_path)
    path = _place(make_pdf("a.pdf", ["hello"]), pdf_root)
    records = _scan([path], pdf_root, config)

    registry, job = merge(Registry(), records, [path], pdf_root, "job1")

    assert len(registry.documents) == 1
    doc = next(iter(registry.documents.values()))
    assert doc.first_seen_job == "job1"
    assert doc.last_seen_job == "job1"
    assert job.stats.added == 1
    assert job.stats.duplicates == 0


def test_first_scan_creates_file_stat(make_pdf, pdf_root, tmp_path):
    config = _config(pdf_root, tmp_path)
    path = _place(make_pdf("b.pdf", ["world"]), pdf_root)
    records = _scan([path], pdf_root, config)

    registry, _ = merge(Registry(), records, [path], pdf_root, "job1")

    assert "b.pdf" in registry.file_stats


# ---------------------------------------------------------------------------
# merge: incremental — unchanged file is skipped
# ---------------------------------------------------------------------------


def test_incremental_unchanged_skipped(make_pdf, pdf_root, tmp_path):
    config = _config(pdf_root, tmp_path)
    path = _place(make_pdf("c.pdf", ["data"]), pdf_root)
    records = _scan([path], pdf_root, config)

    registry, _ = merge(Registry(), records, [path], pdf_root, "job1")
    # second scan, same mtime
    records2 = _scan([path], pdf_root, config)
    _, job2 = merge(registry, records2, [path], pdf_root, "job2")

    assert job2.stats.skipped == 1
    assert job2.stats.updated == 0
    assert job2.stats.added == 0


# ---------------------------------------------------------------------------
# merge: duplicate path (same hash, new path)
# ---------------------------------------------------------------------------


def test_duplicate_path_counted(make_pdf, pdf_root, tmp_path):
    config = _config(pdf_root, tmp_path)
    src = make_pdf("orig.pdf", ["dup content"])
    path1 = _place(src, pdf_root, "copy1.pdf")
    path2 = _place(src, pdf_root, "copy2.pdf")

    records1 = _scan([path1], pdf_root, config)
    registry, _ = merge(Registry(), records1, [path1], pdf_root, "job1")

    records2 = _scan([path2], pdf_root, config)
    _, job2 = merge(registry, records2, [path2], pdf_root, "job2")

    assert job2.stats.duplicates == 1
    sha = next(iter(registry.documents.keys()))
    assert len(registry.documents[sha].paths) == 2


# ---------------------------------------------------------------------------
# merge: removed files
# ---------------------------------------------------------------------------


def test_removed_file_counted(make_pdf, pdf_root, tmp_path):
    config = _config(pdf_root, tmp_path)
    path = _place(make_pdf("gone.pdf", ["bye"]), pdf_root)
    records = _scan([path], pdf_root, config)
    registry, _ = merge(Registry(), records, [path], pdf_root, "job1")

    # second scan with no files
    _, job2 = merge(registry, [], [], pdf_root, "job2")

    assert job2.stats.removed == 1


def test_removed_duplicate_paths_counted_once(make_pdf, pdf_root, tmp_path):
    """A document with two paths that both go missing counts as 1 removal."""
    config = _config(pdf_root, tmp_path)
    src = make_pdf("orig.pdf", ["dup content"])
    path1 = _place(src, pdf_root, "copy1.pdf")
    path2 = _place(src, pdf_root, "copy2.pdf")

    records1 = _scan([path1], pdf_root, config)
    registry, _ = merge(Registry(), records1, [path1], pdf_root, "job1")
    records2 = _scan([path2], pdf_root, config)
    merge(registry, records2, [path2], pdf_root, "job2")

    # both paths now missing
    _, job3 = merge(registry, [], [], pdf_root, "job3")

    assert job3.stats.removed == 1


# ---------------------------------------------------------------------------
# merge: content change on same path (Finding 1 regression)
# ---------------------------------------------------------------------------


def test_content_change_updates_document(make_pdf, pdf_root, tmp_path):
    """Same path, new bytes → new DocumentRecord; old doc loses the path."""
    config = _config(pdf_root, tmp_path)

    # first scan
    path = _place(make_pdf("doc.pdf", ["version one " * 20]), pdf_root)
    records1 = _scan([path], pdf_root, config)
    registry, _ = merge(Registry(), records1, [path], pdf_root, "job1")
    old_sha = next(iter(registry.documents.keys()))

    # overwrite with different content (new hash)
    path.unlink()
    _place(make_pdf("doc.pdf", ["version two " * 20]), pdf_root)
    records2 = _scan([path], pdf_root, config)
    registry, job2 = merge(registry, records2, [path], pdf_root, "job2")

    new_sha = registry.file_stats["doc.pdf"].sha256

    assert new_sha != old_sha, "hash must change after content change"
    assert job2.stats.added == 1
    # old document must no longer claim the path
    assert "doc.pdf" not in registry.documents[old_sha].paths
    # new document owns the path
    assert "doc.pdf" in registry.documents[new_sha].paths
    # file_stats points to the new hash
    assert registry.file_stats["doc.pdf"].sha256 == new_sha


# ---------------------------------------------------------------------------
# run: full integration (load → merge → save)
# ---------------------------------------------------------------------------


def test_run_persists_registry(make_pdf, pdf_root, tmp_path):
    config = _config(pdf_root, tmp_path)
    path = _place(make_pdf("r.pdf", ["run test"]), pdf_root)
    records = _scan([path], pdf_root, config)
    storage = JsonStorage(config.db_path)

    job = run(storage, records, [path], pdf_root)

    assert job.stats.added == 1
    reloaded = storage.load()
    assert len(reloaded.documents) == 1
    assert len(reloaded.jobs) == 1


def test_run_appends_jobs(make_pdf, pdf_root, tmp_path):
    config = _config(pdf_root, tmp_path)
    path = _place(make_pdf("j.pdf", ["jobs"]), pdf_root)
    records = _scan([path], pdf_root, config)
    storage = JsonStorage(config.db_path)

    run(storage, records, [path], pdf_root)
    run(storage, records, [path], pdf_root)

    registry = storage.load()
    assert len(registry.jobs) == 2
