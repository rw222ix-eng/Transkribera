// Plan B3b: e2e för FRÅGE-LÄGET i Inspelningar-fliken (/next/) — RAG över SSE,
// genomsökningen, sifferkällorna och kartotekets lift/dim. Kör mot den riktiga
// backenden med fejkad inferens (e2e/serve_test_app.py): retrievalen,
// FTS5-indexet och SSE-transporten är oförfalskade; bara själva
// svarsgenereringen är stubbad.
//
// TÄCKER:
//   1. att genomsökningen renderar ÄKTA träffantal per lektion (ur
//      scan_result, exakta strängar — inte bara "> 0"), och att utrullningen
//      når alla kort,
//   2. att svaret strömmar in och att [1] blir en markör, inte rå text,
//   3. att läsbordet säger "Svaret bygger på denna" — SINGULAR, med rätt
//      antal — efter done, vilket bara håller om Genomsokning.svelte:s
//      citatfilter verkligen filtrerar bort de olästa källorna,
//   4. att kartotekets kort får data-stage="lift" för lektioner servern
//      räknar som källor, och att INGET stadie sätts utan aktiv fråga,
//   5. att ett fel renderas i SVARSYTAN och inte som ett svar (409 fejkad),
//   6. att en ny fråga överger den föregående strömmen (generationsvakten),
//   7. att fråge-läget är default och att körknappen är aktiv,
//   8. att ett error-event MITT I strömmen (efter deep_read) inte kvitteras
//      som en lyckad genomsökning — slutgranskningens fynd 1 (HIGH).
//
// Punkt 4, 6 och 8 är planens bärande krav. Punkt 4 vaktar att stadiet
// kommer från servern och inte från en klientmatchning på frågans ord —
// gamla appen hade den buggen och kommentaren app.js:3384-3386 säger att den
// togs bort. Punkt 6 vaktar en kapplöpning som är osynlig tills den
// inträffar. Punkt 8 vaktar att ett fel som landar EFTER att servern redan
// hunnit skicka scan_plan/scan_result/deep_read inte får tickern att visa
// "✓ Genomsökte" eller läsbordet att visa "Svaret bygger på" — se
// Genomsokning.svelte.
//
// TÄCKS INTE, och det är avsiktligt:
//   · SERVERNS SÖKORDNING (scan_plan.items i ORDER BY datum DESC). Den här
//     fixturen kan inte bevisa det: alla tre lektionerna får SAMMA namn av
//     fejkens titelförslag (fake_suggest_title, serve_test_app.py:135-137,
//     verifierat: "Bråk och procent — introduktion" för alla tre), PATCH
//     /api/lessons tar inte emot ett `name`-fält (server.py — bara
//     datum/starttid/sal/summary/group_name/course_name), och kortens `key`
//     (lesson_id) syns inte i DOM:en. En klientsortering som råkade byta
//     ordning hade alltså passerat obemärkt. Att bevisa ordning kräver
//     antingen ett synligt lesson_id i markupen eller en väg att ge
//     lektionerna olika namn efter transkribering — ingen av de vägarna
//     finns i den här specens fixtur.
//   · DIM-GRENEN i kartotekets stadiekarta (data-stage="dim"). Alla tre
//     lektionerna delar samma fejktranskript, så alla tre får ordträff och
//     blir källor (done.result.sources = alla 3 djupt lästa) — det finns
//     ingen FJÄRDE lektion UTAN träff i fixturen som kunde blivit dim. Punkt
//     4 nedan verifierar därför bara att lift sätts, aldrig att dim gör det.
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
  await page.getByRole("tab", { name: "Inspelningar", exact: true }).click();
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

