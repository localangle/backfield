/** Aligns with `execute_graph` JSON: human-readable keys + `__outputKeysByNodeId` index. */

export const NODE_OUTPUT_KEY_INDEX = '__outputKeysByNodeId' as const

export function getNodeOutputKeyMap(
  raw: Record<string, unknown> | null | undefined,
): Record<string, string> | null {
  if (!raw) return null
  const m = raw[NODE_OUTPUT_KEY_INDEX]
  if (m && typeof m === 'object' && !Array.isArray(m)) {
    return m as Record<string, string>
  }
  return null
}

export function getNodeOutputById(
  raw: Record<string, unknown> | null | undefined,
  nodeId: string,
): unknown {
  if (!raw) return undefined
  const map = getNodeOutputKeyMap(raw)
  if (map) {
    const pub = map[nodeId]
    if (pub !== undefined && Object.prototype.hasOwnProperty.call(raw, pub)) {
      return raw[pub]
    }
    return undefined
  }
  return raw[nodeId]
}
