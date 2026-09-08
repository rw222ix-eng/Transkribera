/* Godkänn om sparade papper EXAKT som läraren gör det i appen:
   förhandsvisning → «Fortsätt ändra» → «Godkänn och sätt som PDF».

   Varför det här finns (2026-09-08): tools/dokument_godkann.py godkänner via
   API:t utan `blad`, och då bygger servern pappret i LaTeX. För ARBETSBLAD och
   gruppuppgift är det fel papper: deras PDF är skärmens avritning (blad-bild.js,
   routes_exam approve «Skärmen är PDF:ens förlaga»). Sex blad gick ut till
   eleverna i LaTeX-form innan skillnaden syntes. Att ropa BladBild.dokument(v)
   utanför canvasen räcker inte heller: sättningen mäter innan plåtarna hunnit
   in och tomma sidor uppstår. Den enda vägen som ger samma fil som appen är
   appens egen knapp, och det är den som trycks här.

   Kör mot den riktiga servern (APP=http://127.0.0.1:18731 som förval), en
   dokumentrad i taget, och skriver om PDF:en på disk:

     cd e2e && node godkann-avritat.mjs <dokument_id> [fler …] */
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
    && window.Kalender && window.Kalender.franServern(), null, { timeout: 60000 });
  await page.waitForFunction(n => window.Dokument.sparade().some(v => v.id === n), id, { timeout: 60000 });
  await page.evaluate(() => document.fonts.ready);
  const info = await page.evaluate(n => {
    const s = window.Dokument.sparade(); const i = s.findIndex(v => v.id === n);
    return { i, titel: s[i].titel, provId: s[i].provId, sidor: (s[i].uppgifter || []).length };
  }, id);
  console.log(`== dokument ${id} · ${info.titel} · exam ${info.provId}`);
  await page.getByRole('tab', { name: 'Planering' }).click();
  await page.evaluate(i => window.Dokument.visa(i), info.i);
  await page.locator('#forhandsskal').waitFor({ state: 'visible', timeout: 30000 });
  await vila(2500);
  await page.locator('#fh-fortsatt').click();
  await page.locator('#forhandsskal').waitFor({ state: 'hidden', timeout: 30000 });
  await page.locator('#dokument').waitFor({ state: 'visible', timeout: 30000 });
  /* Låt canvasen sätta färdigt och bilderna laddas innan avritningen. */
  await page.waitForFunction(() => [...document.querySelectorAll('#arkskal img')].every(im => im.complete), null, { timeout: 30000 }).catch(() => {});
  await vila(3000);
  const svar = page.waitForResponse(r => r.url().includes(`/api/exams/${info.provId}/approve`), { timeout: 600000 });
  await page.locator('#godkann').click();
  const r = await svar;
  console.log('   approve svarade', r.status());
  /* Strömmen läses av klienten; vi väntar på att högen fått sin pdf-sökväg. */
  const pdf = await page.waitForFunction(n => (window.Dokument.sparade().find(v => v.id === n) || {}).pdf, id, { timeout: 600000 })
    .then(h => h.jsonValue()).catch(() => null);
  console.log('   pdf:', pdf || '(pdf-fältet kom inte i högen)');
  await vila(1500);
}
await browser.close();
