/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** The release this bundle was built from: the image's tag, set by the Docker build. */
  readonly VITE_APP_VERSION?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
