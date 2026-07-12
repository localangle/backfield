import react from "@vitejs/plugin-react"
import path from "path"
import { fileURLToPath, URL } from "node:url"
import { defineConfig } from "vite"

const coreTarget = process.env.VITE_CORE_API_PROXY_TARGET || "http://localhost:8004"
const agateTarget = process.env.VITE_AGATE_API_PROXY_TARGET || "http://localhost:8000"
const stylebookApiTarget =
  process.env.VITE_STYLEBOOK_API_PROXY_TARGET || "http://localhost:8003"

const appRoot = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    // @backfield/ui ships source that imports react-router-dom; without dedupe/alias,
    // Vite can resolve the package's nested copy and Link/NavLink lose Router context
    // ("Cannot destructure property 'basename' of useContext(...) as it is null").
    dedupe: ["react", "react-dom", "react-router", "react-router-dom"],
    alias: {
      "@": path.resolve(appRoot, "./src"),
      "react-router-dom": path.resolve(appRoot, "./node_modules/react-router-dom"),
      "react-router": path.resolve(appRoot, "./node_modules/react-router"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
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
