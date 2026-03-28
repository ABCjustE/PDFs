from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Center
from textual.containers import Container
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Input
from textual.widgets import Label
from textual.widgets import Static


class ChoiceFileScreen(ModalScreen[Path | None]):
    def __init__(self, default_path: Path) -> None:
        super().__init__()
        self._default_path = default_path

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="dialog"):
                yield Label("Load Yazi Selection", id="dialog_title")
                yield Static("Choice file path:", id="dialog_help")
                yield Input(value=str(self._default_path), id="choice_file_input")
                with Container(id="dialog_buttons"):
                    yield Button("Load", id="load", variant="primary")
                    yield Button("Quit", id="quit")

    @on(Button.Pressed, "#load")
    def load_file(self) -> None:
        input_widget = self.query_one("#choice_file_input", Input)
        self.dismiss(Path(input_widget.value).expanduser())

    @on(Button.Pressed, "#quit")
    def quit_dialog(self) -> None:
        self.dismiss(None)
