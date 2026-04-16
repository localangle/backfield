"""Persist successful Agate graph outputs into shared Backfield substrate tables."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

from backfield_core.types import GraphSpec, NodeConfig
from backfield_db import (
    BackfieldArticle,
    BackfieldImage,
    BackfieldLocation,
    BackfieldLocationMention,
    BackfieldLocationMentionOccurrence,
)
from sqlmodel import Session, col, select

_WS_RE = re.compile(r"\s+")


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def persist_enabled() -> bool:
    """Default-on persistence with an explicit kill switch for emergencies."""

    if _truthy_env("BACKFIELD_DISABLE_RUN_SUBSTRATE_PERSISTENCE"):
        return False
    return True


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _normalize_name(value: str) -> str:
    cleaned = _WS_RE.sub(" ", value.strip()).lower()
    return cleaned


def _sha256_hex(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        # Accept YYYY-MM-DD or full ISO timestamps.
        if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                return None
    return None


def _find_output_nodes(nodes: list[NodeConfig]) -> list[NodeConfig]:
    return [n for n in nodes if n.type == "Output"]


def _pick_consolidated_payload(
    graph: GraphSpec, node_outputs: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    output_nodes = _find_output_nodes(graph.nodes)
    if not output_nodes:
        return None

    def score(node_id: str) -> int:
        out = node_outputs.get(node_id) or {}
        consolidated = out.get("consolidated")
        if not isinstance(consolidated, dict):
            return -1
        places = consolidated.get("places")
        if not isinstance(places, dict):
            return 0
        return 1 if places else 0

    best_id = max((n.id for n in output_nodes), key=lambda nid: score(nid))
    if score(best_id) < 0:
        return None
    consolidated = node_outputs.get(best_id, {}).get("consolidated")
    return consolidated if isinstance(consolidated, dict) else None


def _geometry_bind_value(session: Session, geometry_json: dict[str, Any]) -> object | None:
    """Return a dialect-appropriate bind value for `BackfieldLocation.geometry`.

    SQLite tests store `geometry` as plain text and cannot bind GeoAlchemy elements.
    Postgres uses true PostGIS geometry via GeoAlchemy's `WKTElement`.
    """

    gtype = str(geometry_json.get("type") or "").upper()
    coords = geometry_json.get("coordinates")
    if gtype != "POINT" or not isinstance(coords, (list, tuple)) or len(coords) < 2:
        return None

    lon, lat = float(coords[0]), float(coords[1])
    wkt = f"POINT ({lon} {lat})"

    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        from geoalchemy2.elements import WKTElement

        return WKTElement(wkt, srid=4326)

    return wkt


def _external_identity_from_geocode_result(result: dict[str, Any]) -> tuple[str | None, str | None]:
    canonical_id = result.get("canonical_id")
    if canonical_id is not None:
        return "stylebook_location", str(int(canonical_id))

    rid = result.get("id")
    if rid is None:
        return None, None
    rid_str = str(rid)
    if rid_str.startswith("stylebook:"):
        return "stylebook_location", rid_str.removeprefix("stylebook:")
    if rid_str.startswith("wof:"):
        return "wof", rid_str
    if rid_str.startswith("pelias:"):
        return "pelias", rid_str
    if rid_str.startswith("h3:"):
        return "h3", rid_str
    return "geocoder", rid_str


def _fingerprint_for_location(
    *,
    project_id: int,
    location_type: str | None,
    external_source: str | None,
    external_id: str | None,
    geometry_json: dict[str, Any] | None,
    formatted_address: str | None,
    display_name: str,
) -> str:
    payload = {
        "project_id": project_id,
        "location_type": location_type,
        "external_source": external_source,
        "external_id": external_id,
        "geometry_json": geometry_json,
        "formatted_address": formatted_address,
        "display_name": display_name,
    }
    return _sha256_hex(json.dumps(payload, sort_keys=True, default=str))


def _iter_place_entries(places: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    areas = places.get("areas") if isinstance(places.get("areas"), dict) else {}
    for bucket in ("states", "counties", "cities", "neighborhoods", "regions", "other"):
        items = areas.get(bucket)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                yield f"areas.{bucket}", item

    points = places.get("points")
    if isinstance(points, list):
        for item in points:
            if isinstance(item, dict):
                yield "points", item

    needs = places.get("needs_review")
    if isinstance(needs, list):
        for item in needs:
            if isinstance(item, dict):
                yield "needs_review", item


def _display_name_for_place_entry(entry: dict[str, Any]) -> str:
    loc = entry.get("location")
    if isinstance(loc, str) and loc.strip():
        return loc.strip()
    if isinstance(loc, dict):
        full = loc.get("full")
        if isinstance(full, str) and full.strip():
            return full.strip()
    formatted = entry.get("formatted_address")
    if isinstance(formatted, str) and formatted.strip():
        return formatted.strip()
    original = entry.get("original_text")
    if isinstance(original, str) and original.strip():
        return original.strip()
    return "Unknown location"


def _geometry_parts_from_entry(
    session: Session, entry: dict[str, Any]
) -> tuple[dict[str, Any] | None, object | None, str | None]:
    geocode = entry.get("geocode") if isinstance(entry.get("geocode"), dict) else None
    result = geocode.get("result") if geocode and isinstance(geocode.get("result"), dict) else None
    geometry_json: dict[str, Any] | None = None
    if result and isinstance(result.get("geometry"), dict):
        geometry_json = dict(result["geometry"])
    elif isinstance(entry.get("geometry"), dict):
        geometry_json = dict(entry["geometry"])

    bind_value = _geometry_bind_value(session, geometry_json) if geometry_json else None
    geometry_type = geometry_json.get("type") if geometry_json else None
    geometry_type_str = str(geometry_type) if geometry_type else None
    return geometry_json, bind_value, geometry_type_str


def _formatted_address_from_entry(entry: dict[str, Any]) -> str | None:
    geocode = entry.get("geocode") if isinstance(entry.get("geocode"), dict) else None
    result = geocode.get("result") if geocode and isinstance(geocode.get("result"), dict) else None
    if result:
        formatted = result.get("formatted_address") or result.get("processed_str")
        if isinstance(formatted, str) and formatted.strip():
            return formatted.strip()
    formatted = entry.get("formatted_address")
    if isinstance(formatted, str) and formatted.strip():
        return formatted.strip()
    return None


def _geocode_meta_from_entry(entry: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    geocode = entry.get("geocode") if isinstance(entry.get("geocode"), dict) else None
    if not geocode:
        return None, None
    geocode_type = geocode.get("geocode_type")
    geocode_type_str = str(geocode_type) if geocode_type is not None else None
    result = geocode.get("result") if isinstance(geocode.get("result"), dict) else None
    return geocode_type_str, result


def _parent_ids_json(entry: dict[str, Any]) -> list[str]:
    parents = entry.get("parent_ids")
    if not isinstance(parents, list):
        return []
    out: list[str] = []
    for p in parents:
        if isinstance(p, dict):
            pid = p.get("id")
            if pid is not None:
                out.append(str(pid))
        elif p is not None:
            out.append(str(p))
    return out


def _upsert_article(
    session: Session,
    *,
    project_id: int,
    consolidated: dict[str, Any],
    run_id: str,
) -> BackfieldArticle:
    url = consolidated.get("url")
    url_str = str(url).strip() if isinstance(url, str) else None
    if url_str == "":
        url_str = None

    headline = consolidated.get("headline")
    if isinstance(headline, str) and headline.strip():
        headline_str = headline.strip()
    else:
        headline_str = "Article"

    text = consolidated.get("text")
    if not isinstance(text, str) or not text.strip():
        text = consolidated.get("article_text")
    if not isinstance(text, str) or not text.strip():
        text = "(empty)"
    text_str = text if isinstance(text, str) else str(text)

    author = consolidated.get("author")
    author_str = str(author).strip() if isinstance(author, str) else None
    if author_str == "":
        author_str = None

    pub_date = _parse_date(consolidated.get("pub_date"))

    publication = consolidated.get("publication")
    external_source = None
    if isinstance(publication, str) and publication.strip():
        external_source = str(publication).strip()

    entry_id = consolidated.get("entry_id")
    external_id = None
    if entry_id is not None and str(entry_id).strip():
        external_id = str(entry_id).strip()

    article: BackfieldArticle | None = None
    if url_str:
        article = session.exec(
            select(BackfieldArticle).where(
                col(BackfieldArticle.project_id) == project_id,
                col(BackfieldArticle.url) == url_str,
            )
        ).first()

    if article is None and external_source and external_id:
        article = session.exec(
            select(BackfieldArticle).where(
                col(BackfieldArticle.project_id) == project_id,
                col(BackfieldArticle.external_source) == external_source,
                col(BackfieldArticle.external_id) == external_id,
            )
        ).first()

    if article is None:
        fingerprint = _sha256_hex(
            json.dumps(
                {"project_id": project_id, "text": text_str},
                sort_keys=True,
            )
        )
        article = session.exec(
            select(BackfieldArticle).where(
                col(BackfieldArticle.project_id) == project_id,
                col(BackfieldArticle.external_source) == "backfield_text_fingerprint",
                col(BackfieldArticle.external_id) == fingerprint,
            )
        ).first()

    now = _utcnow()
    if article is None:
        text_fingerprint = _sha256_hex(
            json.dumps({"project_id": project_id, "text": text_str}, sort_keys=True)
        )
        resolved_external_id = external_id or text_fingerprint
        article = BackfieldArticle(
            project_id=project_id,
            external_source=external_source or "backfield_text_fingerprint",
            external_id=resolved_external_id,
            url=url_str,
            headline=headline_str,
            author=author_str,
            pub_date=pub_date,
            text=text_str,
            source_run_id=run_id,
            edited=True,
        )
        session.add(article)
        session.flush()
        return article

    article.headline = headline_str
    article.author = author_str
    article.pub_date = pub_date
    article.text = text_str
    article.url = url_str or article.url
    article.source_run_id = run_id
    article.updated_at = now
    article.edited = True
    session.add(article)
    session.flush()
    return article


def _sync_images(session: Session, *, article_id: int, consolidated: dict[str, Any]) -> None:
    images = consolidated.get("images")
    if not isinstance(images, list):
        return

    for raw in images:
        if not isinstance(raw, dict):
            continue
        url = raw.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        url_str = url.strip()

        image_id = raw.get("id") or raw.get("image_id")
        image_id_str = str(image_id).strip() if image_id is not None else ""
        if not image_id_str:
            image_id_str = _sha256_hex(url_str)[:32]

        caption = raw.get("caption")
        caption_str = str(caption).strip() if isinstance(caption, str) else None
        if caption_str == "":
            caption_str = None

        row = session.exec(
            select(BackfieldImage).where(
                col(BackfieldImage.article_id) == article_id,
                col(BackfieldImage.image_id) == image_id_str,
            )
        ).first()
        if row is None:
            session.add(
                BackfieldImage(
                    article_id=article_id,
                    image_id=image_id_str,
                    url=url_str,
                    caption=caption_str,
                )
            )
        else:
            row.url = url_str
            row.caption = caption_str
            session.add(row)

    session.flush()


def _upsert_location(
    session: Session,
    *,
    project_id: int,
    bucket: str,
    entry: dict[str, Any],
    run_id: str,
    graph_id: str,
) -> BackfieldLocation | None:
    display_name = _display_name_for_place_entry(entry)
    normalized = _normalize_name(display_name)
    if not normalized:
        return None

    location_type = entry.get("type")
    location_type_str = str(location_type).lower() if location_type is not None else None

    geocoded = entry.get("geocoded")
    geometry_json, geometry_value, geometry_type_str = _geometry_parts_from_entry(session, entry)
    formatted_address = _formatted_address_from_entry(entry)
    geocode_type, geocode_result = _geocode_meta_from_entry(entry)

    external_source: str | None = None
    external_id: str | None = None
    if isinstance(geocode_result, dict):
        external_source, external_id = _external_identity_from_geocode_result(geocode_result)

    fingerprint = _fingerprint_for_location(
        project_id=project_id,
        location_type=location_type_str,
        external_source=external_source,
        external_id=external_id,
        geometry_json=geometry_json,
        formatted_address=formatted_address,
        display_name=display_name,
    )

    status = "provisional"
    if bucket == "needs_review":
        status = "needs_review"
    if geocoded is False:
        status = "failed"

    loc: BackfieldLocation | None = None
    if external_source and external_id:
        loc = session.exec(
            select(BackfieldLocation).where(
                col(BackfieldLocation.project_id) == project_id,
                col(BackfieldLocation.external_source) == external_source,
                col(BackfieldLocation.external_id) == external_id,
            )
        ).first()

    if loc is None:
        loc = session.exec(
            select(BackfieldLocation).where(
                col(BackfieldLocation.project_id) == project_id,
                col(BackfieldLocation.identity_fingerprint) == fingerprint,
            )
        ).first()

    now = _utcnow()
    details = {
        "graph_id": graph_id,
        "run_id": run_id,
        "places_bucket": bucket,
        "raw_entry_id": entry.get("id"),
    }

    if loc is None:
        loc = BackfieldLocation(
            project_id=project_id,
            name=display_name,
            normalized_name=normalized,
            location_type=location_type_str,
            status=status,
            external_source=external_source,
            external_id=external_id,
            identity_fingerprint=fingerprint,
            geocode_type=geocode_type,
            formatted_address=formatted_address,
            parent_ids_json=_parent_ids_json(entry),
            source_kind="agate_geocode",
            source_details_json=details,
            geometry=geometry_value,
            geometry_type=geometry_type_str,
            geometry_json=geometry_json,
        )
        session.add(loc)
        session.flush()
        return loc

    loc.name = display_name
    loc.normalized_name = normalized
    loc.location_type = location_type_str or loc.location_type
    loc.status = status
    loc.external_source = external_source or loc.external_source
    loc.external_id = external_id or loc.external_id
    loc.identity_fingerprint = fingerprint
    loc.geocode_type = geocode_type or loc.geocode_type
    loc.formatted_address = formatted_address or loc.formatted_address
    loc.parent_ids_json = _parent_ids_json(entry) or loc.parent_ids_json
    loc.source_kind = "agate_geocode"
    loc.source_details_json = details
    loc.geometry = geometry_value or loc.geometry
    loc.geometry_type = geometry_type_str or loc.geometry_type
    loc.geometry_json = geometry_json or loc.geometry_json
    loc.updated_at = now
    session.add(loc)
    session.flush()
    return loc


def _suppress_prior_system_occurrences(
    session: Session,
    *,
    mention_id: int,
    mention_text: str,
) -> None:
    rows = session.exec(
        select(BackfieldLocationMentionOccurrence).where(
            col(BackfieldLocationMentionOccurrence.location_mention_id) == mention_id,
            col(BackfieldLocationMentionOccurrence.mention_text) == mention_text,
            col(BackfieldLocationMentionOccurrence.suppressed).is_(False),
            col(BackfieldLocationMentionOccurrence.source_kind) == "system_extraction",
        )
    ).all()
    now = _utcnow()
    for row in rows:
        row.suppressed = True
        row.updated_at = now
        session.add(row)
    session.flush()


def _upsert_mention_and_occurrence(
    session: Session,
    *,
    article_id: int,
    location_id: int,
    entry: dict[str, Any],
    run_id: str,
    graph_id: str,
    bucket: str,
) -> None:
    original_text = entry.get("original_text")
    mention_text = str(original_text).strip() if isinstance(original_text, str) else ""
    if not mention_text:
        mention_text = _display_name_for_place_entry(entry)

    context = entry.get("description")
    context_str = str(context).strip() if isinstance(context, str) else None
    if context_str == "":
        context_str = None

    mention = session.exec(
        select(BackfieldLocationMention).where(
            col(BackfieldLocationMention.article_id) == article_id,
            col(BackfieldLocationMention.location_id) == location_id,
        )
    ).first()

    needs_review = bucket == "needs_review" or entry.get("geocoded") is False
    review_data: dict[str, Any] | None = None
    if needs_review:
        review_data = {
            "bucket": bucket,
            "entry": entry,
        }

    now = _utcnow()
    if mention is None:
        mention = BackfieldLocationMention(
            article_id=article_id,
            location_id=location_id,
            needs_review=bool(needs_review),
            review_data_json=review_data,
            source_kind="agate_geocode",
            source_details_json={"run_id": run_id, "graph_id": graph_id},
            edited=True,
        )
        session.add(mention)
        session.flush()
    else:
        mention.needs_review = bool(needs_review)
        mention.review_data_json = review_data or mention.review_data_json
        mention.source_kind = "agate_geocode"
        mention.source_details_json = {"run_id": run_id, "graph_id": graph_id}
        mention.updated_at = now
        mention.edited = True
        session.add(mention)
        session.flush()

    _suppress_prior_system_occurrences(
        session,
        mention_id=int(mention.id),
        mention_text=mention_text,
    )

    occurrence = BackfieldLocationMentionOccurrence(
        location_mention_id=int(mention.id),
        source_kind="system_extraction",
        source_details_json={"run_id": run_id, "graph_id": graph_id, "places_bucket": bucket},
        mention_text=mention_text,
        context_text=context_str,
        quote_text=None,
        start_char=None,
        end_char=None,
        occurrence_order=None,
        labels_json=[],
        suppressed=False,
    )
    session.add(occurrence)
    session.flush()


def persist_graph_outputs(
    session: Session,
    *,
    project_id: int,
    graph_id: str,
    run_id: str,
    graph: GraphSpec,
    node_outputs: dict[str, dict[str, Any]],
) -> None:
    if not persist_enabled():
        return

    consolidated = _pick_consolidated_payload(graph, node_outputs)
    if not consolidated:
        return

    places = consolidated.get("places")
    if not isinstance(places, dict):
        return

    article = _upsert_article(
        session,
        project_id=project_id,
        consolidated=consolidated,
        run_id=run_id,
    )
    _sync_images(session, article_id=int(article.id), consolidated=consolidated)

    for bucket, entry in _iter_place_entries(places):
        loc = _upsert_location(
            session,
            project_id=project_id,
            bucket=bucket,
            entry=entry,
            run_id=run_id,
            graph_id=graph_id,
        )
        if loc is None or article.id is None:
            continue
        _upsert_mention_and_occurrence(
            session,
            article_id=int(article.id),
            location_id=int(loc.id),
            entry=entry,
            run_id=run_id,
            graph_id=graph_id,
            bucket=bucket,
        )
