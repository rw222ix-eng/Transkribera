import { expect, test } from "@playwright/test";

/* HELA KEDJAN GENOM GRÄNSSNITTET
 *
 * Prov → rättning elev för elev → CI-profil → riktat arbetsblad. Varje led
 * har sin egen svit; den här prövar SKARVARNA, och den gör det genom att gå
 * lärarens väg: skriv provet, godkänn det, öppna elevmodalen på det, rätta,
 * läs profilen, och skriv sedan bladet till den som föll.
 *
 * Kedjan kördes också skarpt mot riktiga servern och riktiga Claude Code
 * 2026-08-14. Det här är samma väg med servern fejkad, så att den går att köra
 * om på tio sekunder.
 */

const SCHEMA = {
  schema: [{ dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 1c",
             klass: "9Z", sal: "P807" }],
  lov: [], poster: [],
};

const ELEVER = [{ id: 21, namn: "Alva Nyström", sort: 0, aktiv: true }];

/* Provet: tre uppgifter, tre innehållspunkter, platt och E-tung. */
const PROV = {
  titel: "Prov · Matematik 1c",
  kurs: "Matematik, nivå 1c", klass: "9Z", datum: "2026-09-07", tid_min: 60,
  hjalpmedel: "Formelblad och digitala verktyg",
  uppgifter: [
    { del: null, formaga: "P", typ: "rutin", poang: [2, 0, 0],
      text: "Lös $3x - 7 = 8$.", losning: "$x = 5$", bedomning: "+2 E",
      innehall: ["G25-M1C-ALG-5"] },
    { del: null, formaga: "B", typ: "rutin", poang: [2, 0, 0],
      text: "Förenkla $2x + 3x$.", losning: "$5x$", bedomning: "+2 E",
      innehall: ["G25-M1C-ALG-1"] },
    { del: null, formaga: "R", typ: "resonemang", poang: [0, 2, 0],
      text: "Avgör om $2^x > x^2$ för alla $x$.", losning: "Nej.",
      bedomning: "+2 C", innehall: ["G25-M1C-ALG-7"] },
  ],
};

/* Profilen servern räknar ur rättningen ovan: hon föll på ekvationerna. */
const PROFIL = {
  elev_id: 21, dokument: 1, utan_ci: 0, matt: true,
  punkter: [
    { kod: "G25-M1C-ALG-5", kort: "Linjära ekvationer", andel: 0,
      styrka: "svag", tagna: 0, max: 2, dokument: 1, niva: {} },
    { kod: "G25-M1C-ALG-7", kort: "Exponentialfunktioner", andel: 0.5,
      styrka: "ok", tagna: 1, max: 2, dokument: 1, niva: {} },
    { kod: "G25-M1C-ALG-1", kort: "Formler och uttryck", andel: 1,
      styrka: "stark", tagna: 2, max: 2, dokument: 1, niva: {} },
  ],
};

const BLAD = {
  titel: "Övningsblad · linjära ekvationer",
  kurs: "Matematik, nivå 1c", klass: "9Z", elev: "Alva Nyström",
  datum: "2026-09-07", hjalpmedel: "Formelblad",
  uppgifter: [
    { del: null, formaga: "P", typ: "rutin", poang: [2, 0, 0],
      text: "Lös $5x + 3 = 23$.", losning: "$x = 4$", bedomning: "+2 E",
      innehall: ["G25-M1C-ALG-5"] },
    { del: null, formaga: "B", typ: "rutin", poang: [3, 0, 0],
      text: "Vad betyder det att $x = 4$ löser ekvationen?",
      losning: "Att båda leden blir lika.", bedomning: "+3 E",
      innehall: ["G25-M1C-ALG-5"] },
  ],
};

const RADER = PROV.uppgifter.map((u, i) => ({
  nyckel: String(i + 1), kod: String(i + 1), nr: String(i + 1),
  text: u.text, p: u.poang[0] + u.poang[1], peca: u.poang,
  formaga: "Räkning i standardfall", ci: u.innehall,
}));
const GRANSER = { total: 6, E: { minst: 2 }, C: { minst: 3, varav_ca: 1 },
                  A: { minst: 4, varav_a: 1 } };
const ELEVSVAR = {
  group_id: 1, klass: "9Z", rader: RADER, granser: GRANSER, elever: ELEVER,
  resultat: {}, summor: {}, betyg: {}, feedback: {},
};

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

