import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

import { listOperations, mergeOpenApiDocuments, parseOpenApiDocument } from "./openapi"

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../../..")

describe("Playground operation presentation", () => {
  it("uses docs group names, labels, and nav order", () => {
    const document = parseOpenApiDocument({
      openapi: "3.1.0",
      info: { title: "Public API", version: "1" },
      paths: {
        "/public/v1/projects/{project_slug}/articles/geo-cells/query": {
          post: { summary: "Query Project Articles In Geo Cells" },
        },
        "/public/v1/projects/{project_slug}/articles/{article_id}/mentions": {
          get: { summary: "List Project Article Mentions" },
        },
        "/public/v1/projects/{project_slug}/articles/search": {
          get: { summary: "Search Project Articles" },
        },
        "/public/v1/projects/{project_slug}/articles/facets": {
          get: { summary: "Get Project Article Facets" },
        },
        "/public/v1/projects/{project_slug}/runs": {
          post: { summary: "Create Public Run" },
        },
        "/public/v1/projects/{project_slug}": {
          get: { summary: "Get Public Project Metadata" },
        },
        "/public/v1/projects/{project_slug}/people/search": {
          get: { summary: "Search Project People" },
        },
        "/public/v1/projects/{project_slug}/mentions/search": {
          get: { summary: "Search Project Mentions" },
        },
      },
    })

    const operations = listOperations(document)
    expect(
      operations.map((operation) => [
        operation.group,
        operation.summary,
        operation.displayPath,
      ]),
    ).toEqual([
      ["Projects", "Get project", "/project"],
      ["Metadata", "Article facets", "/articles/facets"],
      ["Articles", "List and search", "/articles/search"],
      ["Articles", "List mentions", "/articles/{article_id}/mentions"],
      ["Mentions", "List and search", "/mentions/search"],
      ["People", "List and search", "/people/search"],
      ["Other", "Batch query", "/articles/geo-cells/query"],
    ])
    expect(operations.some((operation) => operation.displayPath === "/runs")).toBe(false)
  })

  it("presents project, entity, and timeline operations with docs names", () => {
    const document = parseOpenApiDocument({
      openapi: "3.1.0",
      info: { title: "Public API", version: "1" },
      paths: {
        "/public/v1/projects/{project_slug}/people/{person_id}/mentions/timeline": {
          get: { summary: "List Project Person Mention Timeline" },
        },
        "/public/v1/projects/{project_slug}/locations/types": {
          get: { summary: "List Project Location Types" },
        },
        "/public/v1/projects/{project_slug}/articles/geo-search": {
          get: { summary: "Search Project Articles By Geo" },
        },
      },
    })

    expect(listOperations(document)).toMatchObject([
      {
        group: "Articles",
        summary: "Geographic search",
        displayPath: "/articles/geo-search",
      },
      {
        group: "Locations",
        summary: "List types",
        displayPath: "/locations/types",
      },
      {
        group: "Other",
        summary: "Get timeline",
        displayPath: "/people/{person_id}/mentions/timeline",
      },
    ])
  })

  it("maps every visible public OpenAPI operation into the docs nav groups", () => {
    const document = parseOpenApiDocument(
      JSON.parse(readFileSync(join(repoRoot, "docs/api/public.openapi.json"), "utf8")),
    )
    const operations = listOperations(document)
    expect(operations).toHaveLength(49)
    expect(operations.map((operation) => operation.group)).toEqual([
      ...Array(1).fill("Projects"),
      ...Array(2).fill("Metadata"),
      ...Array(13).fill("Articles"),
      ...Array(2).fill("Mentions"),
      ...Array(7).fill("People"),
      ...Array(8).fill("Locations"),
      ...Array(7).fill("Organizations"),
      ...Array(9).fill("Other"),
    ])
    expect(
      operations.some(
        (operation) => operation.method === "post" && operation.displayPath === "/runs",
      ),
    ).toBe(false)
    expect(
      operations.every((operation) => !/\b(Public|Project)\b/.test(operation.summary)),
    ).toBe(true)
  })
  describe("preview cleanup operations", () => {
    const readCleanup = () =>
      parseOpenApiDocument(
        JSON.parse(readFileSync(join(repoRoot, "docs/api/cleanup.openapi.json"), "utf8")),
      )

    it("lists the read operations under one group and leaves out the apply operations", () => {
      const operations = listOperations(readCleanup())

      expect(operations).toHaveLength(20)
      expect(operations.every((operation) => operation.group === "Cleanup (preview)")).toBe(true)
      expect(operations.map((operation) => operation.displayPath)).toEqual([
        "/cleanup/capabilities",
        "/cleanup/{entity}/export",
        "/cleanup/{entity}/{canonical_id}/evidence",
        "/cleanup/{entity}/evidence",
        "/cleanup/{entity}/{canonical_id}/compare/{other_id}",
        "/cleanup/{entity}/integrity",
        "/cleanup/{entity}/{canonical_id}/resolution",
        "/cleanup/checks",
        "/cleanup/checks/{check_id}/results",
        "/cleanup/checks/{check_id}/runs",
        "/cleanup/checks/{check_id}/runs/latest",
        "/cleanup/candidates/{entity}",
        "/cleanup/candidates/{entity}/count",
        "/cleanup/candidates/{entity}/types",
        "/cleanup/candidates/{entity}/{candidate_id}/evidence",
        "/cleanup/dismissals",
        "/cleanup/runs",
        "/cleanup/runs/{run_id}",
        "/cleanup/runs/{run_id}/actions",
        "/cleanup/actions/{action_id}",
      ])
      const changing = operations.filter(
        (operation) =>
          operation.method === "post" &&
          (operation.displayPath.endsWith("/merges") ||
            operation.displayPath === "/cleanup/runs" ||
            operation.displayPath.endsWith("/close")),
      )
      expect(changing).toEqual([])
      expect(new Set(operations.map((operation) => operation.summary)).size).toBe(20)
      expect(
        operations.every(
          (operation) => !/\b(Cleanup|Public|Project)\b/.test(operation.summary),
        ),
      ).toBe(true)
    })

    it("lists them after the public groups once the two documents are merged", () => {
      const publicDocument = parseOpenApiDocument(
        JSON.parse(readFileSync(join(repoRoot, "docs/api/public.openapi.json"), "utf8")),
      )
      const merged = mergeOpenApiDocuments(publicDocument, readCleanup())
      const operations = listOperations(merged)

      expect(operations).toHaveLength(69)
      expect(operations.slice(0, 49).some((o) => o.group === "Cleanup (preview)")).toBe(false)
      expect(operations.slice(49).every((o) => o.group === "Cleanup (preview)")).toBe(true)
    })

    it("keeps shared schemas identical so one document can resolve both", () => {
      const publicDocument = parseOpenApiDocument(
        JSON.parse(readFileSync(join(repoRoot, "docs/api/public.openapi.json"), "utf8")),
      )
      const publicSchemas = (publicDocument.components as { schemas: Record<string, unknown> })
        .schemas
      const cleanupSchemas = (readCleanup().components as { schemas: Record<string, unknown> })
        .schemas
      for (const name of Object.keys(cleanupSchemas)) {
        if (name in publicSchemas) {
          expect(cleanupSchemas[name], name).toEqual(publicSchemas[name])
        }
      }
    })

    it("lets the base document win when both define a path or schema", () => {
      const base = parseOpenApiDocument({
        openapi: "3.1.0",
        info: { title: "Base", version: "1" },
        paths: { "/a": { get: { summary: "base" } } },
        components: { schemas: { Shared: { type: "string" } } },
      })
      const extra = parseOpenApiDocument({
        openapi: "3.1.0",
        info: { title: "Extra", version: "1" },
        paths: { "/a": { get: { summary: "extra" } }, "/b": { get: { summary: "extra b" } } },
        components: { schemas: { Shared: { type: "number" }, Added: { type: "object" } } },
      })

      const merged = mergeOpenApiDocuments(base, extra)

      expect(Object.keys(merged.paths).sort()).toEqual(["/a", "/b"])
      expect((merged.paths["/a"] as { get: { summary: string } }).get.summary).toBe("base")
      expect(merged.components).toEqual({
        schemas: { Shared: { type: "string" }, Added: { type: "object" } },
      })
    })
  })
})
