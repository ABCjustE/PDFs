"""Phase 2 pipeline stub — LLM enrichment for scanned PDFs.

All functions raise NotImplementedError until Phase 2 is implemented.
See plans/phase2.md for the full design.
"""

from __future__ import annotations

from pdfzx.models import DocumentRecord


def enrich(record: DocumentRecord) -> DocumentRecord:
    """Run GPT-4o vision enrichment on a scanned DocumentRecord.

    Args:
        record: A DocumentRecord where ``is_digital`` is False.

    Raises:
        NotImplementedError: Always — Phase 2 feature.
    """
    raise NotImplementedError("Phase 2 LLM enrichment is not yet implemented")  # noqa: EM101
