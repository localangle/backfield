import { describe, expect, it } from 'vitest'
import { projectStylebookDisplayName, reviewStylebookSlug } from './projectStylebook'
import type { Project } from '@/lib/api'

/** A project created with an explicit Stylebook: its workspace still points somewhere else. */
const DIVERGENT_PROJECT = {
  id: 1,
  name: 'Investigations',
  slug: 'investigations',
  organization_id: 1,
  created_at: '2026-01-01T00:00:00Z',
  stylebook_id: 2,
  stylebook_name: 'Sports',
  stylebook_slug: 'sports',
  workspace_stylebook_id: 1,
  workspace_stylebook_name: 'House',
  workspace_stylebook_slug: 'house',
} as Project

describe('reviewStylebookSlug', () => {
  it('targets the project Stylebook, never the workspace one', () => {
    expect(reviewStylebookSlug(DIVERGENT_PROJECT)).toBe('sports')
    expect(reviewStylebookSlug(DIVERGENT_PROJECT)).not.toBe(
      DIVERGENT_PROJECT.workspace_stylebook_slug,
    )
  })

  it('has no target before the project loads', () => {
    expect(reviewStylebookSlug(null)).toBeNull()
    expect(reviewStylebookSlug(undefined)).toBeNull()
  })

  it('treats a blank or missing project Stylebook as no target', () => {
    expect(reviewStylebookSlug({ ...DIVERGENT_PROJECT, stylebook_slug: '  ' })).toBeNull()
    expect(reviewStylebookSlug({ ...DIVERGENT_PROJECT, stylebook_slug: null })).toBeNull()
  })
})

describe('projectStylebookDisplayName', () => {
  it('shows the project Stylebook name', () => {
    expect(projectStylebookDisplayName({ stylebook_name: 'Sports' })).toBe('Sports')
  })

  it('stays readable when no name came back', () => {
    expect(projectStylebookDisplayName({ stylebook_name: null })).toBe('Not available')
    expect(projectStylebookDisplayName({ stylebook_name: '  ' })).toBe('Not available')
  })
})
