// Plan B1: e2e för Inspelningar-fliken i Svelte-frontenden (/next/) — själva
// KARTOTEKET. Kör mot den riktiga backenden med fejkad inferens
// (e2e/serve_test_app.py); /api/lessons, /api/history, /api/groups och
// /api/courses är helt oberörda av fejkarna och svarar på riktigt mot samma
// SQLite och samma history.json som i produktion.
//
// TÄCKER:
//   1. att lektionerna renderas veckogrupperade, med rätt antal per grupp,
//   2. att ett byte av KLASSfiltret verkligen skickar ett nytt
//      GET /api/lessons — avläst ur nätverksloggen, inte antaget,
//   3. att ett byte av MÅNADSfiltret INTE skickar något anrop alls, och att de
//      synliga korten ändå ändras,
//   4. att ett långsammare filtersvar inte får skriva över ett nyare
//      (generationsvakten i laddaLektioner),
//   5. att redigeringen skickar PATCH och att kortet visar det nya värdet,
//   6. att raderingen tar bort kortet OCH att ett DELETE verkligen skickades,
//   7. att raderingens 409 når läraren med SERVERNS egen text och att kortet
//      står kvar — planens enda uttalade MÅSTE,
//   8. att de två tomtillstånden hör till var sitt villkor och inte är
//      utbytbara,
//   9. att ärlighetsvakten räknar historikposter utan lektionsrad.
//
// Punkt 2 och 3 är planens bärande krav. Klass och kurs ligger i
// QUERYSTRÄNGEN till /api/lessons, alltså på servern; månaden filtrerar den
// redan hämtade listan på klienten. Slås de ihop till en reaktiv kedja slutar
// omhämtningen tyst att ske, och klassfiltret ser ut att fungera medan det bara
// filtrerar en föråldrad lista. Därför räknas de faktiska HTTP-anropen i
// stället för att kortens innehåll får stå som bevis.
//
// TÄCKS INTE, och det är avsiktligt:
//   · Att ÖPPNA en lektion (transkript, ljud, chatt). Det finns inte i B1 —
//     vyn säger i klartext att det kommer i en senare plan i stället för att
//     navigera till en platshållare. Specen kontrollerar att raden står där.
//   · Sök, arkivfrågan ("Fråga AI") och panelerna. De ligger i B2-B5 och har
//     inget tillstånd i den här vyn.
//   · Miniatyren på kortet (.tumme). Testmiljön har bara en .wav, och wav/webm
//     får medvetet ingen miniatyr — videogrenen kan inte nås utan en riktig
//     videofixtur.
//   · Att en ÄKTA fillåsning framkallar 409:an. Punkt 7 fejkar svaret med
//     page.route och serverns egen kropp, och det är avsiktligt: det som prövas
//     där är klientens visningsväg, inte serverns förmåga att svara 409. Att
//     backend verkligen gör det verifierades manuellt en gång med en riktig
//     låsning (plan B1 Task 4) och har sin egen gren i server.py.
//   · Att insp.laddar VAKTAR de två tomtillstånden. NAMNGIVEN LUCKA, så nästa
//     läsare inte tror att den termen är bevisad: villkorets uppgift är att
//     inget av beskeden ska BLINKA FÖRBI under en omhämtning, men bägge
//     assertionerna i tomtillståndstestet är omprövande (toBeVisible respektive
//     toHaveCount(0)) och prövar alltså om tills läget stabiliserat sig. En
//     enstaka renderingsruta med fel besked mitt i en omhämtning kan de inte
//     fälla — tas !insp.laddar bort ur båda grenarna förblir specen grön.
//     Ingen billig deterministisk fix finns: den hade krävt att ett svar hålls
//     tillbaka och att DOM:en samplas i exakt det fönstret, vilket är just den
//     tidsberoende konstruktion resten av filen undviker.
//
// FIXTUREN BYGGS VIA RIKTIGA API:ER, och det finns bara en väg: fejkservern
// startar med TOM basmapp, och det finns INGEN POST /api/lessons — en
// lektionsrad skapas uteslutande av en färdig transkribering
// (app/web/server.py:686, db.create_lesson, idempotent på history_id). Därför
// kör byggaren nedan tre riktiga POST /api/transcribe mot demofilen och
// PATCH:ar sedan in datum, sal, klass och kurs. Allt via page.request, alltså
// utan omvägen genom guidens UI — det som testas här är kartoteket, inte
// transkriberingen.
//
// Fejkinferensen gör de tre körningarna billiga (uppmätt: 358 ms för tre), så
// fixturen byggs om från grunden före VARJE test. Det gör testerna oberoende av
// varandras ordning, vilket är värt den sekunden: två av dem är destruktiva.
//
// STÄDNING: filen sorteras FÖRST av alla nio i next-foundation-projektet
// (bokstavsordning), så allt den lämnar efter sig ser åtta andra specfiler.
// afterEach raderar därför varje lektion som finns kvar — vilket via
// DELETE /api/lessons/{id} också tar historikposten och resultatmappen — och
// lämnar basmappen i exakt det tomma läge servern startade i. Klass- och
// kursraderna i SQLite blir kvar (de har ingen radering i API:et), men ingen
// annan spec läser /api/groups eller /api/courses.
// Källinspelningen är oförstörbar: /api/sample pekar på kopian DIREKT under
// basmappen (serve_test_app.py), och _delete_recording rör bara downloads/.
import { test, expect, failOnConsoleError } from "./helpers/app";

