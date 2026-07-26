// Plan B3a: e2e för ORDSÖKET i Inspelningar-fliken (/next/). Kör mot den
// riktiga backenden med fejkad inferens (e2e/serve_test_app.py); /api/search är
// helt oberörd av fejkarna och söker på riktigt i samma SQLite och samma
// FTS5-index som i produktion.
//
// TÄCKER:
//   1. att en sökning renderar träffar med MARKERADE utdrag (<mark>), och att
//      styrtecknen \x02/\x03 aldrig läcker som synlig text,
//   2. att kartoteket försvinner under en aktiv sökning och kommer tillbaka
//      när fältet rensas,
//   3. att kartotekets tomtillstånd inte renderas under träfflistan,
//   4. tomtillståndet vid noll träffar,
//   5. att ett KLASSbyte inte ändrar träfflistan — söket är ofiltrerat på
//      servern,
//   6. att "Fråga AI" visar sin förklarande rad och en inaktiv körknapp.
//
// Punkt 2 och 5 är planens bärande krav. Punkt 2 vaktar regeln "en yta i
// taget"; punkt 5 vaktar ett serverbeteende som är lätt att missförstå —
// api_search (server.py:1395-1410) tar inga filterparametrar, så en träff i en
// bortfiltrerad klass ska fortfarande synas.
//
// TÄCKS INTE, och det är avsiktligt:
//   · Fråge-läget i sak. Det svarar inte förrän B3b; punkt 6 prövar bara att
//     B3a säger det i stället för att låtsas.
//   · Att öppna en träff i transkriptet. Det finns inte i B3a — vyn säger i
//     klartext att det kommer senare, och punkt 1 kontrollerar att raden står
//     där.
//   · Generationsvakten i korSokning. inspelningar-kartotek.spec.mjs prövar
//     mönstret på laddaLektioner; den här är en ordagrann kopia av det.
//   · LIKE-fallbacken (sqlite utan FTS5). Miljön har FTS5, och att fejka bort
//     det hade prövat testmiljön snarare än koden.
//
// SÖKORDEN ÄR VALDA UR FEJKENS TRANSKRIPT. Alla lektioner skapas ur samma
// demofil, och fejkinferensen ger dem alltid samma text
// (serve_test_app.py:41-46): "Hej och välkommen till lektionen. Idag ska vi
// prata om bråk och procent. Ta fram era anteckningsböcker." Därav "bråk" —
// som dessutom prövar att FTS-indexet bevarar diakriter
// (tokenize='unicode61 remove_diacritics 0', db.py:79-99). "kvadratrot" finns
// inte i texten och används för nollträffsfallet.
//
// STÄDNING: filen sorteras SIST av de tre inspelningar-specarna
// (kartotek < paneler < sok) och delar server med de övriga. afterEach tömmer
// arkivet, så basmappen lämnas i samma tomma läge servern startade i.
import { test, expect, failOnConsoleError } from "./helpers/app";

/** Två lektioner för 9A och en för 9B. Alla tre bär samma fejktranskript. */
const FIXTUR = [
  { datum: "2026-04-02", sal: "A1", group_name: "9A", course_name: "Matematik 2b" },
  { datum: "2026-03-30", sal: "A2", group_name: "9A", course_name: "Matematik 2b" },
  { datum: "2026-03-25", sal: "B3", group_name: "9B", course_name: "Fysik 1a" },
];

/** Ord ur fejkens transkript, respektive ett som garanterat saknas. */
const ORD = "bråk";
const ORD_UTAN_TRAFF = "kvadratrot";

/**
 * En klass UTAN lektioner. get_or_create_group (server.py:972-979) skapar
 * klassen så fort namnet nämns i en PATCH, och att flytta tillbaka lektionen
 * lämnar den kvar tom — precis som när en lärare raderat alla inspelningar
 * för en klass. Samma mönster som inspelningar-kartotek.spec.mjs.
 *
 * Testet "kartoteket viker för träffarna" behöver den: fixturen har annars
 * ALLTID tre lektioner, så kartotekets tomtillstånd ("Inga inspelningar
 * matchar dina filter") aldrig kan rendera under testet — och en assertion
 * mot ett tillstånd som aldrig kan uppstå är grön oavsett vad koden gör.
 */
const TOM_KLASS = "9C";

/** Raderar varje lektion som finns. Tar historikposten och mappen med sig. */
async function toemArkivet(request) {
  const lektioner = await (await request.get("/api/lessons")).json();
  for (const l of lektioner) {
    const r = await request.delete("/api/lessons/" + l.id);
    expect(r.ok(), `DELETE /api/lessons/${l.id} svarade ${r.status()}`).toBeTruthy();
  }
}

