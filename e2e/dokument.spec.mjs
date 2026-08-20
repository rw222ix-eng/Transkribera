import { expect, test } from "@playwright/test";

/* DOKUMENTPERSISTENSEN — Sparat-högen, versionsarrayen och klassprofilen
 *
 * Allt det här levde i RAM och dog vid omladdning. Etapp 0.2 flyttade det till
 * servern utan att röra designen, och tre saker måste hålla:
 *
 *   1. Högen som ritas är SERVERNS papper, inte prototypens.
 *   2. Varje ändring når servern — ett papper som ser sparat ut men inte är
 *      det är värre än ett som syns försvinna.
 *   3. Utan server står prototypen kvar. Designprojektet har ingen.
 */

const SCHEMA = { schema: [], lov: [], poster: [] };

function papper(extra = {}) {
  return {
    typ: "Arbetsblad", moment: "primitiva funktioner", klass: "9A",
    kurs: "Matematik 3c", datum: "2026-06-02", tid: "",
    gy: ["Primitiva funktioner"], kalla: false, kallor: [],
    inst: { antal: 3, niva: "Blandat", facit: "Facit i bladet", illustration: false },
    bilder: {}, referenser: [], forlaga: null, resultat: null, fokus: "",
    kontext: "start", niva: false, svarighet: 0, andrat: [],
    anteckning: "Sparat tidigare", uppgifter: [{ nr: 1, t: "Beräkna", p: 2 }],
    ...extra,
  };
}

const rad = (id, dok, extra = {}) => ({
  id, status: "godkant", markor: 0, sort: id, foljd: null,
  versioner: [dok], dokument: { ...dok, id }, ...extra,
});

/** Fejkar datagrunden + dokumentlagret. `anrop` samlar allt som skrivs. */
async function fejka(page, { sparade = [], utkast = null, profil = {} } = {}) {
  const anrop = [];
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => {
    const r = route.request();
    if (r.method() === "PUT") {
      anrop.push({ metod: "PUT", vag: "/api/klassprofil", kropp: r.postDataJSON() });
      return json(route, r.postDataJSON());
    }
    return json(route, profil);
  });
  await page.route("**/api/dokument", route => json(route, { sparade, utkast }));
  await page.route("**/api/dokument/**", route => {
    const r = route.request();
    const vag = new URL(r.url()).pathname;
    const kropp = r.method() === "DELETE" ? null : r.postDataJSON();
    anrop.push({ metod: r.method(), vag, kropp });
    if (r.method() === "DELETE") return json(route, { ok: true });
    if (vag.endsWith("/ordning")) return json(route, { ok: true });
    return json(route, rad(99, (kropp && kropp.dokument) || papper()));
  });
  // POST /api/dokument delar väg med listningen — metoden skiljer dem åt.
  await page.route("**/api/dokument", route => {
    const r = route.request();
    if (r.method() !== "POST") return json(route, { sparade, utkast });
    const kropp = r.postDataJSON();
    anrop.push({ metod: "POST", vag: "/api/dokument", kropp });
    return json(route, rad(100 + anrop.length, kropp.dokument, { status: kropp.status }));
  });
  return anrop;
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

test("högen är serverns papper, inte prototypens", async ({ page }) => {
  await fejka(page, { sparade: [rad(1, papper({ moment: "integraler" }))] });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  const hog = await page.evaluate(() => window.Dokument.sparade());
  expect(hog[0].moment).toBe("integraler");
  // Prototypens elva papper får inte ligga kvar bredvid lärarens egna.
  expect(hog.some(v => v.moment === "deriveringsregler")).toBe(false);
});

test("ett rättat prov behåller sitt utfall över omladdningen", async ({ page }) => {
  const rattat = { elever: 22, andel: 0.68, varden: {}, svaga: [{ kod: "5b", andel: 0.34 }] };
  await fejka(page, { sparade: [rad(1, papper({ typ: "Prov", rattat }))] });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  const v = await page.evaluate(() => window.Dokument.sparade()[0]);
  expect(v.rattat.andel).toBe(0.68);
  expect(v.rattat.svaga[0].kod).toBe("5b");
});

test("utkastet ligger framme igen, på sin plats i ångra-historiken", async ({ page }) => {
  const versioner = [
    papper({ anteckning: "Första utkastet" }),
    papper({ svarighet: 1, anteckning: "Svårare uppgifter" }),
    papper({ kontext: "fysik", anteckning: "Fysikaliskt sammanhang" }),
  ];
  await fejka(page, {
    utkast: { id: 7, status: "utkast", markor: 1, sort: 0, foljd: null,
              versioner, dokument: versioner[1] },
  });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();

  await expect(page.locator("#dokument")).toBeVisible();
  // Markören stod på ändring 1 av 2 — inte på den sista, och inte på den första.
  await expect(page.locator("#histnot")).toHaveText("Ändring 1 av 2 · Svårare uppgifter");
  await expect(page.locator("#angra")).toBeEnabled();
  await expect(page.locator("#gorom")).toBeEnabled();
  // Stegen ovanför är ifyllda: pappret hänger inte över en tom planering.
  await expect(page.locator("#moment")).toHaveValue("primitiva funktioner");
});

