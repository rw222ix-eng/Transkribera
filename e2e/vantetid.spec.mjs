import { expect, test } from "@playwright/test";
import { forbiNivavarningen } from "./larardag.mjs";

/* VÄNTETIDEN I GRANSKNINGEN
 *
 * En omskrivning tar minuter, och under dem stod pappret blint: urvalet
 * nollställdes så fort meningen gått i väg, och den enda upplysningen om att
 * något pågick var en rad i panelen längst bort till höger. Fyra saker prövas
 * här — alla fyra är svar på samma iakttagelse.
 *
 * 1. SVEPET. Rutorna varvet gäller lyser så länge det går, och slocknar när
 *    patchen landat.
 * 2. BLINKEN. Det servern FAKTISKT skrev om (`andrade`) blinkar till efter
 *    omritningen — inte det läraren bad om, för det är inte alltid samma sak.
 * 3. ÄNDRADE DELAR. Kortet räknar upp dem med rutornas egna etiketter, och
 *    varje del leder till sitt före/efter.
 * 4. MINI-CHATTEN. En ruta i pappret, en mening om just den — samma kö och
 *    samma prompt som panelchatten, bara en annan plats att skriva på.
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

const prov = (rubrik, ord) => ({
  titel: `Prov · ${rubrik}`,
  kurs: "Matematik, nivå 2c", klass: "NA25", datum: "2026-09-03", tid_min: 60,
  hjalpmedel: "Formelblad och miniräknare.",
  uppgifter: [1, 2, 3, 4].map(n => uppgift(`${ord} nummer ${n}.`)),
});

const FORSTA = prov("Skala", "Byggställningen");
/* Varje omskrivning ger ett SYNLIGT annat papper — utan en verklig skillnad i
   texten kan varken diffen eller kortet prövas. */
const omskrivet = (n) => ({
  ...FORSTA,
  uppgifter: FORSTA.uppgifter.map((u, i) => i === 3
    ? { ...u, text: `Takstolarna, omskrivning ${n}.` } : u),
});

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

/**
 * Fejkar datagrunden och prov-rutterna.
 *
 * `grind` håller ett varv pågående så länge testet vill (svepet syns bara då).
 * `fel` lägger ett skäl i `errors` — det är det «Funkade inte» ska citera.
 */
async function fejka(page, { grind = null, fel = null } = {}) {
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
  await page.route("**/api/exams/**", async route => {
    const vag = new URL(route.request().url()).pathname;
    const kropp = route.request().postDataJSON();
    if (vag.endsWith("/refine")) {
      const n = ++varv;
      anrop.push({ vag, kropp });
      if (grind) await grind(n);
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "done", result: {
          id: 9, exam: omskrivet(n), typ: "prov", status: "utkast",
          errors: fel ? [{ message: fel }] : [],
          rounds: 1, andrade: ["uppg4"], current_version: ++version } }]) });
    }
    anrop.push({ vag, kropp });
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: 9, exam: FORSTA, typ: "prov", status: "utkast", errors: [],
        rounds: 1, granser: { E: 4, C: 7, A: 9 }, summor: { totalt: 12 },
        current_version: ++version } }]) });
  });
  return anrop;
}

async function skrivProv(page) {
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
    f.value = "skala och proportion";
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  });
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

/* Lokatorer med hus — appen har flera `.gvarv` och flera `.rubrik` samtidigt. */
const svep = page => page.locator("#granskaskal .gdok .gshimmer");
const delar = page => page.locator("#g-lista .gandrade .gandradedel");

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

/** Skriver ett prov, öppnar canvasen och lämnar tillbaka anropslistan. */
async function framme(page, val) {
  const anrop = await fejka(page, val);
  await page.goto("/");
  await hydrerad(page);
  await skrivProv(page);
  await oppnaCanvas(page);
  return anrop;
}

// ── SVEPET OCH BLINKEN ──────────────────────────────────────────────────────

test("de valda rutorna sveper medan varvet går — och slocknar efteråt",
  async ({ page }) => {
    const grindar = [];
    await framme(page, { grind: () => new Promise(r => grindar.push(r)) });

    await valj(page, "uppg2", "uppg4");
    await be(page, "Gör dem kortare");

    /* Urvalet är nollställt när meningen gått i väg — det är just därför
       svepet finns: utan det såg pappret orört ut medan varvet gick. */
    await expect(page.locator("#granskaskal .gdok [data-mal]")).toHaveCount(0);
    await expect.poll(() => svep(page).count(), { timeout: 10_000 })
      .toBeGreaterThan(0);
    expect(await page.evaluate(() => [...new Set(Array.from(
      document.querySelectorAll("#granskaskal .gdok .gshimmer"),
      s => s.parentElement.dataset.el))].sort()))
      .toEqual(["uppg2", "uppg4"]);

    await expect.poll(() => grindar.length, { timeout: 10_000 }).toBe(1);
    grindar[0]();
    await expect.poll(() => svep(page).count(), { timeout: 20_000 }).toBe(0);
  });

