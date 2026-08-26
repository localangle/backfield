import { useEffect, useState } from "react"

import type { EntityType } from "@/lib/entityTypes"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"
import {
  getCanonicalLocation,
  type CanonicalLocation,
} from "@/lib/stylebook-api/locations"
import {
  getCanonicalOrganization,
  type CanonicalOrganization,
} from "@/lib/stylebook-api/organizations"
import {
  getCanonicalPerson,
  type CanonicalPerson,
} from "@/lib/stylebook-api/people"

export type GraphEntityProfileLines = string[]

function personProfileLines(
  person: Pick<CanonicalPerson, "title" | "affiliation">,
): GraphEntityProfileLines {
  const lines: string[] = []
  const title = person.title?.trim()
  const affiliation = person.affiliation?.trim()
  if (title) lines.push(title)
  if (affiliation) lines.push(affiliation)
  return lines
}

function organizationProfileLines(
  org: Pick<CanonicalOrganization, "organization_type">,
): GraphEntityProfileLines {
  const type = org.organization_type?.trim()
  return type ? [placeExtractTypeLabel(type)] : []
}

function locationProfileLines(
  location: Pick<CanonicalLocation, "location_type" | "formatted_address">,
): GraphEntityProfileLines {
  const lines: string[] = []
  const type = location.location_type?.trim()
  if (type) lines.push(placeExtractTypeLabel(type))
  const address = location.formatted_address?.trim()
  if (address) lines.push(address)
  return lines
}

export async function fetchGraphEntityProfile(
  stylebookSlug: string,
  entityType: EntityType,
  entityId: string,
  projectSlug?: string,
): Promise<GraphEntityProfileLines> {
  if (entityType === "person") {
    const person = await getCanonicalPerson(entityId, stylebookSlug, projectSlug)
    return personProfileLines(person)
  }
  if (entityType === "organization") {
    const organization = await getCanonicalOrganization(entityId, stylebookSlug, projectSlug)
    return organizationProfileLines(organization)
  }
  if (entityType === "location") {
    const location = await getCanonicalLocation(entityId, stylebookSlug, projectSlug)
    return locationProfileLines(location)
  }
  return []
}

export function profileLinesForPerson(
  person: Pick<CanonicalPerson, "title" | "affiliation">,
): GraphEntityProfileLines {
  return personProfileLines(person)
}

export function profileLinesForOrganization(
  organization: Pick<CanonicalOrganization, "organization_type">,
): GraphEntityProfileLines {
  return organizationProfileLines(organization)
}

export function profileLinesForLocation(
  location: Pick<CanonicalLocation, "location_type" | "formatted_address">,
): GraphEntityProfileLines {
  return locationProfileLines(location)
}

const profileCache = new Map<string, GraphEntityProfileLines>()

function profileCacheKey(
  stylebookSlug: string,
  entityType: EntityType,
  entityId: string,
): string {
  return `${stylebookSlug}:${entityType}:${entityId}`
}

export function useGraphEntityProfile(
  stylebookSlug: string,
  entityType: EntityType,
  entityId: string,
  projectSlug?: string,
  seedLines?: GraphEntityProfileLines,
): { lines: GraphEntityProfileLines; loading: boolean } {
  const cacheKey = profileCacheKey(stylebookSlug, entityType, entityId)
  const [lines, setLines] = useState<GraphEntityProfileLines>(
    () => seedLines ?? profileCache.get(cacheKey) ?? [],
  )
  const [loading, setLoading] = useState(
    () => !(seedLines?.length || profileCache.has(cacheKey)),
  )

  useEffect(() => {
    const seeded = seedLines?.length ? seedLines : profileCache.get(cacheKey)
    if (seeded?.length) {
      setLines(seeded)
      setLoading(false)
      profileCache.set(cacheKey, seeded)
      return
    }

    let active = true
    // Reset so a previous entity's lines never show while this entity's fetch is in flight.
    setLines(profileCache.get(cacheKey) ?? [])
    setLoading(true)
    void fetchGraphEntityProfile(stylebookSlug, entityType, entityId, projectSlug)
      .then((fetched) => {
        if (!active) return
        profileCache.set(cacheKey, fetched)
        setLines(fetched)
      })
      .catch(() => {
        if (!active) return
        setLines([])
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [cacheKey, entityId, entityType, projectSlug, seedLines, stylebookSlug])

  return { lines, loading }
}
