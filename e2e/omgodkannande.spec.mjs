import { expect, test } from "@playwright/test";

/* OMGODKÄNNANDET SKRIVER OM PAPPRET, DET LÄGGER INTE ETT TILL
 *
 * Lärarens fynd 2026-09-21: samma papper godkänt en andra gång — förhandsvisning
 * → «Fortsätt ändra» → «Godkänn och sätt som PDF» — låg plötsligt två gånger på
 * lektionskortet, med samma innehåll och bara det ena med sin PDF-sökväg.
 *
 * Godkännandet BYTER status på raden utkastet kom ifrån (utkastGodkann PATCH),
 * och så länge `utkastId` pekar rätt blir det en rad. Hålet satt i väntan:
 * `v.id` skrivs först när godkännandets PATCH-svar landat, och «Fortsätt ändra»
 * läste det direkt. Trycktes knappen inom de tvåhundra millisekunderna var id:t
 * `undefined`, ingen statusändring gick i väg, och NÄSTA godkännande skrev en ny
 * rad medan den gamla låg kvar godkänd med sin PDF.
 *
 * Sviten kör mot testserverns tomma bas, men dokumentlagret fejkas här (samma
 * mönster som dokument.spec.mjs) — det är just ANROPEN som är påståendet.
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

/** Fejkar datagrunden + dokumentlagret. `anrop` samlar allt som skrivs.
 *  `dröj` fördröjer svaret på dokumentrutterna — det är den fördröjningen
 *  kapplöpningen ovan levde i. */
async function fejka(page, { sparade = [], utkast = null, droj = 0 } = {}) {
  const anrop = [];
  const vila = ms => new Promise(r => setTimeout(r, ms));
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/kalenderposter", route => json(route, { ok: true }));
  await page.route("**/api/klassprofil", route => {
    const r = route.request();
    if (r.method() === "PUT") return json(route, r.postDataJSON());
    return json(route, {});
  });
  await page.route("**/api/dokument/**", async route => {
    const r = route.request();
    const vag = new URL(r.url()).pathname;
    const kropp = r.method() === "DELETE" ? null : r.postDataJSON();
    anrop.push({ metod: r.method(), vag, kropp });
    if (r.method() === "DELETE") return json(route, { ok: true });
    if (vag.endsWith("/ordning")) return json(route, { ok: true });
    const id = Number(vag.split("/")[3]) || 99;
    if (droj) await vila(droj);
    return json(route, rad(id, (kropp && kropp.dokument) || papper(),
                           { status: (kropp && kropp.status) || "godkant" }));
  });
  await page.route("**/api/dokument", async route => {
    const r = route.request();
    if (r.method() !== "POST") return json(route, { sparade, utkast });
    const kropp = r.postDataJSON();
    anrop.push({ metod: "POST", vag: "/api/dokument", kropp });
    if (droj) await vila(droj);
    return json(route, rad(100 + anrop.length, kropp.dokument,
                           { status: kropp.status }));
  });
  return anrop;
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

const nyaRader = anrop => anrop.filter(
  a => a.metod === "POST" && a.vag === "/api/dokument");

test("«Fortsätt ändra» → «Godkänn» skriver om raden, den lägger ingen ny",
     async ({ page }) => {
  const anrop = await fejka(page, {
    sparade: [rad(1, papper({ pdf: "C:/blad.pdf" }))] });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => window.Dokument.visa(0));
  await expect(page.locator("#forhandsskal")).toBeVisible();

  await page.locator("#fh-fortsatt").click();
  await expect(page.locator("#dokument")).toBeVisible();
  await page.locator("#godkann").click();

  // Ett papper i högen, och det är RADEN — samma id, samma PDF.
  await expect.poll(() => page.evaluate(
    () => window.Dokument.sparade().length)).toBe(1);
  await expect.poll(() => page.evaluate(
    () => window.Dokument.sparade()[0].id)).toBe(1);
  expect(await page.evaluate(
    () => window.Dokument.sparade()[0].pdf)).toBe("C:/blad.pdf");
  // Ingen ny rad skrevs: statusen bytte på den som fanns.
  expect(nyaRader(anrop)).toHaveLength(0);
  expect(anrop.filter(a => a.metod === "PATCH" && a.vag === "/api/dokument/1")
    .map(a => a.kropp.status)).toEqual(["utkast", "godkant"]);
});

test("«Fortsätt ändra» innan godkännandets svar landat ger ändå EN rad",
     async ({ page }) => {
  /* Kapplöpningen själv: godkännandets PATCH är långsam, och läraren trycker
     «Fortsätt ändra» medan den är i luften. Förr läste knappen ett `v.id` som
     ännu inte fanns — och nästa godkännande skrev en andra rad. */
  const anrop = await fejka(page, {
    droj: 3000,
    utkast: { id: 7, status: "utkast", markor: 0, sort: 0, foljd: null,
              versioner: [papper()], dokument: papper() } });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await expect(page.locator("#dokument")).toBeVisible();

  await page.locator("#godkann").click();
  // MEDAN svaret är i luften: pappret tillbaka på bordet och godkänt igen.
  await page.evaluate(() => window.Dokument.visa(0));
  await expect(page.locator("#forhandsskal")).toBeVisible();
  await page.locator("#fh-fortsatt").click();
  await expect(page.locator("#dokument")).toBeVisible();
  await page.locator("#godkann").click();

  await expect.poll(() => page.evaluate(
    () => window.Dokument.sparade().length)).toBe(1);
  await expect.poll(() => page.evaluate(
    () => window.Dokument.sparade()[0].id)).toBe(7);
  expect(nyaRader(anrop)).toHaveLength(0);
});
