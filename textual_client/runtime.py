from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
import subprocess
import sys


def build_client_command(
    *,
    client_script: Path,
    choice_file: Path,
    root: Path,
    db: Path,
    log_level: str,
    workers: int,
) -> list[str]:
    return [
        sys.executable,
        str(client_script),
        "--choice-file",
        str(choice_file),
        "--root",
        str(root),
        "--db",
        str(db),
        "--log-level",
        log_level,
        "--workers",
        str(workers),
    ]


def stream_client_run(
    *,
    command: list[str],
    cwd: Path,
    app_log: Path,
    on_stderr_line: Callable[[str], None],
) -> tuple[int, list[str]]:
    proc = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stdout_lines: list[str] = []
    assert proc.stderr is not None
    assert proc.stdout is not None
    with app_log.open("a", encoding="utf-8") as app_log_file:
        for line in proc.stderr:
            entry = line.rstrip()
            if not entry:
                continue
            app_log_file.write(f"{entry}\n")
            app_log_file.flush()
            on_stderr_line(entry)
        stdout_lines = [line for line in proc.stdout.read().splitlines() if line.strip()]
    return proc.wait(), stdout_lines


def parse_json_log_line(line: str) -> dict[str, object] | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def is_attempt_event(payload: dict[str, object]) -> bool:
    return str(payload.get("msg")) in {"processed", "skipping file due to error"}


def event_path(payload: dict[str, object]) -> str | None:
    path = payload.get("path")
    return str(path) if path else None


def parse_run_summary(stdout_lines: list[str]) -> str:
    if not stdout_lines:
        return ""
    try:
        payload = json.loads("\n".join(stdout_lines))
    except json.JSONDecodeError:
        return stdout_lines[-1]
    stats = payload.get("stats", {})
    if not isinstance(stats, dict):
        return stdout_lines[-1]
    return (
        f"job_id={payload.get('job_id')} "
        f"added={stats.get('added', 0)} "
        f"updated={stats.get('updated', 0)} "
        f"skipped={stats.get('skipped', 0)} "
        f"removed={stats.get('removed', 0)} "
        f"duplicates={stats.get('duplicates', 0)}"
    )
