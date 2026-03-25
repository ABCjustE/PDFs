"""User script — read Yazi selections and run an InventoryJob."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pdfzx import InventoryJob
from pdfzx import configure_logging
from pdfzx.config import ScanConfig
from pdfzx.config import get_config


def _read_choice_file(path: Path) -> list[Path]:
    return [Path(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    default_config = get_config()

    parser = argparse.ArgumentParser(description="Run pdfzx inventory on Yazi-selected targets.")
    parser.add_argument(
        "--choice-file",
        type=Path,
        default=Path.cwd() / "yazi-choice.txt",
        help="Absolute path to the Yazi chooser output file.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=default_config.root_path,
        help="Inventory root directory.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=default_config.db_path,
        help="Registry JSON output path.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level for structured JSON output.",
    )
    args = parser.parse_args()

    configure_logging(args.log_level)

    if not args.choice_file.exists():
        parser.error(f"choice file does not exist: {args.choice_file}")

    targets = _read_choice_file(args.choice_file)
    if not targets:
        print("No files selected.")
        return 0

    config = ScanConfig(
        root_path=args.root,
        db_path=args.db,
        ocr_char_threshold=default_config.ocr_char_threshold,
        ocr_scan_pages=default_config.ocr_scan_pages,
    )
    job = InventoryJob(root=config.root_path, config=config).run(targets)
    print(json.dumps(job.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
