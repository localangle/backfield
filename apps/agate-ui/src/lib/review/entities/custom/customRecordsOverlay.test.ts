import { describe, expect, it } from 'vitest'
import type { CustomRecordTableModel } from '@/lib/review/content/customRecordsDisplay'
import {
  applyCustomRecordFieldsPatch,
  applyCustomRecordMentionsPatch,
  applyCustomRecordsOverlayToTables,
  appendUserAddedCustomRecord,
  buildRemoveCustomRecordPatch,
  customRecordsOverlayHasContent,
  newUserAddedRecordKey,
  patchUserAddedCustomRecord,
} from './customRecordsOverlay'

function ingredientsTable(): CustomRecordTableModel {
  return {
    recordType: 'ingredients',
    label: 'Ingredients',
    columns: [
      { name: 'name', label: 'Name', type: 'string' },
      { name: 'quantity', label: 'Quantity', type: 'string' },
    ],
    records: [
      {
        key: 'abc123',
        fields: { name: 'Flour', quantity: '2 cups' },
        mentions: [{ text: 'two cups of flour', quote: false }],
        confidence: 0.9,
        source: 'model',
      },
      {
        key: 'def456',
        fields: { name: 'Salt', quantity: '1 tsp' },
        mentions: [{ text: 'a teaspoon of salt', quote: false }],
        confidence: null,
        source: 'model',
      },
    ],
    droppedUngrounded: 0,
  }
}

describe('customRecordsOverlayHasContent', () => {
  it('is false for empty or missing overlays', () => {
    expect(customRecordsOverlayHasContent(null)).toBe(false)
    expect(customRecordsOverlayHasContent({})).toBe(false)
    expect(customRecordsOverlayHasContent({ custom_records: {} })).toBe(false)
    expect(
      customRecordsOverlayHasContent({
        custom_records: { ingredients: { by_key: {}, removed_keys: [], user_added: [] } },
      }),
    ).toBe(false)
  })

  it('is true for any edit verb', () => {
    let draft: Record<string, unknown> = {}
    draft = applyCustomRecordFieldsPatch(draft, 'ingredients', 'abc123', { quantity: '3 cups' })
    expect(customRecordsOverlayHasContent(draft)).toBe(true)
  })
})

describe('edit verbs', () => {
  it('merges field patches per record key', () => {
    let draft: Record<string, unknown> = {}
    draft = applyCustomRecordFieldsPatch(draft, 'ingredients', 'abc123', { quantity: '3 cups' })
    draft = applyCustomRecordFieldsPatch(draft, 'ingredients', 'abc123', { name: 'Bread flour' })
    const byKey = (draft.custom_records as Record<string, any>).ingredients.by_key
    expect(byKey.abc123.fields).toEqual({ quantity: '3 cups', name: 'Bread flour' })
  })

  it('replaces the mention list on a mentions patch', () => {
    let draft: Record<string, unknown> = {}
    draft = applyCustomRecordMentionsPatch(draft, 'ingredients', 'abc123', [
      { text: 'flour', quote: false },
    ])
    const byKey = (draft.custom_records as Record<string, any>).ingredients.by_key
    expect(byKey.abc123.mentions).toEqual([{ text: 'flour', quote: false }])
  })

  it('removes model records via removed_keys and clears their patches', () => {
    let draft: Record<string, unknown> = {}
    draft = applyCustomRecordFieldsPatch(draft, 'ingredients', 'abc123', { quantity: '3 cups' })
    draft = buildRemoveCustomRecordPatch(draft, 'ingredients', 'abc123', 'model')
    const typeOverlay = (draft.custom_records as Record<string, any>).ingredients
    expect(typeOverlay.removed_keys).toEqual(['abc123'])
    expect(typeOverlay.by_key).toEqual({})
  })

  it('drops reviewer-added records entirely on remove', () => {
    let draft: Record<string, unknown> = {}
    const key = newUserAddedRecordKey()
    draft = appendUserAddedCustomRecord(draft, 'ingredients', {
      key,
      fields: { name: 'Sugar' },
    })
    draft = buildRemoveCustomRecordPatch(draft, 'ingredients', key, 'review')
    const typeOverlay = (draft.custom_records as Record<string, any>).ingredients
    expect(typeOverlay.user_added).toEqual([])
    expect(typeOverlay.removed_keys).toEqual([])
  })

  it('appends reviewer records with review source and patches them in place', () => {
    let draft: Record<string, unknown> = {}
    const key = newUserAddedRecordKey()
    expect(key.startsWith('user_record:')).toBe(true)
    draft = appendUserAddedCustomRecord(draft, 'ingredients', {
      key,
      fields: { name: 'Sugar', quantity: '' },
    })
    draft = patchUserAddedCustomRecord(draft, 'ingredients', key, {
      fields: { quantity: '1 cup' },
      mentions: [{ text: 'a cup of sugar', quote: false }],
    })
    const rows = (draft.custom_records as Record<string, any>).ingredients.user_added
    expect(rows).toHaveLength(1)
    expect(rows[0].source).toBe('review')
    expect(rows[0].fields).toEqual({ name: 'Sugar', quantity: '1 cup' })
    expect(rows[0].mentions).toEqual([{ text: 'a cup of sugar', quote: false }])
  })
})

