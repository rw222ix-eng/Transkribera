import { expect, test } from "@playwright/test";

/* TAVLAN PÅ RIKTIGT
 *
 * «Skriv»-knappen körde en tidskomprimerad låtsaskörning som aldrig rörde
 * nätet: faserna spelades upp med setTimeout och tavlan hämtades ur appens
 * egen innehållsbank. Etapp 0.3 kopplade in servern utan att röra formen, och
 * fyra saker måste hålla:
 *
 *   1. Knappen anropar /api/planning/generate och tavlan som ritas är den
 *      SERVERN skrev (wb-json-v1) — inte prototypens form.
 *   2. Molnraden står kvar tills svaret kommit. Ingen falsk procent, ingen
 *      klocka som springer 22 gånger för fort.
 *   3. Motorns [WB]-varningar går tillbaka till servern för en
 *      reparationsrunda, och den lagade tavlan ritas om.
 *   4. Ett fel blir ett besked med en väg vidare, aldrig en tom ruta.
 */

const SCHEMA = {
  schema: [{ dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 2c",
             klass: "NA25", sal: "P807" }],
  lov: [], poster: [],
};

/** En tavla i wb-json-v1 — två bräden, som lesson_board skriver dem. */
function tavla(rubrik = "Derivatans definition") {
  const brade = (namn, bredd) => ({
    name: namn, width: bredd, height: 780, chrome: "aluminium",
    padding: { top: 24, right: 26, bottom: 24, left: 30 },
    sections: [
      { kind: "heading", text: rubrik, size: 30 },
      { kind: "text", text: "Ändringskvoten när h går mot noll.", size: 19 },
      { kind: "math", latex: "f'(x)=\\lim_{h\\to 0}\\frac{f(x+h)-f(x)}{h}", size: 21 },
    ],
  });
  return { title: rubrik, boards: [brade("teori", 900), brade("exempel", 1800)] };
}

const strom = handelser =>
  handelser.map(h => `data: ${JSON.stringify(h)}\n\n`).join("");

async function fejka(page, { generate, rapport } = {}) {
  const anrop = [];
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
  await page.route("**/api/planning/**", route => {
    const vag = new URL(route.request().url()).pathname;
    anrop.push({ vag, kropp: route.request().postDataJSON() });
    if (vag.endsWith("/render-report")) {
      return route.fulfill({ status: 200, contentType: "text/event-stream",
                             body: rapport || strom([{ type: "done", result: { ok: true, repaired: false } }]) });
    }
    if (vag.endsWith("/approve")) return json(route, { ok: true, planned_id: 5 });
    if (vag.endsWith("/export")) return json(route, { ok: true, path: "tavla.png" });
    return route.fulfill({
      status: 200, contentType: "text/event-stream",
      body: generate || strom([
        { type: "log", msg: "Läser centralt innehåll …" },
        { type: "log", msg: "Skriver lektionstavlan …" },
        { type: "done", result: { id: "abc123def456", board: tavla(), errors: [], rounds: 1 } },
      ]),
    });
  });
  return anrop;
}

/** Ställer planeringen på en tavla om `moment` och trycker Skriv. */
async function skriv(page, moment = "Derivatans definition") {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(m => {
    window.SattLage("Tavla");
    const f = document.querySelector("#moment");
    f.value = m;
    f.dispatchEvent(new Event("input", { bubbles: true }));
    // Knappen bor i steg 4 («Upplägg»); stapeln viker ihop de andra.
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  }, moment);
  await page.locator("#skriv").click();
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

test("Skriv anropar servern och tavlan som ritas är serverns", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skriv(page);

  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
  await expect.poll(() => anrop.filter(a => a.vag.endsWith("/generate")).length).toBe(1);
  const gen = anrop.find(a => a.vag.endsWith("/generate"));
  // Klass och kurs går som NAMN — schemat är namn hela vägen.
  expect(gen.kropp.moment).toBe("Derivatans definition");

  // Tavlan på pappret är serverns wb-json-v1: två bräden, inte prototypens ena.
  await expect(page.locator("#dokument .tavruta .whiteboard, #dokument .tavruta .board"))
    .toHaveCount(2, { timeout: 15_000 });
  await expect(page.locator("#dokument .tavruta")).toContainText("Derivatans definition");
});

test("molnraden står kvar tills svaret kommit — ingen falsk klocka", async ({ page }) => {
  // Servern dröjer: strömmen skickas i två delar med en paus emellan.
  await fejka(page);
  await page.unroute("**/api/planning/**");
  await page.route("**/api/planning/**", async route => {
    const vag = new URL(route.request().url()).pathname;
    if (!vag.endsWith("/generate")) {
      return route.fulfill({ status: 200, contentType: "application/json",
                             body: JSON.stringify({ ok: true }) });
    }
    await new Promise(r => setTimeout(r, 2500));
    route.fulfill({ status: 200, contentType: "text/event-stream",
                    body: strom([{ type: "done",
                                   result: { id: "abc123def456", board: tavla(), errors: [], rounds: 2 } }]) });
  });
  await page.goto("/");
  await hydrerad(page);
  await skriv(page);

  // Medan jobbet går står molnraden som «kör» — inte «klar».
  const molnrad = page.locator("#skrivstatus .ffas", { hasText: "Claude skriver tavlan" });
  await expect(molnrad).toHaveAttribute("data-lage", "kor");
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 20_000 });
  // Svarstexten säger vad som faktiskt hände: två rundor.
  await expect(page.locator("#skrivstatus .ftext, #dokument")).not.toHaveText(/^$/);
});

