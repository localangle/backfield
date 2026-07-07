import { Link } from "react-router-dom"

import { cleanupEntityDetailPath, type CleanupEntityType } from "@/lib/cleanupChecks"
import type { StylebookActivityEvent } from "@/lib/stylebook-api/activity"

export interface ActivityEntityRef {
  label: string
  href?: string
}

function isCanonicalEntityType(
  value: string | null | undefined,
): value is CleanupEntityType {
  return value === "location" || value === "person" || value === "organization"
}

export function formatActivityEventType(eventType: string): string {
  return eventType
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ")
}

function entityRef(
  entityType: string | null | undefined,
  entityId: string | null | undefined,
  entityLabel: string | null | undefined,
  catalogBasePath: string,
  scopeSuffix: string,
): ActivityEntityRef | null {
  const label = (entityLabel || "").trim()
  if (!label) return null
  if (isCanonicalEntityType(entityType) && entityId) {
    return {
      label,
      href: cleanupEntityDetailPath(
        catalogBasePath,
        entityType,
        entityId,
        scopeSuffix,
      ),
    }
  }
  return { label }
}

function resolvePrimaryEntityRef(
  event: StylebookActivityEvent,
  catalogBasePath: string,
  scopeSuffix: string,
): ActivityEntityRef | null {
  switch (event.event_type) {
    case "cleanup_keep":
    case "cleanup_keep_separate":
      return null
    case "substrate_linked":
      return null
    default:
      return entityRef(
        event.entity_type,
        event.entity_id,
        event.entity_label,
        catalogBasePath,
        scopeSuffix,
      )
  }
}

function resolveRelatedEntityRef(
  event: StylebookActivityEvent,
  catalogBasePath: string,
  scopeSuffix: string,
): ActivityEntityRef | null {
  switch (event.event_type) {
    case "canonical_created":
    case "canonical_updated":
    case "canonical_deleted":
      return null
    case "substrate_linked":
      return entityRef(
        event.related_entity_type,
        event.related_entity_id,
        event.related_entity_label || event.entity_label,
        catalogBasePath,
        scopeSuffix,
      )
    case "cleanup_keep":
      return entityRef(
        event.related_entity_type,
        event.related_entity_id,
        event.related_entity_label,
        catalogBasePath,
        scopeSuffix,
      )
    default:
      return entityRef(
        event.related_entity_type,
        event.related_entity_id,
        event.related_entity_label,
        catalogBasePath,
        scopeSuffix,
      )
  }
}

export function buildActivityEventSummary(
  event: StylebookActivityEvent,
  catalogBasePath: string,
  scopeSuffix: string,
): {
  title: string
  primary: ActivityEntityRef | null
  related: ActivityEntityRef | null
} {
  return {
    title: formatActivityEventType(event.event_type),
    primary: resolvePrimaryEntityRef(event, catalogBasePath, scopeSuffix),
    related: resolveRelatedEntityRef(event, catalogBasePath, scopeSuffix),
  }
}

function ActivityEntityLabel({ entityRef }: { entityRef: ActivityEntityRef }) {
  if (entityRef.href) {
    return (
      <Link to={entityRef.href} className="text-primary hover:underline">
        {entityRef.label}
      </Link>
    )
  }
  return <span>{entityRef.label}</span>
}

export function ActivityEventSummary({
  event,
  catalogBasePath,
  scopeSuffix,
}: {
  event: StylebookActivityEvent
  catalogBasePath: string
  scopeSuffix: string
}) {
  const { title, primary, related } = buildActivityEventSummary(
    event,
    catalogBasePath,
    scopeSuffix,
  )

  return (
    <>
      {title}
      {primary || related ? ": " : null}
      {primary ? <ActivityEntityLabel entityRef={primary} /> : null}
      {primary && related ? " → " : null}
      {related ? <ActivityEntityLabel entityRef={related} /> : null}
    </>
  )
}