test("ett nytt papper skickas till servern", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await page.evaluate(() => window.Dokument.arbetsbladAv(
    [{ t: "Beräkna arean", p: 3 }], "integraler", { klass: "9A", kurs: "Matematik 3c" }));

  await expect.poll(() => anrop.filter(a => a.metod === "POST").length).toBe(1);
  const post = anrop.find(a => a.metod === "POST");
  expect(post.kropp.status).toBe("godkant");
  expect(post.kropp.dokument.moment).toBe("integraler");
  expect(post.kropp.dokument.uppgifter[0].t).toBe("Beräkna arean");
});

test("en radering når servern — och ångrandet skriver tillbaka pappret", async ({ page }) => {
  const anrop = await fejka(page, { sparade: [rad(1, papper())] });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);

  await page.evaluate(() => window.Dokument.radera(window.Dokument.sparade()[0]));
  await expect.poll(() => anrop.some(a => a.metod === "DELETE")).toBe(true);

  await page.locator(".toast button", { hasText: "Ångra" }).click();
  await expect.poll(() => anrop.some(a => a.metod === "POST")).toBe(true);
  // Pappret ska tillbaka på sin plats i högen, inte sist.
  await expect.poll(() => anrop.some(a => a.vag.endsWith("/ordning"))).toBe(true);
});

test("rättningen skrivs rakt på pappret, utan ny version", async ({ page }) => {
  const anrop = await fejka(page, { sparade: [rad(1, papper({ typ: "Prov" }))] });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);

  await page.evaluate(() => {
    const v = window.Dokument.sparade()[0];
    v.rattat = { elever: 22, andel: 0.71, svaga: [] };
    window.Dokument.andrad(v);
  });
  await expect.poll(() => anrop.filter(a => a.metod === "PATCH").length).toBe(1);
  const p = anrop.find(a => a.metod === "PATCH");
  expect(p.vag).toBe("/api/dokument/1");
  expect(p.kropp.dokument.rattat.andel).toBe(0.71);
  // Ingen ny version: utfallet är fakta om pappret, inte en ändring att ångra.
  expect(anrop.some(a => a.vag.endsWith("/versioner"))).toBe(false);
});

test("klassprofilen läses ur servern och skrivs tillbaka dit", async ({ page }) => {
  const profil = {
    "9A": { kurs: "Matematik 3c", kursN: 12, bok: "Matematik 5000+ 3c", bokN: 12,
            senasteSida: 244, sidorPerLektion: 5, taktN: 8, typer: { Tavla: 9 }, n: 12 },
  };
  const anrop = await fejka(page, { profil });
  await page.goto("/");
  await hydrerad(page);

  await expect.poll(() => page.evaluate(() => window.Profil.minne()["9A"].senasteSida)).toBe(244);
  // Första skrivningen är läkningen vid start; den vi väntar på är lärandet.
  const putar = () => anrop.filter(a => a.vag === "/api/klassprofil");
  await expect.poll(() => putar().length).toBeGreaterThan(0);
  const fore = putar().length;
  await page.evaluate(() => window.Profil.sattLage("9A", "Matematik 3c", 260));
  await expect.poll(() => putar().length).toBeGreaterThan(fore);
  expect(putar().pop().kropp["9A"].senasteSida).toBe(260);
});

test("utan server står prototypens hög kvar", async ({ page }) => {
  await page.route("**/api/var-kors", route => route.abort());
  await page.goto("/");
  await page.waitForFunction(() => document.documentElement.hasAttribute("data-server") === false);
  const hog = await page.evaluate(() => window.Dokument.sparade());
  expect(hog.length).toBeGreaterThan(0);
  expect(hog.some(v => v.moment === "deriveringsregler")).toBe(true);
  // Ingenting av det här skrivs någonstans — och det är sant om prototypen.
  expect(await page.evaluate(() => window.Dokument.sparade()[0].id)).toBeUndefined();
});

// ── Ladda ner PDF ───────────────────────────────────────────────────────────
// Knappen laddade inte ner något: den väntade 850 ms, sa «Sparad» och toastade
// «PDF:en ligger i Hämtat». Ingen fil, ingen begäran, inget i Hämtat.

/** Öppnar förhandsvisningen av det första sparade pappret. Högen har ingen
 *  egen vy längre — materialet ligger på sin lektion i veckan — så vägen in är
 *  den appen själv använder: window.Dokument.visa(i). */
async function oppnaForhandsvisning(page) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await visa(page, 0);
}

/** Byter papper i den öppna förhandsvisningen. Fliken klickas INTE här: när
 *  rutan redan står framme ligger dess skal över flikraden och fångar klicket. */
async function visa(page, i) {
  await page.evaluate(n => window.Dokument.visa(n), i);
  await expect(page.locator("#forhandsskal")).toBeVisible();
}

