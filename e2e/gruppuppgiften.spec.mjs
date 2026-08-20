import { expect, test } from "@playwright/test";

/* GRUPPUPPGIFTENS ARK — ETT HUVUD, PACKADE BLAD
 *
 * Läraren, med fyra uppgifter framme i canvasen:
 *
 *   «Det bildades fyra separata blad för fyra olika uppgifter — onödigt många.
 *    Man får i alla fall plats med två uppgifter på ett blad.»
 *   «Rubriken 1.1 Tal i olika former behöver bara stå på första bladet.»
 *   «Rutan med beskrivningarna behövs bara en gång — det är samma gruppuppgift.»
 *
 * Tre krav som hänger ihop, och rotorsaken var gemensam: varje blad bar hela
 * huvudet igen (rubrik + metarad + namnrader + instruktionsband, ~264 px), och
 * uppgiftstexten hade svällt av modellens tre-fyra radbrytningar i rad sedan
 * .gufraga fick white-space:pre-line. Två kostnader som tillsammans gav ett
 * papper per uppgift.
 *
 * Det som måste hålla, och som är lätt att förstöra var för sig:
 *   1. Fyra korta uppgifter blir HÖGST två blad, och minst två ryms på det
 *      första.
 *   2. Fortsättningsbladet bär varken rubrik, namnrader eller instruktionsband
 *      — men det bär en forts-rad, för lösa papper på ett bord ska gå att para
 *      ihop igen.
 *   3. Tomraderna kollapsas, men inte bort: «A:» och «B:» står kvar på var sin
 *      rad med en tom rad emellan — det var precis vad läraren bad om när
 *      pre-line lades in (41501d5).
 */

const SCHEMA = { schema: [], lov: [], poster: [] };

/* Texten som den faktiskt kommer ur modellen: tre radbrytningar i rad, inte två,
   och ett led per rad. Fyra led och tre skarvar är lärarens egen uppgift —
   pre-line gav den sex tomrader, alltså ~144 px, och då rymdes bara EN uppgift
   per blad. */
const uppgtext = (...led) =>
  "Beräkna utan räknare. Gruppen ska enas om ett gemensamt svar på varje "
  + "uttryck innan ni skriver ner det. Endast svar krävs.\n\n\n"
  + led.map((u, k) => `${"ABCD"[k]}: $${u}$`).join("\n\n\n");

const UPPGIFTER = [
  { nr: 1, p: 2, ut: "kort", t: uppgtext("7 + 3 \\cdot 6", "\\frac{9 \\cdot 8 + 24}{12}", "5^2 - 4", "8 : 2 + 6") },
  { nr: 2, p: 2, ut: "kort", t: uppgtext("12 - 4 \\cdot 2", "2^3 + 5", "\\frac{18}{6} \\cdot 4", "7 + 7 : 7") },
  { nr: 3, p: 2, ut: "kort", t: uppgtext("(6 + 2) \\cdot 3", "\\frac{15}{3} + 4", "10 - 2^2", "3 \\cdot (4 + 1)") },
  { nr: 4, p: 2, ut: "kort", t: uppgtext("9 - 2 \\cdot 3", "\\sqrt{49} + 1", "\\frac{24}{8} + 9", "6 \\cdot 2 - 5") },
];

function papper(extra = {}) {
  return {
    typ: "Gruppuppgift", moment: "1.1 Tal i olika former", klass: "BA26B",
    kurs: "Matematik, nivå 1a", datum: "2026-09-14", tid: "",
    gy: [], kalla: false, kallor: [],
    inst: { grupp: 3, langd: 45, redovisning: "Muntligt" },
    bilder: {}, referenser: [], forlaga: null, resultat: null, fokus: "",
    kontext: "start", niva: false, svarighet: 0, andrat: [],
    provId: 12, losningsblad: false, uppgifter: UPPGIFTER,
    ...extra,
  };
}

