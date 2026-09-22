/* Ladda ner ett papper med APPENS egen knapp «Ladda ner PDF» (#fh-pdf).

   Syskon till godkann-tavla.mjs. Tavlans knapp ritar av brädena och bokens
   lösningsark i webbläsaren och sätter dem på A4 hos servern (POST
   /api/tavla/pdf) — filen finns alltså inte förrän knappen tryckts, och
   ingen API-rutt ger samma papper.

     cd e2e && node ladda-ner.mjs <mapp> <dokument_id> [fler …] */
import path from 'node:path';
import fs from 'node:fs';
import { iAppen, vila, hogen, tillPlaneringen, losningslaget } from './appen.mjs';

const mapp = process.argv[2];
const ids = process.argv.slice(3).map(Number).filter(n => Number.isFinite(n));
if (!mapp || !ids.length) {
  console.log('ange mapp och minst ett dokument-id');
  process.exit(2);
}
fs.mkdirSync(mapp, { recursive: true });

await iAppen(async (page) => {
  const filer = [];
  for (const id of ids) {
    const d = await hogen(page);
    const rad = ((d || {}).sparade || []).find(r => r.id === id);
    const v = rad && (rad.dokument || (rad.versioner || [])[rad.markor || 0]);
    if (!v) throw new Error(`dokument ${id} ligger inte i högen — godkänt?`);
    console.log(`== dokument ${id} · ${v.typ} · ${v.klass} · ${v.moment}`);
    const los = losningslaget(v);
    if (los) {
      console.log(`   lösningsposter: ${los.skrivna}/${los.av} skrivna`);
      /* Ett ark med platshållare är värre än inget ark: läraren delar ut det
         och upptäcker hålet framför klassen. Hellre stopp här. */
      if (los.klara < los.av) throw new Error(
        `${los.av - los.klara} av ${los.av} lösningsposter är oskrivna — `
        + 'öppna pappret i appen och låt skrivningen gå klart först');
    }

    /* Förhandsvisningen är där knappen sitter, och den öppnas ur högen på
       samma index som appen själv använder. */
    await tillPlaneringen(page);
    const i = await page.evaluate(n => window.Dokument.sparade()
      .findIndex(x => x.id === n), id);
    if (i < 0) throw new Error(`dokument ${id} syns inte i sidans hög`);
    await page.evaluate(k => window.Dokument.visa(k), i);
    await page.locator('#forhandsskal').waitFor({ state: 'visible', timeout: 30000 });
    /* Motorn ritar tavlan och bladen; avritningen mäter DOM:en och kan inte
       göra det innan typsnitten är i bruk (img.decode() räcker inte — se
       blad-bild.js). */
    await page.evaluate(() => document.fonts.ready);
    await vila(4000);

    const nedladdning = page.waitForEvent('download', { timeout: 300000 });
    await page.locator('#fh-pdf').click();
    const fil = path.join(mapp, (await nedladdning).suggestedFilename());
    await (await nedladdning).saveAs(fil);
    const bytes = fs.statSync(fil).size;
    /* En blob som aldrig blev en PDF sparas lika tyst som en riktig fil. */
    const huvud = fs.readFileSync(fil, { encoding: 'latin1', flag: 'r' }).slice(0, 5);
    if (!huvud.startsWith('%PDF')) throw new Error(`${fil} är ingen PDF`);
    console.log(`   sparade ${fil} ${bytes} byte`);
    filer.push(fil);
    await page.locator('#fh-stang').click().catch(() => {});
    await vila(1500);
  }
  return filer;
});