test("PDF-knappen hämtar provets riktiga PDF och sparar den", async ({ page }) => {
  const hamtat = [];
  await fejka(page, { sparade: [rad(1, papper({ typ: "Prov", provId: 42 }))] });
  await page.route("**/api/exams/42/pdf", route => {
    hamtat.push(route.request().url());
    return route.fulfill({ status: 200, contentType: "application/pdf",
                           body: Buffer.from("%PDF-1.5 riktig pdf") });
  });
  await page.goto("/");
  await hydrerad(page);
  await oppnaForhandsvisning(page);

  const nedladdning = page.waitForEvent("download", { timeout: 15_000 });
  await page.locator("#fh-pdf").click();
  const fil = await nedladdning;
  expect(hamtat).toHaveLength(1);
  expect(fil.suggestedFilename()).toMatch(/\.pdf$/);
});

/* En tavla i wb-json-v1, som lesson_board skriver dem (jfr e2e/tryck.spec.mjs). */
const tavla = () => ({
  title: "Derivatans definition",
  boards: [{
    name: "genomgang", width: 1400, height: 460, chrome: "aluminium",
    padding: { top: 24, right: 26, bottom: 24, left: 30 },
    sections: [
      { kind: "heading", text: "Derivatans definition", size: 30 },
      { kind: "text", text: "Ändringskvoten när h går mot noll.", size: 19 },
      { kind: "math", latex: "f'(x)=\\lim_{h\\to 0}\\frac{f(x+h)-f(x)}{h}", size: 21 },
    ],
  }],
});

/* Bokens uppgifter som ett dokument bär dem (Uppgifter.urval) — med SKRIVET
   innehåll, som /api/bocker/{id}/losningar lämnar det. Nivå 1–2 blir ett
   svarsfacit, nivå 3 ett eget lösningsark: två ark. */
const bokuppg = () => ({
  bok: "Matematik 5000+ 3c", sidor: "244–247", avsnitt: "3.2 Derivata", bokId: null,
  uppg: [3101, 3102, 3110], bort: [], remsa: "3101–3102, 3110", bortremsa: "",
  losning: {
    niva: "Nivå 2 och 3", antal: 3, uppg: [3101, 3102, 3110], remsa: "3101–3102, 3110",
    poster: [
      { nr: 3101, niva: 1, text: "Bestäm $f'(x)$ när $f(x) = x^2$.",
        svar: "$2x$", vag: [["$x^2 \\to 2x$", "potensregeln"]] },
      { nr: 3102, niva: 2, text: "Beräkna $f'(3)$ när $f(x) = x^2$.",
        svar: "$6$", vag: [["$f'(x) = 2x$", "derivera först"]] },
      { nr: 3110, niva: 3, text: "Bestäm tangentens ekvation i $x = 1$.",
        svar: "$y = 2x - 1$", vag: [["$k = f'(1) = 2$", "lutningen är derivatan"],
                                    ["$y - 1 = 2(x - 1)$", "enpunktsformen"]] },
    ],
  },
});

test("förhandsvisningen visar tavlan — och lösningsbladen ligger kvar under den", async ({ page }) => {
  /* Läraren såg BARA lösningsförslagen när hon klickade på tavlan i schemat.
     #fh-ark är en flexlåda, traven blir dess flex-item, och krympningen lades
     helt på tavrutan (enda barnet med min-height 0). Tavlan mätte 0 px trots
     sin inline-höjd. Båda halvorna av buggen mäts här: tavlan ska ha höjd OCH
     bladen ska fortfarande ligga under den. */
  await fejka(page, { sparade: [rad(1, papper({
    typ: "Tavla", wbId: "abc", wb: tavla(), bokuppg: bokuppg() }))] });
  await page.goto("/");
  await hydrerad(page);
  await oppnaForhandsvisning(page);

  await expect.poll(() => page.evaluate(() => {
    const r = document.querySelector("#fh-ark .tavruta");
    return r ? Math.round(r.getBoundingClientRect().height) : 0;
  }), { timeout: 20_000 }).toBeGreaterThan(100);
  await expect(page.locator("#fh-ark .bladtrav .blad")).toHaveCount(2);
});

test("«Radera» i förhandsvisningen kastar pappret — och Ångra tar tillbaka det", async ({ page }) => {
  /* Det fanns ingen väg alls att kasta ett dokument: kortens radera-knapp
     ritades bara i #sparatnat, som inte finns i app.html längre. Vägen går nu
     via förhandsvisningen, där man SER vad man raderar. */
  const anrop = await fejka(page, { sparade: [rad(1, papper({ moment: "integraler" }))] });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  await oppnaForhandsvisning(page);

  // Ett klick raderar inte: frågan står i modalen, ovanpå pappret.
  await page.locator("#fh-radera").click();
  await expect(page.locator("#forhandsskal .dokfraga")).toBeVisible();
  expect(anrop.some(a => a.metod === "DELETE")).toBe(false);

  await page.locator("#forhandsskal .dokfraga [data-a='ja']").click();
  await expect.poll(() => anrop.some(a => a.metod === "DELETE")).toBe(true);
  // Rutan stängs: det som visades finns inte längre.
  await expect(page.locator("#forhandsskal")).toBeHidden();
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(0);

  await page.locator(".toast button", { hasText: "Ångra" }).click();
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  await expect.poll(() => anrop.some(a => a.metod === "POST")).toBe(true);
});

