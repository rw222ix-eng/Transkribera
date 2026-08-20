import { expect, test } from "@playwright/test";

/* PROVET UTGÅR FRÅN HELHETEN
 *
 * Ett prov prövar inte lektionen — det prövar det klassen tränat på sedan
 * förra provet. Tre lektionsgester följde ändå med in i provet, för de bodde i
 * samma steg och ingen hade frågat vilken typ som skrevs:
 *
 *   1. «Uppgifterna på sidorna» (#uppgblock) — lärarens urval på det uppslagna
 *      spannet. Ett urval är ett övningsbeslut, och blocket listar dessutom
 *      bara uppgifter på sidor som hunnit läsas in: på ett provspann över
 *      trettio sidor visade det tre och såg ut som ett svar.
 *   2. «Vad var svårt?» och «Vad ska väga tyngst?» — ett prov som lutas efter
 *      vad läraren sett falla är inte representativt, åt något håll.
 *   3. «Lösningar till bokens uppgifter» — provet har sitt eget lösningsförslag
 *      och sitt formelblad; bokens lösningsblad är det klassen övade med.
 *
 * Diagnosen mäter av samma skäl och behandlas likadant. Tavlan, arbetsbladet
 * och gruppuppgiften är övning och rörs inte.
 *
 * Det som prövas här är alltså mest FRÅNVARO — och frånvaro måste prövas mot
 * en närvaro i samma svit, annars är en trasig lokator ett grönt test. Varje
 * påstående om provet har därför sitt motstycke för en övningstyp.
 */

/* Grovplaneringen: lärarens egna rader, en per lektion, som synken läst dem ur
   kalenderhändelsernas beskrivningar. Tre lektioner före provet — spannen
   överlappar precis som verkliga gör, så unionen (2–12) är det enda rätta
   svaret och inte råkar vara sista radens `till`. Den fjärde raden ligger EFTER
   provdagen och ska inte räknas: klassen har inte varit där än. */
const INNEHALL = [
  { datum: "2026-08-24", tid: "09:05–10:20", klass: "NA25",
    kurs: "Matematik, nivå 2c", fran: 2, till: 6, uppg: "1101–1119" },
  { datum: "2026-08-25", tid: "09:05–10:20", klass: "NA25",
    kurs: "Matematik, nivå 2c", fran: 5, till: 9, uppg: "1120–1140" },
  { datum: "2026-08-31", tid: "09:05–10:20", klass: "NA25",
    kurs: "Matematik, nivå 2c", fran: 7, till: 12, uppg: "1201–1230" },
  { datum: "2026-09-14", tid: "09:05–10:20", klass: "NA25",
    kurs: "Matematik, nivå 2c", fran: 20, till: 26, uppg: "1301–1320" },
];

const SCHEMA = { schema: [], lov: [], poster: [], innehall: INNEHALL };

const AVSNITT = [
  { nr: "1.1", titel: "Repetition", kap: "Kapitel 1 · Algebra",
    vag: "Algebraiska uttryck", sid: "2–6", uppg: 19 },
  { nr: "1.2", titel: "Linjära modeller", kap: "Kapitel 1 · Algebra",
    vag: "Räta linjens ekvation", sid: "7–12", uppg: 34 },
];

const BOK = {
  id: 3, namn: "Matematik 5000+ Kurs 2c", kurs: "Matematik, nivå 2c",
  sidor: 120, sidoffset: 0, status: "klar", lasta: 12, avsnitt: AVSNITT,
};

/* Uppslaget s. 2–6 som servern läst det: nitton uppgifter, 1101–1119. */
const UPPG = [];
for (let n = 1101; n <= 1119; n++) {
  UPPG.push({ nr: n, sida: 2 + Math.floor((n - 1101) / 4), niva: 1 + ((n - 1101) % 3) });
}

const PROV = {
  titel: "Prov", kurs: "Matematik, nivå 2c", hjalpmedel: "",
  uppgifter: [{ del: null, formaga: "P", typ: "rutin", poang: [2, 0, 0],
                text: "Beräkna", losning: "1", bedomning: "+2 E" }],
};

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

/* En ANNAN bok i hyllan, kortare och märkt med en annan kurs. Den behövs för
   två frågor som bara går att ställa med en hylla på flera böcker: står dörren
   på kursens bok eller på hyllans FÖRSTA, och överlever uppslaget att spannet
   byter till en bok där de sista sidorna inte finns? */
const BOK_1C = {
  id: 4, namn: "Exponent 1c", kurs: "Matematik, nivå 1c",
  sidor: 40, sidoffset: 0, status: "klar", lasta: 0,
  avsnitt: [{ nr: "1.1", titel: "Tal och räkning", kap: "Kapitel 1 · Tal",
              vag: "De fyra räknesätten", sid: "2–9", uppg: 12 }],
};

