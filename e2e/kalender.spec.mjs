/**
 * Kalendermaskineriet i lektionschatten (plan kalender-2): frågekortet,
 * anteckningsmodalen och deras samspel med förslagsboxen och
 * kalenderkommandots snabbväg. Google-kopplingsguiden (GoogleAnslutModal)
 * byggs den här omgången men täcks INTE här — den stod inte med i den
 * obligatoriska listan, och /api/calendar/connect/status går mot den
 * RIKTIGA backenden (fejkservern patchar inte calendar_google), så dess
 * exakta text beror på om google-auth-oauthlib råkar vara installerat i
 * miljön som kör testet.
 *
 * TÄCKER:
 *   1. Ett [KALENDERFÖRSLAG]-svar ger en förslagsbox med rätt titel/datum/tid.
 *   2. Trasig JSON i [KALENDERFÖRSLAG]-taggen läcker inte ut i chattbubblan (D3).
 *   3. Ett kalenderkommando i skrivraden ändrar förslaget UTAN LLM-anrop.
 *   4. Ogiltig tid ("99:99") avvisas och når aldrig /api/calendar/event (D11).
 *   5. Frågekortet visas på ett [KALENDERFRÅGOR]-svar, och svaret går vidare.
 *   6. "Lägg till" mot ett fejkat /api/calendar/event — lyckat och 400-fel.
 *   7. Anteckningsmodalen öppnas, redigeras och stängs med Escape (D8).
 *
 * TÄCKS INTE:
 *   - Riktig LLM-inferens — /api/chat fejkas i varje test som skickar en fråga.
 *   - Google-kopplingsguiden (GoogleAnslutModal) — se ovan.
 *   - Arkivsvarets kalenderväg — portas inte (bindande beslut, se
 *     .superpowers/sdd/kalender-recon.md).
 */
import { test, expect, failOnConsoleError } from "./helpers/app";

/** Fejkens AI-namngivning, serve_test_app.py:135-137. */
const LEKTIONSNAMN = "Bråk och procent — introduktion";

/** Serverns SSE-kontrakt: ett event per `data: <json>\n\n` (app/web/sse.py). */
function sseKropp(events) {
  return events.map((e) => "data: " + JSON.stringify(e) + "\n\n").join("");
}

/** Fejkar POST /api/chat med EN fast uppsättning events (eller ett HTTP-fel). */
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

/**
 * Fejkar POST /api/chat med EN SEKVENS av svar — anrop N använder
 * svarLista[N-1] (sista posten återanvänds om fler anrop kommer). Behövs för
 * frågekortets tvåstegsflöde: STEG 1 ([KALENDERFRÅGOR]) och sedan STEG 2
 * ([KALENDERFÖRSLAG]) är två SEPARATA POST:er mot samma URL.
 */
