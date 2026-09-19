import { expect, test } from "@playwright/test";
import { forbiNivavarningen } from "./larardag.mjs";

/* EFTERKONTROLLEN PÅ SKÄRMEN
 *
 * Servern räknar om de deterministiska fynden vid varje svar (routes_exam
 * .efterkontroll): balansen mot kursens mål, avsnittet mot boken, förebilden
 * mot sidspannet, plåten mot scenen, provtiden mot uppgifterna, språket. Den
 * här sviten prövar att de NÅR läraren, inte att de räknas rätt, det gör
 * tests/test_prov_kontrakt.py.
 *
 * Tre platser, och alla tre behövs (lärarens granskning 2026-09-19):
 *   1. Chatten i canvasen efter ett varv. Prov 85 tappade sin balans i en
 *      riktad omskrivning och ingen sa något.
 *   2. Rutan i pappret. Prov 86:s uppgift 12 hade BÅDE ett avsnitt som inte
 *      finns i boken och en plåt som visar en fyr på en uppgift om ett
 *      tryckeri, synligt på skärmen, om någon sagt vilken uppgift.
 *   3. Förhandsvisningen, sista läsningen före godkännandet.
 */

const SCHEMA = {
  schema: [{ dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 2c",
             klass: "NA25", sal: "P807" }],
  lov: [], poster: [],
};

const EXAM = {
  titel: "Prov · Derivator",
  kurs: "Matematik, nivå 2c", klass: "NA25", datum: "2026-09-03", tid_min: 90,
  hjalpmedel: "Del B utan räknare. Del C med räknare.",
  uppgifter: [
    { del: "B", formaga: "B", typ: "rutin", poang: [2, 0, 0],
      text: "Ange derivatan till $f(x) = 3x^2$.",
      losning: "$f'(x) = 6x$", bedomning: "+2 E för korrekt derivata." },
    { del: "C", formaga: "PL", typ: "problem", poang: [1, 2, 1],
      text: "Bestäm största värdet för $f(x) = -x^2 + 4x$.",
      losning: "$f(2) = 4$", bedomning: "+1 E ansats, +2 C metod, +1 A motivering." },
  ],
};

/* Serverns form, ordagrant: kod, nummer, elementnyckel, lärarens mening. `el`
   är samma serie som blad.js markera() sätter, alltså rutan i pappret. */
const FYND = [
  { kod: "avsnitt", nr: 2, el: "uppg2",
    text: "Uppgift 2 är märkt med avsnitt 2.6, som inte finns i Liber Ma 1c." },
  { kod: "tid", nr: null, el: null,
    text: "Pappret är satt till 90 minuter men uppgifterna räknas till 130." },
];

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

const svar = extra => ({
  id: 9, exam: EXAM, typ: "prov", status: "utkast", errors: [], rounds: 1,
  granser: { E: 4, C: 7, A: 9 }, summor: { totalt: 6 },
  current_version: 1, efterkontroll: FYND, ...extra,
});

async function fejka(page, { efterkontroll = FYND } = {}) {
  const anrop = [];
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
  await page.route("**/api/planning/**", route => json(route, { ok: true }));
  await page.route("**/api/kalenderposter", route => json(route, { ok: true }));
  await page.route("**/api/exams/**", route => {
    const vag = new URL(route.request().url()).pathname;
    anrop.push({ vag, kropp: route.request().postDataJSON() });
    /* GET på ett prov svarar JSON, inte en ström, det är den vägen
       förhandsvisningen läser om fynden för ett papper som legat i högen
       (plan.js speglaExamen). */
    if (route.request().method() === "GET") {
      return json(route, svar({ efterkontroll }));
    }
    if (vag.endsWith("/approve")) {
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "done", result: {
          id: 9, pdf: "C:/Transkriberingar/prov/derivator.pdf",
          tex: "C:/Transkriberingar/prov/derivator.tex", errors: [],
          efterkontroll } }]) });
    }
    if (vag.endsWith("/refine")) {
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "done",
          result: svar({ efterkontroll, andrade: ["uppg2"] }) }]) });
    }
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: svar({ efterkontroll }) }]) });
  });
  return anrop;
}