/** Fejkar datagrunden, hyllan och generatorrutten. `anrop` samlar kropparna. */
async function fejka(page, { sparade = [], bocker = null, sidbilder = null } = {}) {
  const anrop = [];
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade, utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
  await page.route("**/api/bocker**", route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/uppslag")) {
      return json(route, { fran: 2, till: 6, uppgifter: UPPG,
                           olasta: [], utan_fakta: [], sidor: [] });
    }
    if (url.pathname.endsWith("/las")) {
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "done", result: { uppgifter: UPPG, lasta: 0 } }]) });
    }
    return json(route, { bocker: bocker || [BOK] });
  });
  /* Sidbilderna: en genomskinlig PNG räcker — det som prövas är VILKA sidor i
     VILKEN bok uppslaget ber om, inte hur de ser ut. Rutten registreras SIST
     och vinner därför över hyllans bredare bok-rutt ovan (Playwright matchar i
     omvänd ordning); annars hade varje blad fått hyllans JSON och ett
     `onerror`. */
  if (sidbilder) {
    const PNG = Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
      "base64");
    await page.route("**/api/bocker/*/sida/*.png", route => {
      const m = new URL(route.request().url()).pathname
        .match(/\/api\/bocker\/(\d+)\/sida\/(\d+)\.png/);
      sidbilder.push(`${m[1]}:${m[2]}`);
      return route.fulfill({ status: 200, contentType: "image/png", body: PNG });
    });
  }
  await page.route("**/api/exams/**", route => {
    const vag = new URL(route.request().url()).pathname;
    if (!vag.endsWith("/generate")) return json(route, { ok: true });
    anrop.push(route.request().postDataJSON());
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: { id: 7, exam: PROV, errors: [], rounds: 1 } }]) });
  });
  return anrop;
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern()
  && window.Bok && window.Bok.franServern() && window.Dokument);

/* Stapeln viker ihop de steg man inte står i, så en gömd kontroll kan vara gömd
   av fel skäl. Bokdörren och urvalsblocket bor i steg 3 («Vad ska det utgå
   från?»), typraderna och lärarrutorna i steg 4 («Upplägg — och skriv»). */
const tillSteg = (page, n) => page.evaluate(s => {
  window.PlanSteg.las(4, false);
  window.PlanSteg.gaTill(s);
}, n);

/** Öppnar planeringen med bokdörren uppslagen på s. 2–6 och uppgifterna lästa. */
async function medBoken(page, typ) {
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(t => window.SattLage(t), typ);
  await tillSteg(page, 3);
  await page.evaluate(() => {
    // `tyst` utelämnat: dörren ska stå UPPSLAGEN, för det är i dess panel
    // urvalsblocket bor — en hopfälld panel gömmer blocket av fel skäl.
    window.Kallor.satt("bok", true);
    window.Uppslag.laggBok("Matematik 5000+ Kurs 2c");
    window.Uppslag.satt(2, 6);
  });
  // Uppgifterna kommer ur /uppslag och landar asynkront.
  await page.waitForFunction(() => window.Uppgifter.losningsantal("Alla") > 0);
}

/* ── 1 · Urvalsblocket ──────────────────────────────── */

test("urvalsblocket står framme för tavlan men inte för provet", async ({ page }) => {
  await fejka(page);
  await medBoken(page, "Tavla");
  await expect(page.locator("#uppgblock")).toBeVisible();
  await expect(page.locator("#uppgblock")).toContainText("Uppgifterna på sidorna");

  // Samma uppslag, bara en annan typ: blocket går ner, spannet står kvar.
  await page.evaluate(() => window.SattLage("Prov"));
  await expect(page.locator("#uppgblock")).toBeHidden();
  await expect(page.locator("#bkspann")).toContainText("2");

  // … och kommer tillbaka när läraren går tillbaka till lektionsmaterialet.
  await page.evaluate(() => window.SattLage("Arbetsblad"));
  await expect(page.locator("#uppgblock")).toBeVisible();
});

test("diagnosen behandlas som provet — den mäter också", async ({ page }) => {
  await fejka(page);
  await medBoken(page, "Diagnos");
  await expect(page.locator("#uppgblock")).toBeHidden();
  await tillSteg(page, 4);
  await expect(page.locator("#svartruta")).toBeHidden();
});

/* ── 2 · Remsan i begäran ───────────────────────────── */

test("provets begäran bär spannet men ingen uppgiftsremsa", async ({ page }) => {
  const anrop = await fejka(page);
  await medBoken(page, "Prov");
  await tillSteg(page, 4);
  await page.locator("#skriv").click();

  await expect.poll(() => anrop.length).toBe(1);
  const bok = anrop[0].bok;
  expect(bok).toBeTruthy();
  expect(bok.id).toBe(3);
  expect(bok.fran).toBe(2);
  expect(bok.till).toBe(6);
  /* Nyckeln ska inte FINNAS. Servern öppnar sitt urvalsblock på ifylld remsa
     (routes_planning.bok_urval), och en tom sträng hade räknats som ett svar
     på en fråga provet inte ställer. */
  expect("remsa" in bok).toBe(false);
  expect("bortremsa" in bok).toBe(false);
});

test("arbetsbladets begäran bär remsan som förut", async ({ page }) => {
  const anrop = await fejka(page);
  await medBoken(page, "Arbetsblad");
  await tillSteg(page, 4);
  await page.locator("#skriv").click();

  await expect.poll(() => anrop.length).toBe(1);
  expect(anrop[0].bok.remsa).toContain("1101");
});

/* ── 3 · Lösningar till bokens uppgifter ────────────── */

