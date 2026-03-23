# Phase 2 — LLM Workflow Plan

## Scope

Phase 2 runs only on PDFs where `needs_ocr: true` (scanned/non-digital) and `phase2_status: pending` in `db.json`.

---

## Pipeline per PDF

```
PDF
 └─► [OCR via GPT-4o vision] ─► raw text
       └─► [Chunking] ─► text chunks
             ├─► [Summarizer]  → summary (paragraph, English)
             ├─► [Translator]  → translation notes (if Chinese source)
             ├─► [Extractor]   → structured fields (dates, parties, amounts)
             └─► [Tagger]      → topic tags / category
```

All output is in **English only**.

---

## Deduplication

- Duplicate files (same SHA-256) are tracked as multiple paths on one document record.
- Processing is document-level by SHA-256; duplicate paths do not trigger duplicate Phase 2 work.

---

## Output

Each processed PDF writes to `output/enriched/<sha256>.json`:

```json
{
  "summary": "...",
  "tags": ["finance", "contract", "2023"],
  "extracted_data": {
    "dates": [],
    "parties": [],
    "amounts": []
  },
  "translation_notes": "Originally in Chinese"
}
```

`db.json` `phase2_status` field is updated: `pending → processing → done / failed`.

---

## Implementation

### Files

- `src/phase2_pipeline.py` — main orchestration
- `src/utils.py` — shared helpers (chunking, image conversion)

### Key functions

- `load_registry(path)` — filter scanned + pending PDFs
- `pdf_to_images(path)` — render pages to PIL Images via pymupdf
- `ocr_with_gpt4o(images)` — send images to GPT-4o vision endpoint, return text
- `enrich_with_llm(text, file_name)` — single structured prompt, returns JSON
- `process_batch(db_path)` — async, semaphore-controlled (default concurrency: 5)

### Orchestration

- `asyncio` with `asyncio.Semaphore` for concurrency control
- Exponential backoff on OpenAI rate limit errors
- Resumable: re-running skips PDFs already marked `done`

### Chunking strategy

- Chunk by ToC sections if available
- Fallback: ~3000-token sliding windows
- Summarize chunks first, then produce a final meta-summary

---

## LLM Details

- **Provider**: OpenAI GPT-4o
- **Vision**: used for scanned page images (handles CJK fonts natively)
- **Prompt strategy**: single structured prompt requesting all 4 fields (summary, tags, extracted_data, translation_notes) in one call to minimise API usage

### Example system prompt

```
You are a document analyst. Given document text (which may be in Chinese, English, or both),
return a JSON object with the following fields:
- summary: a concise paragraph summary in English
- tags: a list of topic tags in English (max 10)
- extracted_data: { dates: [], parties: [], amounts: [] }
- translation_notes: brief note on source language(s), or null if English only

Respond with valid JSON only.
```

---

## Invocation

Phase 2 remains library-only. It is invoked programmatically by a watcher, worker, or task queue.

---

## Dependencies

```
openai
pymupdf
pillow
tqdm
pyyaml
```
