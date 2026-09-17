/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Public backend origin, without the /api/v1 suffix. */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
