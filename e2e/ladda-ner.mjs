/* Ladda ner ett papper med APPENS egen knapp «Ladda ner PDF» (#fh-pdf).

   Syskon till godkann-tavla.mjs. Tavlans knapp ritar av brädena och bokens
   lösningsark i webbläsaren och sätter dem på A4 hos servern (POST
   /api/tavla/pdf) — filen finns alltså inte förrän knappen tryckts, och
   ingen API-rutt ger samma papper. Därför en riktig webbläsare.

     cd e2e && node ladda-ner.mjs <mapp> <dokument_id> [fler …] */
import { chromium } from 'playwright';
import path from 'node:path';
import fs from 'node:fs';

const BAS = process.env.APP || 'http://127.0.0.1:18731';
const mapp = process.argv[2];
const ids = process.argv.slice(3).map(Number);
if (!mapp || !ids.length) { console.log('ange mapp och minst ett dokument-id'); process.exit(2); }
fs.mkdirSync(mapp, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1600, height: 1200 }, acceptDownloads: true });
page.on('pageerror', e => console.log('  [pageerror]', String(e).slice(0, 200)));
const vila = ms => new Promise(r => setTimeout(r, ms));

for (const id of ids) {
  await page.goto(BAS + '/', { waitUntil: 'load' });
  await page.waitForFunction(() => window.Dokument && window.API && window.API.pa
    && window.Kalender && window.Kalender.franServern(), null, { timeout: 60000, polling: 500 });
  await page.waitForFunction(n => window.Dokument.sparade().some(v => v.id === n), id, { timeout: 60000, polling: 500 });
  await page.evaluate(() => document.fonts.ready);
  const info = await page.evaluate(n => {
    const s = window.Dokument.sparade(); const i = s.findIndex(v => v.id === n);
    const v = s[i];
    const los = ((v.bokuppg || {}).losning || {}).poster || [];
    return { i, typ: v.typ, moment: v.moment, klass: v.klass,
             poster: los.length, skrivna: los.filter(p => p.text).length };
  }, id);
  console.log(`== dokument ${id} · ${info.typ} · ${info.klass} · ${info.moment}`);
  console.log(`   lösningsposter: ${info.skrivna}/${info.poster} skrivna`);
  await page.getByRole('tab', { name: 'Planering' }).click();
  await page.evaluate(i => window.Dokument.visa(i), info.i);
  await page.locator('#forhandsskal').waitFor({ state: 'visible', timeout: 30000 });
  /* Motorn ritar tavlan och bladen; avritningen mäter DOM:en och måste vänta. */
  await vila(4000);
  const nedladdning = page.waitForEvent('download', { timeout: 300000 });
  await page.locator('#fh-pdf').click();
  const d = await nedladdning;
  const fil = path.join(mapp, d.suggestedFilename());
  await d.saveAs(fil);
  console.log('   sparade', fil, fs.statSync(fil).size, 'byte');
  await vila(1500);
}
await browser.close();
