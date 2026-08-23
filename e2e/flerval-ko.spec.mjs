import { expect, test } from "@playwright/test";
import { forbiNivavarningen } from "./larardag.mjs";

/* FLERA RUTOR, OCH EN KÖ
 *
 * Två saker som båda kommer ur samma iakttagelse: läraren arbetar inte en ruta
 * och en mening i taget.
 *
 * 1. FLERVALET. «Gör 3 och 5 kortare» var två varv, två väntor, och två
 *    chanser för det andra varvet att skriva om det förstas grund. Klicket
 *    växlar nu rutan i urvalet, och alla valda rutor följer med i samma
 *    förfrågan. Kroppen vid ETT mål är oförändrad, byte för byte — kassetterna
 *    i tests/ är inspelade mot den.
 *
 * 2. KÖN. Fältet gick förr i disabled medan ett varv skrevs, och lärarens
 *    nästa mening tappades. Nu tas den emot och väntar på sin tur. Ett varv i
 *    luften åt gången, precis som förut — men ingen mening som försvinner.
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
/* Varje omskrivning ger ett SYNLIGT annat papper. Kön väntar på att pappret
   ritats om innan nästa post avfyras, och utan en verklig skillnad i texten
   hade testet inte kunnat skilja «väntade» från «väntade inte». */
const omskrivet = (n) => ({
  ...FORSTA,
  uppgifter: FORSTA.uppgifter.map((u, i) => i === 3
    ? { ...u, text: `Takstolarna, omskrivning ${n}.` } : u),
});

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

/**
 * Fejkar datagrunden och prov-rutterna.
 *
 * `grind` är en funktion som får varvets nummer och lämnar tillbaka ett löfte
 * omskrivningen väntar på — så hålls varv ett «pågående» medan testet skriver
 * nästa mening.
 */
