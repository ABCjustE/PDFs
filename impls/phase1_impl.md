# Phase 1 — Implementation Status

## Completed Steps

### Step 1 — `models.py` + `config.py`
Stable Pydantic V2 contract for all modules.

**`models.py`**
- `ExtractionStatus(StrEnum)` — pending, skipped, gate_fail, gate_pass, forced, failed
- `PdfMetadata` — title, author, creator, created, modified, extra
- `TocEntry` — level, title, page
- `DocumentRecord` — sha256 (PK), md5, paths[], file_name, normalised_name,
  metadata, toc, languages[], is_digital, extraction_status?, force_extracted,
  first_seen_job?, last_seen_job?
- `FileStatRecord` — rel_path, sha256, size_bytes, mtime, last_scanned_job
- `JobStats` — added, updated, removed, duplicates, skipped
- `JobRecord` — job_id, run_at, root_path, stats
- `Registry` — documents{}, file_stats{}, jobs[]

**`config.py`**
- `ScanConfig` — root_path, db_path, ocr_char_threshold=100, ocr_scan_pages=3,
  fulltext_dir=./pdf_fulltext, extract_text=True
- `get_config()` — reads all `PDFZX_*` env vars including `PDFZX_FULLTEXT_DIR`
  and `PDFZX_EXTRACT_TEXT`, re-reads on every call

**Key decisions:**
- `first_seen_job` / `last_seen_job` are `str | None` — `inventory.py` returns `None`,
  `registry.py` stamps the job ID on merge
- `get_config()` has no cache — caller is responsible for lifecycle
- `ExtractionStatus` uses `StrEnum` (Python 3.11+) — avoids `str, Enum` dual-inheritance

---

### Step 2 — `utils.py`
Four offline pure functions, no state, no PDF-to-record concerns.

- `compute_hashes(path)` — streaming SHA-256 + MD5, O(n) constant memory
- `validate_path(path, root)` — path traversal guard, raises `ValueError`
- `is_digital(doc, threshold, pages=3)` — char count heuristic, pages capped at doc length
- `detect_languages(text)` — langdetect wrapper, `DetectorFactory.seed=0` for determinism

**Key decisions:**
- `extract_metadata`, `extract_toc`, `ocr_pdf` intentionally excluded — belong to
  `inventory.py` and Phase 2 respectively; premature addition would leak API surface
- `pages` is variadic and driven by `ScanConfig.ocr_scan_pages`

---

### Step 3 — `inventory.py`
Single public function `process_pdf(path, root, config) → DocumentRecord`.

- `_extract_metadata(doc)` — maps pymupdf metadata dict to `PdfMetadata`
- `_extract_toc(doc)` — maps pymupdf ToC list to `list[TocEntry]`
- Calls `validate_path`, `compute_hashes`, `is_digital`, `detect_languages`
- `first_seen_job` / `last_seen_job` left as `None` — registry stamps on merge
- Errors logged and re-raised, never swallowed

**Key decisions:**
- ToC titles are cleaned during extraction via `normalizer.clean_text()` so embedded nulls,
  control characters, and common placeholder artifacts (for example `·` from malformed nulls)
  do not leak into `TocEntry.title`

---

### Step 4 — `normalizer.py`
- `normalize(name)` — deterministic token normalization
- `normalize_file_name(name)` — filename-oriented normalization for `normalised_name`;
  uses `file_name` as input, replaces non-alphanumeric runs with spaces, collapses spaces,
  title-cases tokens, and preserves the `.pdf` suffix for rename use
- `normalize_llm(name, context)` — Phase 2 stub, raises `NotImplementedError`

**Key decisions:**
- `normalised_name` is derived from `file_name`, not `metadata.title`
- `normalised_name` is rename-oriented and keeps the `.pdf` suffix

---

### Step 5 — `storage.py`
- `Storage` Protocol — `load() → Registry`, `save(registry) → None`
- `JsonStorage` — concrete implementation; returns empty `Registry` if file absent;
  raises `ValueError` on corrupt JSON or schema mismatch

---

### Step 6 — `registry.py`
- `merge(registry, records, paths, root, job_id) → (Registry, JobRecord)`
- `run(storage, records, paths, root) → JobRecord` — load → merge → save

**Diff logic (corrected after code review):**