/**
 * Fixturen, i den ordning /api/lessons returnerar den (nyast datum först).
 *
 * Datumen bär tre krav samtidigt:
 *   · 2026-04-02 (to) och 2026-03-30 (må) ligger i SAMMA ISO-vecka 14
 *     (30 mar – 5 apr), 2026-03-25 (on) i vecka 13 — alltså två på varandra
 *     följande veckor med 2 respektive 1 lektion, så både grupperingen och
 *     antalsraden (inklusive singularformen) har något att säga,
 *   · veckan spänner över ett MÅNADSSKIFTE, så månadsfiltret har två verkliga
 *     val utan att någon extra lektion behövs,
 *   · klasserna delar listan 2/1, så ett klassbyte ger ett synligt annat
 *     kortset än det föregående (kapplöpningstestet vilar på det).
 *
 * `sal` är det enda fältet som SKILJER korten åt: alla tre kommer ur samma
 * demofil och får därför samma namn av fejkens titelförslag, och kortets
 * datumetikett härleds ur skapandetiden (ts), inte ur `datum` — att PATCH:a
 * datum flyttar alltså kortet till en annan vecka utan att ändra etiketten.
 */
const FIXTUR = [
  { datum: "2026-04-02", sal: "A1", group_name: "9A", course_name: "Matematik 2b" },
  { datum: "2026-03-30", sal: "A2", group_name: "9A", course_name: "Matematik 2b" },
  { datum: "2026-03-25", sal: "B3", group_name: "9B", course_name: "Fysik 1a" },
];

/**
 * En klass UTAN lektioner. get_or_create_group (server.py:972-979) skapar
 * klassen så fort namnet nämns i en PATCH, och att flytta tillbaka lektionen
 * lämnar den kvar tom — precis som när en lärare raderat alla inspelningar för
 * en klass. Tomtillståndstestet behöver den: det är ett SERVERfilter som ger
 * insp.lessons = [] fast arkivet är fullt.
 */
const TOM_KLASS = "9C";

/**
 * En KURS utan lektioner. Behöver inte skapas: db.py seedar hela Gy25-stegen
 * (ensure_gy25_nivaer, app/db.py:407-412) vid databasskapandet, så de tio
 * nivånamnen finns i kursregistret i varje ny testdatabas. Fixturen ovan kan
 * aldrig råka fylla någon av dem — "Matematik 2b" och "Fysik 1a" är inga
 * Gy25-nivånamn och normaliseras inte till några (GY25_KURSNAMN slår bara på
 * kurskoder som "Ma2b"), så get_or_create_course lägger dem i egna rader.
 *
 * Tomtillståndstestets läge 1c behöver den: KURSEN är, precis som klassen, ett
 * SERVERfilter, och den är det ENDA som isolerat utövar !insp.filterCourse.
 */
const TOM_KURS = "Matematik, nivå 1a";

/**
 * Kortets metarad, minus salen. Talen är fejkens: segmenten slutar på 7,6 s
 * (dur "00:07") och modellen väljs nedan så etiketten är förutsägbar.
 * byggFixtur kontrollerar prefixet mot verkligheten, så en miljöändring blir
 * ett begripligt fixturfel i stället för en obegriplig textjämförelse.
 */
const METAPREFIX = "00:07 · KB-Whisper large (sv) · Svenska";
const META = (sal) => METAPREFIX + " · " + sal;

/** Raderar varje lektion som finns. Tar historikposten och mappen med sig. */
async function toemArkivet(request) {
  const lektioner = await (await request.get("/api/lessons")).json();
  for (const l of lektioner) {
    const r = await request.delete("/api/lessons/" + l.id);
    expect(r.ok(), `DELETE /api/lessons/${l.id} svarade ${r.status()}`).toBeTruthy();
  }
}

/**
 * Bygger om fixturen från grunden. Fem steg, alla mot riktiga endpoints:
 *   1. töm arkivet,
 *   2. hämta demofilen och en INSTALLERAD Whisper-modell (modellkatalogen
 *      skannar hårdvaran på riktigt även i fejkläge, så id:t hämtas i stället
 *      för att hårdkodas — men KB-Whisper föredras, annars stämmer inte
 *      METAPREFIX),
 *   3. kör tre POST /api/transcribe, som var och en skapar en historikpost och
 *      en lektionsrad,
 *   4. skapa den tomma klassen,
 *   5. PATCH:a in datum, sal, klass och kurs på de tre nya raderna.
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

  await request.patch("/api/lessons/" + skapade[0].id, { data: { group_name: TOM_KLASS } });
  for (let i = 0; i < FIXTUR.length; i++) {
    const r = await request.patch("/api/lessons/" + skapade[i].id, { data: FIXTUR[i] });
    expect(r.ok(), `PATCH /api/lessons/${skapade[i].id} svarade ${r.status()}`).toBeTruthy();
  }

  // Förkontroll, inte en beteendeassertion: går den sönder är det miljön som
  // ändrats (annan modell, andra fejksegment), och då ska felet säga det.
  for (const l of await (await request.get("/api/lessons")).json()) {
    expect(
      [l.dur, l.model, l.lang].join(" · "),
      "Fixturens metadata ser inte ut som väntat — uppdatera METAPREFIX",
    ).toBe(METAPREFIX);
  }
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

/**
 * Filterradens selecter. Avgränsningen behövs: Planeringsvyn har ett eget
 * "Klass"-fält och redigeringsdialogen ett till, och båda ligger kvar i DOM:en
 * (App.svelte gömmer paneler med hidden, dialogen är alltid monterad). En
 * osäkrad getByLabel("KLASS") träffar därför tre element.
 */
function filter(vy) {
  const rad = vy.locator(".filter");
  return {
    klass: rad.getByLabel("KLASS"),
    kurs: rad.getByLabel("KURS"),
    manad: rad.getByLabel("MÅNAD"),
  };
}