async function fejkaChattSekvens(page, svarLista) {
  let i = 0;
  await page.route("**/api/chat", async (route) => {
    const s = svarLista[Math.min(i, svarLista.length - 1)];
    i += 1;
    if (s.fordroj) await new Promise((klar) => setTimeout(klar, s.fordroj));
    if (s.status && s.status !== 200) {
      return route.fulfill({
        status: s.status,
        contentType: "application/json",
        body: JSON.stringify({ error: s.fel || "" }),
      });
    }
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseKropp(s.events || []),
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

/** Precis EN lektion — kalendertesterna behöver ingen samtalskarta/generationsvakt. */
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
  return lektioner;
}

async function oppnaInspelningar(page) {
  await page.goto("/next/");
  await page.getByRole("tab", { name: "Inspelningar", exact: true }).click();
  const vy = page.locator(".pane:not([hidden]) section.view");
  await expect(vy.locator("article.kort")).toHaveCount(1, { timeout: 15_000 });
  return vy;
}

async function oppnaChatt(page, vy) {
  await vy.locator("article.kort").nth(0).getByRole("button", { name: "Fråga" }).click();
  const ruta = page.getByRole("dialog", { name: "Lektionschatt" });
  await expect(ruta).toBeVisible();
  await expect(ruta.getByRole("heading", { level: 2 })).toHaveText(LEKTIONSNAMN);
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

test("ett [KALENDERFÖRSLAG]-svar ger en förslagsbox med rätt titel, datum och tid", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await fejkaChat(page, {
    events: [
      { type: "token", text: "Visst, här är ett förslag." },
      {
        type: "done",
        result: {
          text:
            "Visst, här är ett förslag.\n" +
            '[KALENDERFÖRSLAG] {"title": "Läxförhör bråk", "date": "2026-08-03", "time": "10:45", "end_date": null, "desc": "Ta med miniräknare."}',
        },
      },
    ],
  });

  const vy = await oppnaInspelningar(page);
  const ruta = await oppnaChatt(page, vy);
  await fraga(ruta, "Boka ett läxförhör om bråk");

  const box = ruta.locator("section.box");
  await expect(box).toBeVisible();
  await expect(box.getByLabel("Titel på händelsen")).toHaveValue("Läxförhör bråk");
  await expect(box.getByLabel("Datum")).toHaveValue("2026-08-03");
  await expect(box.getByLabel("Tid")).toHaveValue("10:45");

  await page.keyboard.press("Escape");
  expect(errors, errors.join("\n")).toEqual([]);
});

test("trasig JSON i [KALENDERFÖRSLAG]-taggen läcker inte ut i chattbubblan (D3)", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await fejkaChat(page, {
    events: [
      { type: "done", result: { text: '[KALENDERFÖRSLAG] {"title": "Prov", trasig json här' } },
    ],
  });

  const vy = await oppnaInspelningar(page);
  const ruta = await oppnaChatt(page, vy);
  await fraga(ruta, "Boka ett prov");

  const svar = ruta.locator("li.rad .svar");
  // Bubblan visar den GENERISKA fallback-texten, aldrig den råa taggraden.
  await expect(svar).toHaveText("Kalenderdelen av svaret gick inte att tolka.");
  await expect(svar).not.toContainText("KALENDERFÖRSLAG");
  await expect(svar).not.toContainText("trasig json här");
  // Statusraden bär den mer specifika förklaringen.
  await expect(ruta.getByTestId("chatt-statusrad")).toHaveText(
    "Kalenderförslaget gick inte att tolka — skriv gärna om vad du vill boka.",
  );
  await expect(ruta.locator("section.box")).toHaveCount(0);

  await page.keyboard.press("Escape");
  expect(errors, errors.join("\n")).toEqual([]);
});

test("ett kalenderkommando i skrivraden ändrar förslaget utan LLM-anrop", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  let anrop = 0;
  await page.route("**/api/chat", async (route) => {
    anrop += 1;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseKropp([
        {
          type: "done",
          result: {
            text: '[KALENDERFÖRSLAG] {"title": "Prov", "date": "2026-08-05", "time": "09:10", "end_date": null, "desc": ""}',
          },
        },
      ]),
    });
  });

  const vy = await oppnaInspelningar(page);
  const ruta = await oppnaChatt(page, vy);
  await fraga(ruta, "Boka ett prov");

  const box = ruta.locator("section.box");
  await expect(box).toBeVisible();
  expect(anrop, "det inledande förslaget ska ha gått via /api/chat").toBe(1);

  await fraga(ruta, "flytta till onsdag 14:30");

  await expect(box.getByLabel("Tid")).toHaveValue("14:30");
  const datumEfter = await box.getByLabel("Datum").inputValue();
  // getDay(): 0=sön ... 3=ons. T12:00:00 undviker tidszonsglidning (samma
  // regel som tid.js:isoEtikett).
  expect(new Date(datumEfter + "T12:00:00").getDay()).toBe(3);
  await expect(ruta.locator("li.rad .svar").last()).toContainText("Klart — jag ändrade");

  // Kärnpunkten: kommandot löstes lokalt. Inget NYTT anrop mot /api/chat.
  expect(anrop, "kalenderkommandot ska INTE ha gått via /api/chat").toBe(1);

  await page.keyboard.press("Escape");
  expect(errors, errors.join("\n")).toEqual([]);
});

