"""Parse Claude Code JSONL files into UsageRecord objects."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .models import UsageRecord, compute_cost


def _parse_timestamp(ts: str | None) -> datetime:
    if not ts:
        return datetime.now(tz=timezone.utc)
    ts = ts.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return datetime.now(tz=timezone.utc)


def _project_label(project_dir: Path) -> str:
    """Convert a ~/.claude/projects/<hash> dir name into a readable label."""
    name = project_dir.name
    # Claude Code encodes paths as -Users-name-path-to-project
    if name.startswith("-"):
        decoded = name.replace("-", "/").lstrip("/")
        return decoded or name
    return name


def iter_records_from_jsonl(
    path: Path,
    engineer: str = "unknown",
    project_path: str = "",
) -> Iterator[UsageRecord]:
    """Yield one UsageRecord per assistant turn in a JSONL file."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if record.get("type") != "assistant":
                continue

            msg = record.get("message", {})
            if not isinstance(msg, dict):
                continue

            usage = msg.get("usage", {})
            if not isinstance(usage, dict):
                continue

            model = msg.get("model", "unknown")
            input_tokens = int(usage.get("input_tokens", 0))
            output_tokens = int(usage.get("output_tokens", 0))
            cache_read = int(usage.get("cache_read_input_tokens", 0))
            cache_write = int(usage.get("cache_creation_input_tokens", 0))

            cost = compute_cost(model, input_tokens, output_tokens, cache_read, cache_write)

            yield UsageRecord(
                session_id=record.get("sessionId", path.stem),
                request_id=record.get("requestId"),
                timestamp=_parse_timestamp(record.get("timestamp")),
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
                project_path=project_path,
                engineer=engineer,
                cost_usd=cost,
            )


def iter_records_from_project_dir(
    project_dir: Path,
    engineer: str = "unknown",
) -> Iterator[UsageRecord]:
    """Yield all UsageRecords from every JSONL under a project dir."""
    label = _project_label(project_dir)
    for jsonl_file in sorted(project_dir.glob("*.jsonl")):
        yield from iter_records_from_jsonl(jsonl_file, engineer=engineer, project_path=label)


def iter_records_from_claude_home(
    claude_home: Path | None = None,
    engineer: str = "unknown",
) -> Iterator[UsageRecord]:
    """
    Walk ~/.claude/projects/ and yield all UsageRecords.

    claude_home defaults to ~/.claude.
    """
    if claude_home is None:
        claude_home = Path.home() / ".claude"
    projects_dir = claude_home / "projects"
    if not projects_dir.exists():
        return
    for project_dir in sorted(projects_dir.iterdir()):
        if project_dir.is_dir():
            yield from iter_records_from_project_dir(project_dir, engineer=engineer)


def iter_records_from_upload_dir(
    upload_dir: Path,
) -> Iterator[UsageRecord]:
    """
    Walk a directory of per-engineer subdirs containing JSONL files.

    Expected layout:
        upload_dir/
            alice/
                project-hash.jsonl
            bob/
                project-hash.jsonl
    """
    for engineer_dir in sorted(upload_dir.iterdir()):
        if not engineer_dir.is_dir():
            continue
        engineer = engineer_dir.name
        for jsonl_file in sorted(engineer_dir.rglob("*.jsonl")):
            project_path = jsonl_file.parent.name
            yield from iter_records_from_jsonl(jsonl_file, engineer=engineer, project_path=project_path)
