import { expect, test } from "@playwright/test";

/* ATT FRONTENDEN ÖVER HUVUD TAGET KOMMER UPP
 *
 * Frontenden är ramverkslös: app.html laddar 41 skript i bestämd ordning, och de
 * delar globaler med varandra. Det finns alltså inget byggsteg som säger ifrån
 * när en fil försvinner, döps om eller hamnar i fel ordning — sidan renderar
 * halvvägs och resten uteblir tyst. Testerna nedan är den saknade kompilatorn.
 */

test("alla skript och stilmallar laddar", async ({ page }) => {
  const misslyckade = [];
  page.on("response", r => { if (r.status() >= 400) misslyckade.push(`${r.status()} ${r.url()}`); });

  await page.goto("/", { waitUntil: "networkidle" });

  // Räknar det webbläsaren FAKTISKT parsade, inte antalet taggar i källan: en
  // stilmall som 404:ar räknas inte som en styleSheet, och ett skript som dör
  // vid parsning syns i pageerror nedan.
  const laddat = await page.evaluate(() => ({
    skript: document.scripts.length,
    stilmallar: document.styleSheets.length,
  }));
  expect(laddat.skript).toBeGreaterThanOrEqual(41);
  expect(laddat.stilmallar).toBeGreaterThanOrEqual(15);

  expect(misslyckade, misslyckade.join(" | ")).toEqual([]);
});

/* Transkribera-fliken och arkivet togs bort 2026-10-07: Planering är appens
   enda vy och den som syns när appen startar. */
test("appen startar på Planering och vyn renderar", async ({ page }) => {
  const jsfel = [];
  page.on("pageerror", e => jsfel.push(e.message));

  await page.goto("/", { waitUntil: "networkidle" });

  // Lokatorerna avgränsas till det som syns: .view och .rubrik finns också i
  // dolda delar av sidan.
  const synlig = () => page.locator(".vy:not([hidden])");
  const rubrik = () => synlig().locator(".view:not([hidden]) .rubrik");
  await expect(synlig()).toHaveCount(1);
  await expect(synlig()).toHaveAttribute("id", "vy-planering");
  await expect(page.getByRole("tab", { name: "Planering" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tab")).toHaveCount(1);
  await expect(rubrik()).toHaveText("Vad ska du planera?");

  // Schemaveckan är planeringens kärna och byggs av JS, så ett tomt rutnät
  // betyder att ett skript dog utan att synas. Dagarna ritas alltid — fem
  // .skdag — medan LEKTIONERNA (.schemagrid .lekt) kommer ur lärarens schema
  // och alltså saknas tills Google Kalender är synkad. Att kräva en lektion
  // här hade gjort ett tomt schema till ett testfel; lektionsritningen prövas
  // mot ett känt schema i schema.spec.mjs i stället.
  await expect(synlig().locator(".schemagrid .skdag")).toHaveCount(5);

  expect(jsfel, jsfel.join(" | ")).toEqual([]);
});

test("himlen och dess bild ligger bakom allt", async ({ page }) => {
  /* Duken är inte dekor: hela färgsättningen förutsätter att texten står mot ett
     ljust foto. Faller bilden bort blir det svart på cerulean, och kontrasten är
     inte längre den som designen valdes mot. */
  await page.goto("/", { waitUntil: "networkidle" });

  const foto = page.locator(".duk .foto.pa").first();
  await expect(foto).toHaveCount(1);

  const laddad = await foto.evaluate(el => {
    const url = getComputedStyle(el).backgroundImage.match(/url\("?([^")]+)"?\)/)?.[1];
    if (!url) return Promise.resolve(false);
    return new Promise(k => { const i = new Image(); i.onload = () => k(true); i.onerror = () => k(false); i.src = url; });
  });
  expect(laddad, "himmelsfotot kunde inte laddas").toBe(true);
});
