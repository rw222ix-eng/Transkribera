/* Godkänn om sparade papper EXAKT som läraren gör det i appen.
   Väntorna pollar med tid, inte requestAnimationFrame (förvalet): 2026-09-19
   stod skriptet still i 60 s på en sida som var redo efter 5, för rAF
   levererade inga bildrutor i den färska profilen.
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
import { readFileSync, statSync } from 'node:fs';
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
  /* Klockan och sökvägen före klicket: PDF:en måste vara skriven EFTER den. */
  const pdfIHogen = () => page.evaluate(
    n => (window.Dokument.sparade().find(v => v.id === n) || {}).pdf || null, id);
  const pdfFore = await pdfIHogen();
  const fore = Date.now();
  /* Filens egen tid före klicket: dok 276 (2026-10-11) hade en gammal PDF
     med mtime före klockan, och «skriven efter klicket» slog till på den. */
  let mtimeFore = null;
  try { mtimeFore = pdfFore ? statSync(pdfFore).mtimeMs : null; } catch { mtimeFore = null; }
  await page.locator('#godkann').click();
  const r = await svar;
  console.log('   approve svarade', r.status());
  /* DEN NYA FILEN, INTE DEN GAMLA (granskningen 2026-09-24 natt). Svaret är
     200 också när godkännandets jobb dör, och ett dokument som godkänts förut
     har redan sin pdf-sökväg i högen. Skriptet skrev då ut den gamla filen,
     och bygg.sh krympte och laddade upp den utan att säga något. Godkänt är
     en NY sökväg i högen, eller samma sökväg till en fil som skrivits om
     efter klicket; annars skrivs ingen «pdf:»-rad. Högen läses om varje
     sekund, för strömmen läses av klienten och sökvägen kommer när den är
     klar. */
  let pdf = null, ny = false;
  for (let t = 0; t < 600 && !ny; t++) {
    pdf = await pdfIHogen().catch(() => null);
    if (pdf && pdf !== pdfFore) ny = true;
    else if (pdf) {
      try {
        const m = statSync(pdf).mtimeMs;
        ny = m >= fore - 2000 && (mtimeFore === null || m !== mtimeFore);
      } catch { ny = false; }
    }
    if (!ny) await vila(1000);
  }
  /* FILEN SKRIVS FÄRDIGT EFTER SVARET (handoff 2026-10-11): sökvägen kommer i
     högen medan appen fortfarande skriver PDF:en, och en fil som lästes eller
     laddades upp direkt var halv. Skriptet svarar först när storleken stått
     still två mätningar i rad med 3 s emellan, och skriver sidantalet. */
  if (pdf && ny) {
    let forra = -1, stabil = false;
    for (let t = 0; t < 60 && !stabil; t++) {
      await vila(3000);
      let nu = -1;
      try { nu = statSync(pdf).size; } catch { nu = -1; }
      stabil = nu > 0 && nu === forra;
      forra = nu;
    }
    if (!stabil) {
      console.log(`   FEL: ${pdf} blev aldrig klar (storleken ändras fortfarande)`);
      process.exitCode = 1;
    }
    let sidor = 0;
    try {
      sidor = (readFileSync(pdf).toString('latin1').match(/\/Type\s*\/Page(?![s\w])/g) || []).length;
    } catch { sidor = 0; }
    console.log('   pdf:', pdf);
    console.log(`   klar: ${forra} byte, ${sidor} sidor`);
  } else {
    console.log(`   FEL: ingen ny PDF för dokument ${id}`
      + (pdf ? ` (${pdf} är inte omskriven, godkännandet föll troligen)` : ' (pdf-fältet kom inte i högen)'));
    process.exitCode = 1;
  }
  await vila(1500);
}
await browser.close();
