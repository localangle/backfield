import { describe, expect, it } from 'vitest'

import {
  isValidJsonInputData,
  jsonInputInvalidNodeData,
  markJsonInputNodeDataInvalid,
  parseJsonInputEditorText,
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
})