const rad = (id, dok) => ({
  id, status: "godkant", markor: 0, sort: id, foljd: null,
  versioner: [dok], dokument: { ...dok, id },
});

async function fejka(page, sparade, utkast = null) {
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade, utkast }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

/** Öppnar förhandsvisningen — samma väg läraren tar, så att delningen körs på
 *  riktigt papper och inte i ett provrör. */
async function visa(page) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => window.Dokument.visa(0));
  await expect(page.locator("#forhandsskal")).toBeVisible();
  await expect(page.locator("#fh-ark .gu").first()).toBeVisible();
}

/** Bladen som traven landade på. formge() körs fyra gånger — sist när
 *  typsnitten laddats, och det är den mätningen som gäller. */
function bladen(page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll("#fh-ark .gu")).map(g => ({
      forts: g.hasAttribute("data-forts"),
      kort: g.querySelectorAll(".gukort").length,
      huvud: !!g.querySelector(".guhuv"),
      namnrader: !!g.querySelector(".gutopp"),
      band: !!g.querySelector(".guband"),
      fortsrad: (g.querySelector(".gufortsrad") || {}).textContent || "",
      spill: -Math.min(0, (() => {
        const kort = g.querySelectorAll(".gukort");
        const sist = kort[kort.length - 1];
        if (!sist) return 0;
        return g.clientHeight - parseFloat(getComputedStyle(g).paddingBottom)
          - (sist.offsetTop + sist.offsetHeight);
      })()),
    })));
}

test("fyra korta uppgifter ryms på två blad — inte fyra", async ({ page }) => {
  await fejka(page, [rad(1, papper())]);
  await page.goto("/");
  await hydrerad(page);
  await visa(page);
  await expect.poll(() => page.locator("#fh-ark .gu").count(),
    { timeout: 20_000 }).toBeGreaterThan(0);
  await page.waitForTimeout(1200);   /* formge() kör fyra varv */

  const blad = await bladen(page);
  // Lärarens dom: fyra blad för fyra uppgifter är onödigt många.
  expect(blad.length).toBeLessThanOrEqual(2);
  // Och minst två uppgifter ska rymmas på det första.
  expect(blad[0].kort).toBeGreaterThanOrEqual(2);
  // Alla fyra står kvar — packningen får inte tappa någon.
  expect(blad.reduce((a, b) => a + b.kort, 0)).toBe(4);
  // Inget blad spiller ut under pappersmarginalen.
  blad.forEach(b => expect(b.spill).toBeLessThanOrEqual(10));
});

test("fortsättningsbladet bär forts-raden — inte huvudet en gång till",
  async ({ page }) => {
    /* Åtta uppgifter tvingar fram en fortsättning även på ett packat blad. */
    const atta = Array.from({ length: 8 }, (_, k) => ({
      ...UPPGIFTER[k % 4], nr: k + 1,
    }));
    await fejka(page, [rad(1, papper({ uppgifter: atta }))]);
    await page.goto("/");
    await hydrerad(page);
    await visa(page);
    await expect.poll(() => page.locator("#fh-ark .gu").count(),
      { timeout: 20_000 }).toBeGreaterThan(1);
    await page.waitForTimeout(1200);

    const blad = await bladen(page);
    const forsta = blad[0], forts = blad.slice(1);
    expect(forts.length).toBeGreaterThan(0);

    // Första bladet är hela huvudet: rubrik, namnrader, instruktionsband.
    expect(forsta.huvud).toBe(true);
    expect(forsta.namnrader).toBe(true);
    expect(forsta.band).toBe(true);
    expect(forsta.fortsrad).toBe("");

    forts.forEach((b, n) => {
      // Inget av huvudet upprepas — det är samma gruppuppgift.
      expect(b.huvud).toBe(false);
      expect(b.namnrader).toBe(false);
      expect(b.band).toBe(false);
      // Men bladet säger vad det hör till och var i ordningen det ligger.
      expect(b.fortsrad).toContain("1.1 Tal i olika former");
      expect(b.fortsrad).toContain(`forts. ${n + 2} av ${blad.length}`);
      expect(b.kort).toBeGreaterThan(0);
    });

    // Rubriken på första bladet är ren — inget «— forts.» klistrat på den.
    const titel = await page.locator("#fh-ark .gu .guhuv .gutitel").first().textContent();
    expect(titel.trim()).toBe("1.1 Tal i olika former");
  });

