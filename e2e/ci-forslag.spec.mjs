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
 *   · håller sig borta när kalendern redan svarat, för det är lärarens eget svar,
 *   · tiger vid tomt svar och vid fel, i stället för att hitta på en förvalsrad,
 *   · låter osäkra punkter ligga som förslag som inte räknas förrän de klickas.
 */

/* MOCKAD RUTT ELLER RIKTIG SERVER
 *
 * Backenden (POST /api/planning/ci-forslag, app/ci_forslag.py) byggs parallellt.
 * Tills den ligger i main svarar `page.route` med kontraktets SSE-svar, och hela
 * frontendflödet prövas mot det. När rutten finns sätts MOCKA till false: då
 * svarar den riktiga servern med kassetten `innehallsdomare` via fejk-claude,
 * och testerna nedan prövar samma flöde hela vägen ner.
 *
 * Påståenden om EXAKT vilka punkter som kommer tillbaka hör till mocken och
 * körs bara under den (`test.skip`), för kassettens svar är modellens, inte vårt.
 * Allt annat gäller i båda lägena. */
const MOCKA = true;

/* Kontraktets svarsform, ord för ord: punkter kryssas i, osakra föreslås,
   kalla står i noten, tomt_skal förklarar ett tomt svar. */
const SVAR = {
  punkter: [
    { kod: "G25-M2C-ALG-6", skal: "s. 44–51 löser andragradsekvationer med pq-formeln" },
    { kod: "G25-M2C-ALG-5", skal: "s. 40–43 andragradsfunktionens graf och nollställen" },
  ],
  osakra: [
    { kod: "G25-M2C-ALG-4", skal: "kvadreringsreglerna används i härledningen" },
  ],
  kalla: "Matematik 5000+ Kurs 2c s. 40–65 · 2.1 Andragradsfunktioner · 2.2 Andragradsekvationer",
  tomt_skal: "",
};

const AVSNITT = [
  { nr: "2.1", titel: "Andragradsfunktioner", kap: "Kapitel 2 · Andragradare",
    vag: "Grafen", sid: "40–51", uppg: 30 },
  { nr: "2.2", titel: "Andragradsekvationer", kap: "Kapitel 2 · Andragradare",
    vag: "pq-formeln", sid: "52–65", uppg: 28 },
];

const BOK = {
  id: 3, namn: "Matematik 5000+ Kurs 2c", kurs: "Matematik, nivå 2c",
  sidor: 120, sidoffset: 0, status: "klar", lasta: 65, avsnitt: AVSNITT,
};

/* Provposten med lärarens egna punkter i beskrivningen. Den används bara i
   rangordningstestet: har hon svarat själv ska modellen inte fråga. */
const KALENDERPROV = {
  datum: "2026-10-01", tid: "09:05–10:20", titel: "NA25: PROV 1 (kap 2)",
  klass: "NA25", slag: "prov", kalla: "schema",
  ci: ["G25-M2C-ALG-2"], ci_okant: 0,
};

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

/** Fejkar datagrunden, hyllan och (när MOCKA) förslagsrutten. `anrop` samlar
    kropparna, så «ingen begäran alls» går att pröva lika hårt som en begäran. */
async function fejka(page, { poster = [], svar = SVAR, fel = false } = {}) {
  const anrop = [];
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
  await page.route("**/api/planning/ci-forslag", route => {
    anrop.push(route.request().postDataJSON());
    if (!MOCKA) return route.continue();
    /* Ett riktigt fel (nätet nere) och inte modellens otydlighet: klienten ska
       tiga om det, inte skriva en rad om något läraren inte bett om. */
    if (fel) return route.fulfill({ status: 500, contentType: "application/json",
                                    body: JSON.stringify({ error: "nej" }) });
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "progress", message: "Läser underlaget mot centralt innehåll …" },
                   { type: "done", result: svar }]) });
  });
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

/** Planeringen med klassen, kursen (som pekar ut nivå 2c) och typen vald. */
async function planeringen(page, typ, datum = "2026-09-28") {
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await staller(page, { klass: "NA25", kurs: "Matematik, nivå 2c", datum });
  await page.evaluate(t => window.SattLage(t), typ);
  await tillSteg(page, 3);
}

