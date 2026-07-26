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

/**
 * Raderar varje lektion. Tar historikposten och mappen med sig.
 *
 * Spelaren (task 3) laddar mediet med preload="metadata" så fort transkriptet
 * öppnas. Webbläsaren avbryter den förfrågan ASYNKRONT när testet är klart och
 * sidan lämnas — inte synkront när testfunktionen returnerar. Kommer DELETE:n
 * hit innan avbrottet hunnit slå igenom svarar backendens rmtree() 409 ("en
 * fil kan vara öppen", server.py:1032-1034), trots att ingenting utom
 * testkörningens EGEN, redan avslutade sida någonsin höll filen öppen. Ett
 * kort, begränsat omförsök löser just den kapplöpningen; ett verkligt låst
 * dokument ger ändå upp och syns som ett äkta testfel efter sista försöket.
 */
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

test("ljudspelaren får rätt källa och renderar inget videoelement", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  const ljud = ruta.locator("audio");
  await expect(ljud).toHaveCount(1);
  await expect(ljud).toHaveAttribute("src", /^\/api\/media\?path=/);
  // Ingen video: fixturen är en .wav.
  await expect(ruta.locator("video")).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("en 404 från /api/media ger ett synligt fel, inte en tyst spelare", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Fejka BARA mediet; allt annat går till riktiga backenden.
  await page.route("**/api/media?**", (route) =>
    route.fulfill({ status: 404, contentType: "application/json", body: '{"error":"finns inte"}' }),
  );

  const ruta = await oppnaTranskript(page);
  await expect(ruta.getByTestId("transkript-statusrad")).toHaveText(
    "Kunde inte spela mediet — filen kan ha flyttats eller tagits bort.",
  );

  // Konsolen får ett nätverksfel av webbläsaren själv när <audio> misslyckas;
  // det är inte ett applikationsfel och räknas inte.
  expect(errors.filter((e) => !/Failed to load|404/.test(e)), errors.join("\n")).toEqual([]);
});

/**
 * En 44 byte lång, giltig och helt tom WAV. Chromium läser metadata utan att
 * fyra `error`, så ljudgrenen blir deterministisk utan en riktig ljudfil.
 */
function tystWav() {
  const b = Buffer.alloc(44);
  b.write("RIFF", 0);
  b.writeUInt32LE(36, 4);
  b.write("WAVE", 8);
  b.write("fmt ", 12);
  b.writeUInt32LE(16, 16);
  b.writeUInt16LE(1, 20);   // PCM
  b.writeUInt16LE(1, 22);   // mono
  b.writeUInt32LE(8000, 24);
  b.writeUInt32LE(16000, 28);
  b.writeUInt16LE(2, 32);
  b.writeUInt16LE(16, 34);
  b.write("data", 36);
  b.writeUInt32LE(0, 40);   // noll sampel
  return b;
}

test("en okänd längd spärrar spolningen i stället för att gissa", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Noll sampel ⇒ längd 0. Gamla appen faller i det läget tillbaka på
  // AUDIO_DUR = 150 s (app.js:2103, 297), så ett klick i spåret räknar mot
  // fel total och landar helt fel på en lång lektion.
  await page.route("**/api/media?**", (route) =>
    route.fulfill({ status: 200, contentType: "audio/wav", body: tystWav() }),
  );

  const ruta = await oppnaTranskript(page);
  const spar = ruta.getByRole("slider", { name: "Sök i uppspelningen" });
  await expect(spar).toHaveAttribute("aria-disabled", "true");
  await expect(spar).toHaveAttribute("tabindex", "-1");
  await expect(ruta.getByText("--:--")).toBeVisible();

  expect(errors.filter((e) => !/Failed to load/.test(e)), errors.join("\n")).toEqual([]);
});

