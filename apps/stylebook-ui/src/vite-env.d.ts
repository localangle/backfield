/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AUTH_API_BASE?: string
  readonly VITE_AGATE_API_BASE?: string
  readonly VITE_STYLEBOOK_API_BASE?: string
  readonly VITE_CORE_API_PROXY_TARGET?: string
  readonly VITE_AGATE_API_PROXY_TARGET?: string
  readonly VITE_STYLEBOOK_API_PROXY_TARGET?: string
  readonly VITE_AGATE_UI_ORIGIN?: string
  readonly VITE_STYLEBOOK_UI_ORIGIN?: string
  readonly VITE_HELP_URL?: string
  readonly VITE_PLAYGROUND_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
