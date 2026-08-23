import { describe, expect, it } from "vitest"

import {
  profileLinesForLocation,
  profileLinesForOrganization,
  profileLinesForPerson,
} from "@/lib/connectionGraphEntityProfile"

describe("connectionGraphEntityProfile", () => {
  it("formats person title and affiliation on separate lines", () => {
    expect(
      profileLinesForPerson({
        title: "President of Baseball Operations",
        affiliation: "Chicago Cubs",
      }),
    ).toEqual(["President of Baseball Operations", "Chicago Cubs"])
  })

  it("formats organization type", () => {
    expect(
      profileLinesForOrganization({
        organization_type: "sports_team",
      }),
    ).toEqual(["Sports team"])
  })

  it("formats location type and address", () => {
    expect(
      profileLinesForLocation({
        location_type: "city",
        formatted_address: "Chicago, IL",
      }),
    ).toEqual(["City", "Chicago, IL"])
  })
})
