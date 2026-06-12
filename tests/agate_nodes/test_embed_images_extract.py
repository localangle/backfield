"""Tests for EmbedImages image extraction helpers."""

from __future__ import annotations

from agate_nodes.embed_images.images import extract_images, resolve_image_id


def test_extract_images_from_top_level_array() -> None:
    payload = {
        "images": [
            {"id": "hero", "url": "https://example.com/hero.jpg", "caption": "Hero"},
            {"url": "https://example.com/inline.jpg"},
        ]
    }
    rows = extract_images(payload)
    assert len(rows) == 2
    assert rows[0]["id"] == "hero"


def test_extract_images_deduplicates_by_url() -> None:
    payload = {
        "images": [{"url": "https://example.com/a.jpg"}],
        "node-1": {"images": [{"url": "https://example.com/a.jpg"}]},
    }
    rows = extract_images(payload)
    assert len(rows) == 1


def test_resolve_image_id_prefers_explicit_id() -> None:
    assert resolve_image_id({"id": "photo-1", "url": "https://example.com/a.jpg"}) == "photo-1"


def test_resolve_image_id_hashes_url_when_missing_id() -> None:
    image_id = resolve_image_id({"url": "https://example.com/a.jpg"})
    assert len(image_id) == 32
