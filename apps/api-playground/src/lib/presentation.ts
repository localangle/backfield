import type {
  OpenApiParameter,
  OpenApiSchema,
  PlaygroundOperation,
} from "./openapi"

export interface SelectOption {
  value: string
  label: string
  group?: string
}

export type ControlKind =
  | "checkboxes"
  | "date"
  | "meta-builder"
  | "number"
  | "select"
  | "text"
  | "textarea"
  | "typeahead"

export type TypeaheadKind =
  | "article"
  | "location"
  | "mention"
  | "organization"
  | "person"

export interface OptionLoad {
  status: "blocked" | "error" | "loading" | "ready"
  values: Record<string, string[]>
}

export interface PresentationContext {
  projectOptions: SelectOption[]
  articleFacets: OptionLoad
  mentionFacets: OptionLoad
  metadataTypes: OptionLoad
}

export interface FieldPresentation {
  control: ControlKind
  disabled?: boolean
  emptyLabel?: string
  helperText?: string
  options?: SelectOption[]
  placeholder?: string
  typeaheadKind?: TypeaheadKind
  typeLabel: string
  wide?: boolean
}

export interface ParameterSection {
  id: string
  title: string
  description: string
  names: string[]
  wide: Set<string>
}

const ENTITY_OPTIONS: SelectOption[] = [
  { value: "location", label: "Location" },
  { value: "person", label: "Person" },
  { value: "organization", label: "Organization" },
]

const BOOLEAN_OPTIONS: SelectOption[] = [
  { value: "true", label: "True" },
  { value: "false", label: "False" },
]

const DIRECTION_OPTIONS: SelectOption[] = [
  { value: "asc", label: "Ascending" },
  { value: "desc", label: "Descending" },
]

const HUMAN_LABELS: Record<string, string> = {
  asc: "Ascending",
  desc: "Descending",
  pub_date: "Publication date",
  created_at: "Created date",
  sort_key: "Default order",
}

function labelForValue(value: unknown): string {
  const text = String(value)
  return (
    HUMAN_LABELS[text] ??
    text
      .replace(/_/g, " ")
      .replace(/\b\w/g, (character) => character.toUpperCase())
  )
}

function optionsFromValues(values: string[] | undefined): SelectOption[] {
  return (values ?? []).map((value) => ({ value, label: labelForValue(value) }))
}

function enumOptions(schema: OpenApiSchema | undefined): SelectOption[] | undefined {
  if (!schema?.enum?.length) return undefined
  return schema.enum.map((value) => ({
    value: String(value),
    label: labelForValue(value),
  }))
}

function loadedOptions(
  load: OptionLoad,
  key: string,
  noun: string,
): Pick<FieldPresentation, "disabled" | "emptyLabel" | "options"> {
  const values = load.values[key] ?? []
  if (load.status === "blocked") {
    return { disabled: true, emptyLabel: "Select a project first", options: [] }
  }
  if (load.status === "loading") {
    return { disabled: true, emptyLabel: "Loading choices…", options: [] }
  }
  if (load.status === "error") {
    return { disabled: true, emptyLabel: "Choices unavailable", options: [] }
  }
  return {
    disabled: values.length === 0,
    emptyLabel: values.length ? `Any ${noun}` : `No ${noun} values available`,
    options: optionsFromValues(values),
  }
}

function sortOptions(operation: PlaygroundOperation): SelectOption[] {
  if (operation.displayPath === "/articles/search") {
    return optionsFromValues(["relevance", "pub_date"])
  }
  if (operation.displayPath.endsWith("/mentions")) {
    return optionsFromValues(["article", "created_at"])
  }
  if (operation.group === "People") {
    return optionsFromValues(["sort_key", "recent", "label"])
  }
  return optionsFromValues(["label", "recent"])
}

function includeOptions(operation: PlaygroundOperation): SelectOption[] {
  const detailPath = /^\/articles\/\{article_id\}$/.test(operation.displayPath)
  return [
    { value: "counts", label: "Mention counts" },
    ...(detailPath ? [{ value: "text", label: "Full article text" }] : []),
  ]
}

function helperTextForField(
  operation: PlaygroundOperation,
  name: string,
  location: OpenApiParameter["in"] | "body",
): string | undefined {
  if (name === "q" && operation.displayPath === "/articles/search") {
    return 'Supports quoted phrases, OR, and -term exclusions.'
  }
  if (name === "use_hyde" && location === "body") {
    return "When true, generates a hypothetical answer and embeds that for retrieval."
  }
  if (name === "resolution" && operation.displayPath === "/articles/geo-cells") {
    return "Leave blank to derive resolution from the bounding-box size."
  }
  if (name === "radius_miles") {
    return "Required together with center_lng and center_lat."
  }
  if (name === "include") {
    return /^\/articles\/\{article_id\}$/.test(operation.displayPath)
      ? "counts adds mention totals; text includes the article body."
      : "counts adds mention totals for each article."
  }
  return undefined
}

