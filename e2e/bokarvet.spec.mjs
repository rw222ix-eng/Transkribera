import { expect, test } from "@playwright/test";

/* BOKARVET I «BYGG VIDARE»
 *
 * Att bygga vidare på en tavla om s. 2–6 och sedan behöva slå upp s. 2–6 för
 * hand igen är att låta appen glömma något den själv har skrivet: förlagan bär
 * `bokuppg` — boken, spannet och lärarens uppgiftsurval — sedan den skrevs.
 *
 * Men arvet får inte ske i smyg. Kommentaren över `ritaArv` i plan.js är
 * husregeln — «ingenting ska ärvas i smyg — valen är nya» — så tre saker måste
 * hålla:
 *
 *   1. Bokdörren står ÖPPEN med rätt spann, där alla andra källval syns.
 *   2. Urvalet kommer tillbaka: de uppgifter som skulle räknas är kvar, och de
 *      läraren medvetet strök är strukna igen.
 *   3. Förlage-rutan SÄGER att boken följde med, och var den ändras.
 *
 * Och tvärtom: en förlaga utan bok (eller med prototypens bok, den utan id på
 * servern) ändrar ingenting — då hade dörren stått öppen och lovat sidor som
 * `bokval()` ändå kastar bort.
 */

const SCHEMA = { schema: [], lov: [], poster: [] };

const AVSNITT = [
  { nr: "1.1", titel: "Repetition", kap: "Kapitel 1 · Algebra",
    vag: "Algebraiska uttryck", sid: "2–6", uppg: 19 },
  { nr: "1.2", titel: "Linjära modeller", kap: "Kapitel 1 · Algebra",
    vag: "Räta linjens ekvation", sid: "7–12", uppg: 34 },
];

const BOK = {
  id: 3, namn: "Matematik 5000+ Kurs 2c", kurs: "Matematik, nivå 2c",
  sidor: 120, sidoffset: 0, status: "klar", lasta: 12, avsnitt: AVSNITT,
};

/* Uppslaget s. 2–6 som servern läst det: nitton uppgifter, 1101–1119. */
const UPPG = [];
for (let n = 1101; n <= 1119; n++) {
  UPPG.push({ nr: n, sida: 2 + Math.floor((n - 1101) / 4), niva: 1 + ((n - 1101) % 3) });
}

/* Lärarens tavla, som `Uppgifter.urval()` la den på pappret: allt på uppslaget
   utom 1104, som hon strök med flit. */
const BOKUPPG = {
  bok: BOK.namn, sidor: "2–6", avsnitt: "1.1 Repetition", bokId: 3,
  uppg: UPPG.map(u => u.nr).filter(n => n !== 1104),
  bort: [1104],
  remsa: "1101–1103, 1105–1119", bortremsa: "1104", losning: null,
};

function papper(extra = {}) {
  return {
    typ: "Tavla", moment: "1.1 Repetition", klass: "NA25",
    kurs: "Matematik, nivå 2c", datum: "2026-08-17", tid: "",
    gy: [], kalla: false, kallor: [], sidor: "2–6",
    inst: { langd: 45, starttid: "", exempel: 2 },
    bilder: {}, referenser: [], forlaga: null, resultat: null, fokus: "",
    kontext: "start", niva: false, svarighet: 0, andrat: [],
    anteckning: "Sparat tidigare", uppgifter: [],
    bokuppg: BOKUPPG, ...extra,
  };
}

const rad = (id, dok) => ({
  id, status: "godkant", markor: 0, sort: id, foljd: null,
  versioner: [dok], dokument: { ...dok, id },
});

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

async function fejka(page, { dokument = papper() } = {}) {
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, {
    sparade: [rad(1, dokument)], utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
  await page.route("**/api/bocker**", route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/uppslag")) {
      return json(route, { fran: 2, till: 6, uppgifter: UPPG,
                           olasta: [], utan_fakta: [], sidor: [] });
    }
    if (url.pathname.endsWith("/las")) {
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "done", result: { uppgifter: UPPG, lasta: 0 } }]) });
    }
    return json(route, { bocker: [BOK] });
  });
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern()
  && window.Bok && window.Bok.franServern() && window.Dokument
  && window.Dokument.sparade().length > 0);

