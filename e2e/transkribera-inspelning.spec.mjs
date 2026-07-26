// Plan A4: e2e för INSPELNINGEN i transkriberingsguidens steg 1 i
// Svelte-frontenden (/next/), plus topbar-brickan. Kör mot den riktiga
// backenden med fejkad inferens (e2e/serve_test_app.py) — /api/recording/*,
// /api/recordings/incomplete och /api/recordings/{id}/markers är INTE stubbade
// och svarar på riktigt mot en isolerad base_dir.
//
// Mikrofonen är Chromiums fejkenhet. Flaggorna
// --use-fake-device-for-media-stream och --use-fake-ui-for-media-stream ligger
// i den GLOBALA use.launchOptions i playwright.config.ts och ärvs av det här
// projektet — specen sätter alltså inga egna launch-flaggor.
//
// TÄCKER:
//  1. viloläget erbjuder Starta inspelning, och timern passerar 00:01;
//  2. bitarna når VERKLIGEN servern — POST /api/recording/append ur
//     nätverksloggen, plus att .part-filen dyker upp på disk;
//  3. Markera räknar upp i knappens etikett OCH skriver till localStorage;
//  4. Stoppa och lägg till lägger filen i kön och tar guiden till steg 2;
//  5. topbar-brickan syns på steg 2 (där widgeten är avmonterad) och efter ett
//     flikbyte, och ett klick tar läraren tillbaka till steg 1 med kön intakt;
//  6. att den PÅGÅENDE inspelningens egen .part filtreras bort ur bannern —
//     annars hade Släng trunkerat lektionen tyst;
//  7. en .part på disk blir en banner, och Släng tar bort både raden och filen;
//  8. varje bit som faller räknas upp: 4 → 8 sekunder, alltså per-bit-bokföring
//     och inte en flagga;
//  9. ett nätverksfel ger ETT omförsök för SAMMA bit (identisk kroppsstorlek,
//     millisekunder isär) och inget felbesked;
// 10. serverns 507 görs INTE om, och serverns egen formulering når läraren;
// 11. hela markörkedjan: inspelning → Stoppa → transkribering klar → POST
//     /api/recordings/{id}/markers med rätt tidsstämplar, och att sessionens
//     localStorage-post är BORTA efteråt;
// 12. nekad mikrofon ger ett begripligt besked, ingen bricka och inget
//     halvstartat tillstånd;
// 13. att en körning inte går att STARTA mitt i en inspelning, och att brickan
//     inte kastar ut läraren ur en körning om den grinden ändå kringgås;
// 14. att nivåmätaren RÖR SIG — scaleX skilt från noll, läst ur computed style
//     (specens §6.1, som tidigare var otäckt);
// 15. att Avbryt SLÄPPER mikrofonen: varje spår getUserMedia delade ut har
//     readyState "ended" efteråt (specens §6.4);
// 16. att Återställ ger filändelsen ur den SPARADE sessionen, inte en
//     hårdkodad .webm — en session med mime audio/mp4 köas som .m4a (specens
//     §6.5, och hela skälet till att Task 5 finns);
// 17. att ett andra klick på samma plats som "Stoppa och lägg till" inte
//     startar en ny inspelning, och att spärren släpper när slutföringen är
//     klar.
//
// TÄCKER INTE — och det här är luckor, inte glömska:
//  · Tystnadsvarningen ("Ingen signal?"). Chromiums fejkenhet skickar en
//    kontinuerlig ton och blir aldrig tyst, så tröskeln i startaNivamatare kan
//    inte nås. Logiken är porterad oförändrad och är alltså OVERIFIERAD här.
//    Mätarens UTSLAG är däremot täckt, se punkt 14 — det är bara
//    tystnadsgrenen som inte går att nå.
//  · localStorage över en pywebview-omstart. Det som är bevisat (A4 Task 4) är
//    att posten överlever en OMLADDNING av dokumentet i Chromium. Om WebView2:s
//    användardatamapp bevarar den när appen dödas och startas om är okänt —
//    kraschnätet ska därför inte beskrivas som bevisat hela vägen.
//  · Riktig mikrofonhårdvara, och att enheten dras ur mitt i en inspelning
//    (spar.onended). Fejkenheten går inte att koppla ur.
//
// Nekad mikrofon är däremot INTE en lucka: fejk-UI-flaggan auto-godkänner bara
// den riktiga behörighetsdialogen och hindrar inte att getUserMedia skuggas —
// se det sista testet.
import { test, expect, failOnConsoleError } from "./helpers/app";
import * as fs from "node:fs";
import * as path from "node:path";

// inspelning.svelte.js:17 — MediaRecorder-timeslice. Hämtas hit som konstant
// för att uttrycka "inom samma bit" relativt koden i stället för att pinna en
// väggklockssiffra.
const CHUNK_MS = 4000;
// inspelningLagring.js:10.
const LAGRINGSPREFIX = "transkribera.inspelning.";

/** Fejkserverns downloads/ — samma isolerade base_dir som webServer startas med. */
function nedladdningar() {
  return path.join(process.env.E2E_TEST_DATA, "downloads");
}

/**
 * Raderar en artefakt ur downloads/.
 *
 * fs.rmSync används MEDVETET inte som förstahandsval: på Windows med Node 24
 * rapporterar den framgång men lämnar filer med icke-ASCII-namn kvar på disk.
 * Verifierat i det här repot — "återställd_rec_e2e_m4a.m4a" (namnet
 * aterstallOavslutad ger) överlevde både rmSync(force) och
 * rmSync(force+recursive) utan att kasta, medan unlinkSync tog den direkt.
 * Med den tysta miss blir filen kvar som senast ändrade mediefil i downloads/,
 * och /api/sample (server.py:1718-1734) serverar den till varje spec som kör
 * efter den här — transkribera-installningar och transkribera-korning faller
 * då på en fil de aldrig bett om.
 *
 * rmSync ligger kvar som andra försök för kataloger, som unlink inte tar.
 */
