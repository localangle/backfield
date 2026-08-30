import { describe, expect, it } from "vitest"

import {
  bundleEdgeLabel,
  classifyConnectionHop,
  connectionsTouchingEntity,
  dedupeConnections,
  egoGraphLayoutMetrics,
  formatNatureLabel,
  gridColumns,
  groupConnectionsByDirectedEdge,
  layoutNeighborGrid,
  neighborFromConnection,
  otherEndFromConnection,
  selectConnectionsForGraphDisplay,
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

  it("prioritizes organizations when capping graph display", () => {
    const center: GraphEntityRef = {
      entityType: "person",
      entityId: "peggy",
      displayName: "Peggy Buffington",
    }
    const rows = [
      conn({
        id: 1,
        from_entity_id: "peggy",
        to_entity_type: "location",
        to_entity_id: "l1",
        to_display_name: "Alpha Loc",
      }),
      conn({
        id: 2,
        from_entity_id: "peggy",
        to_entity_id: "o1",
        to_display_name: "Zeta Org",
      }),
      conn({
        id: 3,
        from_entity_id: "peggy",
        to_entity_type: "person",
        to_entity_id: "p1",
        to_display_name: "Beta Person",
      }),
    ]
    const { selected, displayedNeighborCount, skippedNeighborCount } =
      selectConnectionsForGraphDisplay(rows, center, 2)
    expect(displayedNeighborCount).toBe(2)
    expect(skippedNeighborCount).toBe(1)
    expect(selected.map((row) => row.to_entity_id)).toEqual(["o1", "p1"])
  })

  it("classifies direct connections as hop 1 and others as hop 0", () => {
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
    ).toBe(0)
  })

  it("lays out neighbors in a compact grid above the center", () => {
    expect(gridColumns(1)).toBe(1)
    expect(gridColumns(5)).toBe(3)
    expect(gridColumns(20)).toBe(5)

    const keys = ["organization:o1", "person:p1", "location:l1"]
    const positions = layoutNeighborGrid(keys, 500, 48)
    expect(positions.size).toBe(3)
    expect(positions.get("organization:o1")).toEqual({ x: 310, y: 48 })
    expect(positions.get("person:p1")).toEqual({ x: 514, y: 48 })
    expect(positions.get("location:l1")).toEqual({ x: 412, y: 140 })

    const metrics = egoGraphLayoutMetrics(3)
    expect(metrics.centerX).toBe(500)
    expect(metrics.neighborTopY).toBe(48)
    expect(metrics.centerY).toBeGreaterThan(metrics.neighborTopY)
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

  it("groups parallel connections into one directed edge bundle", () => {
    const rows = [
      conn({
        id: 10,
        from_entity_id: "charles",
        from_display_name: "Charles Hughes",
        to_entity_id: "chamber",
        to_display_name: "Gary Chamber of Commerce",
        nature: "works_for",
      }),
      conn({
        id: 11,
        from_entity_id: "charles",
        from_display_name: "Charles Hughes",
        to_entity_id: "chamber",
        to_display_name: "Gary Chamber of Commerce",
        nature: "leads",
      }),
      conn({
        id: 12,
        from_entity_type: "organization",
        from_entity_id: "chamber",
        to_entity_type: "person",
        to_entity_id: "charles",
        nature: "employs",
      }),
    ]
    const groups = groupConnectionsByDirectedEdge(rows)
    expect(groups.size).toBe(2)
    expect(groups.get("person:charles->organization:chamber")?.map((row) => row.id)).toEqual([
      10, 11,
    ])
    expect(bundleEdgeLabel(groups.get("person:charles->organization:chamber")!)).toBe(
      "works for · leads",
    )
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