test("boklösningsraden hör till lektionsmaterialet, inte till provet", async ({ page }) => {
  await fejka(page);
  await medBoken(page, "Arbetsblad");
  await tillSteg(page, 4);
  await expect(page.locator('.typrad[data-id="boklosniva"]')).toHaveCount(1);

  await page.evaluate(() => window.SattLage("Prov"));
  await expect(page.locator('.typrad[data-id="boklosniva"]')).toHaveCount(0);
  /* Provets egna bilagor står kvar — det är DEM raden förväxlades med. */
  await expect(page.locator('.typrad[data-id="bilagor"]')).toHaveCount(1);

  await page.evaluate(() => window.SattLage("Diagnos"));
  await expect(page.locator('.typrad[data-id="boklosniva"]')).toHaveCount(0);
});

test("ett sparat prov får inget lösningsblad till bokens uppgifter", async ({ page }) => {
  await fejka(page);
  await medBoken(page, "Prov");
  /* `bokuppg` är snapshoten som läggs på pappret när det skrivs — tryck.js
     lägger en «Lösningsförslag · boken»-flik i paketet så fort `losning` finns,
     och den fliken hör inte till ett prov. */
  const losning = await page.evaluate(() =>
    (window.Uppgifter.urval({ boklosning: true, boklosniva: "Alla" }) || {}).losning);
  expect(losning).toBe(null);
});

/* ── 4 · Grovplaneringen som provets förval ─────────── */

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

async function planeringen(page, datum = "2026-09-07") {
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await staller(page, { klass: "NA25", kurs: "Matematik, nivå 2c", datum });
}

test("provet ärver hela sträckan klassen gått igenom, inte förra lektionens sidor",
  async ({ page }) => {
    await fejka(page);
    await planeringen(page);
    await page.evaluate(() => window.SattLage("Prov"));
    await tillSteg(page, 3);

    /* Unionen av de tre lektionerna före provdagen: 2–6, 5–9 och 7–12 blir
       2–12. Den fjärde raden (20–26) ligger efter provet och räknas inte. */
    await expect(page.locator("#bkplanering"))
      .toHaveText("Ur planeringen: 3 lektioner, s. 2–12");
    const spann = await page.evaluate(() => window.Uppslag.spann());
    expect(spann.fran).toBe(2);
    expect(spann.till).toBe(12);
  });

test("noten står bara vid provet — en tavla har ett annat underlag",
  async ({ page }) => {
    await fejka(page);
    await planeringen(page);
    await page.evaluate(() => window.SattLage("Prov"));
    await tillSteg(page, 3);
    await expect(page.locator("#bkplanering")).toBeVisible();

    await page.evaluate(() => window.SattLage("Tavla"));
    await expect(page.locator("#bkplanering")).toBeHidden();
  });

test("utan planering för klassen sägs ingenting alls", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  // Annan klass: raderna i kalendern är NA25:s, och appen hittar inte på ett
  // spann åt någon annan.
  await staller(page, { klass: "SA25", kurs: "Matematik, nivå 2c",
                        datum: "2026-09-07" });
  await page.evaluate(() => window.SattLage("Prov"));
  await tillSteg(page, 3);
  await expect(page.locator("#bkplanering")).toBeHidden();
});

test("ett godkänt prov kapar sträckan — det som redan prövats prövas inte igen",
  async ({ page }) => {
    /* Klassen skrev ett prov den 26 augusti. Nästa prov ska utgå från det som
       kom EFTER det — 7–12 ur lektionen den 31 — och inte pröva om s. 2–9.
       Det är den enda regeln som gör två prov i rad till två olika prov. */
    const forra = {
      typ: "Prov", moment: "1.1 Repetition", klass: "NA25",
      kurs: "Matematik, nivå 2c", datum: "2026-08-26", tid: "09:05–10:20",
      gy: [], kalla: false, kallor: [], sidor: "2–9", inst: {}, bilder: {},
      referenser: [], forlaga: null, resultat: null, fokus: "", svart: "",
      kontext: "start", niva: false, svarighet: 0, andrat: [],
      anteckning: "Sparat tidigare", uppgifter: [], bokuppg: null,
    };
    await fejka(page, { sparade: [{
      id: 1, status: "godkant", markor: 0, sort: 1, foljd: null,
      versioner: [forra], dokument: { ...forra, id: 1 } }] });
    await page.goto("/");
    await page.waitForFunction(() => window.Kalender && window.Kalender.franServern()
      && window.Dokument && window.Dokument.sparade().length > 0);
    await page.getByRole("tab", { name: "Planering" }).click();
    await staller(page, { klass: "NA25", kurs: "Matematik, nivå 2c",
                          datum: "2026-09-07" });
    await page.evaluate(() => window.SattLage("Prov"));
    await tillSteg(page, 3);

    await expect(page.locator("#bkplanering"))
      .toHaveText("Ur planeringen: 1 lektion, s. 7–12");
  });

/* ── 4a · Förvalet följer med när lektionen ändras ───
 *
 * Förvalet satt bara vid TYPBYTET, och läraren väljer inte alltid i den
 * ordningen. Valde hon Prov först och lektionen sedan läste förvalet en tom
 * kurs: bokdörren blev stående på hyllans FÖRSTA bok och spannet räknades ur
 * kalenderns alla rader — och sedan hände ingenting mer.
 *
 * Gränsen mot lärarens egen hand är det svåra, och den prövas i BÅDA
 * riktningar: förvalet ska skriva om sitt eget, aldrig hennes.
 */

