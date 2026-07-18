import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"

import { listOperations, parseOpenApiDocument, resolveInputSchema } from "../lib/openapi"
import EndpointExplorer from "./EndpointExplorer"

describe("OpenAPI parsing and endpoint rendering", () => {
  afterEach(cleanup)

  it("resolves component parameters and renders schema-driven inputs", () => {
    const document = parseOpenApiDocument({
      openapi: "3.1.0",
      info: { title: "Public API", version: "1.2.0" },
      components: {
        parameters: {
          Limit: {
            name: "limit",
            in: "query",
            description: "Maximum results",
            schema: { type: "integer" },
          },
        },
      },
      paths: {
        "/articles": {
          post: {
            tags: ["Articles"],
            summary: "Create article",
            parameters: [{ $ref: "#/components/parameters/Limit" }],
            requestBody: {
              required: true,
              content: {
                "application/json": {
                  schema: {
                    type: "object",
                    properties: { title: { type: "string", example: "City council meets" } },
                  },
                },
              },
            },
          },
        },
      },
    })
    const operation = listOperations(document)[0]

    expect(operation.group).toBe("Other")
    expect(operation.summary).toBe("Create article")
    expect(operation.parameters[0].name).toBe("limit")
    render(
      <EndpointExplorer
        document={document}
        operation={operation}
        origin="https://api.news.backfield.news"
        apiKey=""
      />,
    )

    expect(screen.getByRole("heading", { name: "Create article" })).toBeInTheDocument()
    expect(screen.getByLabelText(/limit/)).toBeInTheDocument()
    const bodyInput = screen.getByLabelText(/JSON request body/) as HTMLTextAreaElement
    expect(bodyInput.value).toContain("City council meets")
  })

  it("renders article search as an aligned, constrained form", () => {
    const document = parseOpenApiDocument({
      openapi: "3.1.0",
      info: { title: "Public API", version: "1.2.0" },
      components: {
        schemas: {
          ArticleSort: { type: "string", enum: ["relevance", "pub_date"] },
          SortDirection: { type: "string", enum: ["asc", "desc"] },
        },
      },
      paths: {
        "/public/v1/projects/{project_slug}/articles/search": {
          get: {
            summary: "Search Project Articles",
            parameters: [
              {
                name: "project_slug",
                in: "path",
                required: true,
                schema: { type: "string" },
              },
              {
                name: "q",
                in: "query",
                schema: { anyOf: [{ type: "string" }, { type: "null" }] },
              },
              {
                name: "has_mentions",
                in: "query",
                schema: { anyOf: [{ type: "string" }, { type: "null" }] },
              },
              {
                name: "pub_date_from",
                in: "query",
                schema: { anyOf: [{ type: "string" }, { type: "null" }] },
              },
              {
                name: "sort",
                in: "query",
                schema: {
                  anyOf: [{ $ref: "#/components/schemas/ArticleSort" }, { type: "null" }],
                },
              },
              {
                name: "sort_direction",
                in: "query",
                schema: {
                  anyOf: [{ $ref: "#/components/schemas/SortDirection" }, { type: "null" }],
                },
              },
              {
                name: "limit",
                in: "query",
                schema: { type: "integer", default: 25, minimum: 1, maximum: 100 },
              },
              {
                name: "meta",
                in: "query",
                schema: { type: "array", items: { type: "string" }, default: [] },
              },
            ],
          },
        },
      },
    })
    const operation = listOperations(document)[0]
    const limitParameter = operation.parameters.find(
      (parameter) => parameter.name === "limit",
    )
    expect(resolveInputSchema(document, limitParameter?.schema)).toMatchObject({
      type: "integer",
      minimum: 1,
      maximum: 100,
    })
    render(
      <EndpointExplorer
        document={document}
        operation={operation}
        origin="https://api.news.backfield.news"
        apiKey=""
        projectOptions={[
          {
            value: "daily-news",
            label: "Daily News (daily-news)",
            group: "Editorial",
          },
          {
            value: "weekend-edition",
            label: "Weekend Edition (weekend-edition)",
            group: "Editorial",
          },
        ]}
      />,
    )

    expect(screen.getByRole("heading", { name: "Search and filters" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Sort and page" })).toBeInTheDocument()

    const project = screen.getByLabelText(/project_slug/) as HTMLSelectElement
    expect(project.tagName).toBe("SELECT")
    expect(project.querySelector("optgroup")).toHaveAttribute("label", "Editorial")
    expect(Array.from(project.options).map((option) => option.value)).toEqual([
      "",
      "daily-news",
      "weekend-edition",
    ])

    const mentionType = screen.getByLabelText(/has_mentions/) as HTMLSelectElement
    expect(mentionType.tagName).toBe("SELECT")
    expect(Array.from(mentionType.options).map((option) => option.value)).toEqual([
      "",
      "location",
      "person",
      "organization",
    ])

    const sort = globalThis.document.getElementById(
      "parameter-query-sort",
    ) as HTMLSelectElement
    expect(Array.from(sort.options).map((option) => option.value)).toEqual([
      "",
      "relevance",
      "pub_date",
    ])
    expect(screen.getByLabelText(/sort_direction/)).toHaveValue("")

    expect(screen.getByLabelText(/pub_date_from/)).toHaveAttribute("type", "date")
    expect(screen.getByLabelText(/limit/)).toHaveAttribute("type", "number")
    expect(screen.getByLabelText(/limit/)).toHaveAttribute("min", "1")
    expect(screen.getByLabelText(/limit/)).toHaveAttribute("max", "100")
    expect(screen.getByLabelText(/limit/)).toHaveAttribute("placeholder", "Default: 25")
    expect(screen.getByLabelText(/meta/).getAttribute("placeholder")).toContain("topic:politics")
    expect(
      globalThis.document
        .getElementById("parameter-query-q")
        ?.closest(".parameter-field"),
    ).toHaveClass("parameter-field-wide")
  })

  it("rejects malformed schema documents", () => {
    expect(() => parseOpenApiDocument({ openapi: "3.1.0" })).toThrow("invalid OpenAPI")
  })
})
