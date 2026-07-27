// Plan B3b: e2e för FRÅGE-LÄGET i Inspelningar-fliken (/next/) — RAG över SSE,
// genomsökningen, sifferkällorna och kartotekets lift/dim. Kör mot den riktiga
// backenden med fejkad inferens (e2e/serve_test_app.py): retrievalen,
// FTS5-indexet och SSE-transporten är oförfalskade; bara själva
// svarsgenereringen är stubbad.
//
// TÄCKER:
//   1. att genomsökningen renderar korten i SERVERNS ordning med ÄKTA
//      träffantal, och att utrullningen når alla kort,
//   2. att svaret strömmar in och att [1] blir en markör, inte rå text,
//   3. att läsbordet säger "Svaret bygger på …" efter done,
//   4. att kartotekets kort får data-stage — lift för träffar, dim för resten
//      — och att INGET stadie sätts utan aktiv fråga,
//   5. att ett fel renderas i SVARSYTAN och inte som ett svar (409 fejkad),
//   6. att en ny fråga överger den föregående strömmen (generationsvakten),
//   7. att fråge-läget är default och att körknappen är aktiv.
//
// Punkt 4 och 6 är planens bärande krav. Punkt 4 vaktar att stadiet kommer
// från servern och inte från en klientmatchning på frågans ord — gamla appen
// hade den buggen och kommentaren app.js:3384-3386 säger att den togs bort.
// Punkt 6 vaktar en kapplöpning som är osynlig tills den inträffar.
//
// TÄCKS INTE, och det är avsiktligt:
//   · Den SEMANTISKA OMSÖKNINGEN (två scan_plan i samma ström). Den kräver en
//     fråga som ger noll ordträffar men ändå har ett ämnesmässigt närliggande
//     transkript, vilket fejkens tre meningar inte räcker till. Backend har
//     egen täckning: tests/test_web_server.py:1125.
//   · Källmodalen, zoom-modalen och följdfrågorna — B3c.
//   · prefers-reduced-motion-grenen i utrullningen.
//
// FEJKENS TEMPO ÄR EN DEL AV KONTRAKTET. fake_answer (serve_test_app.py:90-104)
// strömmar "[FEJK svar] Det togs upp i lektionen [1]." ordvis med 0,3 s per ord
// och 1,5 s tänkpaus före första token, uttryckligen för att progressionen ska
// hinna synas. Vänta därför på DOM-TILLSTÅND, aldrig på klockan.
//
// STÄDNING: filen sorteras FÖRST av inspelningar-specarna (fraga < kartotek <
// paneler < sok) och delar server med de övriga. afterEach tömmer arkivet.
import { test, expect, failOnConsoleError } from "./helpers/app";

/** Tre lektioner, alla med fejkens transkript ("… bråk och procent …"). */
const FIXTUR = [
  { datum: "2026-04-02", sal: "A1", group_name: "9A", course_name: "Matematik 2b" },
  { datum: "2026-03-30", sal: "A2", group_name: "9A", course_name: "Matematik 2b" },
  { datum: "2026-03-25", sal: "B3", group_name: "9B", course_name: "Fysik 1a" },
];

/** Ord ur fejkens transkript. Ger ordträff i alla tre lektionerna. */
const ORD = "bråk";

async function toemArkivet(request) {
  const lektioner = await (await request.get("/api/lessons")).json();
  for (const l of lektioner) {
    const r = await request.delete("/api/lessons/" + l.id);
    expect(r.ok(), `DELETE /api/lessons/${l.id} svarade ${r.status()}`).toBeTruthy();
  }
}

/**
 * Skapar de tre lektionerna och FÖRKONTROLLERAR att frågan verkligen ger
 * ordträffar. Utan det blir en trasig fixtur grön av fel skäl: noll träffar
 * ser ut som en fungerande genomsökning med tomt resultat.
 */
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

  for (let i = 0; i < FIXTUR.length; i++) {
    const r = await request.post("/api/transcribe", {
      data: { source: sample.path, model_id: modell.id, language: "sv", formats: ["srt"] },
      timeout: 60_000,
    });
    expect(r.status(), "POST /api/transcribe misslyckades för post " + i).toBe(200);
  }

  const skapade = await (await request.get("/api/lessons")).json();
  expect(skapade, "Tre transkriberingar skulle ge tre lektionsrader").toHaveLength(FIXTUR.length);

  for (let i = 0; i < FIXTUR.length; i++) {
    const r = await request.patch("/api/lessons/" + skapade[i].id, { data: FIXTUR[i] });
    expect(r.ok(), `PATCH /api/lessons/${skapade[i].id} svarade ${r.status()}`).toBeTruthy();
  }

  const kontroll = await (await request.get("/api/search?q=" + encodeURIComponent(ORD))).json();
  expect(
    (kontroll.hits || []).length,
    `Fejktranskriptet innehåller inte "${ORD}" i alla tre lektionerna — ` +
      "uppdatera ORD efter serve_test_app.py:41-46",
  ).toBe(FIXTUR.length);
}

