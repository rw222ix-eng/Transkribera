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