export function presentationForField(
  operation: PlaygroundOperation,
  name: string,
  schema: OpenApiSchema | undefined,
  description: string | undefined,
  context: PresentationContext,
  location: OpenApiParameter["in"] | "body",
): FieldPresentation {
  if (location === "path" && name === "project_slug") {
    return {
      control: "select",
      emptyLabel: context.projectOptions.length
        ? "Select a project"
        : "No projects available",
      options: context.projectOptions,
      typeLabel: "String",
      wide: true,
    }
  }

  if (location === "path" && name === "h3_cell") {
    return {
      control: "textarea",
      helperText:
        "One H3 cell per line. A single cell uses this endpoint; multiple cells are sent as a batch query.",
      placeholder: "One H3 cell ID per line",
      typeLabel: "String",
      wide: true,
    }
  }

  const typeaheadKinds: Record<string, TypeaheadKind> = {
    article_id: "article",
    location_id: "location",
    mention_id: "mention",
    organization_id: "organization",
    person_id: "person",
  }
  const typeaheadKind = location === "path" ? typeaheadKinds[name] : undefined
  if (typeaheadKind) {
    return {
      control: "typeahead",
      placeholder: `Search ${typeaheadKind === "person" ? "people" : `${typeaheadKind}s`}…`,
      typeaheadKind,
      typeLabel: typeaheadKind === "article" || typeaheadKind === "mention"
        ? "Integer"
        : "String",
      wide: true,
    }
  }

  if (name === "meta") {
    return {
      control: "meta-builder",
      typeLabel: "Repeatable string",
      wide: true,
    }
  }

  if (name === "author" || name === "external_source") {
    const noun = name === "author" ? "author" : "source"
    return {
      control: "select",
      typeLabel: "String",
      ...loadedOptions(
        context.articleFacets,
        name === "author" ? "authors" : "externalSources",
        noun,
      ),
    }
  }

  if (name === "meta_type") {
    return {
      control: "select",
      typeLabel: "String",
      ...loadedOptions(context.metadataTypes, "metaTypes", "metadata type"),
    }
  }

  if (name === "entity_type" || name === "has_mentions" || name === "to_entity_type") {
    return {
      control: "select",
      emptyLabel: name === "has_mentions" ? "Any mention type" : "Any entity type",
      options: ENTITY_OPTIONS,
      typeLabel: "String",
    }
  }

  const mentionFacetKeys: Record<string, string> = {
    nature: "natures",
    location_type: "locationTypes",
    person_type: "personTypes",
    organization_type: "organizationTypes",
  }
  const mentionFacetKey = mentionFacetKeys[name]
  if (mentionFacetKey) {
    return {
      control: schema?.type === "array" ? "checkboxes" : "select",
      typeLabel: schema?.type === "array" ? "Repeatable string" : "String",
      ...loadedOptions(
        context.mentionFacets,
        mentionFacetKey,
        name.replace(/_/g, " "),
      ),
    }
  }

  if (name === "include") {
    return {
      control: "checkboxes",
      emptyLabel: "No extra details",
      helperText: helperTextForField(operation, name, location),
      options: includeOptions(operation),
      typeLabel: "Repeatable string",
      wide: true,
    }
  }

  if (name === "sort") {
    return {
      control: "select",
      emptyLabel: "Default",
      options: enumOptions(schema) ?? sortOptions(operation),
      typeLabel: "String",
    }
  }

  if (name === "sort_direction") {
    return {
      control: "select",
      emptyLabel: "Default",
      options: enumOptions(schema) ?? DIRECTION_OPTIONS,
      typeLabel: "String",
    }
  }

  if (name === "pub_date_from" || name === "pub_date_to") {
    return {
      control: "date",
      typeLabel: "Date",
    }
  }

  if (name === "q" || name === "query") {
    const articleKeywordSearch =
      name === "q" && operation.displayPath === "/articles/search"
    return {
      control: "text",
      helperText: helperTextForField(operation, name, location),
      placeholder:
        name === "query"
          ? "Describe the articles you want to find"
          : articleKeywordSearch
            ? 'For example: budget OR "city council"'
            : undefined,
      typeLabel: "String",
      wide: true,
    }
  }

  if (name === "bbox") {
    return {
      control: "text",
      placeholder: "-87.8,41.7,-87.5,42.0",
      typeLabel: "Coordinates",
      wide: true,
    }
  }

  if (name === "cells") {
    return {
      control: "textarea",
      placeholder: "One H3 cell ID per line",
      typeLabel: "Repeatable string",
      wide: true,
    }
  }

  if (name === "inputs") {
    return {
      control: "textarea",
      placeholder: '{\n  "input_name": "value"\n}',
      typeLabel: "JSON object",
      wide: true,
    }
  }

  const options = enumOptions(schema)
  if (options) {
    return {
      control: "select",
      options,
      typeLabel: schema?.type === "integer" ? "Integer" : "String",
    }
  }

  if (schema?.type === "boolean") {
    return {
      control: "select",
      helperText: helperTextForField(operation, name, location),
      options: BOOLEAN_OPTIONS,
      typeLabel: "Boolean",
    }
  }

  if (schema?.type === "array") {
    return {
      control: "textarea",
      placeholder: "One value per line or comma-separated",
      typeLabel: "Repeatable string",
      wide: true,
    }
  }

  if (schema?.type === "integer" || schema?.type === "number") {
    return {
      control: "number",
      helperText: helperTextForField(operation, name, location),
      placeholder:
        schema.default !== undefined ? `Default: ${String(schema.default)}` : undefined,
      typeLabel: schema.type === "integer" ? "Integer" : "Number",
    }
  }

  return {
    control: "text",
    typeLabel: "String",
  }
}