test("Fråga (/next/): genomsökningen visar äkta träffantal och utrullningen når alla kort", async ({
  page,
}) => {
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

  // EXAKT antal, inte bara "> 0". Ordet "bråk" träffar en gång i fejkens
  // namnförslag ("Bråk och procent — introduktion", suggest_title stubbad i
  // serve_test_app.py) och en gång i transkriptet — 2 per lektion, samma för
  // alla tre eftersom alla delar segment. Ett kort som visar "● 1 träff"
  // (t.ex. bara transkriptet, inte namnet, räknat) ska falla här.
  await expect(teater.locator('li.ruta[data-scan="traff"] span.etikett')).toHaveText([
    "● 2 träffar",
    "● 2 träffar",
    "● 2 träffar",
  ]);
  // Räknaren räknar ANTAL LEKTIONER med träff, inte summan av träffarna —
  // alla tre lektionerna har träff, så den blir 3 oavsett att varje kort
  // visar "2 träffar". "hittills" hänger på att svaret fortfarande strömmar
  // vid det här laget (fejksvaret sover 1,5 s före första token, långt efter
  // att utrullningen — golv 60 ms/kort — hunnit avslöja alla tre korten).
  await expect(teater.locator("span.antal")).toHaveText("3 ordträffar hittills");
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
  await expect(svar.locator("button.cite")).toHaveCount(1, { timeout: 20_000 });
  await expect(svar.locator("button.cite")).toHaveText("1");
  // B3c gjorde markören klickbar — den öppnar källmodalen. Fram till dess
  // var den ett rollöst span, eftersom en knapp som inte gör något är värre
  // än ingen knapp.
  await expect(svar.getByRole("button", { name: /^Öppna källa 1/ })).toBeVisible();
  await expect(svar.locator("p.text")).not.toContainText("[1]");

  // Rubriken räknar bara citerade källor — fejksvaret citerar exakt en.
  await expect(svar.locator("h2.rubrik")).toHaveText("Svar — 1 källa");
  await expect(svar.locator("li.kalla")).toHaveCount(1);
  // Raden "att öppna en källa migreras i en senare plan" är BORTA sedan B3c:
  // markören öppnar nu källmodalen på riktigt. Se testet längre ned.
  await expect(svar).not.toContainText("migreras i en senare plan");

  // Läsbordet efter done: SINGULAR ("denna", inte "dessa 3") — det är den
  // enda assertionen som gör Genomsokning.svelte:s citatfiltrering
  // meningsfull. bordet filtreras till bara den citerade källan (1 av 3
  // djupt lästa), så en bugg som visade alla tre ("dessa 3") ska falla här.
  // Åt-sidan-räkningen (2 av 3 ordträffar) hänger på samma filtrering.
  await expect(vy.locator("section.genomsokning p.bordsrubrik")).toContainText(
    "Svaret bygger på denna",
  );
  await expect(vy.locator("section.genomsokning p.bordsrubrik .aside")).toHaveText(
    "… och la 2 ordträffar åt sidan",
  );

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Fråga (/next/): kartotekets kort lyfts efter serverns träffar", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);

  // Utan aktiv fråga har INGET kort ett stadie.
  await expect(vy.locator("div.hylsa[data-stage]")).toHaveCount(0);

  await stallFraga(page, vy, ORD);
  await expect(vy.locator("section.svar button.cite")).toHaveCount(1, { timeout: 20_000 });

  // Efter done styr done.result.sources — ALLA DJUPT LÄSTA lyfts, inte bara
  // de CITERADE (Svar.svelte:s rubrik "Svar — 1 källa" räknar en annan,
  // smalare mängd: det modellen faktiskt hänvisar till i löptexten).
  //
  // DIM TÄCKS INTE HÄR (se filhuvudets TÄCKS INTE): fixturens tre lektioner
  // delar samma fejktranskript, så alla tre får ordträff och blir källor
  // (done.result.sources = alla 3) — det finns ingen fjärde lektion utan
  // träff som kunde blivit dim. dampade asserteras därför till EXAKT 0, inte
  // "> 0 av misstag", så testet är ärligt om vad det faktiskt visar.
  const lyfta = vy.locator('div.hylsa[data-stage="lift"]');
  const dampade = vy.locator('div.hylsa[data-stage="dim"]');
  await expect(lyfta).toHaveCount(FIXTUR.length);
  await expect(dampade).toHaveCount(0);

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

/**
 * SLUTGRANSKNINGENS FYND 1 (HIGH): servern kan kasta EFTER scan_plan,
 * scan_result och deep_read redan emitterats — t.ex. RuntimeError("Språk-
 * modellen är inte installerad."), server.py:1591 — och streamPost:s
 * syntetiska "Anslutningen till servern bröts." kan landa när som helst.
 * Utan grinden i Genomsokning.svelte kvitterade tickern med "✓ Genomsökte N
 * inspelningar" och läsbordet med "Svaret bygger på dessa N", trots att
 * Svar.svelte SAMTIDIGT visade felet — ett svar påstods finnas när sökningen
 * misslyckades. Ingen fejkjobb-gren i serve_test_app.py kan producera den
 * här händelseordningen (fake_answer kastar aldrig), så strömmen byggs för
 * hand och injiceras med page.route — samma mönster som 409-testet ovan,
 * fast med en handskriven SSE-kropp i stället för ett enkelt JSON-fel.
 */
test("Fråga (/next/): genomsökningen kvitterar inte en sökning som avbröts mitt i strömmen", async ({
  page,
}) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);

  const sse = (events) => events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  const body = sse([
    {
      type: "scan_plan",
      total: FIXTUR.length,
      items: [
        { key: 1, name: "Lektion A" },
        { key: 2, name: "Lektion B" },
        { key: 3, name: "Lektion C" },
      ],
    },
    { type: "scan_result", key: 1, hits: 2 },
    { type: "scan_result", key: 2, hits: 1 },
    { type: "scan_result", key: 3, hits: 0 },
    // deep_read FÖRE felet — det är just den ordningen fyndet gäller.
    {
      type: "deep_read",
      sources: [
        {
          lesson_id: 1, history_id: "h1", name: "Lektion A",
          group: "9A", course: "Matematik 2b", datum: "2026-04-02",
        },
        {
          lesson_id: 2, history_id: "h2", name: "Lektion B",
          group: "9A", course: "Matematik 2b", datum: "2026-03-30",
        },
      ],
    },
    { type: "error", message: "Språkmodellen är inte installerad." },
  ]);
  await page.route("**/api/search/ask", (route) =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body }),
  );

  await sokfalt(vy).input.fill(ORD);
  await sokfalt(vy).kor.click();

  const teater = vy.locator("section.genomsokning");
  // Genomsökningen SYNS — scan_plan kom, så teatern renderas.
  await expect(teater).toBeVisible();

  // KRAVET: tickern får aldrig kvittera en genomsökning som avbröts, men den
  // ska heller inte se ut att fortfarande söka — felet är redan känt.
  await expect(teater.locator("p.ticker")).not.toContainText("Genomsökte");
  await expect(teater.locator("p.ticker")).not.toContainText("Söker igenom");
  await expect(teater.locator("p.ticker")).toContainText("avbröts");

  // Läsbordet får INTE påstå att svaret bygger på källorna — inget svar kom.
  await expect(teater.locator("p.bordsrubrik")).toHaveCount(0);

  // Felet renderas i svarsytan, med streamPost-vägens vanliga textklassning
  // (fragaFelText — allt annat än "matchar sökningen"/anslutningsmönstren).
  await expect(vy.locator("p.fragafel")).toContainText(
    "Kunde inte söka: Språkmodellen är inte installerad.",
  );
  await expect(vy.locator("section.svar")).toHaveCount(0);
  await expect(sokfalt(vy).kor).toBeEnabled();

  await page.unroute("**/api/search/ask");
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