test("raderingen tar provraden med sig — och Ångra märker pappret", async ({ page }) => {
  /* Bara dokumentraden raderades. Provet låg kvar i basen med sina uppgifter,
     och det är DEN raden minnet läser: ett kastat papper räknades i täckningen
     och gick in i nästa prompt som «undvik det du gjort förut».
     Ångra kan inte skriva tillbaka provraden — den och dess filer är borta — så
     pappret märks i stället. Att bära id:t vidare vore värre: SQLite
     återanvänder radnummer, och sökvägen hade förr eller senare hämtat någon
     annans PDF. */
  const examBort = [];
  await page.route("**/api/exams/**", route => {
    if (route.request().method() === "DELETE") {
      examBort.push(new URL(route.request().url()).pathname);
    }
    return route.fulfill({ status: 200, contentType: "application/json",
                           body: JSON.stringify({ ok: true }) });
  });
  await fejka(page, { sparade: [rad(1, papper({ typ: "Prov", provId: 42,
                                                pdf: "C:/prov.pdf" }))] });
  await page.goto("/");
  await hydrerad(page);
  await oppnaForhandsvisning(page);
  await page.locator("#fh-radera").click();
  await page.locator("#forhandsskal .dokfraga [data-a='ja']").click();

  await expect.poll(() => examBort).toEqual(["/api/exams/42"]);

  await page.locator(".toast button", { hasText: "Ångra" }).click();
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  const v = await page.evaluate(() => window.Dokument.sparade()[0]);
  expect(v.provBorta).toBe(true);
  expect(v.pdf).toBeUndefined();
  // Uppgifterna står kvar: de är dokumentets egna, och det är dem hon ville ha.
  expect(v.uppgifter).toHaveLength(1);
});

test("«Fortsätt ändra» lägger tillbaka pappret som utkast", async ({ page }) => {
  /* Godkännandet var en enkelriktad dörr: pappret gick inte att skriva om, och
     det enda gränssnittet erbjöd var «Bygg vidare» — en helt ny körning, alltså
     ett nytt papper och en ny nota, för att rätta en siffra i uppgift 3. */
  const oppnade = [];
  await page.route("**/api/exams/**", route => {
    const vag = new URL(route.request().url()).pathname;
    if (vag.endsWith("/oppna")) oppnade.push(vag);
    return route.fulfill({ status: 200, contentType: "application/json",
                           body: JSON.stringify({ id: 42, status: "utkast" }) });
  });
  const anrop = await fejka(page, {
    sparade: [rad(1, papper({ typ: "Prov", provId: 42 }))] });
  await page.goto("/");
  await hydrerad(page);
  await oppnaForhandsvisning(page);
  // Raden som säger varför knappen finns.
  await expect(page.locator("#fh-last")).toContainText("Godkänt är låst");

  await page.locator("#fh-fortsatt").click();
  await expect(page.locator("#forhandsskal")).toBeHidden();
  // Ur högen, tillbaka i rutan — och provet är upplåst på servern.
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(0);
  await expect(page.locator("#dokument")).toBeVisible();
  await expect.poll(() => oppnade).toEqual(["/api/exams/42/oppna"]);
  await expect.poll(() => anrop.some(
    a => a.metod === "PATCH" && a.kropp && a.kropp.status === "utkast")).toBe(true);
  // Det är pappret självt som ligger framme — med sina uppgifter, inte en tom
  // ruta som bara ser ut som ett utkast.
  await expect(page.locator("#arkskal")).toContainText("Beräkna");
});

test("«Behåll» i förhandsvisningen raderar ingenting", async ({ page }) => {
  const anrop = await fejka(page, { sparade: [rad(1, papper())] });
  await page.goto("/");
  await hydrerad(page);
  await oppnaForhandsvisning(page);

  await page.locator("#fh-radera").click();
  await page.locator("#forhandsskal .dokfraga [data-a='nej']").click();
  await expect(page.locator("#forhandsskal .dokfraga")).toBeHidden();
  await expect(page.locator("#forhandsskal")).toBeVisible();
  expect(anrop.some(a => a.metod === "DELETE")).toBe(false);
});

test("tavlan laddas ner som en PDF — inte som ett besked om att den är en bild", async ({ page }) => {
  // Knappen sa «lägg den i Skriv ut för en PDF»: tavlan var det enda pappret i
  // högen utan nedladdning. Den ritas av här och sätts på ett A4 på servern.
  const skickat = [];
  await fejka(page, { sparade: [rad(1, papper({ typ: "Tavla", wbId: "abc", wb: tavla() }))] });
  await page.route("**/api/tavla/pdf", route => {
    skickat.push(route.request().postDataJSON());
    return route.fulfill({ status: 200, contentType: "application/pdf",
                           body: Buffer.from("%PDF-1.7 tavlan som sida") });
  });
  await page.goto("/");
  await hydrerad(page);
  await oppnaForhandsvisning(page);

  const nedladdning = page.waitForEvent("download", { timeout: 30_000 });
  await page.locator("#fh-pdf").click();
  const fil = await nedladdning;
  expect(fil.suggestedFilename()).toMatch(/\.pdf$/);
  expect(skickat).toHaveLength(1);
  /* Det som skickas är tavlans egen avritning i full storlek — inte en tom
     duk. Och det är en LISTA: ett bräde per sida, i EN fil. Tavlan här har ett
     bräde, så listan är ett långt. */
  expect(Array.isArray(skickat[0].png)).toBe(true);
  expect(skickat[0].png).toHaveLength(1);
  expect(skickat[0].png[0].startsWith("data:image/png;base64,")).toBe(true);
  expect(skickat[0].png[0].length).toBeGreaterThan(10_000);
  await expect(page.locator("#fh-pdf")).toHaveText("Sparad");
});

