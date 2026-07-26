// Plan B5: e2e för de tre PANELERNA i Inspelningar-fliken (/next/) — agendan,
// "Inför nästa lektion" och terminstrenderna. Kör mot den riktiga backenden med
// fejkad inferens (e2e/serve_test_app.py). /api/agenda, /api/trends,
// /api/next-prep, /api/agenda/ics och PATCH /api/insights är helt oberörda av
// fejkarna — de svarar på riktigt mot samma SQLite som i produktion.
//
// TÄCKER:
//   1. att agendan renderar försenad, dagens och framtida post med rätt
//      märkning ("Idag" respektive försenad-markering),
//   2. att en avbockning i agendan BEHÅLLER TANGENTBORDSFOKUS på samma knapp,
//      genom hela PATCH:en och omhämtningen, in i det klarmarkerade läget —
//      slutgranskningens punkt 3 (aria-disabled + tidig retur i onclick i
//      stället för disabled, som tar fokus med sig),
//   3. att ett KLASSbyte skickar nya GET /api/trends och GET /api/next-prep,
//      och att ett KURSbyte DÄREFTER (med klassen redan vald) inte skickar
//      något av de tre — båda avlästa ur nätverksloggen, inte antagna. Ett
//      kursbyte UTAN vald klass mäts medvetet inte här: laddaNastaLektion och
//      laddaTrender gör då en tidig retur innan något anrop görs, oavsett vad
//      kursbytet i sig utlöser, så en sådan mätning hade vaktat den tidiga
//      returen, inte valjKurs,
//   4. att varken trender eller Inför nästa renderas UTAN vald klass,
//   5. att en bock i Inför nästa laddar om AGENDAN — alltså att gamla appens
//      refetch-asymmetri verkligen är fixad,
//   6. att .ics-exporten POSTar och att statusraden får antalet,
//   7. de harmoniserade tomtillstånden: tom agenda respektive klass utan
//      lektioner.
//
// Punkt 3:s kursbytesled och punkt 5 är planens bärande krav. Punkt 4 vaktar
// regeln "ej tillämpligt → ingen panel" (specens avsnitt 4); punkt 5 vaktar
// den enda avsiktliga BETEENDEförändringen mot gamla appen. De flesta mäts på
// faktiska HTTP-anrop i stället för att panelernas innehåll får stå som bevis
// — punkt 2 är undantaget, där själva DOM-nodens identitet och webbläsarens
// fokus ÄR beviset.
//
// TÄCKS INTE, och det är avsiktligt:
//   · Att .ics-FILENS innehåll är giltig iCalendar. Det ägs av
//     tests/test_ics_export.py (5 tester) och rörs inte av den här planen.
//   · Att POST /api/open verkligen startar ett kalenderprogram. Den stubbas —
//     utan stubb öppnar testet lärarens Utforskare mitt i körningen. Att
//     backend validerar sökvägen mot base_dir ägs av
//     tests/test_open_endpoints.py.
//   · Att ett fel i POST /api/open lämnar exportbeskedet orört. NAMNGIVEN
//     LUCKA: det kräver att stubben svarar med felstatus OCH att man kan skilja
//     "beskedet stod kvar" från "beskedet hann aldrig skrivas över", vilket är
//     samma tidsberoende konstruktion resten av filen undviker.
//   · Generationsvakterna. inspelningar-kartotek.spec.mjs prövar mönstret på
//     laddaLektioner; de tre här är ordagranna kopior av det, och en fjärde
//     kapplöpningsuppställning hade kostat mer än den bevisar.
//
// FIXTUREN: samma väg som inspelningar-kartotek.spec.mjs — det finns ingen
// POST /api/lessons, så lektionsrader skapas av riktiga POST /api/transcribe
// mot demofilen och PATCH:as sedan. Insikterna läggs på med
// POST /api/lessons/{id}/insights. byggFixtur skapar BARA lektionerna; varje
// test som behöver insikter kallar laggTillInsikter själv, så tomtillstånden
// går att pröva utan att riva fixturen.
//
// STÄDNING: filen sorteras ANDRA av tio i next-foundation-projektet, direkt
// efter inspelningar-kartotek. Den ärver alltså ett tomt arkiv och måste själv
// lämna det tomt — afterEach raderar varje lektion, vilket via
// DELETE /api/lessons/{id} tar insikterna, historikposten och resultatmappen.
import { test, expect, failOnConsoleError } from "./helpers/app";

