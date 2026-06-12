"""S3Output node — write consolidated flow results as JSON files to S3.

Ported from agate-ai-platform ``flowbuilder_nodes/s3_output`` and adapted to the
Backfield runner contract: the executor hands S3Output every completed node
output (DBOutput-style namespaced inputs) and the node consolidates them with
the same path as JSON Output / DBOutput before uploading.

The run JSON contribution is ``{"consolidated": <file body>, "s3_bucket", "s3_key"}``
so processed-item review merges (places, people, organizations, metadata, custom
records) land inside ``consolidated`` and the S3 file can be re-synced from the
reviewed output later.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import boto3

logger = logging.getLogger(__name__)


def _s3_client():
    aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_session_token = os.environ.get("AWS_SESSION_TOKEN")
    if not aws_access_key or not aws_secret_key:
        raise ValueError(
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set in the environment "
            "(project API keys / worker overlay) for S3Output."
        )
    session_kwargs: dict[str, str] = {
        "aws_access_key_id": aws_access_key,
        "aws_secret_access_key": aws_secret_key,
    }
    if aws_session_token:
        session_kwargs["aws_session_token"] = aws_session_token
    return boto3.client("s3", **session_kwargs)


def _output_timezone() -> ZoneInfo:
    """Timezone for date folders and timestamp fallbacks (``AGATE_TIMEZONE``)."""
    tz_name = os.getenv("AGATE_TIMEZONE", "America/Chicago")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        logger.warning("Invalid AGATE_TIMEZONE %r; falling back to America/Chicago", tz_name)
        return ZoneInfo("America/Chicago")


def extract_date_from_source_file(source_file: str) -> str | None:
    """YYYY-MM-DD date embedded in the source file S3 key path, when present."""
    match = re.search(r"(\d{4}-\d{2}-\d{2})", str(source_file))
    return match.group(1) if match else None


def extract_article_id_from_filename(filename: str) -> str | None:
    """Article id from ``slug-{article_id}-{update_key}.json`` filenames."""
    match = re.search(r"-([a-zA-Z0-9]{10})-([a-zA-Z0-9]{10})\.json$", filename)
    return match.group(1) if match else None


def extract_update_key_from_filename(filename: str) -> str | None:
    """Update key from ``slug-{article_id}-{update_key}.json`` (or ``…-output.json``)."""
    filename_clean = filename.replace("-output.json", ".json")
    match = re.search(r"-([a-zA-Z0-9]{10})\.json$", filename_clean)
    return match.group(1) if match else None


def s3_output_filename(source_file: str | None, *, now: datetime) -> str:
    """``{source basename}-output.json`` or a timestamped fallback name."""
    if source_file:
        base_name = os.path.basename(str(source_file))
        if base_name.lower().endswith(".json"):
            base_name = base_name[:-5]
        if base_name:
            return f"{base_name}-output.json"
    return f"output_{now.strftime('%Y%m%d_%H%M%S_%f')}.json"


def s3_output_key(
    *,
    output_path: str,
    source_file: str | None,
    now: datetime,
) -> str:
    """``{output_path}/{YYYY-MM-DD}/{filename}`` for an upload."""
    date_folder = extract_date_from_source_file(source_file) if source_file else None
    if not date_folder:
        date_folder = now.strftime("%Y-%m-%d")
    prefix = output_path.rstrip("/") + "/" if output_path else ""
    filename = s3_output_filename(source_file, now=now)
    return f"{prefix}{date_folder}/{filename}"


def _delete_stale_outputs_for_article(
    s3_client: Any,
    *,
    bucket: str,
    new_key: str,
    source_file: str | None,
) -> None:
    """Delete older ``…-output.json`` files for the same article but a stale update key."""
    if not source_file:
        return
    base_name = os.path.basename(str(source_file))
    article_id = extract_article_id_from_filename(base_name)
    update_key = extract_update_key_from_filename(base_name)
    if not article_id or not update_key:
        return

    prefix = new_key.rsplit("/", 1)[0] + "/" if "/" in new_key else ""
    try:
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        for obj in response.get("Contents", []):
            key = obj["Key"]
            if key == new_key:
                continue
            filename = key.split("/")[-1]
            file_article_id = extract_article_id_from_filename(
                filename.replace("-output.json", ".json")
            )
            file_update_key = extract_update_key_from_filename(
                filename.replace("-output.json", ".json")
            )
            if file_article_id == article_id and file_update_key and file_update_key != update_key:
                try:
                    s3_client.delete_object(Bucket=bucket, Key=key)
                    logger.info("S3Output deleted stale output file s3://%s/%s", bucket, key)
                except Exception:
                    logger.warning("S3Output failed to delete stale output file %s", key)
    except Exception:
        logger.warning("S3Output failed to check for stale output files under %s", prefix)


def upload_s3_output_body(
    s3_client: Any,
    *,
    bucket: str,
    key: str,
    body: dict[str, Any],
    public_read: bool,
) -> None:
    """Serialize ``body`` as pretty JSON and put it at ``s3://{bucket}/{key}``."""
    json_data = json.dumps(body, indent=2, default=str)
    put_object_kwargs: dict[str, Any] = {
        "Bucket": bucket,
        "Key": key,
        "Body": json_data.encode("utf-8"),
        "ContentType": "application/json",
    }
    if public_read:
        put_object_kwargs["ACL"] = "public-read"
    try:
        s3_client.put_object(**put_object_kwargs)
    except Exception as e:
        raise ValueError(f"Failed to upload to S3: {e}") from e


def s3_output_payloads_in_run_output(output: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Node-output payloads that recorded an S3Output upload (``s3_bucket`` + ``s3_key``)."""
    found: dict[str, dict[str, Any]] = {}
    for key, payload in output.items():
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("s3_bucket"), str)
            and isinstance(payload.get("s3_key"), str)
            and isinstance(payload.get("consolidated"), dict)
        ):
            found[key] = payload
    return found


def normalize_s3_output_bucket(raw: str) -> str:
    bucket = str(raw or "").strip()
    if bucket.lower().startswith("s3://"):
        bucket = bucket[5:].strip()
    return bucket


def run_s3_output(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    # Local import: ``agate_runtime`` package init registers this node's runner,
    # so a top-level import would be circular.
    from agate_runtime.output_node import consolidated_body_from_dboutput

    bucket = normalize_s3_output_bucket(str(params.get("bucket") or ""))
    output_path = str(params.get("output_path") or "").strip()
    public_read = bool(params.get("public_read"))
    if not bucket:
        raise ValueError(
            "S3Output requires a non-empty bucket parameter. "
            "Configure the bucket on the node before running the flow."
        )

    body = consolidated_body_from_dboutput(
        {"exclude": params.get("exclude"), "include": params.get("include")},
        inputs,
    )

    source_file = body.get("source_file")
    source_file = str(source_file) if isinstance(source_file, str) and source_file else None
    now = datetime.now(_output_timezone())
    key = s3_output_key(output_path=output_path, source_file=source_file, now=now)

    s3_client = _s3_client()
    _delete_stale_outputs_for_article(
        s3_client,
        bucket=bucket,
        new_key=key,
        source_file=source_file,
    )
    logger.info("S3Output uploading to s3://%s/%s", bucket, key)
    upload_s3_output_body(
        s3_client,
        bucket=bucket,
        key=key,
        body=body,
        public_read=public_read,
    )

    return {"consolidated": body, "s3_bucket": bucket, "s3_key": key}
