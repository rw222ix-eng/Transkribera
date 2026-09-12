import { expect, test } from "@playwright/test";
import { forbiNivavarningen } from "./larardag.mjs";

/* HÄRLEDDA RADER I CANVASEN
 *
 * Spåret 2026-09-06: tre varv gav `andrade=[]` utan ett enda fel. Läraren
 * pekade på rader som APPEN räknar fram och som inte står i dokumentets JSON.
 *
 *   Arbetsblad 42, 17:23: «Fixa så det blir rätt antal uppgifter. Det är inte
 *   sex. Det är tolv», mål «Metaraden». Metaraden byggs i webbläsaren
 *   (blad.js arkhuvud) ur antalet uppgifter. Servern hade ingenting att skriva
 *   om, och varvet kostade en väntan och svarade ingenting.
 *
 *   Gruppuppgift 37, 18:12 och 18:16: «På sida två och tre … fortsättning …
 *   tre av tre. Allt det ska bort», mål tomt. Sidhuvudena sätts av
 *   pagineringen. Andra försöket skrev om uppgift 2, 3 och 4 i stället.
 *
 * Kravet här är därför dubbelt: rutan ska gå att PEKA PÅ (felet hon ser är
 * verkligt), men meningen om den ska bli ett SVAR och inte ett anrop. Och när
 * ett härlett mål är ett av flera ska resten gå i väg som vanligt, med
 * oförändrad kropp: kassetterna i tests/ är inspelade mot den.
 */

const SCHEMA = {
  schema: [{ dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 2c",
             klass: "NA25", sal: "P807" }],
  lov: [], poster: [],
};

const uppgift = (text) => ({
  del: "C", formaga: "PL", typ: "problem", poang: [2, 1, 0],
  text, losning: `Lösningen till: ${text}`, bedomning: "+2 E, +1 C.",
});

const papper = (antal, ord = "Byggställningen") => ({
  titel: "Räkna med skala",
  kurs: "Matematik, nivå 2c", klass: "NA25", datum: "2026-09-03", tid_min: 60,
  hjalpmedel: "Formelblad och miniräknare.",
  uppgifter: Array.from({ length: antal }, (_, n) => uppgift(`${ord} nummer ${n + 1}.`)),
});

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

/** Fejkar datagrunden och exam-rutterna. Varje refine räknas. */
async function fejka(page, { antal = 4, typ = "arbetsblad" } = {}) {
  const anrop = [];
  let version = 100, varv = 0;
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => route.request().method() === "POST"
    ? json(route, { id: 1, status: "utkast", markor: 0, versioner: [] })
    : json(route, { sparade: [], utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
  await page.route("**/api/planning/**", route => json(route, { ok: true }));
  await page.route("**/api/exams/**", route => {
    const vag = new URL(route.request().url()).pathname;
    anrop.push({ vag, kropp: route.request().postDataJSON() });
    if (vag.endsWith("/refine")) {
      const n = ++varv;
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "done", result: {
          id: 9, exam: papper(antal, `Omskriven ${n}`), typ, status: "utkast",
          errors: [], rounds: 1, andrade: ["uppg2"],
          current_version: ++version } }]) });
    }
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: 9, exam: papper(antal), typ, status: "utkast", errors: [],
        rounds: 1, granser: { E: 4, C: 7, A: 9 }, summor: { totalt: 12 },
        current_version: ++version } }]) });
  });
  return anrop;
}

/** Skriver pappret genom planeringen, samma väg läraren tar. */
async function skrivPapper(page, lage) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(l => {
    window.SattLage(l);
    const satt = (id, v) => {
      const e = document.querySelector(id);
      e.value = v;
      e.dispatchEvent(new Event("change", { bubbles: true }));
    };
    satt("#p-kurs", "Matematik, nivå 2c");
    satt("#p-klass", "NA25");
    const f = document.querySelector("#moment");
    f.value = "skala och proportion";
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  }, lage);
  await page.locator("#skriv").click();
  await forbiNivavarningen(page);
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
}

