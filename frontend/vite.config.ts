import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const fromBase = (env.VITE_API_BASE_URL || env.VITE_API_BASE || '').replace(/\/+$/, '').replace(/\/api$/i, '')
  const apiTarget = (env.VITE_API_PROXY_TARGET || fromBase || 'http://54.234.242.199:8082').replace(/\/+$/, '')

  return {
    plugins: [react()],
    server: {
      host: true,
      port: 5173,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          secure: false,
        },
      },
    },
  }
})