/**
 * Loggar varje GET mot /api/lessons. Registreras EFTER att vyn laddats, så
 * monteringens egna hämtningar inte räknas med.
 */
function loggaLektionsanrop(page) {
  const anrop = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (r.method() === "GET" && u.pathname === "/api/lessons") anrop.push(u.pathname + u.search);
  });
  return anrop;
}

/**
 * Väntar in ett löfte med en generös men ÄNDLIG frist.
 *
 * Finns för att ersätta fasta pauser. En waitForTimeout som går ut för tidigt
 * gör testet FALSKT GRÖNT — assertionen efteråt körs innan det den vaktar ens
 * hunnit hända — medan ett verkligt hängande svar här i stället ger ett
 * begripligt fel med sin egen text.
 */
function vantaPa(loftet, vad, ms = 15_000) {
  let timer;
  return Promise.race([
    Promise.resolve(loftet).finally(() => clearTimeout(timer)),
    new Promise((_, avvisa) => {
      timer = setTimeout(() => avvisa(new Error(vad)), ms);
    }),
  ]);
}

/**
 * Låter sidan rendera två rutor.
 *
 * Ett svar som just levererats behandlas i mikrouppgifter — fetch → json →
 * tilldelning → Sveltes flush — så DOM:en är ännu inte uppdaterad i det
 * ögonblick svaret landat. Efter två requestAnimationFrame har en sådan
 * skrivning garanterat slagit igenom, och en omprövande assertion kan därför
 * inte passera på att den hann före skrivningen.
 */
function tvaRutor(page) {
  return page.evaluate(
    () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))),
  );
}

/**
 * Konsolfelen MINUS de som testet självt framkallat.
 *
 * Chrome loggar varje svar med felstatus som "Failed to load resource: the
 * server responded with a status of 409 (Conflict)". Det är fejkens egen 409,
 * inte ett appfel — utan filtret fäller failOnConsoleError 409-testet på just
 * det svar testet finns för att framkalla. Allt annat räknas fortfarande, och
 * ett riktigt undantag ur bekraftaRadera kommer in som pageerror och passerar
 * inte filtret.
 *
 * MEDVETET en egen kopia. transkribera-inspelning.spec.mjs:128-130 har en
 * identisk privat appfel(), och den ligger inte i e2e/helpers/. Att lyfta dit
 * hade krävt en ändring i den 900+ rader långa, gröna specen också (annars finns
 * duplikatet ändå kvar) — mer sprängradie än två rader regex är värda. Blir det
 * en tredje kopia är det dags att lyfta alla tre.
 */
function appfel(errors) {
  return errors.filter((e) => !/Failed to load resource/.test(e));
}

test.beforeEach(async ({ request }) => {
  await byggFixtur(request);
});

// Lämnar basmappen tom efter varje test — se STÄDNING överst. Ligger i
// afterEach och inte afterAll så att även ett fällt test städar efter sig.
test.afterEach(async ({ request }) => {
  await toemArkivet(request);
});

