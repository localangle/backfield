import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath, URL } from 'node:url'

const coreTarget = process.env.VITE_CORE_API_PROXY_TARGET || 'http://localhost:8004'
const agateTarget = process.env.VITE_AGATE_API_PROXY_TARGET || 'http://localhost:8000'
const stylebookTarget = process.env.VITE_STYLEBOOK_API_PROXY_TARGET || 'http://localhost:8003'

const appRoot = path.dirname(fileURLToPath(import.meta.url))

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    // Keep a single react-router instance so @backfield/ui Link/NavLink share
    // BrowserRouter context from this app (avoids null basename context crashes).
    dedupe: ['react', 'react-dom', 'react-router', 'react-router-dom'],
    alias: {
      '@': path.resolve(appRoot, './src'),
      'react-router-dom': path.resolve(appRoot, './node_modules/react-router-dom'),
      'react-router': path.resolve(appRoot, './node_modules/react-router'),
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
      '/api/stylebook': {
        target: stylebookTarget,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api\/stylebook/, ''),
      },
    },
  },
})
