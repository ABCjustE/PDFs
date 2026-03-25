1. select files or folders in `yazi`
2. write the selection to `yazi-choice.txt`
3. run `client.py`

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

## Run

Use `yazi` to select files or folders and write the result to an absolute chooser file:

```bash
yazi "$PDFZX_PDF_ROOT" --chooser-file="$(pwd)/yazi-choice.txt"
```

Then run the client:

```bash
pdfzx/.venv/bin/python client.py
```

Notes:

- `client.py` reads `.env` automatically — just edit it and run
- `client.py` reads `./yazi-choice.txt` by default
- `--choice-file`, `--root`, `--db`, `--workers`, and `--log-level` can be overridden explicitly

Example with explicit args:

```bash
pdfzx/.venv/bin/python client.py --choice-file "$(pwd)/yazi-choice.txt" --workers 4
```

## Test

Run the test suite:

```bash
cd pdfzx && uv run pytest
```
