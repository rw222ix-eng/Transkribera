import { expect, test } from "@playwright/test";
import { oppna, skriv, spana, traff, vakt, valjKlass } from "./larardag.mjs";

/* ANTECKNINGARNA — femte dokumenttypen, hela vägen
 *
 * Kör mot den RIKTIGA servern (e2e/testserver.py) med Claude fejkat i CLI:t:
 * bandet tests/kassetter/anteckningar.json är en skarp inspelning, så allt
 * efter svaret — strömtolkningen, schemat, stilvalideringen, radbudgeten,
 * lagringen, godkännandet — körs på riktigt.
 *
 * Fyra saker ska hålla, och de är precis de fyra som skiljer typen från de
 * andra:
 *
 *   1. Typvalen byter innehåll: en ruta att skriva i, inte antal uppgifter.
 *      Boklösningsraden hör inte hit och ska inte följa med.
 *   2. Knappen anropar /api/anteckningar/generate — och pappret som ritas är
 *      det servern skrev, satt som ett stödpapper (rubriker, löptext, ingen
 *      uppgiftsbricka).
 *   3. Tom ruta utan möte är ett vänligt stopp, inte ett papper ur ingenting.
 *   4. Godkännandet lägger pappret i Sparat och ber servern bygga PDF:en.
 */

const rutan = page => page.locator(".typfritext");

test("typvalen frågar vad som ska stå på pappret", async ({ page }) => {
  const fel = vakt(page);
  await oppna(page);
  await valjKlass(page, "NA25");
  await page.evaluate(() => {
    window.SattLage("Anteckningar");
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  });

  await expect(rutan(page)).toBeVisible();
  await expect(page.locator('.typrad[data-id="onskemal"]')).toHaveCount(1);
  await expect(page.locator('.typrad[data-id="lektioner"]')).toHaveCount(1);
  /* Det som INTE ska finnas är lika viktigt: anteckningarna har inga
     uppgifter, ingen nivå och inget facit — och lösningar till bokens
     uppgifter hör inte till lärarens stödpapper. */
  for (const id of ["antal", "niva", "facit", "boklosniva", "illustration"]) {
    await expect(page.locator(`.typrad[data-id="${id}"]`)).toHaveCount(0);
  }
  /* Raden under rutan säger vad som fattas — och den ska säga BÅDA vägarna. */
  await expect(page.locator('.typrad[data-id="onskemal"] .typnot'))
    .toHaveText(/Skriv vad pappret ska innehålla, eller välj ett möte/);
  expect(fel).toEqual([]);
});

test("tom ruta utan möte stoppar med ett besked", async ({ page }) => {
  const fel = vakt(page);
  const anrop = spana(page);
  await oppna(page);
  await valjKlass(page, "NA25");
  await page.evaluate(() => {
    window.SattLage("Anteckningar");
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  });
  await page.locator("#skriv").click();
  await page.waitForTimeout(400);

  expect(traff(anrop, "/anteckningar/generate")).toHaveLength(0);
  await expect(page.locator(".toast, #toast")).toContainText(
    /Skriv vad pappret ska innehålla|välj ett möte/);
  expect(fel).toEqual([]);
});

test("pappret skrivs ur rutan och ritas som ett stödpapper", async ({ page }) => {
  const fel = vakt(page);
  const anrop = spana(page);
  await oppna(page);
  await valjKlass(page, "NA25");

  await skriv(page, {
    typ: "Anteckningar", moment: "första lektionen",
    onskemal: "Boken, hur vi räknar, provdatumen och räknaren.",
  });

  /* 1. Anropet gick till anteckningarnas egen rutt, med rutans text. */
  const gen = traff(anrop, "/anteckningar/generate");
  expect(gen).toHaveLength(1);
  expect(gen[0].kropp.onskemal).toContain("Boken");

  /* 2. Pappret är satt som ett stödpapper: rubriker och löptext, inga
        uppgiftsbrickor och ingen svarsrad. */
  const ark = page.locator('[data-form="an"]');
  await expect(ark).toBeVisible();
  await expect(ark.locator(".antitel")).not.toBeEmpty();
  expect(await ark.locator(".ansekt").count()).toBeGreaterThan(1);
  await expect(ark.locator(".anrubrik").first()).not.toBeEmpty();
  await expect(ark.locator(".gubricka")).toHaveCount(0);
  await expect(ark.locator(".gulinje")).toHaveCount(0);

  /* 3. Innehållet kom ur bandet — alltså hela vägen genom servern. */
  await expect(ark).toContainText(/räknare/i);

  /* 4. Facitväxlaren hör till papper med uppgifter, inte till det här. */
  await expect(page.locator("#arkval")).toBeHidden();
  expect(fel).toEqual([]);
});

test("godkännandet lägger pappret i Sparat och ber om PDF:en", async ({ page }) => {
  const fel = vakt(page);
  const anrop = spana(page);
  await oppna(page);
  await valjKlass(page, "NA25");

  const fore = await page.evaluate(() => window.Dokument.sparade().length);
  await skriv(page, {
    typ: "Anteckningar", moment: "kursstart",
    onskemal: "Boken, rutinerna och provdatumen.",
  });
  await page.locator("#godkann").click();
  await page.waitForResponse(
    r => /\/api\/anteckningar\/\d+\/approve$/.test(new URL(r.url()).pathname),
    { timeout: 60_000 });

  /* Godkännandet gör två saker, och båda ska ha hänt: pappret ligger i högen
     OCH servern har bett Tectonic bygga PDF:en. */
  expect(traff(anrop, "/approve")).not.toHaveLength(0);
  await expect
    .poll(() => page.evaluate(() => window.Dokument.sparade().length))
    .toBe(fore + 1);
  const v = await page.evaluate(() => window.Dokument.sparade().at(-1));
  expect(v.typ).toBe("Anteckningar");
  expect(v.antId).toBeTruthy();
  expect(v.ant.sektioner.length).toBeGreaterThan(1);
  /* Inga uppgifter på ett stödpapper — varken skrivna eller ärvda ur
     prototypens avsnittspool. */
  expect(v.uppgifter || []).toHaveLength(0);
  /* Och inget losningsblad-syskon: det finns ingen andra hälft att vända på. */
  const facit = await page.evaluate(
    () => window.Dokument.sparade().filter(x => x.losningsblad).length);
  expect(facit).toBe(0);
  expect(fel).toEqual([]);
});
