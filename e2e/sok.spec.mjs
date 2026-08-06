import { expect, test } from "@playwright/test";

/* SÖKNINGEN OCH FÖRSLAGEN
 *
 * Två saker i transkriberingsvyn kördes på prototypens enda transkription:
 * sökfältet (som «hittade» samma rader i varje lektion) och granskningen efter
 * en körning (fyra regexfraser). Etapp 0.9 kopplade båda till servern:
 *
 *   1. Frågan om det som SADES går till /api/search/ask — FTS över alla
 *      lektioner — och svaret är serverns, inte ett stycke som var skrivet i
 *      förväg och påstod att det byggde på det som sades.
 *   2. Förslagen efter en körning kommer ur den riktiga extraktionen.
 *
 * Utan server står prototypen kvar.
 */

const SCHEMA = { schema: [], lov: [], poster: [] };

const LEKTIONER = [
  { id: 1, history_id: "h1", name: "Derivator NA25", datum: "2026-05-11",
    group: "NA25", course: "Matematik, nivå 2c", dur: "41:00", lang: "Svenska" },
  { id: 2, history_id: "h2", name: "Integraler NA24", datum: "2026-05-12",
    group: "NA24", course: "Matematik, nivå 1c", dur: "38:00", lang: "Svenska" },
];

const HISTORIK = [
  { id: "h1", ts: "2026-05-11T09:05:00", name: "Derivator NA25" },
  { id: "h2", ts: "2026-05-12T09:05:00", name: "Integraler NA24" },
];

const SEGMENT = {
  h1: { id: "h1", transcript: [
    { start: 42, text: "Vi börjar med differenskvoten och låter h gå mot noll." },
    { start: 96, text: "Derivatan är alltså lutningen i en punkt." }] },
  h2: { id: "h2", transcript: [
    { start: 15, text: "Idag tar vi primitiva funktioner." }] },
};

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

async function fejka(page, { hits = null, svar = null } = {}) {
  const anrop = [];
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
  await page.route("**/api/bocker**", route => json(route, { bocker: [] }));
  await page.route("**/api/lessons", route => json(route, LEKTIONER));
  await page.route("**/api/history", route => json(route, HISTORIK));
  await page.route("**/api/history/*", route => {
    const id = new URL(route.request().url()).pathname.split("/").pop();
    anrop.push({ vag: "/api/history/" + id });
    return json(route, SEGMENT[id] || { id, transcript: [] });
  });
  await page.route("**/api/search**", route => {
    const url = new URL(route.request().url());
    anrop.push({ vag: "/api/search", q: url.searchParams.get("q") });
    return json(route, hits || { query: url.searchParams.get("q"), hits: [
      { lesson_id: 1, history_id: "h1", name: "Derivator NA25",
        datum: "2026-05-11", group: "NA25", course: "Matematik, nivå 2c",
        snippet: "låter h gå mot noll." }] });
  });
  await page.route("**/api/search/ask", route => {
    anrop.push({ vag: "/api/search/ask", kropp: route.request().postDataJSON() });
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: svar || strom([
        { type: "log", msg: "Söker i 2 lektioner ..." },
        { type: "done", result: {
          text: "Differenskvoten gicks igenom den 11 maj och följdes upp veckan efter.",
          sources: [{ lesson_id: 1, history_id: "h1", name: "Derivator NA25" }] } }]) });
  });
  return anrop;
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

/* Arkivfältet bor i planeringen — Inspelningar-fliken är pensionerad, och
   lektionerna bor i veckan nu. Fältet har tre lägen; frågan och ordsökningen
   är de två som svarar. */
async function arkivet(page, lage) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(l => {
    const knapp = [...document.querySelectorAll('[data-seg="arkivläge"] button')]
      .find(b => b.textContent.trim() === l);
    knapp && knapp.click();
  }, lage);
}

test("frågan om det som sades besvaras av servern", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await arkivet(page, "Fråga");

  await page.locator("#arkivfalt").fill("Vad sa jag om differenskvoten på lektionen?");
  await page.locator("#arkivknapp").click();

  await expect.poll(() => anrop.some(a => a.vag === "/api/search/ask"), { timeout: 15_000 }).toBe(true);
  const fraga = anrop.find(a => a.vag === "/api/search/ask");
  expect(fraga.kropp.q).toBe("Vad sa jag om differenskvoten på lektionen?");
  await expect(page.locator("#arkivsvar .ftext"))
    .toContainText("Differenskvoten gicks igenom den 11 maj", { timeout: 25_000 });
});

test("ett fel i sökningen blir ett besked, inte ett tomt svar", async ({ page }) => {
  await fejka(page, { svar: strom([{ type: "error", error: "GPU:n är upptagen — försök igen strax." }]) });
  await page.goto("/");
  await hydrerad(page);
  await arkivet(page, "Fråga");
  await page.locator("#arkivfalt").fill("Vad sades om differenskvoten på lektionen?");
  await page.locator("#arkivknapp").click();

  const ruta = page.locator("#arkivsvar .fsvar");
  await expect(ruta).toHaveAttribute("data-lage", "stoppad", { timeout: 25_000 });
  await expect(ruta).toContainText("upptagen");
});

test("utan server svarar prototypen ur högen som förut", async ({ page }) => {
  await page.route("**/api/var-kors", route => route.abort());
  const natanrop = [];
  await page.route("**/api/search**", route => { natanrop.push(route.request().url()); route.abort(); });
  await page.goto("/");
  await page.waitForFunction(() => document.documentElement.hasAttribute("data-server") === false);
  await arkivet(page, "Fråga");

  await page.locator("#arkivfalt").fill("Vad sa jag om derivator på lektionen?");
  await page.locator("#arkivknapp").click();
  await expect(page.locator("#arkivsvar .fsvar")).toBeVisible({ timeout: 25_000 });
  expect(natanrop).toEqual([]);
});
