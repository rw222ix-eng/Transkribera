import { expect, test } from "@playwright/test";
import { forbiNivavarningen } from "./larardag.mjs";

/* NÄR TVÅ SAKER SKER SAMTIDIGT
 *
 * Sviten har prövat en gest i taget: skriv, ändra, godkänn — i tur och ordning,
 * med svar som kommer på en gång. Läraren arbetar inte så. Hon skickar en
 * mening till, byter ark medan modellen skriver, stänger canvasen och skriver
 * ett nytt papper, trycker «Börja om» av misstag.
 *
 * Varje test här är ett sådant ögonblick — och alla utom ett kommer ur en
 * granskning som läste koden och inte gränssnittet.
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
const ANDRA = prov("Andragradare", "Parabeln");
const OMSKRIVET = {
  ...FORSTA,
  uppgifter: FORSTA.uppgifter.map((u, i) => i === 3
    ? { ...u, text: "Takstolarna sitter med 1,2 m mellanrum." } : u),
};

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

/**
 * Fejkar datagrunden och prov-rutterna.
 *
 * `grind` är ett löfte omskrivningen väntar på innan den svarar — det är så ett
 * varv hålls «pågående» medan testet gör något annat. `approveUtanDone` låter
 * godkännandets ström ta slut mitt i, som en server som dör.
 */
async function fejka(page, { grind = null, approveUtanDone = false } = {}) {
  const anrop = [];
  let version = 100, skrivningar = 0;
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => {
    if (route.request().method() !== "POST") {
      return json(route, { sparade: [], utkast: null });
    }
    anrop.push({ vag: "/api/dokument", metod: "POST" });
    return json(route, { id: 1, status: "utkast", markor: 0, versioner: [] });
  });
  await page.route("**/api/dokument/**", route => {
    anrop.push({ vag: new URL(route.request().url()).pathname,
                 metod: route.request().method() });
    return json(route, { ok: true, id: 1 });
  });
  await page.route("**/api/planning/**", route => json(route, { ok: true }));
  await page.route("**/api/exams/**", async route => {
    const vag = new URL(route.request().url()).pathname;
    anrop.push({ vag, metod: route.request().method(),
                 kropp: route.request().postDataJSON() });
    if (vag.endsWith("/approve")) {
      return route.fulfill({
        status: 200, contentType: "text/event-stream",
        body: approveUtanDone
          ? strom([{ type: "log", msg: "Kompilerar PDF …" }])
          : strom([{ type: "done", result: {
              id: 9, pdf: "C:/Transkriberingar/prov/skala.pdf",
              tex: "C:/Transkriberingar/prov/skala.tex", errors: [] } }]),
      });
    }
    if (vag.endsWith("/refine")) {
      if (grind) await grind;
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "done", result: {
          id: 9, exam: OMSKRIVET, typ: "prov", status: "utkast", errors: [],
          rounds: 1, andrade: ["uppg4"], current_version: ++version } }]) });
    }
    /* Varje skrivning är ett EGET papper på servern — det är hela poängen med
       test två nedan: svaret från det förra får inte landa på det nya. */
    skrivningar += 1;
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: 8 + skrivningar, exam: skrivningar === 1 ? FORSTA : ANDRA,
        typ: "prov", status: "utkast", errors: [], rounds: 1,
        granser: { E: 4, C: 7, A: 9 }, summor: { totalt: 12 },
        current_version: ++version } }]) });
  });
  return anrop;
}

async function forbered(page) {
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
}

