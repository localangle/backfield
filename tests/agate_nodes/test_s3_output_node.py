"""S3Output node — consolidation, key naming, upload, and stale-output cleanup."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from agate_nodes.s3_output import node as s3_output_node
from agate_nodes.s3_output.node import (
    extract_article_id_from_filename,
    extract_date_from_source_file,
    extract_update_key_from_filename,
    normalize_s3_output_bucket,
    run_s3_output,
    s3_output_filename,
    s3_output_key,
    s3_output_payloads_in_run_output,
)


class _FakeS3Client:
    def __init__(self, existing_keys: list[str] | None = None) -> None:
        self.existing_keys = existing_keys or []
        self.put_calls: list[dict[str, Any]] = []
        self.deleted_keys: list[str] = []

    def put_object(self, **kwargs: Any) -> None:
        self.put_calls.append(kwargs)

    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
        prefix = str(kwargs.get("Prefix") or "")
        return {
            "Contents": [
                {"Key": key} for key in self.existing_keys if key.startswith(prefix)
            ]
        }

    def delete_object(self, **kwargs: Any) -> None:
        self.deleted_keys.append(str(kwargs["Key"]))


@pytest.fixture
def fake_s3(monkeypatch) -> _FakeS3Client:
    client = _FakeS3Client()
    monkeypatch.setattr(s3_output_node, "_s3_client", lambda: client)
    return client


def test_run_s3_output_requires_bucket() -> None:
    with pytest.raises(ValueError, match="bucket"):
        run_s3_output({"bucket": ""}, {})


def test_run_s3_output_uploads_consolidated_body(fake_s3: _FakeS3Client) -> None:
    inputs = {
        "s3n": {"text": "Hello world.", "source_file": "in/2026-06-01/story.json"},
        "px": {"locations": [{"name": "Springfield"}]},
    }
    out = run_s3_output(
        {"bucket": "s3://my-bucket", "output_path": "results"},
        inputs,
    )

    assert out["s3_bucket"] == "my-bucket"
    assert out["s3_key"] == "results/2026-06-01/story-output.json"
    assert out["consolidated"]["text"] == "Hello world."
    assert out["consolidated"]["locations"] == [{"name": "Springfield"}]

    assert len(fake_s3.put_calls) == 1
    call = fake_s3.put_calls[0]
    assert call["Bucket"] == "my-bucket"
    assert call["Key"] == "results/2026-06-01/story-output.json"
    assert call["ContentType"] == "application/json"
    assert "ACL" not in call
    body = json.loads(call["Body"].decode("utf-8"))
    assert body == out["consolidated"]


def test_run_s3_output_public_read_sets_acl(fake_s3: _FakeS3Client) -> None:
    run_s3_output(
        {"bucket": "b", "output_path": "", "public_read": True},
        {"tn": {"text": "Hi"}},
    )
    assert fake_s3.put_calls[0]["ACL"] == "public-read"


def test_run_s3_output_fallback_filename_without_source_file(fake_s3: _FakeS3Client) -> None:
    out = run_s3_output({"bucket": "b", "output_path": "out"}, {"tn": {"text": "Hi"}})
    assert re.fullmatch(
        r"out/\d{4}-\d{2}-\d{2}/output_\d{8}_\d{6}_\d{6}\.json",
        out["s3_key"],
    )


def test_run_s3_output_deletes_stale_output_for_same_article(monkeypatch) -> None:
    stale = "out/2026-06-01/story-abcdef1234-0000000000-output.json"
    client = _FakeS3Client(existing_keys=[stale])
    monkeypatch.setattr(s3_output_node, "_s3_client", lambda: client)

    out = run_s3_output(
        {"bucket": "b", "output_path": "out"},
        {"s3n": {"text": "Hi", "source_file": "in/2026-06-01/story-abcdef1234-1111111111.json"}},
    )

    assert out["s3_key"] == "out/2026-06-01/story-abcdef1234-1111111111-output.json"
    assert client.deleted_keys == [stale]


def test_filename_and_key_helpers() -> None:
    now = datetime(2026, 6, 12, 10, 30, 0, tzinfo=ZoneInfo("America/Chicago"))
    assert s3_output_filename("in/a/story.json", now=now) == "story-output.json"
    assert s3_output_filename("in/a/story.txt", now=now) == "story.txt-output.json"
    assert s3_output_filename(None, now=now).startswith("output_20260612_")

    assert (
        s3_output_key(output_path="out/", source_file="in/2026-06-01/story.json", now=now)
        == "out/2026-06-01/story-output.json"
    )
    assert (
        s3_output_key(output_path="", source_file=None, now=now)
        == "2026-06-12/output_20260612_103000_000000.json"
    )


def test_source_file_pattern_helpers() -> None:
    assert extract_date_from_source_file("in/2026-06-01/story.json") == "2026-06-01"
    assert extract_date_from_source_file("in/story.json") is None
    assert extract_article_id_from_filename("slug-abcdef1234-0123456789.json") == "abcdef1234"
    assert extract_article_id_from_filename("slug.json") is None
    assert extract_update_key_from_filename("slug-abcdef1234-0123456789.json") == "0123456789"
    assert (
        extract_update_key_from_filename("slug-abcdef1234-0123456789-output.json")
        == "0123456789"
    )


def test_normalize_s3_output_bucket() -> None:
    assert normalize_s3_output_bucket(" s3://my-bucket ") == "my-bucket"
    assert normalize_s3_output_bucket("my-bucket") == "my-bucket"
    assert normalize_s3_output_bucket("") == ""


def test_s3_output_payloads_in_run_output() -> None:
    output = {
        "json_output": {"consolidated": {"text": "Hi"}},
        "s3_output": {
            "consolidated": {"text": "Hi"},
            "s3_bucket": "b",
            "s3_key": "out/2026-06-01/story-output.json",
        },
        "place_extract": {"locations": []},
    }
    found = s3_output_payloads_in_run_output(output)
    assert list(found.keys()) == ["s3_output"]
    assert found["s3_output"]["s3_bucket"] == "b"
