export type LayerId = string

export type LayerVisibility = Record<LayerId, boolean>

export type GroupedFeature = {
  group?: string | null
}

export type LayerOption = {
  id: LayerId
  label: string
}

function normalizeLayerId(raw: string): string {
  return raw.trim()
}

export function layersFromFeatures(features: GroupedFeature[]): LayerOption[] {
  const seen = new Set<string>()
  const out: LayerOption[] = []

  for (const f of features) {
    const g = (f.group ?? "").trim()
    if (!g) continue
    const id = normalizeLayerId(g)
    if (!id || seen.has(id)) continue
    seen.add(id)
    out.push({ id, label: id })
  }

  // Stable ordering: alphabetical, case-insensitive
  out.sort((a, b) => a.label.toLowerCase().localeCompare(b.label.toLowerCase()))
  return out
}

export function defaultVisibility(layers: LayerOption[]): LayerVisibility {
  const vis: LayerVisibility = {}
  for (const layer of layers) vis[layer.id] = true
  return vis
}

export function toggleLayer(visibility: LayerVisibility, layerId: LayerId): LayerVisibility {
  return { ...visibility, [layerId]: !(visibility[layerId] ?? true) }
}

export function showAll(layers: LayerOption[]): LayerVisibility {
  const vis: LayerVisibility = {}
  for (const layer of layers) vis[layer.id] = true
  return vis
}

export function hideAll(layers: LayerOption[]): LayerVisibility {
  const vis: LayerVisibility = {}
  for (const layer of layers) vis[layer.id] = false
  return vis
}

export function isLayerVisible(visibility: LayerVisibility, layerId: LayerId): boolean {
  return visibility[layerId] ?? true
}

