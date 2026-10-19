import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    port: 5173,
    // Forward API calls to the sidecar so the browser sees one origin (no CORS).
    proxy: {
      '/api': 'http://127.0.0.1:8787',
    },
  },
})
