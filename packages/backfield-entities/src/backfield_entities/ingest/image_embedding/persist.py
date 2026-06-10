"""Persist image embeddings from consolidated DBOutput payloads."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from backfield_db import SubstrateImage, SubstrateImageEmbedding
from sqlmodel import Session, col, select

from backfield_entities.ingest.db_output_settings import ReconciliationPolicy

ImageEmbeddingPersistStatus = Literal["not_present", "skipped", "succeeded", "failed"]


def _image_embeddings_block(consolidated: dict[str, Any]) -> list[dict[str, Any]] | None:
    raw = consolidated.get("image_embeddings")
    if not isinstance(raw, list):
        return None
    rows = [item for item in raw if isinstance(item, dict)]
    return rows


def _resolve_image_id(image_obj: dict[str, Any]) -> str:
    raw_id = image_obj.get("id") or image_obj.get("image_id")
    if raw_id is not None and str(raw_id).strip():
        return str(raw_id).strip()
    url = image_obj.get("url")
    if isinstance(url, str) and url.strip():
        import hashlib

        return hashlib.sha256(url.strip().encode()).hexdigest()[:32]
    raise ValueError("image_embeddings row requires id, image_id, or url")


def persist_image_embeddings_after_db_output(
    session: Session,
    *,
    article_id: int,
    consolidated: dict[str, Any],
    policy: ReconciliationPolicy,
) -> dict[str, Any]:
    """Upsert ``substrate_image_embedding`` rows when ``image_embeddings`` is present."""
    rows = _image_embeddings_block(consolidated)
    if rows is None:
        if policy == "replace":
            existing = session.exec(
                select(SubstrateImageEmbedding)
                .join(
                    SubstrateImage,
                    SubstrateImage.id == SubstrateImageEmbedding.substrate_image_id,
                )
                .where(col(SubstrateImage.article_id) == article_id)
            ).all()
            for row in existing:
                session.delete(row)
            session.flush()
            if existing:
                return {
                    "status": "succeeded",
                    "persisted": False,
                    "action": "deleted",
                    "count": 0,
                }
        return {"status": "not_present", "persisted": False, "count": 0}

    if not rows:
        return {"status": "not_present", "persisted": False, "count": 0}

    persisted = 0
    skipped = 0
    errors: list[str] = []

    for block in rows:
        try:
            image_id = _resolve_image_id(block)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        substrate_image = session.exec(
            select(SubstrateImage).where(
                col(SubstrateImage.article_id) == article_id,
                col(SubstrateImage.image_id) == image_id,
            )
        ).first()
        if substrate_image is None or substrate_image.id is None:
            url = block.get("url")
            if not isinstance(url, str) or not url.strip():
                errors.append(f"No substrate image row for image_id={image_id!r}")
                continue
            substrate_image = SubstrateImage(
                article_id=article_id,
                image_id=image_id,
                url=url.strip(),
                caption=str(block.get("caption")).strip()
                if isinstance(block.get("caption"), str) and str(block.get("caption")).strip()
                else None,
            )
            session.add(substrate_image)
            session.flush()

        vector = block.get("embedding")
        if not isinstance(vector, list) or not vector:
            errors.append(f"image_embeddings[{image_id}].embedding must be a non-empty vector")
            continue

        generated_text = str(block.get("generated_text") or "").strip()
        if not generated_text:
            errors.append(f"image_embeddings[{image_id}].generated_text is required")
            continue

        model = str(block.get("embedding_model") or "").strip()
        if not model:
            errors.append(f"image_embeddings[{image_id}].embedding_model is required")
            continue

        dimensions_raw = block.get("embedding_dimensions")
        dimensions = int(dimensions_raw) if dimensions_raw is not None else len(vector)
        embedding_config_id_raw = block.get("embedding_ai_model_config_id")
        embedding_config_id = (
            embedding_config_id_raw.strip()
            if isinstance(embedding_config_id_raw, str) and embedding_config_id_raw.strip()
            else None
        )
        vision_model_raw = block.get("description_model") or block.get("vision_model")
        vision_model = (
            vision_model_raw.strip()
            if isinstance(vision_model_raw, str) and vision_model_raw.strip()
            else None
        )
        vision_config_id_raw = (
            block.get("description_ai_model_config_id") or block.get("vision_ai_model_config_id")
        )
        vision_config_id = (
            vision_config_id_raw.strip()
            if isinstance(vision_config_id_raw, str) and vision_config_id_raw.strip()
            else None
        )

        existing = session.exec(
            select(SubstrateImageEmbedding).where(
                SubstrateImageEmbedding.substrate_image_id == substrate_image.id
            )
        ).first()

        if policy == "add_only" and existing is not None:
            skipped += 1
            continue

        if (
            policy == "smart_merge"
            and existing is not None
            and existing.generated_text == generated_text
            and existing.embedding_model == model
        ):
            skipped += 1
            continue

        now = datetime.now(UTC)
        bind = session.get_bind()
        embedding_value: object = list(vector)
        if bind.dialect.name != "postgresql":
            embedding_value = json.dumps(list(vector))

        if existing is None:
            session.add(
                SubstrateImageEmbedding(
                    substrate_image_id=int(substrate_image.id),
                    generated_text=generated_text,
                    vision_model=vision_model,
                    vision_ai_model_config_id=vision_config_id,
                    embedding_model=model,
                    embedding_dimensions=dimensions,
                    embedding_ai_model_config_id=embedding_config_id,
                    embedding=embedding_value,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            existing.generated_text = generated_text
            existing.vision_model = vision_model
            existing.vision_ai_model_config_id = vision_config_id
            existing.embedding_model = model
            existing.embedding_dimensions = dimensions
            existing.embedding_ai_model_config_id = embedding_config_id
            existing.embedding = embedding_value
            existing.updated_at = now
            session.add(existing)
        persisted += 1

    session.flush()

    if errors and persisted == 0 and skipped == 0:
        return {
            "status": "failed",
            "persisted": False,
            "count": 0,
            "error": "; ".join(errors[:3]),
        }

    status: ImageEmbeddingPersistStatus = "succeeded" if persisted or skipped else "not_present"
    result: dict[str, Any] = {
        "status": status,
        "persisted": persisted > 0,
        "count": persisted,
        "skipped": skipped,
    }
    if errors:
        result["warnings"] = errors
    return result
