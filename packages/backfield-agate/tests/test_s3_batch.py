"""Unit tests for S3 batch helpers."""

from __future__ import annotations

import json

import pytest
from agate_runtime.s3_batch import (
    S3ObjectListing,
    graph_spec_json_contains_s3_input,
    list_json_objects_under_prefix,
    listing_metadata_matches_succeeded,
    logical_item_id,
    parse_s3_text_json_document,
    s3_max_files_from_params,
    sha256_hex,
)


def test_parse_s3_text_json_document_accepts_valid() -> None:
    doc, err = parse_s3_text_json_document(json.dumps({"text": " Hello ", "x": 1}))
    assert err is None
    assert doc == {"text": "Hello", "x": 1}


def test_parse_s3_text_json_document_accepts_article_text_when_text_empty() -> None:
    raw = json.dumps(
        {
            "text": "",
            "article_text": "Full narrative here.",
            "headline": "Hi",
        }
    )
    doc, err = parse_s3_text_json_document(raw)
    assert err is None
    assert doc is not None
    assert doc["text"] == "Full narrative here."


def test_parse_s3_text_json_document_prefers_longest_body_field() -> None:
    doc, err = parse_s3_text_json_document(
        json.dumps({"text": "Music", "article_text": "Something longer than Music."})
    )
    assert err is None
    assert doc is not None
    assert doc["text"] == "Something longer than Music."


@pytest.mark.parametrize(
    "raw,reason_substr",
    [
        ("not json", "invalid_json"),
        ("[]", "json_not_object"),
        ("{}", "missing_or_empty_text"),
        ('{"text":""}', "missing_or_empty_text"),
    ],
)
def test_parse_s3_text_json_document_rejects(raw: str, reason_substr: str) -> None:
    doc, err = parse_s3_text_json_document(raw)
    assert doc is None
    assert err is not None
    assert reason_substr in err


def test_s3_max_files_from_params() -> None:
    assert s3_max_files_from_params({}) == 500
    assert s3_max_files_from_params({"max_files": "3"}) == 3
    assert s3_max_files_from_params({"max_files": 0}) == 1
    assert s3_max_files_from_params({"max_files": 999999}) == 10_000


def test_graph_spec_json_contains_s3_input() -> None:
    spec = json.dumps(
        {
            "name": "g",
            "nodes": [
                {"id": "a", "type": "TextInput", "params": {}},
                {"id": "b", "type": "S3Input", "params": {}},
            ],
            "edges": [],
        }
    )
    assert graph_spec_json_contains_s3_input(spec) is True
    empty = json.dumps({"name": "g", "nodes": [], "edges": []})
    assert graph_spec_json_contains_s3_input(empty) is False


def test_logical_item_id_and_sha256() -> None:
    assert logical_item_id(bucket="b", key="p/a.json") == "b/p/a.json"
    assert sha256_hex(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_listing_metadata_matches_succeeded() -> None:
    from datetime import UTC, datetime

    listing = S3ObjectListing(
        key="p/a.json",
        etag='"abc"',
        size_bytes=10,
        last_modified=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    assert listing_metadata_matches_succeeded(
        listing=listing,
        stored_etag="abc",
        stored_size_bytes=10,
        stored_last_modified=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    assert not listing_metadata_matches_succeeded(
        listing=listing,
        stored_etag="abc",
        stored_size_bytes=11,
        stored_last_modified=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    assert not listing_metadata_matches_succeeded(
        listing=listing,
        stored_etag=None,
        stored_size_bytes=None,
        stored_last_modified=None,
    )


def test_list_json_objects_under_prefix_paginates_and_filters() -> None:
    from datetime import UTC, datetime

    class _Client:
        def __init__(self) -> None:
            self.calls = 0

        def list_objects_v2(self, **kwargs):
            self.calls += 1
            token = kwargs.get("ContinuationToken")
            if token is None:
                return {
                    "Contents": [
                        {
                            "Key": "p/b.json",
                            "ETag": '"b"',
                            "Size": 2,
                            "LastModified": datetime(2024, 1, 2, tzinfo=UTC),
                        },
                        {"Key": "p/note.txt", "ETag": '"t"', "Size": 1},
                        {"Key": "p/", "ETag": '"d"', "Size": 0},
                    ],
                    "IsTruncated": True,
                    "NextContinuationToken": "page-2",
                }
            assert token == "page-2"
            return {
                "Contents": [
                    {
                        "Key": "p/a.json",
                        "ETag": '"a"',
                        "Size": 1,
                        "LastModified": datetime(2024, 1, 1, tzinfo=UTC),
                    },
                ],
                "IsTruncated": False,
            }

    client = _Client()
    objects = list_json_objects_under_prefix(client, bucket="bucket", prefix="p/")
    assert client.calls == 2
    assert [obj.key for obj in objects] == ["p/a.json", "p/b.json"]
    assert objects[0].etag == '"a"'
    assert objects[0].size_bytes == 1
    assert objects[1].size_bytes == 2
