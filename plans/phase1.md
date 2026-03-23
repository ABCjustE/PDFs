# Phase 1 — Inventory

## What It Does

Scans a local directory of PDFs (symlinked cloud drive), extracts document metadata,
computes hashes, and maintains a persistent JSON registry at the project root.

Pure ETL library — no CLI, no daemon. Called programmatically.

---

## Modules

| Module | Concern |
|--------|---------|
| `config.py` | Env vars → `ScanConfig` (Pydantic) |
| `models.py` | All Pydantic V2 data models |
| `utils.py` | Hashing, digital check, language detection |
| `inventory.py` | PDF path → `DocumentRecord` (pure extraction, no I/O) |
| `normalizer.py` | Compute `normalised_name` — regex tier 1, LLM stub for Phase 2 |
| `registry.py` | Load db → diff scan → merge → write job record |
| `storage.py` | JSON read/write, swappable to SQLite via Protocol |
| `pipeline.py` | Phase 2 stub |

---

## Data Models

```
ScanConfig        root_path, db_path, ocr_char_threshold

DocumentRecord    sha256 (PK), md5, paths[], file_name, normalised_name,
                  metadata, toc, languages[], is_digital,
                  first_seen_job, last_seen_job, phase2_status

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
   storage.py → load db.json (existing records)
        │
        ▼
   inventory.py → scan root, hash each PDF (mtime-gated), extract metadata/ToC/language
        │
        ▼
   normalizer.py → compute normalised_name per document
        │
        ▼
   registry.py → diff new scan against loaded db:
        new hash          → add DocumentRecord
        known hash, new path   → append to paths[], log duplicate
        known hash, mtime changed → update FileStatRecord, log updated
        known hash, path gone     → flag removed (record kept, never deleted)
        │
        ▼
   storage.py → write db.json + JobRecord
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

---

## Normaliser

- **Tier 1 (Phase 1):** regex rules — strip illegal chars, collapse whitespace,
  CJK-aware truncation, enforce max length. Offline, deterministic.
- **Tier 2 (Phase 2):** LLM prompt — infer canonical name from content.
  Stubbed as `normalize_with_llm()` raising `NotImplementedError`.

---

## Tests

All fixtures generated programmatically via `pymupdf` in `conftest.py` — no committed PDFs.

| File | Covers |
|------|--------|
| `test_config.py` | Env var parsing, missing vars, invalid paths |
| `test_inventory.py` | Metadata, ToC, digital detection, language detection |
| `test_normalizer.py` | Regex rules, CJK names, missing names, long names |
| `test_registry.py` | First scan, incremental, duplicates, removals, mtime-gating |
| `test_storage.py` | Read/write roundtrip, schema validation on load |

---

## Environment Variables

```
PDFZX_ROOT    path to PDF directory (required)
PDFZX_DB      path to db.json output (default: ./output/db.json)
```
