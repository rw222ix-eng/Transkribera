import { expect, test } from "@playwright/test";

/* PUNKTERNA VÄLJS UR DET MAN UTGÅR IFRÅN
 *
 * Läraren: «AI-modellen ska analysera det man utgår ifrån, exempelvis boken
 * eller en tidigare uppgift, scanna innehållet och korskorrelera det med det
 * centrala innehållet så att punkterna kan väljas automatiskt. Tydligt kopplat,
 * inte långsökt. Förvalt, så man slipper klicka i, men går att klicka bort.»
 *
 * Det som prövas här är förvalet och dess GRÄNSER, för ett förval som alltid
 * slår till är lika trasigt som ett som aldrig gör det:
 *   · slår till när en källa finns (bokspannet), med noten som säger varifrån
 *     och brickans skäl som säger varför just den punkten,
 *   · rör ALDRIG kryss läraren satt själv,
 *   · håller sig borta när kalendern redan svarat, för det är hennes eget svar,
 *   · tiger vid tomt svar och vid fel i stället för att hitta på en förvalsrad,
 *   · låter osäkra punkter ligga som förslag som inte räknas förrän de klickas.
 *
 * RIKTIG RUTT, INTE MOCK. POST /api/planning/ci-forslag finns i main
 * (app/ci_forslag.py), och e2e-servern kör den med fejk-claude: prompten bär
 * markören «innehållsdomare» och kassetten med samma namn svarar. Kassetten är
 * inspelad för nivå 2a och ett spann om andragradsekvationer, och därför står
 * planeringen i den här filen på Matematik, nivå 2a.
 *
 * De två svar som INTE går att beställa av en inspelad kassett, ett tomt svar
 * och ett riktigt nätfel, fejkas med `page.route` i sitt eget test och bara
 * där: `fejka(page, { svar })` respektive `{ fel: true }`. */

/* Kassettens svar, översatt till etiketterna läraren ser i nivå 2a.
   G25-M2A-ALG-8/6/7 är de tydliga, DIG-1 och PRO-2 de osäkra. */
const PUNKTER = ["Andragradsekvationer", "Andragradsfunktioner", "Kvadreringsregler"];
const OSAKRA = ["Digitala verktyg", "Matematiska modeller"];
const I_NIVAN = 17;                       // hela nivå 2a, för täckningsraden

const AVSNITT = [
  { nr: "2.1", titel: "Andragradsfunktioner", kap: "Kapitel 2 · Andragradare",
    vag: "Grafen", sid: "40–51", uppg: 30 },
  { nr: "2.2", titel: "Andragradsekvationer", kap: "Kapitel 2 · Andragradare",
    vag: "pq-formeln", sid: "52–65", uppg: 28 },
];

const BOK = {
  id: 3, namn: "Matematik 5000+ Kurs 2a", kurs: "Matematik, nivå 2a",
  sidor: 120, sidoffset: 0, status: "klar", lasta: 65, avsnitt: AVSNITT,
};

/* Provposten med lärarens egna punkter i beskrivningen. Den används bara i
   rangordningstestet: har hon svarat själv ska modellen inte frågas. */
const KALENDERPROV = {
  datum: "2026-10-01", tid: "09:05–10:20", titel: "NA25: PROV 1 (kap 2)",
  klass: "NA25", slag: "prov", kalla: "schema",
  ci: ["G25-M2A-ALG-5"], ci_okant: 0,
};

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

/** Fejkar datagrunden och hyllan. Förslagsrutten går till den RIKTIGA servern
    om inte `svar` eller `fel` ges. `anrop` samlar kropparna, så «ingen begäran
    alls» går att pröva lika hårt som en begäran. */
async function fejka(page, { poster = [], svar = null, fel = false } = {}) {
  const anrop = [];
  /* Begäran räknas på vägen ut och inte i en rutt: då mäter samma rad både den
     mockade och den riktiga vägen. */
  page.on("request", r => {
    if (r.url().includes("/api/planning/ci-forslag")) anrop.push(r.postDataJSON());
  });
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route =>
    json(route, { schema: [], lov: [], poster, innehall: [] }));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
  await page.route("**/api/bocker**", route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/uppslag")) {
      return json(route, { fran: 40, till: 65, uppgifter: [], olasta: [],
                           utan_fakta: [], sidor: [] });
    }
    if (url.pathname.endsWith("/las")) {
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "done", result: { uppgifter: [], lasta: 0 } }]) });
    }
    return json(route, { bocker: [BOK] });
  });
  if (svar || fel) {
    await page.route("**/api/planning/ci-forslag", route => {
      /* Ett riktigt fel (nätet nere) och inte modellens otydlighet: klienten
         ska tiga om det, inte skriva en rad om något läraren inte bett om. */
      if (fel) return route.fulfill({ status: 500, contentType: "application/json",
                                      body: JSON.stringify({ error: "nej" }) });
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "progress", message: "Läser underlaget …" },
                     { type: "done", result: svar }]) });
    });
  }
  return anrop;
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern()
  && window.Bok && window.Bok.franServern() && window.Dokument);

