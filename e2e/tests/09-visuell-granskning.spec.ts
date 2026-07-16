import {
  test, expect, failOnConsoleError, installFakePywebview, samplePath, gotoApp,
} from "../helpers/app";
import type { Page } from "@playwright/test";

// Visuell granskning: morphdom-nycklar, tema/tokens, SSE-banners, 409-fel,
// dropzon-state och transkriptmodalen. Körs mot fake-projektet med ?e2e=1
// så att window.S är läsbart via page.evaluate.

// Rensa kvarlämnade köposter och gå till källsteget med vald exempel-fil.
async function tillConfigSteg(page: Page) {
  await installFakePywebview(page, samplePath());
  await gotoApp(page);
  const removeBtns = page.getByRole("button", { name: "Ta bort från kön" });
  for (let i = await removeBtns.count(); i > 0; i--) await removeBtns.first().click();
  await page.getByText("klicka för att välja").click();
  await expect(page.locator('[data-pane="config"]')).toBeVisible({ timeout: 8000 });
  await expect(page.getByText("KB-Whisper large (sv)")).toBeVisible({ timeout: 15000 });
}

test("morphdom: data-key/data-pane bevarar respektive ersätter noder", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await tillConfigSteg(page);

  expect(await page.evaluate(() => (window as any).S.step)).toBe("config");

  // Märk config-panelen och köradens data-key-nod med en JS-egenskap.
  await page.evaluate(() => {
    (document.querySelector('[data-pane="config"]') as any).__mark = 1;
    (document.querySelector('[data-pane="config"] [data-key]') as any).__mark = 1;
  });

  // Trigga omrendering utan stegbyte (temaväxling) — noderna ska ÅTERANVÄNDAS.
  await page.getByRole("button", { name: "Växla tema" }).click();
  expect(await page.evaluate(() => ({
    pane: (document.querySelector('[data-pane="config"]') as any).__mark || null,
    rad: (document.querySelector('[data-pane="config"] [data-key]') as any).__mark || null,
  }))).toEqual({ pane: 1, rad: 1 });

  // Stegbyte config -> process: process-panelen ska vara en NY nod (annan nyckel)
  // och config-panelen borta.
  await page.getByRole("button", { name: /Starta/ }).click();
  await expect(page.locator('[data-pane="process"]')).toBeVisible({ timeout: 10000 });
  expect(await page.evaluate(() => ({
    processMark: (document.querySelector('[data-pane="process"]') as any).__mark || null,
    configKvar: !!document.querySelector('[data-pane="config"]'),
  }))).toEqual({ processMark: null, configKvar: false });

  await expect(page.getByText(/Sparade? i Inspelningar/).first()).toBeVisible({ timeout: 25000 });
  expect(errors, errors.join("\n")).toEqual([]);
});

test("tema: data-theme växlar och CSS-tokens följer med", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await gotoApp(page);

  // OBS: setState renderar på nästa requestAnimationFrame — använd retry-
  // assertioner (toHaveAttribute/poll), aldrig omedelbar evaluate efter klick.
  const canvas = () => page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--canvas").trim());
  const html = page.locator("html");
  await expect(html).toHaveAttribute("data-theme", "light");
  const before = await canvas();

  await page.getByRole("button", { name: "Växla tema" }).click();
  await expect(html).toHaveAttribute("data-theme", "dark");
  expect(await canvas()).not.toBe(before);

  // Tillbaka — token återställs.
  await page.getByRole("button", { name: "Växla tema" }).click();
  await expect(html).toHaveAttribute("data-theme", "light");
  expect(await canvas()).toBe(before);
  expect(errors, errors.join("\n")).toEqual([]);
});

test("hover: .cta-knappens fyllnadsanimation aktiveras", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await tillConfigSteg(page);

  const transformFor = () => page.evaluate(() => {
    const el = document.querySelector("button.cta")!;
    return getComputedStyle(el, "::before").transform;
  });
  const vila = await transformFor();
  await page.locator("button.cta").hover();
  // ::before glider från translateY(101%) mot translateY(0) — vänta in transitionen.
  await expect.poll(transformFor, { timeout: 3000 }).not.toBe(vila);
  expect(errors, errors.join("\n")).toEqual([]);
});

test("reducerad rörelse: flödet fungerar utan konsolfel", async ({ browser }) => {
  const ctx = await browser.newContext({ reducedMotion: "reduce" });
  const page = await ctx.newPage();
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await tillConfigSteg(page);
  await page.getByRole("button", { name: /Starta/ }).click();
  await expect(page.getByText(/Sparade? i Inspelningar/).first()).toBeVisible({ timeout: 25000 });
  expect(errors, errors.join("\n")).toEqual([]);
  await ctx.close();
});

