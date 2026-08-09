/* LÄRARDAGARNA — det gemensamma underlaget (Etapp 4.1)
 *
 * Sviten har hittills prövat en skiva i taget: tavlan i tavla.spec, provet i
 * prov.spec, rättningen i rattning.spec. Var och en fejkar hela backenden runt
 * sin egen skiva. Det duger för att pinna ett kontrakt, men det liknar inte en
 * arbetsdag — och de fel som kostar en lektion uppstår mellan skivorna: pappret
 * som inte hänger med till veckan, kön som tappar klassen, godkännandet som
 * lämnar halva dokumentet.
 *
 * Lärardagarna kör därför mot den RIKTIGA servern (e2e/testserver.py, tom bas
 * under temp) och fejkar bara MOLNET:
 *
 *   · OpenAI  — /api/transcribe route:as här. Servern kan inte transkribera på
 *     riktigt i e2e (ingen nyckel, inget ljud, ingen GPU), och ska inte.
 *   · Claude  — fejkas i CLI:t i stället (FEJK_CLAUDE=auto, e2e/testserver.py).
 *     Kassetten väljs ur prompten, så /api/planning/generate,
 *     /api/exams/generate och /api/lessons/{id}/extract kör appens riktiga
 *     kedja: prompt → ström → JSON → schema → balans → reparationsrundor.
 *
 * Allt annat — schemat, dokumenten, versionerna, godkännandet, rättningen,
 * tryckpaketet, säkerhetskopian — går till servern och skrivs på riktigt.
 *
 * Dagarna delar bas: servern startas EN gång för hela sviten. Ett papper som
 * en dag skriver ligger alltså kvar när nästa dag börjar — precis som på
 * lärarens dator. Därför mäter dagarna alltid FÖRE och EFTER, aldrig absoluta
 * antal.
 */
import { expect } from "@playwright/test";

/* Tisdag i vecka 37, 2026 — mitt i terminen, fyra lektioner i exempelschemat.
   Klockan fryses alltid: «veckan appen öppnar» räknas ur dagens datum, och en
   dag som antar «det finns lektioner den här veckan» går sönder på lovet. */
export const SKOLDAG = "2026-09-08T07:30:00";
/* Tisdag i höstlovet (2026-10-26–30 enligt app/data/lasar) — ingen lektion. */
export const LOVDAG = "2026-10-27T07:30:00";

const strom = handelser =>
  handelser.map(h => `data: ${JSON.stringify(h)}\n\n`).join("");

/* En körning som servern skulle ha strömmat: faserna i ordning, kostnaden ur
   usage.seconds (aldrig ur filens längd) och ett transkript i done. */
/* lektionId: servern skriver lektionsraden när den transkriberar, och det är
   den granskningen frågar om insikter (app.js hamtaInsikter). Molnet är fejkat
   här, så raden finns inte i basen — därför fejkas extract-rutten med.
   Utan id:t står regexgissningen kvar och dagen prövar prototypen. */
export function korning({ text = "Vi tittar på derivatans definition. Ändringskvoten när h går mot noll.",
                          usd = 0.07, minuter = 15.1, lektionId = 1 } = {}) {
  return strom([
    { type: "log", msg: "Delar upp ljudet vid naturliga pauser ..." },
    { type: "progress", pct: 8 },
    { type: "log", msg: "Skickar 3 delar till gpt-transcribe ..." },
    { type: "delta", text },
    { type: "progress", pct: 45 },
    { type: "kostnad", usd, minuter },
    { type: "log", msg: "Sätter tidsstämplar lokalt (cuda) ..." },
    { type: "progress", pct: 60 },
    { type: "progress", pct: 98 },
    { type: "done", result: {
        id: "h1", lesson_id: lektionId, files: [], folder: "C:/Transkriberingar/x",
        media: "C:/x/lektion.wav",
        transcript: [{ start: 0.4, end: 6.2, text }] } },
  ]);
}

/** Insikterna som /api/lessons/{id}/extract skulle ha svarat med. */
export const INSIKTER = strom([
  { type: "log", msg: "Analyserar lektionen ..." },
  { type: "done", result: { count: 2, insights: [
      { id: 1, typ: "svårighet", text: "Klassen fastnade på kedjeregeln.",
        ref: null, due_date: null, source: "llm" },
      { id: 2, typ: "kalender", text: "Prov på derivator", ref: null,
        due_date: "2026-09-24", source: "llm" },
    ] } },
]);

/**
 * Fejkar molngränsen. `transkribering` och `extraktion` går att beordra per
 * dag — «dagen då allt går fel» skickar in ett 429 här, inte en annan app.
 */
export async function fejkatMoln(page, { transkribering, extraktion } = {}) {
  const anrop = [];
  await page.route("**/api/transcribe", route => {
    anrop.push("transcribe");
    const svar = transkribering || korning();
    if (typeof svar === "function") return svar(route);
    return route.fulfill({ status: 200, contentType: "text/event-stream", body: svar });
  });
  await page.route("**/api/lessons/*/extract", route => {
    anrop.push("extract");
    const svar = extraktion || INSIKTER;
    if (typeof svar === "function") return svar(route);
    return route.fulfill({ status: 200, contentType: "text/event-stream", body: svar });
  });
  return anrop;
}

