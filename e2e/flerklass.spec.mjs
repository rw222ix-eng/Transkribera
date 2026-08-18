import { expect, test } from "@playwright/test";

/* FLERKLASSKÖN — det som gör appen till en LÄRARES app
 *
 * En gymnasielärare planerar sällan en lektion. Hon planerar torsdagen: NA25
 * klockan nio, TE25 klockan elva, NA24 efter lunch. Kön är därför inte en
 * bekvämlighet utan hela arbetsflödet — och den farligaste buggen i den är
 * tyst: att något från förra klassen följer med in i nästa dokument. Förlagan,
 * det centrala innehållet och boksidorna pekar då på fel kurs, och pappret som
 * skrivs ut ser alldeles rimligt ut.
 *
 * Kontraktet (app/web/ui/plankon.js):
 *   1. Klicket ÄR valet, flera lektioner går bra, också över klassgränsen.
 *   2. Kön är sorterad på datum + tid, oavsett klickordning.
 *   3. Vid byte till en annan KURS nollas moment, förlaga, Gy25-val och
 *      boköppning. Är kursen densamma följer boköppningen med.
 *   4. Kön avancerar på GODKÄNNANDE, inte på ett utkast.
 */

const SCHEMA = {
  schema: [
    // Torsdag (dag 4): tre lektioner, två klasser, två kurser.
    { dag: 4, tid: "09:05–10:20", kurs: "Matematik, nivå 2c", klass: "NA25", sal: "P807" },
    { dag: 4, tid: "11:00–12:15", kurs: "Matematik, nivå 1c", klass: "TE25", sal: "I210" },
    { dag: 4, tid: "13:10–14:25", kurs: "Matematik, nivå 2c", klass: "NA25", sal: "P807" },
  ],
  lov: [],
  poster: [],
};

const json = (route, kropp) => route.fulfill({
  status: 200, contentType: "application/json", body: JSON.stringify(kropp) });

