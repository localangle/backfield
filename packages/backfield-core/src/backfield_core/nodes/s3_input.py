"""S3Input node — load pipeline text from JSON objects in S3 (ported from agate-ai-platform).

Backfield executes one graph per run. This runner lists ``*.json`` keys under the configured
prefix, reads each object, and uses the **first** JSON document whose top-level ``text`` field
is a non-empty string as the pipeline input (same downstream shape as ``TextInput``). The
returned dict also includes batch summary fields for UI parity with the original node.
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3


def _s3_client():
    aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_session_token = os.environ.get("AWS_SESSION_TOKEN")
    if not aws_access_key or not aws_secret_key:
        raise ValueError(
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set in the environment "
            "(project API keys / worker overlay) for S3Input."
        )
    session_kwargs: dict[str, str] = {
        "aws_access_key_id": aws_access_key,
        "aws_secret_access_key": aws_secret_key,
    }
    if aws_session_token:
        session_kwargs["aws_session_token"] = aws_session_token
    return boto3.client("s3", **session_kwargs)


def _list_json_keys(s3_client: Any, *, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3_client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            key = str(obj.get("Key") or "")
            if key.endswith(".json") and not key.endswith("/"):
                keys.append(key)
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
        if not token:
            break
    return keys


def run_s3_input(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    del inputs  # input nodes have no upstream wiring in the executor
    bucket = str(params.get("bucket") or "").strip()
    folder_path = str(params.get("folder_path") or "").strip()
    if not bucket:
        raise ValueError(
            "S3Input requires a non-empty bucket parameter. "
            "Configure the bucket on the node before running the flow."
        )

    s3_client = _s3_client()
    prefix = folder_path.rstrip("/") + "/" if folder_path else ""
    json_keys = _list_json_keys(s3_client, bucket=bucket, prefix=prefix)
    total_files = len(json_keys)
    if total_files == 0:
        raise ValueError(f"No JSON objects found under s3://{bucket}/{prefix or ''}")

    chosen_text: str | None = None
    source_file: str | None = None
    processed_files = 0
    skipped_files = 0

    for file_key in json_keys:
        try:
            response = s3_client.get_object(Bucket=bucket, Key=file_key)
            raw = response["Body"].read().decode("utf-8")
            file_data = json.loads(raw)
        except json.JSONDecodeError:
            skipped_files += 1
            continue
        except Exception:
            skipped_files += 1
            continue

        if not isinstance(file_data, dict):
            skipped_files += 1
            continue
        text_val = file_data.get("text")
        if text_val is None or not str(text_val).strip():
            skipped_files += 1
            continue

        processed_files += 1
        if chosen_text is None:
            chosen_text = str(text_val)
            source_file = file_key

    if not chosen_text:
        raise ValueError(
            "S3Input listed JSON files under the prefix, but none contained a non-empty "
            "top-level 'text' field."
        )

    return {
        "text": chosen_text,
        "total_files": total_files,
        "processed_files": processed_files,
        "skipped_files": skipped_files,
        "source_file": source_file,
        "runs_created": [],
    }
