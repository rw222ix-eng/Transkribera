import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// __dirname finns inte i ESM.
const __dirname = path.dirname(fileURLToPath(import.meta.url));

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
  // Sätts explicit (annars defaultar root till process.cwd(), som de relativa
  // server.fs.allow-posterna nedan råkar tolkas mot) och publicDir stängs av: en
  // framtida <repo>/public/-mapp skulle annars auto-serveras i dev och kopieras
  // rakt in i bygget — förbi fs.allow-allowlistan.
  root: __dirname,
  publicDir: false,
  base: command === 'build' ? '/next/' : '/',
  plugins: [svelte()],
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/api': { target: 'http://127.0.0.1:8750', changeOrigin: false },
      // Tavel-iframen laddas från FastAPI (/static/whiteboard/board.html).
      // Proxy — INTE fs.allow: allowlistan för repo-filer lämnas orörd.
      '/static': { target: 'http://127.0.0.1:8750', changeOrigin: false },
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
