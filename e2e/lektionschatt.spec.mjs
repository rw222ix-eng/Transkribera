/**
 * Lektionschatten (plan B4). Modalen delas av Inspelningar och — senare —
 * arkivsvaret, så den monteras utanför flikpanelerna i App.svelte.
 *
 * TÄCKER:
 *   1. Öppning från lektionskortet, Escape, fokusåtergång, EN annonserande nod.
 *   2. Ett svar strömmar in och står kvar efter done.
 *   3. Generationsvakten: byt lektion medan ett svar strömmar.
 *   4. Skicka är spärrad hela vägen till done, inte bara till första token.
 *   5. 409 visar serverns egen text.
 *   6. En trasig historikpost ger ett synligt fel, inte en tyst tom chatt.
 *   7. Citatklick fäller ut källpanelen; klick igen fäller ihop.
 *   8. Samtalet återkommer för samma lektion, men inte för en annan.
 *
 * TÄCKS INTE:
 *   - Riktig LLM-inferens. /api/chat fejkas i varje test som skickar en fråga;
 *     fejkservern har ingen språkmodell.
 *   - Kalendermaskineriet, som B4 medvetet inte portar.
 */
import { test, expect, failOnConsoleError } from "./helpers/app";

/** Fejkens transkript. Speglar _fake_segments, e2e/serve_test_app.py:41-46. */
const SEGMENT = [
  "Hej och välkommen till lektionen.",
  "Idag ska vi prata om bråk och procent.",
  "Ta fram era anteckningsböcker.",
];

/** Fejkens AI-namngivning, serve_test_app.py:135-137. */
const LEKTIONSNAMN = "Bråk och procent — introduktion";

/** Serverns SSE-kontrakt: ett event per `data: <json>\n\n` (app/web/sse.py). */
function sseKropp(events) {
  return events.map((e) => "data: " + JSON.stringify(e) + "\n\n").join("");
}

/**
 * Fejkar POST /api/chat. `fordroj` håller svaret så testet hinner assertera
 * mellanläget — det är enda sättet att pröva att Skicka är spärrad MEDAN ett
 * svar är i luften.
 */
async function fejkaChat(page, { events = [], fordroj = 0, status = 200, fel = "" } = {}) {
  await page.route("**/api/chat", async (route) => {
    if (fordroj) await new Promise((klar) => setTimeout(klar, fordroj));
    if (status !== 200) {
      return route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify({ error: fel }),
      });
    }
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseKropp(events),
    });
  });
}

async function toemArkivet(request) {
  const lektioner = await (await request.get("/api/lessons")).json();
  for (const l of lektioner) {
    let r = await request.delete("/api/lessons/" + l.id);
    for (let forsok = 0; r.status() === 409 && forsok < 8; forsok++) {
      await new Promise((klar) => setTimeout(klar, 400));
      r = await request.delete("/api/lessons/" + l.id);
    }
    expect(r.ok(), `DELETE /api/lessons/${l.id} svarade ${r.status()}`).toBeTruthy();
  }
}

/** Två lektioner — generationsvakten och samtalskartan behöver båda. */
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

  for (let i = 0; i < 2; i++) {
    const r = await request.post("/api/transcribe", {
      data: { source: sample.path, model_id: modell.id, language: "sv", formats: ["srt"] },
      timeout: 60_000,
    });
    expect(r.status(), "POST /api/transcribe misslyckades för post " + i).toBe(200);
  }

  const lektioner = await (await request.get("/api/lessons")).json();
  expect(lektioner, "Två transkriberingar skulle ge två lektionsrader").toHaveLength(2);
  return lektioner;
}

async function oppnaInspelningar(page) {
  await page.goto("/next/");
  await page.getByRole("button", { name: "Inspelningar", exact: true }).click();
  const vy = page.locator(".pane:not([hidden]) section.view");
  await expect(vy.locator("article.kort")).toHaveCount(2, { timeout: 15_000 });
  return vy;
}