/** Två lektioner för 9A och en för 9B. Datumen är fasta: panelernas
 *  klassbundna innehåll beror på ORDNINGEN mellan lektionerna, inte på var de
 *  ligger i förhållande till idag. */
const FIXTUR = [
  { datum: "2026-04-02", sal: "A1", group_name: "9A", course_name: "Matematik 2b" },
  { datum: "2026-03-30", sal: "A2", group_name: "9A", course_name: "Matematik 2b" },
  { datum: "2026-03-25", sal: "B3", group_name: "9B", course_name: "Fysik 1a" },
];

/** En klass utan lektioner. get_or_create_group skapar den så fort namnet
 *  nämns i en PATCH (server.py:972-979), och att flytta tillbaka lektionen
 *  lämnar den kvar tom. Tomtillståndstestet behöver den: trends svarar då
 *  lessons: 0 med ett sanningsenligt group_id. */
const TOM_KLASS = "9C";

/**
 * Ett datum N dagar från idag, på serverns format.
 *
 * ALDRIG hårdkodat: _agenda_view (app/web/server.py:1298-1304) jämför mot
 * datetime.now().date() på servern, så ett fast datum ger ett test som är
 * grönt i dag och rött i morgon.
 *
 * Byggs ur de LOKALA fälten och inte med toISOString(), som är UTC — nära
 * midnatt hade det gett fel dag och därmed fällt "Idag"-assertionen
 * slumpmässigt beroende på när sviten kördes.
 */
function isoDag(offset) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  const tva = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + tva(d.getMonth() + 1) + "-" + tva(d.getDate());
}

/** Raderar varje lektion som finns. Tar insikter, historikpost och mapp. */
async function toemArkivet(request) {
  const lektioner = await (await request.get("/api/lessons")).json();
  for (const l of lektioner) {
    const r = await request.delete("/api/lessons/" + l.id);
    expect(r.ok(), `DELETE /api/lessons/${l.id} svarade ${r.status()}`).toBeTruthy();
  }
}

/** Skapar de tre lektionerna och den tomma klassen. Returnerar lektionerna i
 *  den ordning /api/lessons ger dem — nyaste datum först, alltså FIXTUR:s. */
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

  // Skapar TOM_KLASS genom att nämna den, och flyttar sedan tillbaka raden.
  await request.patch("/api/lessons/" + skapade[0].id, { data: { group_name: TOM_KLASS } });
  for (let i = 0; i < FIXTUR.length; i++) {
    const r = await request.patch("/api/lessons/" + skapade[i].id, { data: FIXTUR[i] });
    expect(r.ok(), `PATCH /api/lessons/${skapade[i].id} svarade ${r.status()}`).toBeTruthy();
  }

  return await (await request.get("/api/lessons")).json();
}

/**
 * Lägger insikter på 9A:s två lektioner. Ger, per panel:
 *
 *   AGENDAN (tvärs alla klasser, bara daterade poster): tre stycken — en
 *   försenad, en med dagens datum och en i framtiden. Alla öppna, alltså
 *   "3 öppna · 1 försenad".
 *
 *   INFÖR NÄSTA (9A): last_lesson är lektioner[0] (datum 2026-04-02, störst).
 *   open_actions bär bara åtgärd/grupprum/material med status öppen
 *   (_CARRY_TYPER, app/db.py:724), alltså de två åtgärderna på lektioner[0] —
 *   kalenderposten bärs INTE över, och "Rätta prov" är klarmarkerad.
 *   difficulties kommer bara från last_lesson: "Derivata".
 *
 *   TRENDER (9A): lessons 2, analysed 2, counts svårighet 2 / åtgärd 3 /
 *   kalender 1, actions {open: 2, done: 1} → 33 %, och top_difficulties
 *   ["Derivata" ×2] — de två svårighetstexterna skiljer sig bara i skiftläge,
 *   och grupperingen är skiftlägesokänslig (app/db.py:855-868).
 */