function taBort(p) {
  try {
    fs.unlinkSync(p);
    return;
  } catch { /* katalog, eller redan borta */ }
  try {
    fs.rmSync(p, { force: true, recursive: true });
  } catch { /* inget mer att göra här */ }
}

/**
 * Nollställer .part-filerna. Bannern testas både positivt och negativt, och
 * båda riktningarna kräver att vi vet exakt vilka .part-filer som finns.
 * serve_test_app.py rensar visserligen basmappen vid varje START, men testerna
 * i den här filen skapar egna .part-filer och delar server.
 */
function rensaPartFiler() {
  const d = nedladdningar();
  if (!fs.existsSync(d)) return;
  for (const f of fs.readdirSync(d)) {
    if (f.endsWith(".part")) taBort(path.join(d, f));
  }
}

function partFiler() {
  const d = nedladdningar();
  return fs.existsSync(d) ? fs.readdirSync(d).filter((f) => f.endsWith(".part")) : [];
}

/**
 * Chrome loggar varje anrop testet självt aborterat eller besvarat med 5xx som
 * ett konsolfel ("Failed to load resource: net::ERR_FAILED"). De felen är
 * testets egna injektioner, inte appens — allt annat räknas fortfarande.
 * Används BARA i de fyra testerna som injicerar nätverksfel.
 */
function appfel(errors) {
  return errors.filter((e) => !/Failed to load resource/.test(e));
}

/**
 * Noterar VARJE gång bannern för oavslutade inspelningar finns i DOM:en.
 * Ett stickprov efter att listan hämtats bevisar bara att den inte råkade
 * synas just då; filtret av den pågående sessionen ska hålla hela tiden.
 */
async function vaktaBannern(page) {
  await page.addInitScript(() => {
    window.__e2eBanner = [];
    const kolla = () => {
      const b = document.querySelector(".oavslutad");
      if (b) window.__e2eBanner.push((b.textContent || "").replace(/\s+/g, " ").trim());
    };
    const start = () =>
      new MutationObserver(kolla).observe(document.body, { subtree: true, childList: true });
    if (document.body) start();
    else document.addEventListener("DOMContentLoaded", start);
  });
}

/** Samma slags vakt för inspelningens felrad — se vaktaBannern. */
async function vaktaFelraden(page) {
  await page.addInitScript(() => {
    window.__e2eRecFel = [];
    const kolla = () => {
      const el = document.querySelector("p.rec-fel");
      const t = ((el && el.textContent) || "").trim();
      if (t) window.__e2eRecFel.push(t);
    };
    const start = () =>
      new MutationObserver(kolla).observe(document.body, {
        subtree: true,
        childList: true,
        characterData: true,
      });
    if (document.body) start();
    else document.addEventListener("DOMContentLoaded", start);
  });
}

/**
 * Skuggar getUserMedia och sparar VARJE utdelat spår, så att mikrofonens
 * verkliga tillstånd går att läsa av efteråt.
 *
 * Utan det här går "Avbryt släpper mikrofonen" (specens §6.4) inte att
 * assertera: DOM:en säger ingenting om huruvida strömmen stängdes, och en
 * kvarglömd ström lyser vidare i mikrofonlampan medan läraren tror att hon
 * avbrutit. Skuggan anropar originalet — inspelningen körs alltså på riktigt,
 * till skillnad från den avvisande skuggan i det nekade-mikrofonen-testet.
 */
async function vaktaStrommar(page) {
  await page.addInitScript(() => {
    window.__e2eSpar = [];
    // Räknas SYNKRONT vid anropet, inte när löftet löser ut. Det är skillnaden
    // mellan "startade ingen ny inspelning" och "hann inte starta en än":
    // startRecording anropar getUserMedia synkront i klick-hanteraren, så en
    // avläsning direkt efter klicket är sann. Väntar man i stället på ett
    // UTDELAT spår mäter man kapplöpningen mellan enhetsförvärvet och
    // assertionen, och en borttagen spärr kan passera obemärkt.
    window.__e2eAnrop = 0;
    const md = navigator.mediaDevices;
    if (!md || !md.getUserMedia) return;
    const original = md.getUserMedia.bind(md);
    Object.defineProperty(md, "getUserMedia", {
      configurable: true,
      value: (...args) => {
        window.__e2eAnrop += 1;
        return original(...args).then((s) => {
          window.__e2eSpar.push(...s.getTracks());
          return s;
        });
      },
    });
  });
}

/** Spårens readyState, i den ordning de delades ut. Kräver vaktaStrommar. */
function sparTillstand(page) {
  return page.evaluate(() => window.__e2eSpar.map((t) => t.readyState));
}

/** Flikknappen i topbaren (inte någon likanämnd knapp inne i en vy). */
function flik(page, namn) {
  return page.locator("nav.flikar").getByRole("button", { name: namn, exact: true });
}

// Den här specen är den enda som skapar RIKTIGA mediefiler i fejkserverns
// downloads/ (en avslutad inspelning blir lektion_<stämpel>.webm där). Det
// spiller över på andra specer: /api/sample (server.py:1718-1734) letar
// "Mamma waw isolerad.wav" direkt under base_dir — där ligger den inte, den
// kopieras till downloads/ — och faller därför tillbaka på den SENAST ändrade
// mediefilen i downloads/. En kvarlämnad inspelning gör alltså att "ett
// exempel" köar den i stället för demofilen i transkribera-installningar och
// transkribera-korning, som kör efter den här filen i bokstavsordning.
// Därför: allt den här filen lägger till i downloads/ tas bort igen.
let fanns = new Set();

/**
 * Filer som BARA den här specen skapar: avslutade inspelningar
 * (lektion_<stämpel>.<ext>, namnsatt av inspelning.svelte.js) och halvfärdiga
 * .part-filer.
 */
