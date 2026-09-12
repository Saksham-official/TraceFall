import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // The api container publishes no host port; nginx on :80 is the only way in.
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true, secure: false } },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    globals: true,
    // e2e/ belongs to Playwright and needs a running stack. Vitest picking it up gives a
    // confusing "did not expect test.describe() to be called here" instead of a skip.
    exclude: ['node_modules/**', 'e2e/**', 'dist/**'],
  },
})