async function laggTillInsikter(request, lektioner) {
  const skapa = async (lessonId, data) => {
    const r = await request.post("/api/lessons/" + lessonId + "/insights", { data });
    expect(r.ok(), `POST insights svarade ${r.status()} för "${data.text}"`).toBeTruthy();
    return await r.json();
  };

  await skapa(lektioner[0].id, { typ: "åtgärd", text: "Ta med linjaler", due_date: isoDag(-10) });
  await skapa(lektioner[0].id, { typ: "åtgärd", text: "Boka grupprum", due_date: isoDag(0) });
  await skapa(lektioner[0].id, { typ: "kalender", text: "Prov om derivata", due_date: isoDag(10) });
  await skapa(lektioner[0].id, { typ: "svårighet", text: "Derivata", ref: "uppg 3" });

  await skapa(lektioner[1].id, { typ: "svårighet", text: "derivata" });
  const klarad = await skapa(lektioner[1].id, { typ: "åtgärd", text: "Rätta prov" });
  const r = await request.patch("/api/insights/" + klarad.id, { data: { status: "klar" } });
  expect(r.ok(), `PATCH /api/insights/${klarad.id} svarade ${r.status()}`).toBeTruthy();
}

/**
 * Öppnar Inspelningar-fliken och väntar in kartoteket.
 *
 * Flikbytet är inte kosmetik: hämtningarna är grindade på nav.tab
 * (InspelningarView.svelte), inte på montering — App.svelte håller alla paneler
 * monterade och gömmer dem bara med hidden.
 */
async function oppnaInspelningar(page, { kort = FIXTUR.length } = {}) {
  await page.goto("/next/");
  await page.getByRole("button", { name: "Inspelningar", exact: true }).click();
  const vy = page.locator(".pane:not([hidden]) section.view");
  await expect(vy.locator("article.kort")).toHaveCount(kort, { timeout: 15_000 });
  return vy;
}

/** Filterradens selecter. Avgränsningen behövs: Planeringsvyn har ett eget
 *  "Klass"-fält och redigeringsdialogen ett till, och båda ligger kvar i
 *  DOM:en. En osäkrad getByLabel("KLASS") träffar tre element. */
function filter(vy) {
  const rad = vy.locator(".filter");
  return { klass: rad.getByLabel("KLASS"), kurs: rad.getByLabel("KURS") };
}

/** Loggar panelernas GET-anrop. Registreras EFTER att vyn laddats, så
 *  monteringens egna hämtningar inte räknas med. */
function loggaPanelanrop(page) {
  const anrop = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (r.method() === "GET" && /^\/api\/(agenda|trends|next-prep)$/.test(u.pathname)) {
      anrop.push(u.pathname);
    }
  });
  return anrop;
}

/**
 * Stubbar POST /api/open.
 *
 * OBLIGATORISKT för exporttestet: endpointen öppnar filen i Windows
 * standardprogram (server.py:1750-1753), så utan stubben startar testet
 * lärarens kalenderprogram mitt i körningen. Allt annat släpps igenom.
 */
async function stubbaOpen(page) {
  await page.route("**/api/open", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" }),
  );
}

test.afterEach(async ({ request }) => {
  await toemArkivet(request);
});

