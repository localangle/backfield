import { nodeMetadata } from '@/nodes/registry'

// Color mapping by category
export const categoryColors = {
  input: 'text-blue-500',
  enrichment: 'text-green-500',
  filter: 'text-orange-500',
  output: 'text-slate-500',
  geography: 'text-purple-500',
  formatting: 'text-red-500',
  control: 'text-cyan-500',
  people: 'text-indigo-500',
  organization: 'text-amber-600',
  work: 'text-teal-600',
  image: 'text-orange-500',
  text: 'text-orange-500',
} as const

// Background color mapping by category (for colored circles)
export const categoryBgColors = {
  input: 'bg-blue-100',
  enrichment: 'bg-green-100',
  filter: 'bg-orange-100',
  output: 'bg-slate-100',
  geography: 'bg-purple-100',
  formatting: 'bg-red-100',
  control: 'bg-cyan-100',
  people: 'bg-indigo-100',
  organization: 'bg-amber-100',
  work: 'bg-teal-100',
  image: 'bg-orange-100',
  text: 'bg-orange-100',
} as const

// Category type sets
export const geographyTypes = new Set([
  'GeocodeSimple',
  'GeocodeAgent',
  'CustomGeographies',
  'PlaceExtract',
  'PlaceReview',
])
export const imageTypes = new Set(['EmbedImages', 'ImageEnrich'])
export const textTypes = new Set(['Embed', 'LLMEnrich', 'StatsNode'])
export const peopleTypes = new Set(['PersonExtract', 'PeopleExtract', 'PeopleClassify'])
export const organizationTypes = new Set(['OrganizationsExtract', 'OrgLocationConnections'])
export const workTypes = new Set(['WorksExtract'])
export const formattingTypes = new Set(['LLMFormat'])
export const controlTypes = new Set(['ArraySplitter', 'ArrayGather', 'Gather'])

type MetadataCategory = 'input' | 'enrichment' | 'extraction' | 'organization' | 'output' | 'filter' | 'review' | 'formatting' | 'control'
export type NodeCategory = 'input' | 'enrichment' | 'output' | 'filter' | 'geography' | 'formatting' | 'control' | 'people' | 'organization' | 'work' | 'image' | 'text'

/**
 * Get the category for a node type based on scaffold node metadata categories.
 */
export function getNodeCategory(nodeType: string): NodeCategory {
  const metadata = nodeMetadata.find(m => m.type === nodeType)
  if (!metadata) return 'input' // Default fallback

  const metadataCategory = metadata.category as MetadataCategory
  
  if (geographyTypes.has(nodeType)) {
    return 'geography'
  } else if (imageTypes.has(nodeType)) {
    return 'image'
  } else if (textTypes.has(nodeType)) {
    return 'text'
  } else if (peopleTypes.has(nodeType)) {
    return 'people'
  } else if (organizationTypes.has(nodeType)) {
    return 'organization'
  } else if (workTypes.has(nodeType)) {
    return 'work'
  } else if (formattingTypes.has(nodeType)) {
    return 'formatting'
  } else if (controlTypes.has(nodeType)) {
    return 'control'
  } else if (metadataCategory === 'formatting') {
    return 'formatting'
  } else if (metadataCategory === 'control') {
    return 'control'
  } else if (metadataCategory === 'organization') {
    return 'organization'
  } else if (metadataCategory === 'work') {
    return 'work'
  } else if (metadataCategory === 'extraction') {
    return 'people' // Map old extraction category to people for PeopleExtract
  } else if (metadataCategory === 'review') {
    return 'geography' // Map PlaceReview to geography
  } else if (metadataCategory === 'embedding') {
    return 'formatting' // Fallback for other embedding types
  } else {
    return metadataCategory as NodeCategory
  }
}

/**
 * Get the icon color class for a node type
 */
export function getNodeIconColor(nodeType: string): string {
  const category = getNodeCategory(nodeType)
  return categoryColors[category] || 'text-gray-500'
}

/**
 * Get the background color class for a node type
 */
export function getNodeBgColor(nodeType: string): string {
  const category = getNodeCategory(nodeType)
  return categoryBgColors[category] || 'bg-gray-100'
}