function egenArtefakt(namn) {
  // [.-] och inte bara \. — server.py:785 döper om till
  // lektion_<stämpel>-<uuid8>.webm när målnamnet redan finns. En sådan kvarleva
  // från en avbruten körning skulle annars hamna i ögonblicksbilden och förgifta
  // /api/sample bestående, vilket är precis det den här rensningen finns för.
  // "återställd_<session>." kommer ur aterstallOavslutad och är lika mycket en
  // mediefil i downloads/ som en avslutad inspelning — utan den grenen kunde en
  // avbruten körning lämna kvar en som /api/sample sedan serverar bestående.
  return (
    /^lektion_\d{4}-\d{2}-\d{2}_\d{4}[.-]/.test(namn) ||
    /^återställd_rec_e2e/.test(namn) ||
    namn.endsWith(".part")
  );
}

test.beforeAll(() => {
  const d = nedladdningar();
  if (!fs.existsSync(d)) {
    fanns = new Set();
    return;
  }
  // Städa FÖRE ögonblicksbilden, annars konserverar den skräp i stället för att
  // rensa det. playwright.config.ts har reuseExistingServer: true, och
  // serve_test_app.py torkar basmappen bara när servern FAKTISKT startar.
  // Avbryts en körning (Ctrl-C, kraschad worker) med en lektion_*.webm kvar i
  // downloads/, tar nästa körning mot samma levande server in filen i `fanns` —
  // och då rör afterEach den aldrig. Eftersom den fortfarande är senast ändrad
  // mediefil fortsätter /api/sample (server.py:1718-1734) att returnera den, och
  // transkribera-installningar + transkribera-korning faller på nytt — nu
  // BESTÅENDE i stället för övergående. Specens egna filer ska därför aldrig
  // kunna hamna under ögonblicksbildens skydd.
  for (const f of fs.readdirSync(d)) {
    if (egenArtefakt(f)) taBort(path.join(d, f));
  }
  fanns = new Set(fs.readdirSync(d));
});

test.afterEach(() => {
  const d = nedladdningar();
  if (!fs.existsSync(d)) return;
  for (const f of fs.readdirSync(d)) {
    if (!fanns.has(f)) taBort(path.join(d, f));
  }
});