test("Panelerna (/next/): agendan märker försenad, idag och framtid", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const lektioner = await byggFixtur(request);
  await laggTillInsikter(request, lektioner);

  const vy = await oppnaInspelningar(page);
  const agenda = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Kommande/ }) });

  // Hopfälld vid laddning, som gamla appen — rubrikraden bär ändå summan.
  const huvud = agenda.getByRole("button", { name: /Kommande/ });
  await expect(huvud).toHaveAttribute("aria-expanded", "false");
  await expect(huvud).toContainText("3 öppna");
  await expect(huvud).toContainText("1 försenad");

  await huvud.click();
  await expect(huvud).toHaveAttribute("aria-expanded", "true");

  const rader = agenda.locator("li.rad");
  await expect(rader).toHaveCount(3);

  // Dagens post visar "Idag", inte ett datum.
  const idag = rader.filter({ hasText: "Boka grupprum" });
  await expect(idag.locator(".datum")).toHaveText("Idag");

  // Den försenade posten är märkt som sådan i BÅDA lägena — raden och datumet.
  const sen = rader.filter({ hasText: "Ta med linjaler" });
  await expect(sen).toHaveClass(/forsenad/);
  await expect(sen.locator(".datum")).toHaveClass(/forsenad/);

  // Den framtida är varken eller. Båda kontrollerna är NEGATIVA (not.toHave…),
  // så en textändring som tömmer filtret ovan hade fått dem att passera
  // vakuöst — count(1) säkrar att raden faktiskt hittades först.
  const framtid = rader.filter({ hasText: "Prov om derivata" });
  await expect(framtid).toHaveCount(1);
  await expect(framtid).not.toHaveClass(/forsenad/);
  await expect(framtid.locator(".datum")).not.toHaveText("Idag");

  expect(errors).toEqual([]);
});

test("Panelerna (/next/): en avbockning i agendan behåller tangentbordsfokus", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const lektioner = await byggFixtur(request);
  await laggTillInsikter(request, lektioner);

  const vy = await oppnaInspelningar(page);
  const agenda = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Kommande/ }) });
  await agenda.getByRole("button", { name: /Kommande/ }).click();

  // BEVISET för slutgranskningens punkt 3: samma <button>-nod, samma ruta,
  // genom hela PATCH:en och omhämtningen. Fixen bytte disabled mot
  // aria-disabled + en tidig retur i onclick — en fokuserad nod som blir
  // disabled tappar fokus, och webbläsaren återställer det aldrig av sig
  // själv. Ett riktigt klick och en riktig fråga om vem som har fokus, inte
  // bara en läsning av attributen.
  const ruta = agenda.locator("li.rad").filter({ hasText: "Ta med linjaler" }).locator("button.ruta");
  await ruta.click();
  await expect(ruta).toBeFocused();

  // Vänta in att PATCH:en OCH laddaPaneler() faktiskt är klara — annars
  // bevisar assertionen ovan bara fokus under det korta mellanläget, inte att
  // det överlever hela vägen till att raden blir den permanenta checkmarken.
  // Samma <button> i båda lägena (Agenda.svelte) är precis vad som gör att
  // Sveltes keyade #each kan behålla noden, och därmed fokus, över bytet.
  await expect(ruta).toHaveAttribute("aria-disabled", "true");
  await expect(ruta).toHaveClass(/klar/);
  await expect(ruta).toBeFocused();

  expect(errors).toEqual([]);
});

test("Panelerna (/next/): utan vald klass finns varken trender eller Inför nästa", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const lektioner = await byggFixtur(request);
  await laggTillInsikter(request, lektioner);

  const vy = await oppnaInspelningar(page);

  // "Ej tillämpligt" är inte "tomt": panelerna ska inte finnas alls, inte visa
  // en tomtext. Regeln i specens avsnitt 4.
  await expect(vy.getByRole("heading", { name: /Terminstrender/ })).toHaveCount(0);
  await expect(vy.getByRole("heading", { name: /Inför nästa lektion/ })).toHaveCount(0);
  // Agendan är tvärs alla klasser och SKA finnas.
  await expect(vy.getByRole("heading", { name: /Kommande/ })).toHaveCount(1);

  // Kursbytets nätverkskontroll flyttad härifrån: utan vald klass gör
  // laddaNastaLektion/laddaTrender en tidig retur INNAN något anrop görs,
  // oavsett vad valjKurs gör — en mätning här hade vaktat den tidiga returen,
  // inte valjKurs. Se testet "ett klassbyte hämtar trender och Inför nästa",
  // som gör mätningen med en klass redan vald.

  expect(errors).toEqual([]);
});

