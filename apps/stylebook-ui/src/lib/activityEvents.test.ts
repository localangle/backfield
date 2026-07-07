import { describe, expect, it } from "vitest"

import { buildActivityEventSummary, formatActivityEventType } from "./activityEvents"
import type { StylebookActivityEvent } from "./stylebook-api/activity"

const BASE = "/stylebook/demo-sb"
const SCOPE = "?project=demo-proj"

function activityEvent(
  overrides: Partial<StylebookActivityEvent>,
): StylebookActivityEvent {
  return {
    id: 1,
    stylebook_id: 1,
    actor_type: "system",
    source: "ingest_pipeline",
    event_type: "canonical_created",
    created_at: "2026-07-07T18:25:44.000Z",
    ...overrides,
  }
}

describe("activityEvents helpers", () => {
  it("title-cases event types", () => {
    expect(formatActivityEventType("canonical_created")).toBe("Canonical Created")
    expect(formatActivityEventType("cleanup_merge")).toBe("Cleanup Merge")
  })

  it("links canonical created events without showing substrate ids", () => {
    const summary = buildActivityEventSummary(
      activityEvent({
        event_type: "canonical_created",
        entity_type: "organization",
        entity_id: "15435",
        entity_label: "Chicago city officials",
        related_entity_type: "organization",
        related_entity_id: "99001",
      }),
      BASE,
      SCOPE,
    )

    expect(summary.title).toBe("Canonical Created")
    expect(summary.primary).toEqual({
      label: "Chicago city officials",
      href: `${BASE}/organizations/canonical/15435${SCOPE}`,
    })
    expect(summary.related).toBeNull()
  })

  it("links cleanup merge source and target canonicals", () => {
    const summary = buildActivityEventSummary(
      activityEvent({
        event_type: "cleanup_merge",
        entity_type: "location",
        entity_id: "loc-a",
        entity_label: "Bridgeview, IL",
        related_entity_type: "location",
        related_entity_id: "loc-b",
        related_entity_label: "Bridgeview Village, Bridgeview, IL",
      }),
      BASE,
      SCOPE,
    )

    expect(summary.primary?.href).toBe(`${BASE}/locations/canonical/loc-a${SCOPE}`)
    expect(summary.related?.href).toBe(`${BASE}/locations/canonical/loc-b${SCOPE}`)
  })

  it("omits bare ids when labels are missing", () => {
    const summary = buildActivityEventSummary(
      activityEvent({
        entity_type: "location",
        entity_id: "15683",
        entity_label: null,
      }),
      BASE,
      SCOPE,
    )

    expect(summary.primary).toBeNull()
    expect(summary.related).toBeNull()
  })

  it("links substrate linked events to the canonical", () => {
    const summary = buildActivityEventSummary(
      activityEvent({
        event_type: "substrate_linked",
        entity_type: "person",
        entity_id: "substrate-1",
        entity_label: "Matas Buzelis",
        related_entity_type: "person",
        related_entity_id: "person-canonical-1",
      }),
      BASE,
      SCOPE,
    )

    expect(summary.primary).toBeNull()
    expect(summary.related).toEqual({
      label: "Matas Buzelis",
      href: `${BASE}/people/canonical/person-canonical-1${SCOPE}`,
    })
  })
})
