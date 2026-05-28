"""Storage abstraction: local uploads directory and optional S3 backend."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterator

from .parser import iter_records_from_jsonl
from .models import UsageRecord


def get_upload_dir(base: Path | None = None) -> Path:
    """Return the default local upload directory, creating it if needed."""
    if base is None:
        base = Path(os.environ.get("CCTI_DATA_DIR", Path.home() / ".cc-team-intel"))
    uploads = base / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    return uploads


def save_upload(engineer: str, jsonl_path: Path, upload_dir: Path) -> Path:
    """Copy a JSONL file into uploads/<engineer>/. Returns destination path."""
    dest_dir = upload_dir / engineer
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / jsonl_path.name
    shutil.copy2(jsonl_path, dest)
    return dest


def iter_records_from_upload_dir(upload_dir: Path) -> Iterator[UsageRecord]:
    """Yield all UsageRecords from the structured upload directory."""
    for engineer_dir in sorted(upload_dir.iterdir()):
        if not engineer_dir.is_dir():
            continue
        engineer = engineer_dir.name
        for jsonl_file in sorted(engineer_dir.rglob("*.jsonl")):
            yield from iter_records_from_jsonl(
                jsonl_file,
                engineer=engineer,
                project_path=jsonl_file.parent.name,
            )


def try_s3_iter(bucket: str, prefix: str = "") -> Iterator[UsageRecord]:
    """
    Stream JSONL files from an S3 bucket into UsageRecords.

    Layout expected in S3:
        <prefix>/<engineer>/<session>.jsonl

    Requires: pip install boto3
    Set AWS credentials via environment (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    or instance profile.
    """
    try:
        import boto3
        import tempfile
    except ImportError as e:
        raise ImportError("S3 support requires boto3: pip install boto3") from e

    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".jsonl"):
                continue

            parts = key[len(prefix):].lstrip("/").split("/")
            engineer = parts[0] if len(parts) >= 2 else "unknown"

            with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
                s3.download_fileobj(bucket, key, tmp)
                tmp_path = Path(tmp.name)

            try:
                yield from iter_records_from_jsonl(
                    tmp_path,
                    engineer=engineer,
                    project_path="/".join(parts[1:-1]) if len(parts) > 2 else "",
                )
            finally:
                tmp_path.unlink(missing_ok=True)
