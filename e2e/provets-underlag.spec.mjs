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

const SCHEMA = { schema: [], lov: [], poster: [], innehall: [] };

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
async function fejka(page) {
  const anrop = [];
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
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
