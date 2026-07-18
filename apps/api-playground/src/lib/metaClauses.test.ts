import { describe, expect, it } from "vitest"

import {
  metaCategoryLabel,
  metaConditionsToText,
  parseMetaClauses,
} from "./metaClauses"

describe("meta clause grammar", () => {
  it("parses include, exclude, and multi-category clauses", () => {
    const conditions = parseMetaClauses(
      "topic:local_government_politics\n!format:opinion\nsubject:schools|housing\ntimeframe",
    )

    expect(conditions).toMatchObject([
      {
        metaType: "topic",
        exclude: false,
        categories: ["local_government_politics"],
      },
      { metaType: "format", exclude: true, categories: ["opinion"] },
      { metaType: "subject", exclude: false, categories: ["schools", "housing"] },
      { metaType: "timeframe", exclude: false, categories: [] },
    ])
  })

  it("round-trips conditions back to clause text", () => {
    const text = "topic:politics|schools\n!format:opinion\nscope"
    expect(metaConditionsToText(parseMetaClauses(text))).toBe(text)
  })

  it("drops blank tokens and empty types", () => {
    expect(parseMetaClauses(" , \n : \n\n")).toEqual([])
  })

  it("labels machine values for display", () => {
    expect(metaCategoryLabel("local_government_politics")).toBe(
      "Local government politics",
    )
    expect(metaCategoryLabel("opinion")).toBe("Opinion")
  })
})