async function oppnaInspelningar(page) {
  await page.goto("/next/");
  await page.getByRole("button", { name: "Inspelningar", exact: true }).click();
  const vy = page.locator(".pane:not([hidden]) section.view");
  await expect(vy.locator("article.kort")).toHaveCount(FIXTUR.length, { timeout: 15_000 });
  return vy;
}

function sokfalt(vy) {
  const rot = vy.locator("section.sok");
  return {
    input: rot.getByLabel("Sök i arkivet"),
    kor: rot.getByRole("button", { name: /^Fråga$|^Sök$|^Söker/ }),
    fragaAi: rot.getByRole("button", { name: "Fråga AI" }),
    sokOrd: rot.getByRole("button", { name: "Sök ord" }),
  };
}

/**
 * Ställer frågan och väntar in att SSE-svaret börjat komma.
 *
 * OBS: waitForResponse löser ut när RESPONSHUVUDENA anlänt, inte när kroppen
 * lästs färdigt. För en ström betyder det "servern har svarat", inte "strömmen
 * är slut". Behöver ett test det senare — som rensningstestet nedan — måste det
 * dessutom invänta response.finished().
 */
async function stallFraga(page, vy, fraga) {
  const svar = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/search/ask",
  );
  await sokfalt(vy).input.fill(fraga);
  await sokfalt(vy).kor.click();
  return await svar;
}

test.beforeEach(async ({ request }) => {
  await byggFixtur(request);
});

test.afterEach(async ({ request }) => {
  await toemArkivet(request);
});

