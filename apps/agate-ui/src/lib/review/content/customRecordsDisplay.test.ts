import { describe, expect, it } from 'vitest'
import {
  buildCustomRecordTables,
  customAmbientHighlightRanges,
  customMentionHighlightRanges,
  customRecordCellListItems,
  customRecordCellText,
  extractCustomRecordsBlock,
} from './customRecordsDisplay'

const INGREDIENTS_SET = {
  label: 'Ingredients',
  schema: [
    { name: 'name', label: 'Name', type: 'string' },
    { name: 'quantity', label: 'Quantity', type: 'string' },
    { name: 'optional', label: 'Optional', type: 'boolean' },
    { name: 'tags', label: 'Tags', type: 'string_list' },
  ],
  records: [
    {
      key: 'abc123',
      fields: { name: 'Flour', quantity: '2 cups', optional: false, tags: ['dry', 'baking'] },
      mentions: [{ text: 'two cups of flour', quote: false }],
      confidence: 0.9,
    },
    {
      key: 'def456',
      fields: { name: 'Salt', quantity: null, optional: true, tags: [] },
      mentions: [],
      confidence: null,
    },
  ],
  dropped_ungrounded: 1,
}

describe('extractCustomRecordsBlock', () => {
  it('reads custom_records from a node payload', () => {
    const block = extractCustomRecordsBlock({
      'node-3': { custom_records: { ingredients: INGREDIENTS_SET } },
    })
    expect(Object.keys(block)).toEqual(['ingredients'])
  })

  it('reads custom_records from a consolidated output payload', () => {
    const block = extractCustomRecordsBlock({
      json_output: { consolidated: { custom_records: { ingredients: INGREDIENTS_SET } } },
    })
    expect(Object.keys(block)).toEqual(['ingredients'])
  })

  it('unions record types across payloads with later payloads winning per type', () => {
    const block = extractCustomRecordsBlock({
      'node-3': { custom_records: { ingredients: { ...INGREDIENTS_SET, label: 'Old' } } },
      'node-4': { custom_records: { steps: { label: 'Steps', schema: [], records: [] } } },
      db_output: {
        consolidated: { custom_records: { ingredients: INGREDIENTS_SET } },
      },
    })
    expect(Object.keys(block).sort()).toEqual(['ingredients', 'steps'])
    expect((block.ingredients as { label: string }).label).toBe('Ingredients')
  })

  it('returns an empty block for missing or malformed output', () => {
    expect(extractCustomRecordsBlock(null)).toEqual({})
    expect(extractCustomRecordsBlock({})).toEqual({})
    expect(extractCustomRecordsBlock({ 'node-1': { custom_records: 'bogus' } })).toEqual({})
  })
})

describe('buildCustomRecordTables', () => {
  it('builds one table per record type with schema columns and rows', () => {
    const tables = buildCustomRecordTables({
      'node-3': { custom_records: { ingredients: INGREDIENTS_SET } },
    })
    expect(tables).toHaveLength(1)
    const table = tables[0]!
    expect(table.recordType).toBe('ingredients')
    expect(table.label).toBe('Ingredients')
    expect(table.columns.map((c) => c.name)).toEqual(['name', 'quantity', 'optional', 'tags'])
    expect(table.records).toHaveLength(2)
    expect(table.records[0]!.key).toBe('abc123')
    expect(table.records[0]!.mentions).toEqual([{ text: 'two cups of flour', quote: false }])
    expect(table.records[0]!.confidence).toBe(0.9)
    expect(table.records[1]!.confidence).toBeNull()
    expect(table.droppedUngrounded).toBe(1)
  })

  it('falls back to a humanized record type when label is missing', () => {
    const tables = buildCustomRecordTables({
      'node-3': {
        custom_records: { mural_artists: { schema: [], records: [] } },
      },
    })
    expect(tables[0]!.label).toBe('Mural Artists')
  })

  it('tolerates string mentions and missing record keys', () => {
    const tables = buildCustomRecordTables({
      'node-3': {
        custom_records: {
          steps: {
            label: 'Steps',
            schema: [{ name: 'description', label: 'Description', type: 'string' }],
            records: [{ fields: { description: 'Preheat oven' }, mentions: ['Preheat the oven'] }],
          },
        },
      },
    })
    const record = tables[0]!.records[0]!
    expect(record.key).toBe('steps-0')
    expect(record.mentions).toEqual([{ text: 'Preheat the oven', quote: false }])
  })

  it('returns no tables when output has no custom records', () => {
    expect(buildCustomRecordTables({ 'node-1': { text: 'hello' } })).toEqual([])
  })
})

describe('cell display helpers', () => {
  it('formats empty, boolean, and list values for reading', () => {
    expect(customRecordCellText(null)).toBe('—')
    expect(customRecordCellText('')).toBe('—')
    expect(customRecordCellText(true)).toBe('Yes')
    expect(customRecordCellText(false)).toBe('No')
    expect(customRecordCellText(['a', 'b'])).toBe('a, b')
    expect(customRecordCellText(2.5)).toBe('2.5')
  })

  it('returns list items only for non-empty lists', () => {
    expect(customRecordCellListItems(['dry', 'baking'])).toEqual(['dry', 'baking'])
    expect(customRecordCellListItems([])).toBeNull()
    expect(customRecordCellListItems('text')).toBeNull()
  })
})

describe('mention span resolution', () => {
  const body = 'Mix two cups of flour with salt. Add more flour if needed.'

  it('resolves all occurrences of a mention text in the story', () => {
    const ranges = customMentionHighlightRanges(body, 'flour')
    expect(ranges).toHaveLength(2)
    expect(body.slice(ranges[0]!.start, ranges[0]!.end)).toBe('flour')
  })

  it('returns no ranges when the mention is missing from the story', () => {
    expect(customMentionHighlightRanges(body, 'butter')).toEqual([])
    expect(customMentionHighlightRanges('', 'flour')).toEqual([])
  })

  it('collects ambient ranges across all records and tables', () => {
    const tables = buildCustomRecordTables({
      'node-3': { custom_records: { ingredients: INGREDIENTS_SET } },
    })
    const ranges = customAmbientHighlightRanges(body, tables)
    expect(ranges).toHaveLength(1)
    expect(body.slice(ranges[0]!.start, ranges[0]!.end)).toBe('two cups of flour')
  })
})
