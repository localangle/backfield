import { getNodeLabel } from '@/lib/nodeUtils'

export const INGRESS_NODE_TYPES = new Set(['TextInput', 'JSONInput', 'S3Input'])

/** Stable slug for public API `inputs` keys; lowercase letters, digits, underscores. */
export function sanitizePublicAlias(raw: string): string {
  const slug = raw
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
    .replace(/[^a-z0-9_]/g, '')
    .replace(/_+/g, '_')
    .replace(/^[_0-9]+/, '')
  return slug || 'input'
}

/** Derive a public API input key from the node display name (no manual typing). */
export function inferIngressPublicAlias(
  nodeType: string,
  nodeData?: Record<string, unknown>,
): string {
  const name = typeof nodeData?.name === 'string' ? nodeData.name.trim() : ''
  const label = typeof nodeData?.label === 'string' ? nodeData.label.trim() : ''
  const source = name || label || getNodeLabel(nodeType)
  return sanitizePublicAlias(source)
}

export function resolveIngressPublicAlias(
  nodeType: string,
  nodeData?: Record<string, unknown>,
): string {
  const existing =
    typeof nodeData?.public_alias === 'string' ? nodeData.public_alias.trim() : ''
  return existing || inferIngressPublicAlias(nodeType, nodeData)
}