/* ── APPENS EGNA VÄGAR ──────────────────────────────────
   Testen ovan går genom förhandsvisningen, där traven är synlig när den ritas.
   Läraren möter pappret på en annan väg: utkastet plockas upp vid SIDLADDNINGEN
   (plan.js aterstallUtkast), och då ligger #dokument i planeringsvyn — som är
   `hidden` tills hon byter flik. Traven ritades alltså i en gömd vy där varje
   .gu rapporterar clientHeight 0, ledigt() blir −54 på varje blad, och delaArk
   delade tills ett kort låg kvar per papper. Mätt i den skarpa appen: fyra blad
   med 466, 703, 699 och 758 px ledigt.

   De två testen nedan går den vägen: gömd rita, sedan flikbyte. Och den varma
   omritningen efter den — arkväxeln ritar samma utkast en gång till på en sida
   där typsnitten redan är inne. */
const traven = page => page.evaluate(() => ({
  vyDold: document.querySelector("#vy-planering").hidden,
  gu: Array.from(document.querySelectorAll("#arkskal .gu")).map(g => ({
    kort: g.querySelectorAll(".gukort").length,
    ch: g.clientHeight,
    ledigt: (() => {
      const k = g.querySelectorAll(".gukort");
      const s = k[k.length - 1];
      if (!s) return null;
      return Math.floor(g.clientHeight - parseFloat(getComputedStyle(g).paddingBottom)
        - (s.offsetTop + s.offsetHeight));
    })(),
  })),
}));
const antalGu = page => page.evaluate(() => document.querySelectorAll("#arkskal .gu").length);

test("utkastet som plockas upp i en gömd flik delas inte alls — och packas när den öppnas",
  async ({ page }) => {
    await fejka(page, [], { id: 10, markor: 0, versioner: [papper()] });
    await page.goto("/");
    await hydrerad(page);
    await expect.poll(() => antalGu(page), { timeout: 15_000 }).toBeGreaterThan(0);
    await page.waitForTimeout(1200);

    const gomt = await traven(page);
    // Appen står kvar på transkriberingsvyn — pappret är ritat men omätbart.
    expect(gomt.vyDold).toBe(true);
    expect(gomt.gu[0].ch).toBe(0);
    // En gömd mätning får ALDRIG bli en maxdelning: ett blad, alla fyra korten.
    expect(gomt.gu.length).toBe(1);
    expect(gomt.gu[0].kort).toBe(4);

    // Läraren byter flik. Nu har pappret en layout, och nu — först nu — mäts det.
    await page.getByRole("tab", { name: "Planering" }).click();
    await expect.poll(() => antalGu(page), { timeout: 15_000 }).toBe(2);

    const satt = await traven(page);
    expect(satt.vyDold).toBe(false);
    expect(satt.gu.map(g => g.kort)).toEqual([2, 2]);
    // Inget blad står halvtomt medan nästa bär en ensam uppgift.
    satt.gu.forEach(g => expect(g.ledigt).toBeGreaterThanOrEqual(0));
  });