async function skrivProv(page) {
  await forbered(page);
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

async function be(page, text) {
  await page.locator("#g-falt").fill(text);
  await page.locator("#g-form").evaluate(f => f.requestSubmit());
}

test("ett varv i taget: fältet står stilla medan pappret skrivs om", async ({ page }) => {
  /* Två meningar efter varandra blev två omskrivningar av samma text. Båda
     läste dokumentet innan någon sparat, den som kom sist vann, och den förstas
     ändring fanns sedan varken på pappret eller i ångra-historiken. */
  let slapp;
  const grind = new Promise(r => { slapp = r; });
  const anrop = await fejka(page, { grind });
  await page.goto("/");
  await hydrerad(page);
  await skrivProv(page);
  await oppnaCanvas(page);

  await be(page, "Gör uppgift 4 kortare");
  await expect(page.locator("#g-falt")).toBeDisabled({ timeout: 10_000 });
  await expect(page.locator("#g-form button[type=submit]")).toHaveText("Skriver …");

  // Andra meningen går inte i väg — och inte som ett tyst tapp: rutan är låst.
  await page.locator("#g-form").evaluate(f => f.requestSubmit());
  await page.waitForTimeout(300);
  expect(refines(anrop)).toHaveLength(1);

  slapp();
  await expect(page.locator("#g-falt")).toBeEnabled({ timeout: 20_000 });
  await expect(page.locator("#g-form button[type=submit]")).toHaveText("Ändra");
  // Och nu går nästa mening fram.
  await be(page, "Gör uppgift 4 svårare");
  await expect.poll(() => refines(anrop).length, { timeout: 20_000 }).toBe(2);
});

test("ett svar som landar när ett annat papper ligger framme slängs", async ({ page }) => {
  /* Omskrivningen tog tid; läraren stängde canvasen och skrev ett nytt papper.
     Svaret lästes mot `versioner[nu]` VID SVARET, utan id-jämförelse — och
     provets uppgifter skrevs in i det andra pappret som om läraren gjort det. */
  let slapp;
  const grind = new Promise(r => { slapp = r; });
  await fejka(page, { grind });
  await page.goto("/");
  await hydrerad(page);
  await skrivProv(page);
  await oppnaCanvas(page);
  await be(page, "Gör uppgift 4 kortare");
  await expect(page.locator("#g-falt")).toBeDisabled({ timeout: 10_000 });

  await page.locator("#g-stang").click();
  await expect(page.locator("#granskaskal")).toBeHidden();
  await page.locator("#skriv").click();
  await forbiNivavarningen(page);
  await expect(page.locator("#arkskal")).toContainText("Parabeln", { timeout: 20_000 });

  slapp();
  await expect(page.locator(".toast")).toContainText("lades undan", { timeout: 20_000 });
  // Det nya pappret är orört: ingen byggställning, ingen takstol.
  await expect(page.locator("#arkskal")).toContainText("Parabeln");
  await expect(page.locator("#arkskal")).not.toContainText("Takstolarna");
});

test("«Skriv om» frågar innan utkastets historik kastas", async ({ page }) => {
  /* Knappen byter text till «Skriv om provet» så fort ett utkast ligger i
     rutan — och skriver ett HELT NYTT papper. Fyra varvs ångra-historik
     försvann utan en fråga. */
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skrivProv(page);
  await oppnaCanvas(page);
  await be(page, "Gör uppgift 4 kortare");
  // Ångra-knappen tänds när varvet lagts till: nu FINNS det historik att tappa.
  await expect(page.locator("#g-angra")).toBeEnabled({ timeout: 20_000 });
  await page.locator("#g-stang").click();
  await expect(page.locator("#granskaskal")).toBeHidden();

  const skrivningar = () => anrop.filter(
    a => a.vag.endsWith("/generate")).length;
  expect(skrivningar()).toBe(1);

  await page.locator("#skriv").click();
  await expect(page.locator(".toast").filter({ hasText: "ångra-historiken" }))
    .toBeVisible();
  await expect(page.locator("#dokument")).toBeVisible();
  expect(skrivningar()).toBe(1);

  // Andra klicket skriver — läraren har sagt vad hon vill.
  await page.locator("#skriv").click();
  await forbiNivavarningen(page);
  await expect.poll(skrivningar, { timeout: 20_000 }).toBe(2);
});

test("nålen stannar på sitt eget ark", async ({ page }) => {
  /* Provet och lösningsförslaget är två ark med SAMMA element-id:n: uppg4 finns
     på båda. Nålarna sattes på det ark som råkade ligga framme, så ett byte till
     facit flyttade dit hela trådens markeringar — pekande på uppgifter ingen
     kommenterat. */
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skrivProv(page);
  await oppnaCanvas(page);

  await page.locator("#g-valj").click();
  await page.locator("#granskaskal .gdok [data-el='uppg4']").first().click();
  await be(page, "Ta bort deluppgift b)");
  await expect(page.locator("#granskaskal .gdok .gpin"))
    .toHaveCount(1, { timeout: 20_000 });

  // Lösningsförslaget: samma id:n, ingen kommentar.
  await page.locator("#g-arkval button").nth(1).click();
  await expect(page.locator("#granskaskal .gdok .gpin")).toHaveCount(0);
  // Och tillbaka igen — nålen står kvar där den sattes.
  await page.locator("#g-arkval button").nth(0).click();
  await expect(page.locator("#granskaskal .gdok .gpin")).toHaveCount(1);
});

test("godkännandets ström som tystnar säger det", async ({ page }) => {
  /* `API.strom` lämnar tillbaka null när strömmen tar slut utan sitt done.
     Raden var «if (!r) return;»: godkännandet tystnade, dokumentet fick aldrig
     sin PDF-sökväg, och läraren stod med ett papper hon trodde var utskrivet. */
  await fejka(page, { approveUtanDone: true });
  await page.goto("/");
  await hydrerad(page);
  await skrivProv(page);

  await page.locator("#godkann").click();
  await expect(page.locator(".toast")
    .filter({ hasText: "slutade svara mitt i godkännandet" }))
    .toBeVisible({ timeout: 20_000 });
});

test("«Börja om» bär Ångra för utkastet", async ({ page }) => {
  /* Varje annan slängning i appen har en väg tillbaka; den här var slutgiltig —
     ett felklick tog pappret och hela dess historik för gott. */
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skrivProv(page);

  await page.locator(".omstartknapp").click();
  await expect(page.locator("#dokument")).toBeHidden();
  const angra = page.locator(".toast button", { hasText: "Ångra utkastet" });
  await expect(angra).toBeVisible();
  await angra.click();
  await expect(page.locator("#dokument")).toBeVisible();
  await expect(page.locator("#arkskal")).toContainText("Byggställningen");
});
