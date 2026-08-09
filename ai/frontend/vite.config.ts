import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import services from '../config/services.json'

const bridgeTarget = process.env.BRIDGE_URL
  ?? `http://${services.bridge.host}:${services.bridge.port}`
const bridgeWsTarget = bridgeTarget.replace(/^http/, 'ws')
const frontendPort = Number(process.env.FRONTEND_PORT ?? services.frontend.port)

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    port: frontendPort,
    strictPort: true,
    proxy: {
      '/api': {
        target: bridgeTarget,
        changeOrigin: true,
      },
      '/client-ws': {
        target: bridgeWsTarget,
        ws: true,
      },
      '/live2d-models': {
        target: bridgeTarget,
        changeOrigin: true,
      },
    },
  },
})
