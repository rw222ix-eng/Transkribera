import { expect, test } from "@playwright/test";

/* GODKÄNNANDET TAPPAR INGEN VERSION (2026-09-24 kväll, blad 146)
 *
 * Ett sparat papper bar provVersion 546. En omskrivning via API:t lade 561.
 * Förhandsvisningen hämtade provets aktuella uppgifter (speglaExamen) och
 * ritade dem, men provVersion stod kvar på 546, och godkännandet flyttade
 * provets pekare tillbaka dit: 561 försvann ur provet. Nu följer versionen
 * listan, och godkännandet skickar den version pappret faktiskt visar.
 */

const SCHEMA = { schema: [], lov: [], poster: [] };

const EXAM = {
  titel: "Inför provet", kurs: "Matematik, nivå 1a", klass: "BA26B",
  datum: "2026-09-30", tid_min: 60, hjalpmedel: "Utan räknare.",
  uppgifter: [
    { formaga: "B", typ: "rutin", poang: [1, 0, 0],
      text: "Beräkna $3 + 4 \\cdot 2$.", losning: "$11$" },
  ],
};

function papper() {
  return {
    typ: "Arbetsblad", moment: "Inför provet", klass: "BA26B",
    kurs: "Matematik, nivå 1a", datum: "2026-09-30", tid: "",
    gy: [], kalla: false, kallor: [], inst: { antal: 1, niva: "E-nivå" },
    bilder: {}, referenser: [], forlaga: null, resultat: null, fokus: "",
    kontext: "start", niva: false, svarighet: 0, andrat: [],
    provId: 12, provVersion: 546,
    uppgifter: [{ nr: 1, p: 1, t: "Beräkna $2 + 3 \\cdot 2$.", f: "$8$" }],
  };
}

const rad = (id, dok) => ({
  id, status: "godkant", markor: 0, sort: id, foljd: null,
  versioner: [dok], dokument: { ...dok, id },
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
  await page.route("**/api/dokument", route => json(route, {
    sparade: [rad(1, papper())], utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
  await page.route("**/api/exams/**", route => {
    const vag = new URL(route.request().url()).pathname;
    if (vag.endsWith("/approve")) {
      anrop.push(route.request().postDataJSON());
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "done", result: { id: 12, pdf: "C:/x.pdf",
          tex: "C:/x.tex", errors: [] } }]) });
    }
    // GET /api/exams/12: provets AKTUELLA version är 561.
    return json(route, { id: 12, exam: EXAM, current_version: 561,
      typ: "arbetsblad", status: "godkänt", efterkontroll: [],
      efterkontroll_instruktion: "", versions: [], errors: [] });
  });
  return anrop;
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

test("godkännandet skickar versionen pappret visar, inte den sparade",
  async ({ page }) => {
    const anrop = await fejka(page);
    await page.goto("/");
    await hydrerad(page);
    await page.getByRole("tab", { name: "Planering" }).click();
    await page.evaluate(() => window.Dokument.visa(0));
    await expect(page.locator("#forhandsskal")).toBeVisible();
    // Förhandsvisningen ritar provets aktuella uppgift (3 + 4 · 2).
    await expect.poll(() => page.locator("#fh-ark").innerHTML(),
                      { timeout: 15_000 }).toContain("3 + 4");
    await page.locator("#fh-fortsatt").click();
    await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
    await page.locator("#godkann").click();
    await expect.poll(() => anrop.length, { timeout: 30_000 }).toBeGreaterThan(0);
    expect(anrop[0].version).toBe(561);
    expect(anrop[0].aldre_version).toBe(false);
  });