/** Lärarens gest: hon slår upp s. 40–65 i bokdörren. Det är den som startar
    förslaget: uppslaget skriver momentfältet och skickar `input`. */
async function slarUpp(page, fran = 40, till = 65) {
  await page.evaluate(s => {
    window.Kallor.satt("bok", true);
    window.Uppslag.laggBok("Matematik 5000+ Kurs 2c", { fran: s.fran, till: s.till });
  }, { fran, till });
  await tillSteg(page, 4);
}

/* Debouncen (FORSLAG_PAUS, 600 ms) plus lite marginal. Det här är den enda
   väntan i filen, och den används bara för att pröva FRÅNVARO av en begäran. */
const stillhet = page => page.waitForTimeout(1100);

/* ── 1 · Förvalet ───────────────────────────────────── */

test("bokspannet ger brickor och en not som säger varifrån", async ({ page }) => {
  const anrop = await fejka(page);
  await planeringen(page, "Prov");
  await slarUpp(page);

  const not = page.locator("#gykalender");
  await expect(not).toContainText(/Ur underlaget: \d+ punkt/);
  await expect(page.locator("#gychips")).toBeVisible();

  /* Begäran bär nivån och boken i kontraktets form. */
  await expect.poll(() => anrop.length).toBeGreaterThan(0);
  const k = anrop[anrop.length - 1];
  expect(k.niva).toBe("mate/2c");
  expect(k.bok).toEqual({ id: 3, fran: 40, till: 65 });

  test.skip(!MOCKA, "punkterna är kassettens när backenden svarar");
  expect((await valda(page)).sort()).toEqual(
    ["Andragradsekvationer", "Andragradsfunktioner"]);
  await expect(not).toHaveText(
    "Ur underlaget: 2 punkter (Matematik 5000+ Kurs 2c s. 40–65)");
});

test("brickan bär skälet, så läraren ser varför punkten står ikryssad",
  async ({ page }) => {
    test.skip(!MOCKA, "skälet är kassettens när backenden svarar");
    await fejka(page);
    await planeringen(page, "Prov");
    await slarUpp(page);

    const bricka = page.locator("#gychips .gychip", { hasText: "Andragradsekvationer" });
    await expect(bricka).toHaveAttribute(
      "data-tip", "s. 44–51 löser andragradsekvationer med pq-formeln");
  });

/* ── 2 · De osäkra är förslag, inte kryss ───────────── */

test("osäkra punkter ligger som förslag och räknas först när de klickas",
  async ({ page }) => {
    test.skip(!MOCKA, "listan osakra är kassettens när backenden svarar");
    await fejka(page);
    await planeringen(page, "Prov");
    await slarUpp(page);

    const forslag = page.locator("#gychips .gyforslag");
    await expect(forslag).toHaveCount(1);
    await expect(forslag).toHaveText("Kvadreringsregler");
    await expect(forslag).toHaveAttribute("aria-pressed", "false");
    /* Täckningen räknar två, inte tre: ett förslag som räknas är inget förslag. */
    await expect(page.locator("#tacktext")).toContainText("2 av 18");

    await forslag.click();
    expect((await valda(page)).sort()).toEqual(
      ["Andragradsekvationer", "Andragradsfunktioner", "Kvadreringsregler"]);
    await expect(page.locator("#tacktext")).toContainText("3 av 18");
    await expect(page.locator("#gychips .gyforslag")).toHaveCount(0);
  });

/* ── 3 · Lärarens egna kryss ────────────────────────── */