/**
 * Skapar de tre lektionerna.
 *
 * Avslutas med en FÖRKONTROLL mot /api/search: hittar den inte ORD i alla tre
 * transkripten är det miljön som ändrats (annat fejktranskript, saknat
 * FTS5-index), och då ska felet säga det. Utan den blir en trasig fixtur
 * grön av fel skäl — noll träffar ser ut som ett korrekt tomtillstånd.
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

  // Skapa den tomma klassen INNAN de riktiga PATCH:arna, exakt som
  // inspelningar-kartotek.spec.mjs: sätt den på en lektion och flytta sedan
  // tillbaka lektionen till sin riktiga klass i loopen nedan. Kvar blir en
  // registrerad klass utan någon lektion.
  await request.patch("/api/lessons/" + skapade[0].id, { data: { group_name: TOM_KLASS } });
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
  // Loopa över ALLA träffar, inte bara den första: ett index som markerar
  // träff 0 men inte de andra två skulle passera en förkontroll som bara
  // läste hits[0].
  for (const hit of kontroll.hits || []) {
    expect(
      hit.snippet,
      `Utdraget saknar \\x02-markering — kör sqlite utan FTS5? (LIKE-fallbacken markerar inte)`,
    ).toContain("\x02");
  }
}

/**
 * Öppnar Inspelningar-fliken och väntar in kartoteket.
 *
 * Flikbytet är inte kosmetik: hämtningarna är grindade på nav.tab, inte på
 * montering — App.svelte håller alla paneler monterade och gömmer dem bara.
 */
async function oppnaInspelningar(page) {
  await page.goto("/next/");
  await page.getByRole("button", { name: "Inspelningar", exact: true }).click();
  const vy = page.locator(".pane:not([hidden]) section.view");
  await expect(vy.locator("article.kort")).toHaveCount(FIXTUR.length, { timeout: 15_000 });
  return vy;
}

/** Sökfältets delar. Avgränsade till .sok — vyn har fler inmatningsfält. */
function sokfalt(vy) {
  const rot = vy.locator("section.sok");
  return {
    input: rot.getByLabel("Sök i arkivet"),
    rensa: rot.getByRole("button", { name: "Rensa" }),
    kor: rot.getByRole("button", { name: /^Sök$|^Söker/ }),
    fragaAi: rot.getByRole("button", { name: "Fråga AI" }),
    sokOrd: rot.getByRole("button", { name: "Sök ord" }),
  };
}

/** Kör en sökning och väntar in svaret från /api/search. */
async function sok(page, vy, ord) {
  const svar = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/search" && r.status() === 200,
  );
  await sokfalt(vy).input.fill(ord);
  await sokfalt(vy).kor.click();
  await svar;
}

test.beforeEach(async ({ request }) => {
  await byggFixtur(request);
});

test.afterEach(async ({ request }) => {
  await toemArkivet(request);
});

