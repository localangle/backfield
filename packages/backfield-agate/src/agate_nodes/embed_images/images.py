"""Extract and normalize image objects from consolidated upstream state."""

from __future__ import annotations

import hashlib
from typing import Any

from agate_runtime.upstream_input import flatten_upstream_inputs


def resolve_image_id(image_obj: dict[str, Any]) -> str:
    """Stable substrate image key (matches worker ``_sync_images``)."""
    raw_id = image_obj.get("id") or image_obj.get("image_id")
    if raw_id is not None and str(raw_id).strip():
        return str(raw_id).strip()
    url = image_obj.get("url")
    if isinstance(url, str) and url.strip():
        return hashlib.sha256(url.strip().encode()).hexdigest()[:32]
    base64 = image_obj.get("base64")
    if isinstance(base64, str) and base64.strip():
        return hashlib.sha256(base64.strip().encode()).hexdigest()[:32]
    return hashlib.sha256(repr(sorted(image_obj.items())).encode()).hexdigest()[:32]


def is_valid_image_object(obj: Any) -> bool:
    return isinstance(obj, dict) and ("url" in obj or "base64" in obj)


def get_image_key(image_obj: dict[str, Any]) -> str:
    if image_obj.get("id"):
        return f"id:{image_obj['id']}"
    if image_obj.get("url"):
        return f"url:{image_obj['url']}"
    if image_obj.get("base64"):
        base64_str = str(image_obj["base64"])
        return f"base64:{base64_str[:50]}"
    return f"fallback:{image_obj!r}"


def _extract_images_recursive(
    obj: Any,
    images: list[dict[str, Any]],
    seen_keys: set[str],
) -> None:
    if isinstance(obj, dict):
        for container_key in ("image", "images"):
            if container_key in obj:
                image_data = obj[container_key]
                if isinstance(image_data, list):
                    for item in image_data:
                        if is_valid_image_object(item):
                            img_key = get_image_key(item)
                            if img_key not in seen_keys:
                                seen_keys.add(img_key)
                                images.append(item)
                elif is_valid_image_object(image_data):
                    img_key = get_image_key(image_data)
                    if img_key not in seen_keys:
                        seen_keys.add(img_key)
                        images.append(image_data)

        if ("url" in obj or "base64" in obj) and "image" not in obj and "images" not in obj:
            img_key = get_image_key(obj)
            if img_key not in seen_keys:
                seen_keys.add(img_key)
                images.append(obj)
                return

        for value in obj.values():
            _extract_images_recursive(value, images, seen_keys)
    elif isinstance(obj, list):
        for item in obj:
            _extract_images_recursive(item, images, seen_keys)


def flatten_input(input_dict: dict[str, Any]) -> dict[str, Any]:
    return flatten_upstream_inputs(input_dict)


def extract_images(input_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """Return deduplicated image dicts with ``url`` or ``base64`` from upstream state."""
    images: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    _extract_images_recursive(input_dict, images, seen_keys)
    return images


def find_article_text(flattened: dict[str, Any]) -> str | None:
    text = flattened.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    for value in flattened.values():
        if isinstance(value, dict):
            nested = value.get("text")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None
