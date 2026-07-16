import { afterEach, describe, expect, it, vi } from 'vitest'

import { stylebookShellHref, stylebookUiOrigin } from './platformUrls'

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
})