test('ogiltig tid ("99:99") avvisas och når aldrig servern (D11)', async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await fejkaChattSekvens(page, [
    {
      events: [
        {
          type: "done",
          result: {
            text: '[KALENDERFÖRSLAG] {"title": "Prov", "date": "2026-08-05", "time": "09:10", "end_date": null, "desc": ""}',
          },
        },
      ],
    },
    {
      // "flytta till 99:99" matchar inget mönster i kommando.js (den
      // ogiltiga tiden lämnas orörd) och faller därför igenom till modellen
      // — det här är dess svar, utan kalendertagg.
      events: [{ type: "done", result: { text: "Jag är inte säker på vad du menar — kan du skriva om det?" } }],
    },
  ]);

  const vy = await oppnaInspelningar(page);
  const ruta = await oppnaChatt(page, vy);
  await fraga(ruta, "Boka ett prov");

  const box = ruta.locator("section.box");
  await expect(box.getByLabel("Tid")).toHaveValue("09:10");

  await fraga(ruta, "flytta till 99:99");

  await expect(ruta.locator("li.rad .svar").last()).toHaveText(
    "Jag är inte säker på vad du menar — kan du skriva om det?",
  );
  // Den ogiltiga tiden accepterades INTE — fältet står kvar oförändrat.
  await expect(box.getByLabel("Tid")).toHaveValue("09:10");

  // Och: den ogiltiga strängen finns ingenstans i det som SKULLE skickas
  // till kalenderservern om läraren nu godkänner förslaget.
  let kropp = null;
  await page.route("**/api/calendar/event", async (route) => {
    kropp = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, id: "abc", link: "https://calendar.google.com/x" }),
    });
  });
  await ruta.getByRole("button", { name: "Lägg till", exact: true }).click();
  await expect(box.locator(".klar")).toBeVisible();

  expect(kropp).not.toBeNull();
  expect(kropp.start).not.toContain("99:99");
  expect(kropp.start).toContain("09:10");

  await page.keyboard.press("Escape");
  expect(errors, errors.join("\n")).toEqual([]);
});

test("frågekortet visas på ett [KALENDERFRÅGOR]-svar, och svaret går vidare", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await fejkaChattSekvens(page, [
    {
      events: [
        {
          type: "done",
          result: {
            text:
              "Visst!\n" +
              '[KALENDERFRÅGOR] {"fragor": [{"q": "Är det ett prov eller ett läxförhör?", "alternativ": ["Prov", "Läxförhör"]}]}',
          },
        },
      ],
    },
    {
      events: [
        {
          type: "done",
          result: {
            text: '[KALENDERFÖRSLAG] {"title": "Prov bråk", "date": "2026-08-05", "time": "09:10", "end_date": null, "desc": ""}',
          },
        },
      ],
    },
  ]);

  const vy = await oppnaInspelningar(page);
  const ruta = await oppnaChatt(page, vy);
  await fraga(ruta, "Boka ett prov om bråk");

  const kort = page.getByRole("dialog", { name: "Kalenderhändelsen — några frågor först" });
  await expect(kort).toBeVisible();
  await expect(kort.getByText("Är det ett prov eller ett läxförhör?")).toBeVisible();

  const alt = kort.getByRole("button", { name: "Prov", exact: true });
  await alt.click();
  await expect(alt).toHaveAttribute("aria-pressed", "true");

  await kort.getByRole("button", { name: "Skapa förslaget" }).click();
  await expect(kort).toBeHidden();

  // Svaret gick vidare: STEG 2 kördes, ett riktigt förslag landade.
  const box = ruta.locator("section.box");
  await expect(box).toBeVisible();
  await expect(box.getByLabel("Titel på händelsen")).toHaveValue("Prov bråk");

  await page.keyboard.press("Escape");
  expect(errors, errors.join("\n")).toEqual([]);
});

