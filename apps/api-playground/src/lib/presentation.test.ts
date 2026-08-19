import { describe, expect, it } from "vitest"

import publicOpenApi from "../../../../docs/api/public.openapi.json"
import {
  jsonBodySchema,
  listOperations,
  parseOpenApiDocument,
  resolveInputSchema,
} from "./openapi"
import {
  presentationForField,
  sectionsForBodyFields,
  sectionsForOperation,
  type PresentationContext,
} from "./presentation"

const blockedContext: PresentationContext = {
  projectOptions: [],
  articleFacets: { status: "blocked", values: {} },
  mentionFacets: { status: "blocked", values: {} },
  metadataTypes: { status: "blocked", values: {} },
}

describe("endpoint presentation contract", () => {
  const document = parseOpenApiDocument(publicOpenApi)
  const operations = listOperations(document)

  it("covers every public operation and every supported parameter exactly once", () => {
    expect(operations).toHaveLength(49)

    for (const operation of operations) {
      const parameters = operation.parameters.filter(
        (parameter) => parameter.in !== "cookie",
      )
      const presentedNames = sectionsForOperation(parameters).flatMap(
        (section) => section.names,
      )
      const parameterNames = parameters.map((parameter) => parameter.name)
      expect(
        new Set(presentedNames),
        `${operation.method.toUpperCase()} ${operation.displayPath}`,
      ).toEqual(new Set(parameterNames))
      expect(presentedNames).toHaveLength(parameterNames.length)
    }
  })

  it("uses consistent semantic controls across endpoint families", () => {
    for (const operation of operations) {
      for (const parameter of operation.parameters) {
        const schema = resolveInputSchema(document, parameter.schema)
        const presentation = presentationForField(
          operation,
          parameter.name,
          schema,
          parameter.description,
          blockedContext,
          parameter.in,
        )
        expect(presentation.control).toBeTruthy()
        if (parameter.name === "project_slug") expect(presentation.control).toBe("select")
        if (parameter.name === "meta") expect(presentation.control).toBe("meta-builder")
        if (parameter.name === "attr") expect(presentation.control).toBe("textarea")
        if (
          parameter.name === "pub_date_from" ||
          parameter.name === "pub_date_to"
        ) {
          expect(presentation.control).toBe("date")
        }
        if (parameter.name === "limit" || parameter.name === "offset") {
          expect(presentation.control).toBe("number")
        }
        if (
          ["article_id", "location_id", "mention_id", "organization_id", "person_id"].includes(
            parameter.name,
          )
        ) {
          expect(presentation.control).toBe("typeahead")
        }
      }
    }
  })

  it("keeps only non-obvious helper text", () => {
    const articleSearch = operations.find(
      (operation) => operation.displayPath === "/articles/search",
    )
    const semanticSearch = operations.find(
      (operation) => operation.displayPath === "/articles/semantic-search",
    )
    const coverage = operations.find(
      (operation) => operation.displayPath === "/articles/geo-cells",
    )
    const peopleList = operations.find(
      (operation) => operation.displayPath === "/people",
    )
    expect(articleSearch).toBeDefined()
    expect(semanticSearch).toBeDefined()
    expect(coverage).toBeDefined()
    expect(peopleList).toBeDefined()

    expect(
      presentationForField(
        articleSearch!,
        "q",
        { type: "string" },
        "Keyword match",
        blockedContext,
        "query",
      ).helperText,
    ).toMatch(/quoted phrases/)
    expect(
      presentationForField(
        articleSearch!,
        "limit",
        { type: "integer", default: 25 },
        "Maximum results",
        blockedContext,
        "query",
      ).helperText,
    ).toBeUndefined()
    expect(
      presentationForField(
        semanticSearch!,
        "use_hyde",
        { type: "boolean", default: false },
        "When true, use HyDE",
        blockedContext,
        "body",
      ).helperText,
    ).toMatch(/hypothetical/)
    expect(
      presentationForField(
        coverage!,
        "resolution",
        { type: "integer" },
        "Optional H3 display resolution",
        blockedContext,
        "query",
      ).helperText,
    ).toMatch(/Leave blank/)
    expect(
      presentationForField(
        peopleList!,
        "attr",
        { type: "array", items: { type: "string" } },
        "Attribute filter",
        blockedContext,
        "query",
      ).helperText,
    ).toMatch(/One clause per line/)
    const peopleInclude = presentationForField(
      peopleList!,
      "include",
      { type: "array", items: { type: "string" } },
      "Include extras",
      blockedContext,
      "query",
    )
    expect(peopleInclude.options).toEqual([
      { value: "metadata", label: "Stylebook attributes" },
    ])
    expect(peopleInclude.helperText).toMatch(/include metadata/i)

    const articleSearchInclude = presentationForField(
      articleSearch!,
      "include",
      { type: "array", items: { type: "string" } },
      "Include extras",
      blockedContext,
      "query",
    )
    expect(articleSearchInclude.options).toEqual([
      { value: "counts", label: "Mention counts" },
      { value: "images", label: "Attached images" },
    ])
    expect(articleSearchInclude.helperText).toMatch(/images includes up to 10/)

    const semanticInclude = presentationForField(
      semanticSearch!,
      "include",
      { type: "array", items: { type: "string" } },
      "Include extras",
      blockedContext,
      "body",
    )
    expect(semanticInclude.options).toEqual(articleSearchInclude.options)

    const articleDetail = operations.find(
      (operation) => operation.displayPath === "/articles/{article_id}",
    )
    expect(articleDetail).toBeDefined()
    const detailInclude = presentationForField(
      articleDetail!,
      "include",
      { type: "array", items: { type: "string" } },
      "Include extras",
      blockedContext,
      "query",
    )
    expect(detailInclude.options).toEqual([
      { value: "counts", label: "Mention counts" },
      { value: "text", label: "Full article text" },
    ])
    expect(detailInclude.helperText).toMatch(/already includes up to 10 images/)

    const personArticles = operations.find(
      (operation) => operation.displayPath === "/people/{person_id}/articles",
    )
    expect(personArticles).toBeDefined()
    expect(
      presentationForField(
        personArticles!,
        "include",
        { type: "array", items: { type: "string" } },
        "Include extras",
        blockedContext,
        "query",
      ).options,
    ).toEqual(articleSearchInclude.options)
  })

  it("presents every request-body property through the shared field model", () => {
    const bodyOperations = operations.filter((operation) => jsonBodySchema(operation))
    expect(bodyOperations).toHaveLength(2)

    for (const operation of bodyOperations) {
      const schema = resolveInputSchema(document, jsonBodySchema(operation))
      const properties = schema?.properties ?? {}
      const names = Object.keys(properties)
      const presentedNames = sectionsForBodyFields(names).flatMap(
        (section) => section.names,
      )
      expect(new Set(presentedNames)).toEqual(new Set(names))
      for (const name of names) {
        const fieldSchema = resolveInputSchema(document, properties[name])
        const presentation = presentationForField(
          operation,
          name,
          fieldSchema,
          fieldSchema?.description,
          blockedContext,
          "body",
        )
        expect(presentation.control).toBeTruthy()
      }
    }
  })
})