/** Ställer lektionens klass, kurs och dag utan att gå via veckorutan. */
const staller = (page, { klass, kurs, datum }) => page.evaluate(v => {
  const satt = (id, varde) => {
    const f = document.querySelector(id);
    if (f.tagName === "SELECT" && ![...f.options].some(o => o.value === varde
                                                      || o.textContent === varde)) {
      f.appendChild(Object.assign(document.createElement("option"),
                                  { textContent: varde }));
    }
    f.value = varde;
    f.dispatchEvent(new Event("change", { bubbles: true }));
  };
  satt("#p-klass", v.klass);
  satt("#p-kurs", v.kurs);
  satt("#p-datum", v.datum);
}, { klass, kurs, datum });

/* Stapeln viker ihop de steg man inte står i: en gömd not kan vara gömd av fel
   skäl, och då är «inte synlig» ett grönt test utan innehåll. Bokdörren bor i
   steg 3, Gy-brickorna och noten i steg 4. */
const tillSteg = (page, n) => page.evaluate(s => {
  window.PlanSteg.las(4, false);
  window.PlanSteg.gaTill(s);
}, n);

const valda = page => page.evaluate(() => window.GyVal.valda());
const noten = page => page.locator("#gykalender");

/** Planeringen med klassen, kursen (som pekar ut nivå 2a) och typen vald. */
async function planeringen(page, typ, datum = "2026-09-28") {
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await staller(page, { klass: "NA25", kurs: "Matematik, nivå 2a", datum });
  await page.evaluate(t => window.SattLage(t), typ);
  await tillSteg(page, 3);
}

/** Lärarens gest: hon slår upp s. 40–65 i bokdörren. Det är den som startar
    förslaget: uppslaget skriver momentfältet och skickar `input`. */
async function slarUpp(page, fran = 40, till = 65) {
  await page.evaluate(s => {
    window.Kallor.satt("bok", true);
    window.Uppslag.laggBok("Matematik 5000+ Kurs 2a", { fran: s.fran, till: s.till });
  }, { fran, till });
  await tillSteg(page, 4);
}

/* Debouncen (FORSLAG_PAUS, 600 ms) plus modellen och lite marginal. Väntan
   används bara för att pröva FRÅNVARO av en begäran. */
const stillhet = page => page.waitForTimeout(2500);
const SVAR_TID = { timeout: 20_000 };     // fejk-claude startar en process

/* ── 1 · Förvalet ───────────────────────────────────── */

test("bokspannet ger brickor och en not som säger varifrån", async ({ page }) => {
  const anrop = await fejka(page);
  await planeringen(page, "Prov");
  await slarUpp(page);

  await expect(noten(page)).toContainText("Ur underlaget: 3 punkter", SVAR_TID);
  expect((await valda(page)).sort()).toEqual(PUNKTER);
  await expect(page.locator("#gychips")).toBeVisible();

  /* Begäran bär nivån och boken i kontraktets form. */
  const k = anrop[anrop.length - 1];
  expect(k.niva).toBe("mate/2a");
  expect(k.bok).toEqual({ id: 3, fran: 40, till: 65 });
  /* Remsorna hör inte hit: frågan är vad SIDORNA handlar om. */
  expect("remsa" in k.bok).toBe(false);
});

test("brickan bär skälet, så läraren ser varför punkten står ikryssad",
  async ({ page }) => {
    await fejka(page);
    await planeringen(page, "Prov");
    await slarUpp(page);
    await expect(noten(page)).toContainText("Ur underlaget", SVAR_TID);

    const bricka = page.locator("#gychips .gychip", { hasText: "Andragradsekvationer" });
    /* Vilka orden är hör till kassetten. Att skälet PEKAR PÅ MATERIALET, med
       en sida, är kravet. */
    await expect(bricka).toHaveAttribute("data-tip", /[Ss]\. \d+/);
  });

/* ── 2 · De osäkra är förslag, inte kryss ───────────── */

