"""User script — read Yazi selections and run an InventoryJob."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

try:
    from pdfzx.review import export_review_json
except ModuleNotFoundError:
    export_review_json = None

from pdfzx import InventoryJob
from pdfzx import configure_logging
from pdfzx.config import DEFAULT_LLM_MAX_TOC_ENTRIES
from pdfzx.config import DEFAULT_PARTITION_CHUNK_SIZE
from pdfzx.config import DEFAULT_PARTITION_SEED
from pdfzx.config import ScanConfig
from pdfzx.db.migration import migrate_json_to_sqlite
from pdfzx.db.queries import list_document_sha256s
from pdfzx.llm_suggestion import batch_document_suggestion
from pdfzx.llm_suggestion import probe_document_suggestion
from pdfzx.llm_toc_review import batch_toc_review_suggestion
from pdfzx.llm_toc_review import probe_toc_review_suggestion
from pdfzx.partitioning.generalize import generalize_taxonomy_bag
from pdfzx.partitioning.proposal import propose_taxonomy_bags
from pdfzx.partitioning.sampler import chunk_items
from pdfzx.partitioning.sampler import seeded_shuffle
from pdfzx.prompts.taxonomy_partition_proposal import build_sampled_document_summary
from pdfzx.storage import JsonStorage
from pdfzx.storage import SqliteStorage


@dataclass(frozen=True, slots=True)
class WorkflowCommandSpec:
    """CLI registration and dispatch metadata for one LLM workflow."""

    name: str
    probe_command: str
    batch_command: str
    probe_help: str
    batch_help: str
    probe_fn: Callable
    batch_fn: Callable
    uses_max_toc_entries: bool = False


def _load_env() -> None:
    load_dotenv(Path(__file__).parent / ".env")


def _read_choice_file(path: Path) -> list[Path]:
    return [
        Path(line.strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _default_config() -> ScanConfig:
    root = Path(os.environ.get("PDFZX_PDF_ROOT", Path(__file__).parent / "pdf_root"))
    db = Path(os.environ.get("PDFZX_JSON_DB", Path(__file__).parent / "db.json"))
    threshold = int(os.environ.get("PDFZX_OCR_CHAR_THRESHOLD", "100"))
    scan_pages = int(os.environ.get("PDFZX_OCR_SCAN_PAGES", "3"))
    normalize_document_name = (
        os.environ.get("PDFZX_ENABLE_NAME_NORMALIZATION", "true").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    online_features = os.environ.get("PDFZX_ONLINE_FEATURES", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    openai_api_key = os.environ.get("PDFZX_OPENAI_API_KEY")
    openai_model = os.environ.get("PDFZX_OPENAI_MODEL", "gpt-4o-mini")
    sqlite3_db_path = Path(
        os.environ.get("PDFZX_SQLITE3_DB_PATH", Path(__file__).parent / "db.sqlite3")
    )
    llm_max_toc_entries = int(
        os.environ.get(
            "PDFZX_LLM_MAX_TOC_ENTRIES", str(DEFAULT_LLM_MAX_TOC_ENTRIES)
        )
    )
    partition_seed = os.environ.get("PDFZX_PARTITION_SEED", DEFAULT_PARTITION_SEED)
    partition_chunk_size = int(
        os.environ.get(
            "PDFZX_PARTITION_CHUNK_SIZE",
            str(DEFAULT_PARTITION_CHUNK_SIZE),
        )
    )
    return ScanConfig(
        root_path=root,
        db_path=db,
        ocr_char_threshold=threshold,
        ocr_scan_pages=scan_pages,
        normalize_document_name=normalize_document_name,
        online_features=online_features,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        sqlite3_db_path=sqlite3_db_path,
        llm_max_toc_entries=llm_max_toc_entries,
        partition_seed=partition_seed,
        partition_chunk_size=partition_chunk_size,
    )


def _default_log_level() -> str:
    return os.environ.get("PDFZX_LOG_LEVEL", "DEBUG")


def _default_workers() -> int:
    return int(os.environ.get("PDFZX_WORKERS", "1"))


def _base_parser(default_config: ScanConfig) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run pdfzx inventory operations.")
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
        default=_default_log_level(),
        help="Logging level for structured JSON output.",
    )
    return parser


def _emit_json(payload: object) -> None:
    sys.stdout.write(f"{json.dumps(payload, indent=2, ensure_ascii=False)}\n")


def _emit_text(message: str) -> None:
    sys.stdout.write(f"{message}\n")


def _export_review_json(*, sqlite_db_path: Path, output_path: Path):
    if export_review_json is None:
        msg = "export-review-json is unavailable because pdfzx.review is not installed"
        raise ModuleNotFoundError(msg)
    return export_review_json(sqlite_db_path=sqlite_db_path, output_path=output_path)


def _add_batch_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--require-digital",
        action="store_true",
        help="Only run on documents marked as digital.",
    )
    parser.add_argument(
        "--require-toc",
        action="store_true",
        help="Only run on documents that have ToC entries.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on the number of documents to process.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass the same-doc same-prompt duplicate gate.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=1,
        help="Maximum number of concurrent LLM requests for batch commands.",
    )
    parser.add_argument(
        "--output-ndjson",
        type=Path,
        default=None,
        help="Append one JSON record per batch item with prompt input and parsed response.",
    )


def _workflow_specs() -> tuple[WorkflowCommandSpec, ...]:
    return (
        WorkflowCommandSpec(
            name="document",
            probe_command="probe-llm",
            batch_command="suggest-llm",
            probe_help="Probe one document against the LLM prompt and inspect input/output.",
            batch_help="Run document-suggestion over a filtered batch and persist results.",
            probe_fn=probe_document_suggestion,
            batch_fn=batch_document_suggestion,
        ),
        WorkflowCommandSpec(
            name="toc-review",
            probe_command="probe-toc-review",
            batch_command="suggest-toc-review",
            probe_help="Probe one document against the ToC-review prompt and inspect input/output.",
            batch_help="Run ToC review over a filtered batch and persist results.",
            probe_fn=probe_toc_review_suggestion,
            batch_fn=batch_toc_review_suggestion,
            uses_max_toc_entries=True,
        ),
    )


def _add_probe_workflow_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    default_config: ScanConfig,
    spec: WorkflowCommandSpec,
) -> None:
    parser = subparsers.add_parser(
        spec.probe_command,
        parents=[_base_parser(default_config)],
        add_help=False,
        help=spec.probe_help,
    )
    parser.add_argument("--sha256", required=True, help="Document sha256 to probe.")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist the validated suggestion if the probe succeeds.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass the duplicate suggestion gate and send the request anyway.",
    )


def _add_batch_workflow_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    default_config: ScanConfig,
    spec: WorkflowCommandSpec,
) -> None:
    parser = subparsers.add_parser(
        spec.batch_command,
        parents=[_base_parser(default_config)],
        add_help=False,
        help=spec.batch_help,
    )
    _add_batch_filter_args(parser)


def _probe_kwargs(
    config: ScanConfig,
    args: argparse.Namespace,
    *,
    use_max_toc: bool,
) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "sqlite_db_path": config.sqlite3_db_path,
        "sha256": args.sha256,
        "online_features": config.online_features,
        "openai_api_key": config.openai_api_key,
        "openai_model": config.openai_model,
        "persist": args.persist,
        "force": args.force,
    }
    if use_max_toc:
        kwargs["max_toc_entries"] = config.llm_max_toc_entries
    return kwargs


def _batch_kwargs(
    config: ScanConfig,
    args: argparse.Namespace,
    *,
    use_max_toc: bool,
) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "sqlite_db_path": config.sqlite3_db_path,
        "online_features": config.online_features,
        "openai_api_key": config.openai_api_key,
        "openai_model": config.openai_model,
        "require_digital": args.require_digital,
        "require_toc": args.require_toc,
        "limit": args.limit,
        "force": args.force,
        "max_concurrency": args.max_concurrency,
        "output_ndjson": args.output_ndjson,
    }
    if use_max_toc:
        kwargs["max_toc_entries"] = config.llm_max_toc_entries
    return kwargs


def _emit_probe_result(result: object) -> None:
    _emit_json(
        {
            "should_request": result.should_request,
            "reason": result.reason,
            "prompt_id": result.prompt_id,
            "prompt_input": result.prompt_input,
            "parsed_response": result.parsed_response,
            "persisted": result.persisted,
        }
    )


def _emit_batch_result(result: object) -> None:
    _emit_json(asdict(result))


def _partition_batches(config: ScanConfig, *, chunk_size: int) -> list[list[str]]:
    sha256s = list_document_sha256s(config.sqlite3_db_path)
    ordered_sha256s = seeded_shuffle(sha256s, seed=config.partition_seed)
    return chunk_items(ordered_sha256s, chunk_size=chunk_size)


def _probe_partition_runs(  # noqa: PLR0913
    config: ScanConfig,
    *,
    batch_index: int,
    batch_count: int,
    chunk_size: int,
    bag: list[str],
    bag_size_limit: int,
    carry_bag: bool,
) -> list[dict[str, object]]:
    batches = _partition_batches(config, chunk_size=chunk_size)
    if batch_count <= 0:
        msg = "batch_count must be greater than 0"
        raise ValueError(msg)
    end_batch_index = batch_index + batch_count - 1
    if batch_index < 0 or end_batch_index >= len(batches):
        msg = (
            f"batch range out of range: {batch_index}..{end_batch_index} "
            f"(available: 0..{max(len(batches) - 1, 0)})"
        )
        raise ValueError(msg)
    registry = SqliteStorage(config.sqlite3_db_path).load()
    current_bag = list(bag)
    runs: list[dict[str, object]] = []
    for current_batch_index in range(batch_index, batch_index + batch_count):
        batch_sha256s = batches[current_batch_index]
        chunk_documents = [
            build_sampled_document_summary(registry.documents[sha256]) for sha256 in batch_sha256s
        ]
        result = propose_taxonomy_bags(
            batch_index=current_batch_index,
            chunk_documents=chunk_documents,
            taxonomy_bag_before=current_bag,
            bag_size_limit=bag_size_limit,
            online_features=config.online_features,
            openai_api_key=config.openai_api_key,
            openai_model=config.openai_model,
        )
        runs.append(
            {
                "batch_index": current_batch_index,
                "batch_size": len(batch_sha256s),
                "batch_sha256s": batch_sha256s,
                "prompt_input": result.prompt_input,
                "parsed_response": result.parsed_response,
            }
        )
        if carry_bag:
            current_bag = result.parsed_response.get("taxonomy_bag_after", [])
    return runs


def _candidate_counts_from_runs(runs: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for run in runs:
        for item in run.get("parsed_response", {}).get("taxonomy_bag_after", []):
            counts[item] = counts.get(item, 0) + 1
    return counts


def main() -> int:  # noqa: C901,PLR0911,PLR0912,PLR0915
    """Run the pdfzx user script entrypoint."""
    _load_env()
    default_config = _default_config()

    parser = argparse.ArgumentParser(description="Run pdfzx inventory operations.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    workflow_specs = _workflow_specs()
    probe_specs = {spec.probe_command: spec for spec in workflow_specs}
    batch_specs = {spec.batch_command: spec for spec in workflow_specs}

    scan_parser = subparsers.add_parser(
        "scan",
        parents=[_base_parser(default_config)],
        add_help=False,
        help="Run PDF inventory on Yazi-selected targets.",
    )
    scan_parser.add_argument(
        "--choice-file",
        type=Path,
        default=Path.cwd() / "yazi-choice.txt",
        help="Absolute path to the Yazi chooser output file.",
    )
    scan_parser.add_argument(
        "--workers",
        type=int,
        default=_default_workers(),
        help="Number of parallel worker processes for PDF extraction (default 1 = serial).",
    )

    subparsers.add_parser(
        "backfill",
        parents=[_base_parser(default_config)],
        add_help=False,
        help="Backfill normalised_name for existing documents in db.json.",
    )
    migrate_parser = subparsers.add_parser(
        "migrate-sqlite",
        parents=[_base_parser(default_config)],
        add_help=False,
        help="Import the existing db.json registry into SQLite.",
    )
    migrate_parser.add_argument(
        "--sqlite-db",
        type=Path,
        default=default_config.sqlite3_db_path,
        help="Target SQLite database path.",
    )
    migrate_parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace the existing SQLite database file if it already exists.",
    )
    export_parser = subparsers.add_parser(
        "export-json",
        parents=[_base_parser(default_config)],
        add_help=False,
        help="Export the current SQLite-backed registry to JSON.",
    )
    export_parser.add_argument(
        "--json-db",
        type=Path,
        default=default_config.db_path,
        help="Target JSON export path.",
    )
    review_parser = subparsers.add_parser(
        "export-review-json",
        parents=[_base_parser(default_config)],
        add_help=False,
        help="Export side-by-side review rows for current and suggested name/path data.",
    )
    review_parser.add_argument(
        "--output",
        type=Path,
        default=Path("review.json"),
        help="Target review JSON path.",
    )
    partition_probe_parser = subparsers.add_parser(
        "probe-taxonomy-partition",
        parents=[_base_parser(default_config)],
        add_help=False,
        help="Probe the taxonomy-partition prompt against one shuffled batch.",
    )
    partition_probe_parser.add_argument(
        "--batch-index",
        type=int,
        default=0,
        help="Zero-based shuffled batch index to probe.",
    )
    partition_probe_parser.add_argument(
        "--chunk-size",
        type=int,
        default=default_config.partition_chunk_size,
        help="Override the partition chunk size for this probe command.",
    )
    partition_probe_parser.add_argument(
        "--batch-count",
        type=int,
        default=1,
        help="Number of consecutive shuffled batches to probe.",
    )
    partition_probe_parser.add_argument(
        "--bag",
        nargs="*",
        default=[],
        help="Optional taxonomy bag items to pass as the current working bag.",
    )
    partition_probe_parser.add_argument(
        "--bag-size-limit",
        type=int,
        default=10,
        help="Maximum number of taxonomy bag items to request from the model.",
    )
    partition_probe_parser.add_argument(
        "--carry-bag",
        action="store_true",
        help="Feed each batch's taxonomy_bag_after into the next batch as taxonomy_bag_before.",
    )
    partition_generalize_parser = subparsers.add_parser(
        "probe-taxonomy-partition-generalize",
        parents=[_base_parser(default_config)],
        add_help=False,
        help="Probe final taxonomy generalization over one or more shuffled partition batches.",
    )
    partition_generalize_parser.add_argument(
        "--batch-index",
        type=int,
        default=0,
        help="Zero-based shuffled batch index to start from.",
    )
    partition_generalize_parser.add_argument(
        "--chunk-size",
        type=int,
        default=default_config.partition_chunk_size,
        help="Override the partition chunk size for this probe command.",
    )
    partition_generalize_parser.add_argument(
        "--batch-count",
        type=int,
        default=1,
        help="Number of consecutive shuffled batches to accumulate before generalizing.",
    )
    partition_generalize_parser.add_argument(
        "--bag",
        nargs="*",
        default=[],
        help="Optional taxonomy bag items to pass into the accumulation stage.",
    )
    partition_generalize_parser.add_argument(
        "--bag-size-limit",
        type=int,
        default=10,
        help="Maximum number of taxonomy bag items to request from the model.",
    )
    partition_generalize_parser.add_argument(
        "--carry-bag",
        action="store_true",
        help="Feed each accumulation batch's taxonomy_bag_after into the next batch.",
    )
    for spec in workflow_specs:
        _add_probe_workflow_parser(subparsers, default_config, spec)
        _add_batch_workflow_parser(subparsers, default_config, spec)

    args = parser.parse_args()

    configure_logging(args.log_level)

    config = ScanConfig(
        root_path=args.root,
        db_path=args.db,
        ocr_char_threshold=default_config.ocr_char_threshold,
        ocr_scan_pages=default_config.ocr_scan_pages,
        normalize_document_name=default_config.normalize_document_name,
        online_features=default_config.online_features,
        openai_api_key=default_config.openai_api_key,
        openai_model=default_config.openai_model,
        sqlite3_db_path=getattr(args, "sqlite_db", default_config.sqlite3_db_path),
        llm_max_toc_entries=default_config.llm_max_toc_entries,
        partition_seed=default_config.partition_seed,
        partition_chunk_size=default_config.partition_chunk_size,
    )
    inventory = InventoryJob(root=config.root_path, config=config, log_level=args.log_level)

    if args.command == "backfill":
        updated = inventory.backfill_normalised_names()
        _emit_json({"updated": updated, "db_path": str(config.db_path.resolve())})
        return 0
    if args.command == "migrate-sqlite":
        summary = migrate_json_to_sqlite(
            source_json=config.db_path,
            target_sqlite=config.sqlite3_db_path,
            replace=args.replace,
        )
        _emit_json(summary)
        return 0
    if args.command == "export-json":
        registry = inventory._storage.load()  # noqa: SLF001 - explicit export path
        JsonStorage(args.json_db).save(registry)
        _emit_json(
            {
                "source_sqlite": str(config.sqlite3_db_path.resolve()),
                "target_json": str(args.json_db.resolve()),
                "documents": len(registry.documents),
                "file_stats": len(registry.file_stats),
                "jobs": len(registry.jobs),
            }
        )
        return 0
    if args.command == "export-review-json":
        payload = _export_review_json(
            sqlite_db_path=config.sqlite3_db_path,
            output_path=args.output,
        )
        _emit_json(
            {
                "output_path": str(args.output.resolve()),
                "row_count": payload.row_count,
            }
        )
        return 0
    if args.command == "probe-taxonomy-partition":
        batches = _partition_batches(config, chunk_size=args.chunk_size)
        if not batches:
            _emit_json({"batch_index": args.batch_index, "batch_size": 0, "batch_sha256s": []})
            return 0
        runs = _probe_partition_runs(
            config,
            batch_index=args.batch_index,
            batch_count=args.batch_count,
            chunk_size=args.chunk_size,
            bag=args.bag,
            bag_size_limit=args.bag_size_limit,
            carry_bag=args.carry_bag,
        )
        _emit_json(
            {
                "seed": config.partition_seed,
                "chunk_size": args.chunk_size,
                "batch_index": args.batch_index,
                "batch_count": args.batch_count,
                "carry_bag": args.carry_bag,
                "runs": runs,
            }
        )
        return 0
    if args.command == "probe-taxonomy-partition-generalize":
        batches = _partition_batches(config, chunk_size=args.chunk_size)
        if not batches:
            _emit_json(
                {
                    "batch_index": args.batch_index,
                    "batch_count": args.batch_count,
                    "chunk_size": args.chunk_size,
                    "runs": [],
                    "candidate_counts": {},
                }
            )
            return 0
        runs = _probe_partition_runs(
            config,
            batch_index=args.batch_index,
            batch_count=args.batch_count,
            chunk_size=args.chunk_size,
            bag=args.bag,
            bag_size_limit=args.bag_size_limit,
            carry_bag=args.carry_bag,
        )
        candidate_counts = _candidate_counts_from_runs(runs)
        result = generalize_taxonomy_bag(
            taxonomy_bag_before=list(candidate_counts),
            candidate_counts=candidate_counts,
            bag_size_limit=args.bag_size_limit,
            online_features=config.online_features,
            openai_api_key=config.openai_api_key,
            openai_model=config.openai_model,
        )
        _emit_json(
            {
                "seed": config.partition_seed,
                "chunk_size": args.chunk_size,
                "batch_index": args.batch_index,
                "batch_count": args.batch_count,
                "carry_bag": args.carry_bag,
                "runs": runs,
                "candidate_counts": candidate_counts,
                "generalize_prompt_input": result.prompt_input,
                "generalize_parsed_response": result.parsed_response,
            }
        )
        return 0
    if args.command in probe_specs:
        spec = probe_specs[args.command]
        result = spec.probe_fn(
            **_probe_kwargs(config, args, use_max_toc=spec.uses_max_toc_entries)
        )
        _emit_probe_result(result)
        return 0
    if args.command in batch_specs:
        spec = batch_specs[args.command]
        result = spec.batch_fn(
            **_batch_kwargs(config, args, use_max_toc=spec.uses_max_toc_entries)
        )
        _emit_batch_result(result)
        return 0

    if not args.choice_file.exists():
        parser.error(f"choice file does not exist: {args.choice_file}")

    targets = _read_choice_file(args.choice_file)
    if not targets:
        _emit_text("No files selected.")
        return 0

    job = inventory.run(targets, workers=args.workers)
    _emit_json(job.model_dump(mode="json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
