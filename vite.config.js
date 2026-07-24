import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// Vite-roten ÄR repo-roten. Det är ett krav från Impeccables live-läge: det skriver
// temp-variantkomponenter till <projectRoot>/node_modules/.impeccable-live/, och Vite
// transformerar bara filer som ligger inuti sin egen rot. Med Vite-roten i en
// undermapp levererades .svelte-filerna otransformerade och varianterna kunde aldrig
// monteras.
//
// base gäller ENBART bygget. I dev serveras appen från roten så att rot-absoluta
// verktygs-URL:er (/node_modules/.impeccable-live/*) löser ut.
//
// SÄKERHET: eftersom roten är repo-roten skulle dev-servern annars kunna servera hela
// repot över HTTP — inklusive Transkriberingar/ och andra filer med känslig elevdata.
// server.fs.allow är därför en ALLOWLIST: bara frontendens källa, node_modules och
// rotens index.html är servbara. Servern binder dessutom bara till 127.0.0.1, och
// filbevakningen ignorerar datamappar.
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/next/' : '/',
  plugins: [svelte()],
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/api': { target: 'http://127.0.0.1:8750', changeOrigin: false },
    },
    fs: {
      strict: true,
      allow: ['frontend/src', 'node_modules', 'index.html'],
    },
    watch: {
      ignored: [
        '**/Transkriberingar/**',
        '**/downloads/**',
        '**/app/web/next/**',
        '**/.superpowers/**',
        '**/e2e/.test-data*/**',
        '**/bin/**',
      ],
    },
  },
  build: {
    outDir: 'app/web/next',
    emptyOutDir: true,
  },
}));