test("Fråga (/next/): fråge-läget är default och körknappen är aktiv", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  const f = sokfalt(vy);

  await expect(f.fragaAi).toHaveAttribute("aria-pressed", "true");
  await expect(f.sokOrd).toHaveAttribute("aria-pressed", "false");
  await expect(f.kor).toHaveText("Fråga");
  await expect(f.kor).toBeEnabled();
  // Ingen genomsökning innan något frågats.
  await expect(vy.locator("section.genomsokning")).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Fråga (/next/): genomsökningen visar serverns ordning och äkta träffantal", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await stallFraga(page, vy, ORD);

  const teater = vy.locator("section.genomsokning");
  await expect(teater).toBeVisible();

  // Utrullningen ska nå ALLA kort — inte fastna halvvägs.
  await expect(teater.locator("li.ruta")).toHaveCount(FIXTUR.length);

  // ÄKTA träffantal: alla tre lektionerna bär samma transkript, så alla tre
  // ska sluta i träff-tillståndet. Ett kort som stannar i "läst" betyder att
  // scan_result aldrig lästes.
  await expect(teater.locator('li.ruta[data-scan="traff"]')).toHaveCount(FIXTUR.length, {
    timeout: 20_000,
  });
  await expect(teater.locator("p.ticker")).toContainText("Genomsökte 3 inspelningar");

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Fråga (/next/): svaret strömmar in och sifferkällan blir en markör", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await stallFraga(page, vy, ORD);

  const svar = vy.locator("section.svar");
  await expect(svar).toBeVisible({ timeout: 20_000 });
  await expect(svar.locator("p.text")).toContainText("[FEJK svar]", { timeout: 20_000 });

  // MARKÖREN är kravet: [1] ska ha blivit ett element, inte stå kvar som text.
  await expect(svar.locator("span.cite")).toHaveCount(1, { timeout: 20_000 });
  await expect(svar.locator("span.cite")).toHaveText("1");
  await expect(svar.locator("p.text")).not.toContainText("[1]");

  // Rubriken räknar bara citerade källor — fejksvaret citerar exakt en.
  await expect(svar.locator("h2.rubrik")).toHaveText("Svar — 1 källa");
  await expect(svar.locator("li.kalla")).toHaveCount(1);
  await expect(svar).toContainText("migreras i en senare plan");

  // Läsbordet efter done.
  await expect(vy.locator("section.genomsokning p.bordsrubrik")).toContainText(
    "Svaret bygger på",
  );

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Fråga (/next/): kartotekets kort lyfts och dämpas efter serverns träffar", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);

  // Utan aktiv fråga har INGET kort ett stadie.
  await expect(vy.locator("div.hylsa[data-stage]")).toHaveCount(0);

  await stallFraga(page, vy, ORD);
  await expect(vy.locator("section.svar span.cite")).toHaveCount(1, { timeout: 20_000 });

  // Efter done styr done.result.sources: de citerade lyfts, resten dämpas.
  // Summan måste vara alla tre — annars har utrullningen inte nått klart.
  const lyfta = vy.locator('div.hylsa[data-stage="lift"]');
  const dampade = vy.locator('div.hylsa[data-stage="dim"]');
  await expect(vy.locator("div.hylsa[data-stage]")).toHaveCount(FIXTUR.length);
  expect(
    (await lyfta.count()) + (await dampade.count()),
    "Varje avslöjat kort ska ha antingen lift eller dim",
  ).toBe(FIXTUR.length);
  expect(await lyfta.count(), "Minst ett kort ska vara lyft").toBeGreaterThan(0);

  // Och en rensning tar bort stadierna igen.
  await vy.locator("section.genomsokning").getByRole("button", { name: /Ny fråga/ }).click();
  await expect(vy.locator("div.hylsa[data-stage]")).toHaveCount(0);
  await expect(vy.locator("article.kort")).toHaveCount(FIXTUR.length);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Fråga (/next/): ett fel renderas i svarsytan, inte som ett svar", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);

  // Fejkarbitern har alltid ledig GPU, så 409:an måste injiceras. Det som
  // prövas är klientens visningsväg, inte serverns förmåga att svara 409.
  await page.route("**/api/search/ask", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ error: "GPU upptagen med transkribering – försök igen strax." }),
    }),
  );

  await sokfalt(vy).input.fill(ORD);
  await sokfalt(vy).kor.click();

  const fel = vy.locator("p.fragafel");
  await expect(fel).toContainText("Kunde inte söka: GPU upptagen med transkribering");
  // FELET ÄR INTE ETT SVAR: svarskortet får inte finnas.
  await expect(vy.locator("section.svar")).toHaveCount(0);
  // Och körknappen ska ha släppt.
  await expect(sokfalt(vy).kor).toBeEnabled();

  await page.unroute("**/api/search/ask");
  // Chrome loggar den injicerade 409:an som "Failed to load resource". Det är
  // testets egen fejk, inte ett appfel — allt annat räknas fortfarande.
  const appfel = errors.filter((e) => !/Failed to load resource/.test(e));
  expect(appfel, appfel.join("\n")).toEqual([]);
});

test("Fråga (/next/): en rensning överger den pågående strömmen", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);

  // Löftet skapas FÖRE klicket och löses först när hela strömmen lästs.
  const strommen = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/search/ask",
  );
  await sokfalt(vy).input.fill(ORD);
  await sokfalt(vy).kor.click();

  // Vänta in att genomsökningen syns — då är strömmen igång på riktigt.
  await expect(vy.locator("section.genomsokning")).toBeVisible({ timeout: 20_000 });

  await vy.locator("section.genomsokning").getByRole("button", { name: /Ny fråga/ }).click();
  await expect(vy.locator("section.genomsokning")).toHaveCount(0);

  // KRAVET: strömmen rullar vidare hos servern (streamPost saknar
  // AbortController), men generationsvakten ska filtrera bort varje event.
  // Vänta in att den faktiskt tagit slut, och kontrollera först DÄREFTER att
  // ingenting återuppstått. Utan väntan mäter testet ett tomt fönster.
  //
  // response.finished() är det som gör väntan äkta: waitForResponse ovan löser
  // ut redan på responshuvudena, alltså långt innan den fyra sekunder långa
  // fejkströmmen skickat sitt sista token.
  const svarsstrom = await strommen;
  await svarsstrom.finished();
  await expect(vy.locator("section.genomsokning")).toHaveCount(0);
  await expect(vy.locator("section.svar")).toHaveCount(0);
  await expect(sokfalt(vy).input).toHaveValue("");

  expect(errors, errors.join("\n")).toEqual([]);
});