/* Två 404:or är MEDVETNA och står kommenterade i koden de kommer ur. De är
   inte fel att laga utan brus att känna igen — allt annat i konsolen fäller
   dagen.

   1. KaTeX:s CSS listar .woff och .ttf som fallback efter .woff2. Vi vendrar
      bara woff2 (webbläsaren behöver inte mer), men tavlans bildexport
      (tavla-bild.js baka) hämtar VARJE url() i @font-face för att baka in den
      som data:-URI — och får 404 på de två den inte hittar. Den fångar dem och
      låter woff2-URI:n stå först. Webbläsarens egen rendering begär dem aldrig.
   2. `.image-slots.state.json` är omelette-startarens sidovagn (image-slot.js).
      Utanför Claude Designs körtid finns den inte, och komponenten är då
      skrivskyddad — precis som avsett. */
const TILLATNA_404 = [/\/static\/vendor\/katex\/fonts\/.*\.(woff|ttf)$/,
                      /\.image-slots\.state\.json$/];

/**
 * Konsolvakten. Kravet per lärardag är «inga konsolfel» — en dag som ser rätt
 * ut men skriver TypeError i konsolen är en dag som går sönder på lärarens
 * dator i morgon.
 */
export function vakt(page) {
  const fel = [];
  page.on("pageerror", e => fel.push(
    "JS: " + e.message
    + (e.stack ? " @ " + String(e.stack).split("\n").slice(1, 3).join(" ← ") : "")));
  page.on("console", m => {
    if (m.type() !== "error") return;
    const url = (m.location() || {}).url || "";
    if (TILLATNA_404.some(r => r.test(url))) return;
    fel.push("konsol: " + m.text() + (url ? " ← " + url : ""));
  });
  return fel;
}

/** Löftet om serverns dokumenthög — hämtas FÖRE sidladdningen. */
const vantarHogen = page => page.waitForResponse(
  r => new URL(r.url()).pathname === "/api/dokument" && r.request().method() === "GET",
  { timeout: 30_000 });

/**
 * Öppnar appen med fryst klocka och väntar tills serverns data är inne.
 *
 * Också DOKUMENTHÖGEN: prototypens elva papper ligger framme tills
 * /api/dokument svarat, och en dag som frågar «finns det ett prov i Sparat?»
 * innan dess får prototypens svar. Det märks inte i en tom bas — men i en bas
 * som vuxit under en natts soak-körning tar hydreringen längre tid, och då
 * började dagarna arbeta på fel hög.
 */
export async function oppna(page, { tid = SKOLDAG } = {}) {
  await page.clock.install({ time: new Date(tid) });
  // Tryckknappen ber servern öppna paketet i systemets PDF-läsare (tryck.js →
  // /api/open → os.startfile). Rätt i appen, fel i en svit: dag 3 trycker den
  // varje varv, och en soak-natt lämnar hundra PDF-flikar i lärarens webb-
  // läsare. Anropet GÖRS fortfarande — `spana` ser det, os.startfile gör det
  // inte. Samma sak för /api/reveal (Utforskarfönster).
  await page.route(/\/api\/(open|reveal)$/, r => r.fulfill({
    status: 200, contentType: "application/json", body: '{"ok":true}' }));
  const hogen = vantarHogen(page);
  await page.goto("/");
  await page.waitForFunction(() =>
    window.Kalender && window.Kalender.franServern() && window.Dokument && window.API
      && window.API.pa);
  await hogen;
  await page.waitForTimeout(150);          // högen ritas om efter svaret
}

/** Lägger en inspelning i kön och kör den. Molnet är fejkat — kedjan är äkta. */
export async function transkribera(page, { namn = "NA25 2026-09-08 09.05.m4a",
                                           langd = "01:12:04" } = {}) {
  await page.evaluate(([n, l]) => laggTill(n, l, "C:/inspelningar/" + n), [namn, langd]);
  await page.locator("#starta").click();
}

/** Klickar ett lektionskort i veckan (index i rutnätet) — klicket ÄR valet. */
export async function valjLektion(page, ...index) {
  await page.getByRole("tab", { name: "Planering" }).click();
  for (const n of index) await page.locator("#schemagrid .lekt").nth(n).click();
}

/** Samma sak, men på klassens namn — veckan har fjorton lektioner och ett
 *  index säger inget om vilken lektion dagen handlar om.
 *
 *  Klicket läggs på kortets ÖVERKANT (`.lekttopp`). Mitt på kortet ligger
 *  dokumentremsan när lektionen redan har material, och ett klick där öppnar
 *  förhandsvisningen i stället för att välja lektionen — dagarna delar bas, så
 *  gårdagens papper ligger kvar på korten. */
export async function valjKlass(page, klass, nr = 0) {
  await page.getByRole("tab", { name: "Planering" }).click();
  const kort = page.locator("#schemagrid .lekt[data-valjbar]").filter({ hasText: klass });
  await kort.nth(nr).locator(".lekttopp").click();
}

