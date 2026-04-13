/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string
  readonly VITE_AUTH_API_BASE?: string
  readonly VITE_TIMEZONE?: string
  readonly VITE_MAPBOX_API_TOKEN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

