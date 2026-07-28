import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

import { listOperations, parseOpenApiDocument } from "./openapi"

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
    expect(operations).toHaveLength(47)
    expect(operations.map((operation) => operation.group)).toEqual([
      ...Array(1).fill("Projects"),
      ...Array(2).fill("Metadata"),
      ...Array(13).fill("Articles"),
      ...Array(2).fill("Mentions"),
      ...Array(7).fill("People"),
      ...Array(8).fill("Locations"),
      ...Array(7).fill("Organizations"),
      ...Array(7).fill("Other"),
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
})
