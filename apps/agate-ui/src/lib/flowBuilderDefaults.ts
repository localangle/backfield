import { nodeMetadata } from '@/nodes/registry'

export function getInputBookendDefaultData(type: string): Record<string, unknown> {
  switch (type) {
    case 'TextInput':
      return { text: '' }
    case 'JSONInput':
      return { text: '' }
    case 'S3Input':
      return {
        bucket: '',
        folder_path: '',
        max_files: 500,
        reprocess_unchanged: false,
        source_id:
          typeof crypto !== 'undefined' && crypto.randomUUID
            ? crypto.randomUUID()
            : `s3-src-${Date.now()}`,
      }
    default: {
      const meta = nodeMetadata.find((m) => m.type === type)
      return { ...(meta?.defaultParams ?? {}) }
    }
  }
}

export function getOutputBookendDefaultData(type: string): Record<string, unknown> {
  switch (type) {
    case 'Output':
      return {}
    case 'DBOutput': {
      const meta = nodeMetadata.find((m) => m.type === 'DBOutput')
      return { ...(meta?.defaultParams ?? {}) } as Record<string, unknown>
    }
    default: {
      const meta = nodeMetadata.find((m) => m.type === type)
      return { ...(meta?.defaultParams ?? {}) }
    }
  }
}

export function getMiddleNodeDefaultData(type: string): Record<string, unknown> {
  switch (type) {
    case 'PlaceExtract':
    case 'PersonExtract':
    case 'OrganizationExtract': {
      const meta = nodeMetadata.find((m) => m.type === type)
      return (
        meta?.defaultParams ?? {
          model: '',
          aiModelConfigId: null,
        }
      )
    }
    case 'GeocodeAgent': {
      const meta = nodeMetadata.find((m) => m.type === 'GeocodeAgent')
      return { ...(meta?.defaultParams ?? {}) } as Record<string, unknown>
    }
    default: {
      const meta = nodeMetadata.find((m) => m.type === type)
      return { ...(meta?.defaultParams ?? {}) }
    }
  }
}
