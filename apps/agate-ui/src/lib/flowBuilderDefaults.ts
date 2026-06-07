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
      }
    default: {
      const meta = nodeMetadata.find((m) => m.type === type)
      return { ...(meta?.defaultParams ?? {}) }
    }
  }
}

export function getOutputBookendDefaultData(
  type: string,
  workspaceStylebookId?: number | null,
): Record<string, unknown> {
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

export function getMiddleNodeDefaultData(
  type: string,
  workspaceStylebookId?: number | null,
): Record<string, unknown> {
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
      const base = { ...(meta?.defaultParams ?? {}) } as Record<string, unknown>
      if (typeof workspaceStylebookId === 'number') {
        base.stylebook_id = workspaceStylebookId
      }
      return base
    }
    default: {
      const meta = nodeMetadata.find((m) => m.type === type)
      return { ...(meta?.defaultParams ?? {}) }
    }
  }
}
