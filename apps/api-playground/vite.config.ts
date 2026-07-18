import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vite"

const productionCsp = [
  "default-src 'none'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
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
  "img-src 'self' data:",
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
  server: {
    host: "0.0.0.0",
    port: 5176,
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
}))
