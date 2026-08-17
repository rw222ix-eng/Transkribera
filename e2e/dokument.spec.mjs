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
  await page.evaluate(() => window.Dokument.visa(0));
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
  // Det som skickas är tavlans egen avritning i full storlek — inte en tom duk.
  expect(skickat[0].png.startsWith("data:image/png;base64,")).toBe(true);
  expect(skickat[0].png.length).toBeGreaterThan(10_000);
  await expect(page.locator("#fh-pdf")).toHaveText("Sparad");
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
