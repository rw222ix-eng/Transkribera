/* Det de små drivrutinerna delar: en webbläsare på lärarens app, väntan på
   att den är laddad, och en stängning som sker även när något går sönder.

   Skripten (godkann-tavla, godkann-avritat, utkast-godkann, ladda-ner) hade
   var sin kopia av samma tjugo rader, och kopiorna gled isär: en väntade på
   Kalender.franServern, en inte, och ingen av dem stängde webbläsaren när ett
   klick timade ut — ett Chrome-fönster per misslyckad körning blev kvar med
   kvarhållen port. Felkoden saknades också, så ett `node … | tail` såg ut som
   en lyckad körning. */
import { chromium } from 'playwright';

export const BAS = process.env.APP || 'http://127.0.0.1:18731';
export const vila = ms => new Promise(r => setTimeout(r, ms));

/* Kör `arbete(page)` mot appen och stäng ner efteråt, hur det än gick.
   Ett undantag skrivs ut och sätter process.exitCode — anroparen (och
   skalet som kör skriptet) ska kunna se att det gick fel. */
export async function iAppen(arbete, { viewport } = {}) {
  const browser = await chromium.launch({ channel: 'chrome' });
  try {
    const page = await browser.newPage({
      viewport: viewport || { width: 1600, height: 1200 },
      acceptDownloads: true,
    });
    page.on('pageerror', e => console.log('  [pageerror]', String(e).slice(0, 200)));
    await oppna(page);
    return await arbete(page);
  } catch (fel) {
    console.error('FEL:', (fel && fel.message) || fel);
    process.exitCode = 1;
    return null;
  } finally {
    await browser.close();
  }
}

/* Ladda appen och vänta tills den kan svara på frågor om lärarens papper.
   Kalendern är med i väntan: veckovyn och lektionskorten läser den, och ett
   klick i Planering innan den är hemma landar på en tom vecka. */
export async function oppna(page) {
  await page.goto(BAS + '/', { waitUntil: 'load' });
  await page.waitForFunction(() => window.Dokument && window.API && window.API.pa
    && window.Kalender && window.Kalender.franServern(),
    null, { timeout: 60000, polling: 500 });
  await page.evaluate(() => document.fonts.ready);
}

/* Dokumenthögen som servern har den, inte som sidan råkar minnas den:
   lösningsskrivningen PATCH:ar RADEN, och det är raden som avgör om ett
   papper är färdigt. */
export const hogen = page => page.evaluate(
  () => fetch('/api/dokument').then(r => r.json()));

/* Planeringsfliken, med pappret framme. #godkann och #fh-pdf bor båda där och
   är osynliga i en annan flik — Playwright väntar då ut sin timeout på ett
   element som finns. */
export async function tillPlaneringen(page) {
  await page.getByRole('tab', { name: 'Planering' }).click();
}

/* Hur många av bokens lösningsposter som är färdiga på ett papper. `null` när
   pappret inte har några — en tavla utan bokurval är inte ofärdig. */
export function losningslaget(v) {
  const p = ((v || {}).bokuppg || {}).losning;
  if (!p || !(p.poster || []).length) return null;
  const klara = p.poster.filter(x => x.text || x.olast || x.okand).length;
  return { klara, av: p.poster.length,
           skrivna: p.poster.filter(x => x.text).length };
}
