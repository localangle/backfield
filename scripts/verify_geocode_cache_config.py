#!/usr/bin/env python3
"""Verify GeocodeAgent cache settings on a graph spec and Stylebook population."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from sqlmodel import Session, col, func, select

from backfield_db import AgateGraph, StylebookLocationAlias, StylebookLocationCanonical
from backfield_db.session import get_engine


def _geocode_nodes(spec: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = spec.get("nodes")
    if not isinstance(nodes, list):
        return []
    return [
        node
        for node in nodes
        if isinstance(node, dict) and str(node.get("type") or "") == "GeocodeAgent"
    ]


def _node_params(node: dict[str, Any]) -> dict[str, Any]:
    params = node.get("params")
    return params if isinstance(params, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-id", required=True, help="Agate graph id (UUID)")
    args = parser.parse_args()

    engine = get_engine()
    with Session(engine) as session:
        graph = session.get(AgateGraph, args.graph_id)
        if graph is None:
            print(f"Graph not found: {args.graph_id}", file=sys.stderr)
            return 1
        spec = json.loads(graph.spec_json)
        geocode_nodes = _geocode_nodes(spec)
        if not geocode_nodes:
            print("No GeocodeAgent nodes found in graph spec.")
            return 1

        ok = True
        stylebook_ids: set[int] = set()
        for idx, node in enumerate(geocode_nodes, start=1):
            params = _node_params(node)
            use_cache = bool(params.get("useCache") or params.get("use_cache"))
            stylebook_id = params.get("stylebookId") or params.get("stylebook_id")
            print(f"GeocodeAgent #{idx} node_id={node.get('id')!r}")
            print(f"  useCache={use_cache}")
            print(f"  stylebookId={stylebook_id}")
            if not use_cache:
                print("  WARNING: useCache is false; DB geocode cache will not attach.")
                ok = False
            if stylebook_id is None:
                print("  WARNING: stylebookId missing; tier-1 Stylebook cache will not run.")
                ok = False
            else:
                try:
                    stylebook_ids.add(int(stylebook_id))
                except (TypeError, ValueError):
                    print(f"  WARNING: invalid stylebookId={stylebook_id!r}")
                    ok = False

        for sid in sorted(stylebook_ids):
            canonical_count = session.exec(
                select(func.count())
                .select_from(StylebookLocationCanonical)
                .where(col(StylebookLocationCanonical.stylebook_id) == sid)
            ).one()
            alias_count = session.exec(
                select(func.count())
                .select_from(StylebookLocationAlias)
                .where(col(StylebookLocationAlias.stylebook_id) == sid)
            ).one()
            print(f"Stylebook {sid}: canonicals={canonical_count}, aliases={alias_count}")
            if int(canonical_count) == 0:
                print("  WARNING: Stylebook has no location canonicals; cache hit rate will be low.")
                ok = False

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
