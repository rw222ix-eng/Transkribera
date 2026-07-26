/**
 * Transkriptvyn (plan B2). Modalen delas av Inspelningar och Transkribera, så
 * den monteras utanför flikpanelerna i App.svelte.
 *
 * TÄCKER (växer per task):
 *   1. Öppning från lektionskortet: rubrik, dialogroll, fokusåtergång.
 *   2. Live-regionen: EN annonserande nod, räknad via a11y-trädet.
 *
 * TÄCKS INTE:
 *   - Riktig ljuduppspelning. Chromium i CI spelar inte upp; specen mäter att
 *     elementet finns, får rätt src och att kontrollerna kallar rätt kod.
 *
 * FIXTUREN byggs mot riktiga endpoints, som i inspelningar-kartotek.spec.mjs:
 * en POST /api/transcribe med fejkad ASR ger en historikpost OCH en
 * lektionsrad. Fejkens tre segment (serve_test_app.py:41-46) ger de
 * förutsägbara tidkoderna 00:00, 00:02 och 00:05.
 */
import { test, expect, failOnConsoleError } from "./helpers/app";

/** Fejkserverns transkript. Speglar _fake_segments, e2e/serve_test_app.py:41-46. */
const SEGMENT = [
  { tid: "00:00", text: "Hej och välkommen till lektionen." },
  { tid: "00:02", text: "Idag ska vi prata om bråk och procent." },
  { tid: "00:05", text: "Ta fram era anteckningsböcker." },
];

/** Fejkens AI-namngivning, serve_test_app.py:135-137. */
const LEKTIONSNAMN = "Bråk och procent — introduktion";

/** Raderar varje lektion. Tar historikposten och mappen med sig. */
async function toemArkivet(request) {
  const lektioner = await (await request.get("/api/lessons")).json();
  for (const l of lektioner) {
    const r = await request.delete("/api/lessons/" + l.id);
    expect(r.ok(), `DELETE /api/lessons/${l.id} svarade ${r.status()}`).toBeTruthy();
  }
}

/** En lektion med ljud och transkript. Returnerar lektionsraden. */
async function byggFixtur(request) {
  await toemArkivet(request);

  const sampleSvar = await request.get("/api/sample");
  expect(
    sampleSvar.status(),
    'Saknad testfixtur: "Mamma waw isolerad.wav" i repo-roten (se e2e/serve_test_app.py). ' +
      "/api/sample svarade " + sampleSvar.status() + ".",
  ).toBe(200);
  const sample = await sampleSvar.json();

  const katalog = (await (await request.get("/api/models")).json()).whisper || [];
  const modell =
    katalog.find((m) => m.installed && m.id === "KBLab/kb-whisper-large") ||
    katalog.find((m) => m.installed);
  expect(modell, "Ingen installerad Whisper-modell i models/ — kan inte skapa lektioner").toBeTruthy();

  const r = await request.post("/api/transcribe", {
    data: { source: sample.path, model_id: modell.id, language: "sv", formats: ["srt"] },
    timeout: 60_000,
  });
  expect(r.status(), "POST /api/transcribe misslyckades").toBe(200);

  const lektioner = await (await request.get("/api/lessons")).json();
  expect(lektioner, "En transkribering skulle ge en lektionsrad").toHaveLength(1);
  return lektioner[0];
}

/** Öppnar Inspelningar och returnerar den synliga vyn. */
async function oppnaInspelningar(page) {
  await page.goto("/next/");
  await page.getByRole("button", { name: "Inspelningar", exact: true }).click();
  const vy = page.locator(".pane:not([hidden]) section.view");
  await expect(vy.locator("article.kort")).toHaveCount(1, { timeout: 15_000 });
  return vy;
}

/** Öppnar transkriptvyn från kortet och returnerar dialogen. */
async function oppnaTranskript(page) {
  const vy = await oppnaInspelningar(page);
  await vy.getByRole("button", { name: "Öppna" }).click();
  const ruta = page.getByRole("dialog", { name: "Transkript" });
  await expect(ruta).toBeVisible();
  return ruta;
}

test.beforeEach(async ({ request }) => {
  await byggFixtur(request);
});
test.afterEach(async ({ request }) => {
  await toemArkivet(request);
});

test("kortet öppnar transkriptvyn med lektionens namn som rubrik", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  await expect(ruta.getByRole("heading", { level: 2 })).toHaveText(LEKTIONSNAMN);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Escape stänger och fokus återvänder till knappen som öppnade", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  const oppna = vy.getByRole("button", { name: "Öppna" });
  await oppna.click();

  const ruta = page.getByRole("dialog", { name: "Transkript" });
  await expect(ruta).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(ruta).toBeHidden();
  // Webbläsarens <dialog>-återställning, inte egen kod. Faller den har någon
  // gjort komponenten {#if}-grindad så close() aldrig hinner köras.
  await expect(oppna).toBeFocused();

  expect(errors, errors.join("\n")).toEqual([]);
});

test("dialogen har EN annonserande nod", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  // getByRole, aldrig CSS: den synliga aria-hidden-kopian ligger i DOM:en men
  // inte i a11y-trädet, så en CSS-räkning ger 2 där trädet ger 1. Fällan är
  // utskriven i playwright.config.ts:178-190.
  await expect(ruta.getByRole("status")).toHaveCount(1);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("en historikpost som inte går att läsa säger det", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.route("**/api/history/*", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({ status: 500, contentType: "application/json", body: '{"error":"trasig"}' });
  });

  const ruta = await oppnaTranskript(page);
  // Dialogen öppnas ändå — rubriken kommer från kortet, inte från svaret — men
  // den ljuger inte om att den är tom.
  await expect(ruta.getByTestId("transkript-statusrad")).toHaveText(
    "Kunde inte läsa transkriptet — starta om appen och försök igen.",
  );

  expect(errors.filter((e) => !/500|Failed to load/.test(e)), errors.join("\n")).toEqual([]);
});

test("transkriptet renderas med tidkod och text per rad", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  const rader = ruta.locator("li.rad");
  await expect(rader).toHaveCount(SEGMENT.length);

  for (let i = 0; i < SEGMENT.length; i++) {
    await expect(rader.nth(i).locator(".tid")).toHaveText(SEGMENT[i].tid);
    await expect(rader.nth(i).locator(".text")).toHaveText(SEGMENT[i].text);
  }

  expect(errors, errors.join("\n")).toEqual([]);
});

test("en lektion över en timme får en timkomponent i tidkoden", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Gamla appens fmtTime saknar timkomponent (app.js:424) och visar "62:05"
  // för en lektion på en timme och två minuter. Fejkens segment stannar på
  // 7,6 s, så tiden måste skrivas in.
  const lektion = (await (await request.get("/api/lessons")).json())[0];
  const r = await request.patch("/api/history/" + lektion.history_id, {
    data: { transcript: [{ start: 3725, end: 3730, text: "Sent i lektionen." }] },
  });
  expect(r.ok(), `PATCH /api/history svarade ${r.status()}`).toBeTruthy();

  const ruta = await oppnaTranskript(page);
  await expect(ruta.locator("li.rad .tid")).toHaveText("1:02:05");

  expect(errors, errors.join("\n")).toEqual([]);
});