async function fejka(page) {
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/bocker", route => json(route, []));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.PlanKo);

/** Öppnar planeringen i en vecka med lektioner (klockan fryst på en torsdag). */
async function planeringen(page) {
  await fejka(page);
  await page.clock.install({ time: new Date("2026-09-08T08:00:00") });  // tisdag v37
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await expect(page.locator("#schemagrid .lekt")).toHaveCount(3);
}

/** Klickar lektionskorten i angiven ordning (index i veckans rutnät). */
async function valj(page, ...index) {
  for (const n of index) {
    await page.locator("#schemagrid .lekt").nth(n).click();
  }
}

test("flera lektioner över klassgränsen blir en kö i tidsordning", async ({ page }) => {
  await planeringen(page);
  // Klicka i FEL ordning: sist först. Kön ska ändå gå i tidsordning.
  await valj(page, 2, 0, 1);

  const valda = await page.evaluate(() => window.PlanKo.valda());
  expect(valda.map(p => `${p.klass} ${p.tid}`)).toEqual([
    "NA25 09:05–10:20", "TE25 11:00–12:15", "NA25 13:10–14:25",
  ]);
  await expect(page.locator("#planvald")).toContainText("3 lektioner valda");
});

test("ett klick till på en vald lektion tar bort den ur kön", async ({ page }) => {
  await planeringen(page);
  await valj(page, 0, 1);
  await expect.poll(() => page.evaluate(() => window.PlanKo.valda().length)).toBe(2);
  await valj(page, 1);
  const valda = await page.evaluate(() => window.PlanKo.valda());
  expect(valda.map(p => p.klass)).toEqual(["NA25"]);
});

test("kursbyte i kön nollar allt som hörde till förra klassen", async ({ page }) => {
  await planeringen(page);
  await valj(page, 0, 1);                 // NA25 (Ma2c) → TE25 (Ma1c)

  // Planera den första: boken slås upp FÖRST (spannet skriver momentfältet —
  // «spannet ÄR momentet», uppslag.js), och sedan skriver läraren sitt eget
  // moment ovanpå.
  await page.evaluate(() => {
    window.PlanKo.starta();
    window.Uppslag && window.Uppslag.satt(210, 217);
    const m = document.querySelector("#moment");
    m.value = "4.2 Logaritmlagar";
    m.dispatchEvent(new Event("input", { bubbles: true }));
    window.GyVal && window.GyVal.lagg && window.GyVal.lagg("Logaritmer");
  });
  const fore = await page.evaluate(() => ({
    moment: document.querySelector("#moment").value,
    spann: window.Uppslag ? window.Uppslag.spann() : null,
    gy: window.GyVal && window.GyVal.valda ? window.GyVal.valda().length : 0,
  }));
  expect(fore.moment).toContain("Logaritmlagar");

  await page.evaluate(() => window.PlanKo.nasta());

  const efter = await page.evaluate(() => ({
    moment: document.querySelector("#moment").value,
    klass: document.querySelector("#p-klass").value,
    kurs: document.querySelector("#p-kurs").value,
    spann: window.Uppslag ? window.Uppslag.spann() : null,
    gy: window.GyVal && window.GyVal.valda ? window.GyVal.valda().length : 0,
    forlaga: window.Dokument && window.Dokument.forlaga ? !!window.Dokument.forlaga() : false,
  }));
  /* Kursen bytte. Ingenting från förra lektionen får stå kvar — fälten nollas
     och sätts om ur den NYA klassens profil (plankon.js nasta). Det som skulle
     vara en tyst katastrof är motsatsen: att «4.2 Logaritmlagar» och sidorna
     210–217 ur Ma2c-boken följer med in i TE25:s Ma1c-dokument. */
  expect(efter.klass).toBe("TE25");
  expect(efter.moment).not.toContain("Logaritmlagar");
  expect(efter.spann.fran).not.toBe(fore.spann.fran);
  expect(efter.gy).toBe(0);
  expect(efter.forlaga).toBe(false);
});

test("samma kurs igen behåller boköppningen", async ({ page }) => {
  await planeringen(page);
  await valj(page, 0, 2);                 // NA25 → NA25, samma kurs

  await page.evaluate(() => {
    window.PlanKo.starta();
    window.Uppslag && window.Uppslag.satt(210, 217);
    const m = document.querySelector("#moment");
    m.value = "4.2 Logaritmlagar";
    m.dispatchEvent(new Event("input", { bubbles: true }));
  });
  const fore = await page.evaluate(() => window.Uppslag.spann());
  await page.evaluate(() => window.PlanKo.nasta());
  const efter = await page.evaluate(() => window.Uppslag.spann());

  expect(efter.bok).toBe(fore.bok);
  expect(efter.fran).toBe(fore.fran);
  expect(efter.till).toBe(fore.till);
  /* Lärarens EGNA moment följer däremot aldrig med. Det som står i fältet är
     uppslagets egen text — «spannet ÄR momentet» — härlett ur boken som
     fortfarande är öppen, inte den förra lektionens rubrik. */
  const moment = await page.evaluate(() => document.querySelector("#moment").value);
  expect(moment).not.toContain("Logaritmlagar");
  expect(moment).toContain("210");
});

test("kön står kvar när man byter vecka mitt i", async ({ page }) => {
  await planeringen(page);
  await valj(page, 0, 1);
  await page.evaluate(() => window.PlanKo.starta());
  const nu = await page.evaluate(() => window.PlanKo.aktiv());

  await page.locator("#schemafram").click();
  await expect(page.locator("#schemavecka")).toHaveText("Vecka 38");

  expect(await page.evaluate(() => window.PlanKo.aktiv())).toEqual(nu);
  expect(await page.evaluate(() => window.PlanKo.harFler())).toBe(true);
});

test("veckan visar var i kön man står — vald, nu och klar", async ({ page }) => {
  await planeringen(page);
  await valj(page, 0, 1);
  await page.evaluate(() => window.PlanKo.starta());

  const lagen = await page.evaluate(() => {
    const p = window.PlanKo.valda();
    return { nu: window.PlanKo.arNu(p[0]), nasta: window.PlanKo.arNu(p[1]) };
  });
  expect(lagen).toEqual({ nu: true, nasta: false });

  await page.evaluate(() => window.PlanKo.nasta());
  const efter = await page.evaluate(() => {
    const p = window.PlanKo.valda();
    return { forra: window.PlanKo.arNu(p[0]), nu: window.PlanKo.arNu(p[1]) };
  });
  expect(efter).toEqual({ forra: false, nu: true });
});

/* Kalendern läses om medan kön står kvar: rutan som var «Matematik, nivå 2c»
   när man klickade är «Matematik, nivå 1c» nästa gång veckan ritas. Posten i kön
   är då ÄLDRE än schemat — och eftersom nyckeln bär kursen kände veckan inte
   igen sitt eget kort. Ett nytt klick la in samma lektion en gång till, den
   gamla sorterades först (samma dag och timme sorterar lika) och blev den som
   planerades. Följderna var tysta: remsan sa en kurs klassen inte läser, boken
   föll tillbaka på minnets, och kalenderns sidor för dagen hittades inte alls —
   innehallFor slår på kursen. Schemat äger kursen (plankon.js farsk). */
test("en post som blivit äldre än schemat rättas mot schemat — inte dubblerad", async ({ page }) => {
  await planeringen(page);

  // Så såg rutan ut före omsynken: samma dag, klass och timme, annan kurs.
  await page.evaluate(() => window.PlanKo.vaxla({
    datum: "2026-09-10", tid: "11:00–12:15", kurs: "Matematik, nivå 2c",
    klass: "TE25", sal: "I210",
  }));

  expect(await page.evaluate(() => window.PlanKo.valda().map(p => p.kurs)))
    .toEqual(["Matematik, nivå 1c"]);
  expect(await page.evaluate(() => document.querySelector("#p-kurs").value))
    .toBe("Matematik, nivå 1c");
  await expect(page.locator("#schemagrid .lekt").nth(1)).toHaveAttribute("data-vald", "");

  // Kortet är sin egen lektion: klicket tar bort den ur kön, dubblerar den inte.
  await valj(page, 1);
  expect(await page.evaluate(() => window.PlanKo.valda().length)).toBe(0);
});
