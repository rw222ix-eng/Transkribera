/* Plocka upp utkastet som ligger framme, vänta in bokens lösningsförslag och
   godkänn det — precis som läraren gör i appen.

   Appen skriver bokens lösningsark själv när utkastet plockas upp
   (plan.js skrivBokLosningar → POST /api/bocker/{id}/losningar), och det tar
   minuter. Godkännandet måste vänta på det: en PATCH som kommer efter
   godkännandet skriver på en rad som inte längre är utkast.

     cd e2e && node utkast-godkann.mjs [--utan-losningar] */
import { chromium } from 'playwright';

const BAS = process.env.APP || 'http://127.0.0.1:18731';
const utanLos = process.argv.includes('--utan-losningar');
const browser = await chromium.launch({ channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } });
page.on('pageerror', e => console.log('  [pageerror]', String(e).slice(0, 200)));
const vila = ms => new Promise(r => setTimeout(r, ms));

await page.goto(BAS + '/', { waitUntil: 'load' });
await page.waitForFunction(() => window.Dokument && window.API && window.API.pa
  && window.Kalender && window.Kalender.franServern(), null, { timeout: 60000, polling: 500 });
await page.evaluate(() => document.fonts.ready);

/* Utkastet ur RADEN, inte ur sidan: skrivningen PATCH:ar raden och det är den
   som avgör om lösningarna är skrivna. */
const rad = async () => page.evaluate(() => fetch('/api/dokument')
  .then(r => r.json())
  .then(d => {
    const u = d.utkast;
    if (!u) return null;
    const v = (u.versioner || [])[u.markor] || (u.versioner || [])[0];
    if (!v) return null;
    const p = ((v.bokuppg || {}).losning || {}).poster || [];
    return { id: u.id, typ: v.typ, moment: v.moment, klass: v.klass,
             datum: v.datum, wbId: v.wbId,
             poster: p.length,
             klara: p.filter(x => x.text || x.olast || x.okand).length };
  }));

let u = await rad();
if (!u) { console.log('inget utkast ligger framme'); await browser.close(); process.exit(1); }
console.log(`== utkast ${u.id} · ${u.typ} · ${u.klass} · ${u.moment} · ${u.datum}`);
console.log(`   lösningsposter: ${u.klara}/${u.poster}`);

if (!utanLos && u.poster) {
  const slut = Date.now() + 45 * 60 * 1000;
  while (u.klara < u.poster && Date.now() < slut) {
    await vila(15000);
    const f = await rad();
    if (!f || f.id !== u.id) { console.log('   utkastet byttes ut under väntan'); break; }
    if (f.klara !== u.klara) console.log(`   lösningsposter: ${f.klara}/${f.poster}`);
    u = f;
  }
  if (u.klara < u.poster) console.log('   VARNING: alla poster blev inte skrivna');
}

/* Knappen bor i planeringens steg 4, och den fliken är inte den appen öppnar
   på: utan det här klicket står #godkann i en gömd flik och Playwright väntar
   ut sin timeout på ett element som finns men inte syns. */
await page.getByRole('tab', { name: 'Planering' }).click();
await page.locator('#dokument').waitFor({ state: 'visible', timeout: 30000 });
await page.locator('#godkann').scrollIntoViewIfNeeded();
await vila(2000);
const wbId = u.wbId;
const approve = wbId ? page.waitForResponse(
  r => r.url().includes(`/api/planning/${wbId}/approve`), { timeout: 120000 }) : null;
const exportet = wbId ? page.waitForResponse(
  r => r.url().includes('/api/planning/export'), { timeout: 300000 }) : null;
await page.locator('#godkann').click();
if (approve) console.log('   approve svarade', (await approve).status());
if (exportet) console.log('   export svarade', (await exportet).status());
/* Raden behåller sitt id: godkännandet är en PATCH på utkastraden, inte en ny
   post (plan.js utkastGodkann). Att leta upp pappret på MOMENTET i högen gav
   ett annat dokument med samma rubrik. */
const status = await page.evaluate(n => fetch('/api/dokument').then(r => r.json())
  .then(d => ((d.sparade || []).find(x => x.id === n) ? 'godkant' : 'saknas')),
  u.id).catch(() => 'okänt');
console.log(`   dokument ${u.id}: ${status}`);
await vila(2000);
await browser.close();
