import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import IdTypeahead from "./IdTypeahead"

describe("ID typeahead", () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it("searches the public endpoint and stores the selected ID", async () => {
    const onChange = vi.fn()
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [
            {
              id: "person-123",
              label: "Jane Doe",
              title: "Mayor",
              affiliation: "City Hall",
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    )
    vi.stubGlobal("fetch", fetchMock)

    render(
      <IdTypeahead
        id="person-id"
        kind="person"
        origin="https://api.news.backfield.news"
        projectSlug="daily-news"
        apiKey="project-key"
        value=""
        onChange={onChange}
      />,
    )

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "Jane" },
    })
    const candidate = (await screen.findByText("Jane Doe")).closest("button")
    expect(candidate).not.toBeNull()
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/projects/daily-news/people/search?q=Jane",
    )

    fireEvent.click(candidate!)
    expect(onChange).toHaveBeenCalledWith("person-123")
    expect(screen.getByText("Selected ID: person-123")).toBeInTheDocument()
  })

  it("waits for a project before searching", () => {
    render(
      <IdTypeahead
        id="organization-id"
        kind="organization"
        origin="https://api.news.backfield.news"
        projectSlug=""
        apiKey="project-key"
        value=""
        onChange={() => undefined}
      />,
    )

    expect(screen.getByText("Select a project first.")).toBeInTheDocument()
  })
})