const PAGING_NAMES = new Set(["sort", "sort_direction", "limit", "offset"])
const RESPONSE_NAMES = new Set(["include"])
const SEARCH_NAMES = new Set(["q", "query"])
const AREA_NAMES = new Set([
  "bbox",
  "center_lng",
  "center_lat",
  "radius_miles",
  "resolution",
  "h3_cell",
  "cells",
])

function sectionForField(
  name: string,
  location: OpenApiParameter["in"] | "body",
): string {
  if (name === "project_slug") return "project"
  if (location === "header") return "headers"
  if (location === "path") return "resource"
  if (SEARCH_NAMES.has(name)) return "search"
  if (AREA_NAMES.has(name)) return "area"
  if (PAGING_NAMES.has(name)) return "page"
  if (RESPONSE_NAMES.has(name)) return "response"
  return "filters"
}

const SECTION_COPY: Record<string, [string, string]> = {
  project: ["Project", "Choose the project for this request."],
  resource: ["Resource", "Identify the resource you want to retrieve."],
  search: ["Search", "Describe or enter the records you want to find."],
  area: ["Area", "Define the geographic area for this request."],
  filters: ["Filters", "Add only the filters you need. Empty fields are not sent."],
  page: ["Sort and page", "Control result order and pagination."],
  response: ["Response details", "Optionally include additional fields in the response."],
  headers: ["Request options", "Configure optional request behavior."],
}

const SECTION_ORDER = [
  "project",
  "resource",
  "search",
  "area",
  "filters",
  "page",
  "response",
  "headers",
]

export function sectionsForOperation(
  parameters: OpenApiParameter[],
): ParameterSection[] {
  const groups = new Map<string, string[]>()
  for (const parameter of parameters) {
    const section = sectionForField(parameter.name, parameter.in)
    groups.set(section, [...(groups.get(section) ?? []), parameter.name])
  }
  return SECTION_ORDER.flatMap((id) => {
    const names = groups.get(id)
    if (!names?.length) return []
    const [title, description] = SECTION_COPY[id]
    return [{
      id,
      title,
      description,
      names,
      wide: new Set(
        names.filter((name) =>
          ["project_slug", "q", "query", "meta", "bbox", "cells", "include", "h3_cell"].includes(name),
        ),
      ),
    }]
  })
}

export function sectionsForBodyFields(names: string[]): ParameterSection[] {
  const groups = new Map<string, string[]>()
  for (const name of names) {
    const section = sectionForField(name, "body")
    groups.set(section, [...(groups.get(section) ?? []), name])
  }
  return SECTION_ORDER.flatMap((id) => {
    const sectionNames = groups.get(id)
    if (!sectionNames?.length) return []
    const [title, description] = SECTION_COPY[id]
    return [{
      id: `body-${id}`,
      title,
      description,
      names: sectionNames,
      wide: new Set(
        sectionNames.filter((name) =>
          ["query", "meta", "cells", "inputs", "include"].includes(name),
        ),
      ),
    }]
  })
}

export function operationNeedsArticleFacets(operation: PlaygroundOperation): boolean {
  const names = new Set(operation.parameters.map((parameter) => parameter.name))
  return names.has("author") || names.has("external_source")
}

export function operationNeedsMentionFacets(operation: PlaygroundOperation): boolean {
  const names = new Set(operation.parameters.map((parameter) => parameter.name))
  return ["nature", "location_type", "person_type", "organization_type"].some((name) =>
    names.has(name),
  )
}

export function operationNeedsMetadataTypes(operation: PlaygroundOperation): boolean {
  return operation.parameters.some((parameter) => parameter.name === "meta_type")
}

