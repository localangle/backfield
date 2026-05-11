"""S3Input node — load pipeline text from JSON objects in S3."""

from __future__ import annotations

import os
from typing import Any

import boto3
from backfield_agate.s3_batch import list_json_keys_under_prefix, parse_s3_text_json_document

from agate_nodes.json_input.node import json_input_output_from_dict


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


def run_s3_input(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    del inputs
    bucket = str(params.get("bucket") or "").strip()
    folder_path = str(params.get("folder_path") or "").strip()
    if not bucket:
        raise ValueError(
            "S3Input requires a non-empty bucket parameter. "
            "Configure the bucket on the node before running the flow."
        )

    s3_client = _s3_client()
    prefix = folder_path.rstrip("/") + "/" if folder_path else ""
    json_keys = list_json_keys_under_prefix(s3_client, bucket=bucket, prefix=prefix)
    total_files = len(json_keys)
    if total_files == 0:
        raise ValueError(f"No JSON objects found under s3://{bucket}/{prefix or ''}")

    chosen_payload: dict[str, Any] | None = None
    source_file: str | None = None
    processed_files = 0
    skipped_files = 0

    for file_key in json_keys:
        try:
            response = s3_client.get_object(Bucket=bucket, Key=file_key)
            raw = response["Body"].read().decode("utf-8")
        except Exception:
            skipped_files += 1
            continue

        file_data, err = parse_s3_text_json_document(raw)
        if err or file_data is None:
            skipped_files += 1
            continue

        try:
            normalized = json_input_output_from_dict(file_data)
        except ValueError:
            skipped_files += 1
            continue

        processed_files += 1
        if chosen_payload is None:
            chosen_payload = normalized
            source_file = file_key

    if not chosen_payload:
        raise ValueError(
            "S3Input listed JSON files under the prefix, but none contained a non-empty "
            "top-level 'text' field."
        )

    out = dict(chosen_payload)
    out["total_files"] = total_files
    out["processed_files"] = processed_files
    out["skipped_files"] = skipped_files
    out["source_file"] = source_file
    out["runs_created"] = []
    return out