test("Fråga (/next/): en sifferkälla öppnar transkriptionen på rätt ställe", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await stallFraga(page, vy, ORD);
  await expect(vy.locator("section.svar button.cite")).toHaveCount(1, { timeout: 20_000 });

  await vy.locator("section.svar button.cite").click();

  // Native <dialog> — den ligger i top-layer, alltså utanför .pane-avgränsningen.
  const modal = page.locator("dialog.kalla");
  await expect(modal).toBeVisible();

  // Fejkens transkript är tre segment, och bara ett av dem nämner ORD. Fönstret
  // är två rader före och fem efter, så alla tre ryms — men exakt en ska vara
  // MARKERAD. Utan markeringen har termmatchningen tystnat.
  await expect(modal.locator("li.rad")).toHaveCount(3);
  await expect(modal.locator("li.rad.traff")).toHaveCount(1);
  await expect(modal.locator("li.rad.traff")).toContainText(ORD);

  // Tidsstämpeln ska vara en läsbar etikett, inte råa sekunder.
  await expect(modal.locator("li.rad").first().locator("span.tid")).toHaveText("0:00");

  await modal.getByRole("button", { name: "Stäng" }).click();
  await expect(modal).toBeHidden();

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Fråga (/next/): en följdfråga får ett eget svar", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await stallFraga(page, vy, ORD);
  await expect(vy.locator("section.svar")).toBeVisible({ timeout: 20_000 });

  const svar = vy.locator("section.svar");
  const foljd = svar.getByLabel("Ställ en följdfråga");
  await expect(foljd).toBeVisible();

  const stromen = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/search/ask",
  );
  await foljd.fill("procent");
  await svar.getByRole("button", { name: /^Skicka$|^Söker/ }).click();
  await stromen;

  // Frågan syns som en egen rad, och svaret kommer i en egen.
  await expect(svar.locator("p.fraga")).toHaveText("procent");
  await expect(svar.locator("p.foljdsvar")).toContainText("[FEJK svar]", { timeout: 20_000 });
  // Fältet töms så nästa fråga kan skrivas direkt.
  await expect(foljd).toHaveValue("");

  expect(errors, errors.join("\n")).toEqual([]);
});

