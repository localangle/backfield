/**
 * Must match ``backfield_ai.constants`` platform integration_key values (Core API).
 * User-facing labels use product language (Geocode Earth, not Pelias).
 */
export const PLATFORM_INTEGRATION_KEYS = {
  geocodeEarth: 'platform.geocode.geocode_earth',
  geocodio: 'platform.geocode.geocodio',
  braveSearch: 'platform.search.brave',
  s3AccessKeyId: 'platform.storage.s3_access_key_id',
  s3SecretAccessKey: 'platform.storage.s3_secret_access_key',
  s3SessionToken: 'platform.storage.s3_session_token',
} as const

export const PLATFORM_INTEGRATION_KEY_LIST: string[] = Object.values(PLATFORM_INTEGRATION_KEYS)

export const PROJECT_OVERRIDE_ENV_KEYS = [
  'PELIAS_API_KEY',
  'GEOCODIO_API_KEY',
  'BRAVE_SEARCH_API_KEY',
  'AWS_ACCESS_KEY_ID',
  'AWS_SECRET_ACCESS_KEY',
  'AWS_SESSION_TOKEN',
] as const
