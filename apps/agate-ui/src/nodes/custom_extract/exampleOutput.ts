export type CustomExtractFieldPreview = {
  name: string
  label: string
  type: string
  description: string
}

export type CustomExtractPreviewColumn = {
  name: string
  label: string
  type: string
}

/** Placeholder field values aligned with the runtime prompt example shape. */
export function exampleFieldValue(type: string): unknown {
  switch (type) {
    case 'number':
      return 2
    case 'boolean':
      return true
    case 'date':
      return '2026-06-10'
    case 'string_list':
      return ['First value', 'Second value']
    default:
      return 'Sample value'
  }
}

export function previewSchemaFromFields(
  fields: CustomExtractFieldPreview[],
): CustomExtractPreviewColumn[] {
  return fields
    .filter((field) => field.name.trim())
    .map((field) => ({
      name: field.name,
      label: field.label.trim() || field.name.replace(/_/g, ' '),
      type: field.type,
    }))
}

export function buildExampleRecordFields(
  fields: CustomExtractFieldPreview[],
): Record<string, unknown> {
  const configured = fields.filter((field) => field.name.trim())
  const values: Record<string, unknown> = {}
  for (const field of configured) {
    values[field.name] = exampleFieldValue(field.type)
  }
  return values
}

function buildExampleRecord(fields: CustomExtractFieldPreview[]) {
  return {
    fields: buildExampleRecordFields(fields),
    mentions: [{ text: 'exact passage from the article', quote: false }],
    confidence: 0.9,
  }
}

/** Example node output shape for the Output tab preview. */
export function buildExampleCustomRecordsOutput(params: {
  recordType: string
  label: string
  fields: CustomExtractFieldPreview[]
}): { custom_records: Record<string, unknown> } | null {
  const schema = previewSchemaFromFields(params.fields)
  if (schema.length === 0) return null

  const recordType = params.recordType.trim() || 'records'
  const label = params.label.trim() || recordType.replace(/_/g, ' ')

  return {
    custom_records: {
      [recordType]: {
        label,
        schema,
        records: [buildExampleRecord(params.fields)],
        dropped_ungrounded: 0,
      },
    },
  }
}
