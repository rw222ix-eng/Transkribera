import { expect, test } from "@playwright/test";

/* LÄRARENS EGNA ORD — «Vad var svårt?» och «Vad ska väga tyngst?»
 *
 * Appen kunde bara säga vad klassen hade svårt för om lektionen SPELATS IN:
 * tavelprompten får «Svårighet att följa upp» ur transkriptet, och en lektion
 * utan mikrofon lämnade den raden tom hur mycket läraren än visste. Nu finns
 * rutan, och den står alltid framme — den är inte ett svar på vilka källor man
 * kryssat, den är den enda källa som finns när ingen spelat in.
 *
 * Viktningsrutan fanns redan, sparades på pappret och stod i skrivplanen
 * («Väger källorna») — men skickades aldrig med begäran. Samma tomma löfte som
 * förlagan var.
 *
 * Tre saker måste hålla:
 *   1. Fälten står i steget och svårighetsrutan är synlig utan att något valts.
 *   2. Ifyllda fält går med i payloaden — till ALLA typer, inte bara tavlan.
 *   3. Tomma fält skickar INGENTING. Servern lägger sitt promptblock först när
 *      fältet finns, och en tom nyckel hade öppnat det i onödan.
 */

const SCHEMA = {
  schema: [{ dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 2c",
             klass: "NA25", sal: "P807" }],
  lov: [], poster: [],
};

/* Momentet är derivator och inte något ur en annan kurs: skriver man ett moment
   som ligger i en annan kurs än den valda ställer appen en fråga före
   skrivningen («Tryck igen för att skriva ändå»), och det är nivåvarningens
   test, inte det här. */
const MOMENT = "Derivatans definition";
const SVART = "ändringskvoten satt inte — flera blandade ihop den med tangentens lutning";
const FOKUS = "mest ur provet, lite ur boken";

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

function tavla(rubrik = MOMENT) {
  return { title: rubrik, boards: [{
    name: "teori", width: 900, height: 780, chrome: "aluminium",
    padding: { top: 24, right: 26, bottom: 24, left: 30 },
    sections: [{ kind: "heading", text: rubrik, size: 30 }] }] };
}

const PROV = {
  titel: "Prov", kurs: "Matematik, nivå 2c", hjalpmedel: "",
  uppgifter: [{ del: null, formaga: "P", typ: "rutin", poang: [2, 0, 0],
                text: "Beräkna", losning: "1", bedomning: "+2 E" }],
};

const ANTECKNINGAR = {
  titel: "Stödanteckningar",
  avsnitt: [{ rubrik: "Att ta upp", punkter: ["kvadratkomplettering"] }],
};