test("Inspelningar (/next/): kartoteket grupperar per vecka med rätt antal", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);

  // Veckorubrikerna, nyaste först. <h2> är ett krav och inte bara stil: vyns
  // <h1> följs av korten på <h3>, så utan en rubriknivå per vecka finns ingen
  // väg för en skärmläsare att hoppa mellan veckorna.
  //
  // AVGRÄNSAT TILL .grupp (plan B5, upptäckt av inspelningar-paneler.spec.mjs):
  // Agenda.svelte lägger en egen <h2>"Kommande" direkt i vyn, alltid synlig så
  // fort agendan laddats — även tom, vilket är en avsiktlig, testad regel
  // (specens avsnitt 4: agendan gäller tvärs alla klasser och ska alltid
  // finnas). En osäkrad vy.getByRole("heading", {level:2}) fångar därför även
  // den rubriken och fäller ordningen nedan. Kartoteket ägs av .grupp, så det
  // är rätt avgränsning — inte ett svagare krav.
  await expect(vy.locator(".grupp").getByRole("heading", { level: 2 })).toHaveText([
    "Vecka 14",
    "Vecka 13",
  ]);

  // Spannet och antalet står bredvid rubriken. Antalet är den enda kontrollen
  // av att grupperingen räknar rätt — två kort i den ena veckan, ett i den
  // andra — och singularformen ("1 inspelning") har en egen gren i koden.
  const rubriker = vy.locator(".grupp .rubrik");
  await expect(rubriker.nth(0)).toContainText("30 mar – 3 apr");
  await expect(rubriker.nth(0)).toContainText("2 inspelningar");
  await expect(rubriker.nth(1)).toContainText("23 mar – 27 mar");
  await expect(rubriker.nth(1)).toContainText("1 inspelning");

  // Och korten ligger i RÄTT grupp, inte bara i rätt antal.
  const grupp = vy.locator(".grupp");
  await expect(grupp.nth(0).locator("article.kort .meta")).toHaveText([META("A1"), META("A2")]);
  await expect(grupp.nth(1).locator("article.kort .meta")).toHaveText([META("B3")]);

  // Klass och kurs syns på kortet, färgchipet med dem.
  await expect(vy.locator("article.kort .tagg")).toHaveText([
    "9A · Matematik 2b",
    "9A · Matematik 2b",
    "9B · Fysik 1a",
  ]);

  // B1 säger rakt ut vad den inte gör i stället för att antyda det. Texten
  // matchas som STRÄNG och inte som regex: markupen bryter meningen över två
  // rader, och Playwright normaliserar radbrytningar till mellanslag bara vid
  // strängmatchning.
  await expect(
    vy.getByText(
      "Att öppna en lektion — transkript, ljud och chatt — migreras i en senare plan.",
    ),
  ).toBeVisible();

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Inspelningar (/next/): klassfiltret hämtar om från servern", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  const { klass } = filter(vy);
  const meta = vy.locator("article.kort .meta");

  // Loggen registreras först här, så monteringens egna hämtningar inte räknas.
  const anrop = loggaLektionsanrop(page);

  // KÄRNAN: ett klassbyte MÅSTE nå servern, för filtret ligger i
  // querysträngen (db.list_lessons, app/db.py:544-560). Att korten ändras
  // räcker inte som bevis — en klientfiltrering hade sett likadan ut på
  // skärmen och tyst filtrerat en föråldrad lista.
  //
  // Väntan ligger FÖRE kortassertionen med flit. selectOption returnerar innan
  // svaret hunnit landa, så utan den vore nätverkskontrollen en kapplöpning —
  // och med kortassertionen först hade ett borttaget laddaLektioner() fällt
  // testet på fel rad, med "korten ändrades inte" i stället för det som
  // faktiskt gick sönder.
  const forstaAnropet = page
    .waitForRequest(
      (r) => r.method() === "GET" && new URL(r.url()).pathname === "/api/lessons",
      { timeout: 5_000 },
    )
    .catch(() => null);
  await klass.selectOption({ label: "9A" });
  expect(await forstaAnropet, "Klassbytet skickade inget GET /api/lessons").toBeTruthy();

  await expect(meta).toHaveText([META("A1"), META("A2")]);

  // Exakt ETT anrop, och med group_id i querysträngen.
  expect(anrop, "Klassbytet skickade inte exakt ett GET /api/lessons").toHaveLength(1);
  expect(anrop[0]).toMatch(/^\/api\/lessons\?group_id=\d+$/);

  // Och tillbaka igen: "Alla klasser" måste också hämta om, annars står
  // arkivet kvar filtrerat.
  await klass.selectOption({ label: "Alla klasser" });
  await expect(meta).toHaveText([META("A1"), META("A2"), META("B3")]);
  expect(anrop, "Bytet tillbaka till Alla klasser hämtade inte om").toHaveLength(2);
  expect(anrop[1]).toBe("/api/lessons");

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Inspelningar (/next/): månadsfiltret rör inte nätverket men ändrar korten", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  const { manad } = filter(vy);
  const meta = vy.locator("article.kort .meta");

  // Månaderna härleds ur den hämtade listan, inte ur en egen endpoint. Läraren
  // ser MÅNADSNAMN, inte den råa nyckeln — gamla appen gör likadant
  // (app.js:3917-3919), och en select full av "2026-04" var enda stället i vyn
  // där en maskinsträng nådde fram.
  await expect(manad.locator("option")).toHaveText(["Alla månader", "apr 2026", "mar 2026"]);

  // Men VÄRDET är fortfarande 'YYYY-MM'. Den halvan är load-bearing och har
  // ingen annan spärr: filtreringen jämför value mot l.datum.slice(0, 7)
  // (InspelningarView.svelte), så flyttas den läsbara formen in i value slutar
  // månadsfiltret tyst att matcha någonting alls — och kortassertionerna nedan
  // skulle då falla på "inga kort" utan att peka ut varför.
  //
  // evaluateAll och inte toHaveValues: den matchern läser vad ett <select> har
  // VALT, inte vilka värden dess optioner bär. Det som ska prövas här är det
  // senare.
  expect(
    await manad.locator("option").evaluateAll((els) => els.map((el) => el.value)),
    "Månadsvalets VÄRDE är inte längre 'YYYY-MM' — filtreringen slutar matcha",
  ).toEqual(["", "2026-04", "2026-03"]);

  const anrop = loggaLektionsanrop(page);

  // April innehåller bara den ena halvan av vecka 14.
  await manad.selectOption({ label: "apr 2026" });
  await expect(meta).toHaveText([META("A1")]);

  // Mars innehåller den andra halvan plus hela vecka 13 — korten ändras
  // alltså på riktigt MELLAN de två valen, inte bara mot utgångsläget.
  await manad.selectOption({ label: "mar 2026" });
  await expect(meta).toHaveText([META("A2"), META("B3")]);

  await manad.selectOption({ label: "Alla månader" });
  await expect(meta).toHaveText([META("A1"), META("A2"), META("B3")]);

  // KÄRNAN: månaden filtrerar den REDAN hämtade listan. Tre byten, noll
  // anrop. Går den här assertionen sönder har någon slagit ihop de två
  // filtersorterna till en gemensam kedja — och då kostar varje månadsval en
  // onödig rundtur, samtidigt som klassfiltrets explicita omhämtning blir en
  // dubbelhämtning som ser överflödig ut för nästa läsare.
  expect(anrop, "Månadsbytet skickade ett nätverksanrop: " + JSON.stringify(anrop)).toEqual([]);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Inspelningar (/next/): ett långsammare filtersvar får inte skriva över ett nyare", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  const { klass } = filter(vy);
  const meta = vy.locator("article.kort .meta");

  // Tvingar fram överlappet: FÖRSTA svaret hålls tillbaka så det landar SIST.
  // page.route, inte window.fetch-dubbleringen från
  // transkribera-korning.spec.mjs — den behövdes bara för att mata en SSE-ström
  // i egen takt; här räcker en fördröjning före route.continue().
  //
  // Routen registreras EFTER att vyn laddats, så räknaren börjar på
  // klassbytena och inte på monteringens egna hämtningar (laddaLektioner OCH
  // kollaHistorik hämtar båda /api/lessons vid flikbytet).
  //
  // Routen resolvar dessutom ett löfte när det fördröjda svaret VERKLIGEN
  // levererats till sidan. Den andra kortassertionen nedan väntar på det löftet
  // i stället för på en fast paus, och skälet är att den assertionen är testets
  // enda tandade: den FÖRSTA kan bara mäta att 9A:s svar ännu inte hunnit fram.
  // Går en gissad paus ut innan det fördröjda svaret levererats blir testet
  // FALSKT GRÖNT och generationsvakten står otestad.
  let slappFordrojda;
  const fordrojdaSvaretLevererat = new Promise((r) => (slappFordrojda = r));

  let n = 0;
  await page.route("**/api/lessons*", async (route) => {
    if (++n !== 1) return route.continue();
    await new Promise((r) => setTimeout(r, 1500));
    // fetch + fulfill i stället för continue: bara så går det att veta NÄR
    // svaret lämnades över till sidan. continue() returnerar när begäran
    // släppts vidare, inte när svaret kommit tillbaka.
    await route.fulfill({ response: await route.fetch() });
    slappFordrojda();
  });

  // selectOption väntar inte in nätverket, så de två bytena överlappar.
  await klass.selectOption({ label: "9A" });
  await klass.selectOption({ label: "9B" });

  // Det ANDRA svaret måste vinna. Utan generationsvakten i laddaLektioner
  // landar 9A:s svar sist och skriver över 9B:s — korten visar då den FÖRSTA
  // klassens lektioner medan 9B står kvar i rutan.
  await expect(meta).toHaveText([META("B3")]);
  expect(n, "Båda klassbytena nådde inte servern").toBe(2);

  // Och läget står KVAR när det INAKTUELLA svaret väl landat — det här är
  // testets enda assertion med tänder, eftersom den ovan lika gärna kan ha mätt
  // att 9A:s svar ännu inte hunnit fram.
  //
  // Väntan är därför KAUSAL och inte tidsbaserad: löftet resolvas när det
  // fördröjda svaret levererats till sidan, och de två renderingsrutorna efter
  // det gör att en eventuell överskrivning redan slagit igenom i DOM:en när
  // assertionen körs. Fristen är generös men ÄNDLIG, så ett svar som verkligen
  // hänger ger ett begripligt fel i stället för en tyst grön.
  await vantaPa(
    fordrojdaSvaretLevererat,
    "Det fördröjda /api/lessons-svaret levererades aldrig — överlappet uppstod aldrig",
  );
  await tvaRutor(page);
  await expect(meta).toHaveText([META("B3")]);
  await expect(klass.locator("option:checked")).toHaveText("9B");

  await page.unroute("**/api/lessons*");
  expect(errors, errors.join("\n")).toEqual([]);
});