test("Panelerna (/next/): ett klassbyte hämtar trender och Inför nästa", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const lektioner = await byggFixtur(request);
  await laggTillInsikter(request, lektioner);

  const vy = await oppnaInspelningar(page);
  const anrop = loggaPanelanrop(page);

  await filter(vy).klass.selectOption({ label: "9A" });
  await expect(vy.locator("article.kort")).toHaveCount(2);

  // BEVISET är nätverksloggen, inte att panelerna dök upp: en reaktiv kedja som
  // slutat hämta om hade fortfarande kunnat rendera gammal data.
  await expect
    .poll(() => anrop.filter((p) => p === "/api/trends").length, {
      message: "Ett klassbyte ska skicka GET /api/trends",
    })
    .toBeGreaterThan(0);
  await expect
    .poll(() => anrop.filter((p) => p === "/api/next-prep").length, {
      message: "Ett klassbyte ska skicka GET /api/next-prep",
    })
    .toBeGreaterThan(0);

  // Och panelerna renderar 9A:s innehåll.
  const trender = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Terminstrender/ }) });
  await expect(trender).toContainText("2 av 2 lektioner analyserade");
  await expect(trender).toContainText("1/3 · 33 %");
  await expect(trender.locator("li")).toHaveCount(1);
  await expect(trender.locator("li .bricka")).toHaveText("2×");
  // EXAKT text, inte bara "innehåller": vaktar whitespace-buggen (rapporterad
  // i task-5-report.md, fixad i granskningsomgången) som klistrade ihop
  // rubriken och klassen till "Terminstrender· 9A" — Svelte trimmade bort ett
  // bokstavligt mellanslag som stod först i en <span> intill en {#if}-gräns.
  // {level: 2} vaktar samtidigt rubriknivån för en panelrubrik, sedan
  // inspelningar-kartotek.spec.mjs fick avgränsa sina egna h2-lokatorer till
  // .grupp (se motiveringen där för varför den avgränsningen behövdes).
  await expect(trender.getByRole("heading", { level: 2, name: /Terminstrender/ })).toHaveText(
    "Terminstrender · 9A",
  );

  const nasta = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Inför nästa lektion/ }) });
  // Kalenderposten bärs INTE över — bara åtgärd/grupprum/material.
  await expect(nasta.locator("li.rad")).toHaveCount(2);
  await expect(nasta).not.toContainText("Prov om derivata");
  // Mellanslaget här var samma bugg som ovan (NastaLektion.svelte:78, samma
  // {#if}-gräns-trimning) — rapporterad i task-5-report.md, fixad i
  // granskningsomgången genom att lägga separatorn INUTI uttrycket i stället
  // för som ett bokstavligt mellanslag i markupen.
  await expect(nasta.locator("ul.punkter li")).toHaveText(["Derivata (uppg 3)"]);

  // KURSBYTESKONTROLLEN hör hemma här, inte i föregående test: med en klass
  // redan vald prövar ett kursbyte faktiskt valjKurs, i stället för att bara
  // mäta laddarnas tidiga retur (se kommentaren i föregående test). Loggen
  // nollas här så bara kursbytets EGNA anrop räknas.
  //
  // KURSEN ÄR "Fysik 1a", INTE 9A:s egen "Matematik 2b". Med Matematik 2b
  // redan vald lämnar ett byte TILL Matematik 2b kortantalet oförändrat på
  // 2 — ingenting i testet bevisade att change-handlern över huvud taget
  // kördes; kopplas selecten loss från valjKurs blir assertionen grön ändå.
  // 9B äger "Fysik 1a", så filtret 9A + Fysik 1a matchar noll lektioner: ett
  // POSITIVT ankare som bara kan bli sant om valjKurs faktiskt hämtade om med
  // den nya kursen i querysträngen.
  anrop.length = 0;
  await filter(vy).kurs.selectOption({ label: "Fysik 1a" });
  // HÄNDELSEBUNDEN väntan, inte tidsbunden: inväntar /api/lessons-svängen
  // kursbytet utlöser och stänger båda luckorna (positivt bevis + flush) på
  // en gång, i stället för två gissade requestAnimationFrame.
  await expect(vy.locator("article.kort")).toHaveCount(0);
  expect(
    anrop,
    "Ett kursbyte får inte hämta agenda, trender eller next-prep när en klass redan är vald",
  ).toEqual([]);

  expect(errors).toEqual([]);
});

