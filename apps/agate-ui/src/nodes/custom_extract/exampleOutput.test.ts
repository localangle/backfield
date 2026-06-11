import { describe, expect, it } from 'vitest'

import {
  buildExampleCustomRecordsOutput,
  buildExampleRecordFields,
  exampleFieldValue,
  previewSchemaFromFields,
} from './exampleOutput'

describe('custom extract example output', () => {
  it('maps field types to sample values', () => {
    expect(exampleFieldValue('string')).toBe('Sample value')
    expect(exampleFieldValue('number')).toBe(2)
    expect(exampleFieldValue('boolean')).toBe(true)
    expect(exampleFieldValue('date')).toBe('2026-06-10')
    expect(exampleFieldValue('string_list')).toEqual(['First value', 'Second value'])
  })

  it('builds preview schema and example row from configured fields', () => {
    const fields = [
      { name: 'quantity', label: 'Quantity', type: 'string', description: '' },
      { name: 'unit', label: 'Unit', type: 'string', description: '' },
    ]
    expect(previewSchemaFromFields(fields)).toEqual([
      { name: 'quantity', label: 'Quantity', type: 'string' },
      { name: 'unit', label: 'Unit', type: 'string' },
    ])
    expect(buildExampleRecordFields(fields)).toEqual({
      quantity: 'Sample value',
      unit: 'Sample value',
    })
  })

  it('skips fields without names', () => {
    const fields = [{ name: '', label: 'Draft field', type: 'number', description: '' }]
    expect(previewSchemaFromFields(fields)).toEqual([])
    expect(buildExampleRecordFields(fields)).toEqual({})
    expect(
      buildExampleCustomRecordsOutput({
        recordType: 'draft',
        label: 'Draft',
        fields,
      }),
    ).toBeNull()
  })

  it('builds custom_records example output json', () => {
    const fields = [{ name: 'quantity', label: 'Quantity', type: 'number', description: '' }]
    expect(
      buildExampleCustomRecordsOutput({
        recordType: 'ingredients',
        label: 'Ingredients',
        fields,
      }),
    ).toEqual({
      custom_records: {
        ingredients: {
          label: 'Ingredients',
          schema: [{ name: 'quantity', label: 'Quantity', type: 'number' }],
          records: [
            {
              fields: { quantity: 2 },
              mentions: [{ text: 'exact passage from the article', quote: false }],
              confidence: 0.9,
            },
          ],
          dropped_ungrounded: 0,
        },
      },
    })
  })
})
