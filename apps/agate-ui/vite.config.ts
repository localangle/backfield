import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath, URL } from 'node:url'

const coreTarget = process.env.VITE_CORE_API_PROXY_TARGET || 'http://localhost:8004'
const agateTarget = process.env.VITE_AGATE_API_PROXY_TARGET || 'http://localhost:8000'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(path.dirname(fileURLToPath(import.meta.url)), './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/v1': {
        target: coreTarget,
        changeOrigin: true,
      },
      '/api/agate': {
        target: agateTarget,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api\/agate/, ''),
      },
    },
  },
})