test("Panelerna (/next/): en bock i Inför nästa laddar om agendan", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const lektioner = await byggFixtur(request);
  await laggTillInsikter(request, lektioner);

  const vy = await oppnaInspelningar(page);
  await filter(vy).klass.selectOption({ label: "9A" });
  await expect(vy.locator("article.kort")).toHaveCount(2);

  const nasta = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Inför nästa lektion/ }) });
  await expect(nasta.locator("li.rad")).toHaveCount(2);

  // Loggen registreras EFTER klassbytet, så bara bockens omhämtning räknas.
  const anrop = loggaPanelanrop(page);

  await nasta.locator("li.rad").filter({ hasText: "Ta med linjaler" })
    .getByRole("button", { name: "Markera klar" }).click();

  await expect(nasta.locator("li.rad")).toHaveCount(1);

  // KRAVET: gamla appens markPrepDone laddar BARA om prep (app.js:1743), så
  // agendan blev stale. Här ska den hämtas om. Det är planens enda avsiktliga
  // beteendeförändring, och den mäts på anropet — inte på DOM:en, som kunde ha
  // sett rätt ut av en slump.
  await expect
    .poll(() => anrop.filter((p) => p === "/api/agenda").length, {
      message: "En bock i Inför nästa ska ladda om agendan — asymmetrin är fixad",
    })
    .toBeGreaterThan(0);

  expect(errors).toEqual([]);
});

test("Panelerna (/next/): .ics-exporten skriver filen och rapporterar antalet", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const lektioner = await byggFixtur(request);
  await laggTillInsikter(request, lektioner);
  await stubbaOpen(page);

  const vy = await oppnaInspelningar(page);
  const agenda = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Kommande/ }) });
  await agenda.getByRole("button", { name: /Kommande/ }).click();

  const svar = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/agenda/ics" && r.request().method() === "POST",
  );
  await agenda.getByRole("button", { name: /Exportera till kalender/ }).click();
  const kropp = await (await svar).json();

  expect(kropp.count, "Tre daterade insikter ska ge tre VEVENT").toBe(3);
  expect(kropp.path, "Filen ska heta lektionsagenda.ics").toContain("lektionsagenda.ics");

  // Beskedet går i vyns GEMENSAMMA statusrad — panelerna har medvetet ingen
  // egen live-region (ett tredje role="status" fäller antalsspärren).
  await expect(vy.locator('[data-testid="insp-statusrad"]')).toContainText("3 poster sparade i");

  expect(errors).toEqual([]);
});

test("Panelerna (/next/): tomtillstånden syns i stället för att panelen försvinner", async ({ page, request }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // MEDVETET utan laggTillInsikter: agendan är då känt tom, inte okänd.
  await byggFixtur(request);

  const vy = await oppnaInspelningar(page);

  // Läge 1: agendan finns och säger varför den är tom — den försvinner INTE,
  // vilket är skillnaden mot gamla appen.
  const agenda = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Kommande/ }) });
  await expect(agenda).toContainText("Inga daterade insikter ännu");
  await expect(agenda.getByRole("button", { name: /Exportera till kalender/ })).toHaveCount(0);

  // Läge 2: en klass UTAN lektioner. Panelerna är tillämpliga — klassen är vald
  // — och visar därför sina tomtexter i stället för att utebli.
  await filter(vy).klass.selectOption({ label: TOM_KLASS });
  await expect(vy.locator("article.kort")).toHaveCount(0);

  const trender = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Terminstrender/ }) });
  await expect(trender).toContainText("Inga lektioner för den här klassen ännu");

  const nasta = vy.locator("section.panel").filter({ has: page.getByRole("heading", { name: /Inför nästa lektion/ }) });
  await expect(nasta).toContainText("Inget att bära med sig ännu");

  expect(errors).toEqual([]);
});
