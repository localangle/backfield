"""Token helpers for co-mention windows and affiliation matching."""

from __future__ import annotations

from backfield_entities.entities.organization.types import normalize_organization_text


def organization_match_tokens(label: str | None) -> tuple[str, ...]:
    """Searchable normalized tokens for an organization label (nickname + full form)."""
    norm = normalize_organization_text(label)
    if not norm:
        return ()
    tokens: list[str] = [norm]
    parts = norm.split()
    if len(parts) > 1:
        last = parts[-1]
        if last and last not in tokens:
            tokens.append(last)
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return tuple(out)


def person_affiliation_matches_organization_label(
    affiliation: str | None,
    organization_label: str | None,
) -> bool:
    """True when a person's affiliation clearly names the organization."""
    aff = normalize_organization_text(affiliation)
    org_label = normalize_organization_text(organization_label)
    if not aff or not org_label:
        return False
    if aff == org_label:
        return True
    org_parts = org_label.split()
    if len(org_parts) > 1 and aff == org_parts[-1]:
        # Team nickname before player name (e.g. Phillies → Philadelphia Phillies).
        return True
    return False


def entity_comention_tokens(
    *,
    label: str | None,
    affiliation: str | None = None,
) -> tuple[str, ...]:
    """Case-folded tokens used to detect co-mentions in article windows."""
    tokens: list[str] = []
    for source in (label, affiliation):
        tokens.extend(organization_match_tokens(source))
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return tuple(out)