test("Inspelning (/next/): start, bitar till servern, markörer, bricka och kö", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);
  rensaPartFiler();
  await vaktaBannern(page);

  await page.goto("/next/");

  // 1) Viloläget: raden erbjuder Starta inspelning och säger vad den gör.
  const starta = page.getByRole("button", { name: "Starta inspelning", exact: true });
  await expect(starta).toBeEnabled();
  await expect(page.getByText("Spela in lektionen direkt — ljudet sparas lokalt")).toBeVisible();
  await expect(page.locator("header.bar button.bricka")).toHaveCount(0);

  // Väntan på första biten registreras FÖRE klicket — annars kan den missas.
  // Egen timeout (kortare än testets) så utfallet blir en läsbar assertion i
  // stället för en naken testtimeout, se avläsningen längre ned.
  const forstaBiten = page
    .waitForRequest(
      (r) => r.url().includes("/api/recording/append") && r.method() === "POST",
      { timeout: 15_000 },
    )
    .catch(() => null);

  await starta.click();

  // 2) Inspelningsläget, och timern passerar 00:01. Ingen fast paus: vi väntar
  //    in klockans egen text, och ingen väggklockssiffra pinnas.
  const stoppa = page.getByRole("button", { name: "Stoppa och lägg till", exact: true });
  await expect(stoppa).toBeVisible();
  await expect(page.locator(".ruta .tid")).toHaveText(/^00:(0[1-9]|[1-5]\d)$/, { timeout: 15_000 });

  //    Och nivåmätaren RÖR SIG. Läst ur computed style, inte ur attributet:
  //    style:transform skrivs av Svelte oavsett vad tr.recLevel innehåller, så
  //    en avläsning av attributet hade gått igenom även med en död mätare.
  //    scaleX(0.42) beräknas till matrix(0.42, 0, 0, 1, 0, 0); ett stillastående
  //    utslag ger matrix(0, …). Fejkenheten skickar en kontinuerlig ton, så
  //    utslaget SKA vara skilt från noll — faller den här assertionen är det
  //    AnalyserNode-kedjan i startaNivamatare som brustit, inte tonen.
  await expect
    .poll(
      () =>
        page.locator(".ruta .fyllnad").evaluate((el) => {
          const m = /matrix\(\s*([-\d.]+)/.exec(getComputedStyle(el).transform);
          return m ? parseFloat(m[1]) : 0;
        }),
      { timeout: 15_000 },
    )
    .toBeGreaterThan(0);

  // 3) Markera räknar upp i knappens egen etikett …
  const markera = page.getByRole("button", { name: /^Markera/ });
  await markera.click();
  await expect(markera).toHaveText(/Markera \(1\)/);
  await markera.click();
  await expect(markera).toHaveText(/Markera \(2\)/);

  //    … och skriver till localStorage. Det är kraschnätet: gamla appen håller
  //    markörerna bara i JS-minne (app.js:231) och tappar dem permanent vid en
  //    krasch mitt i lektionen.
  const poster = await page.evaluate(
    (prefix) =>
      Object.keys(localStorage)
        .filter((k) => k.startsWith(prefix))
        .map((k) => JSON.parse(localStorage.getItem(k))),
    LAGRINGSPREFIX,
  );
  expect(poster).toHaveLength(1);
  expect(poster[0].markers).toHaveLength(2);
  expect(poster[0].markers.every((m) => typeof m.t === "number")).toBe(true);
  expect(poster[0].mime, "mime måste sparas — annars får en återställd fil .webm på måfå").toBeTruthy();

  // 4) Bitarna når VERKLIGEN servern. Läst ur nätverksloggen, inte härlett ur
  //    koden — och bekräftat på disk: .part-filen är hela poängen med
  //    den inkrementella flushen (server.py:748-769).
  const bit = await forstaBiten;
  expect(
    bit,
    "Ingen POST till /api/recording/append kom fram. Utan timeslice — " +
      "recorder.start(CHUNK_MS), inspelning.svelte.js:158 — emitterar MediaRecorder " +
      "ingen bit alls förrän vid stopp, och då ligger hela lektionen kvar i minnet: " +
      "en krasch mitt i passet tar med sig allt.",
  ).not.toBeNull();
  expect(bit.url()).toContain("session=rec_");
  await expect
    .poll(() => partFiler().length, { timeout: 15_000 })
    .toBe(1);

  // 5) En fil i kön tar guiden till steg 2 — och där är <Inspelning /> AVMONTERAD
  //    (TranskriberaView.svelte), medan mikrofonen fortfarande är på. Brickan är
  //    då den enda indikatorn som finns.
  await page.getByRole("button", { name: "ett exempel", exact: true }).click();
  const laggTillFler = page.getByRole("button", { name: "Lägg till fler", exact: true });
  await expect(laggTillFler).toBeVisible();
  await expect(stoppa).toHaveCount(0);
  const bricka = page.locator("header.bar button.bricka");
  await expect(bricka).toBeVisible();
  await expect(bricka).toContainText("Spelar in");
  await expect(bricka.locator(".tid")).toHaveText(/^\d\d:\d\d$/);
  // Brickan är en riktig knapp med ett läsbart namn, inte en dekoration.
  await expect(page.getByRole("button", { name: /Spelar in/ })).toBeVisible();

  // 6) Tillbaka till steg 1 — vägen som monterar om widgeten mitt i en
  //    inspelning. Effekten i Inspelning.svelte hämtar då listan på nytt, och
  //    den PÅGÅENDE inspelningens .part får inte erbjudas: Släng hade unlink:at
  //    filen medan recordern rullar, och nästa append hade öppnat den igen med
  //    "ab" — lektionen trunkerad tyst till det som spelades in efter klicket.
  const listning = page.waitForResponse((r) => r.url().includes("/api/recordings/incomplete"));
  await laggTillFler.click();
  await expect(page.getByRole("heading", { name: /Vad vill du transkribera/ })).toBeVisible();

  const lista = await (await listning).json();
  expect(
    lista.length,
    "Servern listade ingen .part alls — då bevisar filterassertionen nedan ingenting.",
  ).toBeGreaterThan(0);
  await expect(page.getByText("Oavslutad inspelning hittad")).toHaveCount(0);

  // 7) Brickan överlever ett flikbyte — det är hela defekten den lagar
  //    (setTab, app.js:602, byter flik utan spärr och utan indikator).
  await flik(page, "Planering").click();
  await expect(flik(page, "Planering")).toHaveAttribute("aria-pressed", "true");
  await expect(bricka).toBeVisible();

  // 8) Ett klick tar läraren tillbaka till inspelningen — rätt flik, steg 1,
  //    och kön ORÖRD (goSource, inte nyTranskribering).
  await bricka.click();
  await expect(flik(page, "Transkribera")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: /Vad vill du transkribera/ })).toBeVisible();
  await expect(stoppa).toBeVisible();
  await expect(page.locator("ul.ko li")).toHaveCount(1);

  // 9) Stoppa och lägg till: inspelningen blir en fil i kön, guiden går till
  //    steg 2 och brickan slocknar.
  await stoppa.click();
  await expect(laggTillFler).toBeVisible();
  const ko = page.locator("ul.ko li");
  await expect(ko).toHaveCount(2);
  await expect(ko.filter({ hasText: /lektion_\d{4}-\d{2}-\d{2}_\d{4}\.\w+/ })).toHaveCount(1);
  await expect(bricka).toHaveCount(0);

  // 10) Bannern fick aldrig, i någon enda ruta, visa den pågående inspelningen.
  const sedd = await page.evaluate(() => window.__e2eBanner);
  expect(
    sedd,
    "Bannern erbjöd den PÅGÅENDE inspelningen: " + sedd.join(" | "),
  ).toEqual([]);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Inspelning (/next/): Avbryt släpper mikrofonen — inga levande spår kvar", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);
  rensaPartFiler();
  await vaktaStrommar(page);

  await page.goto("/next/");
  await page.getByRole("button", { name: "Starta inspelning", exact: true }).click();

  const stoppa = page.getByRole("button", { name: "Stoppa och lägg till", exact: true });
  await expect(stoppa).toBeVisible();
  // Referensläget: spåret är LEVANDE medan inspelningen pågår. Utan det steget
  // kunde "ended" nedan lika gärna betyda att getUserMedia aldrig lyckades, och
  // testet hade bevisat fel sak.
  expect(await sparTillstand(page)).toEqual(["live"]);

  // Avbryt ska också städa på servern — annars ligger .part-filen kvar och
  // erbjuds tillbaka i bannern efter att läraren uttryckligen slängt den.
  const kast = page.waitForRequest(
    (r) => r.url().includes("/api/recording/discard") && r.method() === "POST",
  );
  await page.getByRole("button", { name: "Avbryt", exact: true }).click();
  await kast;

  // Mikrofonen är SLÄPPT. Det syns inte i DOM:en: släpps inte spåret lyser
  // mikrofonlampan vidare i operativsystemet medan appen visar viloläget, och
  // nästa startRecording begär en andra ström ovanpå den första.
  await expect.poll(() => sparTillstand(page), { timeout: 10_000 }).toEqual(["ended"]);

  // Och raden är tillbaka i viloläget, utan bricka i topbaren.
  await expect(page.getByRole("button", { name: "Starta inspelning", exact: true })).toBeVisible();
  await expect(page.locator("header.bar button.bricka")).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Inspelning (/next/): en oavslutad .part blir en banner, och Släng tar bort den", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);
  rensaPartFiler();

  // Sessions-id:t måste matcha serverns regex ^[A-Za-z0-9_-]{1,64}$
  // (server.py:741), annars svarar discard 400. Filen skrivs EFTER att
  // fejkservern startat — serve_test_app.py rensar basmappen vid varje start,
  // så en fixtur som lagts dit i förväg hade varit borta.
  const session = "rec_e2e_oavslutad";
  const part = path.join(nedladdningar(), session + ".part");
  fs.mkdirSync(nedladdningar(), { recursive: true });
  fs.writeFileSync(part, Buffer.alloc(2048, 7));

  await page.goto("/next/");

  // Raden bär serverns storlek och datum, inte sessions-id:t — "rec_1738…"
  // säger läraren ingenting om vilket pass hon tappade.
  await expect(page.getByText("Oavslutad inspelning hittad")).toBeVisible();
  await expect(page.locator(".oav-rad")).toHaveCount(1);
  await expect(page.locator(".oav-namn")).toHaveText(/^2 KB · Idag/);
  await expect(page.getByText(session)).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Återställ inspelning / })).toBeVisible();

  const slang = page.getByRole("button", { name: /^Släng inspelning / });
  const kastPost = page.waitForRequest(
    (r) => r.url().includes("/api/recording/discard") && r.method() === "POST",
  );
  await slang.click();
  await kastPost;

  // Raden försvinner OCH filen är borta från disk — bannern får inte tömmas
  // optimistiskt medan ljudet ligger kvar.
  await expect(page.getByText("Oavslutad inspelning hittad")).toHaveCount(0);
  await expect.poll(() => fs.existsSync(part), { timeout: 10_000 }).toBe(false);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Inspelning (/next/): Återställ ger ändelsen ur sessionen, inte hårdkodad .webm", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);
  rensaPartFiler();

  // Det HÄR är defekten Task 5 finns för: gamla appens recoverIncomplete
  // hårdkodar .webm (app.js:1496), så en session som spelades in med audio/mp4
  // — Safari, och Chromium när opus-grenarna faller bort — kom tillbaka med fel
  // filändelse. Utan det här testet har fixen ingen spärr alls: både .webm och
  // .m4a passerar isMedia, så köraden ser lika riktig ut i båda fallen.
  const session = "rec_e2e_m4a";
  const part = path.join(nedladdningar(), session + ".part");
  fs.mkdirSync(nedladdningar(), { recursive: true });
  fs.writeFileSync(part, Buffer.alloc(2048, 7));

  await page.goto("/next/");
  await expect(page.getByText("Oavslutad inspelning hittad")).toBeVisible();

  // Posten seedas EFTER första laddningen och läses vid omladdningen: en
  // addInitScript hade kört redan på about:blank, där localStorage tillhör fel
  // origin. stadaSessioner rör den inte — sessionen ligger i incompleteRecs.
  await page.evaluate(
    ([prefix, s]) =>
      localStorage.setItem(prefix + s, JSON.stringify({ mime: "audio/mp4", markers: [] })),
    [LAGRINGSPREFIX, session],
  );
  await page.reload();
  await expect(page.getByText("Oavslutad inspelning hittad")).toBeVisible();

  await page.getByRole("button", { name: /^Återställ inspelning / }).click();

  // Filen ligger i kön under sitt riktiga format …
  const ko = page.locator("ul.ko li");
  await expect(ko).toHaveCount(1);
  await expect(ko.locator(".namn")).toHaveText("återställd_" + session + ".m4a");
  await expect(ko.locator(".ext")).toHaveText("m4a");
  // … och på disk, med samma namn: servern döper om .part-filen till det namn
  // klienten skickade, så en fel ändelse här hade blivit bestående.
  await expect
    .poll(() => fs.existsSync(path.join(nedladdningar(), "återställd_" + session + ".m4a")), {
      timeout: 10_000,
    })
    .toBe(true);
  // Bannern är tom igen — .part-filen är förbrukad.
  expect(partFiler()).toEqual([]);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Inspelning (/next/): varje förlorad bit räknas upp och läraren får veta", async ({ page }) => {
  test.setTimeout(60_000);
  const errors = [];
  failOnConsoleError(page, errors);
  rensaPartFiler();

  // Gamla appen sväljer det här felet helt (app.js:1420) — ljud försvinner utan
  // att någon märker det. En räknare som VÄXER är det enda som skiljer
  // per-bit-bokföring från en enda flagga.
  await page.route("**/api/recording/append*", (route) => route.abort("failed"));

  await page.goto("/next/");
  await page.getByRole("button", { name: "Starta inspelning", exact: true }).click();

  const fel = page.locator("p.rec-fel");
  const region = page.locator(".pane:not([hidden]) section.view p.fel-sr");
  const fyra =
    "Nätverket svarade inte. 4 sekunder av inspelningen gick förlorade. Inspelningen fortsätter.";
  const atta =
    "Nätverket svarade inte. 8 sekunder av inspelningen gick förlorade. Inspelningen fortsätter.";

  await expect(fel).toHaveText(fyra, { timeout: 30_000 });
  await expect(fel).toBeVisible();
  // Skärmläsaren hör samma sak, ur den enda hoistade live-regionen — brickan
  // och widgeten har medvetet ingen egen.
  await expect(region).toHaveText(fyra);

  await expect(fel).toHaveText(atta, { timeout: 30_000 });
  await expect(region).toHaveText(atta);

  // Städa: Avbryt släpper mikrofonen och skickar discard.
  await page.getByRole("button", { name: "Avbryt", exact: true }).click();

  expect(appfel(errors), appfel(errors).join("\n")).toEqual([]);
});

