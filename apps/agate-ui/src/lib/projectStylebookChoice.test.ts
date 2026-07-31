import { describe, expect, it } from 'vitest'
import {
  resolveStylebookSelection,
  shouldOfferStylebookChoice,
  stylebookIdForCreate,
  type StylebookOption,
} from './projectStylebookChoice'

const stylebook = (id: number, name: string): StylebookOption => ({ id, name })

const ONE_BOOK = [stylebook(1, 'House')]
const TWO_BOOKS = [stylebook(1, 'House'), stylebook(2, 'Sports')]

describe('shouldOfferStylebookChoice', () => {
  it('hides the choice when the organization has one Stylebook', () => {
    expect(shouldOfferStylebookChoice(ONE_BOOK)).toBe(false)
    expect(shouldOfferStylebookChoice([])).toBe(false)
  })

  it('offers the choice when the organization has several Stylebooks', () => {
    expect(shouldOfferStylebookChoice(TWO_BOOKS)).toBe(true)
  })
})

describe('resolveStylebookSelection', () => {
  it('defaults to the selected workspace Stylebook', () => {
    expect(
      resolveStylebookSelection({
        stylebooks: TWO_BOOKS,
        workspaceStylebookId: 2,
        chosenStylebookId: null,
      }),
    ).toBe(2)
  })

  it('keeps an explicit pick when the workspace changes', () => {
    expect(
      resolveStylebookSelection({
        stylebooks: TWO_BOOKS,
        workspaceStylebookId: 1,
        chosenStylebookId: 2,
      }),
    ).toBe(2)
  })

  it('falls back to the first Stylebook so the control is never blank', () => {
    expect(
      resolveStylebookSelection({
        stylebooks: TWO_BOOKS,
        workspaceStylebookId: 99,
        chosenStylebookId: 98,
      }),
    ).toBe(1)
  })

  it('returns null when the organization has no Stylebooks to show', () => {
    expect(
      resolveStylebookSelection({
        stylebooks: [],
        workspaceStylebookId: 1,
        chosenStylebookId: null,
      }),
    ).toBeNull()
  })
})

describe('stylebookIdForCreate', () => {
  it('sends the picked Stylebook', () => {
    expect(
      stylebookIdForCreate({
        stylebooks: TWO_BOOKS,
        workspaceStylebookId: 1,
        chosenStylebookId: 2,
      }),
    ).toBe(2)
  })

  it('sends nothing when the person never picked, so the server applies its own default', () => {
    expect(
      stylebookIdForCreate({
        stylebooks: TWO_BOOKS,
        workspaceStylebookId: 2,
        chosenStylebookId: null,
      }),
    ).toBeNull()
  })

  it('never sends a displayed fallback the person did not choose', () => {
    // The control shows the first Stylebook when the workspace default is unknown; that
    // display-only value must not be pinned onto the project.
    const input = {
      stylebooks: TWO_BOOKS,
      workspaceStylebookId: null,
      chosenStylebookId: null,
    }
    expect(resolveStylebookSelection(input)).toBe(1)
    expect(stylebookIdForCreate(input)).toBeNull()
  })

  it('sends nothing when no choice was offered', () => {
    expect(
      stylebookIdForCreate({
        stylebooks: ONE_BOOK,
        workspaceStylebookId: 1,
        chosenStylebookId: null,
      }),
    ).toBeNull()
  })

  it('drops a pick that is no longer in the organization list', () => {
    expect(
      stylebookIdForCreate({
        stylebooks: TWO_BOOKS,
        workspaceStylebookId: 1,
        chosenStylebookId: 404,
      }),
    ).toBeNull()
  })
})