test("arkväxeln ritar om utkastet på en varm sida — packningen håller",
  async ({ page }) => {
    await fejka(page, [], { id: 10, markor: 0, versioner: [papper()] });
    await page.goto("/");
    await hydrerad(page);
    await page.getByRole("tab", { name: "Planering" }).click();
    await expect.poll(() => antalGu(page), { timeout: 15_000 }).toBe(2);

    /* Fram till facit och tillbaka: `byt` kallar visa() som ritar traven på nytt.
       Typsnitten är redan laddade, så den varma ritningen får inte färre
       mätvarv än den kalla — det var vad villkoret på document.fonts.status
       orsakade. */
    await page.locator("#arkval button").nth(1).click();
    await expect.poll(() => page.locator("#arkskal .ark[data-form='fa']").count(),
      { timeout: 15_000 }).toBeGreaterThan(0);
    await page.locator("#arkval button").nth(0).click();
    await expect.poll(() => antalGu(page), { timeout: 15_000 }).toBe(2);

    const satt = await traven(page);
    expect(satt.gu.map(g => g.kort)).toEqual([2, 2]);
    satt.gu.forEach(g => expect(g.ledigt).toBeGreaterThanOrEqual(0));
  });

/* ── INSTRUKTIONSRUTAN ÄR DOKUMENTETS ───────────────────────────
   Läraren pekade på rutan i canvas och skrev att «ett gemensamt svar per grupp
   lämnas in vid lektionens slut» skulle bort. Ingenting hände på pappret —
   rutan var en hårdkodad mall i två halvor (blad-bygg.js BAND + blad.js
   grupphuvud, som klistrade på redovisningslöftet ur inställningen) och stod
   inte i dokumentets JSON, så det fanns ingenting att skriva om. Panelen
   svarade ändå «Skrivet om … markerad i pappret».

   Nu äger dokumentet bandet (exam_spec.instruktion). De två testen nedan låser
   båda halvorna: fältet vinner OCH löftet klistras inte på igen — annars kommer
   just den mening hon strök tillbaka. */

const skriftligt = { grupp: 3, langd: 45, redovisning: "Skriftligt" };

test("bandet läraren skrev om står på pappret — löftet klistras inte på igen",
  async ({ page }) => {
    const eget = "Läs uppgiften tillsammans. Bestäm vem som skriver.";
    await fejka(page, [rad(1, papper({ instruktion: eget, inst: skriftligt }))]);
    await page.goto("/");
    await hydrerad(page);
    await visa(page);

    const band = page.locator("#fh-ark .guband").first();
    await expect(band).toContainText("Bestäm vem som skriver");
    // Meningen hon strök får inte komma tillbaka ur inställningen.
    await expect(band).not.toContainText("lämnas in vid lektionens slut");
    // Ägarskapstecknet — det grupphuvud() läser för att hålla fingrarna borta.
    await expect(band).toHaveAttribute("data-egen", "");
  });

test("ett papper utan fältet ser ut precis som förut", async ({ page }) => {
  // Ingen migrering: allt som sparades innan fältet fanns ska se likadant ut.
  await fejka(page, [rad(1, papper({ inst: skriftligt }))]);
  await page.goto("/");
  await hydrerad(page);
  await visa(page);

  const band = page.locator("#fh-ark .guband").first();
  await expect(band).toContainText("Läs uppgiften tillsammans");
  await expect(band).toContainText("lämnas in vid lektionens slut");
  await expect(band).not.toHaveAttribute("data-egen", "");
});

/* ── OMSKRIVNINGEN, OCH VAD PANELEN PÅSTÅR OM DEN ───────────────
   Andra halvan av samma bugg: svarsraden i granskningen var en KLIENTSIDIG
   mall som alltid skrevs. Servern skickar `andrade` (app/dokumentdiff.py), och
   det är den listan som ska tala — också när den är tom. */

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

/** Dokumentet så som servern svarar med det: JSON i exam_spec:s form. */
const exam = (extra = {}) => ({
  titel: "1.1 Tal i olika former", kurs: "Matematik, nivå 1a",
  hjalpmedel: "miniräknare",
  grupp: { elever: 3, langd_min: 45, redovisning: "skriftligt" },
  uppgifter: UPPGIFTER.map(u => ({
    text: u.t, poang: [2, 0, 0], typ: "rutin", formaga: "P",
    losning: "Svaret.", bedomning: "+2 E",
  })),
  ...extra,
});