test("tavlans nedladdning ger lösningsbladen som EGNA filer", async ({ page }) => {
  /* «Ladda ner PDF» på en tavla gav tavlan — men bokens lösningsförslag, som
     läraren just sett i samma trav, följde inte med. De har ingen fil på
     servern: de ritas i webbläsaren. Nu ritas de av och sätts på var sitt A4,
     ett papper per fil. */
  const skickat = [];
  await fejka(page, { sparade: [rad(1, papper({
    typ: "Tavla", wbId: "abc", wb: tavla(), bokuppg: bokuppg() }))] });
  await page.route("**/api/tavla/pdf", route => {
    skickat.push(route.request().postDataJSON());
    return route.fulfill({ status: 200, contentType: "application/pdf",
                           body: Buffer.from("%PDF-1.7 en sida") });
  });
  await page.goto("/");
  await hydrerad(page);
  await oppnaForhandsvisning(page);

  const filer = [];
  page.on("download", d => filer.push(d.suggestedFilename()));
  await page.locator("#fh-pdf").click();
  await expect(page.locator("#fh-pdf")).toHaveText("Sparad", { timeout: 60_000 });

  // Tavlan + svarsfacit + nivå 3-arket: tre filer, tre anrop.
  expect(skickat).toHaveLength(3);
  expect(filer).toHaveLength(3);
  /* Tavlan skickas som en lista (ett bräde per sida), bladen som var sin
     sträng — ett ark är ett papper och delas inte. */
  skickat.forEach(s => {
    [].concat(s.png).forEach(p => {
      expect(p.startsWith("data:image/png;base64,")).toBe(true);
      expect(p.length).toBeGreaterThan(10_000);
    });
  });
  // Namnen kommer ur arkens egna huvuden, inte ur dokumentets.
  const namn = skickat.map(s => s.namn);
  expect(namn.some(n => /Lösningsförslag · boken/.test(n))).toBe(true);
  expect(namn.some(n => /Lösningsförslag · nivå 3/.test(n))).toBe(true);
  expect(new Set(filer).size).toBe(3);   // ingen fil skriver över en annan
});

test("lösningsbladet laddar ner sin EGEN fil, inte originalets", async ({ page }) => {
  // Lösningsbladet är en KLON av sitt original och bär samma provId, så
  // knappen laddade ner provet när läraren bad om lösningsförslaget. De två
  // har egna filer bredvid: provets avritade lösningsark och bladets separata
  // facit. Provet hämtade förut `/bedomning` — lärarens LaTeX-satta
  // rättningsdokument, ett annat papper än det på skärmen.
  const hamtat = [];
  await fejka(page, { sparade: [
    rad(1, papper({ typ: "Prov", provId: 42, losningsblad: true })),
    rad(2, papper({ typ: "Arbetsblad", provId: 43, losningsblad: true })),
  ] });
  await page.route("**/api/exams/**", route => {
    hamtat.push(new URL(route.request().url()).pathname);
    return route.fulfill({ status: 200, contentType: "application/pdf",
                           body: Buffer.from("%PDF-1.5 losningarna") });
  });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(2);

  await page.getByRole("tab", { name: "Planering" }).click();
  for (const i of [0, 1]) {
    await visa(page, i);
    const nedladdning = page.waitForEvent("download", { timeout: 15_000 });
    await page.locator("#fh-pdf").click();
    await nedladdning;
    // Knappen står kvar på «Sparad» i knappt två sekunder och tar inga nya
    // klick under tiden — vänta ut den i stället för att missa nästa hämtning.
    await expect(page.locator("#fh-pdf")).toHaveText("Ladda ner PDF");
  }
  expect(hamtat).toEqual(["/api/exams/42/losningar", "/api/exams/43/facit"]);
});

