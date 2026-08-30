import { describe, expect, it } from 'vitest'
import {
  defaultProjectWorkspaceTab,
  isProjectWorkspaceTab,
  parseProjectWorkspaceTab,
  projectWorkspaceTabSearch,
} from './projectWorkspaceTab'

describe('projectWorkspaceTab', () => {
  it('defaults to flows', () => {
    expect(defaultProjectWorkspaceTab()).toBe('flows')
    expect(parseProjectWorkspaceTab(null)).toBe('flows')
    expect(parseProjectWorkspaceTab('nope')).toBe('flows')
  })

  it('accepts known tabs', () => {
    expect(isProjectWorkspaceTab('articles')).toBe(true)
    expect(parseProjectWorkspaceTab('articles')).toBe('articles')
    expect(parseProjectWorkspaceTab('runs')).toBe('runs')
  })

  it('builds tab search strings', () => {
    expect(projectWorkspaceTabSearch('articles')).toBe('?tab=articles')
    expect(projectWorkspaceTabSearch('flows')).toBe('?tab=flows')
  })
})
