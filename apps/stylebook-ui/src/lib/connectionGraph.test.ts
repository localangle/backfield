import { describe, expect, it } from "vitest"

import {
  classifyConnectionHop,
  connectionsTouchingEntity,
  dedupeConnections,
  formatNatureLabel,
  neighborFromConnection,
  otherEndFromConnection,
  selectNeighborsForHop2Expansion,
  type GraphEntityRef,
} from "@/lib/connectionGraph"
import type { Connection } from "@/lib/stylebook-api/connections"

function conn(partial: Partial<Connection> & Pick<Connection, "id">): Connection {
  return {
    from_entity_type: "person",
    from_entity_id: "p1",
    from_display_name: "Person One",
    to_entity_type: "organization",
    to_entity_id: "o1",
    to_display_name: "Org One",
    ...partial,
  }
}

describe("connectionGraph", () => {
  it("finds the neighbor on the other end of a center connection", () => {
    const center: GraphEntityRef = {
      entityType: "person",
      entityId: "peggy",
      displayName: "Peggy Buffington",
    }
    const neighbor = neighborFromConnection(
      conn({
        id: 1,
        from_entity_type: "person",
        from_entity_id: "peggy",
        from_display_name: "Peggy Buffington",
        to_entity_type: "organization",
        to_entity_id: "hobart",
        to_display_name: "School City of Hobart",
        nature: "works_for",
      }),
      center,
    )
    expect(neighbor).toEqual({
      entityType: "organization",
      entityId: "hobart",
      displayName: "School City of Hobart",
    })
  })

  it("dedupes connections by id", () => {
    const rows = dedupeConnections([conn({ id: 1 }), conn({ id: 1, nature: "leads" }), conn({ id: 2 })])
    expect(rows).toHaveLength(2)
    expect(rows.map((r) => r.id)).toEqual([1, 2])
  })

  it("prioritizes organizations when capping hop-2 expansion", () => {
    const neighbors: GraphEntityRef[] = [
      { entityType: "location", entityId: "l1", displayName: "Alpha Loc" },
      { entityType: "organization", entityId: "o1", displayName: "Zeta Org" },
      { entityType: "person", entityId: "p1", displayName: "Beta Person" },
    ]
    const { selected, skipped } = selectNeighborsForHop2Expansion(neighbors, 2)
    expect(selected.map((n) => n.entityId)).toEqual(["o1", "p1"])
    expect(skipped).toBe(1)
  })

  it("classifies hop-1 vs hop-2 edges", () => {
    const center = { entityType: "person" as const, entityId: "peggy" }
    expect(
      classifyConnectionHop(
        conn({
          id: 1,
          from_entity_id: "peggy",
          to_entity_id: "hobart",
        }),
        center,
      ),
    ).toBe(1)
    expect(
      classifyConnectionHop(
        conn({
          id: 2,
          from_entity_id: "hobart",
          to_entity_id: "district",
          to_entity_type: "organization",
          to_display_name: "District",
        }),
        center,
      ),
    ).toBe(2)
  })

  it("formats nature labels for display", () => {
    expect(formatNatureLabel("member_of")).toBe("member of")
    expect(formatNatureLabel("")).toBeNull()
  })

  it("finds the other end of a connection", () => {
    const row = conn({
      id: 3,
      from_entity_id: "alex",
      from_display_name: "Alex Bregman",
      to_entity_id: "cubs",
      to_display_name: "Chicago Cubs",
      nature: "member_of",
    })
    expect(
      otherEndFromConnection(row, { entityType: "person", entityId: "alex" }),
    ).toEqual({
      entityType: "organization",
      entityId: "cubs",
      displayName: "Chicago Cubs",
    })
  })

  it("lists connections touching an entity", () => {
    const rows = [
      conn({
        id: 1,
        from_entity_type: "organization",
        from_entity_id: "x",
        to_entity_type: "person",
        to_entity_id: "b",
      }),
      conn({
        id: 2,
        from_entity_type: "person",
        from_entity_id: "b",
        to_entity_type: "organization",
        to_entity_id: "c",
        to_display_name: "C",
      }),
      conn({ id: 3, from_entity_id: "p1", to_entity_id: "o1" }),
    ]
    expect(
      connectionsTouchingEntity(rows, { entityType: "person", entityId: "b" }).map((r) => r.id),
    ).toEqual([1, 2])
  })
})