test("en video begärs som video och faller tillbaka på ljudet när den inte går att förbereda", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Låtsas att posten är en .mkv. Riktiga svaret hämtas och lappas, som
  // kapplöpningstestet i inspelningar-kartotek.spec.mjs:448-514.
  await page.route("**/api/history/*", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const svar = await route.fetch();
    const post = await svar.json();
    post.video = { path: "C:\\Transkriberingar\\lektion.mkv" };
    await route.fulfill({ response: svar, body: JSON.stringify(post) });
  });

  const videoanrop = [];
  await page.route("**/api/media?**", async (route) => {
    const url = route.request().url();
    if (url.includes("want=video")) {
      videoanrop.push(url);
      // ensure_web_video transkodar .mkv vid första begäran och kan kasta —
      // servern svarar då 500 (server.py:1703-1707). Fördröjningen gör att
      // "Förbereder videon …" hinner bli synlig och alltså assertbar.
      await new Promise((r) => setTimeout(r, 1200));
      return route.fulfill({ status: 500, contentType: "application/json", body: '{"error":"ffmpeg"}' });
    }
    return route.fulfill({ status: 200, contentType: "audio/wav", body: tystWav() });
  });

  const ruta = await oppnaTranskript(page);

  // Video först, med want=video — annars strömmar servern .mkv:n rå.
  await expect(ruta.locator("video")).toHaveAttribute("src", /want=video/);
  await expect(ruta.getByText("Förbereder videon …")).toBeVisible();

  // Och när den inte går att förbereda: ljudet, inte en död ruta.
  await expect(ruta.locator("audio")).toHaveCount(1, { timeout: 10_000 });
  await expect(ruta.locator("video")).toHaveCount(0);
  await expect(ruta.locator("audio")).toHaveAttribute("src", /^\/api\/media\?path=[^&]*$/);
  await expect(ruta.getByTestId("transkript-statusrad")).toHaveText(
    "Kunde inte förbereda videon — spelar ljudet.",
  );
  expect(videoanrop, "videon begärdes aldrig som video").toHaveLength(1);

  expect(errors.filter((e) => !/Failed to load|500/.test(e)), errors.join("\n")).toEqual([]);
});

test("hastigheten cyklar och skrivs med decimalkomma", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  const knapp = ruta.getByRole("button", { name: /^Uppspelningshastighet/ });
  await expect(knapp).toHaveText("1×");
  await knapp.click();
  await expect(knapp).toHaveText("1,25×");
  await knapp.click();
  await expect(knapp).toHaveText("1,5×");

  // Hastigheten når faktiskt mediaelementet — annars är knappen dekoration.
  const rate = await ruta.locator("audio").evaluate((el) => el.playbackRate);
  expect(rate, "playbackRate följde inte med knappen").toBeCloseTo(1.5, 5);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("mellanslag växlar uppspelning men inte medan fokus står i ett fält", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  const hastighet = ruta.getByRole("button", { name: /^Uppspelningshastighet/ });

  // Mellanslag på en FOKUSERAD KNAPP ska trycka knappen, inte spela upp.
  await hastighet.focus();
  await page.keyboard.press("Space");
  await expect(hastighet).toHaveText("1,25×");

  expect(errors, errors.join("\n")).toEqual([]);
});

test("ett enkelklick i spåret spolar dit, inte bara dragningen", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // paKlick är borta — pointerdown ska ensam bära det gamla enkelklicket.
  // Utan det här testet skulle en framtida ändring kunna tysta klicket och
  // bara låta dragningen fungera, utan att någon spärr slog till.
  const ruta = await oppnaTranskript(page);
  const spar = ruta.getByRole("slider", { name: "Sök i uppspelningen" });
  await expect(spar).toHaveAttribute("aria-disabled", "false");

  const langd = await ruta.locator("audio").evaluate((el) => el.duration);
  const box = await spar.boundingBox();
  await spar.click({ position: { x: box.width * 0.25, y: box.height / 2 } });

  const forvantat = langd * 0.25;
  const valuenow = Number(await spar.getAttribute("aria-valuenow"));
  expect(valuenow, "aria-valuenow följde inte klicket").toBeGreaterThan(forvantat - 3);
  expect(valuenow, "aria-valuenow följde inte klicket").toBeLessThan(forvantat + 3);

  const currentTime = await ruta.locator("audio").evaluate((el) => el.currentTime);
  expect(currentTime, "currentTime följde inte klicket").toBeGreaterThan(forvantat - 3);
  expect(currentTime, "currentTime följde inte klicket").toBeLessThan(forvantat + 3);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("ett klick var som helst på raden hoppar dit", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  const rader = ruta.locator("li.rad");

  // Klicka på TEXTEN, inte på tidkoden. Gamla appen gjorde bara tidkoden
  // klickbar (app.js:5538 vs 5543-5549).
  await rader.nth(2).locator(".text").click();
  let t = await ruta.locator("audio").evaluate((el) => el.currentTime);
  expect(t, "klicket på radens text spolade inte dit").toBeCloseTo(5.0, 1);

  // Och tidkoden fungerar fortfarande — den ligger i samma knapp.
  await rader.nth(1).locator(".tid").click();
  t = await ruta.locator("audio").evaluate((el) => el.currentTime);
  expect(t, "klicket på tidkoden spolade inte dit").toBeCloseTo(2.4, 1);

  // Stäng rutan. Till skillnad från alla tidigare tester i den här filen har
  // hoppaTillRad faktiskt startat uppspelning mot RIKTIGA backend-mediet (inget
  // /api/media-route här) — lämnas rutan öppen håller webbläsaren filen öppen
  // in i afterEach, och toemArkivets DELETE kan kapplöpa mot den även efter dess
  // ordinarie omförsök. actions.js:210-214 dokumenterar precis den här vägen:
  // stängning släpper filen med en gång via slappMedia.
  await page.keyboard.press("Escape");
  await expect(ruta).toBeHidden();

  expect(errors, errors.join("\n")).toEqual([]);
});