test("blinken går på serverns egen lista, inte på det läraren bad om",
  async ({ page }) => {
    /* Fejkservern skriver om uppgift 4 vad läraren än pekar på, och säger det
       i `andrade`. Blinkar uppgift 2 vore en lögn om vad som hänt. */
    await framme(page);
    await valj(page, "uppg2");
    await be(page, "Gör den kortare");

    await expect.poll(() => page.evaluate(() => window.Granska.blinkade),
                      { timeout: 25_000 })
      .toEqual(["uppg4"]);
  });

// ── ÄNDRADE DELAR ───────────────────────────────────────────────────────────

test("kortet räknar upp det som faktiskt ändrades, med rutans egen etikett",
  async ({ page }) => {
    await framme(page);
    await valj(page, "uppg2");
    await be(page, "Gör den kortare");

    await expect(delar(page)).toHaveCount(1, { timeout: 25_000 });
    await expect(delar(page)).toHaveText(["Uppgift 4"]);
    await expect(page.locator("#g-lista .gandradehuv")).toHaveText("1 del ändrades");
    /* Etiketten kommer ur samma `data-namn` som målchipsen läser — kortet får
       inte kunna säga «uppg4» där panelen säger «Uppgift 4». */
    expect(await page.evaluate(() =>
      document.querySelector('#granskaskal .gdok [data-el="uppg4"]').dataset.namn))
      .toBe("Uppgift 4");

    /* Ett klick leder till delens före/efter i varvets egen diff. */
    await expect(page.locator('#g-lista .gdiff p[data-el="uppg4"]'))
      .toBeVisible({ timeout: 20_000 });
    await delar(page).first().click();
    await expect(page.locator('#g-lista .gdiff p[data-el="uppg4"]'))
      .toHaveAttribute("data-lyst", "");
  });

test("ändrade ingenting — då står inget kort där heller", async ({ page }) => {
  /* Ett tomt `andrade` är ett SVAR («ingenting på pappret ändrades»), och ett
     kort med noll delar hade sagt emot det. */
  const anrop = [];
  await framme(page);
  await page.unroute("**/api/exams/**");
  await page.route("**/api/exams/**", route => {
    const vag = new URL(route.request().url()).pathname;
    anrop.push(vag);
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: 9, exam: FORSTA, typ: "prov", status: "utkast", errors: [],
        rounds: 1, andrade: [], current_version: 300 } }]) });
  });

  await valj(page, "uppg2");
  await be(page, "Gör den kortare");
  await expect(page.locator("#g-antal")).toHaveText("1 ändring", { timeout: 20_000 });
  await expect(page.locator("#g-lista .gvarv .fsvar[data-lage='klar']"))
    .toBeVisible({ timeout: 25_000 });
  await expect(page.locator("#g-lista .gandrade")).toHaveCount(0);
});

// ── «FUNKADE INTE» ──────────────────────────────────────────────────────────

test("Funkade inte köar ett omtag med samma mål, samma önskan och skälet",
  async ({ page }) => {
    const anrop = await framme(page, { fel: "Varje uppgift måste ge minst en poäng." });

    await valj(page, "uppg4");
    await be(page, "Ta bort poängen från uppgift 4");
    await expect.poll(() => refines(anrop).length, { timeout: 25_000 }).toBe(1);

    const knapp = page.locator("#g-lista .gvarv .gomtag").first();
    await expect(knapp).toBeVisible({ timeout: 25_000 });
    await knapp.click();
    await expect(knapp).toBeDisabled();

    await expect.poll(() => refines(anrop).length, { timeout: 25_000 }).toBe(2);
    const omtag = refines(anrop)[1].kropp;
    // Lärarens ursprungliga mening står kvar oförändrad …
    expect(omtag.message).toContain("Ta bort poängen från uppgift 4");
    // … skälet servern gav följer med, i klartext …
    expect(omtag.message).toContain("varje uppgift måste ge minst en poäng.");
    // … och rutan hon pekade på är fortfarande målet.
    expect(omtag.mal.el).toBe("uppg4");
    expect(omtag.nummer).toBe(4);
  });

