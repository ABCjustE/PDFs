# Phase 1 — Current Implementation

Phase 1 is the offline scan and merge layer.
It walks PDFs under the configured root, extracts deterministic document facts, and persists the
merged state to SQLite.

## Scope

- offline only
- library-first execution
- deterministic extraction from local files
- no LLM calls
- no watcher-driven manual file CRUD yet

## Runtime Entry Point

Phase 1 currently runs through `InventoryJob` in `pdfzx/src/pdfzx/__init__.py`.

High-level flow:

1. resolve selected PDF paths under `PDFZX_PDF_ROOT`
2. run `inventory.process_pdf(...)` in `pdfzx/src/pdfzx/inventory.py` for each file
3. merge scanned records through `registry.run(...)` in `pdfzx/src/pdfzx/registry.py`
4. persist through `SqliteStorage` in `pdfzx/src/pdfzx/storage.py`

## Current Persistence Model

SQLite is the normal persistence target for Phase 1.
`db.json` is no longer the live runtime store for scan runs. It remains only as:

- legacy import source
- export format
- compatibility shape for the in-memory `Registry` contract

Current Phase 1 tables:

- `documents`
  - canonical document row keyed by `sha256`
  - stores metadata, names, language list, digital flag, ToC validity fields, and job references
- `document_paths`
  - canonical mapping from `sha256` to current relative paths
  - this is the path table to reason about for future watcher/manual file operations
- `document_toc`
  - ordered ToC entries per document
- `scanned_file_in_job`
  - per-path batch-scan state
  - used by the scan diff/merge logic, not as the main path model
  - legacy JSON key: `file_stats`
- `scan_jobs`
  - one audit row per scan run with aggregate counters
  - legacy JSON key: `jobs`

Phase 2 tables also exist in the same database, but they are outside the Phase 1 scan pipeline.

## What `scanned_file_in_job` Means

- remember what a scan run last saw at a relative path
- support batch diffing in `registry.py`
- let the merge logic decide added / updated / skipped / removed counts

The canonical path mapping is `document_paths`, not `scanned_file_in_job`.
The old JSON registry shape may still use the legacy key `file_stats`; the current bridge accepts
that key for compatibility and serializes the newer name `scanned_files_in_job`.

## What `registry.py` Does

Registry is the bridge concept that combines in-memory state, persistence, and the batch merge algorithm.

`pdfzx/src/pdfzx/registry.py` is the Phase 1 batch diff/merge engine.

It merges freshly scanned `DocumentRecord`s into the existing in-memory `Registry` and records one
`ScanJobRecord`.

Current scan cases:

- new `sha256`
  - add new document state
  - add new `scanned_file_in_job` entry
- known `sha256`, new path
  - treat as another known path for that document
  - count as duplicate
- known `sha256`, path mtime changed
  - refresh `scanned_file_in_job`
  - count as updated
- known `sha256`, same path mtime
  - skip
- path known in previous registry state but not seen in this batch
  - count as removed for the job summary

Important constraint:

- this is still a batch-scan model
- it is not yet the watcher/manual file-operation model

## Pydantic Contract vs SQLite Schema

- `inventory.py` produces `DocumentRecord`
- `registry.py` still merges in-memory `Registry` objects
- `SqliteStorage` bridges between the in-memory contract and SQLite rows

This means Phase 1 currently has two layers:

- in-memory Pydantic registry contract
- SQLite persistence layer

That bridge is intentional for the current stage.

## Phase 1 Boundaries

Phase 1 includes:

- file hashing
- PDF metadata extraction
- ToC extraction
- digital/language heuristics
- deterministic normalized names
- batch scan merge
- SQLite persistence

Phase 1 does not include:

- LLM prompting
- taxonomy proposal or assignment
- watcher-driven manual path reconciliation
- OCR enrichment pipeline design beyond existing extraction flags

## Mental Model

The simplest accurate way to read Phase 1 is:

- `inventory.py` extracts document facts from files
- `registry.py` computes batch scan deltas
- `documents` + `document_paths` are the canonical persisted document state
- `scanned_file_in_job` + `scan_jobs` track scan-run history and diff state
- `db.json` is no longer the normal persistence target
