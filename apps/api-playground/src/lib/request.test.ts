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
        ],
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
})
