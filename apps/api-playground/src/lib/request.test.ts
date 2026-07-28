import { describe, expect, it } from "vitest"

import { listOperations, parseOpenApiDocument } from "./openapi"
import { prepareRequest } from "./request"

const document = parseOpenApiDocument({
  openapi: "3.1.0",
  info: { title: "Test API", version: "1" },
  paths: {
    "/articles/{article_id}": {
      get: {
        summary: "Get an article",
        parameters: [
          {
            name: "article_id",
            in: "path",
            required: true,
            schema: { type: "string" },
          },
          {
            name: "topic",
            in: "query",
            schema: { type: "array", items: { type: "string" } },
          },
          {
            name: "X-Test",
            in: "header",
            schema: { type: "string" },
          },
          {
            name: "sort",
            in: "query",
            schema: { type: "string", enum: ["relevance", "pub_date"] },
          },
          {
            name: "limit",
            in: "query",
            schema: { type: "integer", minimum: 1, maximum: 100 },
          },
        ],
      },
    },
  },
})

const bodyDocument = parseOpenApiDocument({
  openapi: "3.1.0",
  info: { title: "Test API", version: "1" },
  paths: {
    "/semantic-search": {
      post: {
        summary: "Semantic search",
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: {
                type: "object",
                required: ["query"],
                properties: {
                  query: { type: "string", minLength: 1 },
                  limit: { type: "integer", minimum: 1, maximum: 100 },
                  meta: {
                    type: "array",
                    minItems: 1,
                    items: { type: "string" },
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

describe("request construction", () => {
  it("encodes path values, repeats array queries, and applies the bearer key", () => {
    const operation = listOperations(document)[0]
    const request = prepareRequest(
      document,
      operation,
      "https://api.news.backfield.news",
      {
        "path:article_id": "story/123",
        "query:topic": "local\npolitics",
        "header:X-Test": "enabled",
      },
      "",
      "secret-project-key",
    )

    expect(request.url).toBe(
      "https://api.news.backfield.news/articles/story%2F123?topic=local&topic=politics",
    )
    expect(new Headers(request.init.headers).get("Authorization")).toBe(
      "Bearer secret-project-key",
    )
    expect(new Headers(request.init.headers).get("X-Test")).toBe("enabled")
    expect(request.curl).toContain("$BACKFIELD_PROJECT_API_KEY")
    expect(request.curl).not.toContain("secret-project-key")
  })

  it("rejects missing required path values", () => {
    expect(() =>
      prepareRequest(
        document,
        listOperations(document)[0],
        "https://api.news.backfield.news",
        {},
        "",
        "",
      ),
    ).toThrow("article_id is required")
  })

  it("rejects parameter values outside their schema constraints", () => {
    const operation = listOperations(document)[0]
    const baseValues = { "path:article_id": "story-123" }

    expect(() =>
      prepareRequest(
        document,
        operation,
        "https://api.news.backfield.news",
        { ...baseValues, "query:sort": "newest" },
        "",
        "",
      ),
    ).toThrow("sort must be one of: relevance, pub_date")

    expect(() =>
      prepareRequest(
        document,
        operation,
        "https://api.news.backfield.news",
        { ...baseValues, "query:limit": "101" },
        "",
        "",
      ),
    ).toThrow("limit must be at most 100")
  })

  it("validates structured request bodies before sending", () => {
    const operation = listOperations(bodyDocument)[0]
    expect(() =>
      prepareRequest(
        bodyDocument,
        operation,
        "https://api.news.backfield.news",
        {},
        JSON.stringify({ query: "", limit: 25 }),
        "",
      ),
    ).toThrow("Request body.query is required")

    expect(() =>
      prepareRequest(
        bodyDocument,
        operation,
        "https://api.news.backfield.news",
        {},
        JSON.stringify({ query: "city budget", limit: 101 }),
        "",
      ),
    ).toThrow("Request body.limit must be at most 100")

    expect(() =>
      prepareRequest(
        bodyDocument,
        operation,
        "https://api.news.backfield.news",
        {},
        JSON.stringify({ query: "city budget", meta: [] }),
        "",
      ),
    ).toThrow("Request body.meta must contain at least 1 item")
  })
})
