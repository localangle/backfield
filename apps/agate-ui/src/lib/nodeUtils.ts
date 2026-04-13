import React from 'react'
import { FileText, Tag, Zap, Database, Brain, Filter, MapPin, Package, Search, Sparkles, Braces, FileJson, Image, Eye, GitBranch, GitMerge, BarChart, Building2, User, Network, BookOpen } from 'lucide-react'
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
  MapPin: MapPin,
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

/**
 * Get the background color class for a node type (for colored circles)
 */
export function getNodeBgColor(type: string): string {
  return getNodeBgColorFromColors(type)
}

