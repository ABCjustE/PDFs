# Project Overview — pdfzx

## What It Is

`pdfzx` is a pure Python ETL library for PDF inventory and enrichment. It takes a local
folder of PDFs as input and produces structured JSON output suitable for downstream
ML, LLM, search, and knowledge base systems.

No daemon, no server, no CLI. Called programmatically by whatever orchestrator the
consumer provides (cron, Airflow, Jupyter, FastAPI, etc.).

---

## Two-Phase Architecture

### Phase 1 — Inventory (current focus)

For every PDF in the input directory:

- Compute SHA-256 + MD5 hashes (streaming, constant memory)
- Extract metadata: title, author, creator, creation/modification dates
- Extract table of contents (recursive hierarchy)
- Detect language(s): Chinese, English, or mixed
- Classify: digital (text layer present) vs scanned (image-only)
- Write a single `output/manifest.json` keyed by SHA-256

**Output record:**
```json
{
  "file_name": "doc.pdf",
  "sha256": "abc123...",
  "md5": "def456...",
  "size_bytes": 1048576,
  "page_count": 42,
  "is_digital": true,
  "languages": ["zh", "en"],
  "metadata": { "title": "", "author": "", "created": "", "modified": "" },
  "toc": [{ "level": 1, "title": "Chapter 1", "page": 1 }],
  "needs_ocr": false,
  "phase2_status": "pending"
}
```

### Phase 2 — LLM Enrichment (deferred)

For scanned PDFs (`needs_ocr: true`) only. See `plans/phase2.md`.

Produces `output/enriched/<sha256>.json` with: OCR text, summary, tags, extracted
structured fields, and translation notes. Uses OpenAI GPT-4o vision.

---

## Repository Structure

```
pdfzx/
├── plans/
│   ├── project.md          # this file
│   └── phase2.md           # Phase 2 LLM design
├── pdfs/                   # input PDFs (gitignored)
├── output/                 # generated output (gitignored)
│   ├── manifest.json
│   └── enriched/
├── src/
│   └── pdfzx/
│       ├── __init__.py     # public API
│       ├── inventory.py    # Phase 1 core
│       ├── pipeline.py     # Phase 2 stub
│       └── utils.py        # hashing, lang detect, digital check
├── tests/
│   ├── fixtures/           # minimal committed PDFs
│   ├── conftest.py
│   ├── test_inventory.py
│   └── test_utils.py
├── pyproject.toml
├── uv.lock
└── .python-version         # 3.14
```

---

## Stack

| Concern | Package |
|---------|---------|
| PDF parsing, ToC, metadata, image export | `pymupdf` |
| Language detection | `langdetect` |
| OCR + LLM enrichment (Phase 2) | `openai` (GPT-4o vision) |
| Image handling (Phase 2) | `pillow` |
| Serialisation | `json` + `dataclasses` (stdlib) |
| Hashing | `hashlib` (stdlib) |
| Tooling | `uv`, `ruff`, `pytest`, `pytest-asyncio` |

---

## Output Design Principles

- **Schema-stable** — consistent field names/types; consumers must not break across runs
- **Self-describing** — every entry carries enough context to be used in isolation
- **Flat where possible** — nested only where structure is meaningful (toc, extracted_data)
- **NDJSON-compatible** — manifest can be streamed line-by-line into vector DBs or search indexes
