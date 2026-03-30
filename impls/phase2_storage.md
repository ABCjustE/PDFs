# SQLite Storage Cutover — Current State

## What Changed

Primary persistence has moved from `db.json` to SQLite.

Current roles:

- SQLite is the source of truth for Phase 1 scan/backfill state
- JSON is import/export only
- Phase 2 prompt/suggestion tables also live in SQLite
- Alembic is the schema manager for SQLite

## Why

Keeping both `db.json` and SQLite as normal write targets would create drift and duplicated
persistence logic.

SQLite is now the single primary store because it supports:

- Phase 1 inventory persistence
- prompt CRUD
- LLM suggestion persistence
- later review/apply workflows

JSON remains useful as a readable export and as a legacy import source.

## Current Data Model

Implemented ORM tables:

- `documents`
- `document_paths`
- `document_toc`
- `file_stats`
- `jobs`
- `prompts`
- `llm_document_suggestions`
- `llm_taxonomy_suggestions`

Key modeling decisions:

- `sha256` remains the canonical document identity
- path state is separate from document/content state
- nested metadata extras and language lists stay pragmatic as JSON columns
- prompt provenance is relational through `prompt_id`

## How Runtime Works

Phase 1 runtime still preserves the existing `Registry` contract.

Current storage layer:

- `JsonStorage`
  - used for legacy import and JSON export
- `SqliteStorage`
  - current primary runtime storage
  - reconstructs a canonical `Registry` from SQLite
  - saves canonical `Registry` state back into SQLite

This keeps the Phase 1 merge logic stable while the backend persistence moved to relational
storage.

## Migration Path

Implemented flow:

1. create or upgrade SQLite schema with Alembic
2. import legacy `db.json` into SQLite
3. run normal scan/backfill against SQLite
4. export JSON only when a readable snapshot is needed

## Commands

Baseline schema setup:

```bash
cd pdfzx
uv run alembic upgrade head
```

Import legacy JSON into SQLite:

```bash
uv run python ../client.py migrate-sqlite --replace
```

Run Phase 1 scan against SQLite:

```bash
uv run python ../client.py scan
```

Backfill `normalised_name` against SQLite:

```bash
uv run python ../client.py backfill
```

Export the current SQLite state back to JSON:

```bash
uv run python ../client.py export-json
```

## Alembic

Alembic is now the intended schema-evolution path.

Current rule:

- runtime code should not perform implicit SQLite schema mutation
- schema changes should become Alembic revisions

Typical workflow after model changes:

```bash
cd pdfzx
uv run alembic revision --autogenerate -m "describe schema change"
uv run alembic upgrade head
```

## Verification

The current implementation has been verified through:

- JSON to SQLite import tests
- SQLite-backed storage tests
- scan/backfill runtime tests
- real local migration from legacy `db.json`
- Alembic baseline setup against a fresh SQLite database

## Remaining Constraint

Phase 1 persistence is now relational, but the runtime still adapts through full-`Registry`
load/save operations.

That is acceptable for the current cutover.

Longer term, Phase 2 will benefit from moving more logic toward repository/service-style CRUD
instead of treating SQLite as a serialized `Registry`.
