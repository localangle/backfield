/**
 * Utilities for translating processed item outputs into visualization descriptors.
 *
 * The goal is to keep the processed item page agnostic of specific node types.
 * Each descriptor describes what type of visualization to render and the data
 * required to render it. Additional node types can extend this registry by
 * adding a VisualizationComponent.tsx file in their node's ui directory.
 */

import type { ProcessedItem, Graph } from '@/lib/api'
import { getNodeOutputById, nodeOutputLookupFromGraphSpec } from '@/lib/nodeOutputs'
import { visualizationComponents } from '@/nodes/registry'
import type React from 'react'

// Shared types for visualizations
export interface MapPointFeature {
  id: string
  coordinates: [number, number] // [longitude, latitude]
  label?: string
  description?: string
  group?: string
}

export interface MapBoundingBoxFeature {
  id: string
  bbox: [number, number, number, number] // [west, south, east, north]
  label?: string
  description?: string
  group?: string
  // Optional: full GeoJSON geometry (Polygon or MultiPolygon) - takes precedence over bbox
  geometry?: {
    type: 'Polygon' | 'MultiPolygon'
    coordinates: number[][][] | number[][][][]
  }
}

export interface VisualizationProps {
  nodeId: string
  nodeLabel: string
  output: any
  mapboxToken?: string
  data?: {
    points: MapPointFeature[]
    polygons: MapBoundingBoxFeature[]
  }
}

export interface VisualizationDescriptor {
  id: string
  nodeId: string
  title: string
  description?: string
  component: React.ComponentType<VisualizationProps>
  requiresMapboxToken?: boolean
  data?: {
    points: MapPointFeature[]
    polygons: MapBoundingBoxFeature[]
  }
  nodeOutput?: any // Store the node-specific output for the component to use
}

export async function getVisualizationsForItem(params: {
  item: ProcessedItem
  graph: Graph | null
}): Promise<VisualizationDescriptor[]> {
  const { item, graph } = params
  if (!item.node_outputs) {
    return []
  }

  type GraphNode = Graph['spec']['nodes'][number]
  const nodeById = new Map<string, GraphNode>()
  if (graph?.spec?.nodes) {
    graph.spec.nodes.forEach((node) => nodeById.set(node.id, node))
  }

  const visuals: VisualizationDescriptor[] = []
  const rawOutputs = item.node_outputs as Record<string, unknown>

  const processOne = async (nodeId: string, output: unknown) => {
    const nodeConfig = nodeById.get(nodeId)
    const nodeType = nodeConfig?.type ?? 'Unknown'
    const nodeLabel =
      nodeConfig?.params?.name ??
      nodeConfig?.params?.label ??
      `${nodeType} (${nodeId})`

    const visualizationLoader = visualizationComponents[nodeType as keyof typeof visualizationComponents]
    if (visualizationLoader) {
      try {
        const visualizationModule = await visualizationLoader()
        if (visualizationModule && typeof visualizationModule.buildVisualization === 'function') {
          const viz = visualizationModule.buildVisualization(nodeId, nodeLabel, output)
          if (viz) {
            viz.nodeOutput = output
            visuals.push(viz)
          }
        }
      } catch (error) {
        console.error(`Failed to load visualization for node type ${nodeType}:`, error)
      }
    }
  }

  const lookup =
    graph?.spec?.nodes && graph.spec.nodes.length > 0 ? nodeOutputLookupFromGraphSpec(graph.spec) : null

  if (graph?.spec?.nodes) {
    for (const node of graph.spec.nodes) {
      const output = getNodeOutputById(rawOutputs, node.id, lookup)
      if (output === undefined) continue
      await processOne(node.id, output)
    }
  } else {
    for (const [key, output] of Object.entries(item.node_outputs)) {
      if (key === '__outputKeysByNodeId' || key.startsWith('__')) continue
      await processOne(key, output)
    }
  }

  return visuals
}

