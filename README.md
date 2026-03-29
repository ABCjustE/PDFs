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

## Run

`client.py` now has four explicit commands:

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

## Test

Run the test suite:

```bash
cd pdfzx && uv run pytest
```
