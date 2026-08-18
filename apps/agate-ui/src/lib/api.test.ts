import { afterEach, describe, expect, it, vi } from 'vitest'
import { createProject, replayRun, rerunProcessedItem } from './api'

function stubFetch() {
  const fetchMock = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ id: 7 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function sentBody(fetchMock: ReturnType<typeof stubFetch>): Record<string, unknown> {
  const init = fetchMock.mock.calls[0]?.[1]
  return JSON.parse(String(init?.body))
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('createProject', () => {
  it('sends the chosen Stylebook', async () => {
    const fetchMock = stubFetch()

    await createProject({ name: 'Investigations', workspace_id: 3, stylebook_id: 9 })

    expect(sentBody(fetchMock).stylebook_id).toBe(9)
  })

  it('omits the Stylebook so the workspace default applies', async () => {
    const fetchMock = stubFetch()

    await createProject({ name: 'Investigations', workspace_id: 3 })

    expect(sentBody(fetchMock)).not.toHaveProperty('stylebook_id')
  })

  it('omits an explicitly null Stylebook rather than sending null', async () => {
    const fetchMock = stubFetch()

    await createProject({ name: 'Investigations', workspace_id: 3, stylebook_id: null })

    expect(sentBody(fetchMock)).not.toHaveProperty('stylebook_id')
  })
})

describe('rerun and replay current flow', () => {
  it('omits use_current_flow unless the caller chose the updated flow', async () => {
    const fetchMock = stubFetch()
    await rerunProcessedItem('run-1', 9)
    expect(sentBody(fetchMock)).toEqual({})

    const replayMock = stubFetch()
    await replayRun('run-1', { useCurrentFlow: true })
    expect(sentBody(replayMock)).toEqual({ use_current_flow: true })
  })
})
