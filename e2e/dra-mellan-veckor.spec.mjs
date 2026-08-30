import { expect, test } from "@playwright/test";

/* DRAGET SOM BLÄDDRAR VECKAN
 *
 * Ett papper som fungerade ska kunna läggas på en lektion längre fram — men
 * draget slutade förr vid veckans kant: chipet kunde bara släppas på en lektion
 * som råkade vara uppritad, och nästa vecka nåddes bara genom att först bläddra
 * (och då tappa greppet om chipet). Nu bläddrar veckopilen medan chipet hålls
 * över den.
 *
 * Två saker måste hålla:
 *   1. Kopian landar på MÅLVECKANS datum — inte på den vecka draget började i.
 *   2. Draget städas upp centralt. Bläddringen river käll-chipet mitt i draget,
 *      och chipets egen dragend når då aldrig dokumentet: utan städningen låg
 *      dragDok och släppmarkeringarna kvar och nästa klick i veckan lästes fel.
 */

/* Måndag (dag 1) och onsdag (dag 3) i varje vecka: två lektioner att dra
   mellan, och en av dem i en helt annan vecka. */
const SCHEMA = {
  schema: [
    { dag: 1, tid: "08:15–09:00", kurs: "Matematik, nivå 2c", klass: "NA24", sal: "C112" },
    { dag: 3, tid: "10:15–11:00", kurs: "Matematik, nivå 2c", klass: "NA24", sal: "C112" },
  ],
  lov: [],
  poster: [],
};

/* Klockan fryses på tisdagen i v37 2026: veckan appen öppnar är då den som
   börjar måndag 2026-09-07, och nästa är 2026-09-14. Utan frysning berodde
   datumen nedan på vilken dag sviten råkade köras (testdatum-rötan). */
const IDAG = "2026-09-08T08:00:00";
const V1_MANDAG = "2026-09-07";
const V2_MANDAG = "2026-09-14";

const TAVLAN = {
  typ: "Tavla", moment: "andragradsekvationer", klass: "NA24",
  kurs: "Matematik, nivå 2c", datum: V1_MANDAG, tid: "08:15–09:00",
  gy: [], kalla: false, kallor: [], inst: {}, bilder: {}, referenser: [],
  forlaga: null, resultat: null, fokus: "", kontext: "start", niva: false,
  svarighet: 0, andrat: [], anteckning: "", uppgifter: [],
};

const rad = (id, dok) => ({
  id, status: "godkant", markor: 0, sort: id, foljd: null,
  versioner: [dok], dokument: { ...dok, id },
});

const json = (route, kropp) => route.fulfill({
  status: 200, contentType: "application/json", body: JSON.stringify(kropp) });

/** Fejkar datagrunden med en sparad tavla i vecka 1. `postat` samlar kopiorna. */
async function fejka(page) {
  const postat = [];
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/bocker", route => json(route, []));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
  await page.route("**/api/dokument", route => {
    const r = route.request();
    if (r.method() !== "POST") return json(route, { sparade: [rad(1, TAVLAN)], utkast: null });
    const kropp = r.postDataJSON();
    postat.push(kropp.dokument);
    return json(route, rad(100 + postat.length, kropp.dokument));
  });
  return postat;
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument && window.Klass);

/* HTML5-draget går inte att spela upp med mus i Playwright — webbläsaren äger
   dragoperationen. Händelserna dispatchas därför för hand, med EN DataTransfer
   genom hela gesten precis som webbläsaren gör. */
const DRAGET = `
  window.__dt = new DataTransfer();
  const drag = (el, typ) => el.dispatchEvent(new DragEvent(typ, {
    bubbles: true, cancelable: true, dataTransfer: window.__dt }));
`;

