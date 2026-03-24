# Phase 1 — Inventory

## What It Does

Scans a local directory of PDFs (symlinked cloud drive), extracts document metadata,
computes hashes, and maintains a persistent JSON registry at the project root.

Pure ETL library — no CLI, no daemon. Called programmatically.

---

## Modules

| Module | Concern |
|--------|---------|
| `models.py` | All Pydantic V2 data models — stable contract for all modules |
| `config.py` | Env vars → `ScanConfig` (Pydantic) |
| `utils.py` | Path validation, streaming hashing, digital check, language detection |
| `inventory.py` | PDF path → `DocumentRecord` (pure extraction, no I/O, no state) |
| `normalizer.py` | Compute `normalised_name` — regex tier 1, LLM stub for Phase 2 |
| `storage.py` | JSON read/write behind a `Storage` Protocol, schema validation on load |
| `registry.py` | Load db → diff scan → merge → emit `JobRecord` |
| `__init__.py` | `run_inventory()` entrypoint, JSON logging setup |
| `pipeline.py` | Phase 2 stub only |

---

## Data Models

```
ScanConfig        root_path, db_path, ocr_char_threshold

DocumentRecord    sha256 (PK), md5, paths[], file_name, normalised_name,
                  metadata, toc, languages[], is_digital,
                  first_seen_job?, last_seen_job?

FileStatRecord    rel_path (PK), sha256, size_bytes, mtime, last_scanned_job

JobRecord         job_id, run_at, root_path, added, updated, removed, duplicates
```

---

## Scan Flow

```
env: PDFZX_ROOT, PDFZX_DB
        │
        ▼
   config.py → ScanConfig
        │
        ▼
   storage.py → load db.json (existing records keyed by sha256)
        │
        ▼
   inventory.py → scan root, hash each PDF (mtime-gated), extract metadata/ToC/language
        │
        ▼
   normalizer.py → compute normalised_name per document
        │
        ▼
   registry.py → diff new scan against loaded db:
        new hash               → add DocumentRecord (remove path from old doc if path existed)
        known hash, new path   → append to paths[], log duplicate
        known hash, mtime ≠    → update FileStatRecord, log updated
        known hash, same mtime → skip
        known hash, path gone  → flag removed per document (not per path), record kept
        │
        ▼
   storage.py → write db.json + JobRecord
        │
        ▼
   __init__.py → structured JSON log summary
```

---

## Key Decisions

| Concern | Decision |
|---------|----------|
| Document identity | SHA-256 as PK — content-based, path-independent |
| Duplicates | One `DocumentRecord` per hash, `paths[]` lists all known locations |
| Incremental scan | mtime-gated — skip re-hashing unchanged files |
| Removed files | Flagged via `last_seen_job`, never deleted from registry |
| File renaming | Never — `normalised_name` is a computed field only |
| Storage | JSON now, SQLite later via `Storage` Protocol |
| Validation | Pydantic V2 on all records crossing module boundaries |
| Logging | Structured JSON via stdlib `logging`; configured once in `__init__.py` |
| Errors | Logged and recorded in registry entries — never swallowed silently |

---

## Normaliser

- **Tier 1 (Phase 1):** regex sanitiser — strip illegal chars, collapse whitespace,
  strip leading dots, CJK-aware truncation, max 120 chars. Does **not** strip file
  extensions or path components — caller's responsibility. Original paths preserved
  in `DocumentRecord.paths[]`.
- **Tier 2 (Phase 2):** LLM prompt — infer canonical name from content; stubbed as `NotImplementedError`

---

## Tests

All fixtures generated programmatically via `pymupdf` in `conftest.py` — no committed PDFs.

| File | Covers |
|------|--------|
| `test_models.py` | Validation, field defaults, serialisation roundtrip |
| `test_config.py` | Env var parsing, missing vars, invalid paths, path traversal |
| `test_utils.py` | Streaming hash, digital/scanned detection, language detection |
| `test_inventory.py` | Metadata, ToC, digital detection, CJK language detection |
| `test_normalizer.py` | Regex rules, CJK names, missing names, long names |
| `test_storage.py` | Read/write roundtrip, schema validation, missing file, corrupt JSON |
| `test_registry.py` | First scan, incremental, duplicates, removals, content-change-in-place, mtime-gating |

---

## Implementation Order

1. `models.py` + `config.py` — stable contract
2. `utils.py` — offline pure functions
3. `inventory.py` — pure PDF extraction
4. `normalizer.py` — regex tier 1 + LLM stub
5. `storage.py` — persistence behind Protocol
6. `registry.py` — diff/merge core
7. `__init__.py` — `run_inventory()` + logging setup
8. `pipeline.py` — Phase 2 stub
9. `tests/` — all test files with generated fixtures
10. Polish — pyproject.toml, README, ruff/mypy clean

---

## Environment Variables

```
PDFZX_ROOT    path to PDF directory, e.g. ./pdf_root (required)
PDFZX_DB      path to db.json output (default: ./db.json at project root)
```