async function skriv(page) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => {
    window.SattLage("Prov");
    const satt = (id, v) => {
      const e = document.querySelector(id);
      e.value = v;
      e.dispatchEvent(new Event("change", { bubbles: true }));
    };
    satt("#p-kurs", "Matematik, nivå 2c");
    satt("#p-klass", "NA25");
    const f = document.querySelector("#moment");
    f.value = "derivator";
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  });
  await page.locator("#skriv").click();
  await forbiNivavarningen(page);
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

test("fynden ligger på pappret så fort canvasen öppnas", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skriv(page);

  await page.locator("#granska").click();
  await expect(page.locator("#granskaskal")).toBeVisible({ timeout: 15_000 });
  /* Rutan med fyndet är märkt, och bara den. Ett fynd utan `el` (provtiden
     gäller hela pappret) får inte hamna på en godtycklig uppgift. */
  await expect.poll(() => page.evaluate(() => Object.keys(window.Granska.fynd)))
    .toEqual(["uppg2"]);
  const markt = page.locator('#granskaskal .gdok [data-el="uppg2"][data-fynd]');
  await expect(markt.first()).toHaveCount(1);
  await expect(markt.first()).toHaveAttribute("title", /avsnitt 2\.6/);
  // …och en ruta utan fynd bär ingen markering.
  await expect(page.locator('#granskaskal .gdok [data-el="uppg1"][data-fynd]'))
    .toHaveCount(0);
});

test("varvet i canvasen säger vad efterkontrollen hittade", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skriv(page);

  await page.locator("#granska").click();
  await expect(page.locator("#granskaskal")).toBeVisible({ timeout: 15_000 });
  await page.locator("#g-falt").fill("Gör uppgift 2 svårare");
  await page.locator("#g-form button[type='submit']").click();
  /* Serverns egen mening, i tråden. Det var precis den raden som saknades när
     prov 85 tappade sin balans i ett varv och godkändes ändå. */
  await expect(page.locator("#granskaskal .gvarv").first())
    .toContainText("avsnitt 2.6", { timeout: 20_000 });
});

test("förhandsvisningen räknar upp fynden före godkännandet", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skriv(page);

  await page.locator("#godkann").click();
  await expect(page.locator(".toast").last())
    .toContainText("utskriven som PDF", { timeout: 15_000 });

  /* Samma väg som klassvyn går när läraren klickar på pappret på lektionen
     (window.Dokument.visa). Kortet i högen ritas om mellan versioner; det som
     prövas här är förhandsvisningen, inte kortets markup. */
  await page.evaluate(() => window.Dokument.visa(0));
  await expect(page.locator("#forhandsskal")).toBeVisible({ timeout: 15_000 });
  const lista = page.locator("#fh-fynd");
  await expect(lista).toBeVisible();
  await expect(lista).toContainText("2 fynd att läsa innan du godkänner");
  await expect(lista).toContainText("avsnitt 2.6");
  await expect(lista).toContainText("90 minuter");
  /* Fynden BLOCKERAR inte. Knapparna står kvar där de stod, listan är en
     andra läsning, inte en spärr. */
  await expect(page.locator("#fh-pdf")).toBeVisible();
  await expect(page.locator("#fh-fortsatt")).toBeVisible();
});

test("ett papper utan fynd bär ingen lugnande rad", async ({ page }) => {
  await fejka(page, { efterkontroll: [] });
  await page.goto("/");
  await hydrerad(page);
  await skriv(page);

  await page.locator("#granska").click();
  await expect(page.locator("#granskaskal")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("#granskaskal .gdok [data-fynd]")).toHaveCount(0);
  expect(await page.evaluate(() => Object.keys(window.Granska.fynd))).toEqual([]);
});
