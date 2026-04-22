`pdfzx` is a Python library for PDF inventory and enrichment.

It processes a local PDF collection in two phases:

- offline: hash files, extract metadata and ToC, detect digital vs scanned PDFs, normalize
  document names, and persist the registry to SQLite
- online: run prompt-based LLM workflows against the scanned registry to generate reviewable
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
- `migrate-sqlite` imports offline inventory data from `PDFZX_JSON_DB` into the current SQLite schema
- if you reset `db.sqlite3`, run `alembic upgrade head` before importing data

## Operator Workflows

### First-Time Setup

Goal: create the SQLite schema and import existing registry data.

```bash
uv run alembic upgrade head
```

### Offline Inventory

Goal: scan selected PDFs and update the registry.

```bash
yazi "$PDFZX_PDF_ROOT" --chooser-file="$(pwd)/yazi-choice.txt"
uv run python client.py scan
```

Check:

```bash
uv run python client.py show-duplicate-docs
```

Related cleanup:

```bash
uv run python client.py delete-document-paths --input to_del.txt
```

Use this when:

- adding new PDFs to the registry
- refreshing metadata and scan-state after local file changes
- cleaning duplicate paths for the same document hash

### Registry Maintenance

Goal: maintain deterministic registry fields without rescanning PDFs.

```bash
uv run python client.py backfill
uv run python client.py export-json
```

Use this when:

- `normalised_name` logic changes
- you want a readable JSON snapshot of the current SQLite registry

### Single-Document LLM Probing

Goal: inspect one prompt request and response before running a batch.

```bash
uv run python client.py probe-llm --sha256 <sha256>
uv run python client.py probe-toc-review --sha256 <sha256>
```

Persist only when the result is worth keeping:

```bash
uv run python client.py probe-llm --sha256 <sha256> --persist
```

Use this when:

- testing prompt behavior
- checking one document before spending tokens on a batch
- verifying `prompt_input` and `parsed_response`

### Batch LLM Suggestions

Goal: run LLM workflows over filtered documents and persist reviewable suggestions.

```bash
uv run python client.py suggest-llm --require-digital --require-toc --limit 50
uv run python client.py suggest-toc-review --require-digital --limit 50
```

Useful controls:

```bash
--limit 100
--max-concurrency 2
--output-ndjson ndjsons/run.ndjson
--force
```

Use this when:

- the single-document probe looks good
- you want persisted suggestions for later review
- you want NDJSON traces for prompt debugging

### Taxonomy Bootstrapping

Goal: create the taxonomy root and inspect current tree state.

```bash
uv run python client.py bootstrap-taxonomy-root
uv run python client.py show-taxonomy-node-stats
uv run python client.py show-taxonomy-node-documents --node-path Root --limit 50
```

Use this when:

- starting taxonomy work for the first time
- checking whether documents are attached to `Root`
- checking document counts by node

### Taxonomy Partitioning

Goal: create child categories for one taxonomy node.

First probe the proposed categories:

```bash
uv run python client.py probe-taxonomy-partition --node-path Root --chunk-size 50 --batch-offset 0 --batch-count 1
```

Then probe the merged category result:

```bash
uv run python client.py probe-taxonomy-partition-generalize --node-path Root --chunk-size 500 --batch-offset 0 --batch-count 3
```

Then persist child nodes:

```bash
uv run python client.py run-taxonomy-partition --node-path Root --chunk-size 500 --batch-offset 0 --batch-count 3
```

Check:

```bash
uv run python client.py show-taxonomy-node-stats --depth 1
uv run python client.py show-taxonomy-node-terms
```

Use this when:

- a node has too many documents
- you want broad child categories plus review terms
- you want to manually adjust child nodes before assignment

### Taxonomy Assignment

Goal: assign documents from a parent node into existing child nodes.

Probe first:

```bash
uv run python client.py probe-taxonomy-assign --node-path Root --limit 10 --offset 0
```

Run and persist pending assignments:

```bash
uv run python client.py run-taxonomy-assign --node-path Root --limit 100 --offset 0 --max-concurrency 2
```

Review:

```bash
uv run python client.py show-taxonomy-assignments --node-path Root --status pending --limit 50
```