test("Inspelning (/next/): ett nätverksfel ger ETT omförsök för samma bit, utan besked", async ({ page }) => {
  test.setTimeout(60_000);
  const errors = [];
  failOnConsoleError(page, errors);
  rensaPartFiler();
  await vaktaFelraden(page);

  // Rutthanteraren kan INTE skilja original från omförsök: samma URL, samma
  // metod, samma kropp. Därför räknas anropen — nummer ett aborteras, resten
  // släpps igenom — och beviset läses ur nätverksloggen, inte ur hanteraren.
  let n = 0;
  await page.route("**/api/recording/append*", (route) => {
    n += 1;
    return n === 1 ? route.abort("failed") : route.continue();
  });

  const bitar = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/recording/append") && r.method() === "POST") {
      const kropp = r.postDataBuffer();
      bitar.push({ ms: Date.now(), bytes: kropp ? kropp.length : 0 });
    }
  });
  const lyckat = page.waitForResponse(
    (r) => r.url().includes("/api/recording/append") && r.status() === 200,
  );

  await page.goto("/next/");
  await page.getByRole("button", { name: "Starta inspelning", exact: true }).click();

  // Omförsöket måste ha KOMMIT FRAM innan felraden läses av, annars vore
  // "ingen feltext" bara ett för tidigt stickprov.
  await lyckat;
  await expect.poll(() => bitar.length, { timeout: 30_000 }).toBeGreaterThanOrEqual(2);

  // Samma bit två gånger: identisk kroppsstorlek …
  //
  // LÄS INTE storleksjämförelsen som beviset. Fejkenheten skickar en
  // KONTINUERLIG ton, så två på varandra följande Opus-bitar har med stor
  // sannolikhet identisk storlek ändå — likhet skiljer alltså inte ett
  // omförsök från nästa bit. Den fäller bara det grövsta utfallet (en kropp
  // som uppenbart hör till något annat) och är därför ett komplement.
  // Beviset bärs av AVSTÅNDET nedan plus "ingen feltext" längre ned.
  expect(bitar[0].bytes, "tom kropp — då säger storleksjämförelsen ingenting").toBeGreaterThan(0);
  expect(
    bitar[1].bytes,
    "Andra anropet bar en ANNAN kropp (" + bitar[0].bytes + " → " + bitar[1].bytes +
      " byte) — det är nästa bit, inte ett omförsök av den första.",
  ).toBe(bitar[0].bytes);
  // … och det kom OMEDELBART efter, inte som nästa bit.
  //
  // Gränsen är CHUNK_MS/4, inte CHUNK_MS. Nästa bit POSTas en hel timeslice
  // efter den förra, så < CHUNK_MS utesluter exakt ingenting: en nästa-bit-POST
  // 3 990 ms senare hade passerat som "omförsök". Omförsöket har ingen backoff
  // — laddaUppChunk (inspelning.svelte.js:293) går direkt in i varv två när
  // fetch:en avvisas — så en fjärdedels timeslice är rundlig marginal för den
  // riktiga händelsen och långt under nästa bit.
  expect(
    bitar[1].ms - bitar[0].ms,
    "De två anropen låg " + (bitar[1].ms - bitar[0].ms) + " ms isär, alltså långt mer än " +
      "ett omedelbart omförsök — det är nästa bit, inte ett omförsök.",
  ).toBeLessThan(CHUNK_MS / 4);

  // Ingen feltext — omförsöket räddade biten. Vakten läser varje DOM-mutation,
  // så inte ens en blinkande text går förbi.
  await expect(page.locator("p.rec-fel")).toHaveText("");
  await expect(page.locator(".pane:not([hidden]) section.view p.fel-sr")).toHaveText("");
  const blinkat = await page.evaluate(() => window.__e2eRecFel);
  expect(blinkat, "Felraden visade text trots att omförsöket lyckades: " + blinkat.join(" | "))
    .toEqual([]);

  await page.getByRole("button", { name: "Avbryt", exact: true }).click();

  expect(appfel(errors), appfel(errors).join("\n")).toEqual([]);
});