test("varje pappersort hämtar sin egen byggda fil", async ({ page }) => {
  /* Fem sorter delar exams-tabellen och därmed rutten: prov, arbetsblad,
     gruppuppgift och diagnos bär `provId`, anteckningarna `antId` (samma
     tabell, egen router). Knappen ska fungera för alla fem — det är lätt att
     tro att den gör det och lika lätt att en sort tappar sitt id på vägen. */
  const hamtat = [];
  await fejka(page, { sparade: [
    rad(1, papper({ typ: "Prov", provId: 11 })),
    rad(2, papper({ typ: "Arbetsblad", provId: 12 })),
    rad(3, papper({ typ: "Gruppuppgift", provId: 13 })),
    rad(4, papper({ typ: "Diagnos", provId: 14 })),
    rad(5, papper({ typ: "Anteckningar", antId: 15 })),
  ] });
  await page.route("**/api/exams/**", route => {
    hamtat.push(new URL(route.request().url()).pathname);
    return route.fulfill({ status: 200, contentType: "application/pdf",
                           body: Buffer.from("%PDF-1.5 pappret") });
  });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(5);

  await page.getByRole("tab", { name: "Planering" }).click();
  for (const i of [0, 1, 2, 3, 4]) {
    await visa(page, i);
    const nedladdning = page.waitForEvent("download", { timeout: 15_000 });
    await page.locator("#fh-pdf").click();
    await nedladdning;
    await expect(page.locator("#fh-pdf")).toHaveText("Ladda ner PDF");
  }
  expect(hamtat).toEqual(["/api/exams/11/pdf", "/api/exams/12/pdf",
                          "/api/exams/13/pdf", "/api/exams/14/pdf",
                          "/api/exams/15/pdf"]);
});

test("ett papper utan byggd PDF ger serverns besked, inte «Sparad»", async ({ page }) => {
  await fejka(page, { sparade: [rad(1, papper({ typ: "Arbetsblad", provId: 7 }))] });
  await page.route("**/api/exams/7/pdf", route => route.fulfill({
    status: 404, contentType: "application/json",
    body: JSON.stringify({ error: "ingen pdf ännu — godkänn provet" }) }));
  await page.goto("/");
  await hydrerad(page);
  await oppnaForhandsvisning(page);

  await page.locator("#fh-pdf").click();
  await expect(page.locator(".toast").last()).toContainText("ingen pdf ännu");
  await expect(page.locator("#fh-pdf")).toHaveText("Ladda ner PDF");
});

// ── Att slänga utkastet ─────────────────────────────────────────────────────
// Ett övergivet utkast låg framme i planeringens dokumentruta för evigt: det
// plockas upp igen vid varje laddning (v20-designen, som ska vara kvar) och det
// fanns ingen väg alls att kasta det. Rutan hade ångra, gör om och godkänn —
// men ingen papperskorg.

/** Ett utkast med tre versioner, markören på den mittersta. */
const treVersioner = () => [
  papper({ anteckning: "Första utkastet" }),
  papper({ svarighet: 1, anteckning: "Svårare uppgifter" }),
  papper({ kontext: "fysik", anteckning: "Fysikaliskt sammanhang" }),
];

const utkastrad = versioner => ({
  id: 7, status: "utkast", markor: 1, sort: 0, foljd: null,
  versioner, dokument: versioner[1],
});

/** Öppnar planeringen med ett utkast liggande i rutan. */
async function medUtkast(page, versioner) {
  const anrop = await fejka(page, { utkast: utkastrad(versioner) });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await expect(page.locator("#dokument")).toBeVisible();
  return anrop;
}

test("«Släng utkastet» tömmer rutan och tar bort serverraden", async ({ page }) => {
  const anrop = await medUtkast(page, treVersioner());

  await page.locator("#dokslang").click();
  await expect(page.locator("#dokument")).toBeHidden();
  /* Raden går bort MED EN GÅNG. Väntade slängningen på att toasten skulle
     ticka ut vore utkastet bara gömt, och en omladdning hade lagt fram det
     igen — vilket är precis buggen. */
  await expect.poll(() => anrop.some(a => a.metod === "DELETE" && a.vag === "/api/dokument/7")).toBe(true);
});

test("ett slängt utkast är borta efter omladdningen", async ({ page }) => {
  /* Servern har raden kvar i fejken (den svarar med samma utkast igen) — så
     det här mäter det appen själv kan garantera: att DELETE:n gick i väg mot
     RÄTT rad. Sanningsprovet mot en riktig bas görs i den skarpa körningen. */
  const anrop = await medUtkast(page, treVersioner());
  await page.locator("#dokslang").click();
  await expect.poll(() => anrop.filter(a => a.metod === "DELETE").length).toBe(1);
  expect(anrop.filter(a => a.metod === "DELETE").map(a => a.vag)).toEqual(["/api/dokument/7"]);
});

test("Ångra tar tillbaka utkastet med hela sin ångra-historik", async ({ page }) => {
  const anrop = await medUtkast(page, treVersioner());
  await page.locator("#dokslang").click();
  await expect(page.locator("#dokument")).toBeHidden();

  await page.locator(".toast button", { hasText: "Ångra" }).click();
  await expect(page.locator("#dokument")).toBeVisible();
  // Markören stod på ändring 1 av 2 och ska stå där igen — inte på den sista.
  await expect(page.locator("#histnot")).toHaveText("Ändring 1 av 2 · Svårare uppgifter");
  await expect(page.locator("#angra")).toBeEnabled();
  await expect(page.locator("#gorom")).toBeEnabled();

  // Och på servern: en ny utkastrad med den första versionen, de två andra
  // påskrivna i tur och ordning, och markören satt sist.
  await expect.poll(() => anrop.some(a => a.vag.endsWith("/versioner"))).toBe(true);
  const post = anrop.find(a => a.metod === "POST" && a.vag === "/api/dokument");
  expect(post.kropp.status).toBe("utkast");
  expect(post.kropp.dokument.anteckning).toBe("Första utkastet");
  const versionsposter = anrop.filter(a => a.vag.endsWith("/versioner"));
  expect(versionsposter.map(a => a.kropp.dokument.anteckning))
    .toEqual(["Svårare uppgifter", "Fysikaliskt sammanhang"]);
  await expect.poll(() => anrop.some(a => a.metod === "PATCH" && a.kropp && a.kropp.markor === 1)).toBe(true);
});