test("SSE: progress rör sig, loggen når Klar och resultat visas", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await tillConfigSteg(page);
  await page.getByRole("button", { name: /Starta/ }).click();

  // Progressen ska röra sig uppåt under körningen och sluta på 100 vid done.
  await expect.poll(() => page.evaluate(() => (window as any).S.progress),
    { timeout: 15000 }).toBeGreaterThan(0);
  await expect.poll(() => page.evaluate(() => (window as any).S.run),
    { timeout: 20000 }).toBe("done");

  // Läs state direkt vid done — finishTranscribe nollställer wizarden strax efter.
  const vidDone = await page.evaluate(() => ({
    progress: (window as any).S.progress,
    log: ((window as any).S.log || []).join("\n"),
  }));
  expect(vidDone.progress).toBe(100);
  expect(vidDone.log).toContain("Färdig");

  // Fire-and-forget: Inspelningar öppnas automatiskt med kvittens-toast.
  await expect(page.getByText(/Sparade? i Inspelningar/).first()).toBeVisible({ timeout: 10000 });
  expect(errors, errors.join("\n")).toEqual([]);
});

test("409: svensk felbanner med Försök igen", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await tillConfigSteg(page);

  await page.route("**/api/transcribe", (route) => route.fulfill({
    status: 409,
    contentType: "application/json",
    body: JSON.stringify({ error: "GPU upptagen – vänta tills pågående jobb är klart." }),
  }));
  await page.getByRole("button", { name: /Starta/ }).click();

  await expect(page.getByText("Transkriberingen misslyckades")).toBeVisible({ timeout: 10000 });
  await expect(page.getByText("GPU upptagen", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Försök igen" })).toBeVisible();
  expect(await page.evaluate(() => (window as any).S.run)).toBe("error");
  // 409-svaret loggas av webbläsaren som resursfel — det är förväntat här.
  const ovantade = errors.filter((e) => !e.includes("409"));
  expect(ovantade, ovantade.join("\n")).toEqual([]);
});

test("dropzon: dragover/dragleave uppdaterar S.dragging", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await installFakePywebview(page, samplePath());
  await gotoApp(page);

  const zone = page.locator("[data-dragover]").first();
  await zone.dispatchEvent("dragover");
  expect(await page.evaluate(() => (window as any).S.dragging)).toBe(true);
  await zone.dispatchEvent("dragleave");
  expect(await page.evaluate(() => (window as any).S.dragging)).toBe(false);
  expect(errors, errors.join("\n")).toEqual([]);
});

test("sökfältet: Fråga-knappen flyttar sig inte när text skrivs (ingen layout-shift)", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await gotoApp(page);
  await page.getByRole("button", { name: "Inspelningar", exact: true }).first().click();
  await page.getByRole("button", { name: "Fråga AI", exact: true }).first().click();

  const knapp = page.getByRole("button", { name: "Fråga", exact: true });
  const fore = await knapp.boundingBox();
  const inp = page.getByPlaceholder("Ställ en fråga, t.ex. när hade vi prov om derivata?");
  await inp.fill("bråk");
  // Rensa-knappen blir synlig — men den upptog redan sin plats, så submit-
  // knappen får inte ha flyttats (klick på gamla koordinater var buggen).
  await expect(page.getByRole("button", { name: "Rensa" })).toBeVisible();
  const efter = await knapp.boundingBox();
  expect(efter!.x).toBe(fore!.x);
  expect(efter!.y).toBe(fore!.y);
  expect(errors, errors.join("\n")).toEqual([]);
});

test("transkriptmodal: sök med åäö, matchnavigering och redigeringsläge", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await tillConfigSteg(page);
  await page.getByRole("button", { name: /Starta/ }).click();
  // Fire-and-forget: vänta in auto-navigeringen till Inspelningar, öppna kortet
  // och gå in i transkriptvyn via overlayns Transkript-knapp.
  await expect(page.getByText(/Sparade? i Inspelningar/).first()).toBeVisible({ timeout: 25000 });
  await page.locator('[data-rec-id]').first().click();
  await page.getByRole("button", { name: "Transkript", exact: true }).click();
  const sok = page.locator("input[data-tsearch]");
  await expect(sok).toBeVisible();

  // Sök med svenska tecken — fake-transkriptet innehåller "bråk".
  await sok.fill("bråk");
  await expect(page.locator('[data-current="1"]')).toBeVisible();
  const fore = await page.locator('[data-current="1"]').textContent();
  await sok.press("Enter");           // nästa match (kan vara samma om bara en)
  await expect(page.locator('[data-current="1"]')).toBeVisible();
  await sok.press("Shift+Enter");     // föregående match
  await expect(page.locator('[data-current="1"]')).toHaveText(fore || "");

  // Redigeringsläge på/av utan konsolfel.
  await page.getByRole("button", { name: "Redigera", exact: true }).click();
  await expect(page.getByRole("button", { name: "✓ Klar" })).toBeVisible();
  await page.getByRole("button", { name: "✓ Klar" }).click();

  await page.getByRole("button", { name: "Stäng" }).first().click();
  await expect(sok).not.toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
});
