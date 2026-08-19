import { expect, test } from "@playwright/test";

/* FACITBLADEN — kort text, hela A4:an
 *
 * Läraren, med ett facit på skärmen: «alla de här facitbladen … de ska bara
 * ange svaret och en typ av lösning. Annars blir det så jävla mycket text och
 * det är svårläst.» Och strax därpå: «Texten på facit ska fylla hela
 * A4-bladet … dynamiskt justera texten … en minimistorlek på texten, typ
 * storlek 12 — texten kan bara bli större från 12.»
 *
 * Två krav som drar åt olika håll, och därför lätta att förstöra var för sig:
 *
 *   1. Facit trycker inte hela uppgiftstexten en gång till. Kvar står det som
 *      IDENTIFIERAR uppgiften — brickan och matematiken — medan
 *      instruktionsprosan («Gruppen ska enas om ett gemensamt svar …») hör till
 *      elevens papper och stannar där.
 *   2. Det som blir över i höjd går till GRADEN, inte till vitt papper. Ratten
 *      är CSS-variabeln --fsk (losning.css), och blad.js skruvar upp den efter
 *      pagineringen: aldrig under basen, aldrig över kanten, aldrig över taket.
 *
 * Ordningen mellan stegen är det som lättast går sönder: skalas arket FÖRE
 * pagineringen delas ett blad som renderaren själv blåst upp, och läraren får
 * två papper där ett räckte.
 */

const SCHEMA = { schema: [], lov: [], poster: [] };

/* Gruppuppgiften läraren hade framme: instruktionsprosan i mitten är precis
   det som inte ska följa med till facit. */
const LANG = "Beräkna utan räknare. Gruppen ska enas om ett gemensamt svar på "
  + "varje uttryck innan ni skriver ner det. A: $7 + 3 \\cdot 6$ "
  + "B: $\\frac{9 \\cdot 8 + 24}{12}$";

function papper(extra = {}) {
  return {
    typ: "Arbetsblad", moment: "prioriteringsregler", klass: "BA26B",
    kurs: "Matematik, nivå 1a", datum: "2026-09-14", tid: "",
    gy: [], kalla: false, kallor: [], inst: { antal: 3, niva: "Blandat" },
    bilder: {}, referenser: [], forlaga: null, resultat: null, fokus: "",
    kontext: "start", niva: false, svarighet: 0, andrat: [],
    provId: 12, losningsblad: true, uppgifter: [],
    ...extra,
  };
}

const rad = (id, dok) => ({
  id, status: "godkant", markor: 0, sort: id, foljd: null,
  versioner: [dok], dokument: { ...dok, id },
});

async function fejka(page, sparade) {
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade, utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

/** Öppnar förhandsvisningen på pappret — samma väg läraren tar, så att
 *  pagineringen och skalningen körs på riktigt och inte i ett provrör. */
async function visa(page) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => window.Dokument.visa(0));
  await expect(page.locator("#forhandsskal")).toBeVisible();
  await expect(page.locator("#fh-ark .ark[data-form='fa']").first()).toBeVisible();
}

/** Skalan arket landade på. Väntar ut formge(), som körs fyra gånger — sist när
 *  typsnitten laddats, och det är den mätningen som gäller. */
function skalan(page, n = 0) {
  return page.evaluate(i => {
    const ark = document.querySelectorAll("#fh-ark .ark[data-form='fa']")[i];
    return ark ? Number(ark.style.getPropertyValue("--fsk")) : 0;
  }, n);
}

test("facit upprepar inte uppgiftstexten — brickan och matematiken räcker",
  async ({ page }) => {
    await fejka(page, []);
    await page.goto("/");
    await hydrerad(page);

    const text = await page.evaluate(lang => {
      const d = document.createElement("div");
      d.id = "facitprov";
      d.innerHTML = window.BladBygg.arkfacit(
        { moment: "prioriteringsregler" },
        [{ nr: 1, p: 2, t: lang, f: "$25$ respektive $8$" }]);
      document.body.appendChild(d);
      return d.querySelector(".prtext").textContent;
    }, LANG);

    // Instruktionsprosan hör till elevens ark och följer inte med.
    expect(text).not.toContain("Gruppen ska enas");
    // Men uppgiften går fortfarande att känna igen: verbet och matematiken.
    expect(text).toContain("Beräkna");
    // Och det är KORTARE — annars var kortandet ingen kortning.
    expect(text.length).toBeLessThan(LANG.length * 0.7);

    /* Ett klipp mitt i en formel är obalanserade dollartecken, och då sätts
       resten av arket som matematik. Räkna spännen i stället för tecken: varje
       $…$ ska ha blivit ett eget mat-spann. */
    const spann = await page.locator("#facitprov .prtext .mat").count();
    expect(spann).toBeGreaterThan(0);
  });

