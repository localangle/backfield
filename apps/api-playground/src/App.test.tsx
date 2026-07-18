import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import App from "./App"

const schema = {
  openapi: "3.1.0",
  info: { title: "Backfield Public API", version: "1.0.0" },
  paths: {
    "/public/v1/articles": {
      get: {
        tags: ["Articles"],
        summary: "List articles",
      },
    },
  },
}

function sessionResponse(input: RequestInfo | URL): Response | undefined {
  const url = String(input)
  if (url.endsWith("/v1/auth/me")) {
    return new Response(
      JSON.stringify({
        authenticated: true,
        email: "developer@example.test",
        organization_id: 1,
        organization_name: "Newsroom",
        org_role: "org_admin",
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    )
  }
  if (url.endsWith("/v1/me/workspaces")) {
    return new Response(
      JSON.stringify([
        {
          id: 1,
          name: "Editorial",
          slug: "editorial",
          projects: [{ id: 2, name: "Daily News", slug: "daily-news" }],
        },
      ]),
      { status: 200, headers: { "Content-Type": "application/json" } },
    )
  }
  if (url.endsWith("/v1/organizations/1/stylebooks")) {
    return new Response(
      JSON.stringify([
        { id: 3, name: "Newsroom Stylebook", slug: "newsroom", is_default: true },
      ]),
      { status: 200, headers: { "Content-Type": "application/json" } },
    )
  }
  return undefined
}

describe("API key handling", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockImplementation(async (input) => {
        const response = sessionResponse(input)
        if (!response) throw new Error(`Unexpected request: ${String(input)}`)
        return response
      }),
    )
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("renders the Backfield product shell, sidebar, and connection landmarks", async () => {
    render(<App />)

    expect(screen.getByRole("banner")).toBeInTheDocument()
    expect(screen.getByRole("main")).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "API Playground", level: 1 })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Connect to the API" })).toBeInTheDocument()
    expect(screen.queryByLabelText(/Organization slug/)).not.toBeInTheDocument()
    expect(screen.getByText("http://localhost:8004")).toBeInTheDocument()
    expect(
      await screen.findByRole("navigation", { name: "Backfield products" }),
    ).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "API Playground" })).toHaveAttribute(
      "aria-current",
      "page",
    )
  })

  it("announces schema loading through the connection region", async () => {
    let resolveSchemaRequest!: (response: Response) => void
    const fetchMock = vi.fn<typeof fetch>().mockImplementation((input) => {
      const response = sessionResponse(input)
      if (response) return Promise.resolve(response)
      return new Promise<Response>((resolve) => {
        resolveSchemaRequest = resolve
      })
    })
    vi.stubGlobal("fetch", fetchMock)

    render(<App />)
    fireEvent.click(screen.getByRole("button", { name: "Load API schema" }))

    const connectionRegion = screen.getByRole("region", {
      name: "Connect to the API",
    })
    await waitFor(() => expect(connectionRegion).toHaveAttribute("aria-busy", "true"))

    resolveSchemaRequest(
      new Response(JSON.stringify(schema), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )
    expect(await screen.findByRole("heading", { name: "List articles" })).toBeInTheDocument()
    expect(connectionRegion).toHaveAttribute("aria-busy", "false")

    const groupToggle = screen.getByRole("button", { name: "Other, 1 endpoint" })
    expect(groupToggle).toHaveAttribute("aria-expanded", "true")
    const endpointLink = document.querySelector(".endpoint-link")
    expect(endpointLink?.querySelector(".endpoint-summary")).toHaveTextContent("List articles")
    expect(endpointLink?.querySelector("code")).toHaveTextContent("/public/v1/articles")

    fireEvent.click(groupToggle)
    expect(groupToggle).toHaveAttribute("aria-expanded", "false")
    expect(document.querySelector(".endpoint-link")).not.toBeInTheDocument()
  })

  it("uses the key for requests without persisting or displaying it", async () => {
    const storageWrite = vi.spyOn(Storage.prototype, "setItem")
    const fetchMock = vi.fn<typeof fetch>().mockImplementation((input, init) => {
      const session = sessionResponse(input)
      if (session) return Promise.resolve(session)
      if (String(input).endsWith("/openapi.json")) {
        return Promise.resolve(
          new Response(JSON.stringify(schema), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        )
      }
      if (init?.method === "GET") {
        return Promise.resolve(
        new Response(JSON.stringify({ items: [] }), {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "X-Request-ID": "request-123",
          },
        }),
      )
      }
      return Promise.reject(new Error(`Unexpected request: ${String(input)}`))
    })
    vi.stubGlobal("fetch", fetchMock)

    render(<App />)
    fireEvent.change(screen.getByLabelText(/Project API key/), {
      target: { value: "top-secret-key" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Load API schema" }))

    expect(await screen.findByRole("heading", { name: "List articles" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Execute request" }))
    expect(await screen.findByText("request-123")).toBeInTheDocument()

    const apiRequest = fetchMock.mock.calls.find(([, init]) =>
      new Headers(init?.headers).has("Authorization"),
    )
    expect(apiRequest).toBeDefined()
    const requestInit = apiRequest?.[1]
    expect(new Headers(requestInit?.headers).get("Authorization")).toBe("Bearer top-secret-key")
    // The sidebar persists layout state; the key itself must never reach storage.
    for (const [storageKey, storedValue] of storageWrite.mock.calls) {
      expect(storageKey).not.toContain("top-secret-key")
      expect(storedValue).not.toContain("top-secret-key")
    }
    expect(screen.getByText(/BACKFIELD_PROJECT_API_KEY/)).toBeInTheDocument()
    expect(document.body.textContent).not.toContain("top-secret-key")
  })
})
