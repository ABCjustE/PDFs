"""Phase 2 pipeline stub — LLM enrichment for scanned PDFs.

Implementation is deferred; see plans/phase2.md for the full design.
This module intentionally imports nothing from phase 1 (no cross-phase imports).
"""

# TODO Phase 2:
#   load_manifest(path)      → filter scanned + pending records
#   pdf_to_images(path)      → render pages to PIL Images via pymupdf
#   ocr_with_gpt4o(images)   → send images to GPT-4o vision, return text
#   enrich_with_llm(text)    → structured prompt → {summary, tags, extracted_data, …}
#   process_batch(manifest)  → async, semaphore-controlled (default concurrency 5)
