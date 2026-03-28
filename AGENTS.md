Build a PDF process automation service using classic Python packages.

You are a professional programmer and software architect.

# Design Concept

Modular, iterative development with smooth CI.
Concise documentation — high-level principles only, no implementation detail in docs.
Concise comment and elegant code style.
Leveled Logging design.
Best practices,
Testing
Security

# Project

`pdfzx` — a Python library for PDF inventory and enrichment.
Two phases: (1) hash/metadata/classify, (2) LLM enrichment for scanned PDFs.
See `plans/phase2.md` for Phase 2 design. Phase 1 is the current focus.

Execution model: library, not CLI. Invoked by file-watcher or task queue.

# Code Practices

- if can, one-liner, less lines of code
- TDA(Tell, don't ask), KISS (Keep it simple, solid), SOLID, DRY, YAGNI principles
- Prefer composition over inheritance
- One concern per module; no cross-phase imports
- Type hints on all public APIs; Google-style docstrings
- Structured JSON logging via stdlib `logging`; no `print()` in library code
- Errors are logged and surfaced in registry entries — never swallowed silently
- Choose data structures deliberately: `Pydantic` for validated typed records, generators for
  large file iteration, dicts for O(1) hash-keyed registry lookups
- Algorithm complexity matters: hash files via streaming (O(n), constant memory);
  deduplication via hash sets (O(1) lookup); ToC hierarchy via recursive descent, not O(n²) scans

# Code Style Conformance

After any significant code change (new module, refactor, or multi-file edit):

1. Run `uv run ruff check --fix src/ tests/` — apply auto-fixes, then resolve remaining errors manually
2. Run `uv run mypy src/` — all source files must pass strict type checking
3. Use `# type: ignore[<code>]` only for untyped third-party C extensions (e.g. `pymupdf`, `langdetect`); never suppress real type errors
4. Use `[tool.ruff.lint.per-file-ignores]` in `pyproject.toml` for test-specific rule suppressions — not in source files
5. Remove temporary debugging artifacts before finishing a change: no committed `pdb.set_trace()`, demo `raise ValueError(...)`, or commented-out production call paths

# Security

- Credentials via environment variables only — never hardcoded
- `pdf_root/` and `db.json` are gitignored — never commit real content
- Phase 1 is fully offline — no network calls in `inventory.py` or `utils.py`
- Validate input paths against `pdf_dir` to prevent path traversal