async function fejka(page) {
  const anrop = [];
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  /* GET listar högen, POST lägger ett papper i den — och svaret måste bära ett
     id, annars vet klienten inte vilket dokument rättningen hör till. */
  await page.route("**/api/dokument", route => json(
    route, route.request().method() === "POST"
      ? { id: 5 } : { sparade: [], utkast: null }));
  await page.route("**/api/groups", route => json(route, [{ id: 1, namn: "9Z" }]));
  await page.route("**/api/groups/*/elever", route => json(route, { elever: ELEVER }));
  await page.route("**/ci-profil*", route => json(route, PROFIL));
  await page.route("**/api/exams/**", route => {
    const vag = new URL(route.request().url()).pathname;
    const kropp = route.request().postDataJSON();
    anrop.push({ vag, kropp });
    if (vag.endsWith("/approve")) {
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "done", result: { id: 3, pdf: "d.pdf", tex: "d.tex", errors: [] } }]) });
    }
    const prov = kropp && kropp.typ === "prov";
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: prov ? 3 : 4, exam: prov ? PROV : BLAD,
        typ: prov ? "prov" : "arbetsblad", status: "utkast",
        errors: [], rounds: 1, tid: prov ? 55 : 20,
        summor: { total: 6, e: 4, c: 2, a: 0 } } }]) });
  });
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 5 }));
  /* Elevresultatet registreras SIST: Playwright provar de senast tillagda
     mönstren först, och den generella dokumentvägen ovan matchar annars den
     här med. */
  await page.route("**/api/dokument/*/elevresultat", route => {
    const r = route.request();
    anrop.push({ vag: "elevresultat", metod: r.method(),
                 kropp: r.method() === "PUT" ? r.postDataJSON() : null });
    if (r.method() === "PUT") {
      return json(route, { ...ELEVSVAR, resultat: r.postDataJSON().resultat,
        rattat: { elever: 1, varden: { 1: 0, 2: 2, 3: 1 }, andel: 0.5, svaga: [] } });
    }
    return json(route, ELEVSVAR);
  });
  return anrop;
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

async function planera(page, typ, moment) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(([t, m]) => {
    window.SattLage(t);
    const satt = (id, v) => {
      const e = document.querySelector(id);
      e.value = v;
      e.dispatchEvent(new Event("change", { bubbles: true }));
    };
    satt("#p-kurs", "Matematik, nivå 1c");
    satt("#p-klass", "9Z");
    const f = document.querySelector("#moment");
    f.value = m;
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  }, [typ, moment]);
}

test("prov → rättning → CI-profil → riktat blad", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);

  // ── 1. Provet: hela kursens innehåll, en lektion ─────────────────────
  await planera(page, "Prov", "hela kursen");
  /* Läraren kryssar innehållet själv: kedjan behöver koderna på uppgifterna
     för att profilen ska ha något att räkna på. */
  await page.evaluate(() => window.Gy.punkter(window.GyVal.niva())
    .forEach(p => { if (!window.GyVal.har(p.kort)) window.GyVal.vaxla(p.kort); }));
  await page.locator("#skriv").click();
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
  const gen = anrop.find(a => a.vag && a.vag.endsWith("/generate"));
  expect(gen.kropp.typ).toBe("prov");
  expect(gen.kropp.punkter).toHaveLength(21);

  await page.locator("#godkann").click();
  /* Två papper, inte ett: provets bedömningsanvisning sparas som ett eget
     dokument (plan.js losningsblad). Kedjan går vidare på provet, som ligger
     först. */
  await expect.poll(() => page.evaluate(
    () => window.Dokument.sparade().length), { timeout: 15_000 }).toBe(2);

  // ── 2. Rättningen elev för elev ──────────────────────────────────────
  await page.evaluate(() => window.Elever.oppna(window.Dokument.sparade()[0]));
  await expect(page.locator("#elevvy")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("#elevnamn")).toHaveText("Alva Nyström");

  /* Noll på ekvationerna, full pott på uttrycken, hälften på resonemanget —
     samma utfall som profilen nedan säger att servern räknade fram. */
  await page.locator('.elevrad[data-nyckel="1"] .elevknapp[data-v="0"]').click();
  await page.locator('.elevrad[data-nyckel="2"] .elevknapp[data-v="2"]').click();
  await page.locator('.elevrad[data-nyckel="3"] .elevknapp[data-v="1"]').click();
  await page.locator("#elevspara").click();
  await expect.poll(() => anrop.some(a => a.vag === "elevresultat" && a.metod === "PUT"),
                    { timeout: 15_000 }).toBe(true);
  const put = anrop.find(a => a.vag === "elevresultat" && a.metod === "PUT");
  expect(Object.keys(put.kropp.resultat)).toEqual(["21"]);

  // ── 3. CI-profilen säger vad som brister ─────────────────────────────
  const rader = page.locator("#elevcilista .elevcirad");
  await expect(rader).toHaveCount(3, { timeout: 15_000 });
  await expect(rader.first().locator(".elevcinamn")).toHaveText("Linjära ekvationer");
  await expect(rader.first()).toHaveAttribute("data-styrka", "svag");
  await page.locator("#elevstang").click();

  // ── 4. Riktat blad på just den punkten ───────────────────────────────
  await planera(page, "Arbetsblad", "linjära ekvationer");
  await page.locator('.typrad[data-id="mottagare"] .tkvalj').click();
  await page.locator('.typmottagare .lrad-val', { hasText: "Alva Nyström" }).click();
  await page.keyboard.press("Escape");
  /* Punkten hon föll på kryssas för av sig själv — det är hela poängen med att
     profilen finns. */
  await expect.poll(() => page.evaluate(() => window.GyVal.valda()),
                    { timeout: 15_000 }).toEqual(["Linjära ekvationer"]);

  // Bara elevens blad den här gången.
  await page.locator('.typrad[data-id="mottagare"] .lchip').first().click();
  await page.locator("#skriv").click();
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  const blad = anrop.filter(a => a.vag && a.vag.endsWith("/generate")).at(-1);
  expect(blad.kropp.typ).toBe("arbetsblad");
  expect(blad.kropp.elev_id).toBe(21);
  expect(blad.kropp.syfte).toBe("stotta");
  expect(blad.kropp.punkter).toEqual(["G25-M1C-ALG-5"]);
  await expect(page.locator("#arkskal .gumottagare").first())
    .toHaveText("Alva Nyström");
});