test("Inspelningar (/next/): redigeringen sparar med PATCH och kortet visar det nya värdet", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  const kort = vy.locator("article.kort");
  const meta = vy.locator("article.kort .meta");

  const patchar = [];
  page.on("request", (r) => {
    if (r.method() === "PATCH") patchar.push(new URL(r.url()).pathname);
  });

  await kort.first().getByRole("button", { name: "Redigera" }).click();

  // Dialogen är ett native <dialog> som öppnas med showModal(). Den lokaliseras
  // på sin tillgängliga roll och etikett, inte på en klass — showModal() ger
  // role="dialog" och aria-modal från webbläsaren.
  const dialog = page.getByRole("dialog", { name: "Redigera lektionsuppgifter" });
  await expect(dialog).toBeVisible();

  await dialog.getByLabel("Sal").fill("C99");
  await dialog.getByRole("button", { name: "Spara" }).click();

  // Dialogen stängs, kortet visar det nya värdet, och listan är omhämtad från
  // servern — inte lokalt petad.
  await expect(dialog).toBeHidden();
  await expect(meta).toHaveText([META("C99"), META("A2"), META("B3")]);

  expect(patchar, "Sparandet skickade inte exakt en PATCH").toHaveLength(1);
  expect(patchar[0]).toMatch(/^\/api\/lessons\/\d+$/);

  // Och det gick hela vägen till disken: en omladdning visar samma värde.
  await oppnaInspelningar(page);
  await expect(meta).toHaveText([META("C99"), META("A2"), META("B3")]);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Inspelningar (/next/): raderingen skickar DELETE och kortet försvinner", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const vy = await oppnaInspelningar(page);
  const kort = vy.locator("article.kort");
  const meta = vy.locator("article.kort .meta");

  const raderingar = [];
  page.on("request", (r) => {
    if (r.method() === "DELETE") raderingar.push(new URL(r.url()).pathname);
  });

  await kort.last().getByRole("button", { name: "Radera" }).click();

  // Bekräftelsen är MEDVETET ingen confirm(): den går varken att styla eller
  // att testa. Den namnger lektionen och säger vad som faktiskt försvinner.
  // Den är ett native <dialog> som öppnas med showModal(), precis som
  // redigeringsdialogen — den destruktiva av de två får inte vara den som saknar
  // fokusfälla, Escape och fokusåterställning.
  const bekraft = vy.locator(".bekraft");
  await expect(bekraft).toBeVisible();
  await expect(bekraft).toContainText("Ta bort");
  await expect(bekraft).toContainText("Lektionen tas bort ur lektionsdatabasen och historiken");

  // ESCAPE stänger, och det är webbläsarens showModal() som ger den — inte egen
  // kod. Den handgjorda tabindex="-1"-diven den ersatte ignorerade Escape helt.
  await page.keyboard.press("Escape");
  await expect(bekraft).toBeHidden();

  // FOKUS ÅTERSTÄLLS till knappen som öppnade rutan. Det är hela skälet till att
  // dialogen är ALLTID monterad i stället för {#if}-grindad: avmonteras den i
  // stängningsögonblicket kör close() aldrig, och fokus hamnar på <body>.
  await expect(kort.last().getByRole("button", { name: "Radera" })).toBeFocused();
  expect(raderingar, "Escape skickade ett DELETE").toEqual([]);

  // Avbryt måste vara lika ofarligt — annars är bekräftelsen ingen bekräftelse.
  await kort.last().getByRole("button", { name: "Radera" }).click();
  await expect(bekraft).toBeVisible();
  await bekraft.getByRole("button", { name: "Avbryt" }).click();
  await expect(bekraft).toBeHidden();
  await expect(meta).toHaveText([META("A1"), META("A2"), META("B3")]);
  expect(raderingar, "Avbryt skickade ett DELETE").toEqual([]);

  await kort.last().getByRole("button", { name: "Radera" }).click();
  await vy.locator(".bekraft").getByRole("button", { name: "Radera" }).click();

  await expect(meta).toHaveText([META("A1"), META("A2")]);
  expect(raderingar, "Raderingen skickade inte exakt ett DELETE").toHaveLength(1);
  expect(raderingar[0]).toMatch(/^\/api\/lessons\/\d+$/);

  // Vecka 13 hade bara det kortet — hela gruppen ska vara borta, inte stå kvar
  // tom med rubrik och "0 inspelningar".
  //
  // AVGRÄNSAT TILL .grupp — se motiveringen vid samma mönster ovan (rad ~314).
  await expect(vy.locator(".grupp").getByRole("heading", { level: 2 })).toHaveText(["Vecka 14"]);

  // Och raderingen nådde disken: efter en omhämtning är kortet fortfarande
  // borta.
  await oppnaInspelningar(page, { kort: 2 });
  await expect(meta).toHaveText([META("A1"), META("A2")]);

  expect(errors, errors.join("\n")).toEqual([]);
});