/** Hyllan med två böcker: 1c-boken FÖRST, så att «hyllans första» och «kursens
    bok» är olika svar och testet kan skilja dem åt. */
const HYLLAN = [BOK_1C, BOK];

test("kursen sätts EFTER typbytet — förvalet följer med till rätt bok",
  async ({ page }) => {
    await fejka(page, { bocker: HYLLAN });
    await page.goto("/");
    await hydrerad(page);
    await page.getByRole("tab", { name: "Planering" }).click();

    // Prov först, medan steg 1 är tomt: hyllans första bok står i dörren.
    await page.evaluate(() => window.SattLage("Prov"));
    await tillSteg(page, 3);
    await expect(page.locator("#bokvalj .valjtext")).toHaveText("Exponent 1c");

    // …och SEDAN lektionen. Förr var det för sent.
    await staller(page, { klass: "NA25", kurs: "Matematik, nivå 2c",
                          datum: "2026-09-07" });
    await expect(page.locator("#bokvalj .valjtext"))
      .toHaveText("Matematik 5000+ Kurs 2c");
    await expect(page.locator("#bkplanering"))
      .toHaveText("Ur planeringen: 3 lektioner, s. 2–12");
    await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
      .toMatchObject({ fran: 2, till: 12, bok: "Matematik 5000+ Kurs 2c" });
  });

test("förvalet skriver om sitt EGET spann när provdagen flyttas",
  async ({ page }) => {
    await fejka(page, { bocker: HYLLAN });
    await planeringen(page);
    await page.evaluate(() => window.SattLage("Prov"));
    await tillSteg(page, 3);
    await expect(page.locator("#bkplanering"))
      .toHaveText("Ur planeringen: 3 lektioner, s. 2–12");

    /* Provet flyttas till den 25 augusti: bara lektionen den 24 ligger före,
       och spannet ska krympa med fönstret. */
    await staller(page, { klass: "NA25", kurs: "Matematik, nivå 2c",
                          datum: "2026-08-25" });
    await expect(page.locator("#bkplanering"))
      .toHaveText("Ur planeringen: 1 lektion, s. 2–6");
    await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
      .toMatchObject({ fran: 2, till: 6 });
  });

test("lärarens eget spann överlever ett senare förval", async ({ page }) => {
  await fejka(page, { bocker: HYLLAN });
  await planeringen(page);
  await page.evaluate(() => window.SattLage("Prov"));
  await tillSteg(page, 3);
  await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
    .toMatchObject({ fran: 2, till: 12 });

  /* Hon drar i remsan själv — första sidan, sedan sista, precis som i huset. */
  await page.locator('#bkremsa .bksida[data-s="8"]').click();
  await page.locator('#bkremsa .bksida[data-s="9"]').click();
  await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
    .toMatchObject({ fran: 8, till: 9 });

  // Provdagen flyttas. Noten följer planeringen — remsan följer LÄRAREN.
  await staller(page, { klass: "NA25", kurs: "Matematik, nivå 2c",
                        datum: "2026-08-25" });
  await expect(page.locator("#bkplanering"))
    .toHaveText("Ur planeringen: 1 lektion, s. 2–6");
  await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
    .toMatchObject({ fran: 8, till: 9 });
});

/* ── 4d · Fönstrets högra kant är provdagen i kalendern ─
 *
 * Provet är bokat innan det är skrivet: läraren la in det när hon la terminen.
 * Planerar hon det sedan FRÅN en lektion — kortet i veckan, den vanliga vägen
 * in — vet steg 1 bara lektionens dag, och fönstret stängdes då mitt i
 * sträckan. TE26A:s prov den 16 september fick «s. 2–5» i stället för
 * planeringens s. 2–39.
 *
 * Poster: ett prov för klassen den 16 september, och ett äldre den 26 augusti
 * som prövar vänsterkanten. Den fjärde innehållsraden (20–26, den 14
 * september) ligger före provdagen men efter lektionen — det är precis den
 * raden som visar vilken kant som gäller.
 */
const PROVPOSTER = [
  { datum: "2026-08-26", tid: "09:05–10:20", titel: "NA25: PROV 1", klass: "NA25",
    slag: "prov", kalla: "schema" },
  { datum: "2026-09-16", tid: "09:05–10:20", titel: "NA25: PROV 2 (kap 1)",
    klass: "NA25", slag: "prov", kalla: "schema" },
];

/** Samma fejk som ovan, men med provposterna i kalendern. */
async function medProvpost(page, { poster = PROVPOSTER, bocker = null } = {}) {
  await fejka(page, { bocker });
  await page.unroute("**/api/schema");
  await page.route("**/api/schema", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ ...SCHEMA, poster }) }));
}

/** Lärarens egen provdag: samma gest som väljaren i upplägget gör. */
const valjProvdag = (page, datum) => page.evaluate(d => {
  const f = document.querySelector('.typrad[data-id="nartid"] .nardatum');
  f.value = d;
  f.dispatchEvent(new Event("change", { bubbles: true }));
}, datum);

