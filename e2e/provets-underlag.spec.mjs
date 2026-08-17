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

/** Fejkar datagrunden, hyllan och generatorrutten. `anrop` samlar kropparna. */
async function fejka(page, { sparade = [] } = {}) {
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
    return json(route, { bocker: [BOK] });
  });
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

test("datorn i planeringen föreslår Del A + Del B", async ({ page }) => {
  await fejka(page);
  await medPlanering(page, medHjalpmedel(["dator", "", "raknare"]));
  await expect(delprovet(page)).toHaveText("Del A + Del B");
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
  await expect(delprovet(page)).toHaveText("Del A + Del B");   // standarden
  await expect(delprovnot(page)).toHaveCount(0);
});

test("förvalet är ett förslag — läraren byter fritt", async ({ page }) => {
  await fejka(page);
  await medPlanering(page, medHjalpmedel(["dator", "dator", "dator"]));
  await expect(delprovet(page)).toHaveText("Del A + Del B");
  await page.locator('.typrad[data-id="delprov"] button', { hasText: "En del" })
    .click();
  await expect(delprovet(page)).toHaveText("En del");
  // Grunden står kvar och säger varför förslaget var det andra.
  await expect(delprovnot(page)).toContainText("Dator eller räknare står på 3");
});