describe('applyCustomRecordsOverlayToTables', () => {
  it('returns tables unchanged without overlay content', () => {
    const tables = [ingredientsTable()]
    expect(applyCustomRecordsOverlayToTables(tables, null)).toEqual(tables)
    expect(applyCustomRecordsOverlayToTables(tables, {})).toEqual(tables)
  })

  it('applies field edits, removals, and reviewer additions like the server merge', () => {
    let draft: Record<string, unknown> = {}
    draft = applyCustomRecordFieldsPatch(draft, 'ingredients', 'abc123', { quantity: '3 cups' })
    draft = buildRemoveCustomRecordPatch(draft, 'ingredients', 'def456', 'model')
    draft = appendUserAddedCustomRecord(draft, 'ingredients', {
      key: 'user_record:1',
      fields: { name: 'Sugar', quantity: '1 cup' },
      mentions: [{ text: 'a cup of sugar', quote: false }],
    })

    const [merged] = applyCustomRecordsOverlayToTables([ingredientsTable()], draft)
    expect(merged!.records.map((r) => r.key)).toEqual(['abc123', 'user_record:1'])
    expect(merged!.records[0]!.fields).toEqual({ name: 'Flour', quantity: '3 cups' })
    expect(merged!.records[0]!.mentions).toEqual([{ text: 'two cups of flour', quote: false }])
    expect(merged!.records[1]!.source).toBe('review')
    expect(merged!.records[1]!.mentions).toEqual([{ text: 'a cup of sugar', quote: false }])
  })

  it('replaces mentions when a mentions patch exists', () => {
    let draft: Record<string, unknown> = {}
    draft = applyCustomRecordMentionsPatch(draft, 'ingredients', 'abc123', [])
    const [merged] = applyCustomRecordsOverlayToTables([ingredientsTable()], draft)
    expect(merged!.records[0]!.mentions).toEqual([])
  })

  it('leaves sibling record types untouched', () => {
    const stepsTable: CustomRecordTableModel = {
      recordType: 'steps',
      label: 'Steps',
      columns: [{ name: 'description', label: 'Description', type: 'string' }],
      records: [
        {
          key: 's1',
          fields: { description: 'Preheat oven' },
          mentions: [{ text: 'Preheat the oven', quote: false }],
          confidence: null,
          source: 'model',
        },
      ],
      droppedUngrounded: 0,
    }
    let draft: Record<string, unknown> = {}
    draft = buildRemoveCustomRecordPatch(draft, 'ingredients', 'abc123', 'model')
    const merged = applyCustomRecordsOverlayToTables([ingredientsTable(), stepsTable], draft)
    expect(merged[1]).toEqual(stepsTable)
  })
})
