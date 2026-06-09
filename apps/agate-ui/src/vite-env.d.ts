/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string
  readonly VITE_AUTH_API_BASE?: string
  readonly VITE_TIMEZONE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

