import { expect, test } from "@playwright/test";

/* RIKTADE ARBETSBLAD — ETT TILL KLASSEN, ETT TILL ALVA
 *
 * Ett arbetsblad har alltid varit klassens. Etapp 4 gör det möjligt att skriva
 * ett till EN elev, ur hennes CI-profil, på samma lektion som klassens. Tre
 * saker måste hålla i gränssnittet:
 *
 *   1. Mottagarna är flera. Väljs klassen OCH en elev skrivs två blad — ett i
 *      taget, för läraren ska läsa igenom vart och ett.
 *   2. Elevens punkter kryssas för av sig själva ur profilen, och «stötta» och
 *      «utmana» plockar motsatta ändar av den.
 *   3. Namnet följer med hela vägen: på pappret, i dokumentets namn och i
 *      klassvyns remsa — annars går två blad på samma lektion inte att skilja.
 */

const SCHEMA = {
  schema: [{ dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 1c",
             klass: "NA25", sal: "P807" }],
  lov: [], poster: [],
};

const ELEVER = [{ id: 11, namn: "Alva Nyström", sort: 0, aktiv: true },
                { id: 12, namn: "Elis Hedlund", sort: 1, aktiv: true }];

/* Profilen som app/ci_profil.py räknar den: svagast först. */
const PROFIL = {
  elev_id: 11, dokument: 2, utan_ci: 0, matt: true,
  punkter: [
    { kod: "G25-M1C-ALG-5", kort: "Linjära ekvationer", andel: 0.2,
      styrka: "svag", dokument: 2, niva: {} },
    { kod: "G25-M1C-ALG-1", kort: "Formler och uttryck", andel: 0.95,
      styrka: "stark", dokument: 2, niva: {} },
  ],
};

const BLAD = elev => ({
  titel: "Arbetsblad · Linjära ekvationer",
  kurs: "Matematik, nivå 1c", klass: "NA25", elev: elev || null,
  datum: "2026-09-03", hjalpmedel: "Formelblad",
  uppgifter: [
    { del: null, formaga: "P", typ: "rutin", poang: [2, 0, 0],
      text: "Lös $3x - 7 = 8$.", losning: "$x = 5$", bedomning: "+2 E",
      innehall: ["G25-M1C-ALG-5"] },
    { del: null, formaga: "B", typ: "rutin", poang: [3, 0, 0],
      text: "Ange lutningen.", losning: "$2$", bedomning: "+3 E",
      innehall: ["G25-M1C-ALG-5"] },
  ],
});

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
  await page.route("**/api/groups", route => json(route, [{ id: 1, namn: "NA25" }]));
  await page.route("**/api/groups/*/elever", route => json(route, { elever: ELEVER }));
  await page.route("**/ci-profil*", route => json(route, PROFIL));
  await page.route("**/api/exams/**", route => {
    const vag = new URL(route.request().url()).pathname;
    const kropp = route.request().postDataJSON();
    anrop.push({ vag, kropp });
    if (vag.endsWith("/approve")) {
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "done", result: { id: 7, pdf: "x.pdf", tex: "x.tex", errors: [] } }]) });
    }
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: 7, exam: BLAD(kropp && kropp.elev), typ: "arbetsblad",
        status: "utkast", errors: [], rounds: 1,
        summor: { total: 5, e: 5, c: 0, a: 0 } } }]) });
  });
  return anrop;
}

async function planera(page) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => {
    window.SattLage("Arbetsblad");
    const satt = (id, v) => {
      const e = document.querySelector(id);
      e.value = v;
      e.dispatchEvent(new Event("change", { bubbles: true }));
    };
    satt("#p-kurs", "Matematik, nivå 1c");
    satt("#p-klass", "NA25");
    const f = document.querySelector("#moment");
    f.value = "linjära ekvationer";
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  });
}

/** Väljer en elev som mottagare via panelen — samma väg läraren går. */
async function valjElev(page, namn) {
  await page.locator('.typrad[data-id="mottagare"] .tkvalj').click();
  await page.locator('.typmottagare .lrad-val', { hasText: namn }).click();
  await page.keyboard.press("Escape");
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

test("mottagaren är hela klassen tills en elev väljs", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await planera(page);

  const chips = page.locator('.typrad[data-id="mottagare"] .lchip');
  await expect(chips).toHaveCount(1);
  await expect(chips.first()).toContainText("Hela klassen");
  // Riktningen frågas inte förrän det finns någon att rikta bladet mot.
  await expect(page.locator('.typrad[data-id="syfte"]')).toHaveCount(0);

  await valjElev(page, "Alva Nyström");
  await expect(page.locator('.typrad[data-id="mottagare"] .lchip')).toHaveCount(2);
  await expect(page.locator('.typrad[data-id="syfte"]')).toHaveCount(1);
});

test("elevens svaga punkter kryssas för ur profilen", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await planera(page);
  await valjElev(page, "Alva Nyström");

  /* «Stötta» är förvalet: bladet handlar om det hon INTE kan. Kryssen kommer ur
     profilen, inte ur en gissning om kursen. */
  await expect.poll(() => page.evaluate(() => window.GyVal.valda()),
                    { timeout: 15_000 }).toEqual(["Linjära ekvationer"]);

  // Utmana plockar andra änden av samma profil.
  await page.locator('[data-seg="tv-syfte"] button', { hasText: "Utmana" }).click();
  await expect.poll(() => page.evaluate(() => window.GyVal.valda()),
                    { timeout: 15_000 }).toEqual(["Formler och uttryck"]);
});

test("två mottagare ger två blad — ett i taget", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await planera(page);
  await valjElev(page, "Alva Nyström");
  await expect(page.locator('.typrad[data-id="mottagare"] .typnot'))
    .toContainText("2 blad skrivs");

  // Första bladet är klassens: inget elev_id i anropet.
  await page.locator("#skriv").click();
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
  const forsta = anrop.filter(a => a.vag.endsWith("/generate")).at(-1);
  expect(forsta.kropp.elev_id).toBeUndefined();

  /* Godkännandet är grinden: nästa blad erbjuds först när det här ligger i
     Sparat. Momentet står kvar — det är samma lektion. */
  await page.locator("#godkann").click();
  await expect(page.locator("#bladkorad"))
    .toContainText("Arbetsblad till Alva Nyström väntar", { timeout: 15_000 });
  await expect(page.locator("#moment")).toHaveValue("linjära ekvationer");

  await page.locator("#bladkogor").click();
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
  const andra = anrop.filter(a => a.vag.endsWith("/generate")).at(-1);
  expect(andra.kropp.elev_id).toBe(11);
  expect(andra.kropp.elev).toBe("Alva Nyström");
  expect(andra.kropp.syfte).toBe("stotta");
});

test("elevens namn står på pappret och i dokumentets namn", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await planera(page);
  await valjElev(page, "Alva Nyström");
  /* Bara elevens blad den här gången — klassbrickan går att stänga av. */
  await page.locator('.typrad[data-id="mottagare"] .lchip').first().click();
  await page.locator("#skriv").click();
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  await expect(page.locator("#arkskal .gumottagare").first())
    .toHaveText("Alva Nyström");
  await page.locator("#godkann").click();
  await expect.poll(() => page.evaluate(
    () => window.Dokument.sparade().map(v => window.Dokument.namn
      ? window.Dokument.namn(v) : v.typ)), { timeout: 15_000 })
    .toEqual([expect.stringContaining("Alva Nyström")]);
});