test("skalan växer på ett halvtomt facit — men aldrig under basen",
  async ({ page }) => {
    /* Tre korta svar på ett A4. Utan ratten satt de i samma grad som fjorton
       skulle ha gjort, och två tredjedelar av pappret var vitt. */
    await fejka(page, [rad(1, papper({ uppgifter: [
      { nr: 1, p: 2, t: "Beräkna $7 + 3 \\cdot 6$.", f: "$25$" },
      { nr: 2, p: 2, t: "Beräkna $12 - 4 \\cdot 2$.", f: "$4$" },
      { nr: 3, p: 2, t: "Beräkna $(6 + 2) \\cdot 3$.", f: "$24$" },
    ] }))]);
    await page.goto("/");
    await hydrerad(page);
    await visa(page);

    await expect.poll(() => skalan(page), { timeout: 20_000 }).toBeGreaterThan(1);

    const matt = await page.evaluate(() => {
      const ark = document.querySelector("#fh-ark .ark[data-form='fa']");
      const grad = sel => parseFloat(getComputedStyle(ark.querySelector(sel)).fontSize);
      return {
        spill: ark.scrollHeight - ark.clientHeight,
        vag: grad(".losvar > span"),
        titel: grad(".lotitel"),
        nr: grad(".prnr"),
        blad: document.querySelectorAll("#fh-ark .ark[data-form='fa']").length,
      };
    });

    // Aldrig över kanten: ett svar under nederkanten är värre än vitt papper.
    expect(matt.spill).toBeLessThanOrEqual(0);
    // Aldrig under lärarens tolva — och basen (17,5 px) är golvet, inte taket.
    expect(matt.vag).toBeGreaterThanOrEqual(17.5);
    expect(matt.vag).toBeGreaterThanOrEqual(12);
    // EN ratt: rubrik och marginalsiffra växer med svaret, inte var för sig.
    expect(matt.titel).toBeGreaterThan(25);
    expect(matt.nr).toBeGreaterThan(23);
    // Tre svar är ett blad. Skalningen får inte hitta på en sida till.
    expect(matt.blad).toBe(1);
  });

test("ett fullt facit paginerar fortfarande — och sida två får sin egen grad",
  async ({ page }) => {
    /* Fjorton uppgifter med utskriven lösningsgång ryms inte på ett A4.
       Pagineringen mäter i BASGRADEN och delar därför på samma ställe som
       förut; sedan fyller varje blad sig självt, och sida två — den halvtomma —
       får en större grad än sida ett. */
    const vag = k => [[`Ledet ${k}`, "1 p"], ["Svaret sätts in", "1 p"]];
    const uppgifter = Array.from({ length: 14 }, (_, k) => ({
      nr: k + 1, p: 3, f: `$x = ${k + 1}$`,
      t: `Lös ekvationen $${k + 2}x + ${k} = ${(k + 2) * (k + 1) + k}$ och `
         + "kontrollera svaret genom insättning i det ursprungliga ledet.",
      vag: vag(k + 1),
    }));
    await fejka(page, [rad(1, papper({ uppgifter }))]);
    await page.goto("/");
    await hydrerad(page);
    await visa(page);

    await expect.poll(
      () => page.locator("#fh-ark .ark[data-form='fa']").count(),
      { timeout: 20_000 }).toBeGreaterThan(1);

    const arken = await page.evaluate(() =>
      Array.from(document.querySelectorAll("#fh-ark .ark[data-form='fa']"))
        .map(a => ({ fsk: Number(a.style.getPropertyValue("--fsk")),
                     spill: a.scrollHeight - a.clientHeight,
                     uppg: a.querySelectorAll(".pruppg").length })));

    // Inget blad spiller, och inget blad är tomt.
    arken.forEach(a => {
      expect(a.spill).toBeLessThanOrEqual(0);
      expect(a.uppg).toBeGreaterThan(0);
      expect(a.fsk).toBeGreaterThanOrEqual(1);
    });
    // Sista bladet bär resten och har därför luft kvar — den går till graden.
    expect(arken[arken.length - 1].fsk).toBeGreaterThan(arken[0].fsk);
  });
