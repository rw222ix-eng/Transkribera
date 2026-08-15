import { expect, test } from "@playwright/test";
import { oppna, rent, spana, traff, vakt, valjKlass } from "./larardag.mjs";

/* NIVÅVARNINGEN — momentet mot ämnesplanen, före pengarna
 *
 * Fyndet den kom ur (2026-08-15, skarp körning mot riktiga Claude Code): ett
 * prov beställdes på «derivator» i en 2c-lektion. Derivator ligger i 3c, så
 * modellen skrev ett 2c-prov — funktioner, trigonometri, sannolikhet — medan
 * appen satte rubriken ur MOMENTFÄLTET. Pappret hette «Derivator» och innehöll
 * något annat, och det syntes först efter 230 sekunders generering.
 *
 * Tre saker ska hålla, och den första är den som kostar pengar när den brister:
 *
 *   1. Varningen kommer INNAN anropet. Inget /generate får ha gått i väg.
 *   2. Andra klicket skriver ändå. Läraren bestämmer över sin lektion —
 *      repetition av en lägre nivå är ett giltigt skäl, och en spärr vore fel.
 *   3. Ett moment som passar nivån är tyst. En varning som kommer för ofta
 *      läser ingen, och då är den värre än ingen alls.
 *
 * Kontrollen bor i gy.js (window.Gy.utanfor) och kopplas in i plan.js vid
 * #skriv. Den är rent lokal — ingen server och ingen modell behövs för att
 * pröva den, och därför är det här testet snabbt.
 */

const UTANFOR = "derivator: definition, deriveringsregler, tangent";
const INOM = "andragradsfunktioner och nollställen";

/** Ställer typ och moment utan att trycka Skriv. */
const stall = (page, moment) => page.evaluate(m => {
  window.SattLage("Prov");
  const f = document.querySelector("#moment");
  f.value = m;
  f.dispatchEvent(new Event("input", { bubbles: true }));
  window.PlanSteg.las(4, false);
  window.PlanSteg.gaTill(4);
}, moment);

test("moment ur en annan nivå varnar — och anropet uteblir", async ({ page }) => {
  const fel = vakt(page);
  const anrop = spana(page);
  await oppna(page);
  await valjKlass(page, "NA25");
  await stall(page, UTANFOR);

  await page.locator("#skriv").click();
  /* Nivåerna sägs med lärarens egna beteckningar — «Matematik 3c», inte
     Gy25-etiketten hon aldrig säger högt. */
  await expect(page.locator(".toast, [class*=toast]").first())
    .toContainText(/Matematik 3c.*inte i.*Matematik 2c/s);
  /* Det här är hela poängen: kontrollen hann före. */
  expect(traff(anrop, "/generate")).toEqual([]);
  rent(fel);
});

test("andra klicket skriver ändå", async ({ page }) => {
  const fel = vakt(page);
  await oppna(page);
  await valjKlass(page, "NA25");
  await stall(page, UTANFOR);

  await page.locator("#skriv").click();          // varningen
  const svar = page.waitForResponse(
    r => /\/api\/exams\/generate$/.test(new URL(r.url()).pathname), { timeout: 60_000 });
  await page.locator("#skriv").click();          // beslutet
  expect((await svar).status()).toBe(200);
  rent(fel);
});

test("moment som hör till nivån är tyst", async ({ page }) => {
  const fel = vakt(page);
  await oppna(page);
  await valjKlass(page, "NA25");
  await stall(page, INOM);

  const svar = page.waitForResponse(
    r => /\/api\/exams\/generate$/.test(new URL(r.url()).pathname), { timeout: 60_000 });
  await page.locator("#skriv").click();          // ETT klick ska räcka
  expect((await svar).status()).toBe(200);
  rent(fel);
});

test("lärarens egna ord varnar aldrig", async ({ page }) => {
  await oppna(page);
  /* Ingen ämnesplan nämner «repetition inför provet», och en varning på lärarens
     eget språk vore ren skada. Prövas direkt mot kontrollen: den ska tiga för
     allt den inte känner igen, inte bara för det den känner igen som rätt. */
  for (const m of ["repetition inför provet", "det som föll förra veckan", "prov"]) {
    expect(await page.evaluate(
      t => !!window.Gy.utanfor(t, window.Gy.foreslagen("Matematik, nivå 2c")), m),
      `varnade för «${m}»`).toBe(false);
  }
});
