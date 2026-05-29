import React from 'react'
import { FileText, Tag, Zap, Database, Brain, Filter, Map, MapPinned, Package, Search, Sparkles, Braces, FileJson, Image, Eye, GitBranch, GitMerge, BarChart, Building2, User, Network, BookOpen } from 'lucide-react'
import { nodeMetadata } from '@/nodes/registry'
import { getNodeIconColor as getNodeIconColorFromColors, getNodeBgColor as getNodeBgColorFromColors } from '@/lib/nodeColors'

// Icon mapping for dynamic icon rendering
const iconMap = {
  FileText: FileText,
  Tag: Tag,
  Zap: Zap,
  Database: Database,
  Brain: Brain,
  Filter: Filter,
  Map: Map,
  MapPinned: MapPinned,
  Package: Package,
  Search: Search,
  Sparkles: Sparkles,
  Braces: Braces,
  FileJson: FileJson,
  Image: Image,
  Eye: Eye,
  Split: GitBranch,
  Combine: GitMerge,
  BarChart: BarChart,
  Building2: Building2,
  BookOpen: BookOpen,
  User: User,
  Network: Network,
}

/**
 * Get the icon component for a node type with appropriate color
 */
export function getNodeIcon(type: string, size: string = 'h-4 w-4'): React.ReactElement | null {
  const metadata = nodeMetadata.find(m => m.type === type)
  if (!metadata) return null

  const iconName = metadata.icon as keyof typeof iconMap
  const IconComponent = iconMap[iconName] || FileText
  const colorClass = getNodeIconColorFromColors(type)

  return React.createElement(IconComponent, {
    className: `${size} ${colorClass}`
  })
}

/**
 * Get the color class for a node type
 */
export function getNodeColor(type: string): string {
  return getNodeIconColorFromColors(type)
}

/**
 * Get the label for a node type
 */
export function getNodeLabel(type: string): string {
  const metadata = nodeMetadata.find(m => m.type === type)
  return metadata?.label || type
}

/** Node shape from `Graph['spec']['nodes']` (API / flow editor). */
export type GraphSpecNode = {
  id: string
  type: string
  params?: Record<string, unknown>
}

/**
 * User-facing label for a node in summaries (matches ProcessedItemDetail / visualizations).
 * Falls back to the node-type catalog label, then the raw id if the node is missing from the graph.
 */
export function getNodeStepDisplayName(
  nodes: GraphSpecNode[] | undefined,
  nodeId: string | null | undefined,
  options?: { wholeFlowLabel?: string }
): string {
  const flowLabel = options?.wholeFlowLabel ?? 'Flow'
  if (nodeId == null || nodeId === '') {
    return flowLabel
  }
  const node = nodes?.find((n) => n.id === nodeId)
  if (!node) {
    return nodeId
  }
  const p = node.params ?? {}
  const name = p.name
  const label = p.label
  if (typeof name === 'string' && name.trim()) return name.trim()
  if (typeof label === 'string' && label.trim()) return label.trim()
  return getNodeLabel(node.type)
}

/**
 * Get the background color class for a node type (for colored circles)
 */
export function getNodeBgColor(type: string): string {
  return getNodeBgColorFromColors(type)
}

