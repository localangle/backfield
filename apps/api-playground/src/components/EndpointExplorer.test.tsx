import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { listOperations, parseOpenApiDocument, resolveInputSchema } from "../lib/openapi"
import EndpointExplorer from "./EndpointExplorer"

describe("OpenAPI parsing and endpoint rendering", () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

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
    expect(screen.getByText("Request body")).toBeInTheDocument()
    expect(screen.getByLabelText(/title/)).toHaveValue("City council meets")
    expect(screen.getByRole("button", { name: "Edit as JSON" })).toBeInTheDocument()
  })

  it("renders article search as an aligned, constrained form", async () => {
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
                name: "author",
                in: "query",
                description: "Filter by byline",
                schema: { anyOf: [{ type: "string" }, { type: "null" }] },
              },
              {
                name: "external_source",
                in: "query",
                description: "Filter by publication or outlet",
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
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockImplementation(async (input) => {
        const url = String(input)
        if (url.endsWith("/articles/facets")) {
          return new Response(
            JSON.stringify({
              authors: ["Jane Doe", "Sam Rivera"],
              external_sources: ["Springfield Daily", "Wire Service"],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          )
        }
        if (url.endsWith("/articles/metadata/types")) {
          return new Response(
            JSON.stringify({ meta_types: ["topic", "format"] }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          )
        }
        if (url.includes("/articles/metadata/types/")) {
          return new Response(
            JSON.stringify({
              meta_type: "topic",
              values: ["local_government_politics", "public_safety"],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          )
        }
        throw new Error(`Unexpected request: ${url}`)
      }),
    )
    render(
      <EndpointExplorer
        document={document}
        operation={operation}
        origin="https://api.news.backfield.news"
        apiKey="project-key"
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

    expect(screen.getByRole("heading", { name: "Search" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Filters" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Sort and page" })).toBeInTheDocument()

    const project = screen.getByLabelText(/project_slug/) as HTMLSelectElement
    expect(project.tagName).toBe("SELECT")
    expect(
      project.closest(".parameter-field")?.querySelector(".required-badge"),
    ).toHaveTextContent("Required")
    expect(project.querySelector("optgroup")).toHaveAttribute("label", "Editorial")
    expect(Array.from(project.options).map((option) => option.value)).toEqual([
      "",
      "daily-news",
      "weekend-edition",
    ])
    fireEvent.change(project, { target: { value: "daily-news" } })

    const author = screen.getByLabelText(/author/) as HTMLSelectElement
    expect(author.tagName).toBe("SELECT")
    expect(await screen.findByRole("option", { name: "Jane Doe" })).toBeInTheDocument()
    expect(Array.from(author.options).map((option) => option.value)).toEqual([
      "",
      "Jane Doe",
      "Sam Rivera",
    ])
    expect(screen.getByLabelText(/external_source/)).toHaveTextContent("Springfield Daily")

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

    // The meta parameter renders the visual condition builder instead of a textarea.
    const addCondition = await screen.findByRole("button", { name: "Add condition" })
    fireEvent.click(addCondition)
    const metaType = await screen.findByLabelText("Metadata type")
    expect(Array.from((metaType as HTMLSelectElement).options).map((o) => o.value)).toEqual([
      "topic",
      "format",
    ])
    expect(screen.getByLabelText("Condition operator")).toBeInTheDocument()
    const categoryTrigger = screen.getByRole("button", { name: /Categories for condition/ })
    fireEvent.click(categoryTrigger)
    const option = await screen.findByRole("checkbox", {
      name: "Local government politics",
    })
    fireEvent.click(option)
    expect(screen.getByText("topic:local_government_politics")).toBeInTheDocument()
    expect(
      globalThis.document
        .getElementById("parameter-query-q")
        ?.closest(".parameter-field"),
    ).toHaveClass("parameter-field-wide")
  })

  it("renders request-body properties with the shared controls and raw JSON escape hatch", () => {
    const document = parseOpenApiDocument({
      openapi: "3.1.0",
      info: { title: "Public API", version: "1.2.0" },
      paths: {
        "/public/v1/projects/{project_slug}/articles/semantic-search": {
          post: {
            summary: "Semantic search",
            parameters: [
              {
                name: "project_slug",
                in: "path",
                required: true,
                schema: { type: "string" },
              },
            ],
            requestBody: {
              required: true,
              content: {
                "application/json": {
                  schema: {
                    type: "object",
                    required: ["query"],
                    properties: {
                      query: {
                        type: "string",
                        minLength: 1,
                        example: "city budget",
                      },
                      use_hyde: { type: "boolean", default: false },
                      limit: {
                        type: "integer",
                        default: 25,
                        minimum: 1,
                        maximum: 100,
                      },
                    },
                  },
                },
              },
            },
          },
        },
      },
    })
    const operation = listOperations(document)[0]
    render(
      <EndpointExplorer
        document={document}
        operation={operation}
        origin="https://api.news.backfield.news"
        apiKey=""
      />,
    )

    expect(screen.getByRole("heading", { name: "Search" })).toBeInTheDocument()
    expect(screen.getByLabelText(/query/)).toHaveValue("city budget")
    expect(screen.getByLabelText(/use_hyde/).tagName).toBe("SELECT")
    expect(screen.getByLabelText(/limit/)).toHaveAttribute("type", "number")

    fireEvent.click(screen.getByRole("button", { name: "Edit as JSON" }))
    const rawBody = screen.getByRole("textbox") as HTMLTextAreaElement
    expect(rawBody.value).toContain('"query": "city budget"')
  })

  it("clears request validation errors when form values change", async () => {
    const document = parseOpenApiDocument({
      openapi: "3.1.0",
      info: { title: "Public API", version: "1.2.0" },
      paths: {
        "/public/v1/projects/{project_slug}/articles/semantic-search": {
          post: {
            summary: "Semantic search",
            parameters: [
              {
                name: "limit",
                in: "query",
                schema: { type: "integer", minimum: 1, maximum: 100 },
              },
            ],
            requestBody: {
              required: true,
              content: {
                "application/json": {
                  schema: {
                    type: "object",
                    required: ["query"],
                    properties: {
                      query: { type: "string", example: "city budget" },
                    },
                  },
                },
              },
            },
          },
        },
      },
    })
    const operation = listOperations(document)[0]
    render(
      <EndpointExplorer
        document={document}
        operation={operation}
        origin="https://api.news.backfield.news"
        apiKey="project-key"
      />,
    )

    fireEvent.change(screen.getByLabelText(/limit/), { target: { value: "0" } })
    fireEvent.click(screen.getByRole("button", { name: "Execute request" }))
    expect(screen.getByRole("alert")).toHaveTextContent("limit must be at least 1.")

    fireEvent.change(screen.getByLabelText(/limit/), { target: { value: "25" } })
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument())

    fireEvent.click(screen.getByRole("button", { name: "Edit as JSON" }))
    fireEvent.change(screen.getByLabelText("JSON request body"), {
      target: { value: "{" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Execute request" }))
    expect(screen.getByRole("alert")).toHaveTextContent("Request body must be valid JSON.")

    fireEvent.change(screen.getByLabelText("JSON request body"), {
      target: { value: '{"query":"city budget"}' },
    })
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument())
  })

  it("adds a map selector to geographic search parameters", async () => {
    const document = parseOpenApiDocument({
      openapi: "3.1.0",
      info: { title: "Public API", version: "1.2.0" },
      paths: {
        "/public/v1/projects/{project_slug}/articles/geo-search": {
          get: {
            summary: "Geographic search",
            parameters: [
              {
                name: "project_slug",
                in: "path",
                required: true,
                schema: { type: "string" },
              },
              { name: "center_lng", in: "query", schema: { type: "number" } },
              { name: "center_lat", in: "query", schema: { type: "number" } },
              { name: "radius_miles", in: "query", schema: { type: "number" } },
              { name: "bbox", in: "query", schema: { type: "string" } },
            ],
          },
        },
      },
    })
    const operation = listOperations(document)[0]

    render(
      <EndpointExplorer
        document={document}
        operation={operation}
        origin="https://api.news.backfield.news"
        apiKey=""
      />,
    )

    expect(await screen.findByLabelText("Geographic area map")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Bounding box" })).toHaveAttribute(
      "aria-pressed",
      "true",
    )
    expect(screen.getByRole("button", { name: "Point and radius" })).toBeInTheDocument()
    expect(screen.getByLabelText(/bbox/)).toBeInTheDocument()
  })

  it("rejects malformed schema documents", () => {
    expect(() => parseOpenApiDocument({ openapi: "3.1.0" })).toThrow("invalid OpenAPI")
  })
})