async function fejka(page, { grind = null } = {}) {
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
          id: 9, exam: omskrivet(n), typ: "prov", status: "utkast", errors: [],
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

/* Lokatorer med hus. Appen har flera `.rubrik` och flera `.gvarv` på skärmen
   samtidigt — allting här hänger i #granskaskal eller i panelens egen lista. */
const chips = page => page.locator("#g-mal .gmalchip");
const koade = page => page.locator("#g-lista .gvarv[data-i-ko]");
const skickaknapp = page => page.locator("#g-form button[type=submit]");

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

// ── FLERVALET ───────────────────────────────────────────────────────────────

test("två klick ger två chips — och båda målen följer med till servern",
  async ({ page }) => {
    const anrop = await fejka(page);
    await page.goto("/");
    await hydrerad(page);
    await skrivProv(page);
    await oppnaCanvas(page);

    await valj(page, "uppg2", "uppg4");
    await expect(chips(page)).toHaveCount(2);
    await expect(chips(page).locator(".gmaltext")).toHaveText(["Uppgift 2", "Uppgift 4"]);
    await expect(page.locator("#g-mal")).toHaveAttribute("data-satt", "");
    await expect(page.locator("#g-mal")).toHaveAttribute("data-flera", "");
    /* Båda rutorna är markerade i pappret, inte bara den sist klickade. Räknat
       på ID:n och inte på noder: ligger facit i samma blad bär två noder samma
       id med flit (blad.js), och båda ska lysa. */
    expect(await page.evaluate(() => [...new Set(Array.from(
      document.querySelectorAll("#granskaskal .gdok [data-mal]"),
      e => e.dataset.el))])).toEqual(["uppg2", "uppg4"]);
    // Frågan i fältet räknar upp dem på svenska.
    await expect(page.locator("#g-falt"))
      .toHaveAttribute("placeholder", "Vad ska ändras i uppgift 2 och uppgift 4?");

    await be(page, "Gör dem kortare");
    await expect.poll(() => refines(anrop).length, { timeout: 20_000 }).toBe(1);
    const kropp = refines(anrop)[0].kropp;
    // `mal` är FÖRSTA målet — bakåtkompatibelt — och `malen` bär alla.
    expect(kropp.mal.el).toBe("uppg2");
    expect(kropp.malen.map(m => m.el)).toEqual(["uppg2", "uppg4"]);
    expect(kropp.malen.every(m => typeof m.innehall === "string"
                              && typeof m.renderat === "string")).toBe(true);
    // Provets riktade väg tar en LISTA när målen är flera.
    expect(kropp.nummer).toEqual([2, 4]);
    // Urvalet är nollställt när meningen gått i väg.
    await expect(page.locator("#g-mal")).not.toHaveAttribute("data-satt", "");
  });

test("ETT mål skickas exakt som förut — ingen malen, nummer som tal",
  async ({ page }) => {
    /* Kassetterna i tests/ är inspelade mot den kroppen. En extra nyckel gör
       varenda inspelning obrukbar, och det är därför formen prövas här. */
    const anrop = await fejka(page);
    await page.goto("/");
    await hydrerad(page);
    await skrivProv(page);
    await oppnaCanvas(page);

    await valj(page, "uppg4");
    await expect(chips(page)).toHaveCount(1);
    await expect(page.locator("#g-mal")).not.toHaveAttribute("data-flera", "");
    await be(page, "Ta bort deluppgift b)");

    await expect.poll(() => refines(anrop).length, { timeout: 20_000 }).toBe(1);
    const kropp = refines(anrop)[0].kropp;
    expect(kropp.mal.el).toBe("uppg4");
    expect(kropp.malen).toBeUndefined();
    expect(kropp.nummer).toBe(4);
  });

test("ett andra klick på samma ruta tar bort den ur urvalet", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skrivProv(page);
  await oppnaCanvas(page);

  await valj(page, "uppg2", "uppg3");
  await expect(chips(page)).toHaveCount(2);
  await valj(page, "uppg2");                       // samma ruta igen
  await expect(chips(page)).toHaveCount(1);
  await expect(chips(page).locator(".gmaltext")).toHaveText(["Uppgift 3"]);

  // Chipets eget kryss tar bara sitt eget mål …
  await valj(page, "uppg4");
  await expect(chips(page)).toHaveCount(2);
  await chips(page).first().locator(".gmalkryss").click();
  await expect(chips(page).locator(".gmaltext")).toHaveText(["Uppgift 4"]);
  // … och målrutans kryss tömmer allt.
  await page.locator("#g-malx").click();
  await expect(chips(page)).toHaveCount(0);
  await expect(page.locator("#granskaskal .gdok [data-mal]")).toHaveCount(0);
});

// ── KÖN ─────────────────────────────────────────────────────────────────────

test("två meningar i följd blir två varv i tur och ordning", async ({ page }) => {
  const grindar = [];
  const anrop = await fejka(page, {
    grind: () => new Promise(r => grindar.push(r)) });
  await page.goto("/");
  await hydrerad(page);
  await skrivProv(page);
  await oppnaCanvas(page);

  await be(page, "Först detta");
  await expect(skickaknapp(page)).toHaveText("Lägg i kö", { timeout: 10_000 });
  await expect(page.locator("#g-falt")).toBeEnabled();
  await expect(page.locator("#g-falt"))
    .toHaveAttribute("placeholder", "Skriv nästa — läggs i kö");

  await be(page, "Sedan detta");
  await be(page, "Och sist detta");
  await expect(koade(page)).toHaveCount(2);
  await expect(koade(page).locator(".gkonot")).toHaveText(["I kö", "I kö"]);
  expect(await page.evaluate(() => window.Granska.koad))
    .toEqual(["Sedan detta", "Och sist detta"]);

  // Bara ETT varv är i luften medan grinden är stängd.
  await expect.poll(() => refines(anrop).length, { timeout: 10_000 }).toBe(1);

  await expect.poll(() => grindar.length, { timeout: 10_000 }).toBe(1);
  grindar[0]();
  await expect.poll(() => refines(anrop).length, { timeout: 20_000 }).toBe(2);
  await expect.poll(() => grindar.length, { timeout: 10_000 }).toBe(2);
  grindar[1]();
  await expect.poll(() => refines(anrop).length, { timeout: 20_000 }).toBe(3);
  await expect.poll(() => grindar.length, { timeout: 10_000 }).toBe(3);
  grindar[2]();

  // FIFO: den ordning läraren skrev meningarna i är hennes.
  await expect.poll(() => refines(anrop).map(a => a.kropp.message),
                    { timeout: 20_000 })
    .toEqual(["Först detta", "Sedan detta", "Och sist detta"]);
  await expect(page.locator("#g-antal")).toHaveText("3 ändringar", { timeout: 20_000 });
  await expect(koade(page)).toHaveCount(0);
  // Raderna numreras i samma ordning — den köade raden BLEV varvets rad.
  await expect(page.locator("#g-lista .gvarv .gnotnr")).toHaveText(["1", "2", "3"]);
  await expect(page.locator("#g-lista .gvarv .gfraga"))
    .toHaveText(["Först detta", "Sedan detta", "Och sist detta"]);
});

