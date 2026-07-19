import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("@backfield/ui/UserAccountMenu", () => ({
  UserAccountMenu: ({
    userLabel,
    onLogout,
  }: {
    userLabel?: string
    onLogout: () => void
  }) => (
    <div>
      <button
        type="button"
        aria-haspopup="menu"
        aria-label={userLabel ? `Account menu for ${userLabel}` : "Account menu"}
      >
        Account
      </button>
      <button type="button" onClick={() => void onLogout()}>
        Log out
      </button>
    </div>
  ),
}))

import App from "./App"

const schema = {
  openapi: "3.1.0",
  info: { title: "Backfield Public API", version: "1.0.0" },
  paths: {
    "/public/v1/projects/{project_slug}/articles/search": {
      get: {
        tags: ["Articles"],
        summary: "Search Project Articles",
        parameters: [
          {
            name: "project_slug",
            in: "path",
            required: true,
            schema: { type: "string" },
          },
        ],
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
    sessionStorage.clear()
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockImplementation(async (input) => {
        const response = sessionResponse(input)
        if (response) return response
        if (String(input).endsWith("/openapi.json")) {
          return new Response(JSON.stringify(schema), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          })
        }
        throw new Error(`Unexpected request: ${String(input)}`)
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
    expect(
      await screen.findByRole("heading", { name: "Browse the API schema" }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Browse every endpoint without authentication/),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Execute request" })).toBeDisabled()
    expect(screen.queryByLabelText(/Organization slug/)).not.toBeInTheDocument()
    expect(screen.queryByText("Backfield developer tools")).not.toBeInTheDocument()
    expect(screen.getByText("http://localhost:8004")).toBeInTheDocument()
    expect(
      await screen.findByRole("navigation", { name: "Backfield products" }),
    ).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "API Playground" })).toHaveAttribute(
      "aria-current",
      "page",
    )
    const accountMenu = screen.getByRole("button", {
      name: "Account menu for developer@example.test",
    })
    expect(accountMenu).toHaveAttribute("aria-haspopup", "menu")
    expect(screen.queryByText("Backfield developer tools")).not.toBeInTheDocument()
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
    const connectionRegion = screen.getByRole("region", {
      name: "API schema",
    })
    await waitFor(() => expect(connectionRegion).toHaveAttribute("aria-busy", "true"))

    resolveSchemaRequest(
      new Response(JSON.stringify(schema), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )
    expect(await screen.findByRole("heading", { name: "List and search" })).toBeInTheDocument()
    expect(screen.queryByText(/Version 1\.0\.0/)).not.toBeInTheDocument()
    expect(screen.queryByText(/^1\.0\.0$/)).not.toBeInTheDocument()
    expect(screen.getByText("1 operations")).toBeInTheDocument()
    const projectSelect = screen.getByLabelText(/project_slug/) as HTMLSelectElement
    expect(projectSelect.tagName).toBe("SELECT")
    expect(projectSelect).toHaveTextContent("Daily News (daily-news)")
    expect(connectionRegion).toHaveAttribute("aria-busy", "false")

    const groupToggle = screen.getByRole("button", { name: "Articles, 1 endpoint" })
    expect(groupToggle).toHaveAttribute("aria-expanded", "false")
    expect(document.querySelector(".endpoint-link")).not.toBeInTheDocument()

    fireEvent.click(groupToggle)
    expect(groupToggle).toHaveAttribute("aria-expanded", "true")
    const endpointLink = document.querySelector(".endpoint-link")
    expect(endpointLink?.querySelector(".endpoint-summary")).toHaveTextContent("List and search")
    expect(endpointLink?.querySelector("code")).toHaveTextContent("/articles/search")
  })

  it("keeps the key for tab reloads without displaying or locally persisting it", async () => {
    const localStorageWrite = vi.spyOn(window.localStorage, "setItem")
    const clipboardWrite = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal("navigator", { clipboard: { writeText: clipboardWrite } })
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
      if (String(input).endsWith("/articles/facets")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              authors: ["Jane Doe"],
              external_sources: ["Daily News"],
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
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

    const firstRender = render(<App />)
    fireEvent.change(screen.getByLabelText(/Project API key/), {
      target: { value: "top-secret-key" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Use API key" }))
    await waitFor(() =>
      expect(
        sessionStorage.getItem("backfield-playground-project-api-key"),
      ).toBe("top-secret-key"),
    )

    // A fresh mount models a reload in the same browser tab.
    firstRender.unmount()
    render(<App />)
    expect(screen.getByLabelText(/Project API key/)).toHaveValue("top-secret-key")

    expect(await screen.findByRole("heading", { name: "List and search" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "API schema loaded" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Reload schema" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Clear key" })).toBeInTheDocument()
    expect(screen.queryByLabelText(/Project API key/)).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/project_slug/), {
      target: { value: "daily-news" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Execute request" }))
    expect(await screen.findByText("request-123")).toBeInTheDocument()

    const apiRequest = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input).includes("/articles/search") &&
        new Headers(init?.headers).has("Authorization"),
    )
    expect(apiRequest).toBeDefined()
    expect(String(apiRequest?.[0])).toContain("/projects/daily-news/articles/search")
    const requestInit = apiRequest?.[1]
    expect(new Headers(requestInit?.headers).get("Authorization")).toBe("Bearer top-secret-key")
    // The sidebar persists layout state in localStorage; the API key must not.
    for (const [storageKey, storedValue] of localStorageWrite.mock.calls) {
      expect(storageKey).not.toContain("top-secret-key")
      expect(storedValue).not.toContain("top-secret-key")
    }
    expect(screen.getByText(/BACKFIELD_PROJECT_API_KEY/)).toBeInTheDocument()
    expect(document.body.textContent).not.toContain("top-secret-key")

    fireEvent.click(screen.getByRole("button", { name: "Copy curl" }))
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledTimes(1))
    expect(clipboardWrite.mock.calls[0][0]).toContain("curl")
    expect(clipboardWrite.mock.calls[0][0]).not.toContain("top-secret-key")

    fireEvent.click(screen.getByRole("button", { name: "Copy response body" }))
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledTimes(2))
    expect(clipboardWrite.mock.calls[1][0]).toContain('"items": []')

    fireEvent.click(screen.getByRole("button", { name: "Clear key" }))
    expect(
      await screen.findByRole("heading", { name: "Browse the API schema" }),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Execute request" })).toBeDisabled()
    expect(screen.getByRole("heading", { name: "List and search" })).toBeInTheDocument()
    await waitFor(() =>
      expect(
        sessionStorage.getItem("backfield-playground-project-api-key"),
      ).toBeNull(),
    )
  })

  it("clears the project API key from storage and UI on logout", async () => {
    const assign = vi.fn()
    vi.stubGlobal("location", { ...window.location, assign })
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (input, init) => {
      const response = sessionResponse(input)
      if (response) return response
      if (String(input).endsWith("/openapi.json")) {
        return new Response(JSON.stringify(schema), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      }
      if (String(input).endsWith("/v1/auth/logout") && init?.method === "POST") {
        return new Response(null, { status: 204 })
      }
      throw new Error(`Unexpected request: ${String(input)}`)
    })
    vi.stubGlobal("fetch", fetchMock)

    render(<App />)
    fireEvent.change(screen.getByLabelText(/Project API key/), {
      target: { value: "logout-secret-key" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Use API key" }))
    await waitFor(() =>
      expect(
        sessionStorage.getItem("backfield-playground-project-api-key"),
      ).toBe("logout-secret-key"),
    )

    fireEvent.click(screen.getByRole("button", { name: "Log out" }))

    await waitFor(() => expect(assign).toHaveBeenCalled())
    expect(sessionStorage.getItem("backfield-playground-project-api-key")).toBeNull()
    expect(screen.queryByDisplayValue("logout-secret-key")).not.toBeInTheDocument()
  })
})