/** Öppnar chatten för kort nr `n` och returnerar dialogen. */
async function oppnaChatt(page, vy, n = 0) {
  await vy.locator("article.kort").nth(n).getByRole("button", { name: "Fråga" }).click();
  const ruta = page.getByRole("dialog", { name: "Lektionschatt" });
  await expect(ruta).toBeVisible();
  return ruta;
}

async function fraga(ruta, text) {
  await ruta.getByRole("textbox", { name: "Skriv en fråga till lektionen" }).fill(text);
  await ruta.getByRole("button", { name: "Skicka" }).click();
}

test.beforeEach(async ({ request }) => {
  await byggFixtur(request);
});
test.afterEach(async ({ request }) => {
  await toemArkivet(request);
});

test("kortet öppnar chatten, Escape stänger och fokus återvänder", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  const knapp = vy.locator("article.kort").nth(0).getByRole("button", { name: "Fråga" });
  await knapp.click();

  const ruta = page.getByRole("dialog", { name: "Lektionschatt" });
  await expect(ruta).toBeVisible();
  await expect(ruta.getByRole("heading", { level: 2 })).toHaveText(LEKTIONSNAMN);
  // getByRole, aldrig CSS: den synliga aria-hidden-kopian ligger i DOM:en men
  // inte i a11y-trädet.
  await expect(ruta.getByRole("status")).toHaveCount(1);

  await page.keyboard.press("Escape");
  await expect(ruta).toBeHidden();
  await expect(knapp).toBeFocused();

  expect(errors, errors.join("\n")).toEqual([]);
});

test("ett svar strömmar in och står kvar efter done", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await fejkaChat(page, {
    events: [
      { type: "token", text: "Du pratade om " },
      { type: "token", text: "bråk och procent." },
      { type: "done", result: { text: "Du pratade om bråk och procent." } },
    ],
  });

  const vy = await oppnaInspelningar(page);
  const ruta = await oppnaChatt(page, vy);
  await fraga(ruta, "Vad handlade lektionen om?");

  await expect(ruta.locator("li.rad .svar")).toHaveText("Du pratade om bråk och procent.");
  await expect(ruta.locator("li.rad .fraga")).toHaveText("Vad handlade lektionen om?");

  await page.keyboard.press("Escape");
  expect(errors, errors.join("\n")).toEqual([]);
});

test("Skicka är spärrad hela vägen till done, inte bara till första token", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Gamla appen släcker sin typing-flagga vid FÖRSTA token (app.js:2536-2537),
  // vilket återaktiverar knappen mitt i svaret och låter två strömmar skriva
  // till samma meddelande.
  await fejkaChat(page, {
    fordroj: 1500,
    events: [
      { type: "token", text: "Ett " },
      { type: "done", result: { text: "Ett svar." } },
    ],
  });

  const vy = await oppnaInspelningar(page);
  const ruta = await oppnaChatt(page, vy);
  await fraga(ruta, "Vad sa jag?");

  const skicka = ruta.getByRole("button", { name: "Svarar …" });
  await expect(skicka).toBeDisabled();

  await expect(ruta.locator("li.rad .svar")).toHaveText("Ett svar.", { timeout: 10_000 });
  await expect(ruta.getByRole("button", { name: "Skicka" })).toBeVisible();

  await page.keyboard.press("Escape");
  expect(errors, errors.join("\n")).toEqual([]);
});

test("ett svar från en annan lektion landar inte i den nya tråden", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await fejkaChat(page, {
    fordroj: 2000,
    events: [{ type: "done", result: { text: "SVAR FRÅN LEKTION A" } }],
  });

  const vy = await oppnaInspelningar(page);
  const ruta = await oppnaChatt(page, vy, 0);
  await fraga(ruta, "Fråga till A");

  // Byt lektion medan svaret fortfarande är i luften.
  await page.keyboard.press("Escape");
  await expect(ruta).toBeHidden();
  const ruta2 = await oppnaChatt(page, vy, 1);

  // Vänta förbi fördröjningen. Utan generationsvakt skriver A:s done in sig
  // i B:s tråd (app.js:2527 kollar bara att tråden inte är tom).
  await page.waitForTimeout(3000);
  await expect(ruta2.getByText("SVAR FRÅN LEKTION A")).toHaveCount(0);
  await expect(ruta2.locator("li.rad")).toHaveCount(0);

  await page.keyboard.press("Escape");
  expect(errors, errors.join("\n")).toEqual([]);
});