test("provdagen kommer ur den bokade posten, inte ur lektionen", async ({ page }) => {
  await medProvpost(page);
  await planeringen(page);                     // lektionen den 7 september
  await page.evaluate(() => window.SattLage("Prov"));
  await tillSteg(page, 3);

  /* Fönstret slutar den 16 september och inte den 7:e, så lektionen den 14
     räknas med: 2–12 blir 2–26. Vänsterkanten är provet den 26 augusti —
     det klassen redan prövats på prövas inte igen — och de två första
     lektionerna faller därför bort. */
  await expect(page.locator("#bkplanering"))
    .toHaveText("Ur planeringen: 2 lektioner, s. 7–26 — fram till provet 16 september.");
  await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
    .toMatchObject({ fran: 7, till: 26 });
});

test("dagen läraren själv väljer vinner över posten", async ({ page }) => {
  await medProvpost(page);
  await planeringen(page);
  await page.evaluate(() => window.SattLage("Prov"));
  await tillSteg(page, 4);
  await valjProvdag(page, "2026-09-08");

  /* Hennes dag stänger fönstret före den 14:e — och noten säger inte längre
     «fram till provet», för kanten är inte kalenderns. */
  await tillSteg(page, 3);
  await expect(page.locator("#bkplanering"))
    .toHaveText("Ur planeringen: 1 lektion, s. 7–12");
});

test("ett prov BAKÅT i kalendern är ingen högerkant", async ({ page }) => {
    /* Golvet för sökningen är lektionens egen dag: annars hade en lektion i
       november fått terminens första bokade prov som högerkant. */
    await medProvpost(page, { poster: [PROVPOSTER[0]] });
    await planeringen(page);                   // lektionen den 7 september
    await page.evaluate(() => window.SattLage("Prov"));
    await tillSteg(page, 3);
    // Enda posten ligger BAKÅT (26 augusti) — då gäller lektionens dag.
    await expect(page.locator("#bkplanering"))
      .toHaveText("Ur planeringen: 1 lektion, s. 7–12");
  });

test("«Komplettering och omprov» är ingen kant — åt något håll", async ({ page }) => {
  /* Omprovet är slag 'prov' i kalendern (ordet omprov), men det prövar GAMMALT
     stoff: den 2 september fick det inte avsluta sträckan (vänsterkanten är
     fortfarande provet den 26 augusti), och den 9 september fick det inte kapa
     fönstret före lektionen den 14 (högerkanten är provet den 16). */
  await medProvpost(page, { poster: [...PROVPOSTER,
    { datum: "2026-09-02", tid: "09:05–10:20", klass: "NA25", slag: "prov",
      titel: "NA25: Komplettering och omprov", kalla: "schema" },
    { datum: "2026-09-09", tid: "09:05–10:20", klass: "NA25", slag: "prov",
      titel: "NA25: Omprov kap 1", kalla: "schema" },
  ] });
  await planeringen(page);
  await page.evaluate(() => window.SattLage("Prov"));
  await tillSteg(page, 3);
  await expect(page.locator("#bkplanering"))
    .toHaveText("Ur planeringen: 2 lektioner, s. 7–26 — fram till provet 16 september.");
});

test("lärarens remsa överlever att kanten kommer ur kalendern", async ({ page }) => {
  await medProvpost(page);
  await planeringen(page);
  await page.evaluate(() => window.SattLage("Prov"));
  await tillSteg(page, 3);
  await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
    .toMatchObject({ fran: 7, till: 26 });

  await page.locator('#bkremsa .bksida[data-s="8"]').click();
  await page.locator('#bkremsa .bksida[data-s="9"]').click();
  await staller(page, { klass: "NA25", kurs: "Matematik, nivå 2c",
                        datum: "2026-08-31" });
  await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
    .toMatchObject({ fran: 8, till: 9 });
});

/* ── 4e · Kursnamnet på raderna är synkens gissning ──
 *
 * Rubriken i skolans kalender säger «nivå 2c» på en klass som läser 1c, och
 * kursfiltret tystade då hela unionen: provet fick klassprofilens gissning
 * «s. 2–5» i stället för planeringens sträcka. Klassen och fönstret är det
 * läraren själv pekat ut — etiketten är en gissning ovanpå.
 */
test("kursetiketten på raderna tystar inte klassens planering", async ({ page }) => {
  await fejka(page);
  await planeringen(page);
  // Lektionen säger 1c, raderna i kalendern är märkta 2c. Sidorna är samma.
  await staller(page, { klass: "NA25", kurs: "Matematik, nivå 1c",
                        datum: "2026-09-07" });
  await page.evaluate(() => window.SattLage("Prov"));
  await tillSteg(page, 3);
  await expect(page.locator("#bkplanering"))
    .toHaveText("Ur planeringen: 3 lektioner, s. 2–12");
});

test("en annan klass planering är fortfarande ingens", async ({ page }) => {
  /* Motstycket: klassen är det enda filtret som finns kvar, och det håller. */
  await fejka(page);
  await planeringen(page);
  await staller(page, { klass: "SA25", kurs: "Matematik, nivå 2c",
                        datum: "2026-09-07" });
  await page.evaluate(() => window.SattLage("Prov"));
  await tillSteg(page, 3);
  await expect(page.locator("#bkplanering")).toBeHidden();
});