/* ---- Kalenderkedjan -------------------------------------------------------
   Fejkserverns fake_answer skickar ALDRIG en [KALENDERFÖRSLAG]-rad, så kedjan
   går inte att nå genom den vanliga vägen. Testerna nedan injicerar därför en
   egen SSE-kropp med page.route. Det som prövas är klientens tolkning och
   visning — inte serverns förmåga att producera raden, som har egen täckning i
   backend. */

/** Bygger en SSE-kropp av samma form som app/web/sse.py skickar. */
function sseKropp(events) {
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
}

const KALLA = {
  lesson_id: 1,
  history_id: "h1",
  name: "lektion.mp3",
  group: "9A",
  course: "Matematik 2b",
  datum: "2026-04-02",
};

/** Rutar /api/search/ask till en egen ström som slutar med `svarstext`. */
async function stubbaStrom(page, svarstext) {
  await page.route("**/api/search/ask", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseKropp([
        { type: "scan_plan", total: 1, items: [{ key: 1, name: "lektion.mp3" }] },
        { type: "scan_result", key: 1, hits: 2 },
        { type: "deep_read", sources: [KALLA] },
        { type: "token", text: svarstext },
        { type: "done", result: { text: svarstext, sources: [KALLA] } },
      ]),
    }),
  );
}

// De två testerna nedan vaktar kalender/Forslagsbox.svelte och
// kalender/FragekortModal.svelte — DELADE med lektionschatten (se
// kalender-sammanslagningen). Lokatorerna speglar den delade komponenten,
// inte den tidigare arkiv-egna Kalenderforslag.svelte/Kalenderfragor.svelte.

test("Fråga (/next/): ett kalenderförslag blir en granskningsbar ruta", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.route("**/api/calendar/status", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ connected: true, client_ready: true }),
    }),
  );
  // "9:10" (inte "09:10") är MEDVETET: modellens tid nollutfylls av
  // kalender/tagg.js:tolkaForslag, och den utfyllningen ska bevisas här, inte
  // bara en redan zero-padded konstant.
  const FORSLAG =
    'Provet ligger på fredag [1].\n[KALENDERFÖRSLAG] {"title":"Prov om bråk","date":"2026-09-04","time":"9:10","desc":"Kapitel 3"}';
  await stubbaStrom(page, FORSLAG);

  const vy = await oppnaInspelningar(page);
  await stallFraga(page, vy, ORD);

  // Forslagsbox.svelte: <section class="box" aria-label="Kalenderförslag">.
  const ruta = vy.getByRole("region", { name: "Kalenderförslag" });
  await expect(ruta).toBeVisible({ timeout: 20_000 });
  await expect(ruta.getByLabel("Titel på händelsen")).toHaveValue("Prov om bråk");
  await expect(ruta.getByLabel("Tid")).toHaveValue("09:10");
  // Anteckningen är en klippt FÖRHANDSVISNING som öppnar AnteckningModal —
  // inget eget redigeringsfält i boxen (till skillnad från B:s tidigare UI).
  await expect(ruta.getByRole("button", { name: "Kapitel 3" })).toBeVisible();

  // DEN MASKINLÄSBARA RADEN FÅR ALDRIG SYNAS — varken i svaret eller någon
  // annanstans i vyn.
  await expect(vy).not.toContainText("KALENDERFÖRSLAG");
  await expect(vy.locator("section.svar p.text")).toContainText("Provet ligger på fredag");

  // Och först ett medvetet klick skickar något ut ur maskinen. "Lägg till"
  // är INTE avstängd av Google-anslutningsstatus (se kalender/Forslagsbox.svelte
  // — provat och medvetet backat: A:s egen e2e-täckning i kalender.spec.mjs
  // klickar utan att först stubba /api/calendar/status), bara av `upptagen`.
  let skickat = null;
  await page.route("**/api/calendar/event", (route) => {
    skickat = JSON.parse(route.request().postData() || "{}");
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  const laggTill = ruta.getByRole("button", { name: "Lägg till" });
  await expect(laggTill).toBeEnabled();
  await laggTill.click();

  // A:s bekräftelsetext, inte B:s tidigare "Händelsen är tillagd …".
  await expect(ruta).toContainText("Tillagd i Google Kalender");
  expect(skickat.title).toBe("Prov om bråk");
  expect(skickat.start).toBe("2026-09-04T09:10:00");

  await page.unroute("**/api/search/ask");
  await page.unroute("**/api/calendar/event");
  await page.unroute("**/api/calendar/status");
  expect(errors, errors.join("\n")).toEqual([]);
});

