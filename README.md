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
- `PDFZX_ENABLE_NAME_NORMALIZATION`
- `PDFZX_WORKERS`

## Run

`client.py` now has two explicit commands:

- `scan`
  - read the Yazi chooser file and run PDF inventory
- `backfill`
  - update `normalised_name` in the existing `db.json` without rescanning PDFs
  - `normalised_name` is derived from `file_name`, not metadata title
  - the normalized value keeps the `.pdf` suffix so it can be used for rename suggestions

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
- `backfill` updates `normalised_name` for the existing `db.json` without rescanning PDFs
- `PDFZX_ENABLE_NAME_NORMALIZATION=false` disables deterministic name normalization in both scan and backfill flows

Example with explicit args:

```bash
pdfzx/.venv/bin/python client.py scan --choice-file "$(pwd)/yazi-choice.txt" --workers 4
```

Backfill existing registry names only:

```bash
pdfzx/.venv/bin/python client.py backfill
```

## Test

Run the test suite:

```bash
cd pdfzx && uv run pytest
```