async function fejkaRefine(page, { doc, andrade, errors }) {
  const anrop = [];
  await page.route("**/api/exams/**", route => {
    const vag = new URL(route.request().url()).pathname;
    if (!vag.endsWith("/refine")) return route.continue();
    anrop.push(route.request().postDataJSON());
    const klar = { id: 12, exam: doc, errors: errors || [], rounds: 1 };
    if (andrade) klar.andrade = andrade;
    return route.fulfill({ status: 200, contentType: "text/event-stream",
                           body: strom([{ type: "done", result: klar }]) });
  });
  return anrop;
}

/** Utkastet plockas upp, planeringen öppnas och canvasen med den — samma väg
 *  läraren tog när hon hittade buggen. */
async function iCanvas(page, dok) {
  await fejka(page, [], { id: 10, markor: 0, versioner: [dok] });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await expect.poll(() => antalGu(page), { timeout: 15_000 }).toBeGreaterThan(0);
  await page.locator("#granska").click();
  await expect(page.locator("#g-falt")).toBeVisible({ timeout: 10_000 });
}

async function pekaPa(page, valjare) {
  await page.locator("#g-valj").click();
  await page.locator(valjare).first().click();
  await expect(page.locator("#g-mal")).toHaveAttribute("data-satt", "");
}

async function skickaOnskemal(page, mening) {
  await page.locator("#g-falt").fill(mening);
  await page.locator("#g-form").evaluate(f => f.requestSubmit());
  await expect(page.locator("#g-antal")).toHaveText("1 ändring", { timeout: 20_000 });
}

const svarsrad = page => page.locator(".gvarv .fsvar .ftext").first();

test("en ändrad instruktion ändrar bandet på pappret — och märks", async ({ page }) => {
  const utan = "Läs uppgiften tillsammans. Bestäm vem som skriver.";
  await fejkaRefine(page, {
    doc: exam({ instruktion: utan }), andrade: ["instr"] });
  await iCanvas(page, papper({
    instruktion: "Läs uppgiften tillsammans. Bestäm vem som skriver. "
      + "Redovisas skriftligt: ett gemensamt svar per grupp lämnas in vid "
      + "lektionens slut.",
    inst: skriftligt }));

  await pekaPa(page, '#granskaskal .gdok [data-el="instr"]');
  await skickaOnskemal(page, "Ta bort meningen om att svaret lämnas in.");

  const band = page.locator("#arkskal .guband").first();
  await expect(band).not.toContainText("lämnas in vid lektionens slut",
                                       { timeout: 20_000 });
  await expect(band).toHaveClass(/andrad/);
  await expect(svarsrad(page)).toContainText("Skrivet om");
});

test("en omskrivning som inte ändrade något säger det rakt ut", async ({ page }) => {
  await fejkaRefine(page, { doc: exam(), andrade: [] });
  await iCanvas(page, papper({ inst: skriftligt }));

  await pekaPa(page, '#granskaskal .gdok [data-el="instr"]');
  await skickaOnskemal(page, "Ta bort meningen om att svaret lämnas in.");

  // Den gamla mallen påstod «Skrivet om … markerad i pappret» här. Den lögnen
  // är hela buggen, och det här testet är vakten.
  const svar = svarsrad(page);
  await expect(svar).toContainText("Ingenting på pappret ändrades", { timeout: 20_000 });
  await expect(svar).not.toContainText("Skrivet om");
});