| Case | Action |
|------|--------|
| new sha256 | add `DocumentRecord` + `FileStatRecord` |
| new sha256, path previously held by another doc | remove path from old doc's `paths[]` first |
| known sha256, new path | append to `paths[]`, count as duplicate |
| known sha256, mtime changed | update `FileStatRecord`, count as updated |
| known sha256, same mtime | count as skipped |
| path in db, not in scan | count as removed — **per document** (deduped by sha256), never deleted |

**Key decisions:**
- `removed` is counted once per logical document (sha256), not once per missing path
- Content-change-in-place: old document loses the path before new document is inserted
- `file_stats` is the path-level source of truth for incremental scans: when the same
  `rel_path` keeps the same file name but its PDF bytes change, the old `file_stats[rel_path]`
  entry tells us which previous sha256 owned that path. Merge then reassigns the path from the
  old `DocumentRecord` to the new one and updates `file_stats` to the new sha256/mtime/size

**Example: same path, changed PDF content**

- same `rel_path`
- different file bytes
- therefore different `sha256`
- likely different `mtime` and maybe different `size_bytes`

How `file_stats` is used:

- look up the existing `FileStatRecord` by `rel_path`
- compare current file state with stored state
- if the path is the same but the content hash changed, that path now belongs to a new
  `DocumentRecord`

Flow:

1. scan `sub/doc.pdf`
2. find existing `file_stats["sub/doc.pdf"]`
3. old record says `sha256 = A`
4. current scan produces `sha256 = B`
5. registry updates `file_stats["sub/doc.pdf"]` to `sha256 = B`
6. old document with `sha256 = A` loses that path
7. new/current document with `sha256 = B` owns that path

**Example: moved or removed PDF**

Removed:

- old path exists in `file_stats`
- current scan does not see that `rel_path`
- registry counts it as removed
- old `DocumentRecord` is kept for history; it is not deleted

Moved:

- old path: `a/doc.pdf`
- new path: `b/doc.pdf`
- same bytes, therefore same `sha256`

Flow:

1. previous scan stored `file_stats["a/doc.pdf"]`
2. current scan no longer sees `a/doc.pdf`
3. current scan sees `b/doc.pdf`
4. scanned record for `b/doc.pdf` has the same `sha256` as the old document
5. registry appends `b/doc.pdf` to that existing document's `paths[]`
6. old path is treated as missing/removed
7. new path is treated as another known path for the same logical document

Current interpretation:

- remove = previously known path not seen this run
- move = missing old path + newly seen path with the same `sha256`

This means Phase 1 does not store a first-class "rename" event. It infers moves from
path disappearance plus reappearance of the same content hash at another path.

---

### Step 7 — `__init__.py`
- `configure_logging(level)` — dictConfig JSON formatter to stdout
- `run_inventory(config)` — discovers PDFs via `rglob`, processes each, normalises name,
  runs registry merge; errors per-file are logged and skipped, not fatal

---

### Step 8 — `pipeline.py`
Phase 2 stub only. `enrich(record)` raises `NotImplementedError`.


---

### Step 9 — Polish
- `pyproject.toml` — `TC001` added to ruff ignore (runtime imports); mypy overrides for
  `pymupdf` and `langdetect` (untyped C extensions); `[per-file-ignores]` for test files
- `AGENTS.md` — Code Style Conformance section added

---

## Test Coverage

| File | Tests | Coverage |
|------|-------|----------|
| `models.py` | 14 | 100% |
| `config.py` | 11 | 100% |
| `utils.py` | 10 | 95% |
| `inventory.py` | 10 | 96% |
| `normalizer.py` | 11 | 98% |
| `storage.py` | 8 | 100% |
| `registry.py` | 9 | 100% |

**96 passing, 0 failing, 93% total coverage**

---

## Notes

- pymupdf SWIG `DeprecationWarning` on Python 3.14 — upstream issue, not actionable
- `utils.py` lines 57–58 (`LangDetectException` branch) not covered — acceptable,
  requires deliberately undetectable text to trigger
- `inventory.py` lines 66–68 (pymupdf open exception) not covered — requires a corrupt PDF
- `__init__.py` `run_inventory()` not covered by unit tests — integration-level entrypoint
- `pipeline.py` not covered — Phase 2 stub, deferred

---

## Pending

| Item | Notes |
|------|-------|
| Real-world integration test | Run `run_inventory()` against actual `pdf_root/` symlink |
| `phase1_impl.md` → archive | Move to `plans/phase1_done.md` once integration test passes |
| Phase 2.2 implementation | Review `plans/phase2.md` Part 2 before starting |
