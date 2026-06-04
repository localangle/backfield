import { describe, expect, it } from "vitest"
import { parseCsvRows } from "@/lib/parseCsv"

describe("parseCsvRows", () => {
  it("parses quoted fields that contain commas", () => {
    const csv = [
      "name,title,affiliation,type,public_figure,sort_key",
      'Daniel La Spata,Alderman,"1st Ward, Chicago",Politician,true,La Spata',
    ].join("\n")

    expect(parseCsvRows(csv)).toEqual([
      {
        name: "Daniel La Spata",
        title: "Alderman",
        affiliation: "1st Ward, Chicago",
        type: "Politician",
        public_figure: "true",
        sort_key: "La Spata",
      },
    ])
  })

  it("parses simple unquoted rows", () => {
    const csv = [
      "name,title,affiliation,type,public_figure,sort_key",
      "Jane Doe,Mayor,City Hall,official,true,Doe",
    ].join("\n")

    expect(parseCsvRows(csv)).toEqual([
      {
        name: "Jane Doe",
        title: "Mayor",
        affiliation: "City Hall",
        type: "official",
        public_figure: "true",
        sort_key: "Doe",
      },
    ])
  })
})