test("motorns varningar går tillbaka för en reparationsrunda", async ({ page }) => {
  const anrop = await fejka(page, {
    // Första tavlan har ett omöjligt brett bräde → motorn varnar «ryms inte».
    generate: strom([{ type: "done", result: {
      id: "abc123def456", errors: [], rounds: 1,
      board: (() => { const t = tavla(); t.boards[0].width = 120; return t; })() } }]),
    rapport: strom([{ type: "done", result: {
      id: "abc123def456", board: tavla("Lagad tavla"), errors: [], rounds: 2, repaired: true } }]),
  });
  await page.goto("/");
  await hydrerad(page);
  await skriv(page);

  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
  await expect.poll(() => anrop.some(a => a.vag.endsWith("/render-report")),
                    { timeout: 15_000 }).toBe(true);
  const rap = anrop.find(a => a.vag.endsWith("/render-report"));
  expect(rap.kropp.warnings.join(" ")).toContain("[WB]");
  // Den lagade tavlan ritas om.
  await expect(page.locator("#dokument .tavruta")).toContainText("Lagad tavla", { timeout: 15_000 });
});

test("grafens kurva kompileras ur uttrycket — inte bara axlar och rutnät", async ({ page }) => {
  /* wb-json-v1 bär kurvan som en uttryckssträng (plots[].expr) — språkmodellen
     får inte skicka JS-funktioner. Utan kompileringen ritades axlar och rutnät
     men ingen kurva, och tavlan såg färdig ut utan det den handlade om. */
  const medGraf = tavla();
  medGraf.boards[0].sections.push({
    kind: "graph", width: 250, height: 210, xRange: [-3, 3], yRange: [-2, 6],
    plots: [{ expr: "x^2", color: "blue" }],
  });
  await fejka(page, { generate: strom([{ type: "done", result: {
    id: "abc123def456", board: medGraf, errors: [], rounds: 1 } }]) });
  await page.goto("/");
  await hydrerad(page);
  await skriv(page);

  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('#dokument .tavruta path[stroke="var(--ink-blue)"]'))
    .toHaveCount(1, { timeout: 15_000 });
});

test("godkännandet skriver in tavlan i planeringsarkivet", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skriv(page);
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  await page.locator("#godkann").click();
  await expect.poll(() => anrop.some(a => a.vag.endsWith("/approve"))).toBe(true);

  /* Tavlan är två saker i arkivet: JSON:en den skrevs som och bilden den såg ut
     som. Bilden ritas av på klienten — servern har ingen motor — och det som
     skickas ska vara en riktig PNG, inte en tom duk. */
  await expect.poll(() => anrop.some(a => a.vag.endsWith("/export")),
                    { timeout: 20_000 }).toBe(true);
  const exp = anrop.find(a => a.vag.endsWith("/export"));
  expect(exp.kropp.pid).toBe("abc123def456");
  const rå = Buffer.from(exp.kropp.png.slice("data:image/png;base64,".length), "base64");
  expect([...rå.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  expect(rå.readUInt32BE(16)).toBeGreaterThan(2000);   // bredden ur IHDR
});

test("ett fel från servern blir ett besked, inte en tom ruta", async ({ page }) => {
  const jsfel = [];
  await fejka(page);
  await page.unroute("**/api/planning/**");
  await page.route("**/api/planning/**", route => route.fulfill({
    status: 409, contentType: "application/json",
    body: JSON.stringify({ error: "GPU:n är upptagen — försök igen strax." }) }));
  await page.goto("/");
  page.on("pageerror", e => jsfel.push(e.message));
  await hydrerad(page);
  await skriv(page);

  const ruta = page.locator("#skrivstatus .fsvar");
  await expect(ruta).toHaveAttribute("data-lage", "stoppad", { timeout: 15_000 });
  await expect(ruta).toContainText("upptagen");
  await expect(ruta.getByRole("button", { name: "Försök igen" })).toBeVisible();
  // Inget halvskrivet dokument får ligga kvar.
  await expect(page.locator("#dokument")).toBeHidden();
  expect(jsfel, jsfel.join(" | ")).toEqual([]);
});

test("utan server körs prototypens takt som förut", async ({ page }) => {
  await page.route("**/api/var-kors", route => route.abort());
  const natanrop = [];
  await page.route("**/api/planning/**", route => { natanrop.push(route.request().url()); route.abort(); });
  await page.goto("/");
  await page.waitForFunction(() => document.documentElement.hasAttribute("data-server") === false);
  await skriv(page);
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 20_000 });
  expect(natanrop).toEqual([]);
});
