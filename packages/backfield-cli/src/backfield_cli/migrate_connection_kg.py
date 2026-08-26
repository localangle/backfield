"""CLI: remap/merge stylebook_connections into Phase A KG shape (evidence children)."""

from __future__ import annotations

import argparse
import json
import logging

from backfield_db.session import get_engine
from backfield_entities.connections.migrate_kg_phase_a import migrate_connections_kg_phase_a
from sqlmodel import Session

from backfield_cli.console import CONSOLE

logger = logging.getLogger(__name__)


def register_subcommand(subparsers) -> None:
    parser = subparsers.add_parser(
        "migrate-connection-kg",
        help=(
            "Phase A knowledge-graph connection migration: inventory, nature remaps, "
            "and duplicate-edge merges that reattach evidence to survivors; "
            "078 materializes remaining evidence_json (default dry-run)"
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit remaps, merges, and evidence reattachment (default is dry-run)",
    )
    parser.add_argument(
        "--inventory-only",
        action="store_true",
        help="Only print inventory counts; do not remap or merge",
    )
    parser.add_argument(
        "--stylebook-id",
        type=int,
        default=None,
        help="Limit migration to one Stylebook id",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the migration report as JSON",
    )
    parser.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    try:
        with Session(get_engine()) as session:
            report = migrate_connections_kg_phase_a(
                session,
                apply=bool(args.apply),
                inventory_only=bool(args.inventory_only),
                stylebook_id=args.stylebook_id,
            )
    except Exception as error:
        logger.error("Connection KG migration failed: %s", error)
        CONSOLE.print(f"[red]Connection KG migration failed: {error}[/red]")
        return 2

    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return 0

    mode = "apply" if report.apply else "dry-run"
    if report.inventory_only:
        mode = f"inventory ({mode})"
    CONSOLE.print(f"[bold]Connection KG migration ({mode})[/bold]")
    if report.stylebook_id is not None:
        CONSOLE.print(f"  stylebook_id: {report.stylebook_id}")
    CONSOLE.print(f"  connections: {report.connection_total}")
    CONSOLE.print(f"  null nature: {report.null_nature_count}")
    CONSOLE.print(f"  with evidence_json: {report.with_evidence_json}")
    CONSOLE.print(f"  without evidence_json: {report.without_evidence_json}")
    CONSOLE.print(f"  open edge groups (post-plan): {report.open_edge_groups}")
    if not report.inventory_only:
        would = "" if report.apply else "would "
        CONSOLE.print(f"  {would}backfill stylebook_id: {report.stylebook_id_backfilled}")
        CONSOLE.print(f"  {would}remap: {report.remapped}")
        CONSOLE.print(f"  {would}quarantine: {report.quarantined}")
        CONSOLE.print(f"  merge groups: {report.merge_groups}")
        CONSOLE.print(f"  {would}delete duplicates: {report.duplicates_deleted}")
        CONSOLE.print(f"  {would}move evidence to survivors: {report.evidence_moved}")
        CONSOLE.print(f"  {would}skip existing evidence: {report.evidence_skipped_existing}")
    if report.by_nature_pair:
        CONSOLE.print("[bold]Top nature×pair counts[/bold]")
        for key, count in list(report.by_nature_pair.items())[:20]:
            CONSOLE.print(f"  {count:5d}  {key}")
    if report.remap_samples:
        CONSOLE.print("[yellow]Remap samples[/yellow]")
        for sample in report.remap_samples[:10]:
            CONSOLE.print(
                f"  id={sample['id']} {sample['reason']}: "
                f"{sample['nature_before']!r} -> {sample['nature_after']!r}"
            )
    if report.quarantine_samples:
        CONSOLE.print("[yellow]Quarantine samples[/yellow]")
        for sample in report.quarantine_samples[:10]:
            CONSOLE.print(f"  id={sample['id']} {sample['reason']}: {sample['description']!r}")
    return 0