test("krysset på en köad rad tar bara den posten", async ({ page }) => {
  const grindar = [];
  const anrop = await fejka(page, {
    grind: () => new Promise(r => grindar.push(r)) });
  await page.goto("/");
  await hydrerad(page);
  await skrivProv(page);
  await oppnaCanvas(page);

  await be(page, "Först detta");
  await expect(skickaknapp(page)).toHaveText("Lägg i kö", { timeout: 10_000 });
  await be(page, "Ångrar mig om detta");
  await be(page, "Men inte om detta");
  await expect(koade(page)).toHaveCount(2);

  await koade(page).first().locator(".gkokryss").click();
  await expect(koade(page)).toHaveCount(1);
  expect(await page.evaluate(() => window.Granska.koad)).toEqual(["Men inte om detta"]);

  await expect.poll(() => grindar.length, { timeout: 10_000 }).toBe(1);
  grindar[0]();
  await expect.poll(() => grindar.length, { timeout: 20_000 }).toBe(2);
  grindar[1]();
  await expect.poll(() => refines(anrop).map(a => a.kropp.message),
                    { timeout: 20_000 })
    .toEqual(["Först detta", "Men inte om detta"]);
});

test("klick på en köad rad lägger tillbaka meningen i fältet", async ({ page }) => {
  const grindar = [];
  await fejka(page, { grind: () => new Promise(r => grindar.push(r)) });
  await page.goto("/");
  await hydrerad(page);
  await skrivProv(page);
  await oppnaCanvas(page);

  await be(page, "Först detta");
  await expect(skickaknapp(page)).toHaveText("Lägg i kö", { timeout: 10_000 });
  await valj(page, "uppg2");
  await be(page, "Skriv om den här");
  await expect(koade(page)).toHaveCount(1);

  await koade(page).first().click();
  // Meningen är tillbaka i rutan, posten är ur kön — och rutan hon pekade på
  // följer med, annars hade nästa Enter gällt hela arket utan att någon sa det.
  await expect(page.locator("#g-falt")).toHaveValue("Skriv om den här");
  await expect(koade(page)).toHaveCount(0);
  await expect(chips(page).locator(".gmaltext")).toHaveText(["Uppgift 2"]);
  expect(await page.evaluate(() => window.Granska.koad)).toEqual([]);

  await expect.poll(() => grindar.length, { timeout: 10_000 }).toBe(1);
  grindar[0]();
});