/**
 * DELETE:ets 409. Planens enda uttalade MÅSTE, och fram till nu utan en enda
 * rad täckning: inget test i sviten skrev insp.fel över huvud taget, så
 * data-testid="insp-statusrad" refererades av noll spärrar.
 *
 * VARFÖR EN FEJK ÄR RÄTT HÄR. Ett äkta 409 kräver att resultatmappen är låst av
 * en annan process — det gjorde Task 4 manuellt, EN gång, och efter merge finns
 * ingenting som fångar en regression. Invändningen "att fejka svaret hade bara
 * testat vår egen fejk" gäller om man prövar SERVERN. Det som prövas här är
 * KLIENTENS visningsväg: att !r.ok-grenen i bekraftaRadera plockar serverns text
 * ur kroppen, lägger den i insp.fel, och att båda felnoderna i vyn visar den
 * medan kortet står kvar. Ingen del av den kedjan är fejkad.
 *
 * Kroppen är serverns EGNA, ordagrant ur app/web/server.py:1030-1032 — går den
 * texten isär från serverns är det den här assertionen som säger det.
 *
 * BAKGRUNDEN som gör felet nödvändigt: backend raderar mappen FÖRST och lämnar
 * vid 409 medvetet både lektionsraden och historikposten intakta. Sväljs
 * beskedet står kortet alltså kvar efter nästa hämtning, utan förklaring — och
 * B2-B5 ärver både felrörledningen och den här statusraden.
 */
test("Inspelningar (/next/): raderingens 409 når läraren och kortet står kvar", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const SERVERTEXT = "kunde inte radera mappen — en fil kan vara öppen";

  const vy = await oppnaInspelningar(page);
  const kort = vy.locator("article.kort");
  const meta = vy.locator("article.kort .meta");

  // BARA DELETE fångas. GET /api/lessons måste fortsätta gå till den riktiga
  // backenden — annars är korten nedan fejkade och "kortet står kvar" mäter
  // ingenting. page.route påverkar inte request-fixturen, så beforeEach/
  // afterEach bygger och river fixturen oberoende av routen.
  let raderingar = 0;
  await page.route("**/api/lessons/*", async (route) => {
    if (route.request().method() !== "DELETE") return route.continue();
    raderingar++;
    await route.fulfill({ status: 409, json: { error: SERVERTEXT } });
  });

  // Loggen registreras FÖRE klicket: en av sakerna som prövas är att felgrenen
  // INTE hämtar om listan.
  const anrop = loggaLektionsanrop(page);

  await kort.last().getByRole("button", { name: "Radera" }).click();
  await vy.locator(".bekraft").getByRole("button", { name: "Radera" }).click();

  // KÄRNAN: SERVERNS text, inte vår reservtext ("Kunde inte radera lektionen."),
  // i den SYNLIGA felraden. Reservtexten säger inte att en fil är öppen, och
  // det är den upplysningen som gör felet åtgärdbart.
  const statusrad = vy.locator('[data-testid="insp-statusrad"]');
  await expect(statusrad).toHaveText(SERVERTEXT);
  await expect(statusrad).toBeVisible();

  // Och i live-regionen, som är den enda vägen fram för en skärmläsare: den
  // synliga kopian är aria-hidden och finns inte i tillgänglighetsträdet.
  //
  // getByRole("status") och INTE locator("p.fel-sr"): den här panelen innehåller
  // TVÅ noder med den klassen — vyns egen och RedigeraLektions, som ligger inuti
  // <section class="view"> eftersom dialogen alltid är monterad. En CSS-räkning
  // ger alltså 2 och fälls av strict mode (uppmätt, inte antaget: det var precis
  // så den här raden gick sönder första gången). Tillgänglighetsträdet ger 1 —
  // den stängda dialogen är display:none och därmed borta ur det — och det är
  // trädet frågan handlar om. Fällan står nedskriven i playwright.config.ts:
  // varje spec B2-B5 lägger till ärver den.
  await expect(vy.getByRole("status")).toHaveText(SERVERTEXT);

  // KORTET STÅR KVAR. Klienten får inte plocka bort det optimistiskt — servern
  // har medvetet lämnat både lektionsraden och historikposten intakta, så ett
  // borttaget kort hade varit en ren lögn som nästa hämtning ändå avslöjar.
  await expect(meta).toHaveText([META("A1"), META("A2"), META("B3")]);
  await expect(kort).toHaveCount(3);

  // Bekräftelsen stängs — beskedet hör hemma i vyns statusrad, inte bakom en
  // ruta läraren måste stänga. toBeHidden och inte toHaveCount(0): den passerar
  // både för en avmonterad ruta och för en stängd <dialog> (display:none).
  await expect(vy.locator(".bekraft")).toBeHidden();

  // Exakt ETT DELETE, och INGEN omhämtning efteråt. Omhämtningen är medvetet
  // utelämnad i felgrenen (actions.js): laddaLektioner sätter insp.fel = '' vid
  // ett lyckat svar, så en omhämtning här hade rensat beskedet innan läraren
  // hunnit läsa det — kortet hade stått kvar helt utan förklaring, vilket är
  // exakt det feltillstånd hela det här testet finns för att förbjuda.
  expect(raderingar, "Raderingen skickade inte exakt ett DELETE").toBe(1);
  expect(
    anrop,
    "Felgrenen hämtade om lektionslistan och riskerade att rensa felet: " + JSON.stringify(anrop),
  ).toEqual([]);

  await page.unroute("**/api/lessons/*");

  // Chromes egen "Failed to load resource … 409 (Conflict)" är testets
  // injektion, inte ett appfel — se appfel().
  expect(appfel(errors), appfel(errors).join("\n")).toEqual([]);
});