test("ändrades något annat än det läraren pekade på säger panelen det",
  async ({ page }) => {
    await fejkaRefine(page, {
      doc: exam({ uppgifter: exam().uppgifter.map((u, k) =>
        k === 0 ? { ...u, text: "Beräkna $1 + 1$." } : u) }),
      andrade: ["uppg1"] });
    await iCanvas(page, papper({ inst: skriftligt }));

    await pekaPa(page, '#granskaskal .gdok [data-el="instr"]');
    await skickaOnskemal(page, "Ta bort meningen om att svaret lämnas in.");

    const svar = svarsrad(page);
    await expect(svar).toContainText("står kvar oförändrad", { timeout: 20_000 });
    // «uppgift 1» sedan brickorna blev siffror (lärarens val 2026-08-20).
    await expect(svar).toContainText("uppgift 1");
  });

/* ── METARADEN ÄR DOKUMENTETS ───────────────────────────────────
   «3 elever per grupp · 60 minuter · muntlig redovisning» ritades ur
   planeringens väljare medan dokumentets egna fält (exam_spec.GruppUpplagg)
   bara nådde PDF:en. «Gör grupperna om 4» skrev alltså om pappret men inte
   skärmen — och namnraderna, som räknas ur samma tal, stod kvar på tre. */

test("namnraderna följer dokumentets upplägg — och metaraden är borta", async ({ page }) => {
  await fejkaRefine(page, {
    doc: exam({ grupp: { elever: 4, langd_min: 60, redovisning: "poster" } }),
    andrade: ["namn"] });
  await iCanvas(page, papper({ inst: skriftligt }));

  // Metaraden trycks inte längre (lärarens beslut 2026-08-20): hon säger
  // villkoren själv i klassrummet. Fälten lever kvar och styr namnraderna.
  await expect(page.locator("#arkskal .gumeta")).toHaveCount(0);
  await expect(page.locator("#arkskal .gutopp .gurad")).toHaveCount(3);

  await skickaOnskemal(page, "Gör grupperna om 4, och en timme.");

  // Namnraderna räknas ur gruppstorleken och ska följa med dokumentet.
  await expect(page.locator("#arkskal .gutopp .gurad")).toHaveCount(4, { timeout: 20_000 });
  await expect(page.locator("#arkskal .gumeta")).toHaveCount(0);
});

/* ── RUBRIKEN ÄR DOKUMENTETS ────────────────────────────────────
   `titel` sparades ur serverns svar men ritades aldrig: pappret satte alltid
   momentets namn. «Döp om det» var alltså ett önskemål utan verkan — modellen
   skrev fältet, appen läste det inte. */

test("dokumentets titel står på arket — och på fortsättningsbladet",
  async ({ page }) => {
    await fejkaRefine(page, {
      doc: exam({ titel: "Repetition inför provet" }), andrade: ["rubrik"] });
    await iCanvas(page, papper({ inst: skriftligt }));

    await expect(page.locator("#arkskal .gutitel").first())
      .toHaveText("1.1 Tal i olika former");

    await pekaPa(page, '#granskaskal .gdok [data-el="rubrik"]');
    await skickaOnskemal(page, "Döp om det till Repetition inför provet.");

    await expect(page.locator("#arkskal .gutitel").first())
      .toHaveText("Repetition inför provet", { timeout: 20_000 });
    // Stämpelraden på blad två läser första bladets rubrik och följer med.
    await expect(page.locator("#arkskal .gufortstitel").first())
      .toHaveText("Repetition inför provet");
  });

test("en begäran servern inte kan gå med på får sitt skäl", async ({ page }) => {
  /* Reparationsloopen validerar varje varv: «ta bort poängen» faller på regeln
     att varje uppgift måste ge minst en poäng, dokumentet lämnas orört och
     `andrade` blir tom. «Ingenting ändrades» är sant men till ingen hjälp —
     läraren vet inte om modellen missförstod henne eller om det var förbjudet,
     och det avgör om hon ska skriva om meningen eller släppa det. */
  await fejkaRefine(page, {
    doc: exam(), andrade: [],
    errors: [{ path: "uppgifter[0]", code: "poang",
               message: "Uppgiften har 0 poäng — ge minst 1 poäng." }] });
  await iCanvas(page, papper({ inst: skriftligt }));

  await pekaPa(page, '#granskaskal .gdok [data-el="uppg1"]');
  await skickaOnskemal(page, "Ta bort poängen på den här.");

  const svar = svarsrad(page);
  await expect(svar).toContainText("uppgiften har 0 poäng — ge minst 1 poäng",
                                   { timeout: 20_000 });
  await expect(svar).not.toContainText("Skrivet om");
});

