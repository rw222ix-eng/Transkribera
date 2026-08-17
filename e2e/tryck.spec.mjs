import { expect, test } from "@playwright/test";

/* TAVLAN I TRYCKPAKETET
 *
 * Paketet byggdes på riktigt i etapp 0.9b — utom tavlan. Den finns bara som
 * ritad DOM i webbläsaren: ingen bild, ingen PDF, och servern kan inte rendera
 * om den eftersom motorn bor på klienten. Den hamnade därför i `saknas` och
 * kvittot fick säga det.
 *
 * tavla-bild.js ritar av den. Tre saker måste hålla:
 *
 *   1. Det som skickas är en RIKTIG PNG i tavlans verkliga storlek — inte en
 *      tom duk, inte en krympt förhandsvisning.
 *   2. Tavlan ligger överst i paketet, före elevernas papper.
 *   3. Utan server körs prototypens kvittering precis som förut.
 */

const SCHEMA = { schema: [], lov: [], poster: [] };

/** En tavla i wb-json-v1, som lesson_board skriver dem. */
const tavla = (rubrik = "Derivatans definition") => ({
  title: rubrik,
  boards: [{
    name: "genomgang", width: 1400, height: 460, chrome: "aluminium",
    padding: { top: 24, right: 26, bottom: 24, left: 30 },
    sections: [
      { kind: "heading", text: rubrik, size: 30 },
      { kind: "text", text: "Ändringskvoten när h går mot noll.", size: 19 },
      { kind: "math", latex: "f'(x)=\\lim_{h\\to 0}\\frac{f(x+h)-f(x)}{h}", size: 21 },
    ],
  }],
});

const papper = (extra = {}) => ({
  typ: "Tavla", moment: "derivatans definition", klass: "NA25",
  kurs: "Matematik, nivå 2c", datum: "2026-06-02", tid: "",
  gy: [], kalla: false, kallor: [], inst: {}, bilder: {}, referenser: [],
  forlaga: null, resultat: null, fokus: "", kontext: "start", niva: false,
  svarighet: 0, andrat: [], uppgifter: [], wb: tavla(), ...extra,
});

const rad = (id, dok) => ({
  id, status: "godkant", markor: 0, sort: id, foljd: null,
  versioner: [dok], dokument: { ...dok, id },
});

const strom = handelser =>
  handelser.map(h => `data: ${JSON.stringify(h)}\n\n`).join("");

async function fejka(page, sparade) {
  const anrop = [];
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade, utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
  await page.route("**/api/open", route => json(route, { ok: true }));
  await page.route("**/api/reveal", route => json(route, { ok: true }));
  await page.route("**/api/tryck", route => {
    const kropp = route.request().postDataJSON();
    anrop.push(kropp);
    /* Servern svarar olika på de två gesterna: en hopfogad fil för utskriften,
       en mapp med skilda filer för nedladdningen (routes_tryck, `separat`). */
    const resultat = kropp.separat
      ? { path: "C:\\\\Transkriberingar\\\\utskrift\\\\NA25 2026-06-02 101500",
          mapp: true, filer: ["01 Tavla — derivator.pdf", "02 Prov.pdf"],
          sidor: 4, dokument: [], saknas: [] }
      : { path: "C:\\\\Transkriberingar\\\\utskrift\\\\paket.pdf", sidor: 45,
          dokument: [], saknas: [] };
    return route.fulfill({
      status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: resultat }]),
    });
  });
  return anrop;
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

/** PNG:ens egna mått, lästa ur IHDR — bilden ska vara tavlan, inte en tumnagel. */
function png(dataurl) {
  expect(dataurl.startsWith("data:image/png;base64,")).toBe(true);
  const rå = Buffer.from(dataurl.slice("data:image/png;base64,".length), "base64");
  expect([...rå.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  return { bredd: rå.readUInt32BE(16), hojd: rå.readUInt32BE(20), byte: rå.length };
}

test("tavlan följer med i paketet som en riktig bild", async ({ page }) => {
  const anrop = await fejka(page, [rad(1, papper())]);
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);

  // Utskriftsrutan bor i planeringsvyn — den måste vara framme.
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => window.Tryck.oppna());
  await expect(page.locator("#tryckruta")).toBeVisible();
  await page.locator("#tryckskicka").click();

  await expect.poll(() => anrop.length, { timeout: 30_000 }).toBe(1);
  const tavlerad = anrop[0].dokument.find(d => d.typ === "Tavla");
  expect(tavlerad, JSON.stringify(anrop[0].dokument)).toBeTruthy();
  const bild = png(tavlerad.png);
  // Tavlan är 1400 px bred och ritas i 2×: en krympt förhandsvisning eller en
  // tom duk skulle synas här.
  expect(bild.bredd).toBeGreaterThan(2000);
  expect(bild.hojd).toBeGreaterThan(600);
  expect(bild.byte).toBeGreaterThan(10_000);
  // Överst i paketet — läraren bär in högen i den ordningen.
  expect(anrop[0].dokument[0].typ).toBe("Tavla");
  // «Skriv ut» förblir EN hopfogad fil: kopiorna ligger i den.
  expect(anrop[0].separat).toBeUndefined();
  // Kvittot säger inte längre att tavlan blev kvar.
  await expect(page.locator(".toast")).toContainText("i rätt ordning");
});

test("nedladdningen ber om skilda filer, inte om högen", async ({ page }) => {
  /* Läraren som sparar undan lektionens material vill ha tavlan, provet och
     facit var för sig — inte en enda PDF att bläddra i. Zip valdes bort (ett
     steg till att packa upp) och flera nedladdningar i rad likaså (webbläsare
     stoppar dem som «multipla nedladdningar»); servern lägger filerna i en
     mapp och /api/reveal öppnar den. */
  const anrop = await fejka(page, [rad(1, papper())]);
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);

  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => window.Tryck.oppna());
  await expect(page.locator("#tryckruta")).toBeVisible();
  await page.locator("#trycksampdf").click();

  await expect.poll(() => anrop.length, { timeout: 30_000 }).toBe(1);
  expect(anrop[0].separat).toBe(true);
  // Samma hög som utskriften — det är bara formen som skiljer.
  expect(anrop[0].dokument[0].typ).toBe("Tavla");
  await expect(page.locator(".toast")).toContainText("egen mapp");
});

test("utan server spelas prototypens kvittering upp som förut", async ({ page }) => {
  await page.route("**/api/var-kors", route => route.abort());
  const natanrop = [];
  await page.route("**/api/tryck", route => { natanrop.push(route.request().url()); route.abort(); });
  await page.goto("/");
  await page.waitForFunction(() => document.documentElement.hasAttribute("data-server") === false);

  // Utskriftsrutan bor i planeringsvyn — den måste vara framme.
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => window.Tryck.oppna());
  await page.locator("#tryckskicka").click();
  await expect(page.locator("#tryckskicka")).toHaveText("Utskrivet");
  expect(natanrop).toEqual([]);
});
