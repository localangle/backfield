import react from "@vitejs/plugin-react"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { defineConfig, type Plugin } from "vite"

const appRoot = path.dirname(fileURLToPath(import.meta.url))

// Leaflet basemaps load raster tiles from CARTO (see GeoAreaMap / H3CellMap).
const mapTileImgSrc = "https://*.basemaps.cartocdn.com"

const productionCsp = [
  "default-src 'none'",
  "script-src 'self'",
  "style-src 'self'",
  `img-src 'self' data: ${mapTileImgSrc}`,
  "font-src 'self'",
  "connect-src 'self' https://*.backfield.news",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'",
  "object-src 'none'",
].join("; ")

const developmentCsp = [
  "default-src 'none'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: ${mapTileImgSrc}`,
  "connect-src 'self' http://localhost:8003 http://127.0.0.1:8003 http://localhost:8004 http://127.0.0.1:8004 ws://localhost:* ws://127.0.0.1:*",
  "base-uri 'none'",
  "form-action 'none'",
  "object-src 'none'",
].join("; ")

function securityMetaPlugin(isProduction: boolean): Plugin {
  return {
    name: "playground-security-meta",
    transformIndexHtml: {
      order: "pre",
      handler() {
        return [
          {
            tag: "meta",
            attrs: {
              "http-equiv": "Content-Security-Policy",
              content: isProduction ? productionCsp : developmentCsp,
            },
            injectTo: "head-prepend",
          },
        ]
      },
    },
  }
}

export default defineConfig(({ command }) => ({
  plugins: [securityMetaPlugin(command === "build"), react()],
  resolve: {
    // Shared UI dependencies must use the Playground's React instance.
    dedupe: ["react", "react-dom"],
    alias: [
      {
        find: /^react$/,
        replacement: path.resolve(appRoot, "node_modules/react"),
      },
      {
        find: /^react-dom$/,
        replacement: path.resolve(appRoot, "node_modules/react-dom"),
      },
    ],
  },
  server: {
    host: "0.0.0.0",
    port: 5176,
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    server: {
      deps: {
        // Transform Radix so React aliases apply to the linked shared package in tests.
        inline: [/@radix-ui/],
      },
    },
  },
}))