// ── Godkännandet städar det övergivna utkastet ──────────────────────────────
// Godkännandet bytte status på det AKTUELLA utkastet och lämnade äldre rader för
// samma lektion med status utkast för evigt — och de plockas upp igen vid varje
// laddning. Städningen sker på servern; det appen svarar för är att den ber om
// den, och bara vid godkännande.

test("godkännandet ber servern städa — och säger till när något städades", async ({ page }) => {
  await medUtkast(page, treVersioner());
  /* Egen rutt för utkastraden: den svarar att en föräldralös rad för samma
     lektion gick bort, och den fångar samtidigt anropet — en senare rutt tar
     över helt i Playwright, så fejkans egen loggning når inte hit. */
  const patchar = [];
  await page.route("**/api/dokument/7", route => {
    const r = route.request();
    if (r.method() === "PATCH") patchar.push(r.postDataJSON());
    return route.fulfill({ status: 200, contentType: "application/json",
      body: JSON.stringify({ ...rad(7, papper(), { status: "godkant" }), stadade: 1 }) });
  });

  await page.locator("#godkann").click();
  await expect.poll(() => patchar.some(k => k.status === "godkant" && k.stada === true)).toBe(true);
  await expect(page.locator(".toast").last()).toContainText("Det gamla utkastet lades undan");
});

test("städades inget sägs inget", async ({ page }) => {
  /* Läraren godkände ett papper. Att appen letade efter skräp och inte hittade
     något är inte en nyhet — det är bakgrundsbrus vid varje godkännande. */
  await medUtkast(page, treVersioner());
  await page.route("**/api/dokument/7", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ ...rad(7, papper(), { status: "godkant" }), stadade: 0 }) }));

  await page.locator("#godkann").click();
  await expect(page.locator("#dokument")).toBeHidden();
  await expect(page.locator(".toast", { hasText: "Det gamla utkastet" })).toHaveCount(0);
});

// ── «Börja om» lägger undan utkastet ────────────────────────────────────────
// «Allt rensat» rensade panelen men lämnade pappret liggande i rutan — och
// eftersom utkastet plockas upp igen vid varje laddning var det tillbaka nästa
// gång appen öppnades, efter att läraren uttryckligen bett om ett tomt bord.

test("«Börja om» slänger utkastet och säger det", async ({ page }) => {
  const anrop = await medUtkast(page, treVersioner());

  await page.locator(".omstartknapp").click();
  await expect(page.locator("#dokument")).toBeHidden();
  await expect.poll(() => anrop.some(a => a.metod === "DELETE" && a.vag === "/api/dokument/7")).toBe(true);
  await expect(page.locator(".toast").last()).toContainText("utkastet är slängt");
});

test("«Börja om» utan utkast påstår inte att något slängdes", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();

  await page.locator(".omstartknapp").click();
  await expect(page.locator(".toast").last()).toHaveText("Allt rensat — välj lektionen i veckan igen");
});

// ── BOKENS LÖSNINGSARK FÅR SITT INNEHÅLL ────────────────────────────────────
// Posterna skrivs ur bokens lästa sidor (/api/bocker/{id}/losningar) och
// PATCH:as på pappret. Tre saker gick fel i den vägen, och alla tre var TYSTA:
// överskottet över serverns tak försvann, PATCH:en kunde skriva över en
// omskrivning som skedde under minuten, och «en skrivning pågår»-flaggan
// hamnade i dokumentets JSON och blev därmed permanent.

/* Urvalet som Uppgifter.urval lämnar det INNAN någon lösning är skriven:
   posterna bär nummer och nivå, ingenting mer. `bokId` är satt — utan det är
   boken prototypens och skrivningen sker aldrig. */
const oskrivetBokurval = (nr) => ({
  bok: "Matematik 5000+ 3c", sidor: "244–247", avsnitt: "3.2 Derivata", bokId: 4,
  uppg: nr, bort: [], remsa: `${nr[0]}–${nr[nr.length - 1]}`, bortremsa: "",
  losning: {
    niva: "Nivå 2 och 3", antal: nr.length, uppg: nr,
    remsa: `${nr[0]}–${nr[nr.length - 1]}`,
    poster: nr.map((n, i) => ({ nr: n, niva: 1 + (i % 2) })),
  },
});

const skriven = nr => ({
  nr, niva: 1, skriven: 3, text: `Bestäm $f'(x)$ när $f(x) = ${nr}x$.`,
  svar: `$${nr}$`, vag: [["derivera", "potensregeln"]],
});

/** Fejkar lösningsrutten (bocker → losningar) som en SSE-ström. `grind` (en
    Promise) håller svaret öppet tills testet släpper det. */
