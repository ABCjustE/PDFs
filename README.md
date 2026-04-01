`pdfzx` is a Python library for PDF inventory and enrichment.

It processes a local PDF collection in two phases:

- Phase 1 offline: hash files, extract metadata and ToC, detect digital vs scanned PDFs, normalize document names, and persist the registry to SQLite
- Phase 2 online: run prompt-based LLM workflows against the scanned registry to generate reviewable suggestions such as document attributes and taxonomy classification

The package is library-first. The repo-level `client.py` is an operator helper for local workflows such as Yazi selection, migration, export, and single-document LLM probing.

This project is intentionally more rigorous than a one-off filename categorization prompt. If the goal is only a quick manual hierarchy suggestion, a lightweight prompt over filenames is much simpler. `pdfzx` exists to keep the slower but more durable parts: persistent scan facts, prompt provenance, repeatable LLM suggestions, and a review/apply workflow over a large local collection.

1. select files or folders in `yazi`
2. write the selection to `yazi-choice.txt`
3. run `client.py scan`

## Setup

Install dependencies:

```bash
cd pdfzx && uv sync
```

Create your local env file:

```bash
cp .env.example .env
```

Edit `.env` with your paths. `client.py` loads it automatically via `python-dotenv` — no
manual `source .env` needed.

Important env knobs:

- `PDFZX_PDF_ROOT`
- `PDFZX_JSON_DB`
- `PDFZX_SQLITE3_DB_PATH`
- `PDFZX_ENABLE_NAME_NORMALIZATION`
- `PDFZX_WORKERS`
- `PDFZX_ONLINE_FEATURES`
- `PDFZX_OPENAI_API_KEY`
- `PDFZX_OPENAI_MODEL`
- `PDFZX_LLM_MAX_TOC_ENTRIES`

## Schema

SQLite schema changes are now managed with Alembic.

Typical baseline flow for a fresh or reset SQLite DB:

```bash
cd /path/to/PDFs
uv run alembic upgrade head
cd pdfzx
uv run python ../client.py migrate-sqlite --replace
```

Typical workflow after editing SQLAlchemy models:

```bash
cd /path/to/PDFs
uv run alembic revision --autogenerate -m "describe schema change"
uv run alembic upgrade head
```

Notes:

- Alembic owns schema evolution; runtime code should not mutate SQLite schema implicitly
- `migrate-sqlite` imports Phase 1 inventory data from `PDFZX_JSON_DB` into the current SQLite schema
- if you reset `db.sqlite3`, run `alembic upgrade head` before importing data

## Run

`client.py` now has explicit commands for import, scan, export, and LLM probing:

- `migrate-sqlite`
  - import the legacy `db.json` registry into SQLite
- `scan`
  - read the Yazi chooser file and run PDF inventory
  - writes Phase 1 state to SQLite
- `backfill`
  - update `normalised_name` in the existing SQLite-backed registry without rescanning PDFs
  - `normalised_name` is derived from `file_name`, not metadata title
  - the normalized value keeps the `.pdf` suffix so it can be used for rename suggestions
- `export-json`
  - export the current SQLite-backed registry to a readable JSON snapshot
- `probe-llm`
  - run the document-suggestion prompt against one document in SQLite
  - inspect `prompt_input` and validated `parsed_response`
  - respects the duplicate gate by default
- `probe-taxonomy`
  - run the taxonomy prompt against one document in SQLite
  - classify subject path and document type
- `probe-toc-review`
  - run the ToC-review prompt against one document in SQLite
  - judge ToC validity, topical relevance, and likely preface page
- `suggest-llm`
  - run document suggestion over a filtered batch and persist results
- `suggest-taxonomy`
  - run taxonomy suggestion over a filtered batch and persist results
- `suggest-toc-review`
  - run ToC review over a filtered batch and persist results

Storage roles:

