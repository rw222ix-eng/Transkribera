/* Renderar en eller flera tavlor (wb-json-v1) i Chrome med APPENS motor och
   skriver en skärmdump per fil plus motorns invändningar.

     node e2e/render-board.mjs <spec.json> [fler.json …]
     WB_UT=<mapp>  var bilderna hamnar (förval: e2e/test-results/tavlor)
     WB_PORT=<port> statiska serverns port (förval 8126)

   Motorn som appen ritar med är app/web/ui/tavla-wb.js (WBLayout), samma
   som blad.js ritaTavlan använder. /static/whiteboard/board.html laddar en
   ÄLDRE kopia (components.js + layout.js, vendrade i juli) — två sessioner
   renderade sina few-shots mot den och såg tabellceller radbrytas som appen
   aldrig radbryter. Därför laddar harnesset appens egna filer, inte
   board.html, och därför ligger det i repot: det har byggts om i scratchpad
   två gånger och tappats bort båda gångerna.

   Utfallet: «skalade upp till N %» är motorns fit-pass (innehåll mindre än
   tavlan förstoras) och inget fel. «ryms inte», «element-överlapp» och
   «utanför» är fel. Skriptet avslutar med 1 när något av dem finns. */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HAR = path.dirname(fileURLToPath(import.meta.url));
const ROT = path.resolve(HAR, '..');
const PORT = process.env.WB_PORT || '8126';
const UT = process.env.WB_UT || path.join(HAR, 'test-results', 'tavlor');
const filer = process.argv.slice(2);
if (!filer.length) { console.error('ge minst en spec.json'); process.exit(2); }
fs.mkdirSync(UT, { recursive: true });

/* Statisk server över app/web — samma filer som appen serverar under /ui
   och /static. Ingen appserver behövs: motorn är ren klientkod. */
const server = spawn('python', ['-m', 'http.server', PORT, '--bind', '127.0.0.1',
  '--directory', path.join(ROT, 'app', 'web')], { stdio: 'ignore' });
const bas = `http://127.0.0.1:${PORT}`;
for (let i = 0; i < 200; i++) {
  try { await fetch(`${bas}/ui/tavla-wb.js`, { method: 'HEAD' }); break; }
  catch { await new Promise(r => setTimeout(r, 50)); }
}

const HARNESS = `<!doctype html><html lang="sv"><head><meta charset="utf-8">
<link rel="stylesheet" href="/ui/typsnitt.css">
<link rel="stylesheet" href="/static/vendor/katex/katex.min.css">
<link rel="stylesheet" href="/ui/tavla-wb.css">
<link rel="stylesheet" href="/ui/blad.css">
<style>body{margin:0;padding:12px;background:#2b2b2b}.tavhost{display:inline-block}</style>
</head><body><div class="tavhost" id="host"></div>
<script src="/static/vendor/katex/katex.min.js"></script>
<script src="/static/whiteboard/expr.js"></script>
<script src="/ui/tavla-wb.js"></script>
</body></html>`;

const browser = await chromium.launch({ channel: 'chrome' });
let daligt = 0;
try {
  for (const f of filer) {
    const spec = JSON.parse(fs.readFileSync(f, 'utf8'));
    const page = await browser.newPage({ viewport: { width: 2000, height: 1000 } });
    await page.route('**/harness.html', r => r.fulfill({ contentType: 'text/html', body: HARNESS }));
    const varningar = [];
    page.on('console', m => { const t = m.text(); if (t.startsWith('[WB')) varningar.push(t); });
    page.on('pageerror', e => varningar.push('[WB] pageerror: ' + e.message));
    await page.goto(`${bas}/ui/harness.html`, { waitUntil: 'load' });
    /* Typsnitten måste vara INNE innan motorn mäter — tabellens kolumner
       mäts med canvas i samma typsnitt, och Caveat laddas först när något
       använder det. */
    await page.evaluate(async () => {
      await document.fonts.load("20px 'Caveat'");
      await document.fonts.ready;
    });
    const res = await page.evaluate(spec => {
      /* Samma kompilering som blad.js kurvor(): wb-json bär uttrycken som
         strängar, motorn vill ha funktioner. */
      const kurvor = x => {
        if (Array.isArray(x)) return x.map(kurvor);
        if (!x || typeof x !== 'object') return x;
        const ut = {};
        for (const k of Object.keys(x)) ut[k] = kurvor(x[k]);
        if (ut.kind === 'graph' && Array.isArray(ut.plots)) {
          ut.plots = ut.plots.filter(p => {
            if (typeof p.fn === 'function') return true;
            if (!p.expr) return false;
            try { p.fn = window.WBExpr.compile(p.expr); return true; }
            catch (e) { console.warn(`[WB] ogiltigt uttryck i plots[].expr: '${p.expr}' — ${e.message}`); return false; }
          });
        }
        return ut;
      };
      const host = document.getElementById('host');
      host.innerHTML = '';
      window.WBLayout.renderWhiteboard(kurvor(spec.boards ? spec : { boards: [spec] }), host);
      return new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => {
        /* Sticker något innehåll utanför sin tavla? Motorn varnar om det
           den mäter; det här är en rå kontroll av det som faktiskt ritades. */
        const ut = [];
        document.querySelectorAll('.whiteboard').forEach((b, bi) => {
          const br = b.getBoundingClientRect();
          b.querySelectorAll('*').forEach(el => {
            if (!el.getClientRects().length) return;
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return;
            if (r.right > br.right + 1 || r.bottom > br.bottom + 1 ||
                r.left < br.left - 1 || r.top < br.top - 1) {
              const t = (el.textContent || '').trim().slice(0, 40);
              if (t) ut.push(`tavla ${bi}: "${t}"`);
            }
          });
        });
        r({ utanfor: [...new Set(ut)].slice(0, 8) });
      })));
    }, spec);
    const namn = path.basename(f, '.json');
    const bild = path.join(UT, namn + '.png');
    await page.screenshot({ path: bild, fullPage: true });
    console.log(`\n=== ${namn} ===\n  bild: ${bild}`);
    const alla = [...new Set(varningar)];
    const fel = alla.filter(w => !/skalade upp/.test(w));
    alla.forEach(w => console.log('  ' + (/skalade upp/.test(w) ? '·' : '!') + ' ' + w));
    res.utanfor.forEach(u => console.log('  ! utanför: ' + u));
    if (!alla.length && !res.utanfor.length) console.log('  inga [WB]-varningar');
    if (fel.length || res.utanfor.length) daligt++;
    await page.close();
  }
} finally {
  await browser.close();
  server.kill();
}
process.exit(daligt ? 1 : 0);