/** Alla API-anrop sidan gör, med kropp — dagen ska kunna svara på frågan
 *  «nådde det verkligen servern?» utan att fejka rutten. */
export function spana(page) {
  const anrop = [];
  page.on("request", r => {
    let u;
    try { u = new URL(r.url()); } catch (e) { return; }
    if (!u.pathname.startsWith("/api/")) return;
    let kropp = null;
    try { kropp = r.postDataJSON(); } catch (e) { /* inte JSON */ }
    anrop.push({ metod: r.method(), vag: u.pathname, kropp });
  });
  return anrop;
}

export const traff = (anrop, slut) => anrop.filter(a => a.vag.endsWith(slut));

/**
 * Ställer planeringen och trycker Skriv. Klass/kurs sätts bara när dagen inte
 * valt en lektion i veckan (då bär lektionen dem själv).
 */
export async function skriv(page, { typ = "Tavla", moment = "derivatans definition",
                                    klass = null, kurs = null, onskemal = null,
                                    vantaSvar = true } = {}) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(([t, m, kl, ku, ons]) => {
    window.SattLage(t);
    const satt = (id, v) => {
      const e = document.querySelector(id);
      if (!e || v == null) return;
      e.value = v;
      e.dispatchEvent(new Event("change", { bubbles: true }));
    };
    satt("#p-kurs", ku);
    satt("#p-klass", kl);
    const f = document.querySelector("#moment");
    f.value = m;
    f.dispatchEvent(new Event("input", { bubbles: true }));
    // Skriv-knappen bor i steg 4 («Upplägg»); stapeln viker ihop de andra.
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
    /* Anteckningarnas källa är rutan i typvalen, inte momentet — den fylls
       EFTER gaTill, för raderna ritas om när typen byts. */
    if (ons != null) {
      const ruta = document.querySelector(".typfritext");
      if (ruta) {
        ruta.value = ons;
        ruta.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
  }, [typ, moment, klass, kurs, onskemal]);
  /* Vänta på SVARET, inte på att ett papper syns. Utkastet återställs ur
     servern vid sidladdning (Etapp 0.2), så «#dokument är synligt» kan vara
     gårdagens papper — och då mäter dagen ingenting. */
  const svar = vantaSvar
    ? page.waitForResponse(
        r => /\/api\/(planning|exams|anteckningar)\/generate$/.test(new URL(r.url()).pathname),
        { timeout: 60_000 })
    : Promise.resolve(null);
  await page.locator("#skriv").click();
  return svar;
}

/** Löftet om nästa generering — ska hämtas FÖRE klicket som startar den. */
export const vantarGenerering = (page, timeout = 60_000) =>
  page.waitForResponse(
    r => /\/api\/(planning|exams)\/generate$/.test(new URL(r.url()).pathname),
    { timeout });

/** Väntar ut molnraden. Kassetten svarar snabbt, men servern validerar,
 *  reparerar och renderar på riktigt — och renderingen kan gå en runda till.
 *
 *  Kommer inget papper är beskedet i skrivrutan det enda som förklarar varför,
 *  och det är borta när testet är slut — så det följer med i felet. */
export async function vantaPapper(page, timeout = 40_000) {
  try {
    await expect(page.locator("#dokument")).toBeVisible({ timeout });
  } catch (e) {
    const besked = await page.locator("#skrivstatus").innerText().catch(() => "");
    throw new Error("inget papper kom fram. Skrivrutan sa: "
                    + (besked.replace(/\s+/g, " ").trim().slice(0, 400) || "ingenting"));
  }
}

/** Godkänner pappret och väntar tills servern skrivit in det. */
export async function godkann(page, { timeout = 60_000 } = {}) {
  const fore = await antalSparade(page);
  await page.locator("#godkann").click();
  await expect.poll(() => antalSparade(page), { timeout }).toBeGreaterThan(fore);
}

export const antalSparade = page =>
  page.evaluate(() => window.Dokument.sparade().length);

/** Papperen servern faktiskt har — läst genom en omladdning, inte ur minnet. */
export async function efterOmladdning(page) {
  const hogen = vantarHogen(page);
  await page.reload();
  await page.waitForFunction(() =>
    window.Dokument && window.API && window.API.pa && window.Kalender
      && window.Kalender.franServern());
  await hogen;
  await page.waitForTimeout(150);
  return page.evaluate(() => window.Dokument.sparade());
}

/**
 * Kravet som gäller varje dag: inga konsolfel, inga JS-fel.
 *
 * `tillat` är för dagen som SJÄLV sabbar nätet: webbläsaren skriver en rad i
 * konsolen för varje 409 och varje avbruten begäran, och den raden är då inte
 * ett fynd utan kvittot på att felinjektionen träffade. Appens egna fel — ett
 * TypeError, ett obehandlat löfte — går aldrig att tillåta bort så länge
 * mönstret pekar på en URL vi själva stoppade.
 */
export function rent(fel, { tillat = [] } = {}) {
  const kvar = fel.filter(f => !tillat.some(r => r.test(f)));
  expect(kvar, kvar.join(" | ")).toEqual([]);
}
