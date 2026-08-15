import { expect, test } from "@playwright/test";
import { forbiNivavarningen } from "./larardag.mjs";

/* PROVET OCH ARBETSBLADET PÅ RIKTIGT
 *
 * Arken sattes ur appens egen uppgiftsbank (innehall.js) — samma avsnitt gav
 * samma prov varje gång, och «8 uppgifter» betydde bara att listan kapades.
 * Etapp 0.4 kopplade in provgeneratorn. Fyra saker måste hålla:
 *
 *   1. Arket som ritas bär SERVERNS uppgifter, i frontendens form: nummer,
 *      poäng, nivå, svarsyta och facit.
 *   2. Poängen på en uppgift med deluppgifter är delarnas summa — den ligger
 *      aldrig på båda ställena.
 *   3. Arbetsbladets facitläge styr vad som skrivs ut, precis som förut.
 *   4. Godkännandet bygger PDF:en, och ett misslyckande säger det rakt ut.
 */

const SCHEMA = {
  schema: [{ dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 2c",
             klass: "NA25", sal: "P807" }],
  lov: [], poster: [],
};

/** Prov-JSON som app/exam_spec.py definierar den. */
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
    { del: "C", formaga: "P", typ: "redovisning", poang: [0, 0, 0],
      text: "Derivera funktionerna.",
      losning: "", bedomning: "",
      deluppgifter: [
        { poang: [2, 0, 0], text: "$g(x) = x^3$", losning: "$3x^2$", bedomning: "+2 E" },
        { poang: [0, 3, 0], text: "$h(x) = (2x+1)^4$", losning: "$8(2x+1)^3$", bedomning: "+3 C" },
      ] },
  ],
};

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

async function fejka(page, { generate, approve } = {}) {
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
  await page.route("**/api/exams/**", route => {
    const vag = new URL(route.request().url()).pathname;
    anrop.push({ vag, kropp: route.request().postDataJSON() });
    if (vag.endsWith("/approve")) {
      /* Fälten är rutten's egna: `pdf` och `tex` (routes_exam approve). Mocken
         sa förut `pdf_path` — DB-kolumnens namn — och då fick klientens fel
         fält aldrig något att falla på. Namnen hålls mot riktiga rutten av
         test_routes_exam::test_approve_svaret_bar_falten_plan_js_laser. */
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: approve || strom([{ type: "done",
          result: { id: 9, pdf: "C:/Transkriberingar/prov/derivator.pdf",
                    tex: "C:/Transkriberingar/prov/derivator.tex", errors: [] } }]) });
    }
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: generate || strom([
        { type: "log", msg: "Skriver provet …" },
        { type: "done", result: {
          id: 9, exam: EXAM, typ: "prov", status: "utkast", errors: [], rounds: 1,
          granser: { E: 4, C: 7, A: 9 }, summor: { totalt: 11 } } },
      ]) });
  });
  return anrop;
}

async function skriv(page, typ, moment = "derivator") {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(([t, m]) => {
    window.SattLage(t);
    // Klass och kurs kommer normalt ur lektionen man klickat i veckan.
    const satt = (id, v) => {
      const e = document.querySelector(id);
      e.value = v;
      e.dispatchEvent(new Event("change", { bubbles: true }));
    };
    satt("#p-kurs", "Matematik, nivå 2c");
    satt("#p-klass", "NA25");
    const f = document.querySelector("#moment");
    f.value = m;
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  }, [typ, moment]);
  await page.locator("#skriv").click();
  /* «derivator» är 3c-innehåll och kursen här är 2c — plan.js varnar för det
     innan den anropar, och första klicket blir alltså varningen. Se
     larardag.mjs och nivavarning.spec.mjs; provet som prövas här är rutten, inte
     ämnesplanen. */
  await forbiNivavarningen(page);
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

test("provet på arket är serverns uppgifter, i arkets form", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skriv(page, "Prov");
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  const gen = anrop.find(a => a.vag.endsWith("/generate"));
  expect(gen.kropp.kurs).toBe("Matematik, nivå 2c");
  expect(gen.kropp.typ).toBe("prov");

  // Uppgifterna översatta till arkets form: nivå ur poängvektorn, svarsyta ur
  // uppgiftstypen, poängen summerad över deluppgifterna.
  const arket = await page.locator("#dokument .pruppg").allTextContents();
  expect(arket.length).toBe(3);
  expect(arket[0]).toContain("2 p");
  expect(arket[1]).toContain("4 p");          // 1+2+1
  expect(arket[2]).toContain("5 p");          // 2 + 3 ur deluppgifterna
  // En rutinuppgift svaras på; de andra redovisas på lösblad.
  await expect(page.locator("#dokument .pruppg .prlosblad")).toHaveCount(2);
  // Deluppgifterna står som a) och b).
  await expect(page.locator("#dokument .pruppg .prdel[data-avdelad] li")).toHaveCount(2);
});