test("en upptagen GPU visar serverns egen text", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await fejkaChat(page, {
    status: 409,
    fel: "GPU upptagen med transkribering – försök igen strax.",
  });

  const vy = await oppnaInspelningar(page);
  const ruta = await oppnaChatt(page, vy);
  await fraga(ruta, "Vad sa jag?");

  await expect(ruta.getByTestId("chatt-statusrad")).toHaveText(
    "GPU upptagen med transkribering – försök igen strax.",
  );

  await page.keyboard.press("Escape");
  expect(errors.filter((e) => !/409|Failed to load/.test(e)), errors.join("\n")).toEqual([]);
});

test("en trasig historikpost ger ett synligt fel, inte en tyst tom chatt", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Gamla appens getJSON saknar resp.ok-koll (app.js:2983), och servern
  // svarar 404 med giltig JSON — så dess .catch triggas aldrig och läraren
  // får en chatt som svarar att det inte framgår av transkriptet.
  await page.route("**/api/history/*", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: '{"error":"finns inte"}',
    });
  });

  const vy = await oppnaInspelningar(page);
  const ruta = await oppnaChatt(page, vy);

  await expect(ruta.getByTestId("chatt-statusrad")).toHaveText(
    "Kunde inte läsa lektionens transkript — starta om appen och försök igen.",
  );

  await page.keyboard.press("Escape");
  expect(errors.filter((e) => !/404|Failed to load/.test(e)), errors.join("\n")).toEqual([]);
});

test("ett citat fäller ut källpanelen, och ett andra klick fäller ihop den", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await fejkaChat(page, {
    events: [{ type: "done", result: { text: "Du pratade om bråk [2]." } }],
  });

  const vy = await oppnaInspelningar(page);
  const ruta = await oppnaChatt(page, vy);
  await fraga(ruta, "Vad sa jag om bråk?");

  // Källa [2] är svarets första citat och visas därför som 1.
  const citat = ruta.getByRole("button", { name: "Visa källa 1 i transkriptet" });
  await expect(citat).toBeVisible();
  await expect(ruta.locator("aside.kallor")).toHaveCount(0);

  await citat.click();
  const panel = ruta.locator("aside.kallor");
  await expect(panel).toBeVisible();
  await expect(panel.locator("li.rad.vald .text")).toHaveText(SEGMENT[1]);

  await citat.click();
  await expect(panel).toHaveCount(0);

  await page.keyboard.press("Escape");
  expect(errors, errors.join("\n")).toEqual([]);
});

test("samtalet återkommer för samma lektion, men en annan börjar tom", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await fejkaChat(page, {
    events: [{ type: "done", result: { text: "Ett sparat svar." } }],
  });

  const vy = await oppnaInspelningar(page);
  const ruta = await oppnaChatt(page, vy, 0);
  await fraga(ruta, "Minns du det här?");
  await expect(ruta.locator("li.rad .svar")).toHaveText("Ett sparat svar.");

  await page.keyboard.press("Escape");
  await expect(ruta).toBeHidden();

  // Samma lektion, samma sidladdning: tråden ska komma tillbaka.
  const igen = await oppnaChatt(page, vy, 0);
  await expect(igen.locator("li.rad .fraga")).toHaveText("Minns du det här?");
  await expect(igen.locator("li.rad .svar")).toHaveText("Ett sparat svar.");

  await page.keyboard.press("Escape");

  // Den andra lektionen delar inte samtalet.
  const annan = await oppnaChatt(page, vy, 1);
  await expect(annan.locator("li.rad")).toHaveCount(0);

  await page.keyboard.press("Escape");
  expect(errors, errors.join("\n")).toEqual([]);
});
