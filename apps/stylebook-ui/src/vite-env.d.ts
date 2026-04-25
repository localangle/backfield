/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AUTH_API_BASE?: string
  readonly VITE_AGATE_API_BASE?: string
  readonly VITE_STYLEBOOK_API_BASE?: string
  readonly VITE_CORE_API_PROXY_TARGET?: string
  readonly VITE_AGATE_API_PROXY_TARGET?: string
  readonly VITE_STYLEBOOK_API_PROXY_TARGET?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