test("utan skäl från servern säger omtaget att det inte blev som önskat",
  async ({ page }) => {
    const anrop = await framme(page);
    await be(page, "Byt sammanhang");
    await expect.poll(() => refines(anrop).length, { timeout: 25_000 }).toBe(1);
    await page.locator("#g-lista .gvarv .gomtag").first().click();
    await expect.poll(() => refines(anrop).length, { timeout: 25_000 }).toBe(2);
    expect(refines(anrop)[1].kropp.message)
      .toContain("resultatet blev inte som önskat.");
  });

// ── MINI-CHATTEN ────────────────────────────────────────────────────────────

test("en vald ruta ger en knapp vid rutan — meningen går samma väg som panelens",
  async ({ page }) => {
    const anrop = await framme(page);

    await valj(page, "uppg2");
    await expect(page.locator("#g-mini")).toBeVisible();
    /* Knappen ligger vid RUTAN, inte i panelen: den ska överlappa dukens yta
       och stå ovanför den ruta läraren pekat på. */
    const nara = await page.evaluate(() => {
      const m = document.querySelector("#g-mini").getBoundingClientRect();
      const d = document.querySelector("#g-duk").getBoundingClientRect();
      return m.left >= d.left && m.right <= d.right
          && m.top >= d.top && m.bottom <= d.bottom;
    });
    expect(nara).toBe(true);

    await page.locator("#g-miniknapp").click();
    await expect(page.locator("#g-miniform")).toBeVisible();
    await expect(page.locator("#g-miniknapp")).toBeHidden();

    await page.locator("#g-minifalt").fill("Skriv om den här rutan");
    await page.locator("#g-minifalt").press("Enter");

    await expect.poll(() => refines(anrop).length, { timeout: 25_000 }).toBe(1);
    const kropp = refines(anrop)[0].kropp;
    expect(kropp.message).toBe("Skriv om den här rutan");
    expect(kropp.mal.el).toBe("uppg2");
    // Meningen står i TRÅDEN, som all annan chatt — inte i en egen ström.
    await expect(page.locator("#g-lista .gvarv .gfraga"))
      .toHaveText(["Skriv om den här rutan"]);
    // Urvalet är nollställt, alltså är knappen borta igen.
    await expect(page.locator("#g-mini")).toBeHidden();
  });

test("mini-chatten köar när ett varv redan går", async ({ page }) => {
  const grindar = [];
  const anrop = await framme(page, { grind: () => new Promise(r => grindar.push(r)) });

  await be(page, "Först detta");
  await expect(page.locator("#g-form button[type=submit]"))
    .toHaveText("Lägg i kö", { timeout: 10_000 });

  await valj(page, "uppg3");
  await page.locator("#g-miniknapp").click();
  await page.locator("#g-minifalt").fill("Och den här");
  await page.locator("#g-minifalt").press("Enter");

  await expect(page.locator("#g-lista .gvarv[data-i-ko]")).toHaveCount(1);
  expect(await page.evaluate(() => window.Granska.koad)).toEqual(["Och den här"]);

  await expect.poll(() => grindar.length, { timeout: 10_000 }).toBe(1);
  grindar[0]();
  await expect.poll(() => grindar.length, { timeout: 25_000 }).toBe(2);
  grindar[1]();
  await expect.poll(() => refines(anrop).map(a => a.kropp.message),
                    { timeout: 25_000 })
    .toEqual(["Först detta", "Och den här"]);
});

test("Esc fäller ihop fältet och stänger inte canvasen", async ({ page }) => {
  await framme(page);
  await valj(page, "uppg2");
  await page.locator("#g-miniknapp").click();
  await page.locator("#g-minifalt").fill("Halvskrivet");
  await page.locator("#g-minifalt").press("Escape");

  await expect(page.locator("#g-miniform")).toBeHidden();
  await expect(page.locator("#g-miniknapp")).toBeVisible();
  await expect(page.locator("#granskaskal")).toBeVisible();
  expect(await page.evaluate(() => window.Granska.oppen)).toBe(true);
});

test("två valda rutor ger ingen knapp — «den här» om två betyder ingenting",
  async ({ page }) => {
    await framme(page);
    await valj(page, "uppg2");
    await expect(page.locator("#g-mini")).toBeVisible();
    await valj(page, "uppg4");
    await expect(page.locator("#g-mini")).toBeHidden();
    // Tillbaka till en ruta, och knappen är där igen.
    await valj(page, "uppg4");
    await expect(page.locator("#g-mini")).toBeVisible();
    // Väljläget av: rutan är inte längre vald på ett sätt som går att skriva om.
    await page.locator("#g-valj").click();
    await expect(page.locator("#g-mini")).toBeHidden();
  });
