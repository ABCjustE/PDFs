## Textual CLI

### What

`textual_cli.py` is the interactive terminal client for Phase 1 inventory.

It is not part of the `pdfzx` library API. It is an operator-facing wrapper that:

- loads a Yazi chooser file
- previews resolved PDF paths
- asks for confirmation
- runs the inventory job
- shows live logs and progress in a Textual UI

The library boundary stays in `pdfzx`. The Textual app is only a client around that library and the existing `client.py` script.

### Why

The Textual client exists to give a better operator workflow than a plain shell command:

- inspect what Yazi selected before running
- avoid accidental execution
- see progress and logs in one screen
- keep the library free of TUI concerns

The actual run path is intentionally delegated to `client.py`, not executed directly inside the Textual process.

Reason:

- `client.py` is already the known-good execution path
- `InventoryJob.run(..., workers > 1)` is safe there
- starting a `ProcessPoolExecutor` from inside the Textual/background-thread path on macOS caused runtime issues such as `bad value(s) in fds_to_keep`

So the Textual app is a UI shell around the proven subprocess path.

### How

Execution flow:

1. `textual_cli.py` loads `.env` and launches `PdfzxTextualApp`
2. the app opens a modal to choose the Yazi output file
3. raw lines are read from the chooser file
4. `InventoryJob.resolve(...)` expands directories, filters PDFs, validates root safety, and deduplicates targets
5. the resolved PDF list is shown in the table
6. on confirm, the app launches `client.py` as a subprocess
7. `client.py` performs the real inventory run using the configured worker count
8. stderr JSON logs from `client.py` are streamed back into the Textual `RichLog`
9. the progress bar advances from streamed log events
10. stdout JSON from `client.py` is parsed at the end for the final run summary

Progress model:

- the log pane shows the real stdlib/json logs emitted by the run
- progress advances from attempted-file events, not only successful files
- this prevents the progress bar from stalling when a file is skipped due to an extraction error

### Where

Code split:

- [textual_cli.py](/Users/tkingkwun/Development/Github/PDFs/textual_cli.py)
  - thin entrypoint
- [textual_client/app.py](/Users/tkingkwun/Development/Github/PDFs/textual_client/app.py)
  - Textual widgets, event handlers, UI state
- [textual_client/screens.py](/Users/tkingkwun/Development/Github/PDFs/textual_client/screens.py)
  - modal choice-file dialog
- [textual_client/runtime.py](/Users/tkingkwun/Development/Github/PDFs/textual_client/runtime.py)
  - subprocess command building
  - stderr log streaming
  - JSON log parsing
  - final summary parsing
- [textual_client/config.py](/Users/tkingkwun/Development/Github/PDFs/textual_client/config.py)
  - `.env` loading
  - default root/db/workers/log-level
  - Textual log paths
  - choice-file path
  - client script/cwd overrides
- [client.py](/Users/tkingkwun/Development/Github/PDFs/client.py)
  - actual run worker used by the Textual client

Logs:

- `PDFZX_TEXTUAL_DEBUG_LOG`
  - app-internal breadcrumbs
- `PDFZX_TEXTUAL_APP_LOG`
  - persistent copy of streamed stdlib/json run logs

### Notes

- `textual_simple.py` is the smaller verification client
- `textual_cli.py` is the richer operator client
- both now follow the same basic idea: use Textual for interaction, keep the real inventory execution in the proven client/library path
