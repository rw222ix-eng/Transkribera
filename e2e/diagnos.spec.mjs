import { expect, test } from "@playwright/test";

/* DIAGNOSEN — HELA KURSENS INNEHÅLL PÅ EN LEKTION
 *
 * Diagnosen är den enda dokumenttypen där antalet uppgifter INTE är ett val.
 * Två saker är givna — hela kursens centrala innehåll och lektionens längd —
 * och servern räknar resten (exam_spec.diagnosplan). Det ställer tre krav på
 * gränssnittet som ingen annan typ ställer:
 *
 *   1. Väljs typen kryssas HELA nivåns centrala innehåll i. En diagnos med
 *      halva kursen kryssad är inte en diagnos, och att kryssa 21 rutor för
 *      hand är inte en väg.
 *   2. Anropet bär KODERNA (G25-…) och ingen `antal` — skickade frontenden ett
 *      antal skulle den bestämma något den inte vet.
 *   3. Tiden går båda vägarna: läraren sätter ramen, servern svarar med hur
 *      lång diagnosen faktiskt blev.
 */

const SCHEMA = {
  schema: [{ dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 1c",
             klass: "NA25", sal: "P807" }],
  lov: [], poster: [],
};

/* Prov-JSON som app/exam_spec.py definierar den — diagnosens form: platt (inga
   delar), E-tyngd, och varje uppgift taggad med sina innehållskoder. */
const DIAGNOS = {
  titel: "Diagnos · Matematik 1c",
  kurs: "Matematik, nivå 1c", klass: "NA25", datum: "2026-09-03", tid_min: 60,
  hjalpmedel: "Formelblad och digitala verktyg",
  uppgifter: [
    { del: null, formaga: "B", typ: "rutin", poang: [2, 0, 0],
      text: "Förenkla $2x + 3x$.", losning: "$5x$",
      bedomning: "+2 E korrekt förenkling.",
      innehall: ["G25-M1C-ALG-1", "G25-M1C-ALG-2"] },
    { del: null, formaga: "P", typ: "rutin", poang: [2, 0, 0],
      text: "Lös ekvationen $3x - 7 = 8$.", losning: "$x = 5$",
      bedomning: "+2 E korrekt lösning.",
      innehall: ["G25-M1C-ALG-5"] },
    { del: null, formaga: "R", typ: "resonemang", poang: [0, 2, 0],
      text: "Avgör om $2^x$ växer snabbare än $x^2$. Motivera.",
      losning: "Ja, för stora $x$.", bedomning: "+2 C jämförelse och motivering.",
      innehall: ["G25-M1C-ALG-7"] },
  ],
};

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

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
  await page.route("**/api/exams/**", route => {
    const vag = new URL(route.request().url()).pathname;
    anrop.push({ vag, kropp: route.request().postDataJSON() });
    if (vag.endsWith("/approve")) {
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "done", result: {
          id: 11, pdf: "C:/Transkriberingar/prov/diagnos.pdf",
          tex: "C:/Transkriberingar/prov/diagnos.tex", errors: [] } }]) });
    }
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([
        { type: "log", msg: "Skriver diagnosen …" },
        { type: "done", result: {
          id: 11, exam: DIAGNOS, typ: "diagnos", status: "utkast",
          errors: [], rounds: 1, tid: 55,
          summor: { total: 6, e: 4, c: 2, a: 0 } } },
      ]) });
  });
  return anrop;
}

async function planera(page, typ, moment) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(([t, m]) => {
    window.SattLage(t);
    const satt = (id, v) => {
      const e = document.querySelector(id);
      e.value = v;
      e.dispatchEvent(new Event("change", { bubbles: true }));
    };
    satt("#p-kurs", "Matematik, nivå 1c");
    satt("#p-klass", "NA25");
    const f = document.querySelector("#moment");
    f.value = m;
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  }, [typ, moment]);
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

test("diagnosen kryssar i hela nivåns centrala innehåll", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await planera(page, "Diagnos", "hela kursen");

  const { valda, alla } = await page.evaluate(() => ({
    valda: window.GyVal.valda().length,
    alla: window.Gy.punkter(window.GyVal.niva()).length,
  }));
  expect(alla).toBe(21);                       // Ma1c enligt gy25_ma1c.json
  expect(valda).toBe(alla);
});

test("anropet bär koderna och överlåter antalet till servern", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await planera(page, "Diagnos", "hela kursen");
  await page.locator("#skriv").click();
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  const gen = anrop.find(a => a.vag.endsWith("/generate"));
  expect(gen.kropp.typ).toBe("diagnos");
  expect(gen.kropp.antal).toBeUndefined();
  expect(gen.kropp.tid_min).toBe(60);
  expect(gen.kropp.delar).toBe(false);
  expect(gen.kropp.punkter).toHaveLength(21);
  expect(gen.kropp.punkter.every(k => k.startsWith("G25-M1C-"))).toBe(true);
});

test("serverns tid står kvar som besked — diagnosen skrevs för att rymmas", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await planera(page, "Diagnos", "hela kursen");
  await page.locator("#skriv").click();
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
  /* Statusraden töms när pappret ritas (plan.js efterKlar) — beskedet om tiden
     måste alltså överleva den, annars ser läraren aldrig svaret på frågan hon
     ställde när hon satte ramen. */
  await expect(page.locator(".toast").last())
    .toContainText("ca 55 min av dina 60", { timeout: 15_000 });
});

test("uppgifternas centrala innehåll följer med ner på pappret", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await planera(page, "Diagnos", "hela kursen");
  await page.locator("#skriv").click();
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  /* `ci` är koderna som når rättningen (app/rattning.py bygg). Tappas de här
     kan CI-profilen aldrig räknas — och det syns först flera veckor senare.
     Godkännandet lägger pappret i Sparat, och DÄR ligger uppgifterna som de
     kommer att läsas när diagnosen ska rättas. */
  await page.locator("#godkann").click();
  await expect.poll(() => page.evaluate(
    () => window.Dokument.sparade().length), { timeout: 15_000 }).toBeGreaterThan(0);
  const listan = await page.evaluate(() =>
    window.Dokument.sparade()[0].uppgifter.map(u => u.ci));
  expect(listan).toEqual([
    ["G25-M1C-ALG-1", "G25-M1C-ALG-2"], ["G25-M1C-ALG-5"], ["G25-M1C-ALG-7"],
  ]);
});

test("diagnosen bär sin rättning i samma dokument", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await planera(page, "Diagnos", "hela kursen");
  await page.locator("#skriv").click();
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  /* Två ark: elevens och facit. Arbetsbladet får sitt facit bara när läraren
     valt det; diagnosen har det alltid, för det är rättningsbladet. */
  await expect(page.locator("#arkskal .gu")).toHaveCount(1);
  await expect(page.locator('#arkskal .ark[data-form="fa"]')).toHaveCount(1);
  await expect(page.locator("#arkskal .guband").first())
    .toContainText("sätter inget betyg");
});
