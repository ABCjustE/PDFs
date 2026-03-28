from __future__ import annotations

from textual_client import PdfzxTextualApp
from textual_client.config import load_env


if __name__ == "__main__":
    load_env()
    PdfzxTextualApp().run()