/** Samma väg som läraren: kortet öppnas och «Bygg vidare på den här» trycks. */
async function byggVidare(page) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => window.Dokument.visa(0));
  await page.locator("#fh-oppna").click();
}

const dorren = page => page.locator('.kalla[data-dorr="bok"]');

/* Förlage-rutan bor i steget «Upplägg — och skriv», och stapeln viker ihop de
   steg man inte står i. «Bygg vidare» landar på steg 2 med förlagan på plats;
   det här är att bläddra dit den syns. */
const tillUppl = page => page.evaluate(() => {
  window.PlanSteg.las(4, false);
  window.PlanSteg.gaTill(4);
});

test("bokdörren står öppen på förlagans spann", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await byggVidare(page);

  await expect(dorren(page)).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => page.evaluate(() => window.Uppslag.spann()))
    .toEqual({ fran: 2, till: 6, bok: BOK.namn });
});

test("urvalet kommer tillbaka — också det läraren strök", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await byggVidare(page);

  /* Uppgifterna läses från servern efter att spannet satts, så listan fylls i
     efterhand — därför poll och inte en direkt avläsning. */
  const kvar = page.locator("#uppgnivaer .uppgchip:not([data-bort])");
  await expect.poll(() => kvar.count(), { timeout: 15_000 }).toBe(18);
  // 1104 var lärarens medvetna bortval och ska vara bortvald igen, inte
  // återuppstånden av att «tillbaka till förslaget» gällde.
  await expect(page.locator('#uppgnivaer .uppgchip[data-bort]')).toHaveText(["1104"]);
});

test("arvet står skrivet i förlage-rutan", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await byggVidare(page);
  await tillUppl(page);

  const rutan = page.locator("#refbok");
  await expect(rutan).toBeVisible();
  await expect(rutan).toContainText("Boken följer med: s. 2–6");
  await expect(rutan).toContainText("1101–1103, 1105–1119");
  // Raden säger var det ändras — arvet är ett förval, inte ett beslut.
  await expect(rutan).toContainText("bokdörren");
});

test("en förlaga utan bok ändrar ingenting", async ({ page }) => {
  await fejka(page, { dokument: papper({ bokuppg: null, sidor: "" }) });
  await page.goto("/");
  await hydrerad(page);
  await byggVidare(page);
  await tillUppl(page);

  await expect(dorren(page)).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator("#refruta")).toBeVisible();
  await expect(page.locator("#refbok")).toBeHidden();
});

test("prototypens bok — den utan id på servern — ärvs inte", async ({ page }) => {
  /* `bokval()` i plan.js kastar tyst bort en bok utan `bokId`: sidorna når
     aldrig prompten. Då får dörren inte stå öppen och lova dem. */
  await fejka(page, { dokument: papper({
    bokuppg: { ...BOKUPPG, bokId: null, bok: "Matematik 5000 3c" } }) });
  await page.goto("/");
  await hydrerad(page);
  await byggVidare(page);

  await expect(dorren(page)).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator("#refbok")).toBeHidden();
});

test("momentet är fortfarande förlagans — uppslaget skriver inte över det",
  async ({ page }) => {
    /* Att sätta ett spann skriver momentfältet (uppslag.js skrivMoment). Det är
       rätt när sidorna är det man utgår från, men här är momentet förlagans och
       redan satt: skrivs det över byter pappret ämne av ett arv. */
    await fejka(page, { dokument: papper({ moment: "repetition inför provet" }) });
    await page.goto("/");
    await hydrerad(page);
    await byggVidare(page);

    await expect(page.locator("#moment")).toHaveValue("repetition inför provet");
  });
