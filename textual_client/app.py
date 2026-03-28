from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import App
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Button
from textual.widgets import DataTable
from textual.widgets import Footer
from textual.widgets import Header
from textual.widgets import ProgressBar
from textual.widgets import RichLog
from textual.widgets import Static

from pdfzx import InventoryJob
from textual_client.config import default_client_cwd
from textual_client.config import default_client_script
from textual_client.config import default_choice_file
from textual_client.config import default_config
from textual_client.config import default_log_level
from textual_client.config import default_textual_app_log
from textual_client.config import default_textual_debug_log
from textual_client.config import default_workers
from textual_client.mupdf import silence_pymupdf_stdout
from textual_client.runtime import build_client_command
from textual_client.runtime import event_path
from textual_client.runtime import is_attempt_event
from textual_client.runtime import parse_json_log_line
from textual_client.runtime import parse_run_summary
from textual_client.screens import ChoiceFileScreen
from textual_client.runtime import stream_client_run


class PdfzxTextualApp(App[None]):
    CSS = """
    #dialog {
        width: 70;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }

    #dialog_title {
        text-style: bold;
        margin-bottom: 1;
    }

    #dialog_help {
        margin-bottom: 1;
    }

    #dialog_buttons {
        width: 100%;
        height: auto;
        margin-top: 1;
    }

    #status {
        padding: 0 1;
        height: auto;
    }

    #confirm_bar {
        height: auto;
        padding: 0 1;
    }

    #confirm_message {
        margin-right: 1;
    }

    #paths_table {
        height: 1fr;
    }

    #run_log {
        height: 50%;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("l", "load_dialog", "Load Choice File"),
        ("ctrl+u", "page_up", "Page Up"),
        ("ctrl+d", "page_down", "Page Down"),
    ]

    def __init__(self) -> None:
        super().__init__()
        config = default_config()
        silence_pymupdf_stdout()
        self.job = InventoryJob(root=config.root_path, config=config, log_level=default_log_level())
        self._resolved_count = 0
        self._selected_targets: list[Path] = []
        self._completed = 0
        self._choice_file: Path | None = None
        self._worker_count = default_workers()
        self._log_level = default_log_level()
        self._debug_log = default_textual_debug_log()
        self._app_log = default_textual_app_log()
        self._client_script = default_client_script()
        self._client_cwd = default_client_cwd()
        self._run_active = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("No choice file loaded.", id="status")
        with Container(id="confirm_bar"):
            yield Static("Load a choice file to preview PDFs.", id="confirm_message")
            yield Button("Confirm", id="confirm", disabled=True, variant="primary")
            yield Button("Cancel", id="cancel", disabled=True)
        yield ProgressBar(total=1, id="progress_bar", show_eta=False)
        yield DataTable(id="paths_table")
        yield RichLog(id="run_log", wrap=False, highlight=False, markup=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#paths_table", DataTable)
        table.add_columns("Selected Paths")
        self._app_log.write_text("", encoding="utf-8")
        self._debug("app init")
        self.action_load_dialog()

    def action_load_dialog(self) -> None:
        if self._run_active:
            return
        self.push_screen(ChoiceFileScreen(default_choice_file()), self._handle_choice_file)

    def action_page_up(self) -> None:
        table = self.query_one("#paths_table", DataTable)
        table.action_page_up()

    def action_page_down(self) -> None:
        table = self.query_one("#paths_table", DataTable)
        table.action_page_down()

    @on(Button.Pressed, "#confirm")
    def confirm_selection(self) -> None:
        if self._run_active or not self._selected_targets or self._choice_file is None:
            return

        self._run_active = True
        self._completed = 0
        self._set_running_ui()
        self._debug("confirm_selection entered")

        self.run_worker(self._run_job_worker, thread=True)

    @on(Button.Pressed, "#cancel")
    def cancel_selection(self) -> None:
        if self._run_active:
            return
        self.query_one("#paths_table", DataTable).clear(columns=False)
        self._resolved_count = 0
        self._selected_targets = []
        self._choice_file = None
        self._reset_run_ui("Selection cleared.")

    def _run_job_worker(self) -> None:
        try:
            command = build_client_command(
                client_script=self._client_script,
                choice_file=self._choice_file,
                root=self.job.config.root_path,
                db=self.job.config.db_path,
                log_level=self._log_level,
                workers=self._worker_count,
            )
            returncode, stdout_lines = stream_client_run(
                command=command,
                cwd=self._client_cwd,
                app_log=self._app_log,
                on_stderr_line=lambda line: self.call_from_thread(self._handle_log_line, line),
            )
        except Exception as exc:
            self.call_from_thread(self._finish_run_error, str(exc))
            return

        if returncode != 0:
            self.call_from_thread(self._finish_run_error, f"client.py exited with {returncode}")
            return

        self.call_from_thread(self._finish_run_success, parse_run_summary(stdout_lines))

    def _handle_log_line(self, line: str) -> None:
        run_log = self.query_one("#run_log", RichLog)
        run_log.write(line)
        self._debug(f"log {line}")
        payload = parse_json_log_line(line)
        if payload is None or not is_attempt_event(payload):
            return

        path = event_path(payload)
        if not path:
            return

        self._completed += 1
        progress_bar = self.query_one("#progress_bar", ProgressBar)
        status = self.query_one("#status", Static)
        progress_bar.update(progress=self._completed)
        status.update(f"Processed {self._completed}/{self._resolved_count}: {path}")

    def _finish_run_success(self, summary: str) -> None:
        self._run_active = False
        self.query_one("#confirm_message", Static).update("Inventory run complete.")
        self.query_one("#confirm", Button).disabled = False
        self.query_one("#cancel", Button).disabled = False
        self.query_one("#status", Static).update(summary or f"Completed {self._resolved_count} PDF(s).")

    def _finish_run_error(self, message: str) -> None:
        self._run_active = False
        self.query_one("#confirm_message", Static).update("Inventory run failed.")
        self.query_one("#confirm", Button).disabled = False
        self.query_one("#cancel", Button).disabled = False
        self.query_one("#status", Static).update(f"Run failed: {message}")

    def _handle_choice_file(self, path: Path | None) -> None:
        if path is None:
            self.exit()
            return

        table = self.query_one("#paths_table", DataTable)
        table.clear(columns=False)
        self._resolved_count = 0
        self._selected_targets = []
        self._completed = 0
        self._choice_file = path
        self._reset_run_ui()

        if not path.exists():
            self.query_one("#status", Static).update(f"Choice file not found: {path}")
            return

        raw_rows = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not raw_rows:
            self.query_one("#status", Static).update(f"No selections in {path}")
            return

        self._selected_targets = [Path(row) for row in raw_rows]
        try:
            resolved_paths = self.job.resolve(self._selected_targets)
        except ValueError as exc:
            self.query_one("#status", Static).update(str(exc))
            return

        if not resolved_paths:
            self.query_one("#status", Static).update(f"No PDFs resolved from {path}")
            return

        for resolved_path in resolved_paths:
            table.add_row(str(resolved_path.relative_to(self.job.root)))

        self._resolved_count = len(resolved_paths)
        self.query_one("#confirm_message", Static).update(
            f"Proceed with {self._resolved_count} resolved PDF(s)?"
        )
        self.query_one("#confirm", Button).disabled = False
        self.query_one("#cancel", Button).disabled = False
        self.query_one("#status", Static).update(
            f"Loaded {len(raw_rows)} selection(s), resolved {len(resolved_paths)} PDF(s) from {path}"
        )

    def _debug(self, message: str) -> None:
        with self._debug_log.open("a", encoding="utf-8") as file_obj:
            file_obj.write(f"{message}\n")

    def _reset_run_ui(self, status_message: str = "Load a choice file to preview PDFs.") -> None:
        self.query_one("#confirm_message", Static).update("Load a choice file to preview PDFs.")
        self.query_one("#confirm", Button).disabled = True
        self.query_one("#cancel", Button).disabled = True
        self.query_one("#progress_bar", ProgressBar).update(total=1, progress=0)
        self.query_one("#run_log", RichLog).clear()
        self.query_one("#status", Static).update(status_message)

    def _set_running_ui(self) -> None:
        self.query_one("#confirm", Button).disabled = True
        self.query_one("#cancel", Button).disabled = True
        self.query_one("#confirm_message", Static).update(
            f"Running inventory for {self._resolved_count} PDF(s)..."
        )
        self.query_one("#status", Static).update("Inventory run started.")
        self.query_one("#progress_bar", ProgressBar).update(
            total=max(self._resolved_count, 1), progress=0
        )
        self.query_one("#run_log", RichLog).clear()