/** Fejkar datagrunden och alla tre generatorrutterna. `anrop` samlar kropparna. */
async function fejka(page) {
  const anrop = [];
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
  const generator = (route, resultat) => {
    const vag = new URL(route.request().url()).pathname;
    if (!vag.endsWith("/generate")) return json(route, { ok: true });
    anrop.push({ vag, kropp: route.request().postDataJSON() });
    return route.fulfill({ status: 200, contentType: "text/event-stream",
                           body: strom([{ type: "done", result: resultat }]) });
  };
  await page.route("**/api/planning/**", route => generator(route, {
    id: "abc123def456", board: tavla(), errors: [], rounds: 1 }));
  await page.route("**/api/exams/**", route => generator(route, {
    id: 7, exam: PROV, errors: [], rounds: 1 }));
  await page.route("**/api/anteckningar/**", route => generator(route, {
    id: 8, anteckningar: ANTECKNINGAR, errors: [], rounds: 1 }));
  return anrop;
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

/** Ställer planeringen på `typ` med ett moment och trycker Skriv. */
async function skriv(page, typ, moment = MOMENT) {
  await page.evaluate(([t, m]) => {
    window.SattLage(t);
    const f = document.querySelector("#moment");
    f.value = m;
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  }, [typ, moment]);
  await page.locator("#skriv").click();
}

/** Skriver i ett fält som läraren gör det — så att `input` går och planKoll körs. */
async function fyll(page, id, text) {
  await page.evaluate(([i, t]) => {
    const f = document.querySelector(i);
    f.value = t;
    f.dispatchEvent(new Event("input", { bubbles: true }));
  }, [id, text]);
}

async function planering(page) {
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
}

test("svårighetsrutan står framme utan att någon källa valts", async ({ page }) => {
  await fejka(page);
  await planering(page);
  await page.evaluate(() => { window.SattLage("Tavla"); window.PlanSteg.las(4, false); window.PlanSteg.gaTill(4); });
  // Den är INTE villkorad som viktningsrutan: utan inspelning är den det enda
  // som finns, och då får den inte vara gömd bakom ett källval.
  await expect(page.locator("#svartruta")).toBeVisible();
  await expect(page.locator("#svartruta")).toContainText("Vad var svårt?");
  await expect(page.locator("#fokusruta")).toBeHidden();
});

test("ifylld svårighet och viktning går med i tavlans begäran", async ({ page }) => {
  const anrop = await fejka(page);
  await planering(page);
  await page.evaluate(() => { window.SattLage("Tavla"); window.PlanSteg.las(4, false); window.PlanSteg.gaTill(4); });
  await fyll(page, "#svart", SVART);
  await fyll(page, "#fokus", FOKUS);
  await skriv(page, "Tavla");

  await expect.poll(() => anrop.length).toBe(1);
  expect(anrop[0].kropp.svart).toBe(SVART);
  expect(anrop[0].kropp.fokus).toBe(FOKUS);
});

test("skrivplanen lovar läsningen — men bara när rutan är ifylld", async ({ page }) => {
  await fejka(page);
  await planering(page);
  await page.evaluate(() => { window.SattLage("Tavla"); window.PlanSteg.las(4, false); window.PlanSteg.gaTill(4); });
  await fyll(page, "#svart", SVART);
  await skriv(page, "Tavla");
  await expect(page.locator("#skrivstatus")).toContainText("var svårt", { timeout: 15_000 });
});

test("tomma rutor lägger inga nycklar i begäran", async ({ page }) => {
  const anrop = await fejka(page);
  await planering(page);
  await skriv(page, "Tavla");

  await expect.poll(() => anrop.length).toBe(1);
  // Inte `''`, inte `null` — nyckeln ska inte finnas. Servern öppnar sitt
  // promptblock på ifyllt fält, och prompten för en tom ruta måste vara ord
  // för ord den som gick i väg innan rutorna byggdes (kassetterna).
  expect("svart" in anrop[0].kropp).toBe(false);
  expect("fokus" in anrop[0].kropp).toBe(false);
});

/* Fälten står i steget för det som ska ÖVAS, och de ska nå fram oavsett vilken
   rutt som svarar. Arbetsbladet och gruppuppgiften delar rutt med provet;
   anteckningarna har en egen. */
for (const [typ, vag] of [["Arbetsblad", "/api/exams/generate"],
                          ["Gruppuppgift", "/api/exams/generate"],
                          ["Anteckningar", "/api/anteckningar/generate"]]) {
  test(`${typ} bär också lärarens egna ord`, async ({ page }) => {
    const anrop = await fejka(page);
    await planering(page);
    await page.evaluate(t => { window.SattLage(t); window.PlanSteg.las(4, false); window.PlanSteg.gaTill(4); }, typ);
    await fyll(page, "#svart", SVART);
    await fyll(page, "#fokus", FOKUS);
    // Anteckningarna kan inte skrivas ur ingenting: rutan eller ett möte krävs.
    if (typ === "Anteckningar") await fyll(page, ".typfritext", "tre exempel att gå igenom");
    await skriv(page, typ);

    await expect.poll(() => anrop.length).toBe(1);
    expect(anrop[0].vag).toBe(vag);
    expect(anrop[0].kropp.svart).toBe(SVART);
    expect(anrop[0].kropp.fokus).toBe(FOKUS);
  });
}

/* … men PROVET och DIAGNOSEN mäter, och ett mätinstrument som lutas efter vad
   läraren sett var svårt är inte representativt — åt något håll. Båda rutorna
   går därför ner när typen väljs, och fälten utelämnas ur begäran även om de
   bär text från en tidigare typ i samma session. Det senare är hela poängen:
   en gömd ruta som ändå skickas är den värsta sorten. */
for (const typ of ["Prov", "Diagnos"]) {
  test(`${typ} varken visar eller skickar lärarens egna ord`, async ({ page }) => {
    const anrop = await fejka(page);
    await planering(page);
    // Först en tavla, med båda rutorna ifyllda — texten ligger kvar i fälten.
    await page.evaluate(() => { window.SattLage("Tavla"); window.PlanSteg.las(4, false); window.PlanSteg.gaTill(4); });
    await fyll(page, "#svart", SVART);
    await fyll(page, "#fokus", FOKUS);
    await expect(page.locator("#svartruta")).toBeVisible();

    await page.evaluate(t => window.SattLage(t), typ);
    await expect(page.locator("#svartruta")).toBeHidden();
    await expect(page.locator("#fokusruta")).toBeHidden();

    await skriv(page, typ);
    await expect.poll(() => anrop.length).toBe(1);
    expect(anrop[0].vag).toBe("/api/exams/generate");
    expect("svart" in anrop[0].kropp).toBe(false);
    expect("fokus" in anrop[0].kropp).toBe(false);
  });
}
