import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// Served in prod at /next by FastAPI; built into app/web/next.
// Dev server proxies /api to the running FastAPI (uvicorn) on 8750.
export default defineConfig({
  base: '/next/',
  plugins: [svelte()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8750', changeOrigin: false },
    },
  },
  build: {
    outDir: '../app/web/next',
    emptyOutDir: true,
  },
});
