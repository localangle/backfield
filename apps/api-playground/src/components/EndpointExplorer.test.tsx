import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { listOperations, parseOpenApiDocument } from "../lib/openapi"
import EndpointExplorer from "./EndpointExplorer"

describe("OpenAPI parsing and endpoint rendering", () => {
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

    expect(operation.group).toBe("Articles")
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

  it("rejects malformed schema documents", () => {
    expect(() => parseOpenApiDocument({ openapi: "3.1.0" })).toThrow("invalid OpenAPI")
  })
})