async function fejkaLosningar(page, resultat, grind) {
  const anrop = [];
  await page.route("**/api/bocker/*/losningar", async route => {
    anrop.push(route.request().postDataJSON());
    if (grind) await grind;
    return route.fulfill({
      status: 200, contentType: "text/event-stream",
      body: `data: ${JSON.stringify({ type: "done", result: resultat })}\n\n`,
    });
  });
  return anrop;
}

const utkastMed = (versioner, markor = 0) => ({
  id: 7, status: "utkast", markor, sort: 0, foljd: null,
  versioner, dokument: versioner[markor],
});

test("en kvarglömd «skriver»-flagga hindrar inte lösningarna för alltid", async ({ page }) => {
  /* Flaggan satt på `bokuppg.losning` — inne i dokumentets JSON — och en
     omskrivning djupkopierar versionen, så «en skrivning pågår» skrevs till
     servern. Stängdes fliken innan skrivningen hann nolla den plockades
     utkastet upp med flaggan kvar, och anropet hoppades över vid varje
     laddning: arket sa «Lösningarna är inte skrivna än» till tidens ände. */
  const bok = oskrivetBokurval([3101, 3102]);
  bok.losning.skriver = true;               // arvet från en skrivning som dog
  const v = papper({ typ: "Tavla", bokuppg: bok });
  const anrop = await fejkaLosningar(page, {
    poster: [skriven(3101), skriven(3102)],
    olasta_uppg: [], okanda: [], over_taket: [] });
  await fejka(page, { utkast: utkastMed([v]) });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await expect(page.locator("#dokument")).toBeVisible();

  await expect.poll(() => anrop.length).toBe(1);
  expect(anrop[0].uppg).toEqual([3101, 3102]);
});

test("uppgifterna som inte fick plats sägs i klartext", async ({ page }) => {
  /* Servern skriver högst bok_losning.MAX_UPPGIFTER i ett anrop. Överskottet
     kom hem varken som `okanda` eller som `olasta_uppg`, nollades till
     platshållare i klienten och filtrerades bort av arket — läraren valde
     femton uppgifter, fick tolv och fick inget veta. */
  const nr = Array.from({ length: 15 }, (_, i) => 3101 + i);
  const v = papper({ typ: "Tavla", bokuppg: oskrivetBokurval(nr) });
  await fejkaLosningar(page, {
    poster: nr.slice(0, 12).map(skriven),
    olasta_uppg: [], okanda: [], over_taket: nr.slice(12) });
  await fejka(page, { utkast: utkastMed([v]) });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();

  await expect(page.locator(".toast").last())
    .toContainText("3 uppgifter till rymdes inte i skrivningen");
});

test("arket räknar upp de uppgifter det inte har någon lösning till", async ({ page }) => {
  /* Samma tystnad en gång till, men på pappret: posterna utan innehåll
     filtreras bort av renderaren, och utan raden gick det inte att se VILKA
     som fattades. */
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  const nr = [3101, 3102, 3103];
  const dok = papper({ typ: "Tavla", bokuppg: oskrivetBokurval(nr) });
  dok.bokuppg.losning.poster = [skriven(3101), { nr: 3102, niva: 2 },
                                { nr: 3103, niva: 1 }];
  const html = await page.evaluate(
    v => window.BokLosning.blad(v).join(""), dok);
  expect(html).toContain("Utan lösning här");
  expect(html).toContain("uppgift 3102, 3103");
});

test("lösningarna skriver inte över en omskrivning som skedde under tiden", async ({ page }) => {
  /* PATCH:en bär versionen från när skrivningen STARTADE, och
     db.update_dokument skriver den version markören står på. Flyttade läraren
     markören under minuten (en omskrivning, ett gör om) hamnade alltså det
     gamla varvet ovanpå det nya — tyst, för omritningen är en nolloperation i
     samma läge och skärmen såg rätt ut till nästa laddning. */
  const bok = oskrivetBokurval([3101, 3102]);
  const v0 = papper({ typ: "Tavla", bokuppg: bok, anteckning: "Första utkastet" });
  const v1 = papper({ typ: "Tavla", bokuppg: JSON.parse(JSON.stringify(bok)),
                      svarighet: 1, anteckning: "Svårare uppgifter" });
  let slapp;
  const grind = new Promise(r => { slapp = r; });
  const skrivningar = await fejkaLosningar(page, {
    poster: [skriven(3101), skriven(3102)],
    olasta_uppg: [], okanda: [], over_taket: [] }, grind);
  const anrop = await fejka(page, { utkast: utkastMed([v0, v1], 0) });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await expect(page.locator("#dokument")).toBeVisible();
  await expect.poll(() => skrivningar.length).toBe(1);

  // Läraren går fram till det nyare varvet medan lösningarna skrivs.
  await page.locator("#gorom").click();
  await expect(page.locator("#histnot")).toContainText("Ändring 1 av 1");
  slapp();

  await expect(page.locator(".toast").last())
    .toContainText("hade hunnit skrivas om");
  // Och INGET papper skrevs till raden: markören står på ett annat varv.
  expect(anrop.filter(a => a.metod === "PATCH" && a.kropp && a.kropp.dokument))
    .toEqual([]);
});
