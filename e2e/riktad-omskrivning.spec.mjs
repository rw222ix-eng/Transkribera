import { expect, test } from "@playwright/test";
import { forbiNivavarningen } from "./larardag.mjs";

/* RIKTAD OMSKRIVNING — MÅLET ÄR SPELPLANEN
 *
 * Läraren pekade på uppgift D och bad «ta bort deluppgift b)». Modellen skrev
 * om ALLA fyra uppgifterna och bytte sammanhanget — bygg blev pizza — trots
 * promptens «Övriga uppgifter lämnas oförändrade». Hon fick ångra varvet.
 *
 * Servern håller numera löftet själv: pekade läraren på något avgränsat byggs
 * svaret som originalet plus kandidatens ändring av just det målet
 * (exam_gen.riktat_mal/sammanfoga_riktat, låst av tests/test_exam.py och
 * tests/test_routes_exam.py). Här prövas de två halvorna som bara syns i
 * gränssnittet:
 *
 *   1. Klienten skickar `mal.el`. Utan elementets id kan servern inte veta vad
 *      önskemålet avgränsar — namnet är till för prompten, id:t för servern.
 *   2. Pappret visar att bara målet ändrades, och panelen märker den rutan
 *      ensam. Modellen «råkar» skriva om allt i fejksvaret nedan; det som når
 *      pappret är vad servern släppte igenom.
 */

const SCHEMA = {
  schema: [{ dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 2c",
             klass: "NA25", sal: "P807" }],
  lov: [], poster: [],
};

const uppgift = (bokstav, text) => ({
  del: "C", formaga: "PL", typ: "problem", poang: [2, 1, 0],
  text, losning: `Svaret till ${bokstav}.`, bedomning: "+2 E, +1 C.",
});

/* Fyra uppgifter i samma sammanhang — bygget. Det är dem läraren känner igen. */
const EXAM = {
  titel: "Gruppuppgift · Skala och proportion",
  kurs: "Matematik, nivå 2c", klass: "NA25", datum: "2026-09-03", tid_min: 60,
  hjalpmedel: "Formelblad och miniräknare.",
  uppgifter: [
    uppgift("A", "På bygget blandas betong i förhållandet 1:3."),
    uppgift("B", "I verkstaden byggs en ramp med lutningen 1:12."),
    uppgift("C", "Ritningen har skalan 1:50. Bestäm rummets verkliga area."),
    uppgift("D", "Takstolarna sitter med 1,2 m mellanrum över 9 m."),
  ],
};

/* Det servern släpper igenom när läraren pekat på uppgift D: originalet, med
   ENBART uppgift 4 omskriven. Modellens övriga pizzor slängdes. */
const EFTER = {
  ...EXAM,
  uppgifter: EXAM.uppgifter.map((u, i) => i === 3
    ? { ...u, text: "Takstolarna sitter med 1,2 m mellanrum över 12 m." }
    : u),
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
  await page.route("**/api/planning/**", route => json(route, { ok: true }));
  await page.route("**/api/exams/**", route => {
    const vag = new URL(route.request().url()).pathname;
    anrop.push({ vag, kropp: route.request().postDataJSON() });
    const svar = vag.endsWith("/refine")
      /* `andrade` är serverns egen diff mot det som faktiskt sparades — och
         den blir ärlig av sig själv när sammanfogningen är det som sparas. */
      ? { id: 9, exam: EFTER, typ: "prov", status: "utkast", errors: [],
          rounds: 1, andrade: ["uppg4"] }
      : { id: 9, exam: EXAM, typ: "prov", status: "utkast", errors: [],
          rounds: 1, granser: { E: 4, C: 7, A: 9 }, summor: { totalt: 12 } };
    return route.fulfill({ status: 200, contentType: "text/event-stream",
                           body: strom([{ type: "done", result: svar }]) });
  });
  return anrop;
}

async function skrivProv(page) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => {
    window.SattLage("Prov");
    const satt = (id, v) => {
      const e = document.querySelector(id);
      e.value = v;
      e.dispatchEvent(new Event("change", { bubbles: true }));
    };
    satt("#p-kurs", "Matematik, nivå 2c");
    satt("#p-klass", "NA25");
    const f = document.querySelector("#moment");
    f.value = "skala och proportion";
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  });
  await page.locator("#skriv").click();
  await forbiNivavarningen(page);
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
}

async function oppnaCanvas(page) {
  await page.locator("#granska").click();
  await expect(page.locator("#g-falt")).toBeVisible({ timeout: 10_000 });
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

const markerade = page => page.evaluate(() => Array.from(
  document.querySelectorAll("#granskaskal .gdok .andrad, #arkskal .andrad"),
  el => el.dataset.el).filter(Boolean));

test("elementets id följer med — servern ska veta vad önskemålet avgränsar",
  async ({ page }) => {
    const anrop = await fejka(page);
    await page.goto("/");
    await hydrerad(page);
    await skrivProv(page);
    await oppnaCanvas(page);

    await page.locator("#g-valj").click();
    const mal = page.locator("#granskaskal .gdok [data-el='uppg4']").first();
    await mal.click();
    await page.locator("#g-falt").fill("Ta bort deluppgift b)");
    await page.locator("#g-form").evaluate(f => f.requestSubmit());

    await expect.poll(() => anrop.some(a => a.vag.endsWith("/refine")),
                      { timeout: 20_000 }).toBe(true);
    const kropp = anrop.find(a => a.vag.endsWith("/refine")).kropp;
    /* Numret är den precisare vägen och har funnits — id:t är det nya, och det
       är det som bär de mål som INTE är uppgifter (sidhuvudet, bandet). */
    expect(kropp.nummer).toBe(4);
    expect(kropp.mal.el).toBe("uppg4");
  });

test("bara målet ändras på pappret, och panelen märker den rutan ensam",
  async ({ page }) => {
    await fejka(page);
    await page.goto("/");
    await hydrerad(page);
    await skrivProv(page);
    await oppnaCanvas(page);

    await page.locator("#g-valj").click();
    await page.locator("#granskaskal .gdok [data-el='uppg4']").first().click();
    await page.locator("#g-falt").fill("Ta bort deluppgift b)");
    await page.locator("#g-form").evaluate(f => f.requestSubmit());
    await expect(page.locator("#g-antal")).toHaveText("1 ändring", { timeout: 20_000 });

    /* De tre andra uppgifterna står kvar ORDAGRANT — inga pizzor. Det var det
       som gick sönder: läraren fick ett helt nytt papper av ett önskemål om en
       deluppgift. */
    const arket = page.locator("#granskaskal .gdok .pruppg");
    await expect(arket.nth(0)).toContainText("betong i förhållandet 1:3");
    await expect(arket.nth(1)).toContainText("ramp med lutningen 1:12");
    await expect(arket.nth(2)).toContainText("skalan 1:50");
    await expect(arket.nth(3)).toContainText("över 12 m");
    await expect(page.locator("#granskaskal .gdok")).not.toContainText("pizzeria");

    await expect.poll(() => markerade(page), { timeout: 20_000 })
      .toEqual(expect.arrayContaining(["uppg4"]));
    const marks = await markerade(page);
    expect(marks).not.toContain("uppg1");
    expect(marks).not.toContain("uppg2");
    expect(marks).not.toContain("uppg3");
  });
