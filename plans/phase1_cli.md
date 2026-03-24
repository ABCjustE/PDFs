# Phase 1 — CLI Layer (`InventoryJob` + `client.py`)

## Problem

`run_inventory()` in `__init__.py` does its own `rglob` internally, so the caller has
no way to specify a subset of files or folders. `client.py` needs to present a fzf picker,
let the user select targets, then hand them to the library for processing — which is
impossible with the current design.

---

## Solution

### 1. Refactor `__init__.py` — introduce `InventoryJob`

Replace `run_inventory()` with a class that separates target resolution from execution.

```python
class InventoryJob:
    def __init__(self, root: Path, config: ScanConfig) -> None: ...

    def resolve(self, targets: list[Path]) -> list[Path]:
        """Expand dirs via rglob, pass files through directly.

        - Deduplicates via set of resolved absolute paths.
        - Validates every resolved path is under root (path traversal guard).
          Paths outside root raise ValueError, aborting the whole job.
        - Returns a sorted flat list of absolute .pdf paths.
        """

    def run(
        self,
        targets: list[Path],
        on_progress: Callable[[Path], None] | None = None,
    ) -> JobRecord:
        """resolve() → process each → registry merge → JobRecord.

        Calls on_progress(path) after each file if provided.
        Per-file errors are logged and skipped — not fatal.
        """
```

Private helper (module-level, not on the class):

```python
def _process_one(path: Path, root: Path, config: ScanConfig) -> DocumentRecord | None:
    ...
```

`__all__ = ["configure_logging", "InventoryJob"]`

`run_inventory()` is removed. `client.py` is the only consumer.

---

### 2. Rewrite `client.py` — `InventoryCLI`

Standalone script at repo root (not inside the library). Uses `rich` for progress and
confirmation; `fzf` for multi-select. Neither is a library dependency.

```python
class InventoryCLI:
    def __init__(self, job: InventoryJob) -> None: ...

    def select(self) -> list[Path]:
        """Present fzf multi-select over all subdirs + PDF files under root.

        Returns the raw selected paths. If the user presses Escape (empty
        selection), prints 'No files selected.' and exits 0 immediately.
        """

    def confirm(self, paths: list[Path]) -> bool:
        """Rich table: filename | size | rel_path.

        Footer: 'N PDFs — proceed? [y/N]'
        """

    def execute(self) -> JobRecord | None:
        """Full flow: select → job.resolve() → confirm → job.run() with rich progress."""
```

fzf candidates: **subdirectories + individual PDF files** under `pdf_root/` — user can
pick folders (all PDFs inside are included) or individual files, or mix both.

---

## Behaviour Contracts

| Scenario | Behaviour |
|----------|-----------|
| Path outside `root` in `resolve()` | `ValueError` raised — whole job aborts |
| Empty fzf selection (Escape) | Print `No files selected.` and `sys.exit(0)` |
| `on_progress` callback | Called with absolute path after each file completes |
| Per-file processing error | Logged, skipped — job continues with remaining files |

---

## Implementation Order

1. Refactor `__init__.py` — replace `run_inventory()` with `InventoryJob`
2. Add/update unit tests for `InventoryJob.resolve()` and `InventoryJob.run()`
3. `ruff` + `mypy` clean
4. Rewrite `client.py` — `InventoryCLI` class
5. Manual integration test against real `pdf_root/`

---

## Tests

All new tests follow existing patterns: fixtures generated via `pymupdf` in `conftest.py`.

| Test | Covers |
|------|--------|
| `resolve()` with dirs | Expands subdirs recursively, deduplicates |
| `resolve()` with files | Passes through, deduplicates |
| `resolve()` mixed | Dirs + files combined, still deduplicates |
| `resolve()` path traversal | `ValueError` on any path outside root |
| `run()` processes files | Records created, `JobRecord` returned |
| `run()` on_progress callback | Called once per file |
| `run()` per-file error | Error logged, remaining files processed |

`client.py` is not unit-tested — it is integration-only (fzf + real filesystem).

---

## Dependencies

| Package | Where | Already present |
|---------|-------|-----------------|
| `rich` | `client.py` only | No — install manually, not in `pyproject.toml` |
| `fzf` | `client.py` only | Yes (brew) |
| `pdfzx` | `client.py` | Yes (editable install via `uv`) |
