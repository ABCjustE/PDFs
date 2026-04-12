"""User script — read Yazi selections and run an InventoryJob."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.orm import Session

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
from pdfzx.db.repositories import TaxonomyTreeRepository
from pdfzx.db.session import create_sqlite_engine
from pdfzx.llm_suggestion import batch_document_suggestion
from pdfzx.llm_suggestion import probe_document_suggestion
from pdfzx.llm_toc_review import batch_toc_review_suggestion
from pdfzx.llm_toc_review import probe_toc_review_suggestion
from pdfzx.models import Registry
from pdfzx.partitioning.assignment import assign_taxonomy_child
from pdfzx.partitioning.generalize import generalize_taxonomy_bag
from pdfzx.partitioning.proposal import propose_taxonomy_bags
from pdfzx.partitioning.sampler import chunk_items
from pdfzx.partitioning.sampler import seeded_shuffle
from pdfzx.prompts.taxonomy_assignment import build_taxonomy_assignment_prompt_input
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


def _truncate_reasoning(value: str | None, *, width: int) -> str:
    text = (value or "").replace("\n", " ").strip()
    if len(text) <= width:
        return text
    return f"{text[: max(0, width - 1)]}…"


def _render_table(rows: list[dict[str, str]], *, columns: list[tuple[str, str, int]]) -> str:
    headers = [header for _, header, _ in columns]
    widths = [
        max(width, len(header), *(len(row[key]) for row in rows))
        for key, header, width in columns
    ]
    header_row = " | ".join(
        header.ljust(width) for header, width in zip(headers, widths, strict=True)
    )
    divider = "-+-".join("-" * width for width in widths)
    body = [
        " | ".join(
            row[key].ljust(width)
            for (key, _, _), width in zip(columns, widths, strict=True)
        )
        for row in rows
    ]
    return "\n".join([header_row, divider, *body])


def _append_ndjson(path: Path | None, payload: dict[str, object]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{json.dumps(payload, ensure_ascii=False)}\n")


class _RequestThrottle:
    def __init__(self, *, min_interval_seconds: float) -> None:
        self._min_interval_seconds = min_interval_seconds
        self._lock = threading.Lock()
        self._last_started_at = 0.0

    def wait_turn(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_started_at
            if elapsed < self._min_interval_seconds:
                time.sleep(self._min_interval_seconds - elapsed)
            self._last_started_at = time.monotonic()


def _show_taxonomy_assignments(
    sqlite_db_path: Path,
    *,
    node_path: str,
    limit: int | None,
    offset: int,
) -> str:
    engine = create_sqlite_engine(sqlite_db_path)
    try:
        with Session(engine) as session:
            repo = TaxonomyTreeRepository(session)
            node = repo.get_node_by_path(path=node_path)
            if node is None:
                msg = f"Taxonomy node not found: {node_path}"
                raise ValueError(msg)
            assignment_rows = repo.list_assignment_views(
                node_id=node.id,
                limit=limit,
                offset=offset,
            )
    finally:
        engine.dispose()
    if not assignment_rows:
        return f"No taxonomy assignments found for node: {node_path}"
    rows = [
        {
            "node_path": (row.node_path or "").replace("\n", " ").strip(),
            "document_path": (row.document_path or "").replace("\n", " ").strip(),
            "assigned_path": (row.assigned_path or "").replace("\n", " ").strip(),
            "confidence": (row.confidence or "").replace("\n", " ").strip(),
            "reasoning": _truncate_reasoning(row.reasoning_summary, width=100),
        }
        for row in assignment_rows
    ]
    return _render_table(
        rows,
        columns=[
            ("node_path", "node", 18),
            ("document_path", "document", 48),
            ("assigned_path", "assigned", 28),
            ("confidence", "confidence", 10),
            ("reasoning", "reasoning", 48),
        ],
    )


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


def _filter_document_sha256s(
    registry: Registry,
    sha256s: list[str],
    *,
    require_digital: bool,
    require_toc: bool,
) -> list[str]:
    filtered = []
    for sha256 in sha256s:
        record = registry.documents[sha256]
        if require_digital and not record.is_digital:
            continue
        if require_toc and not record.toc:
            continue
        filtered.append(sha256)
    return filtered


def _add_partition_args(
    parser: argparse.ArgumentParser,
    *,
    default_chunk_size: int,
    node_path_help: str | None,
    default_batch_count: int | None,
    batch_count_help: str,
) -> None:
    if node_path_help is not None:
        parser.add_argument(
            "--node-path",
            default="Root",
            help=node_path_help,
        )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=default_chunk_size,
        help="Override the partition chunk size for this run.",
    )
    parser.add_argument(
        "--batch-index",
        type=int,
        default=0,
        help="Zero-based shuffled batch index to start from.",
    )
    parser.add_argument(
        "--batch-count",
        type=int,
        default=default_batch_count,
        help=batch_count_help,
    )
    parser.add_argument(
        "--bag",
        nargs="*",
        default=[],
        help="Optional taxonomy bag items to pass into the accumulation stage.",
    )
    parser.add_argument(
        "--bag-size-limit",
        type=int,
        default=10,
        help="Maximum number of taxonomy bag items to request from the model.",
    )
    parser.add_argument(
        "--carry-bag",
        action="store_true",
        help="Feed each accumulation batch's taxonomy_bag_after into the next batch.",
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


def _partition_batches_from_sha256s(
    sha256s: list[str], *, seed: str, chunk_size: int
) -> list[list[str]]:
    ordered_sha256s = seeded_shuffle(sha256s, seed=seed)
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
    return _probe_partition_runs_from_batches(
        config,
        batches=batches,
        batch_index=batch_index,
        batch_count=batch_count,
        bag=bag,
        bag_size_limit=bag_size_limit,
        carry_bag=carry_bag,
    )


def _probe_partition_runs_from_batches(  # noqa: PLR0913
    config: ScanConfig,
    *,
    batches: list[list[str]],
    batch_index: int,
    batch_count: int,
    bag: list[str],
    bag_size_limit: int,
    carry_bag: bool,
) -> list[dict[str, object]]:
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


def _bootstrap_taxonomy_root(sqlite_db_path: Path) -> dict[str, object]:
    engine = create_sqlite_engine(sqlite_db_path)
    try:
        with Session(engine) as session:
            repo = TaxonomyTreeRepository(session)
            existing_root = repo.get_node_by_path(path="Root")
            root = repo.ensure_root_node()
            synced_count = repo.sync_root_documents(root_node_id=root.id)
            document_count = len(repo.list_document_sha256s(node_id=root.id))
            session.commit()
    finally:
        engine.dispose()
    return {
        "bootstrapped": existing_root is None,
        "node_id": root.id,
        "node_path": root.path,
        "document_count": document_count,
        "synced_count": synced_count,
        "message": (
            "Root node initialized. Rerun the partition workflow to start LLM partitioning."
            if existing_root is None
            else "Root node already exists. Membership has been synchronized."
        ),
    }


def _partition_generalize_payload(  # noqa: PLR0913
    config: ScanConfig,
    *,
    sha256s: list[str],
    node_path: str | None,
    chunk_size: int,
    batch_index: int,
    batch_count: int | None,
    bag: list[str],
    bag_size_limit: int,
    carry_bag: bool,
) -> dict[str, object]:
    batches = _partition_batches_from_sha256s(
        sha256s,
        seed=config.partition_seed,
        chunk_size=chunk_size,
    )
    if not batches:
        return {
            "node_path": node_path,
            "seed": config.partition_seed,
            "chunk_size": chunk_size,
            "batch_index": batch_index,
            "batch_count": batch_count,
            "carry_bag": carry_bag,
            "node_document_count": len(sha256s),
            "runs": [],
            "candidate_counts": {},
        }
    effective_batch_count = batch_count
    if effective_batch_count is None:
        effective_batch_count = len(batches) - batch_index
    runs = _probe_partition_runs_from_batches(
        config,
        batches=batches,
        batch_index=batch_index,
        batch_count=effective_batch_count,
        bag=bag,
        bag_size_limit=bag_size_limit,
        carry_bag=carry_bag,
    )
    candidate_counts = _candidate_counts_from_runs(runs)
    result = generalize_taxonomy_bag(
        taxonomy_bag_before=list(candidate_counts),
        candidate_counts=candidate_counts,
        bag_size_limit=bag_size_limit,
        online_features=config.online_features,
        openai_api_key=config.openai_api_key,
        openai_model=config.openai_model,
    )
    return {
        "node_path": node_path,
        "seed": config.partition_seed,
        "chunk_size": chunk_size,
        "batch_index": batch_index,
        "batch_count": effective_batch_count,
        "carry_bag": carry_bag,
        "node_document_count": len(sha256s),
        "runs": runs,
        "candidate_counts": candidate_counts,
        "generalize_prompt_input": result.prompt_input,
        "generalize_parsed_response": result.parsed_response,
    }


def _ensure_taxonomy_node(
    sqlite_db_path: Path, *, node_path: str
) -> tuple[dict[str, object] | None, list[str] | None]:
    engine = create_sqlite_engine(sqlite_db_path)
    try:
        with Session(engine) as session:
            repo = TaxonomyTreeRepository(session)
            if node_path == "Root":
                existing_root = repo.get_node_by_path(path="Root")
                root = repo.ensure_root_node()
                synced_count = repo.sync_root_documents(root_node_id=root.id)
                document_sha256s = repo.list_document_sha256s(node_id=root.id)
                session.commit()
                if existing_root is None:
                    return (
                        {
                            "bootstrapped": True,
                            "node_id": root.id,
                            "node_path": root.path,
                            "document_count": len(document_sha256s),
                            "synced_count": synced_count,
                            "message": (
                                "Root node initialized. Rerun the command to start "
                                "LLM partitioning."
                            ),
                        },
                        None,
                    )
                return None, document_sha256s
            node = repo.get_node_by_path(path=node_path)
            if node is None:
                msg = f"Taxonomy node not found: {node_path}"
                raise ValueError(msg)
            return None, repo.list_document_sha256s(node_id=node.id)
    finally:
        engine.dispose()


def _taxonomy_node_probe_context(
    sqlite_db_path: Path, *, node_path: str
) -> tuple[int, list[str], list[str]]:
    engine = create_sqlite_engine(sqlite_db_path)
    try:
        with Session(engine) as session:
            repo = TaxonomyTreeRepository(session)
            node = repo.get_node_by_path(path=node_path)
            if node is None:
                msg = f"Taxonomy node not found: {node_path}"
                raise ValueError(msg)
            child_labels = [child.name for child in repo.list_nodes(parent_id=node.id)]
            if not child_labels:
                msg = f"Taxonomy node has no child labels: {node_path}"
                raise ValueError(msg)
            return node.id, child_labels, repo.list_document_sha256s(node_id=node.id)
    finally:
        engine.dispose()


def _probe_taxonomy_assignments(  # noqa: PLR0913
    config: ScanConfig,
    *,
    node_path: str,
    limit: int,
    offset: int,
    require_digital: bool,
    require_toc: bool,
) -> dict[str, object]:
    node_id, child_labels, node_sha256s = _taxonomy_node_probe_context(
        config.sqlite3_db_path,
        node_path=node_path,
    )
    registry = SqliteStorage(config.sqlite3_db_path).load()
    filtered_sha256s = _filter_document_sha256s(
        registry,
        node_sha256s,
        require_digital=require_digital,
        require_toc=require_toc,
    )
    batch_sha256s = filtered_sha256s[offset : offset + limit]
    results: list[dict[str, object]] = []
    for sha256 in batch_sha256s:
        record = registry.documents[sha256]
        prompt_input = build_taxonomy_assignment_prompt_input(
            node_path=node_path,
            child_labels=child_labels,
            record=record,
        )
        result = assign_taxonomy_child(
            prompt_input=prompt_input,
            online_features=config.online_features,
            openai_api_key=config.openai_api_key,
            openai_model=config.openai_model,
        )
        results.append(
            {
                "sha256": sha256,
                "prompt_input": result.prompt_input,
                "parsed_response": result.parsed_response,
            }
        )
    return {
        "node_id": node_id,
        "node_path": node_path,
        "child_labels": child_labels,
        "total_documents": len(node_sha256s),
        "filtered_documents": len(filtered_sha256s),
        "require_digital": require_digital,
        "require_toc": require_toc,
        "offset": offset,
        "limit": limit,
        "results": results,
    }


def _run_taxonomy_assignments(  # noqa: PLR0913,PLR0915
    config: ScanConfig,
    *,
    node_path: str,
    limit: int | None,
    offset: int,
    max_concurrency: int,
    require_digital: bool,
    require_toc: bool,
    force: bool,
    output_ndjson: Path | None,
) -> dict[str, object]:
    node_id, child_labels, node_sha256s = _taxonomy_node_probe_context(
        config.sqlite3_db_path,
        node_path=node_path,
    )
    registry = SqliteStorage(config.sqlite3_db_path).load()
    filtered_sha256s = _filter_document_sha256s(
        registry,
        node_sha256s,
        require_digital=require_digital,
        require_toc=require_toc,
    )
    batch_sha256s = (
        filtered_sha256s[offset:]
        if limit is None
        else filtered_sha256s[offset : offset + limit]
    )
    engine = create_sqlite_engine(config.sqlite3_db_path)
    try:
        with Session(engine) as session:
            repo = TaxonomyTreeRepository(session)
            existing_assignment_sha256s = {
                assignment.sha256 for assignment in repo.list_assignments(node_id=node_id)
            }
            child_id_by_name = {
                child.name: child.id for child in repo.list_nodes(parent_id=node_id)
            }
    finally:
        engine.dispose()
    skipped_existing_sha256s = [] if force else [
        sha256 for sha256 in batch_sha256s if sha256 in existing_assignment_sha256s
    ]
    request_sha256s = batch_sha256s if force else [
        sha256 for sha256 in batch_sha256s if sha256 not in existing_assignment_sha256s
    ]
    prompt_inputs = [
        (
            sha256,
            build_taxonomy_assignment_prompt_input(
                node_path=node_path,
                child_labels=child_labels,
                record=registry.documents[sha256],
            ),
        )
        for sha256 in request_sha256s
    ]
    results: list[dict[str, object]] = [
        {"sha256": sha256, "skipped_existing": True, "persisted": False}
        for sha256 in skipped_existing_sha256s
    ]
    for sha256 in skipped_existing_sha256s:
        _append_ndjson(
            output_ndjson,
            {
                "workflow": "taxonomy_assignment",
                "node_path": node_path,
                "sha256": sha256,
                "status": "skipped_existing",
                "reason": "existing assignment row present",
                "prompt_input": None,
                "parsed_response": None,
                "persisted": False,
            },
        )
    persisted = 0
    failed = 0
    throttle = _RequestThrottle(min_interval_seconds=0.35)
    try:
        with Session(engine) as session:
            repo = TaxonomyTreeRepository(session)
            def persist_result(sha256: str, result) -> None:
                assigned_child_id = child_id_by_name.get(result.parsed_response["assigned_child"])
                if assigned_child_id is None:
                    msg = (
                        "LLM assignment returned an unknown child label after validation: "
                        f"{result.parsed_response['assigned_child']}"
                    )
                    raise ValueError(msg)
                repo.upsert_assignment(
                    node_id=node_id,
                    sha256=sha256,
                    assigned_child_id=assigned_child_id,
                    confidence=result.parsed_response["confidence"],
                    reasoning_summary=result.parsed_response["reasoning_summary"],
                    status="pending",
                )
                session.commit()

            if max_concurrency <= 1:
                for sha256, prompt_input in prompt_inputs:
                    try:
                        throttle.wait_turn()
                        result = assign_taxonomy_child(
                            prompt_input=prompt_input,
                            online_features=config.online_features,
                            openai_api_key=config.openai_api_key,
                            openai_model=config.openai_model,
                        )
                        persist_result(sha256, result)
                    except Exception as exc:
                        session.rollback()
                        failed += 1
                        results.append(
                            {
                                "sha256": sha256,
                                "prompt_input": prompt_input,
                                "persisted": False,
                                "error": str(exc),
                            }
                        )
                        _append_ndjson(
                            output_ndjson,
                            {
                                "workflow": "taxonomy_assignment",
                                "node_path": node_path,
                                "sha256": sha256,
                                "status": "failed",
                                "reason": str(exc),
                                "prompt_input": prompt_input,
                                "parsed_response": None,
                                "persisted": False,
                            },
                        )
                        continue
                    persisted += 1
                    results.append(
                        {
                            "sha256": sha256,
                            "prompt_input": result.prompt_input,
                            "parsed_response": result.parsed_response,
                            "persisted": True,
                        }
                    )
                    _append_ndjson(
                        output_ndjson,
                        {
                            "workflow": "taxonomy_assignment",
                            "node_path": node_path,
                            "sha256": sha256,
                            "status": "persisted",
                            "reason": "assignment request completed",
                            "prompt_input": result.prompt_input,
                            "parsed_response": result.parsed_response,
                            "persisted": True,
                        },
                    )
            else:
                with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
                    def submit_assignment(sha256: str, prompt_input):
                        throttle.wait_turn()
                        return assign_taxonomy_child(
                            prompt_input=prompt_input,
                            online_features=config.online_features,
                            openai_api_key=config.openai_api_key,
                            openai_model=config.openai_model,
                        )

                    future_map = {
                        executor.submit(
                            submit_assignment,
                            sha256,
                            prompt_input,
                        ): (sha256, prompt_input)
                        for sha256, prompt_input in prompt_inputs
                    }
                    for future in as_completed(future_map):
                        sha256, prompt_input = future_map[future]
                        try:
                            result = future.result()
                            persist_result(sha256, result)
                        except Exception as exc:
                            session.rollback()
                            failed += 1
                            results.append(
                                {
                                    "sha256": sha256,
                                    "prompt_input": prompt_input,
                                    "persisted": False,
                                    "error": str(exc),
                                }
                            )
                            _append_ndjson(
                                output_ndjson,
                                {
                                    "workflow": "taxonomy_assignment",
                                    "node_path": node_path,
                                    "sha256": sha256,
                                    "status": "failed",
                                    "reason": str(exc),
                                    "prompt_input": prompt_input,
                                    "parsed_response": None,
                                    "persisted": False,
                                },
                            )
                            continue
                        persisted += 1
                        results.append(
                            {
                                "sha256": sha256,
                                "prompt_input": result.prompt_input,
                                "parsed_response": result.parsed_response,
                                "persisted": True,
                            }
                        )
                        _append_ndjson(
                            output_ndjson,
                            {
                                "workflow": "taxonomy_assignment",
                                "node_path": node_path,
                                "sha256": sha256,
                                "status": "persisted",
                                "reason": "assignment request completed",
                                "prompt_input": result.prompt_input,
                                "parsed_response": result.parsed_response,
                                "persisted": True,
                            },
                        )
    finally:
        engine.dispose()
    return {
        "node_id": node_id,
        "node_path": node_path,
        "child_labels": child_labels,
        "total_documents": len(node_sha256s),
        "filtered_documents": len(filtered_sha256s),
        "require_digital": require_digital,
        "require_toc": require_toc,
        "offset": offset,
        "limit": limit,
        "max_concurrency": max_concurrency,
        "force": force,
        "skipped_existing": len(skipped_existing_sha256s),
        "persisted": persisted,
        "failed": failed,
        "results": results,
    }


def _persist_partition_children(
    sqlite_db_path: Path,
    *,
    node_path: str,
    child_names: list[str],
) -> dict[str, object]:
    engine = create_sqlite_engine(sqlite_db_path)
    try:
        with Session(engine) as session:
            repo = TaxonomyTreeRepository(session)
            parent = repo.get_node_by_path(path=node_path)
            if parent is None:
                msg = f"Taxonomy node not found: {node_path}"
                raise ValueError(msg)
            parent_node_id = parent.id
            parent_node_path = parent.path
            deleted_subtree_count = repo.replace_child_subtree(parent_id=parent_node_id)
            children = [
                repo.ensure_child_node(
                    parent_id=parent_node_id,
                    parent_path=parent_node_path,
                    name=name,
                )
                for name in child_names
            ]
            child_payload = [{"id": child.id, "path": child.path} for child in children]
            session.commit()
    finally:
        engine.dispose()
    return {
        "parent_node_id": parent_node_id,
        "parent_node_path": parent_node_path,
        "deleted_subtree_count": deleted_subtree_count,
        "child_count": len(child_payload),
        "children": child_payload,
    }


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
    _add_partition_args(
        partition_probe_parser,
        default_chunk_size=default_config.partition_chunk_size,
        node_path_help=None,
        default_batch_count=1,
        batch_count_help=(
            "Number of consecutive shuffled batches to accumulate before "
            "generalizing."
        ),
    )
    partition_generalize_parser = subparsers.add_parser(
        "probe-taxonomy-partition-generalize",
        parents=[_base_parser(default_config)],
        add_help=False,
        help="Probe final taxonomy generalization over one or more shuffled partition batches.",
    )
    _add_partition_args(
        partition_generalize_parser,
        default_chunk_size=default_config.partition_chunk_size,
        node_path_help=None,
        default_batch_count=1,
        batch_count_help=(
            "Number of consecutive shuffled batches to accumulate before "
            "generalizing."
        ),
    )
    run_partition_parser = subparsers.add_parser(
        "run-taxonomy-partition",
        parents=[_base_parser(default_config)],
        add_help=False,
        help=(
            "Bootstrap Root if needed, otherwise run taxonomy partitioning over one "
            "node's document memberships."
        ),
    )
    _add_partition_args(
        run_partition_parser,
        default_chunk_size=default_config.partition_chunk_size,
        node_path_help="Taxonomy node path to operate on.",
        default_batch_count=None,
        batch_count_help=(
            "Number of consecutive shuffled batches to accumulate before "
            "generalizing. Defaults to all remaining batches in the node."
        ),
    )
    assign_probe_parser = subparsers.add_parser(
        "probe-taxonomy-assign",
        parents=[_base_parser(default_config)],
        add_help=False,
        help="Probe document-to-child assignment under one taxonomy node without persisting.",
    )
    assign_probe_parser.add_argument(
        "--node-path",
        required=True,
        help="Taxonomy node path whose existing children will be used as assignment labels.",
    )
    assign_probe_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of node documents to probe in stable order.",
    )
    assign_probe_parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Start offset into the node's current document memberships.",
    )
    assign_probe_parser.add_argument(
        "--require-digital",
        action="store_true",
        help="Only run on documents marked as digital.",
    )
    assign_probe_parser.add_argument(
        "--require-toc",
        action="store_true",
        help="Only run on documents that have ToC entries.",
    )
    assign_run_parser = subparsers.add_parser(
        "run-taxonomy-assign",
        parents=[_base_parser(default_config)],
        add_help=False,
        help="Run document-to-child assignment under one taxonomy node and persist pending rows.",
    )
    assign_run_parser.add_argument(
        "--node-path",
        required=True,
        help="Taxonomy node path whose existing children will be used as assignment labels.",
    )
    assign_run_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of node documents to process from the start offset.",
    )
    assign_run_parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Start offset into the node's current document memberships.",
    )
    assign_run_parser.add_argument(
        "--max-concurrency",
        type=int,
        default=1,
        help="Maximum number of concurrent LLM requests for assignment.",
    )
    assign_run_parser.add_argument(
        "--require-digital",
        action="store_true",
        help="Only run on documents marked as digital.",
    )
    assign_run_parser.add_argument(
        "--require-toc",
        action="store_true",
        help="Only run on documents that have ToC entries.",
    )
    assign_run_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-request and overwrite existing assignment rows for the selected documents.",
    )
    assign_run_parser.add_argument(
        "--output-ndjson",
        type=Path,
        default=None,
        help="Append one JSON record per assignment result as it completes.",
    )
    show_assignments_parser = subparsers.add_parser(
        "show-taxonomy-assignments",
        parents=[_base_parser(default_config)],
        add_help=False,
        help="Display readable taxonomy assignment rows for one taxonomy node.",
    )
    show_assignments_parser.add_argument(
        "--node-path",
        required=True,
        help="Taxonomy node path whose assignment rows will be displayed.",
    )
    show_assignments_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of assignment rows to display.",
    )
    show_assignments_parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Start offset into the node's assignment rows.",
    )
    subparsers.add_parser(
        "bootstrap-taxonomy-root",
        parents=[_base_parser(default_config)],
        add_help=False,
        help=(
            "Create the Root taxonomy node if missing and sync all current "
            "document hashes into it."
        ),
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
    if args.command == "bootstrap-taxonomy-root":
        _emit_json(_bootstrap_taxonomy_root(config.sqlite3_db_path))
        return 0
    if args.command == "run-taxonomy-partition":
        bootstrap_result, node_sha256s = _ensure_taxonomy_node(
            config.sqlite3_db_path,
            node_path=args.node_path,
        )
        if bootstrap_result is not None:
            _emit_json(bootstrap_result)
            return 0
        assert node_sha256s is not None
        payload = _partition_generalize_payload(
            config,
            sha256s=node_sha256s,
            node_path=args.node_path,
            chunk_size=args.chunk_size,
            batch_index=args.batch_index,
            batch_count=args.batch_count,
            bag=args.bag,
            bag_size_limit=args.bag_size_limit,
            carry_bag=args.carry_bag,
        )
        child_names = payload.get("generalize_parsed_response", {}).get("taxonomy_bag_after", [])
        if child_names:
            payload["persisted_children"] = _persist_partition_children(
                config.sqlite3_db_path,
                node_path=args.node_path,
                child_names=child_names,
            )
        _emit_json(payload)
        return 0
    if args.command == "probe-taxonomy-assign":
        _emit_json(
            _probe_taxonomy_assignments(
                config,
                node_path=args.node_path,
                limit=args.limit,
                offset=args.offset,
                require_digital=args.require_digital,
                require_toc=args.require_toc,
            )
        )
        return 0
    if args.command == "run-taxonomy-assign":
        _emit_json(
            _run_taxonomy_assignments(
                config,
                node_path=args.node_path,
                limit=args.limit,
                offset=args.offset,
                max_concurrency=args.max_concurrency,
                require_digital=args.require_digital,
                require_toc=args.require_toc,
                force=args.force,
                output_ndjson=args.output_ndjson,
            )
        )
        return 0
    if args.command == "show-taxonomy-assignments":
        _emit_text(
            _show_taxonomy_assignments(
                config.sqlite3_db_path,
                node_path=args.node_path,
                limit=args.limit,
                offset=args.offset,
            )
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
        _emit_json(
            _partition_generalize_payload(
                config,
                sha256s=list_document_sha256s(config.sqlite3_db_path),
                node_path=None,
                chunk_size=args.chunk_size,
                batch_index=args.batch_index,
                batch_count=args.batch_count,
                bag=args.bag,
                bag_size_limit=args.bag_size_limit,
                carry_bag=args.carry_bag,
            )
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
