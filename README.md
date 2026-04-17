`pdfzx` is a Python library for PDF inventory and enrichment.

It processes a local PDF collection in two phases:

- Phase 1 offline: hash files, extract metadata and ToC, detect digital vs scanned PDFs, normalize
  document names, and persist the registry to SQLite
- Phase 2 online: run prompt-based LLM workflows against the scanned registry to generate reviewable
  suggestions such as document attributes and taxonomy classification

The package is library-first. The repo-level `client.py` is an operator helper for local workflows
such as Yazi selection, migration, export, and single-document LLM probing.

This project is intentionally more rigorous than a one-off filename categorization prompt. If the
goal is only a quick manual hierarchy suggestion, a lightweight prompt over filenames is much
simpler. `pdfzx` exists to keep the slower but more durable parts: persistent scan facts, prompt
provenance, repeatable LLM suggestions, and a review/apply workflow over a large local collection.

1. select files or folders in `yazi` ( which outputs a list of absolute paths)
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
- `PDFZX_PARTITION_SEED`
- `PDFZX_TAXONOMY_EXCLUDE_PATH_KEYWORDS`

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
- `probe-toc-review`
  - run the ToC-review prompt against one document in SQLite
  - judge ToC validity, topical relevance, and likely preface page
- `probe-taxonomy-partition`
  - run the proposal-stage taxonomy partition prompt against one taxonomy node's shuffled batches
  - inspect batch JSON with `categories` and `supporting`
  - supports repeated `--exclude-path-keyword`
- `probe-taxonomy-partition-generalize`
  - run the node-scoped proposal plus generalize flow
  - inspect the merged final JSON with `categories` and `supporting`
  - supports repeated `--exclude-path-keyword`
- `probe-taxonomy-assign`
  - probe one-by-one document assignment under an existing taxonomy node
  - supports repeated `--exclude-path-keyword`
- `run-taxonomy-partition`
  - run taxonomy partitioning on one node path such as `Root` or `Root/Physics`
  - bootstraps `Root` on first use, then persists child nodes on later runs
  - supports repeated `--exclude-path-keyword`
- `run-taxonomy-assign`
  - run one-by-one document assignment under an existing taxonomy node
  - persists `pending` `taxonomy_assignments` rows
  - supports repeated `--exclude-path-keyword`
- `show-taxonomy-assignments`
  - display readable joined assignment rows for one taxonomy node
  - supports filtering by assignment status
- `apply-taxonomy-assignments`
  - move pending high-confidence assignment rows from a parent node into child node memberships
  - supports repeated `--exclude-path-keyword`
- `show-taxonomy-node-stats`
  - display direct document counts grouped by taxonomy node
- `show-taxonomy-node-documents`
  - display one taxonomy node's current document memberships with readable document paths
- `suggest-llm`
  - run document suggestion over a filtered batch and persist results
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
- `probe-toc-review` uses the same ToC cap and keeps suggestions separate from canonical document fields
- `PDFZX_PARTITION_SEED` is the stable seed that future taxonomy-partition batching uses to derive a deterministic document order
- `PDFZX_PARTITION_CHUNK_SIZE` is the default batch size for taxonomy-partition probing
- `PDFZX_TAXONOMY_EXCLUDE_PATH_KEYWORDS` is a comma-separated default exclude list shared by taxonomy partition, assignment, and apply workflows
- taxonomy partitioning command details are documented in [`docs/partitioning.md`](docs/partitioning.md)
- batch suggestion commands support:
  - `--require-digital`
  - `--require-toc`
  - `--limit`
  - `--force`
  - `--max-concurrency`
  - `--output-ndjson`
- batch NDJSON output is appended during the run as each request completes; it is not buffered until the whole batch finishes
- keep `--max-concurrency` low at first; `2` or `4` is a practical starting point if you are near API rate limits
- taxonomy partition commands also support:
  - repeated `--exclude-path-keyword`
- taxonomy assignment commands also support:
  - `--require-digital`
  - `--require-toc`
  - `--limit`
  - `--offset`
  - repeated `--exclude-path-keyword`
- `apply-taxonomy-assignments` also supports:
  - repeated `--exclude-path-keyword`
- taxonomy exclude keywords come from `PDFZX_TAXONOMY_EXCLUDE_PATH_KEYWORDS` by default, and command-line `--exclude-path-keyword` values override that default list for the current command
- `run-taxonomy-assign` also supports:
  - `--force`
  - `--max-concurrency`
  - `--output-ndjson`

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

Probe one shuffled taxonomy-partition batch:

```bash
pdfzx/.venv/bin/python client.py probe-taxonomy-partition --node-path Root
```

Probe three consecutive shuffled batches with batch size 20:

```bash
pdfzx/.venv/bin/python client.py probe-taxonomy-partition --node-path Root --chunk-size 20 --batch-offset 0 --batch-count 3
```

Probe final taxonomy generalization over shuffled batches:

```bash
pdfzx/.venv/bin/python client.py probe-taxonomy-partition-generalize --node-path Root --chunk-size 500 --batch-offset 0 --batch-count 7
```

Run taxonomy partitioning on the root node:

```bash
pdfzx/.venv/bin/python client.py run-taxonomy-partition --node-path Root --chunk-size 500 --batch-offset 0 --batch-count 7
```

Exclude manual path buckets during partition probing or runs:

```bash
pdfzx/.venv/bin/python client.py probe-taxonomy-partition --node-path Root --exclude-path-keyword lectures --exclude-path-keyword archive --exclude-path-keyword inbox --exclude-path-keyword misc
```

Probe taxonomy assignment under the root node:

```bash
pdfzx/.venv/bin/python client.py probe-taxonomy-assign --node-path Root --limit 10 --offset 0 --exclude-path-keyword lectures --exclude-path-keyword archive
```

Run taxonomy assignment over filtered documents under the root node:

```bash
pdfzx/.venv/bin/python client.py run-taxonomy-assign --node-path Root --require-digital --require-toc --limit 100 --offset 0 --max-concurrency 5 --exclude-path-keyword lectures --exclude-path-keyword archive
```

Show readable taxonomy assignment rows:

```bash
pdfzx/.venv/bin/python client.py show-taxonomy-assignments --node-path Root --limit 50 --offset 0
```

Show only pending taxonomy assignment rows:

```bash
pdfzx/.venv/bin/python client.py show-taxonomy-assignments --node-path Root --status pending --limit 50 --offset 0
```

Apply pending high-confidence assignments while excluding manual path buckets:

```bash
pdfzx/.venv/bin/python client.py apply-taxonomy-assignments --node-path Root --minimum-confidence high --exclude-path-keyword lectures --exclude-path-keyword archive --exclude-path-keyword inbox --exclude-path-keyword misc
```

Show direct document counts grouped by taxonomy node:

```bash
pdfzx/.venv/bin/python client.py show-taxonomy-node-stats --depth 1
```

Show one node's current document memberships with readable paths:

```bash
pdfzx/.venv/bin/python client.py show-taxonomy-node-documents --node-path Root/Physics --limit 50 --offset 0
```

For taxonomy assignment, `--output-ndjson` writes one JSON line per item as it completes, including:

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

# Reference projects

  * https://www.getsortio.com/#faqs