test("Inspelning (/next/): serverns 507 görs inte om, och dess egen text når läraren", async ({ page }) => {
  test.setTimeout(60_000);
  const errors = [];
  failOnConsoleError(page, errors);
  rensaPartFiler();

  // 507 (full disk, server.py:765-768) är det enda serverfel som realistiskt
  // inträffar — 413 kräver 2 GiB (MAX_UPLOAD_BYTES, server.py:40). Det är
  // dessutom BESTÄNDIGT: ett omförsök av ett svar servern redan gett hade bara
  // försenat nästa bit.
  await page.route("**/api/recording/append*", (route) =>
    route.fulfill({
      status: 507,
      contentType: "application/json",
      body: JSON.stringify({ error: "Kunde inte skriva till disk — kontrollera ledigt utrymme." }),
    }),
  );

  const anrop = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/recording/append") && r.method() === "POST") anrop.push(r.url());
  });

  await page.goto("/next/");
  await page.getByRole("button", { name: "Starta inspelning", exact: true }).click();

  const fel = page.locator("p.rec-fel");
  await expect(fel).toHaveText(
    "Kunde inte skriva till disk — kontrollera ledigt utrymme. 4 sekunder av inspelningen " +
      "gick förlorade. Inspelningen fortsätter.",
    { timeout: 30_000 },
  );
  await expect(fel).toBeVisible();

  // Avbryt först: det nollar ondataavailable, så inga fler bitar kan tillkomma
  // mellan avläsningen och assertionen nedan.
  await page.getByRole("button", { name: "Avbryt", exact: true }).click();
  expect(
    anrop.length,
    "Biten POSTades " + anrop.length + " gånger — ett svar från servern ska INTE göras om.",
  ).toBe(1);

  expect(appfel(errors), appfel(errors).join("\n")).toEqual([]);
});

