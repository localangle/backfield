import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export interface PlaceExtractLocationTypesResponse {
  types: string[]
}

export async function fetchPlaceExtractLocationTypes(): Promise<PlaceExtractLocationTypesResponse> {
  return stylebookJsonFetch<PlaceExtractLocationTypesResponse>("/v1/place-extract-location-types")
}
