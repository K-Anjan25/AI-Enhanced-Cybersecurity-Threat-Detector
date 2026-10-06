/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  server: {
    // Bind to all interfaces so the sandbox preview proxy can reach the dev
    // server (NFR-08). Origin/host are left permissive for the same reason.
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      // The browser must never call the backend directly; the dev server
      // proxies relative /api and /ws URLs to it.
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8000', ws: true },
      // The overview's pipeline strip reads the scrape directly (T-403), and
      // /readyz tells it which dependency is down. Both are same-origin paths in
      // the browser; this is what makes them reach the backend in development.
      '/metrics': { target: 'http://localhost:8000', changeOrigin: true },
      '/readyz': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
    allowedHosts: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
});
