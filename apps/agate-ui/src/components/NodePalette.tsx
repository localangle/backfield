import React, { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { FileText, Tag, Zap, Database, Brain, Filter, MapPin, Package, Search, Sparkles, Braces, FileJson, Image, Eye, Plug, User, ChevronDown, ChevronRight, ChevronsDown, ChevronsUp, GitBranch, GitMerge, Building2, BookOpen } from 'lucide-react'
import { nodeMetadata } from '@/nodes/registry'
import { categoryColors, categoryBgColors, getNodeCategory } from '@/lib/nodeColors'

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
  Plug: Plug,
  User: User,
  Building2: Building2,
  BookOpen: BookOpen,
  Split: GitBranch,
  Combine: GitMerge,
}

interface NodeType {
  type: string
  label: string
  icon: React.ReactNode
  description: string
  category: 'input' | 'enrichment' | 'output' | 'filter' | 'geography' | 'formatting' | 'control' | 'people' | 'organization' | 'work' | 'image' | 'text'
}

// Convert metadata to NodeType format (exclude disabled nodes from palette)
const nodeTypes: NodeType[] = nodeMetadata
  .filter((meta) => meta.enabled !== false)
  .map((meta) => {
    const category = getNodeCategory(meta.type)
    const colorClass = categoryColors[category]
    const bgColorClass = categoryBgColors[category]

    return {
      type: meta.type,
      label: meta.label,
      icon: (
        <div className={`flex items-center justify-center w-6 h-6 rounded-full ${bgColorClass}`}>
          {React.createElement(iconMap[meta.icon as keyof typeof iconMap] || FileText, {
            className: `h-4 w-4 ${colorClass}`,
          })}
        </div>
      ),
      description: meta.description || '',
      category: category,
    }
  })

// Group nodes by category
const nodesByCategory = {
  input: nodeTypes.filter((n) => n.category === 'input'),
  enrichment: nodeTypes.filter((n) => n.category === 'enrichment'),
  filter: nodeTypes.filter((n) => n.category === 'filter'),
  output: nodeTypes.filter((n) => n.category === 'output'),
  geography: nodeTypes.filter((n) => n.category === 'geography'),
  formatting: nodeTypes.filter((n) => n.category === 'formatting'),
  control: nodeTypes.filter((n) => n.category === 'control'),
  people: nodeTypes.filter((n) => n.category === 'people'),
  organization: nodeTypes.filter((n) => n.category === 'organization'),
  work: nodeTypes.filter((n) => n.category === 'work'),
  image: nodeTypes.filter((n) => n.category === 'image'),
  text: nodeTypes.filter((n) => n.category === 'text'),
}

const categoryLabels = {
  input: 'Input Nodes',
  enrichment: 'Enrichment Nodes',
  filter: 'Filter Nodes',
  output: 'Output Nodes',
  geography: 'Geography Nodes',
  formatting: 'Other Nodes',
  control: 'Control flow nodes',
  people: 'People Nodes',
  organization: 'Organization Nodes',
  work: 'Work Nodes',
  image: 'Image Nodes',
  text: 'Text Nodes',
} as const

// Define the order of categories in the UI
const categoryOrder: Array<keyof typeof nodesByCategory> = [
  'input',
  'control',
  'enrichment',
  'text',
  'image',
  'geography',
  'people',
  'organization',
  'work',
  'filter',
  'formatting',
  'output'
]

export default function NodePalette() {
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
    new Set() // Start with all categories collapsed by default
  )
  const [searchQuery, setSearchQuery] = useState('')

  const toggleCategory = (category: string) => {
    setExpandedCategories(prev => {
      const newSet = new Set(prev)
      if (newSet.has(category)) {
        newSet.delete(category)
      } else {
        newSet.add(category)
      }
      return newSet
    })
  }

  const expandAllCategories = () => {
    setExpandedCategories(new Set(categoryOrder))
  }

  const collapseAllCategories = () => {
    setExpandedCategories(new Set())
  }

  const allExpanded = categoryOrder.every(category => expandedCategories.has(category))
  const allCollapsed = categoryOrder.every(category => !expandedCategories.has(category))

  const onDragStart = (event: React.DragEvent, nodeType: string) => {
    event.dataTransfer.setData('application/reactflow', nodeType)
    event.dataTransfer.effectAllowed = 'move'
  }

  // Filter nodes based on search query
  const filterNodes = (nodes: NodeType[]) => {
    if (!searchQuery.trim()) return nodes
    const query = searchQuery.toLowerCase()
    return nodes.filter(node => 
      node.label.toLowerCase().includes(query) ||
      node.description.toLowerCase().includes(query) ||
      node.type.toLowerCase().includes(query)
    )
  }

  const filteredNodesByCategory = {
    input: filterNodes(nodesByCategory.input),
    control: filterNodes(nodesByCategory.control),
    enrichment: filterNodes(nodesByCategory.enrichment),
    text: filterNodes(nodesByCategory.text),
    image: filterNodes(nodesByCategory.image),
    geography: filterNodes(nodesByCategory.geography),
    people: filterNodes(nodesByCategory.people),
    organization: filterNodes(nodesByCategory.organization),
    work: filterNodes(nodesByCategory.work),
    filter: filterNodes(nodesByCategory.filter),
    formatting: filterNodes(nodesByCategory.formatting),
    output: filterNodes(nodesByCategory.output),
  }

  return (
    <Card className="w-64 h-full overflow-auto">
      <CardHeader>
        <div className="flex items-center justify-between mb-3">
          <CardTitle className="text-lg">Nodes</CardTitle>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={expandAllCategories}
              disabled={allExpanded}
              className="h-6 w-6 p-0"
              title="Expand all categories"
            >
              <ChevronsDown className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={collapseAllCategories}
              disabled={allCollapsed}
              className="h-6 w-6 p-0"
              title="Collapse all categories"
            >
              <ChevronsUp className="h-3 w-3" />
            </Button>
          </div>
        </div>
        <div className="relative">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search nodes..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 h-9 text-sm"
          />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {searchQuery.trim() && Object.values(filteredNodesByCategory).every(nodes => nodes.length === 0) ? (
          <div className="text-center py-8 text-muted-foreground text-sm">
            No nodes match "{searchQuery}"
          </div>
        ) : (
          categoryOrder.map((category) => {
            const nodes = filteredNodesByCategory[category]
            if (!nodes || nodes.length === 0) return null

            // Auto-expand categories with search results
            const isExpanded = searchQuery.trim() ? true : expandedCategories.has(category)
            const ChevronIcon = isExpanded ? ChevronDown : ChevronRight

            return (
            <div key={category}>
              <button
                onClick={() => toggleCategory(category)}
                className="flex items-center gap-2 w-full text-left mb-2 hover:bg-muted/50 rounded p-1 -m-1 transition-colors"
              >
                <ChevronIcon className="h-3 w-3 text-muted-foreground" />
                <h3 className="text-xs font-semibold text-muted-foreground uppercase">
                  {categoryLabels[category]}
                </h3>
              </button>
              {isExpanded && (
                <div className="space-y-2">
                  {nodes.map((node) => (
                    <div
                      key={node.type}
                      draggable
                      onDragStart={(e) => onDragStart(e, node.type)}
                      className="p-3 border rounded-lg cursor-move hover:border-primary hover:bg-accent transition-colors"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        {node.icon}
                        <span className="font-medium text-sm">{node.label}</span>
                      </div>
                      {node.description && (
                        <p className="text-xs text-muted-foreground">{node.description}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
          })
        )}
      </CardContent>
    </Card>
  )
}