test("Inspelningar (/next/): de två tomtillstånden är inte utbytbara", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const TOMT_ARKIV = "Inga inspelningar än. Transkribera en lektion så dyker den upp här.";
  const TOMT_FILTER = "Inga inspelningar matchar dina filter.";

  const vy = await oppnaInspelningar(page);
  const { klass, kurs, manad } = filter(vy);
  const kort = vy.locator("article.kort");

  // Fullt arkiv, inga filter: inget av beskeden ska synas.
  await expect(vy.getByText(TOMT_ARKIV)).toHaveCount(0);
  await expect(vy.getByText(TOMT_FILTER)).toHaveCount(0);

  // LÄGE 1 — arkivet är fullt men filtren döljer allt. Månaden väljs FÖRST,
  // medan alla tre lektionerna är hämtade och båda månaderna alltså finns i
  // rutan; klassbytet krymper sedan listan till vecka 13, som ligger i mars.
  await manad.selectOption({ label: "apr 2026" });
  await klass.selectOption({ label: "9B" });
  await expect(kort).toHaveCount(0);
  await expect(vy.getByText(TOMT_FILTER)).toBeVisible();
  await expect(
    vy.getByText(TOMT_ARKIV),
    "En lärare med fullt arkiv fick beskedet att hon aldrig spelat in något",
  ).toHaveCount(0);

  // LÄGE 1b — klassfiltret ENSAMT, på en klass utan lektioner. Det är den
  // exakta konflationen filtertermerna i första villkoret finns för: klassen är
  // ett SERVERfilter, så insp.lessons är [] här precis som i ett tomt arkiv.
  // Utan !insp.filterGroup hade fel besked stått på skärmen.
  await manad.selectOption({ label: "Alla månader" });
  await klass.selectOption({ label: TOM_KLASS });
  await expect(kort).toHaveCount(0);
  await expect(vy.getByText(TOMT_FILTER)).toBeVisible();
  await expect(
    vy.getByText(TOMT_ARKIV),
    "Ett tomt SERVERfilter förväxlades med ett tomt arkiv",
  ).toHaveCount(0);

  // LÄGE 1c — KURSfiltret ENSAMT, på en kurs utan lektioner. Villkorets FJÄRDE
  // term (!insp.filterCourse) har ingen annan täckning i filen: läge 1 lämnar
  // insp.lessons med ETT kort (månaden döljer det på klienten, så filtertermerna
  // utövas inte alls där) och läge 1b utövar bara klasstermen. Utan det här
  // läget går !insp.filterCourse att stryka ur villkoret utan att ett enda test
  // faller — och felläget är exakt det steget finns för att förbjuda: en lärare
  // med fullt arkiv får "Inga inspelningar än" så fort hon väljer en kurs hon
  // ännu inte spelat in något i.
  await klass.selectOption({ label: "Alla klasser" });
  // Arkivet ÄR fullt här. Utan den kontrollen vore nollan nedan trivial: läge
  // 1b lämnade redan noll kort på skärmen.
  await expect(kort).toHaveCount(3);
  await kurs.selectOption({ label: TOM_KURS });
  await expect(kort).toHaveCount(0);
  await expect(vy.getByText(TOMT_FILTER)).toBeVisible();
  await expect(
    vy.getByText(TOMT_ARKIV),
    "Ett tomt KURSfilter förväxlades med ett tomt arkiv",
  ).toHaveCount(0);

  // LÄGE 2 — arkivet är verkligen tomt. Raderas via API:et och hämtas om genom
  // ett riktigt flikbyte (hämtningarna är grindade på nav.tab, inte montering).
  await kurs.selectOption({ label: "Alla kurser" });
  await expect(kort).toHaveCount(3);
  await toemArkivet(page.request);

  await page.getByRole("button", { name: "Transkribera", exact: true }).click();
  await page.getByRole("button", { name: "Inspelningar", exact: true }).click();

  await expect(kort).toHaveCount(0);
  await expect(vy.getByText(TOMT_ARKIV)).toBeVisible();
  await expect(
    vy.getByText(TOMT_FILTER),
    "Ett tomt arkiv skyllde på filter som inte är satta",
  ).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Inspelningar (/next/): ärlighetsvakten räknar historikposter utan lektionsrad", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Skillnaden mellan history.json och lektionstabellen går INTE att framkalla
  // via API:et: create_lesson ligger i ett try/except som bara loggar
  // (server.py:682-696), och enda vägen dit är en riktig DB-miss. Servern
  // svarar därför sanningsenligt om historiken (tre poster) medan det
  // OFILTRERADE /api/lessons kortas ner med en post på vägen in — exakt den
  // asymmetri en tappad lektionsrad ger.
  //
  // route.fetch() hämtar serverns EGNA svar och trimmar det, i stället för att
  // hitta på en kropp: kortens innehåll ska fortsätta komma från den riktiga
  // backenden, annars mäter assertionerna nedan bara fixturen.
  // Trimningen stängs av med en FLAGGA i stället för page.unroute(): ett
  // "Alla klasser"-val skickar ett ofiltrerat /api/lessons, och att kalla
  // unroute medan just det anropet ligger inne i route.fetch() ger
  // "Route is already handled!".
  //
  // slappTrimmat signalerar när ett trimmat svar VERKLIGEN levererats till
  // sidan. Flikbytet längre ner väntar på den signalen i stället för på en
  // gissad paus — se kommentaren där.
  let slappTrimmat = () => {};
  const nastaTrimmadeSvar = () => new Promise((r) => (slappTrimmat = r));

  let trimma = true;
  await page.route("**/api/lessons*", async (route) => {
    const u = new URL(route.request().url());
    if (!trimma || route.request().method() !== "GET" || u.search) return route.continue();
    const svar = await route.fetch();
    await route.fulfill({ json: (await svar.json()).slice(1) });
    slappTrimmat();
  });

  const vy = await oppnaInspelningar(page, { kort: 2 });

  // SINGULARgrenen: en post saknas. BÅDA meningarna böjs — "1 inspelning ...
  // De går att öppna" vore fel numerus på pronomenet.
  await expect(
    vy.getByText(
      "1 inspelning finns i historiken men saknas i kartoteket. Den går att öppna i den gamla appen.",
    ),
  ).toBeVisible();

  // Vakten gör ett EGET, ofiltrerat anrop — talet ska alltså inte följa den
  // filtrerade vyn. Härleddes det ur insp.lessons.length skulle ett klassbyte
  // som lämnar ett kort kvar göra beskedet till "2 inspelningar".
  //
  // FLIKBYTET NEDAN ÄR ASSERTIONENS TÄNDER, inte kosmetik. kollaHistorik() körs
  // BARA ur monteringseffekten, som är grindad på nav.tab
  // (InspelningarView.svelte) — ett klassbyte kör den alltså aldrig om. Utan
  // flikbytet skulle en implementation som räknade antalH - insp.lessons.length
  // VID MONTERINGEN lämna historikExtra orört genom klassbytet, och raden nedan
  // hade passerat på ett tal som ingen räknat om. Bara en $derived-variant hade
  // fällts.
  //
  // Med flikbytet körs vakten om medan ett SERVERfilter är aktivt. Routen ovan
  // trimmar bara det OFILTRERADE svaret, så rätt kod ser fortfarande 3 - 2 = 1
  // medan en läsning av den filtrerade listan ger 3 - 1 = 2 och fäller raden.
  const { klass } = filter(vy);
  await klass.selectOption({ label: "9B" });
  await expect(vy.locator("article.kort")).toHaveCount(1);

  // Vaktens omräkning väntas IN, inte gissas. Assertionen efteråt hade annars
  // kunnat läsa det gamla talet (1, skrivet vid monteringen) innan flikbytets
  // omräkning ens skett — och då hade även den felaktiga implementationen
  // passerat. kollaHistorik skriver först när BÅDA dess hämtningar landat, så
  // båda väntas in: /api/history går direkt till servern, det ofiltrerade
  // /api/lessons genom routen ovan.
  const historikOm = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/history",
    { timeout: 15_000 },
  );
  const lektionerOm = nastaTrimmadeSvar();

  await page.getByRole("button", { name: "Transkribera", exact: true }).click();
  await page.getByRole("button", { name: "Inspelningar", exact: true }).click();

  await historikOm;
  await vantaPa(
    lektionerOm,
    "Vaktens ofiltrerade GET /api/lessons levererades aldrig efter flikbytet",
  );
  await tvaRutor(page);

  await expect(vy.locator("article.kort")).toHaveCount(1);
  await expect(
    vy.getByText("1 inspelning finns i historiken men saknas i kartoteket."),
    "Vakten läste den FILTRERADE listan i stället för hela arkivet",
  ).toBeVisible();

  // Utan avvikelse säger vyn ingenting alls — raden är ett besked, inte en
  // permanent etikett.
  trimma = false;
  await klass.selectOption({ label: "Alla klasser" });
  await page.getByRole("button", { name: "Transkribera", exact: true }).click();
  await page.getByRole("button", { name: "Inspelningar", exact: true }).click();
  await expect(vy.locator("article.kort")).toHaveCount(3);
  await expect(vy.getByText(/saknas i kartoteket/)).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});