Apply:

```bash
uv run python client.py apply-taxonomy-assignments --node-path Root --minimum-confidence high
```

Check:

```bash
uv run python client.py show-taxonomy-node-stats
uv run python client.py show-taxonomy-node-documents --node-path Root/SomeChild --limit 50
```

Use this when:

- child nodes already exist
- assignment prompt behavior has been probed
- you want a review/apply step instead of direct movement

### File Watching

Goal: observe filesystem changes under `PDFZX_PDF_ROOT`.

```bash
uv run python client.py watch
```

Use this when:

- studying raw and routed file events
- preparing manual file-operation reconciliation
- validating watcher behavior before wiring more state transitions

### Review Commands

Use these to inspect the system before and after each workflow:

```bash
uv run python client.py show-duplicate-docs
uv run python client.py show-taxonomy-node-stats
uv run python client.py show-taxonomy-node-documents --node-path Root --limit 50
uv run python client.py show-taxonomy-node-terms
uv run python client.py show-taxonomy-assignments --node-path Root --status pending
```

### Recommended Order

For a new or restored local registry:

1. `alembic upgrade head` — make sure the SQLite schema matches the current code.
2. `migrate-sqlite --replace` — import the JSON registry into SQLite; back up the DB first if you are not sure.
3. `scan` — refresh offline inventory facts from selected PDFs.
4. `show-duplicate-docs` — inspect documents whose `sha256` has multiple paths.
5. `delete-document-paths` — remove duplicate path rows and matching files after review.
6. `bootstrap-taxonomy-root` — create `Root` and attach current document hashes.
7. `probe-taxonomy-partition` — inspect the proposal-stage LLM output before persisting child nodes.
8. `probe-taxonomy-partition-generalize` — inspect the merged category output across batches.
9. `run-taxonomy-partition` — persist child taxonomy nodes from the merged result.
10. Manually review or adjust child nodes if needed before assignment.
11. `probe-taxonomy-assign` — inspect document-to-child assignment LLM output before persisting rows.
12. `run-taxonomy-assign` — persist pending assignment rows for review.
13. `show-taxonomy-assignments` — review pending, applied, rejected, or manually touched assignments.
14. `apply-taxonomy-assignments` — apply reviewed pending assignments into node memberships.

## Command Reference

Use help for the full command and flag list:

```bash
uv run python client.py --help
uv run python client.py <command> --help
```

Key docs:

- duplicate inspection and cleanup: [`docs/duplicates_show_delete.md`](docs/duplicates_show_delete.md)
- LLM workflow behavior: [`docs/llm_workflows.md`](docs/llm_workflows.md)
- taxonomy partition and assignment: [`docs/partitioning.md`](docs/partitioning.md)

Common command groups:

- registry: `migrate-sqlite`, `scan`, `backfill`, `export-json`
- duplicate cleanup: `show-duplicate-docs`, `delete-document-paths`
- LLM suggestions: `probe-llm`, `suggest-llm`, `probe-toc-review`, `suggest-toc-review`
- taxonomy partitioning: `bootstrap-taxonomy-root`, `probe-taxonomy-partition`, `probe-taxonomy-partition-generalize`, `run-taxonomy-partition`
- taxonomy assignment: `probe-taxonomy-assign`, `run-taxonomy-assign`, `show-taxonomy-assignments`, `apply-taxonomy-assignments`
- taxonomy inspection: `show-taxonomy-node-stats`, `show-taxonomy-node-documents`, `show-taxonomy-node-terms`
- filesystem observation: `watch`

LLM commands require:

- `PDFZX_ONLINE_FEATURES=true`
- `PDFZX_OPENAI_API_KEY`

Useful shared controls:

- batch commands support `--limit`, `--force`, `--max-concurrency`, and `--output-ndjson`
- taxonomy commands support repeated `--exclude-path-keyword`
- `PDFZX_TAXONOMY_EXCLUDE_PATH_KEYWORDS` provides the default taxonomy exclude list

## Test

Run the test suite:

```bash
cd pdfzx && uv run pytest
```

# Reference projects

  * https://www.getsortio.com/#faqs
