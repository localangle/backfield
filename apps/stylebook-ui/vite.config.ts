import react from "@vitejs/plugin-react"
import path from "path"
import { fileURLToPath, URL } from "node:url"
import { defineConfig } from "vite"

const coreTarget = process.env.VITE_CORE_API_PROXY_TARGET || "http://localhost:8004"
const agateTarget = process.env.VITE_AGATE_API_PROXY_TARGET || "http://localhost:8000"
const stylebookApiTarget =
  process.env.VITE_STYLEBOOK_API_PROXY_TARGET || "http://localhost:8003"

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(path.dirname(fileURLToPath(import.meta.url)), "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5175,
    proxy: {
      "/v1": {
        target: coreTarget,
        changeOrigin: true,
      },
      "/api/agate": {
        target: agateTarget,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api\/agate/, ""),
      },
      "/api/stylebook": {
        target: stylebookApiTarget,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api\/stylebook/, ""),
      },
    },
  },
})
