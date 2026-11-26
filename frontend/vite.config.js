import { resolve } from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Two pages:
//   /      index.html      the landing page (static HTML + the design kit in public/assets)
//   /app/  app/index.html  the React app (hash routes: /app/#/book, /app/#/sessions, ...)
// The kit lives in public/assets and is served as plain files, so Vite's own bundles go to
// dist/static instead of dist/assets.
export default defineConfig({
  plugins: [react()],
  build: {
    assetsDir: 'static',
    modulePreload: { polyfill: false },
    rollupOptions: {
      input: {
        landing: resolve(import.meta.dirname, 'index.html'),
        app: resolve(import.meta.dirname, 'app/index.html'),
      },
    },
  },
  server: {
    port: 5173,
    // FastAPI runs on :8000 (uvicorn app.main:app --reload); the app calls /api/... on this origin.
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
});