test('"Lägg till" mot ett fejkat /api/calendar/event — lyckat och ett 400-fel', async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await fejkaChat(page, {
    events: [
      {
        type: "done",
        result: {
          text: '[KALENDERFÖRSLAG] {"title": "Prov", "date": "2026-08-05", "time": "09:10", "end_date": null, "desc": ""}',
        },
      },
    ],
  });

  const vy = await oppnaInspelningar(page);
  const ruta = await oppnaChatt(page, vy);
  await fraga(ruta, "Boka ett prov");

  const box = ruta.locator("section.box");
  await expect(box).toBeVisible();

  // 400-fel — statusraden visar serverns EGEN text ordagrant.
  await page.route("**/api/calendar/event", async (route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ error: 'Inte ansluten till Google Kalender — klicka "Anslut Google-konto" först.' }),
    });
  });
  await ruta.getByRole("button", { name: "Lägg till", exact: true }).click();
  await expect(ruta.getByTestId("chatt-statusrad")).toHaveText(
    'Inte ansluten till Google Kalender — klicka "Anslut Google-konto" först.',
  );
  // Knappen är klickbar igen — inte låst i "Lägger till …".
  await expect(box.getByRole("button", { name: "Lägg till", exact: true })).toBeEnabled();
  await page.unroute("**/api/calendar/event");

  // Lyckat försök.
  await page.route("**/api/calendar/event", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, id: "xyz", link: "https://calendar.google.com/event?eid=xyz" }),
    });
  });
  await ruta.getByRole("button", { name: "Lägg till", exact: true }).click();
  await expect(box.locator(".klar")).toContainText("Tillagd i Google Kalender — Prov");
  await expect(box.getByRole("link", { name: "Öppna i Google Kalender" })).toHaveAttribute(
    "href",
    "https://calendar.google.com/event?eid=xyz",
  );

  await page.keyboard.press("Escape");
  expect(errors.filter((e) => !/400|Failed to load/.test(e)), errors.join("\n")).toEqual([]);
});

test("anteckningsmodalen öppnas, redigeras och stängs med Escape (D8)", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await fejkaChat(page, {
    events: [
      {
        type: "done",
        result: {
          text: '[KALENDERFÖRSLAG] {"title": "Prov", "date": "2026-08-05", "time": "09:10", "end_date": null, "desc": "Ta med miniräknare."}',
        },
      },
    ],
  });

  const vy = await oppnaInspelningar(page);
  const ruta = await oppnaChatt(page, vy);
  await fraga(ruta, "Boka ett prov");

  const box = ruta.locator("section.box");
  await expect(box).toBeVisible();
  await box.getByRole("button", { name: /Ta med miniräknare/ }).click();

  const modal = page.getByRole("dialog", { name: "Anteckning i kalenderposten" });
  await expect(modal).toBeVisible();
  const falt = modal.getByRole("textbox", { name: "Anteckning i kalenderposten" });
  await expect(falt).toHaveValue("Ta med miniräknare.");

  await falt.fill("Ta med miniräknare och linjal.");

  await page.keyboard.press("Escape");
  await expect(modal).toBeHidden();
  // D8: gamla appens läsmodal saknade Escape-hantering helt, så Escape föll
  // vidare och stängde HELA lektionsoverlayen. Här stänger Escape BARA
  // anteckningsmodalen — chatten står kvar öppen, med ändringen bevarad.
  await expect(ruta).toBeVisible();
  await expect(box.getByText("Ta med miniräknare och linjal.")).toBeVisible();

  await page.keyboard.press("Escape");
  expect(errors, errors.join("\n")).toEqual([]);
});
