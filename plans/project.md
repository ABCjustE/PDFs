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
- Maintain a persistent `db.json` registry at the project root

**Document record:**
```json
{
  "file_name": "doc.pdf",
  "sha256": "abc123...",
  "md5": "def456...",
  "paths": ["contracts/doc.pdf"],
  "is_digital": true,
  "languages": ["zh", "en"],
  "metadata": { "title": "", "author": "", "created": "", "modified": "", "creator": "" },
  "toc": [{ "level": 1, "title": "Chapter 1", "page": 1 }],
  "phase2_status": "pending"
}
```

Phase 1 also tracks per-path scan state and per-run job history in the same registry.

### Phase 2 — LLM Enrichment (deferred)

For scanned PDFs (`needs_ocr: true`) only. See `plans/phase2.md`.

Consumes Phase 1 registry records for scanned PDFs and writes enrichment output.
See `plans/phase2.md` for the deferred design.

---

## Repository Structure

```
(to update)
```

---

## Stack

| Concern | Package |
|---------|---------|
| PDF parsing, ToC, metadata, image export | `pymupdf` |
| Language detection | `langdetect` |
| OCR + LLM enrichment (Phase 2) | `openai` (GPT-4o vision) |
| Image handling (Phase 2) | `pillow` |
| Serialisation | `json` + `pydantic` |
| Hashing | `hashlib` (stdlib) |
| Tooling | `uv`, `ruff`, `pytest`, `pytest-asyncio` |

---

## Output Design Principles

- **Schema-stable** — consistent field names/types; consumers must not break across runs
- **Self-describing** — every entry carries enough context to be used in isolation
- **Flat where possible** — nested only where structure is meaningful (toc, extracted_data)
- **NDJSON-compatible** — registry exports can be streamed line-by-line into vector DBs or search indexes
