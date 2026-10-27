import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// In dev, /api is proxied to the FastAPI server, so the frontend always calls
// same-origin relative URLs. In production FastAPI serves the built app itself,
// so the same relative URLs work unchanged and no CORS or env juggling is needed.
// VITE_API_URL still lets the frontend point at a separately hosted API.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
