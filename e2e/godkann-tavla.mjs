/* Godkänn en sparad TAVLA exakt som läraren gör det i appen.
   Syskon till godkann-avritat.mjs (arbetsblad/gruppuppgift). Tavlan har
   ingen exam-rad att vänta på: appens #godkann gör tre saker för den —
   utkastGodkann (dokumentet blir godkänt och hamnar på lektionskortet),
   POST /api/planning/{wbId}/approve (planned_lessons + lektionsminnet) och
   POST /api/planning/export med PNG:en (arkivkopian, tavla-bild.js). Bara
   appens egen knapp gör alla tre; ett API-anrop till approve ensamt ger
   varken kort eller bild (minnet tavlan-fran-borjan, 2026-09-20).

   Skriptet fanns som e2e/_godkann-tavla.tmp.mjs 2026-09-17 och raderades;
   nu ligger det i repot.

     cd e2e && node godkann-tavla.mjs <dokument_id> [fler …] */
import { chromium } from 'playwright';

const BAS = process.env.APP || 'http://127.0.0.1:18731';
const ids = process.argv.slice(2).map(Number);
const browser = await chromium.launch({ channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } });
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
    return { i, typ: s[i].typ, moment: s[i].moment, wbId: s[i].wbId, status: s[i].status };
  }, id);
  console.log(`== dokument ${id} · ${info.typ} · ${info.moment} · wbId ${info.wbId}`);
  if (info.typ !== 'Tavla' || !info.wbId) { console.log('   hoppar: inte en servertavla'); continue; }
  await page.getByRole('tab', { name: 'Planering' }).click();
  await page.evaluate(i => window.Dokument.visa(i), info.i);
  await page.locator('#forhandsskal').waitFor({ state: 'visible', timeout: 30000 });
  await vila(2500);
  await page.locator('#fh-fortsatt').click();
  await page.locator('#forhandsskal').waitFor({ state: 'hidden', timeout: 30000 });
  await page.locator('#dokument').waitFor({ state: 'visible', timeout: 30000 });
  /* Motorn ska ha ritat färdigt innan avritningen (tavla-bild.js) tar bilden. */
  await vila(3000);
  const approve = page.waitForResponse(r => r.url().includes(`/api/planning/${info.wbId}/approve`), { timeout: 120000 });
  const exportet = page.waitForResponse(r => r.url().includes('/api/planning/export'), { timeout: 180000 });
  await page.locator('#godkann').click();
  console.log('   approve svarade', (await approve).status());
  console.log('   export svarade', (await exportet).status());
  const status = await page.waitForFunction(n => {
    const v = window.Dokument.sparade().find(v => v.id === n);
    return v && v.status === 'godkant' ? 'godkant' : null;
  }, id, { timeout: 60000 }).then(h => h.jsonValue()).catch(() => null);
  console.log('   status:', status || '(dokumentet fick aldrig status godkant i högen)');
  await vila(1500);
}
await browser.close();