test("en textmarkering hindrar hoppet", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  const rader = ruta.locator("li.rad");

  // Markera texten i sista raden med musen: pointerdown, dra, släpp.
  const ruta3 = await rader.nth(2).locator(".text").boundingBox();
  await page.mouse.move(ruta3.x + 4, ruta3.y + ruta3.height / 2);
  await page.mouse.down();
  await page.mouse.move(ruta3.x + ruta3.width - 4, ruta3.y + ruta3.height / 2, { steps: 8 });
  await page.mouse.up();

  const t = await ruta.locator("audio").evaluate((el) => el.currentTime);
  expect(t, "en markering tolkades som ett hopp — lärare kopierar citat").toBe(0);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("egen scroll släpper följandet och knappen tar tillbaka det", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  const folj = ruta.getByRole("button", { name: "Följ uppspelningen" });

  // Följer från start: knappen ska inte finnas.
  await expect(folj).toHaveCount(0);

  // Ett hjulsvep i listan släpper följandet.
  await ruta.locator("ol.rader").hover();
  await page.mouse.wheel(0, 120);
  await expect(folj).toHaveCount(1);

  await folj.click();
  await expect(folj).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("ett radklick återtar följandet trots att pointerdown släpper det", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  await ruta.locator("ol.rader").hover();
  await page.mouse.wheel(0, 120);
  await expect(ruta.getByRole("button", { name: "Följ uppspelningen" })).toHaveCount(1);

  await ruta.locator("li.rad").nth(1).locator(".text").click();
  await expect(ruta.getByRole("button", { name: "Följ uppspelningen" })).toHaveCount(0);

  // Radklicket har startat uppspelning mot RIKTIGA backend-mediet, som i "ett
  // klick var som helst på raden hoppar dit" ovan — stäng rutan så filen
  // släpps innan afterEach:s DELETE.
  await page.keyboard.press("Escape");
  await expect(ruta).toBeHidden();

  expect(errors, errors.join("\n")).toEqual([]);
});

test("markören sparas och dyker upp i raden", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const ruta = await oppnaTranskript(page);
  await ruta.getByRole("button", { name: "Markera" }).click();

  await expect(ruta.locator(".markor")).toHaveCount(1);
  await expect(ruta.getByTestId("transkript-statusrad")).toHaveText("");

  expect(errors, errors.join("\n")).toEqual([]);
});

test("en markör som servern tyst kastar ger ett synligt fel", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Servern svarar 200 med count: 0 när historikposten saknar lektionsrad
  // (app/db.py:804-806). Gamla appen läser aldrig count (app.js:1679-1685), så
  // knappen blir en tyst no-op. Backenden är orörd — fixen är på klienten.
  await page.route("**/api/recordings/*/markers", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: '{"markers":[],"count":0}',
    });
  });

  const ruta = await oppnaTranskript(page);
  await ruta.getByRole("button", { name: "Markera" }).click();

  await expect(ruta.getByTestId("transkript-statusrad")).toHaveText(
    "Markören kunde inte sparas — inspelningen saknar en lektionspost att koppla den till.",
  );
  await expect(ruta.locator(".markor")).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});
