/**
 * Basemap used by Agate, Stylebook, and the API Playground.
 * OpenStreetMap's tile policy requires this host and a valid Referer on web requests.
 */
export const OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

export const OSM_TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'

/** Origin only: enough for OpenStreetMap, and it does not include the page path or query. */
export const OSM_TILE_REFERRER_POLICY = "strict-origin-when-cross-origin" as const
