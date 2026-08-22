import { describe, expect, it } from 'vitest'

import {
  isValidJsonInputData,
  jsonInputInvalidNodeData,
  markJsonInputNodeDataInvalid,
  mergeJsonInputUploads,
  normalizeJsonInputParamsForSave,
  parseJsonInputEditorText,
  parseJsonInputFileText,
} from './jsonInputValidation'

describe('jsonInputValidation', () => {
  it('accepts object with empty string text', () => {
    expect(isValidJsonInputData({ text: '' })).toBe(true)
    expect(parseJsonInputEditorText('{"text":""}')).toEqual({ ok: true, data: { text: '' } })
  })

  it('rejects missing text field', () => {
    expect(isValidJsonInputData({ headline: 'Hi' })).toBe(false)
    expect(parseJsonInputEditorText('{"headline":"Hi"}')).toEqual({
      ok: false,
      error: 'JSON must include a "text" field',
    })
  })

  it('rejects invalid JSON', () => {
    expect(parseJsonInputEditorText('{')).toEqual({ ok: false, error: 'Invalid JSON syntax' })
  })

  it('treats invalid-editor marker as not continuable', () => {
    expect(isValidJsonInputData(jsonInputInvalidNodeData())).toBe(false)
    expect(isValidJsonInputData(jsonInputInvalidNodeData({ text: 'hello' }))).toBe(false)
  })

  it('preserves prior fields when marking invalid', () => {
    expect(markJsonInputNodeDataInvalid({ text: 'hello', headline: 'Hi' })).toEqual({
      text: 'hello',
      headline: 'Hi',
      __jsonInputInvalid: true,
    })
  })

  it('accepts multi-document node data', () => {
    expect(
      isValidJsonInputData({
        documents: [
          { text: 'a', source_file: 'a.json' },
          { text: 'b', source_file: 'b.json' },
        ],
      }),
    ).toBe(true)
  })

  it('rejects documents lists outside 2–20', () => {
    expect(isValidJsonInputData({ documents: [{ text: 'only' }] })).toBe(false)
    const tooMany = {
      documents: Array.from({ length: 21 }, (_, i) => ({
        text: `t${i}`,
        source_file: `${i}.json`,
      })),
    }
    expect(isValidJsonInputData(tooMany)).toBe(false)
  })

  it('collapses length-1 documents on save normalize', () => {
    expect(
      normalizeJsonInputParamsForSave({
        public_alias: 'in',
        documents: [{ text: 'solo', source_file: 'a.json', headline: 'H' }],
      }),
    ).toEqual({ public_alias: 'in', text: 'solo', headline: 'H' })
  })

  it('parses uploaded file text with plain-language errors', () => {
    expect(parseJsonInputFileText('{"text":"hi"}', 'story.json')).toEqual({
      ok: true,
      document: { text: 'hi', source_file: 'story.json' },
    })
    expect(parseJsonInputFileText('[1]', 'bad.json').ok).toBe(false)
  })

  it('merges uploads: flat node uses uploads only; multi node appends', () => {
    const single = mergeJsonInputUploads({ text: '' }, [
      { text: 'one', source_file: 'a.json' },
    ])
    expect(single.ok).toBe(true)
    if (single.ok) {
      expect(single.data).toEqual({ text: 'one' })
    }

    const replace = mergeJsonInputUploads({ text: 'kept', headline: 'H' }, [
      { text: 'two', source_file: 'b.json' },
    ])
    expect(replace.ok).toBe(true)
    if (replace.ok) {
      expect(replace.data).toEqual({ text: 'two' })
    }

    const batch = mergeJsonInputUploads({ text: 'kept', headline: 'H' }, [
      { text: 'two', source_file: 'b.json' },
      { text: 'three', source_file: 'c.json' },
    ])
    expect(batch.ok).toBe(true)
    if (batch.ok) {
      expect(batch.data.documents).toHaveLength(2)
      expect(batch.data.documents).toEqual([
        { text: 'two', source_file: 'b.json' },
        { text: 'three', source_file: 'c.json' },
      ])
    }

    const append = mergeJsonInputUploads(
      {
        documents: [
          { text: 'a', source_file: 'a.json' },
          { text: 'b', source_file: 'b.json' },
        ],
      },
      [{ text: 'c', source_file: 'c.json' }],
    )
    expect(append.ok).toBe(true)
    if (append.ok) {
      expect(append.data.documents).toHaveLength(3)
    }
  })
})