/* ── TABELLEN, NOTISEN OCH BOKENS ARK ───────────────────────────
   Tre element som pekade fel eller inte fanns: alla jämförelsetabeller delade
   id:t «tabell», notisen gick aldrig från JSON:en till skärmen, och bokens
   lösningsark bar sina boknummer i dokumentets uppgiftsserie. */

const medTabell = () => UPPGIFTER.map((u, k) => k === 1
  ? { ...u, tabell: { rubriker: ["År", "Antal"], rader: [["2020", "12"]] } } : u);

test("ett klick i tabellen låser omskrivningen till uppgiftens nummer",
  async ({ page }) => {
    const anrop = await fejkaRefine(page, { doc: exam(), andrade: ["uppg2"] });
    await iCanvas(page, papper({ inst: skriftligt, uppgifter: medTabell() }));

    await pekaPa(page, "#granskaskal .gdok .gutab");
    // Namnet säger fortfarande att det var tabellen — id:t är uppgiftens.
    // «Uppgift 2» sedan brickorna blev siffror (lärarens val 2026-08-20).
    await expect(page.locator("#g-mal .gmaltext")).toHaveText("Tabellen · Uppgift 2");
    await skickaOnskemal(page, "Lägg till en rad för 2021.");
    expect(anrop[0].nummer).toBe(2);
  });

test("notisen på uppgiften ritas på arket", async ({ page }) => {
  await fejkaRefine(page, {
    doc: exam({ uppgifter: exam().uppgifter.map((u, k) =>
      k === 0 ? { ...u, notis: "Rita en teckenrad som stöd." } : u) }),
    andrade: ["uppg1"] });
  await iCanvas(page, papper({ inst: skriftligt }));

  await expect(page.locator("#arkskal .gunotis")).toHaveCount(0);
  await pekaPa(page, '#granskaskal .gdok [data-el="uppg1"]');
  await skickaOnskemal(page, "Påminn om teckenraden.");

  await expect(page.locator("#arkskal .gunotis").first())
    .toHaveText("Rita en teckenrad som stöd.", { timeout: 20_000 });
});

/* Posterna bär SKRIVET innehåll, så som /api/bocker/{id}/losningar lämnar dem
   (fb4a47d): utan text och svar ritar blad-boklos bara platshållararket
   «Lösningarna är inte skrivna än», och då finns ingen post att peka på. */
const BOKUPPG = {
  bok: "Matematik 5000+ 1a", sidor: "12–15", avsnitt: "1.1 Tal", bokId: null,
  uppg: [3101, 3102], bort: [], remsa: "3101–3102", bortremsa: "",
  losning: { niva: "Nivå 2 och 3", antal: 2, uppg: [3101, 3102],
             remsa: "3101–3102",
             poster: [
               { nr: 3101, niva: 1, text: "Beräkna $7 + 3 \\cdot 6$.",
                 svar: "$25$", vag: [["$3 \\cdot 6 = 18$", "multiplikation före addition"]] },
               { nr: 3102, niva: 2, text: "Beräkna $(6 + 2) \\cdot 3$.",
                 svar: "$24$", vag: [["$6 + 2 = 8$", "parentesen först"]] }] },
};