/* ── 4f · Förvalsminnet noteras i EN bok ─────────────
 *
 * Steg 1 fylls i tur och ordning: klassen först, kursen strax efter. Mellan
 * dem satte förvalet spannet i den bok som råkade stå i dörren, och en bok
 * vars PDF saknar sina första blad KLAMPAR spannet (s. 2 blir s. 6). När
 * kursens bok sedan kom in läste förvalet skillnaden som lärarens hand — och
 * rörde aldrig spannet igen. Provet som flyttades behöll då förra fönstrets
 * sidor fast noten under remsan sa något annat.
 */
test("förvalet skriver om sitt eget spann fast boken bytts under det",
  async ({ page }) => {
    /* «Kapad bok» är en bok vars PDF saknar sina fem första blad: tryckt s. 6
       är PDF-sida 1, och uppslaget klampar därför varje spann till s. 6 och
       uppåt (se «remsan börjar där boken börjar»). */
    const KAPAD = { ...BOK_1C, namn: "Kapad bok", sidoffset: -5, sidor: 40 };
    await fejka(page, { bocker: [BOK, KAPAD] });
    await page.goto("/");
    await hydrerad(page);
    await page.getByRole("tab", { name: "Planering" }).click();
    await page.evaluate(() => window.SattLage("Prov"));
    await tillSteg(page, 3);

    // Klassen först — kursen är ännu tom, och dörren står på hyllans första bok.
    await page.evaluate(() => {
      const f = document.querySelector("#p-klass");
      if (![...f.options].some(o => o.value === "NA25" || o.textContent === "NA25")) {
        f.appendChild(Object.assign(document.createElement("option"),
                                    { textContent: "NA25" }));
      }
      f.value = "NA25";
      f.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
      .toMatchObject({ fran: 2, till: 26, bok: "Matematik 5000+ Kurs 2c" });

    /* Klassprofilens egen förvalsgest lägger kursens bok i dörren en bråkdel
       senare (profil.js anvand: `laggBok(boken)`) — och spannet klampas om.
       Det är INTE lärarens hand, och förvalet får inte tolka det så. */
    await page.evaluate(() => window.Uppslag.laggBok("Kapad bok"));
    await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
      .toMatchObject({ fran: 6, till: 26, bok: "Kapad bok" });

    // …och sedan kursen och dagen. Förvalet ska skriva om sitt eget spann.
    await staller(page, { klass: "NA25", kurs: "Matematik, nivå 1c",
                          datum: "2026-09-07" });
    await expect(page.locator("#bkplanering"))
      .toHaveText("Ur planeringen: 3 lektioner, s. 2–12");
    // Noten säger planeringens sidor, remsan bokens: s. 2 finns inte i den här.
    await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
      .toMatchObject({ fran: 6, till: 12, bok: "Kapad bok" });

    // Provet flyttas: förvalet är fortfarande sitt eget och följer med.
    await staller(page, { klass: "NA25", kurs: "Matematik, nivå 1c",
                          datum: "2026-08-31" });
    await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
      .toMatchObject({ fran: 6, till: 9 });
  });

/* ── 4c · Uppslaget överlever ett bokbyte ───────────── */

test("bokbytet ritar om båda bladen med den nya bokens id", async ({ page }) => {
  const sidbilder = [];
  await fejka(page, { bocker: HYLLAN, sidbilder });
  await planeringen(page);
  await page.evaluate(() => window.SattLage("Prov"));
  await tillSteg(page, 3);
  await page.evaluate(() => window.Kallor.satt("bok", true));
  await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
    .toMatchObject({ fran: 2, till: 12, bok: "Matematik 5000+ Kurs 2c" });
  await expect.poll(() => sidbilder.filter(x => x === "3:2").length).toBe(1);
  await expect.poll(() => sidbilder.filter(x => x === "3:12").length).toBe(1);

  // Läraren byter bok i panelen. Båda bladen ska hämtas ur den NYA boken.
  sidbilder.length = 0;
  await page.locator("#bokvalj").click();
  await page.locator(".bkbokrad", { hasText: "Exponent 1c" }).click();
  await expect.poll(() => page.evaluate(() => window.Uppslag.spann().bok))
    .toBe("Exponent 1c");
  await expect.poll(() => sidbilder.slice().sort()).toEqual(["4:12", "4:2"]);
  /* …och ingen sida ur den gamla boken. Ett halvt uppslag — ett blad ur den
     nya boken och ett ur den gamla — är precis vad läraren såg. */
  expect(sidbilder.some(x => x.startsWith("3:"))).toBe(false);
});

test("spannet klampas mot den nya bokens sista sida", async ({ page }) => {
  const sidbilder = [];
  await fejka(page, { bocker: HYLLAN, sidbilder });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await tillSteg(page, 3);
  await page.evaluate(() => window.Kallor.satt("bok", true));

  /* Ett spann långt inne i den TJOCKA boken (120 sidor) … */
  await page.evaluate(() => {
    window.Uppslag.laggBok("Matematik 5000+ Kurs 2c");
    window.Uppslag.satt(100, 110);
  });
  await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
    .toMatchObject({ fran: 100, till: 110 });

  /* … och så en bok på fyrtio sidor. Utan klampning bad uppslaget om s. 110 i
     en bok som slutar på 40: servern svarar 404, `onerror` tar bort bilden och
     bladet står tomt utan att säga varför. */
  sidbilder.length = 0;
  await page.evaluate(() => window.Uppslag.laggBok("Exponent 1c"));
  await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
    .toMatchObject({ fran: 40, till: 40, bok: "Exponent 1c" });
  /* Bladen är det som räknas — vilken sida de PEKAR på. Nätverket räcker inte
     som mätare här: en sidbild som redan hämtats en gång serveras ur webbläsarens
     cache och syns aldrig som en begäran. */
  await expect.poll(() => page.evaluate(() =>
    [...document.querySelectorAll("#bkuppslag img")].map(i => i.getAttribute("src"))))
    .toEqual(["/api/bocker/4/sida/40.png", "/api/bocker/4/sida/40.png"]);
  expect(sidbilder.every(x => Number(x.split(":")[1]) <= 40)).toBe(true);
});

test("remsan börjar där boken börjar — sidorna före pärmen finns inte",
  async ({ page }) => {
    /* Ett negativt sidoffset betyder att PDF:en saknar bokens första blad:
       tryckt s. 6 är PDF-sida 1, och s. 1–5 kan bara bli 404 och ett tomt
       blad (routes_bok.sidbild: «sidan ligger före bokens början»). */
    const KAPAD = { ...BOK_1C, namn: "Kapad bok", sidoffset: -5, sidor: 40 };
    const sidbilder = [];
    await fejka(page, { bocker: [BOK, KAPAD], sidbilder });
    await page.goto("/");
    await hydrerad(page);
    await page.getByRole("tab", { name: "Planering" }).click();
    await tillSteg(page, 3);
    await page.evaluate(() => window.Kallor.satt("bok", true));

    await page.evaluate(() => {
      window.Uppslag.laggBok("Matematik 5000+ Kurs 2c");
      window.Uppslag.satt(2, 4);
    });
    sidbilder.length = 0;
    await page.evaluate(() => window.Uppslag.laggBok("Kapad bok"));
    await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
      .toMatchObject({ fran: 6, till: 6, bok: "Kapad bok" });
    // Första knappen i remsan är s. 6, inte s. 1.
    await expect(page.locator("#bkremsa .bksida").first()).toHaveAttribute("data-s", "6");
    await expect.poll(() => page.evaluate(() =>
      [...document.querySelectorAll("#bkuppslag img")].map(i => i.getAttribute("src"))))
      .toEqual(["/api/bocker/4/sida/6.png", "/api/bocker/4/sida/6.png"]);
    expect(sidbilder.every(x => Number(x.split(":")[1]) >= 6)).toBe(true);
  });

/* ── 4b · Faktapasset väntar till skrivningen ───────── */

test("provets förval slår inte upp sidorna — passet tas när det skrivs",
  async ({ page }) => {
    /* Förvalet ur grovplaneringen öppnar bokdörren och sätter spannet — och
       panelen drog då igång faktapasset fast den är fälld: på ett riktigt
       provspann över trettio sidor är det minuters LLM-anrop för en lista
       ingen ser. Passet ska vänta till skrivningen, där servern tar det
       (routes_planning.bok_las_text) och väntan syns i molnraden. */
    /* `anrop` märker varje läsning med sitt `fran`: remsan står på prototypens
       standardspann tills förvalet skriver det, och det spannets egen läsning
       (en tavlegest, helt riktig) får inte förväxlas med provets. */
    const anrop = [];
    await fejka(page);
    await page.unroute("**/api/bocker**");
    await page.route("**/api/bocker**", route => {
      const r = route.request();
      const url = new URL(r.url());
      if (url.pathname.endsWith("/uppslag")) {
        const fran = Number(url.searchParams.get("fran"));
        const till = Number(url.searchParams.get("till"));
        anrop.push(`uppslag:${fran}`);
        // Provspannet (2–12) är oläst: det är precis läget som drog igång
        // läsningen. Alla andra spann svarar lästa och tysta.
        const olast = fran === 2;
        return route.fulfill({ status: 200, contentType: "application/json",
          body: JSON.stringify({ fran, till, uppgifter: [],
                                 olasta: olast ? [2, 3] : [],
                                 utan_fakta: olast ? [2, 3] : [],
                                 sidor: [] }) });
      }
      if (url.pathname.endsWith("/las")) {
        anrop.push(`las:${(r.postDataJSON() || {}).fran}`);
        return route.fulfill({ status: 200, contentType: "text/event-stream",
          body: strom([{ type: "done",
                         result: { uppgifter: UPPG, lasta: 0 } }]) });
      }
      return route.fulfill({ status: 200, contentType: "application/json",
                             body: JSON.stringify({ bocker: [BOK] }) });
    });
    await planeringen(page);
    await page.evaluate(() => window.SattLage("Prov"));
    await tillSteg(page, 3);
    await expect(page.locator("#bkplanering")).toBeVisible();

    // Uppslaget frågades — men läsningen begärdes aldrig.
    await expect.poll(() => anrop.includes("uppslag:2")).toBe(true);
    await page.waitForTimeout(1000);
    expect(anrop.filter(a => a === "las:2").length).toBe(0);

    /* Tillbaka till lektionsmaterialet: panelen är uppe igen och behöver sina
       uppgifter — nu ska passet tas direkt, inte förbli hoppat. */
    await page.evaluate(() => window.SattLage("Tavla"));
    await expect.poll(() => anrop.filter(a => a === "las:2").length,
                      { timeout: 15_000 }).toBe(1);
  });

/* ── 5 · Antalet uppgifter ──────────────────────────── */

const antalet = page => page.locator('.typrad[data-id="antal"] .steppervarde');
const stepp = (page, riktning) =>
  page.locator(`.typrad[data-id="antal"] [data-steg="${riktning}"]`);

test("provets antal går från tre till tjugo — och säger varför vid kanten",
  async ({ page }) => {
    await fejka(page);
    await page.goto("/");
    await hydrerad(page);
    await page.getByRole("tab", { name: "Planering" }).click();
    await page.evaluate(() => window.SattLage("Prov"));
    await tillSteg(page, 4);

    // Standarden rörs inte: sex uppgifter, som förut.
    await expect(antalet(page)).toHaveText("6");
    await expect(page.locator('.typrad[data-id="antal"] .typnot')).toBeHidden();

    /* Ner till golvet. Det gamla golvet var 4 — nu ska tre gå, och raden ska
       säga vad kanten är i stället för att bara ta emot. */
    for (let i = 0; i < 5; i++) await stepp(page, "-1").click();
    await expect(antalet(page)).toHaveText("3");
    await expect(page.locator('.typrad[data-id="antal"] .typnot'))
      .toContainText("Färre än tre går inte att balansera");

    // Och upp till taket: 20, långt över de gamla tolv.
    for (let i = 0; i < 30; i++) await stepp(page, "1").click();
    await expect(antalet(page)).toHaveText("20");
    await expect(page.locator('.typrad[data-id="antal"] .typnot'))
      .toContainText("Tjugo är appens tak");
  });

test("antalet läraren satte är det som skickas", async ({ page }) => {
  const anrop = await fejka(page);
  // Boken ger momentet, som knappen kräver — samma väg som läraren går.
  await medBoken(page, "Prov");
  await tillSteg(page, 4);
  for (let i = 0; i < 9; i++) await stepp(page, "1").click();
  await expect(antalet(page)).toHaveText("15");
  await page.locator("#skriv").click();

  await expect.poll(() => anrop.length).toBe(1);
  expect(anrop[0].antal).toBe(15);
});

/* ── 6 · Hjälpmedlen ur kalendern ───────────────────── */

const delprovet = page =>
  page.locator('.typrad[data-id="delprov"] [aria-pressed="true"]');
const delprovnot = page => page.locator('.typrad[data-id="delprov"] .typnot');

/** Samma sidor, bara en annan hjälpmedelsflagga per lektion. */
const medHjalpmedel = flaggor => INNEHALL.map((i, n) =>
  flaggor[n] === undefined ? i : { ...i, hjalpmedel: flaggor[n] });

async function medPlanering(page, innehall) {
  await page.route("**/api/schema", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ ...SCHEMA, innehall }) }));
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await staller(page, { klass: "NA25", kurs: "Matematik, nivå 2c",
                        datum: "2026-09-07" });
  await page.evaluate(() => window.SattLage("Prov"));
  await tillSteg(page, 4);
}

