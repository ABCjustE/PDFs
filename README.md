1. select files or folders in `yazi`
2. write the selection to `yazi-choice.txt`
3. run `client.py`

## Setup

Install dependencies:

```bash
uv sync
```

Create your local env file:

```bash
cp .env.example .env
```

Default variables:

```bash
PDFZX_PDF_ROOT=./pdf_root
PDFZX_JSON_DB=./db.json
PDFZX_OCR_CHAR_THRESHOLD=100
PDFZX_OCR_SCAN_PAGES=3
```

If you want Python to see values from `.env`, export them before running:

```bash
set -a
source .env
set +a
```

## Run

Use `yazi` to select files or folders and write the result to an absolute chooser file:

```bash
yazi "$PDFZX_PDF_ROOT" --chooser-file="$(pwd)/yazi-choice.txt"
```

Then run the client:

```bash
uv run python client.py
```

Notes:

- `client.py` reads `./yazi-choice.txt` by default
- `client.py` uses env-backed defaults when available
- if env vars are not exported, `client.py` falls back to repo-local defaults
- `--choice-file`, `--root`, and `--db` can still be overridden explicitly

Example:

```bash
uv run python client.py --choice-file "$(pwd)/yazi-choice.txt"
```

## Test

Run the test suite:

```bash
uv run pytest
```
