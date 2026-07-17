"""Shared helpers for substrate-to-canonical name mismatch finders."""

from __future__ import annotations

from dataclasses import dataclass, field

from backfield_db import BackfieldProject
from sqlmodel import Session, select

MAX_MISMATCH_EXAMPLES = 3
LOCATION_NAME_MISMATCH_CHECK_ID = "mismatched-locations"
PERSON_NAME_MISMATCH_CHECK_ID = "mismatched-people"
ORGANIZATION_NAME_MISMATCH_CHECK_ID = "mismatched-organizations"
ORG_TRIGRAM_CANDIDATE_FLOOR = 0.30


@dataclass
class CanonicalMismatchAgg:
    count: int = 0
    examples: list[str] = field(default_factory=list)

    def record(self, substrate_name: str) -> None:
        self.count += 1
        clean = str(substrate_name or "").strip()
        if not clean:
            return
        if clean in self.examples:
            return
        if len(self.examples) >= MAX_MISMATCH_EXAMPLES:
            return
        self.examples.append(clean)


def organization_project_ids(session: Session, *, organization_id: int) -> list[int]:
    rows = session.exec(
        select(BackfieldProject.id).where(BackfieldProject.organization_id == organization_id)
    ).all()
    return [int(row) for row in rows if row is not None]