test("prototypens uppgifter kommer inte tillbaka vid en ändring", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skriv(page, "Prov");
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  const fore = await page.locator("#dokument .pruppg .prtext").allTextContents();
  expect(fore[0]).toContain("derivatan");
  // nyVersion räknar om uppgifterna vid varje ändring — serverns lista måste
  // överleva den.
  await page.evaluate(() => window.Blad.uppgifter({
    typ: "Prov", provId: 9, moment: "derivator",
    uppgifter: [{ nr: 1, p: 2, t: "Serverns uppgift", niva: "E", ut: "kort" }],
    inst: { antal: 6 } }));
  const efter = await page.evaluate(() => window.Blad.uppgifter({
    typ: "Prov", provId: 9, moment: "derivator",
    uppgifter: [{ nr: 1, p: 2, t: "Serverns uppgift", niva: "E", ut: "kort" }],
    inst: { antal: 6 } }));
  expect(efter).toHaveLength(1);
  expect(efter[0].t).toBe("Serverns uppgift");
});

test("arbetsbladet går på samma rutt men med sin egen typ", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skriv(page, "Arbetsblad", "primitiva funktioner");
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
  expect(anrop.find(a => a.vag.endsWith("/generate")).kropp.typ).toBe("arbetsblad");
});

test("godkännandet bygger PDF:en och säger till", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skriv(page, "Prov");
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  await page.locator("#godkann").click();
  await expect.poll(() => anrop.some(a => a.vag.endsWith("/approve"))).toBe(true);
  /* «PDF» ensamt räcker inte: den misslyckade toasten säger också «PDF». Just
     den luckan lät klienten läsa fel fält ur svaret utan att något sa ifrån —
     kvittot för LYCKAT bygge måste vara det som prövas. */
  await expect(page.locator(".toast").last())
    .toContainText("utskriven som PDF", { timeout: 15_000 });
  // …och sökvägen ska ha nått dokumentet i Sparat, inte bara toasten.
  await expect.poll(() => page.evaluate(
    () => window.Dokument.sparade().map(d => d.pdf).filter(Boolean)[0] || ""))
    .toContain(".pdf");
});

test("en PDF som inte går att bygga sägs rakt ut", async ({ page }) => {
  await fejka(page, {
    approve: strom([{ type: "done", result: { id: 9, pdf: null,
      tex: "C:/Transkriberingar/prov/derivator.tex",
      errors: ["Tectonic: Undefined control sequence"] } }]),
  });
  await page.goto("/");
  await hydrerad(page);
  await skriv(page, "Prov");
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
  await page.locator("#godkann").click();
  await expect(page.locator(".toast").last()).toContainText("tex", { timeout: 15_000 });
});

test("ett prov som inte gick att skriva blir ett besked", async ({ page }) => {
  const jsfel = [];
  await fejka(page, {
    generate: strom([{ type: "done", result: {
      id: null, exam: null, errors: ["balansen gick inte ihop"], rounds: 3 } }]),
  });
  await page.goto("/");
  page.on("pageerror", e => jsfel.push(e.message));
  await hydrerad(page);
  await skriv(page, "Prov");

  const ruta = page.locator("#skrivstatus .fsvar");
  await expect(ruta).toHaveAttribute("data-lage", "stoppad", { timeout: 15_000 });
  await expect(page.locator("#dokument")).toBeHidden();
  expect(jsfel, jsfel.join(" | ")).toEqual([]);
});

test("gruppuppgiften går samma väg och bär sitt upplägg", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => {
    window.SattLage("Gruppuppgift");
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
  await forbiNivavarningen(page);          // «derivator» i 2c — se helpern
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  const gen = anrop.find(a => a.vag.endsWith("/generate"));
  expect(gen.kropp.typ).toBe("gruppuppgift");
  // Upplägget är väljarnas, inte modellens: namnrader, tid och redovisning.
  expect(gen.kropp.grupp.elever).toBeGreaterThanOrEqual(2);
  expect(gen.kropp.grupp.elever).toBeLessThanOrEqual(5);
  expect(gen.kropp.grupp.langd_min).toBeGreaterThan(0);
  expect(["muntligt", "skriftligt", "poster"]).toContain(gen.kropp.grupp.redovisning);
  // Fyra rutor är formen, inte en väljare.
  expect(gen.kropp.antal).toBe(4);
});