test("Fråga (/next/): klargörande frågor blir en dialog som går att hoppa över", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const FRAGOR =
    'Ett par frågor först.\n[KALENDERFRÅGOR] {"fragor":[{"q":"Hur långt ska provet vara?","alternativ":["60 min","90 min"]}]}';
  await stubbaStrom(page, FRAGOR);

  const vy = await oppnaInspelningar(page);
  await stallFraga(page, vy, ORD);

  // FragekortModal.svelte: <dialog aria-label="Kalenderhändelsen — några
  // frågor först">. Native <dialog> — ligger i top-layer, utanför
  // .pane-avgränsningen (monteras på App.svelte-nivå, se App.svelte).
  const dialog = page.getByRole("dialog", { name: "Kalenderhändelsen — några frågor först" });
  await expect(dialog).toBeVisible({ timeout: 20_000 });
  await expect(dialog).toContainText("Hur långt ska provet vara?");
  await expect(dialog.getByRole("button", { name: "60 min" })).toBeVisible();

  // Taggen får inte läcka ut i svarstexten.
  await expect(vy).not.toContainText("KALENDERFRÅGOR");

  // Ett val markeras, och ett andra klick ångrar det.
  const val = dialog.getByRole("button", { name: "90 min" });
  await val.click();
  await expect(val).toHaveAttribute("aria-pressed", "true");
  await val.click();
  await expect(val).toHaveAttribute("aria-pressed", "false");

  // "Skapa direkt utan svar" (A:s text för B:s "Hoppa över") ska alltid
  // finnas: läraren får aldrig tvingas svara för att få en kalenderhändelse.
  //
  // SKÄRPNING (slutgranskningens fynd): fejkservern svarar med SAMMA
  // [KALENDERFRÅGOR]-rad oavsett vad som skickas (stubbaStrom är statisk),
  // så efter klicket öppnas kortet snart igen av precis den anledningen —
  // "dialogen är dold" är därför ett ÖVERGÅENDE tillstånd, inte ett bevis på
  // att svaret faktiskt gick iväg. Den riktiga vakten är den UTGÅENDE
  // begäran: skickaKalenderSvar (sokActions.js) går via stallFoljdfraga, som
  // postar {q} till /api/search/ask — vänta in DEN och läs dess kropp.
  const uppfoljning = page.waitForRequest(
    (r) => new URL(r.url()).pathname === "/api/search/ask" && r.method() === "POST",
  );
  await dialog.getByRole("button", { name: "Skapa direkt utan svar" }).click();
  await expect(dialog).toBeHidden();
  const begaran = await uppfoljning;
  expect(begaran.postDataJSON().q).toBe(
    "Skapa kalenderhändelsen direkt med rimliga antaganden.",
  );

  await page.unroute("**/api/search/ask");
  expect(errors, errors.join("\n")).toEqual([]);
});