- SQLite (`PDFZX_SQLITE3_DB_PATH`) is now the primary store
- JSON (`PDFZX_JSON_DB`) is used for import/export, not live scan writes

If you already have an old `db.json`, import it first:

```bash
pdfzx/.venv/bin/python client.py migrate-sqlite --replace
```

Use `yazi` to select files or folders and write the result to an absolute chooser file:

```bash
yazi "$PDFZX_PDF_ROOT" --chooser-file="$(pwd)/yazi-choice.txt"
```

Then run the client:

```bash
pdfzx/.venv/bin/python client.py scan
```

Notes:

- `client.py` reads `.env` automatically — just edit it and run
- `client.py` reads `./yazi-choice.txt` by default
- `scan` uses `--choice-file`, `--root`, `--db`, `--workers`, and `--log-level`
- `migrate-sqlite` imports `PDFZX_JSON_DB` into `PDFZX_SQLITE3_DB_PATH`
- `backfill` updates `normalised_name` in SQLite without rescanning PDFs
- `export-json` writes a JSON snapshot from SQLite to `PDFZX_JSON_DB` or `--json-db`
- `PDFZX_ENABLE_NAME_NORMALIZATION=false` disables deterministic name normalization in both scan and backfill flows
- all LLM probe and batch commands require:
  - `PDFZX_ONLINE_FEATURES=true`
  - `PDFZX_OPENAI_API_KEY`
- single-document probes also require:
  - a target document `--sha256`
- `probe-llm --persist` stores the validated suggestion
- `probe-llm --force` bypasses the same-doc same-prompt duplicate gate
- `probe-taxonomy` uses `PDFZX_LLM_MAX_TOC_ENTRIES` to cap ToC evidence sent to the model
- `probe-toc-review` uses the same ToC cap and keeps suggestions separate from canonical document fields
- batch suggestion commands support:
  - `--require-digital`
  - `--require-toc`
  - `--limit`
  - `--force`
  - `--max-concurrency`
  - `--output-ndjson`
- batch NDJSON output is appended during the run as each request completes; it is not buffered until the whole batch finishes
- keep `--max-concurrency` low at first; `2` or `4` is a practical starting point if you are near API rate limits

Example with explicit args:

```bash
pdfzx/.venv/bin/python client.py scan --choice-file "$(pwd)/yazi-choice.txt" --workers 4
```

Backfill existing registry names only:

```bash
pdfzx/.venv/bin/python client.py backfill
```

Export the current SQLite-backed registry to JSON:

```bash
pdfzx/.venv/bin/python client.py export-json
```

Probe one document against the LLM prompt:

```bash
pdfzx/.venv/bin/python client.py probe-llm --sha256 <sha256>
```

Probe and persist one validated suggestion:

```bash
pdfzx/.venv/bin/python client.py probe-llm --sha256 <sha256> --persist
```

Probe one document against the ToC-review prompt:

```bash
pdfzx/.venv/bin/python client.py probe-toc-review --sha256 <sha256>
```

Run taxonomy suggestion for only digital documents that already have ToC:

```bash
pdfzx/.venv/bin/python client.py suggest-taxonomy --require-digital --require-toc --limit 10
```

Write per-document prompt input/output records during a batch run:

```bash
pdfzx/.venv/bin/python client.py suggest-taxonomy --require-digital --require-toc --output-ndjson ./taxonomy.ndjson
```

The NDJSON file grows during the batch run, so it can be tailed while requests are still in flight:

```bash
tail -f ./taxonomy.ndjson
```

Run a small concurrent batch:

```bash
pdfzx/.venv/bin/python client.py suggest-taxonomy --require-digital --require-toc --limit 10 --max-concurrency 4
```

`--output-ndjson` writes one JSON line per candidate document, including:

- `workflow`
- `sha256`
- `status`
- `reason`
- `prompt_input`
- `parsed_response`
- `persisted`

## Test

Run the test suite:

```bash
cd pdfzx && uv run pytest
```