test("datorn i planeringen föreslår Del B + Del C", async ({ page }) => {
  await fejka(page);
  await medPlanering(page, medHjalpmedel(["dator", "", "raknare"]));
  await expect(delprovet(page)).toHaveText("Del B + Del C");
  await expect(delprovnot(page))
    .toHaveText("Dator eller räknare står på 2 av 3 lektioner i planeringen.");
});

test("papper och penna hela vägen föreslår En del", async ({ page }) => {
  await fejka(page);
  await medPlanering(page, medHjalpmedel(["", "", ""]));
  await expect(delprovet(page)).toHaveText("En del");
  await expect(delprovnot(page))
    .toHaveText("Inga digitala verktyg i planeringens 3 lektioner.");
});

test("osynkade rader påstår ingenting — standarden står kvar", async ({ page }) => {
  await fejka(page);
  // Ingen rad bär nyckeln: basen är skriven före v21 och ingen har läst dem med
  // hjälpmedelsögon. Då ska appen tiga, inte säga «inga digitala verktyg».
  await medPlanering(page, INNEHALL);
  await expect(delprovet(page)).toHaveText("Del B + Del C");   // standarden
  await expect(delprovnot(page)).toHaveCount(0);
});

test("förvalet är ett förslag — läraren byter fritt", async ({ page }) => {
  await fejka(page);
  await medPlanering(page, medHjalpmedel(["dator", "dator", "dator"]));
  await expect(delprovet(page)).toHaveText("Del B + Del C");
  await page.locator('.typrad[data-id="delprov"] button', { hasText: "En del" })
    .click();
  await expect(delprovet(page)).toHaveText("En del");
  // Grunden står kvar och säger varför förslaget var det andra.
  await expect(delprovnot(page)).toContainText("Dator eller räknare står på 3");
});
