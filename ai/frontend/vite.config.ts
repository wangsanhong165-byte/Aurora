import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:9528',
        changeOrigin: true,
      },
      '/client-ws': {
        target: 'ws://127.0.0.1:9528',
        ws: true,
      },
      '/live2d-models': {
        target: 'http://127.0.0.1:9528',
        changeOrigin: true,
      },
    },
  },
})
