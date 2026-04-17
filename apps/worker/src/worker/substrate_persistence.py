"""Persist successful Agate graph outputs into shared substrate_* tables."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

from backfield_db import (
    SubstrateArticle,
    SubstrateImage,
    SubstrateLocation,
    SubstrateLocationCache,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from sqlmodel import Session, col, select

_WS_RE = re.compile(r"\s+")

# LLM / consolidation sometimes appends closing punctuation not present in `consolidated["text"]`.
# passlib is unrelated; these are stripped only when locating a substring for start_char/end_char.
_TRAILING_SPAN_ARTIFACT_CHARS: frozenset[str] = frozenset(
    '.,;:!?)]}"\'…\u201d\u2019\u201c'  # ASCII closers + ellipsis + curly quotes
)


def _rstrip_trailing_span_artifacts(fragment: str) -> str:
    """Drop trailing whitespace and common sentence/closing marks (iteratively)."""

    s = fragment.rstrip()
    while s and s[-1] in _TRAILING_SPAN_ARTIFACT_CHARS:
        s = s[:-1].rstrip()
    return s


def _mention_text_span_variants(needle: str) -> list[str]:
    """Longest-first candidates to search in article text (exact substring match)."""

    stripped = _rstrip_trailing_span_artifacts(needle)
    if stripped == needle:
        return [needle] if needle else []
    out: list[str] = []
    if needle:
        out.append(needle)
    if stripped:
        out.append(stripped)
    return out


# Primary editorial role (PlaceExtract `nature`). Extras: `nature_secondary_tags` in extraction JSON
# → `SubstrateLocationMention.nature_secondary_tags_json`.
_NATURE_PRIMARY_ALLOWED = frozenset(
    {"primary", "secondary", "subject", "context", "person", "unknown"}
)
_NATURE_PRIMARY_SYNONYMS: dict[str, str] = {
    "setting": "primary",
    "main": "primary",
    "scene": "primary",
    "dateline": "primary",
}


def _normalize_nature_primary(entry: dict[str, Any]) -> str | None:
    raw = entry.get("nature")
    if not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if not s:
        return None
    if s in _NATURE_PRIMARY_ALLOWED:
        return s
    return _NATURE_PRIMARY_SYNONYMS.get(s, "unknown")


def _parse_nature_secondary_tags(entry: dict[str, Any]) -> list[str]:
    raw = entry.get("nature_secondary_tags")
    if raw is None:
        raw = entry.get("nature_secondary")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for x in raw:
        if isinstance(x, str):
            t = _WS_RE.sub(" ", x.strip()).lower()
            if t:
                out.append(t)
    seen: set[str] = set()
    uniq: list[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


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


def _coord_pair_wkt(pair: Any) -> str | None:
    if not isinstance(pair, (list, tuple)) or len(pair) < 2:
        return None
    lon, lat = float(pair[0]), float(pair[1])
    return f"{lon} {lat}"


def _ring_coords_wkt(ring: Any) -> str | None:
    if not isinstance(ring, list) or not ring:
        return None
    pts: list[str] = []
    for pair in ring:
        wkt_pair = _coord_pair_wkt(pair)
        if not wkt_pair:
            return None
        pts.append(wkt_pair)
    if len(pts) < 3:
        return None
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return ", ".join(pts)


def _geojson_to_wkt(geometry_json: dict[str, Any]) -> str | None:
    gtype = str(geometry_json.get("type") or "").title()
    coords = geometry_json.get("coordinates")

    try:
        if gtype == "Point":
            pair = _coord_pair_wkt(coords)
            if not pair:
                return None
            return f"POINT ({pair})"

        if gtype == "MultiPoint":
            if not isinstance(coords, list) or not coords:
                return None
            parts: list[str] = []
            for pair in coords:
                wkt_pair = _coord_pair_wkt(pair)
                if not wkt_pair:
                    return None
                parts.append(f"({wkt_pair})")
            return "MULTIPOINT (" + ", ".join(parts) + ")"

        if gtype == "LineString":
            if not isinstance(coords, list) or len(coords) < 2:
                return None
            pts: list[str] = []
            for pair in coords:
                wkt_pair = _coord_pair_wkt(pair)
                if not wkt_pair:
                    return None
                pts.append(wkt_pair)
            return "LINESTRING (" + ", ".join(pts) + ")"

        if gtype == "Polygon":
            if not isinstance(coords, list) or not coords:
                return None
            rings_wkt: list[str] = []
            for ring in coords:
                ring_wkt = _ring_coords_wkt(ring)
                if not ring_wkt:
                    return None
                rings_wkt.append(f"({ring_wkt})")
            return "POLYGON (" + ", ".join(rings_wkt) + ")"

        if gtype == "MultiPolygon":
            if not isinstance(coords, list) or not coords:
                return None
            polys: list[str] = []
            for poly in coords:
                if not isinstance(poly, list) or not poly:
                    return None
                rings_wkt = []
                for ring in poly:
                    ring_wkt = _ring_coords_wkt(ring)
                    if not ring_wkt:
                        return None
                    rings_wkt.append(f"({ring_wkt})")
                polys.append("(" + ", ".join(rings_wkt) + ")")
            return "MULTIPOLYGON (" + ", ".join(polys) + ")"
    except Exception:
        return None

    return None


def _geometry_bind_value(session: Session, geometry_json: dict[str, Any]) -> object | None:
    """Return a dialect-appropriate bind value for `SubstrateLocation.geometry`.

    SQLite tests store `geometry` as plain text and cannot bind GeoAlchemy elements.
    Postgres uses true PostGIS geometry via GeoAlchemy's `WKTElement`.
    """

    wkt = _geojson_to_wkt(geometry_json)
    if not wkt:
        return None

    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        from geoalchemy2.elements import WKTElement

        return WKTElement(wkt, srid=4326)

    return wkt


def _find_mention_span(*, haystack: str, needle: str) -> tuple[int, int] | None:
    if not needle:
        return None

    for candidate in _mention_text_span_variants(needle):
        idx = haystack.find(candidate)
        if idx >= 0:
            return idx, idx + len(candidate)

    collapsed_hay = _WS_RE.sub(" ", haystack).strip()
    for candidate in _mention_text_span_variants(needle):
        if not candidate:
            continue
        collapsed_needle = _WS_RE.sub(" ", candidate).strip()
        if not collapsed_needle:
            continue
        idx2 = collapsed_hay.find(collapsed_needle)
        if idx2 >= 0:
            # Approximate mapping back to original indices by scanning for the first token.
            first_token = collapsed_needle.split(" ")[0]
            if first_token:
                idx3 = haystack.find(first_token)
                if idx3 >= 0:
                    return idx3, idx3 + len(candidate)

    return None


def _cache_fingerprint(*, project_id: int, normalized_query: str, location_type: str | None) -> str:
    return _sha256_hex(
        json.dumps(
            {
                "project_id": project_id,
                "normalized_query": normalized_query,
                "location_type": location_type,
            },
            sort_keys=True,
        )
    )


def _upsert_location_cache(
    session: Session,
    *,
    project_id: int,
    query_text: str,
    location_type: str | None,
    entry: dict[str, Any],
    geocode_type: str | None,
    geocode_result: dict[str, Any] | None,
    geometry_json: dict[str, Any] | None,
    geometry_value: object | None,
    geometry_type_str: str | None,
    formatted_address: str | None,
) -> None:
    normalized_query = _normalize_name(query_text)
    if not normalized_query:
        return

    fingerprint = _cache_fingerprint(
        project_id=project_id,
        normalized_query=normalized_query,
        location_type=location_type,
    )

    external_source, external_id = (
        _external_identity_from_geocode_result(geocode_result) if geocode_result else (None, None)
    )

    row = session.exec(
        select(SubstrateLocationCache).where(
            col(SubstrateLocationCache.project_id) == project_id,
            col(SubstrateLocationCache.query_fingerprint) == fingerprint,
        )
    ).first()

    now = _utcnow()
    payload = {
        "places_entry": entry,
        "geocode_result": geocode_result,
    }

    if row is None:
        session.add(
            SubstrateLocationCache(
                project_id=project_id,
                query_text=query_text,
                normalized_query=normalized_query,
                query_fingerprint=fingerprint,
                request_components_json=None,
                external_source=external_source,
                external_id=external_id,
                location_name=query_text,
                location_type=location_type,
                geocode_type=geocode_type,
                formatted_address=formatted_address,
                geometry=geometry_value,
                geometry_type=geometry_type_str,
                geometry_json=geometry_json,
                response_payload_json=payload,
            )
        )
    else:
        row.query_text = query_text
        row.normalized_query = normalized_query
        row.external_source = external_source or row.external_source
        row.external_id = external_id or row.external_id
        row.location_name = query_text
        row.location_type = location_type or row.location_type
        row.geocode_type = geocode_type or row.geocode_type
        row.formatted_address = formatted_address or row.formatted_address
        row.geometry = geometry_value or row.geometry
        row.geometry_type = geometry_type_str or row.geometry_type
        row.geometry_json = geometry_json or row.geometry_json
        row.response_payload_json = payload
        row.updated_at = now
        session.add(row)

    session.flush()


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
) -> SubstrateArticle:
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

    article: SubstrateArticle | None = None
    if url_str:
        article = session.exec(
            select(SubstrateArticle).where(
                col(SubstrateArticle.project_id) == project_id,
                col(SubstrateArticle.url) == url_str,
            )
        ).first()

    if article is None and external_source and external_id:
        article = session.exec(
            select(SubstrateArticle).where(
                col(SubstrateArticle.project_id) == project_id,
                col(SubstrateArticle.external_source) == external_source,
                col(SubstrateArticle.external_id) == external_id,
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
            select(SubstrateArticle).where(
                col(SubstrateArticle.project_id) == project_id,
                col(SubstrateArticle.external_source) == "backfield_text_fingerprint",
                col(SubstrateArticle.external_id) == fingerprint,
            )
        ).first()

    now = _utcnow()
    if article is None:
        text_fingerprint = _sha256_hex(
            json.dumps({"project_id": project_id, "text": text_str}, sort_keys=True)
        )
        resolved_external_id = external_id or text_fingerprint
        article = SubstrateArticle(
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
            select(SubstrateImage).where(
                col(SubstrateImage.article_id) == article_id,
                col(SubstrateImage.image_id) == image_id_str,
            )
        ).first()
        if row is None:
            session.add(
                SubstrateImage(
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
) -> SubstrateLocation | None:
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

    # Status semantics (intentionally simple for now):
    # - provisional: extracted/geocoded-ish row but not editorially confirmed
    # - resolved: geocoder returned a usable identity/geometry payload
    # - needs_review: explicit review bucket / partial failures
    # - failed: explicitly not geocoded / hard failure entries
    status = "provisional"
    if bucket == "needs_review":
        status = "needs_review"
    if geocoded is False:
        status = "failed"
    if geocode_result and geometry_json:
        status = "resolved"

    loc: SubstrateLocation | None = None
    if external_source and external_id:
        loc = session.exec(
            select(SubstrateLocation).where(
                col(SubstrateLocation.project_id) == project_id,
                col(SubstrateLocation.external_source) == external_source,
                col(SubstrateLocation.external_id) == external_id,
            )
        ).first()

    if loc is None:
        loc = session.exec(
            select(SubstrateLocation).where(
                col(SubstrateLocation.project_id) == project_id,
                col(SubstrateLocation.identity_fingerprint) == fingerprint,
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
        loc = SubstrateLocation(
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
        _upsert_location_cache(
            session,
            project_id=project_id,
            query_text=display_name,
            location_type=location_type_str,
            entry=entry,
            geocode_type=geocode_type,
            geocode_result=geocode_result if isinstance(geocode_result, dict) else None,
            geometry_json=geometry_json,
            geometry_value=geometry_value,
            geometry_type_str=geometry_type_str,
            formatted_address=formatted_address,
        )
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
    _upsert_location_cache(
        session,
        project_id=project_id,
        query_text=display_name,
        location_type=location_type_str,
        entry=entry,
        geocode_type=geocode_type,
        geocode_result=geocode_result if isinstance(geocode_result, dict) else None,
        geometry_json=geometry_json,
        geometry_value=geometry_value,
        geometry_type_str=geometry_type_str,
        formatted_address=formatted_address,
    )
    return loc


def _suppress_prior_system_occurrences(
    session: Session,
    *,
    mention_id: int,
    mention_text: str,
) -> None:
    rows = session.exec(
        select(SubstrateLocationMentionOccurrence).where(
            col(SubstrateLocationMentionOccurrence.location_mention_id) == mention_id,
            col(SubstrateLocationMentionOccurrence.mention_text) == mention_text,
            col(SubstrateLocationMentionOccurrence.suppressed).is_(False),
            col(SubstrateLocationMentionOccurrence.source_kind) == "system_extraction",
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
    article_text: str,
    entry: dict[str, Any],
    run_id: str,
    graph_id: str,
    bucket: str,
    occurrence_order: int,
) -> None:
    original_text = entry.get("original_text")
    mention_text = str(original_text).strip() if isinstance(original_text, str) else ""
    if not mention_text:
        mention_text = _display_name_for_place_entry(entry)

    description = entry.get("description")
    description_str = str(description).strip() if isinstance(description, str) else None
    if description_str == "":
        description_str = None

    role = entry.get("role_in_story")
    role_str = str(role).strip() if isinstance(role, str) else None
    if role_str == "":
        role_str = None
    if role_str is None:
        role_str = description_str

    nature_str = _normalize_nature_primary(entry)
    secondary_tags = _parse_nature_secondary_tags(entry)

    # `description` is editorial "why this place matters" context.
    # `role_in_story` is a compact label when PlaceExtract provides it.

    span = _find_mention_span(haystack=article_text, needle=mention_text)

    mention = session.exec(
        select(SubstrateLocationMention).where(
            col(SubstrateLocationMention.article_id) == article_id,
            col(SubstrateLocationMention.location_id) == location_id,
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
        mention = SubstrateLocationMention(
            article_id=article_id,
            location_id=location_id,
            role_in_story=role_str,
            nature=nature_str,
            nature_secondary_tags_json=secondary_tags,
            needs_review=bool(needs_review),
            review_data_json=review_data,
            source_kind="agate_geocode",
            source_details_json={"run_id": run_id, "graph_id": graph_id},
            edited=True,
        )
        session.add(mention)
        session.flush()
    else:
        mention.role_in_story = role_str or mention.role_in_story
        mention.nature = nature_str or mention.nature
        mention.nature_secondary_tags_json = secondary_tags
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

    occurrence = SubstrateLocationMentionOccurrence(
        location_mention_id=int(mention.id),
        source_kind="system_extraction",
        source_details_json={"run_id": run_id, "graph_id": graph_id, "places_bucket": bucket},
        mention_text=mention_text,
        quote_text=None,
        start_char=span[0] if span else None,
        end_char=span[1] if span else None,
        occurrence_order=occurrence_order,
        labels_json=[],
        suppressed=False,
    )
    session.add(occurrence)
    session.flush()


def persist_from_consolidated(
    session: Session,
    *,
    project_id: int,
    graph_id: str,
    run_id: str,
    consolidated: dict[str, Any],
) -> int:
    places = consolidated.get("places")
    if not isinstance(places, dict):
        raise RuntimeError(
            "DBOutput persistence requires consolidated['places'] (GeocodeAgent output)"
        )

    article = _upsert_article(
        session,
        project_id=project_id,
        consolidated=consolidated,
        run_id=run_id,
    )
    _sync_images(session, article_id=int(article.id), consolidated=consolidated)

    article_text = str(consolidated.get("text") or "")
    order = 0
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
            article_text=article_text,
            entry=entry,
            run_id=run_id,
            graph_id=graph_id,
            bucket=bucket,
            occurrence_order=order,
        )
        order += 1

    return int(article.id)
