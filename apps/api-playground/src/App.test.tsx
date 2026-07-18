import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

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

describe("API key handling", () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("renders the Backfield product shell and connection landmarks", () => {
    render(<App />)

    expect(screen.getByRole("banner")).toBeInTheDocument()
    expect(screen.getByRole("main")).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "API Playground", level: 1 })).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Connect to an organization" }),
    ).toBeInTheDocument()
    expect(screen.getByText("Backfield developer tools")).toBeInTheDocument()
  })

  it("announces schema loading through the connection region", async () => {
    let resolveSchemaRequest!: (response: Response) => void
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          resolveSchemaRequest = resolve
        }),
    )
    vi.stubGlobal("fetch", fetchMock)

    render(<App />)
    fireEvent.change(screen.getByLabelText(/Organization slug/), {
      target: { value: "newsroom" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Load API schema" }))

    const connectionRegion = screen.getByRole("region", {
      name: "Connect to an organization",
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
  })

  it("uses the key for requests without persisting or displaying it", async () => {
    const storageWrite = vi.spyOn(Storage.prototype, "setItem")
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(schema), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [] }), {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "X-Request-ID": "request-123",
          },
        }),
      )
    vi.stubGlobal("fetch", fetchMock)

    render(<App />)
    fireEvent.change(screen.getByLabelText(/Organization slug/), {
      target: { value: "newsroom" },
    })
    fireEvent.change(screen.getByLabelText(/Project API key/), {
      target: { value: "top-secret-key" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Load API schema" }))

    expect(await screen.findByRole("heading", { name: "List articles" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Execute request" }))
    expect(await screen.findByText("request-123")).toBeInTheDocument()

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const requestInit = fetchMock.mock.calls[1][1]
    expect(new Headers(requestInit?.headers).get("Authorization")).toBe("Bearer top-secret-key")
    expect(storageWrite).not.toHaveBeenCalled()
    expect(screen.getByText(/BACKFIELD_PROJECT_API_KEY/)).toBeInTheDocument()
    expect(document.body.textContent).not.toContain("top-secret-key")
  })
})