test("chipet dras till en lektion i en ANNAN vecka — pilen bläddrar under draget", async ({ page }) => {
  const postat = await fejka(page);
  await page.clock.install({ time: new Date(IDAG) });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await expect(page.locator("#schemagrid .lekt")).toHaveCount(2);
  expect(await page.evaluate(() => window.Klass.veckan())).toBe(V1_MANDAG);

  const chipet = page.locator("#schemagrid .dokchip[draggable='true']", { hasText: "Tavla" });
  await expect(chipet).toHaveCount(1);

  // Läraren tar tag i tavlan. Pilarna lyser upp: de hör till gesten nu.
  await page.evaluate(DRAGET + `
    drag(document.querySelector("#schemagrid .dokchip[draggable='true']"), 'dragstart');
  `);
  await expect(page.locator("#schemafram")).toHaveAttribute("data-dragmal", "");
  await expect(page.locator("#schemabak")).toHaveAttribute("data-dragmal", "");

  /* Chipet vilar över framåtpilen. dragover eldar om och om igen så länge det
     ligger kvar — tio händelser är EN vecka, inte tio, och kön (koat) får inte
     spela upp övertrampen efteråt. */
  await page.evaluate(() => {
    const p = document.querySelector("#schemafram");
    for (let i = 0; i < 10; i++) {
      p.dispatchEvent(new DragEvent('dragover', {
        bubbles: true, cancelable: true, dataTransfer: window.__dt }));
    }
  });
  await expect.poll(() => page.evaluate(() => window.Klass.veckan()),
    { timeout: 5000 }).toBe(V2_MANDAG);
  await page.waitForTimeout(800);
  expect(await page.evaluate(() => window.Klass.veckan())).toBe(V2_MANDAG);

  // Käll-chipet revs med veckan — men greppet om pappret sitter kvar.
  await expect(page.locator("#schemagrid .dokchip[draggable='true']")).toHaveCount(0);

  // Släpp på måndagens lektion i den nya veckan.
  await page.evaluate(`
    const mal = document.querySelector("#schemagrid .lekt");
    const skicka = typ => mal.dispatchEvent(new DragEvent(typ, {
      bubbles: true, cancelable: true, dataTransfer: window.__dt }));
    skicka('dragover'); skicka('drop');
  `);

  // Kopian ligger på MÅLVECKANS dag, inte på den vecka draget började i.
  await expect.poll(() => postat.length).toBe(1);
  expect(postat[0].datum).toBe(V2_MANDAG);
  expect(postat[0].typ).toBe("Tavla");
  expect(postat[0].aterbruk.datum).toBe(V1_MANDAG);
  expect(postat[0].id).toBeUndefined();

  // Och gesten är över: ingen släppmarkering, ingen lysande pil, inget grepp.
  await page.evaluate(`document.dispatchEvent(new DragEvent('dragend', {
    bubbles: true, dataTransfer: window.__dt }));`);
  await expect(page.locator("[data-drop]")).toHaveCount(0);
  await expect(page.locator("[data-dragmal]")).toHaveCount(0);
});

test("släpps chipet på pilen försvinner det inte tyst", async ({ page }) => {
  const postat = await fejka(page);
  await page.clock.install({ time: new Date(IDAG) });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await expect(page.locator("#schemagrid .lekt")).toHaveCount(2);

  await page.evaluate(DRAGET + `
    drag(document.querySelector("#schemagrid .dokchip[draggable='true']"), 'dragstart');
    drag(document.querySelector("#schemafram"), 'drop');
  `);

  await expect(page.locator(".toast")).toContainText("släpp pappret på en lektion");
  expect(postat.length).toBe(0);
  // Släppet avslutar draget: pilen slocknar, greppet släpps.
  await expect(page.locator("[data-dragmal]")).toHaveCount(0);
});

test("avbrutet drag efter en bläddring lämnar inget kvar", async ({ page }) => {
  await fejka(page);
  await page.clock.install({ time: new Date(IDAG) });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await expect(page.locator("#schemagrid .lekt")).toHaveCount(2);

  await page.evaluate(DRAGET + `
    drag(document.querySelector("#schemagrid .dokchip[draggable='true']"), 'dragstart');
  `);
  await page.evaluate(() => {
    document.querySelector("#schemabak").dispatchEvent(new DragEvent('dragover', {
      bubbles: true, cancelable: true, dataTransfer: window.__dt }));
  });
  await expect.poll(() => page.evaluate(() => window.Klass.veckan()),
    { timeout: 5000 }).toBe("2026-08-31");

  /* Chipet är rivet, så dragend eldar på det rivna elementet och når aldrig
     dokumentet. Webbläsaren gör likadant — och det är precis fallet där
     dragDok läckte: nästa klick på en lektion tolkades som ett släpp. */
  await page.evaluate(`document.dispatchEvent(new DragEvent('dragend', {
    bubbles: true, dataTransfer: window.__dt }));`);
  await expect(page.locator("[data-dragmal]")).toHaveCount(0);
  await page.locator("#schemagrid .lekt").first().click();
  await expect(page.locator("#schemagrid .lekt[data-vald]")).toHaveCount(1);
  await expect(page.locator("[data-drop]")).toHaveCount(0);
});