test("osäkra punkter ligger som förslag och räknas först när de klickas",
  async ({ page }) => {
    await fejka(page);
    await planeringen(page, "Prov");
    await slarUpp(page);
    await expect(noten(page)).toContainText("Ur underlaget", SVAR_TID);

    const forslag = page.locator("#gychips .gyforslag");
    await expect(forslag).toHaveCount(OSAKRA.length);
    expect((await forslag.allTextContents()).sort()).toEqual(OSAKRA);
    await expect(forslag.first()).toHaveAttribute("aria-pressed", "false");
    /* Täckningen räknar tre, inte fem: ett förslag som räknas är inget förslag. */
    await expect(page.locator("#tacktext")).toContainText(`3 av ${I_NIVAN}`);

    await forslag.first().click();
    expect((await valda(page)).length).toBe(4);
    await expect(page.locator("#tacktext")).toContainText(`4 av ${I_NIVAN}`);
    await expect(page.locator("#gychips .gyforslag")).toHaveCount(OSAKRA.length - 1);
  });

/* ── 3 · Lärarens egna kryss ────────────────────────── */

test("kryss läraren satt själv skrivs aldrig över", async ({ page }) => {
  await fejka(page);
  await planeringen(page, "Prov");
  await slarUpp(page);
  await expect(noten(page)).toContainText("Ur underlaget", SVAR_TID);

  /* Hennes hand: nu står urvalet inte längre precis som förvalet lämnade det,
     och vakten (punktforval/punktnyckel) stänger dörren för nästa omkörning. */
  await page.evaluate(() => window.GyVal.vaxla("Normalfördelning"));
  /* Ett NYTT spann är en ny källa och därmed en ny fråga till modellen. */
  await page.evaluate(() => window.Uppslag.satt(52, 65));

  await expect(noten(page)).toContainText("dina kryss står kvar", SVAR_TID);
  expect((await valda(page)).sort()).toEqual(PUNKTER.concat("Normalfördelning").sort());
  /* Modellens punkter går inte förlorade, de ligger som förslag att ta. */
  await expect(page.locator("#gychips .gyforslag").first()).toBeVisible();
});

/* ── 4 · Tystnaden ─────────────────────────────────── */

test("tomt svar rör ingenting och säger modellens egen förklaring",
  async ({ page }) => {
    await fejka(page, { svar: { punkter: [], osakra: [], kalla: "",
                                tomt_skal: "Inga sidor är lästa än" } });
    await planeringen(page, "Prov");
    await slarUpp(page);
    await expect(noten(page)).toHaveText("Inga sidor är lästa än", SVAR_TID);
    expect(await valda(page)).toEqual([]);
  });

test("ett fel är tyst, ingen påhittad förvalsrad", async ({ page }) => {
  await fejka(page, { fel: true });
  await planeringen(page, "Prov");
  await slarUpp(page);
  await stillhet(page);
  await expect(noten(page)).toBeHidden();
  expect(await valda(page)).toEqual([]);
});

/* ── 5 · Rangordningen mellan förvalen ──────────────── */

test("har läraren skrivit punkterna i kalendern frågas modellen inte",
  async ({ page }) => {
    const anrop = await fejka(page, { poster: [KALENDERPROV] });
    await planeringen(page, "Prov", "2026-10-01");
    await slarUpp(page);
    await stillhet(page);
    /* Kalendern svarade, och det är lärarens eget svar. */
    await expect(noten(page)).toContainText("Ur kalendern: 1 punkt");
    expect(await valda(page)).toEqual(["Exponentialekvationer"]);
    expect(anrop).toEqual([]);
  });

test("anteckningarna har inget centralt innehåll och frågar aldrig",
  async ({ page }) => {
    /* Frånvaron prövas mot en närvaro i samma test: provet frågar på samma
       bokdörr, anteckningarna gör det inte. Annars hade en trasig lokator
       eller en stängd dörr sett ut som ett grönt svar. */
    const anrop = await fejka(page);
    await planeringen(page, "Prov");
    await slarUpp(page);
    await expect(noten(page)).toContainText("Ur underlaget", SVAR_TID);
    expect(anrop.length).toBe(1);

    await page.evaluate(() => window.SattLage("Anteckningar"));
    await page.evaluate(() => window.Uppslag.satt(52, 65));
    await stillhet(page);
    expect(anrop.length).toBe(1);
  });

/* ── 6 · Samma källa frågas inte två gånger ─────────── */

test("en omkörning kostar inget nytt anrop, svaret ritas om ur minnet",
  async ({ page }) => {
    const anrop = await fejka(page);
    await planeringen(page, "Prov");
    await slarUpp(page);
    await expect(noten(page)).toContainText("Ur underlaget", SVAR_TID);
    expect(anrop.length).toBe(1);

    /* Typbytet suddar noten och kör förvalen på nytt. Källan är densamma, så
       noten ska komma tillbaka utan att modellen frågas igen. */
    await page.evaluate(() => window.SattLage("Tavla"));
    await tillSteg(page, 4);
    await expect(noten(page)).toContainText("Ur underlaget");
    await stillhet(page);
    expect(anrop.length).toBe(1);
  });
