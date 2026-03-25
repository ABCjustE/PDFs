# MuPDF stdout silencing

## Remark — a general pattern for third-party library logging

This problem is an instance of a wider challenge: **C-extension and native libraries bypass
Python's logging system entirely**, writing directly to stdout/stderr via their own internal
channels. The same pattern recurs whenever you integrate a library that wraps a C/C++ core
(e.g. `opencv`, `tesseract`, `libvips`, `ffmpeg` bindings).

The general solution has two layers:

1. **Silence the raw print channel** — find the library's official API to redirect its
   internal `print`/`fprintf` calls into a Python-controlled sink. For pymupdf this is
   `set_messages(pylogging=True, ...)`. Some libraries expose a callback; others require
   redirecting `sys.stdout` temporarily or using `os.dup2` at the file-descriptor level.

2. **Attach job/file context at the call site** — the library's own logger has no knowledge
   of your application's context (which file is being processed, which job it belongs to).
   The drain pattern here (`JM_mupdf_warnings_store` cleared before each file, flushed after
   each operation) is the idiomatic way to bridge that gap: collect messages during a bounded
   operation, then emit them enriched with `path`, `job_id`, or whatever context matters.

This two-layer approach — silence at the library boundary, enrich at the call site — applies
directly to any native-backed library and keeps your structured log clean and queryable.

---

## Problem

`pymupdf` writes raw `MuPDF error: ...` and `MuPDF warning: ...` lines directly to
`sys.stdout` via its internal `message()` C function. This pollutes structured JSON log
output and cannot be suppressed by setting Python log levels.

## Two independent channels

| Channel | Mechanism | Purpose |
|---|---|---|
| `message()` print | `JM_mupdf_show_errors`, `_g_out_message` | Human-readable raw output to stdout |
| `JM_mupdf_warnings_store` | Process-global Python list | Accumulates all messages regardless of print setting |

Both errors (`JM_mupdf_error`) and warnings (`JM_mupdf_warning`) write to the **same** store —
they are indistinguishable after the fact.

## Solution

### 1. Route `message()` into stdlib logging (once at startup)

```python
pymupdf.set_messages(pylogging=True, pylogging_name="pymupdf", pylogging_level=logging.WARNING)
```

Called in `configure_logging()` (`__init__.py`). Redirects all `message()` calls through the
`pymupdf` stdlib logger, silencing raw stdout permanently. The `pymupdf` logger is left at
WARNING so debug noise is filtered.

### 2. Drain `JM_mupdf_warnings_store` per file (`inventory.py`)

```python
_DEBUG_PREFIXES = ("ignoring ", "font ", "cmap ", "embedded icc")

def _mupdf_level(msg: str) -> int:
    return logging.DEBUG if msg.lower().startswith(_DEBUG_PREFIXES) else logging.WARNING

def _drain_mupdf_store(rel_path: str) -> None:
    store: list[str] = pymupdf.JM_mupdf_warnings_store
    for msg in store:
        logger.log(_mupdf_level(msg), "mupdf", extra={"path": rel_path, "detail": msg})
    store.clear()
```

Called twice per file:
- **After `pymupdf.open()`** — captures xref repair, syntax errors during parse
- **After extraction** (`get_toc`, `get_text`) — captures errors during content extraction

The store is **cleared before `open()`** to discard residue from prior files.

`JM_mupdf_show_errors = 0` is set narrowly around `open()` only (restored in `finally`) as an
extra guard; `set_messages` already handles the print channel but belt-and-suspenders is safe.

## Key findings

- MuPDF errors do **not** raise Python exceptions — MuPDF repairs/skips corrupt structures
  silently; `open()`, `get_toc()`, `get_text()` all succeed with possibly degraded results.
- The store is **process-global** — safe in `ProcessPoolExecutor` (each worker has own memory)
  but must be cleared between files.
- MuPDF warnings fire during **both** `open()` and extraction, not just at open time.
- `set_messages` and `JM_mupdf_warnings_store` are orthogonal — both must be handled.

## Target log output

```json
{"level":"DEBUG",   "logger":"pdfzx.inventory","msg":"mupdf","path":"Books/foo.pdf","detail":"ignoring broken object (12 0 R)"}
{"level":"DEBUG",   "logger":"pdfzx.inventory","msg":"mupdf","path":"Books/foo.pdf","detail":"font missing encoding"}
{"level":"WARNING", "logger":"pdfzx.inventory","msg":"mupdf","path":"Books/foo.pdf","detail":"syntax error: invalid key in dict"}
{"level":"WARNING", "logger":"pdfzx.inventory","msg":"mupdf","path":"Books/foo.pdf","detail":"trying to repair broken xref"}
{"level":"INFO",    "logger":"pdfzx.inventory","msg":"processed","path":"Books/foo.pdf"}
```
