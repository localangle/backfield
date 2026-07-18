import { describe, expect, it } from "vitest"

import { listOperations, parseOpenApiDocument } from "./openapi"

describe("Playground operation presentation", () => {
  it("groups public operations by resource and removes the repeated project prefix", () => {
    const document = parseOpenApiDocument({
      openapi: "3.1.0",
      info: { title: "Public API", version: "1" },
      paths: {
        "/public/v1/projects/{project_slug}/articles/{article_id}/mentions": {
          get: {
            tags: ["public"],
            summary: "List Project Article Mentions",
          },
        },
      },
    })

    expect(listOperations(document)[0]).toMatchObject({
      group: "Articles",
      displayPath: "/articles/{article_id}/mentions",
      summary: "List Article Mentions",
    })
  })

  it("presents the project metadata operation as a project resource", () => {
    const document = parseOpenApiDocument({
      openapi: "3.1.0",
      info: { title: "Public API", version: "1" },
      paths: {
        "/public/v1/projects/{project_slug}": {
          get: {
            tags: ["public"],
            summary: "Get Public Project Metadata",
          },
        },
      },
    })

    expect(listOperations(document)[0]).toMatchObject({
      group: "Project",
      displayPath: "/project",
      summary: "Get Project Metadata",
    })
  })
})