test("ångra är låst så länge något står i kön", async ({ page }) => {
  /* Backar läraren mitt i byggs det köade önskemålet på en bas hon just
     kastat — servern skriver om den version som ligger framme när posten
     avfyras, inte den hon såg när hon skrev meningen. */
  const grindar = [];
  await fejka(page, { grind: () => new Promise(r => grindar.push(r)) });
  await page.goto("/");
  await hydrerad(page);
  await skrivProv(page);
  await oppnaCanvas(page);

  await be(page, "Först detta");
  await expect(skickaknapp(page)).toHaveText("Lägg i kö", { timeout: 10_000 });
  await be(page, "Sedan detta");
  await expect(koade(page)).toHaveCount(1);
  // Första varvet går, det andra väntar — och räknaren räknar bara det som
  // faktiskt avfyrats.
  await expect(page.locator("#g-antal")).toHaveText("1 ändring");
  await expect(page.locator("#g-angra")).toBeDisabled();

  await expect.poll(() => grindar.length, { timeout: 10_000 }).toBe(1);
  grindar[0]();
  /* Första varvet är klart och det finns något att ångra — men det köade
     avfyras av sig självt (räknaren går till 2 så fort det gått i luften),
     och så länge DET varvet går står knappen kvar låst. Mellanläget «klar
     och kön väntar» varar bara den väntan omritningen tar — det går inte
     att fånga med en väntande expect, så det som prövas är nästa stabila
     läge: varv två i luften, ångra fortfarande låst. */
  await expect.poll(() => grindar.length, { timeout: 20_000 }).toBe(2);
  await expect(page.locator("#g-antal")).toHaveText("2 ändringar");
  await expect(page.locator("#g-angra")).toBeDisabled();
  grindar[1]();
  await expect(page.locator("#g-antal")).toHaveText("2 ändringar", { timeout: 20_000 });
  // Tom kö, inget varv — nu är historiken lärarens igen.
  await expect(page.locator("#g-angra")).toBeEnabled({ timeout: 20_000 });
});

test("snabbknapparna köar också — samma väg som fritexten", async ({ page }) => {
  const grindar = [];
  const anrop = await fejka(page, {
    grind: () => new Promise(r => grindar.push(r)) });
  await page.goto("/");
  await hydrerad(page);
  await skrivProv(page);
  await oppnaCanvas(page);

  await be(page, "Först detta");
  await expect(skickaknapp(page)).toHaveText("Lägg i kö", { timeout: 10_000 });
  await valj(page, "uppg3");
  await page.locator("#g-snabb .gsnabbknapp", { hasText: "Svårare" }).click();
  await expect(koade(page)).toHaveCount(1);

  await expect.poll(() => grindar.length, { timeout: 10_000 }).toBe(1);
  grindar[0]();
  await expect.poll(() => grindar.length, { timeout: 20_000 }).toBe(2);
  grindar[1]();
  await expect.poll(() => refines(anrop).length, { timeout: 20_000 }).toBe(2);
  const andra = refines(anrop)[1].kropp;
  expect(andra.message).toContain("svårare");
  expect(andra.mal.el).toBe("uppg3");
});

test("utan server fungerar kön ändå — prototypens takt, i ordning",
  async ({ page }) => {
    /* Canvasen kör prototypens fejkväntan när det inte finns någon server att
       fråga (jobb == null). Kön får inte kräva ett riktigt anrop för att rulla:
       det är samma panel, samma tråd, samma ordning. */
    await page.route("**/api/var-kors", route => route.abort());
    const natanrop = [];
    await page.route("**/api/exams/**",
                     route => { natanrop.push(route.request().url()); route.abort(); });
    await page.goto("/");
    await page.waitForFunction(() =>
      document.documentElement.hasAttribute("data-server") === false);
    await page.getByRole("tab", { name: "Planering" }).click();
    await page.evaluate(() => {
      window.SattLage("Tavla");
      const f = document.querySelector("#moment");
      f.value = "derivatans definition";
      f.dispatchEvent(new Event("input", { bubbles: true }));
      window.PlanSteg.las(4, false);
      window.PlanSteg.gaTill(4);
    });
    await page.locator("#skriv").click();
    await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
    await oppnaCanvas(page);

    await be(page, "Först detta");
    await be(page, "Sedan detta");
    await expect(page.locator("#g-antal")).toHaveText("2 ändringar", { timeout: 30_000 });
    await expect(page.locator("#g-lista .gvarv .gfraga"))
      .toHaveText(["Först detta", "Sedan detta"]);
    expect(natanrop).toEqual([]);
  });