test("Sök (/next/): träffarna renderas med markerade utdrag", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await sok(page, vy, ORD);

  const lista = vy.locator("section.traffar");
  await expect(lista.locator("li.traff")).toHaveCount(FIXTUR.length);
  await expect(lista.locator("p.antal")).toHaveText(`${FIXTUR.length} träffar`);

  // MARKERINGEN är kravet, inte bara att texten finns: utan <mark> har
  // Snippet.svelte:s \x02-parser tystnat.
  const markerade = lista.locator("li.traff mark");
  await expect(markerade.first()).toHaveText(new RegExp(ORD, "i"));

  // Styrtecknen får ALDRIG synas. Samma spärr som planering-arkiv.spec.mjs:147-149.
  // Skriv teckenklassen som ESCAPE-SEKVENSER, aldrig som literala styrtecken —
  // de överlever varken kopiering eller de flesta redigerare.
  const text = await lista.innerText();
  expect(text, "\\x02/\\x03 läckte som synlig text").not.toMatch(/[\x02\x03]/);

  // B3a navigerar inte till transkriptet, och säger det.
  await expect(lista).toContainText("migreras i en senare plan");

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Sök (/next/): kartoteket viker för träffarna och kommer tillbaka", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await expect(vy.locator("article.kort")).toHaveCount(FIXTUR.length);

  await sok(page, vy, ORD);

  // EN YTA I TAGET: korten ska vara borta, inte bara nedtonade.
  await expect(vy.locator("article.kort")).toHaveCount(0);
  await expect(vy.locator("section.traffar li.traff")).toHaveCount(FIXTUR.length);

  // Två billiga spärrar: i DET HÄR tillståndet (tre lektioner, inget filter)
  // kan kartotekets tomtillstånd ändå inte rendera, så de här raderna bevisar
  // inget om huruvida "en yta i taget" faktiskt hålls. Den skarpa kontrollen
  // — att tomtillståndet FAKTISKT kan rendera och ändå döljs av sökningen —
  // ligger i BEVISBLOCKET nedan, i ett annat tillstånd (TOM_KLASS).
  await expect(vy.getByText("Inga inspelningar än")).toHaveCount(0);
  await expect(vy.getByText("Inga inspelningar matchar dina filter")).toHaveCount(0);

  await sokfalt(vy).rensa.click();

  await expect(vy.locator("section.traffar")).toHaveCount(0);
  await expect(vy.locator("article.kort")).toHaveCount(FIXTUR.length);

  // BEVISET: driv kartotekets FILTRERADE tomtillstånd till att faktiskt
  // rendera, sök därefter, och kontrollera att det försvinner medan
  // träffarna visas. Fixturen har annars alltid tre lektioner, så
  // "Inga inspelningar matchar dina filter" kan aldrig rendera i den här
  // filen, och assertionerna ovan mot den vore gröna oavsett vad koden gör.
  // TOM_KLASS är ett SERVERfilter (samma mönster som
  // inspelningar-kartotek.spec.mjs) som ger insp.lessons = [] fast arkivet
  // är fullt. Görs EFTER "kommer tillbaka"-kontrollen ovan, så den ursprungliga
  // "en yta i taget"-mätningen (mot ett FULLT, ofiltrerat kartotek) inte
  // späds ut av filtret.
  const lektionerSvar = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/lessons" && r.status() === 200,
  );
  await vy.locator(".filter").getByLabel("KLASS").selectOption({ label: TOM_KLASS });
  await lektionerSvar;
  await expect(vy.locator("article.kort")).toHaveCount(0);
  await expect(vy.getByText("Inga inspelningar matchar dina filter")).toBeVisible();

  await sok(page, vy, ORD);
  await expect(vy.locator("section.traffar li.traff")).toHaveCount(FIXTUR.length);
  await expect(
    vy.getByText("Inga inspelningar matchar dina filter"),
    "Kartotekets tomtillstånd renderade under träfflistan trots att det bevisligen KAN rendera",
  ).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Sök (/next/): noll träffar visar sin egen text", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await sok(page, vy, ORD_UTAN_TRAFF);

  const lista = vy.locator("section.traffar");
  await expect(lista).toContainText("Inga lektioner matchade din sökning.");
  await expect(lista.locator("li.traff")).toHaveCount(0);
  // Fortfarande en yta i taget: korten är borta, och kartotekets tomtext
  // ersätter inte sökets.
  await expect(vy.locator("article.kort")).toHaveCount(0);
  await expect(vy.getByText("Inga inspelningar matchar dina filter")).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Sök (/next/): ett klassbyte ändrar inte träffarna", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await sok(page, vy, ORD);

  // FÖRHANDSRÄKNING: bevisar att sökningen redan gav FIXTUR.length träffar
  // INNAN klassfiltret rörs, så assertionen efter bytet nedan mäter att bytet
  // INTE ändrade träfflistan — inte bara att den råkade ha rätt antal från
  // början. Utan den här raden kan testet inte skilja "klassbytet tog bort en
  // träff" från "sökningen gav bara två från början".
  //
  // Tandkontrollerad mot ETT rättat sabotage i Traefflista.svelte (grindat på
  // insp.filterGroup, se planens Task 5 Step 4b) — den här raden PASSERAR (3)
  // och fällningen sker på den märkta assertionen nedan. Ett tidigare
  // sabotageförslag som filtrerade OVILLKORLIGT på träffens egen h.group i
  // stället för UI-filtret fällde i stället den här raden, eftersom 2 av 3
  // fixturlektioner redan bär group='9A' innan KLASS-selecten ens rörs — det
  // var ett fel i det sabotaget, inte i den här assertionen.
  await expect(vy.locator("section.traffar li.traff")).toHaveCount(FIXTUR.length);

  // 9A har två av tre lektioner. Söket är OFILTRERAT — api_search tar inga
  // filterparametrar — så alla tre träffarna ska stå kvar.
  const lektionerSvar = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/lessons" && r.status() === 200,
  );
  await vy.locator(".filter").getByLabel("KLASS").selectOption({ label: "9A" });
  // Vänta in att filtret verkligen slog igenom. valjKlass (actions.js) avfyrar
  // /api/lessons, /api/next-prep och /api/trends PARALLELLT (laddaPaneler) —
  // löftet ovan är avgränsat till /api/lessons, det enda som räknas här.
  await lektionerSvar;

  await expect(
    vy.locator("section.traffar li.traff"),
    "Söket är ofiltrerat: ett klassbyte får inte ändra träfflistan",
  ).toHaveCount(FIXTUR.length);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Sök (/next/): Fråga AI säger att den kommer senare", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  const f = sokfalt(vy);

  await expect(f.sokOrd).toHaveAttribute("aria-pressed", "true");
  await expect(f.fragaAi).toHaveAttribute("aria-pressed", "false");

  await f.fragaAi.click();

  await expect(f.fragaAi).toHaveAttribute("aria-pressed", "true");
  await expect(f.kor).toBeDisabled();
  await expect(vy).toContainText("Att fråga arkivet med egna ord migreras i nästa plan");
  // Lägesbytet gömmer inte lärarens lektioner.
  await expect(vy.locator("article.kort")).toHaveCount(FIXTUR.length);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Sök (/next/): ett lägesbyte nollställer fältet och träffarna", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  await sok(page, vy, ORD);
  await expect(vy.locator("section.traffar li.traff")).toHaveCount(FIXTUR.length);

  await sokfalt(vy).fragaAi.click();
  await expect(vy.locator("section.traffar")).toHaveCount(0);
  await expect(sokfalt(vy).input).toHaveValue("");
  await expect(vy.locator("article.kort")).toHaveCount(FIXTUR.length);

  expect(errors, errors.join("\n")).toEqual([]);
});