test("bokens lösningsark skickar inget uppgiftsnummer till servern",
  async ({ page }) => {
    /* Arket skrivs ur bokens lästa sidor och finns inte i provets JSON.
       Posterna bar ändå dokumentets serie: 3101 blev `uppg3101`, och
       nummerlåsningen skickade «uppgift 3101» till ett dokument med fyra
       uppgifter. Modellen fick ett mål som inte finns. */
    const anrop = await fejkaRefine(page, { doc: exam(), andrade: [] });
    await iCanvas(page, papper({ inst: skriftligt, bokuppg: BOKUPPG }));

    await pekaPa(page, '#granskaskal .gdok [data-el="bokuppg3101"]');
    await expect(page.locator("#g-mal .gmaltext")).toHaveText("Bokens uppgift 3101");
    await skickaOnskemal(page, "Skriv ut hela uträkningen.");

    expect(anrop[0].nummer).toBeUndefined();
    expect(anrop[0].mal.namn).toBe("Bokens uppgift 3101");
  });

/* ── FACITPOSTEN ÄR SIN UPPGIFT ─────────────────────────────────
   «Om jag ändrar något i facit så ska uppgiften också ändras.» Första steget är
   att facitposten alls går att peka på: dess bricka är en BOKSTAV («D.»), och
   markera() läste den med parseInt — NaN, alltså inget data-el, alltså ingen
   `nummer`-låsning till servern. Facit i bladet lägger båda arken i samma
   trave, och då syns det andra kravet också: ändringen märks på båda. */

test("ett klick på facitposten låser omskrivningen till uppgiftens nummer",
  async ({ page }) => {
    const anrop = await fejkaRefine(page, {
      doc: exam({ uppgifter: exam().uppgifter.map((u, k) => k === 3
        ? { ...u, text: "Beräkna $6 : 2$.", losning: "$3$" } : u) }),
      andrade: ["uppg4"] });
    await iCanvas(page, papper({
      inst: { ...skriftligt, facit: "Facit i bladet" } }));

    // Facitets fjärde post heter «4.» sedan gruppuppgiften bytte till siffer-
    // brickor (lärarens val 2026-08-20) — och är uppgift 4.
    await pekaPa(page, '#granskaskal .gdok .pruppg[data-el="uppg4"]');
    await expect(page.locator("#g-mal .gmaltext")).toHaveText("Uppgift 4");
    await skickaOnskemal(page, "Mindre tal, och svaret ska bli ett heltal.");

    // Låsningen läses ur elementets id — utan den fick modellen gissa vilken
    // av fyra uppgifter «mindre tal» gällde.
    expect(anrop[0].nummer).toBe(4);
    expect(anrop[0].mal.namn).toBe("Uppgift 4");
    // Uppgiften och dess facit är samma sak sedd från två håll: båda märks.
    await expect(page.locator('#arkskal .gukort[data-el="uppg4"]'))
      .toHaveClass(/andrad/, { timeout: 20_000 });
    await expect(page.locator('#arkskal .pruppg[data-el="uppg4"]'))
      .toHaveClass(/andrad/);
  });

test("tre radbrytningar i data blir EN tomrad på arket — inte noll",
  async ({ page }) => {
    await fejka(page, [rad(1, papper())]);
    await page.goto("/");
    await hydrerad(page);
    await visa(page);
    await expect(page.locator("#fh-ark .gufraga").first()).toBeVisible();

    const text = await page.locator("#fh-ark .gufraga").first().evaluate(el => {
      /* KaTeX har bytt ut $…$ mot spann — läs den råa texten som pre-line
         faktiskt renderar, med formlerna som de nu står. */
      return el.textContent;
    });
    // Tre radbrytningar i rad blir aldrig tre rader tomt papper.
    expect(text).not.toMatch(/\n\s*\n\s*\n/);
    // Men den tomma raden mellan A: och B: står kvar — det var hela poängen
    // med pre-line (41501d5), och läraren bad om just det avståndet.
    expect(text).toMatch(/\n\s*\n/);
    expect(text).toContain("A:");
    expect(text).toContain("B:");
  });