test("kryss läraren satt själv skrivs aldrig över", async ({ page }) => {
  test.skip(!MOCKA, "vakten prövas mot ett känt svar");
  await fejka(page);
  await planeringen(page, "Prov");
  await slarUpp(page);
  await expect(page.locator("#gykalender")).toContainText("Ur underlaget");

  /* Hennes hand: nu står urvalet inte längre precis som förvalet lämnade det,
     och vakten (punktforval/punktnyckel) stänger dörren för nästa omkörning. */
  await page.evaluate(() => window.GyVal.vaxla("Regressionsanalys"));
  /* Ett NYTT spann är en ny källa och därmed en ny fråga till modellen. */
  await page.evaluate(() => window.Uppslag.satt(52, 65));

  await expect(page.locator("#gykalender")).toContainText("dina kryss står kvar");
  expect((await valda(page)).sort()).toEqual(
    ["Andragradsekvationer", "Andragradsfunktioner", "Regressionsanalys"]);
  /* Modellens punkter går inte förlorade, de ligger som förslag att ta. */
  await expect(page.locator("#gychips .gyforslag")).toHaveText("Kvadreringsregler");
});

/* ── 4 · Tystnaden ─────────────────────────────────── */

test("tomt svar rör ingenting och säger modellens egen förklaring",
  async ({ page }) => {
    test.skip(!MOCKA, "det tomma svaret går bara att beställa av mocken");
    await fejka(page, { svar: { punkter: [], osakra: [], kalla: "",
                                tomt_skal: "Inga sidor är lästa än" } });
    await planeringen(page, "Prov");
    await slarUpp(page);
    await expect(page.locator("#gykalender")).toHaveText("Inga sidor är lästa än");
    expect(await valda(page)).toEqual([]);
  });

test("ett fel är tyst, ingen påhittad förvalsrad", async ({ page }) => {
  test.skip(!MOCKA, "felvägen går bara att beställa av mocken");
  await fejka(page, { fel: true });
  await planeringen(page, "Prov");
  await slarUpp(page);
  await stillhet(page);
  await expect(page.locator("#gykalender")).toBeHidden();
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
    await expect(page.locator("#gykalender")).toContainText("Ur kalendern: 1 punkt");
    expect(await valda(page)).toEqual(["Logaritmer"]);
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
    await expect.poll(() => anrop.length).toBe(1);

    await page.evaluate(() => window.SattLage("Anteckningar"));
    await page.evaluate(() => window.Uppslag.satt(52, 65));
    await stillhet(page);
    expect(anrop.length).toBe(1);
  });

/* ── 6 · Diagnosen ─────────────────────────────────── */

test("diagnosen utan källa är hela nivån och frågar inte", async ({ page }) => {
  const anrop = await fejka(page);
  await planeringen(page, "Diagnos");
  await tillSteg(page, 4);
  await stillhet(page);
  /* Diagnosen ÄR hela kursens innehåll så länge inget avgränsar den. */
  expect((await valda(page)).length).toBe(18);
  expect(anrop).toEqual([]);
});

test("diagnosen med ett bokspann smalnar av mot underlaget", async ({ page }) => {
  const anrop = await fejka(page);
  await planeringen(page, "Diagnos");
  await slarUpp(page);
  await expect.poll(() => anrop.length).toBeGreaterThan(0);
  await expect(page.locator("#gykalender")).toContainText(/Ur underlaget: \d+ punkt/);

  test.skip(!MOCKA, "punkterna är kassettens när backenden svarar");
  expect((await valda(page)).sort()).toEqual(
    ["Andragradsekvationer", "Andragradsfunktioner"]);
});

/* ── 7 · Samma källa frågas inte två gånger ─────────── */

test("en omkörning kostar inget nytt anrop, svaret ritas om ur minnet",
  async ({ page }) => {
    const anrop = await fejka(page);
    await planeringen(page, "Prov");
    await slarUpp(page);
    await expect(page.locator("#gykalender")).toContainText("Ur underlaget");
    await expect.poll(() => anrop.length).toBe(1);

    /* Typbytet suddar noten och kör förvalen på nytt. Källan är densamma, så
       noten ska komma tillbaka utan att modellen frågas igen. */
    await page.evaluate(() => window.SattLage("Tavla"));
    await tillSteg(page, 4);
    await expect(page.locator("#gykalender")).toContainText("Ur underlaget");
    await stillhet(page);
    expect(anrop.length).toBe(1);
  });
