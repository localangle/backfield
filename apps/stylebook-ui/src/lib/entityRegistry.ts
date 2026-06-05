/**
 * Central registry of Stylebook entity types and their EntityConfig objects.
 */

import {
  locationPickerConfig,
  organizationPickerConfig,
  workPickerConfig,
} from "@/lib/entityConfigs/connectionPickers"
import { personConfig } from "@/lib/entityConfigs/person"
import type { EntityConfig, EntityType } from "@/lib/entityTypes"
import type { LucideIcon } from "lucide-react"
import { BookOpen, Building2, MapPin, Users } from "lucide-react"

export const ENTITY_REGISTRY: Record<EntityType, EntityConfig<unknown>> = {
  location: locationPickerConfig as EntityConfig<unknown>,
  person: personConfig as EntityConfig<unknown>,
  organization: organizationPickerConfig as EntityConfig<unknown>,
  work: workPickerConfig as EntityConfig<unknown>,
}

export interface EntityHomeCard {
  entityType: EntityType
  /** URL segment under the catalog base path (e.g. ``locations``, ``people``). */
  routeSegment: string
  icon: LucideIcon
  description: string
  /** When true, canonical list is the primary entry (locations). */
  canonicalFirst?: boolean
}

export const ENTITY_HOME_CARDS: EntityHomeCard[] = [
  {
    entityType: "location",
    routeSegment: "locations",
    icon: MapPin,
    description: "Canonical places and locations",
    canonicalFirst: true,
  },
  {
    entityType: "person",
    routeSegment: "people",
    icon: Users,
    description: "Canonical people",
    canonicalFirst: true,
  },
  {
    entityType: "organization",
    routeSegment: "organizations",
    icon: Building2,
    description: "Canonical organizations and institutions",
  },
  {
    entityType: "work",
    routeSegment: "works",
    icon: BookOpen,
    description: "Canonical works (laws, reports, books, products, artworks)",
  },
]

export function entityDisplayName(entityType: EntityType, plural = false): string {
  const config = ENTITY_REGISTRY[entityType]
  return plural ? config.displayName.plural : config.displayName.singular
}