test("Inspelning (/next/): markörerna följer med hela vägen till den sparade lektionen", async ({ page }) => {
  test.setTimeout(120_000);
  const errors = [];
  failOnConsoleError(page, errors);
  rensaPartFiler();

  await page.goto("/next/");
  await page.getByRole("button", { name: "Starta inspelning", exact: true }).click();

  // Markörerna sätts ur WIDGETENS egen klocka, inte efter väggklockan:
  // addRecMarker skriver tr.recElapsed, och det är samma värde som visas. Att
  // vänta in "00:01" respektive "00:02" ger därför deterministiskt t=1 och t=2
  // utan att någon paus pinnas.
  const tid = page.locator(".ruta .tid");
  const markera = page.getByRole("button", { name: /^Markera/ });
  await expect(tid).toHaveText("00:01", { timeout: 15_000 });
  await markera.click();
  await expect(tid).toHaveText("00:02", { timeout: 15_000 });
  await markera.click();
  await expect(markera).toHaveText(/Markera \(2\)/);

  // Kedjan spänner över TRE filer — inspelning.svelte.js skriver, stores.svelte.js
  // bär (tr.recMarkersByPath), actions.js postar när transkriberingen är klar.
  // POSTen registreras före körningen så den inte kan missas.
  const markorPost = page.waitForRequest(
    (r) => /\/api\/recordings\/[^/]+\/markers$/.test(r.url()) && r.method() === "POST",
  );

  await page.getByRole("button", { name: "Stoppa och lägg till", exact: true }).click();
  await expect(page.locator("ul.ko li")).toHaveCount(1);

  // Posten ligger kvar medan markörerna väntar — det ÄR kraschnätet.
  expect(
    await page.evaluate(
      (p) => Object.keys(localStorage).filter((k) => k.startsWith(p)).length,
      LAGRINGSPREFIX,
    ),
    "Sessionens post glömdes redan vid Stoppa — då finns inget kraschnät mellan " +
      "inspelningens slut och transkriberingens.",
  ).toBe(1);

  const start = page.getByRole("button", { name: "Starta transkribering", exact: true });
  await expect(start).toBeEnabled({ timeout: 30_000 });
  await start.click();
  await expect(page.locator(".kort .status")).toHaveText("Klar", { timeout: 60_000 });

  // POSTen bär exakt de tidsstämplar läraren satte.
  const post = await markorPost;
  expect(JSON.parse(post.postData())).toEqual({ markers: [{ t: 1 }, { t: 2 }] });

  // Och sessionens post är BORTA — glomSession körs först när servern kvitterat.
  await expect
    .poll(
      () =>
        page.evaluate(
          (p) => Object.keys(localStorage).filter((k) => k.startsWith(p)).length,
          LAGRINGSPREFIX,
        ),
      { timeout: 20_000 },
    )
    .toBe(0);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Inspelning (/next/): ett andra klick på samma plats startar ingen ny inspelning", async ({ page }) => {
  test.setTimeout(60_000);
  const errors = [];
  failOnConsoleError(page, errors);
  rensaPartFiler();
  await vaktaStrommar(page);

  // Båda grenarna av .ruta slutar med samma högerställda .primar-knapp, och
  // "Starta inspelning" ligger helt innanför fotavtrycket för "Stoppa och lägg
  // till". tr.recording slår om till false SYNKRONT i stopRecording, så raden
  // hinner ritas om mellan två snabba klick och det andra landar på Starta.
  //
  // /api/recording/finish HÅLLS här, så fönstret blir deterministiskt i stället
  // för en kapplöpning: slutföringen är i flykt hela tiden mellan klicken,
  // precis som vid ett riktigt dubbelklick på en långsammare dator.
  /** @type {import("@playwright/test").Route | null} */
  let hallen = null;
  await page.route(
    (url) => url.pathname === "/api/recording/finish",
    (route) => { hallen = route; },
  );

  await page.goto("/next/");
  const starta = page.getByRole("button", { name: "Starta inspelning", exact: true });
  const stoppa = page.getByRole("button", { name: "Stoppa och lägg till", exact: true });

  await starta.click();
  await expect(stoppa).toBeVisible();
  // Vänta in att det finns ljud att slutföra, annars svarar finish 404 och
  // fönstret som testas uppstår aldrig.
  await expect(page.locator(".ruta .tid")).toHaveText(/^00:(0[1-9]|[1-5]\d)$/, { timeout: 15_000 });

  await stoppa.click();
  // Raden är redan omritad — det är hela problemet.
  await expect(starta).toBeVisible();

  await starta.click();
  // Ingen ny inspelning. Beviset är ANROPSRÄKNAREN, inte DOM:en: startRecording
  // anropar getUserMedia synkront i klick-hanteraren, medan raden och brickan
  // ritas om först när löftet löst ut — en assertion på dem hade varit sann i
  // några millisekunder även med spärren borttagen. Utan spärren hade det andra
  // klicket gett läraren en inspelning hon aldrig bad om, och hade dess
  // getUserMedia hunnit lösa ut före den gamla recorderns onstop hade
  // slutforInspelning nollställt den NYA sessionen — varpå bitarna POSTat mot
  // ?session=null och Stoppa kastat hela lektionen utan ett ord.
  expect(
    await page.evaluate(() => window.__e2eAnrop),
    "getUserMedia anropades en andra gång — det andra klicket startade en ny inspelning.",
  ).toBe(1);
  await expect(stoppa).toHaveCount(0);
  await expect(page.locator("header.bar button.bricka")).toHaveCount(0);

  // Spärren är en spärr, inte ett lås: så fort slutföringen är klar går det att
  // spela in igen.
  await expect.poll(() => (hallen ? 1 : 0), { timeout: 15_000 }).toBe(1);
  await hallen.continue();
  await expect(page.locator("ul.ko li")).toHaveCount(1);
  await page.getByRole("button", { name: "Lägg till fler", exact: true }).click();
  await starta.click();
  await expect(stoppa).toBeVisible();
  expect(await page.evaluate(() => window.__e2eAnrop)).toBe(2);

  await page.getByRole("button", { name: "Avbryt", exact: true }).click();

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Inspelning (/next/): nekad mikrofon ger ett begripligt besked och ingen bricka", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);
  rensaPartFiler();

  // Fejk-UI-flaggan (--use-fake-ui-for-media-stream) auto-godkänner bara den
  // riktiga behörighetsdialogen — den hindrar inte att getUserMedia skuggas här.
  // Nekad mikrofon är alltså fullt testbar, och värd att testa: gamla appen ger
  // SAMMA intetsägande text för alla orsaker (app.js:1445), så en lärare med
  // blockerad mikrofon fick samma besked som en utan mikrofon.
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      configurable: true,
      value: () =>
        Promise.reject(Object.assign(new Error("nekad"), { name: "NotAllowedError" })),
    });
  });

  await page.goto("/next/");
  const starta = page.getByRole("button", { name: "Starta inspelning", exact: true });
  await starta.click();

  const besked = "Mikrofonen blockerades. Tillåt mikrofon för appen och försök igen.";
  const fel = page.locator("p.rec-fel");
  await expect(fel).toHaveText(besked);
  await expect(fel).toBeVisible();
  await expect(page.locator(".pane:not([hidden]) section.view p.fel-sr")).toHaveText(besked);

  // Inget halvstartat tillstånd: ingen bricka, ingen timer, och knappen går att
  // trycka igen så fort läraren släppt fram mikrofonen.
  await expect(page.locator("header.bar button.bricka")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Stoppa och lägg till", exact: true })).toHaveCount(0);
  await expect(starta).toBeEnabled();

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Inspelning (/next/): brickan kastar inte ut läraren ur en pågående körning", async ({ page }) => {
  test.setTimeout(60_000);
  const errors = [];
  failOnConsoleError(page, errors);
  rensaPartFiler();

  // /api/transcribe besvaras ALDRIG: körningen blir kvar i 'running' hela
  // testet igenom. Fejkserverns transkribering är i praktiken omedelbar
  // (serve_test_app.py: fake_transcribe), så utan det här tävlar "done" med
  // assertionerna nedan och testet mäter en annan gren än den det påstår.
  // Ruttet släpps med abort() längre ned — då, och först då, blir run 'error'.
  /** @type {import("@playwright/test").Route | null} */
  let hallen = null;
  await page.route(
    (url) => url.pathname === "/api/transcribe",
    (route) => { hallen = route; },
  );

  await page.goto("/next/");

  // Referensläget FÖRST, utan inspelning: knappen är klickbar med precis den
  // här kön och den här modellkatalogen. Utan det steget kunde "avstängd" nedan
  // lika gärna betyda att katalogen inte hunnit landa (startEtikett har flera
  // grindvillkor), och testet hade bevisat fel sak.
  const exempel = page.getByRole("button", { name: "ett exempel", exact: true });
  await exempel.click();
  const start = page.locator(".start button.primar");
  await expect(start).toBeEnabled({ timeout: 30_000 });
  await expect(start).toHaveText("Starta transkribering");

  await page.getByRole("button", { name: "Lägg till fler", exact: true }).click();
  await page.getByRole("button", { name: "Starta inspelning", exact: true }).click();
  const stoppa = page.getByRole("button", { name: "Stoppa och lägg till", exact: true });
  await expect(stoppa).toBeVisible();

  // Vägen in i defekten: addFiles sätter tr.step = 'config' OVILLKORLIGT
  // (actions.js) — även för en dubblett — så steg 2 nås mitt i en inspelning
  // utan att passera "Nästa: inställningar" och dess tr.recording-grind.
  await exempel.click();
  // Den synliga kopian, inte live-regionen — samma data-testid som övriga specer.
  await expect(page.getByTestId("statusrad")).toHaveText("1 fil låg redan i kön.");

  // LÅS 1 — samma knapp, samma kö, samma katalog, men nu avstängd, och den
  // säger varför.
  await expect(start).toBeDisabled();
  await expect(start).toHaveText("Stoppa inspelningen först");

  // LÅS 2 kan bara nås genom att kringgå lås 1; det är hela innebörden av ett
  // andra lås. disabled tas bort och knappen klickas i SAMMA tick, så ingen
  // Svelte-uppdatering hinner sätta tillbaka attributet emellan.
  await start.evaluate((el) => {
    el.removeAttribute("disabled");
    /** @type {HTMLButtonElement} */ (el).click();
  });
  const status = page.locator(".kort .status");
  await expect(status).toHaveText("Kör", { timeout: 15_000 });

  // Före fixen tog det här klicket läraren till steg 1: <Korning /> avmonterades,
  // stegindikatorn är inte klickbar och startRun returnerar tyst medan run ===
  // 'running'. Körningen blev alltså osynlig och oåterkallelig — inget
  // klarbesked, inga resultatfiler, och ett nytt tryck på Starta hade kört om
  // samma tr.activeId till en andra lessons-rad för samma lektion.
  const bricka = page.locator("header.bar button.bricka");
  await expect(bricka).toBeVisible();
  await bricka.click();
  await expect(status).toHaveText("Kör");
  await expect(flik(page, "Transkribera")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: /Vad vill du transkribera/ })).toHaveCount(0);

  // Men brickan är ingen död knapp: så fort körsteget inte längre bär något
  // oåterkalleligt — här ett fel, där kortet ändå erbjuder "Byt fil" — tar
  // samma klick läraren till steg 1 och widgetens egna knappar.
  await hallen.abort("failed");
  await expect(page.getByRole("button", { name: "Byt fil", exact: true })).toBeVisible({
    timeout: 15_000,
  });
  await bricka.click();
  await expect(page.getByRole("heading", { name: /Vad vill du transkribera/ })).toBeVisible();
  await expect(stoppa).toBeVisible();

  // Och grinden släpper igen så fort lektionen är stoppad och köad — det är en
  // spärr, inte ett förbud. Det här är också det som pinnar fast att det VAR
  // tr.recording som stängde knappen ovan.
  await stoppa.click();
  await expect(page.locator("ul.ko li")).toHaveCount(2);
  await expect(start).toBeEnabled();
  await expect(start).toHaveText("Starta · 2 filer");
  await expect(bricka).toHaveCount(0);

  expect(appfel(errors), appfel(errors).join("\n")).toEqual([]);
});
