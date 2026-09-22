/* Plocka upp utkastet som ligger framme, vänta in bokens lösningsförslag och
   godkänn det — precis som läraren gör det i appen.

   Appen skriver bokens lösningsark själv när utkastet plockas upp
   (plan.js skrivBokLosningar → POST /api/bocker/{id}/losningar), och det tar
   minuter. Godkännandet måste vänta på det: en PATCH som kommer efter
   godkännandet skriver på en rad som inte längre är utkast, och arken hamnar
   ingenstans.

     cd e2e && node utkast-godkann.mjs [--utan-losningar] [--vanta 45] */
import { iAppen, vila, hogen, tillPlaneringen, losningslaget } from './appen.mjs';

const args = process.argv.slice(2);
const utanLos = args.includes('--utan-losningar');
const vantaMin = Number(args[args.indexOf('--vanta') + 1]) || 45;

await iAppen(async (page) => {
  /* Utkastet ur RADEN, inte ur sidan: skrivningen PATCH:ar raden. */
  const utkastet = async () => {
    const d = await hogen(page);
    const u = d && d.utkast;
    if (!u) return null;
    const v = (u.versioner || [])[u.markor] || (u.versioner || [])[0];
    if (!v) return null;
    return { id: u.id, typ: v.typ, moment: v.moment, klass: v.klass,
             datum: v.datum, wbId: v.wbId, los: losningslaget(v) };
  };

  let u = await utkastet();
  if (!u) throw new Error('inget utkast ligger framme');
  console.log(`== utkast ${u.id} · ${u.typ} · ${u.klass} · ${u.moment} · ${u.datum}`);
  if (u.los) console.log(`   lösningsposter: ${u.los.klara}/${u.los.av}`);

  if (!utanLos && u.los) {
    const slut = Date.now() + vantaMin * 60 * 1000;
    while (u.los.klara < u.los.av && Date.now() < slut) {
      await vila(15000);
      const f = await utkastet();
      if (!f || f.id !== u.id) throw new Error(
        'utkastet byttes ut under väntan — någon annan flik skrev ett nytt '
        + 'papper (ett utkast i taget), börja om');
      if (f.los.klara !== u.los.klara) {
        console.log(`   lösningsposter: ${f.los.klara}/${f.los.av}`);
      }
      u = f;
    }
    if (u.los.klara < u.los.av) throw new Error(
      `bara ${u.los.klara} av ${u.los.av} lösningsposter blev skrivna på `
      + `${vantaMin} min — godkänner inte, då hamnar resten utanför pappret`);
  }

  /* Knappen bor i planeringens steg 4. */
  await tillPlaneringen(page);
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

  /* Raden behåller sitt id genom godkännandet (PATCH på utkastraden, inte en
     ny post) — att leta upp pappret på MOMENTET i högen gav ett annat
     dokument med samma rubrik. */
  const klar = await page.waitForFunction(n => fetch('/api/dokument')
    .then(r => r.json())
    .then(d => ((d.sparade || []).some(x => x.id === n) ? n : null)),
    u.id, { timeout: 120000, polling: 2000 }).then(h => h.jsonValue());
  console.log(`   dokument ${klar}: godkänt`);
  return klar;
});