async function oppnaCanvas(page) {
  await page.locator("#granska").click();
  await expect(page.locator("#g-falt")).toBeVisible({ timeout: 10_000 });
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

const refines = anrop => anrop.filter(a => a.vag.endsWith("/refine"));

/* Lokatorer med hus: appen har flera `.gvarv` och flera `.rubrik` samtidigt,
   och allt här hänger i #granskaskal eller i panelens egen lista. */
const chips = page => page.locator("#g-mal .gmalchip");
const svar = page => page.locator("#g-lista .gvarv[data-harledd]");

/** Slår på väljläget och klickar rutorna med de givna id:na. */
async function valj(page, ...idn) {
  if (await page.locator("#g-valj").getAttribute("aria-pressed") !== "true") {
    await page.locator("#g-valj").click();
  }
  for (const id of idn) {
    await page.locator(`#granskaskal .gdok [data-el="${id}"]`).first().click();
  }
}

async function be(page, text) {
  await page.locator("#g-falt").fill(text);
  await page.locator("#g-form").evaluate(f => f.requestSubmit());
}

// ── ETT HÄRLETT MÅL ENSAMT: SVAR, INTE VARV ─────────────────────────────────

test("metaraden svarar direkt och skickar inget refine", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skrivPapper(page, "Arbetsblad");
  await oppnaCanvas(page);

  /* Raden finns, den går att peka på, och den är MÄRKT. Chipet säger det
     redan innan meningen skickas. */
  await valj(page, "meta");
  await expect(chips(page)).toHaveCount(1);
  await expect(chips(page).locator(".gmaltext")).toHaveText(["Metaraden"]);
  await expect(chips(page).first()).toHaveAttribute("data-harledd", "");

  await be(page, "Fixa så det blir rätt antal uppgifter. Det är inte sex. Det är tolv.");

  // Beskedet står i tråden, på samma plats som modellens svar hade stått …
  await expect(svar(page)).toHaveCount(1, { timeout: 10_000 });
  await expect(svar(page)).toContainText("räknas fram i appen ur antalet uppgifter");
  await expect(svar(page).locator(".gvarvel")).toHaveText("Metaraden");
  // … och ingenting gick till servern.
  expect(refines(anrop)).toEqual([]);
  // Raden räknas inte som en ändring: ingen ändring skedde.
  await expect(page.locator("#g-antal")).not.toHaveText(/1 ändring/);
  /* Meningen är inte förbrukad: inget varv tog den. Ett klick på raden lägger
     tillbaka den i fältet, redo att riktas mot en ruta som går att skriva om. */
  await svar(page).click();
  await expect(page.locator("#g-falt")).toHaveValue(/Det är tolv/);
  // … men urvalet följer inte med: den härledda rutan är inte vald igen.
  await expect(chips(page)).toHaveCount(0);
});

test("anvisningen på provets försättsblad svarar likadant", async ({ page }) => {
  const anrop = await fejka(page, { typ: "prov" });
  await page.goto("/");
  await hydrerad(page);
  await skrivPapper(page, "Prov");
  await oppnaCanvas(page);

  await valj(page, "not");
  await expect(chips(page).locator(".gmaltext")).toHaveText(["Anvisningen"]);
  await be(page, "Ta bort meningen om lösblad.");

  await expect(svar(page)).toHaveCount(1, { timeout: 10_000 });
  await expect(svar(page)).toContainText("provets poäng och delar");
  expect(refines(anrop)).toEqual([]);
});

// ── ETT HÄRLETT MÅL BLAND FLERA: SLÄPPS, RESTEN GÅR ─────────────────────────

test("med flera mål släpps det härledda och resten skrivs om", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skrivPapper(page, "Arbetsblad");
  await oppnaCanvas(page);

  await valj(page, "meta", "uppg2");
  await expect(chips(page)).toHaveCount(2);
  await be(page, "Rätt antal uppgifter, och gör nummer två kortare.");

  await expect.poll(() => refines(anrop).length, { timeout: 20_000 }).toBe(1);
  const kropp = refines(anrop)[0].kropp;
  /* KASSETTREGELN: ett riktigt mål kvar betyder EXAKT dagens kropp. Släpptes
     det härledda målet får den inte lämna ett spår i `malen` eller i
     nummerlåsningen: kassetterna i tests/ är inspelade byte för byte. */
  expect(kropp.mal.el).toBe("uppg2");
  expect(kropp.malen).toBeUndefined();
  expect(kropp.nummer).toBe(2);
  expect("harledd" in kropp.mal).toBe(false);

  // Och läraren får veta vad som inte gick med, i samma bubbla som svaret.
  const rad = page.locator("#g-lista .gvarv").last();
  await expect(rad).toContainText("Det som inte gick med:", { timeout: 20_000 });
  await expect(rad).toContainText("Metaraden räknas fram");
});

// ── PAGINERINGENS EGNA RADER ────────────────────────────────────────────────

test("fortsättningsraden går att peka på, men blir ett svar", async ({ page }) => {
  /* Sexton uppgifter ryms inte på ett blad: delaArk föder ett
     fortsättningsblad, och det bär raden läraren pekade på (gruppuppgift 37). */
  const anrop = await fejka(page, { antal: 16 });
  await page.goto("/");
  await hydrerad(page);
  await skrivPapper(page, "Arbetsblad");
  await oppnaCanvas(page);

  const rad = page.locator('#granskaskal .gdok [data-el="forts"]');
  await expect(rad.first()).toBeVisible({ timeout: 15_000 });
  await expect(rad.first()).toHaveAttribute("data-namn", "Fortsättningsraden");

  await valj(page, "forts");
  await be(page, "Ta bort fortsättning tre av tre längst upp.");

  await expect(svar(page)).toHaveCount(1, { timeout: 10_000 });
  await expect(svar(page)).toContainText("sätts av pagineringen");
  expect(refines(anrop)).toEqual([]);
});
