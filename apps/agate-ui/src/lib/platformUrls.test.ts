import { afterEach, describe, expect, it, vi } from 'vitest'

import { playgroundHref, stylebookShellHref, stylebookUiOrigin } from './platformUrls'

describe('platformUrls sibling hosts', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('links Stylebook on the stylebook host when browsing Agate', () => {
    vi.stubGlobal('window', {
      location: { origin: 'https://agate.cpm.backfield.news' },
    })

    expect(stylebookUiOrigin()).toBe('https://stylebook.cpm.backfield.news')
    expect(stylebookShellHref('cpm-stylebook', 'general')).toBe(
      'https://stylebook.cpm.backfield.news/stylebook/cpm-stylebook?project=general',
    )
  })

  it('links the local Playground while developing locally', () => {
    vi.stubGlobal('window', {
      location: { origin: 'http://127.0.0.1:5173' },
    })

    expect(playgroundHref()).toBe('http://127.0.0.1:5176')
  })

  it('supports an explicit Playground URL', () => {
    vi.stubGlobal('window', {
      location: { origin: 'https://agate.cpm.backfield.news' },
    })
    vi.stubEnv('VITE_PLAYGROUND_URL', 'https://developer-tools.example.test')

    expect(playgroundHref()).toBe('https://developer-tools.example.test')
  })

  it('uses a tenant-specific hosted Playground domain', () => {
    vi.stubGlobal('window', {
      location: { origin: 'https://agate.cpm.backfield.news' },
    })

    expect(playgroundHref()).toBe('https://playground.cpm.backfield.news')
  })

  it('preserves staging when linking to the Playground', () => {
    vi.stubGlobal('window', {
      location: { origin: 'https://agate.canary.stg.backfield.news' },
    })

    expect(playgroundHref()).toBe('https://playground.canary.stg.backfield.news')
  })

  it('supports an organization placeholder in a custom Playground URL', () => {
    vi.stubGlobal('window', {
      location: { origin: 'https://agate.cpm.backfield.news' },
    })
    vi.stubEnv(
      'VITE_PLAYGROUND_URL',
      'https://developer-tools.{organization_slug}.example.test',
    )

    expect(playgroundHref()).toBe('https://developer-tools.cpm.example.test')
  })
})
