import { expect, test } from "@playwright/test";
import * as L from "./larardag.mjs";

/* FORMERNA — arken ska se ut som förlagan gör
 *
 * Facit är designdokumentet «Arbetsblad prov och tavlor — femton former» i
 * Claude Design: fyra arbetsbladsformer, fem provblad, två lösningsförslag och
 * två tavlor. Stilbladen i repot är samma filer som där (blad.css, prov.css,
 * losning.css, gruppark.css) — men CSS ensam gör ingen form. Formen uppstår
 * först när renderaren sätter rätt element med rätt formnyckel, och det var
 * där arken hade glidit:
 *
 *   1. Arbetsbladet bar `data-form="ab"` — en nyckel ingen regel känner — och
 *      fick basvärdena i stället för form 1:s eller form 2:s egen sättning.
 *   2. Figuren lades UNDER frågan i stället för bredvid den. Förlagans form 2
 *      är just figurspalten; utan den är det en annan form.
 *   3. Provets figur ritades inte alls på skärmarket, fast provet bär den och
 *      PDF:en har den. Uppgiften hänvisade till «figuren» och där fanns ingen.
 *   4. Deluppgifternas poäng var totalen delad jämnt, inte provets egna.
 *   5. Tavlans spaltlinje ritades streckad och blek. På en riktig tavla är den
 *      dragen — designdokumentet tog upp den i sitt eget stilblad, vilket var
 *      beviset på att motorn ritade fel.
 */

const papper = (extra = {}) => ({
  typ: "Arbetsblad", moment: "andragradsekvationer", klass: "NA25",
  kurs: "Matematik, nivå 2c", datum: "2026-09-10", tid: "",
  gy: [], kalla: false, kallor: [], inst: { antal: 3, niva: "Blandat" },
  bilder: {}, referenser: [], forlaga: null, resultat: null, fokus: "",
  kontext: "start", niva: false, svarighet: 0, andrat: [], uppgifter: [],
  ...extra,
});

/** Sätter ett ark ur BladBygg och lägger det i sidan — samma väg som pappret
 *  ritas i planeringen, utan att behöva köra en hel generering. */
async function satt(page, html) {
  return page.evaluate(h => {
    const d = document.createElement("div");
    d.id = "formprov";
    d.innerHTML = h;
    document.body.appendChild(d);
    return d.firstElementChild.getAttribute("data-form");
  }, html);
}

test("arbetsbladet bär en av förlagans formnycklar — inte en egen", async ({ page }) => {
  await L.fejkatMoln(page);
  await L.oppna(page);

  const utan = await page.evaluate(() => window.BladBygg.ark(
    { typ: "Arbetsblad", moment: "andragradsekvationer", inst: {} },
    [{ nr: 1, p: 2, t: "Lös ekvationen $x^2 = 49$.", ut: "kort" }], {}));
  expect(await satt(page, utan)).toBe("gu1");          // form 1 · radbunden

  const med = await page.evaluate(() => window.BladBygg.ark(
    { typ: "Arbetsblad", moment: "cirkeln", inst: {} },
    [{ nr: 1, p: 2, t: "Bestäm randvinkeln.", ut: "kort",
       fig: { typ: "cirkel", gradA: 168, gradB: 18 } }], {}));
  expect(await satt(page, med)).toBe("gu2");           // form 2 · figurspalt
});

test("figuren står bredvid frågan, aldrig under den", async ({ page }) => {
  await L.fejkatMoln(page);
  await L.oppna(page);
  const html = await page.evaluate(() => window.BladBygg.ark(
    { typ: "Arbetsblad", moment: "cirkeln", inst: {} },
    [{ nr: 1, p: 2, t: "Bestäm randvinkeln.", ut: "kort",
       fig: { typ: "cirkel", gradA: 168, gradB: 18 },
       figkap: "Punkterna ligger på cirkeln." }], {}));
  await satt(page, html);

  const spalt = page.locator("#formprov .gukort .gutva");
  await expect(spalt).toHaveCount(1);
  // Frågan i vänstra spalten, figuren i den högra — och bildtexten under den.
  await expect(spalt.locator("> div").first().locator(".gufraga")).toHaveCount(1);
  await expect(spalt.locator("> div").last().locator(".gufigur")).toHaveCount(1);
  await expect(page.locator("#formprov .gufigkap")).toHaveText("Punkterna ligger på cirkeln.");
});

test("provbladet ritar uppgiftens figur och deluppgifternas egna poäng",
  async ({ page }) => {
    await L.fejkatMoln(page);
    await L.oppna(page);
    const html = await page.evaluate(() => window.BladBygg.provblad(
      { kurs: "Matematik, nivå 2c", klass: "NA25" },
      [{ nr: 7, p: 4, t: "Bestäm extrempunkterna.", ut: "rakna",
         fig: { typ: "graf", uttryck: "x => x*x" }, figkap: "Grafen är en hjälp.",
         del: ["Bestäm koordinaterna.", "Avgör karaktären."], delp: [3, 1] }],
      "C", true));
    await satt(page, html);

    // Figuren finns på arket, i förlagans klass, med sin bildtext.
    await expect(page.locator("#formprov .prfig")).toHaveCount(1);
    await expect(page.locator("#formprov .prfigkap")).toHaveText("Grafen är en hjälp.");
    // Poängen är provets egna: 3 p och 1 p — inte 2 + 2.
    const po = await page.locator("#formprov .prdel .prpo").allTextContents();
    expect(po).toEqual(["3 p", "1 p"]);
  });

test("provets figur följer med från serverns JSON hela vägen till arket",
  async ({ page }) => {
    /* Kedjan är franProv → Blad → arket. Figuren fanns i provets JSON och
       ritades i PDF:en, men föll bort på vägen till skärmen — och det syns
       bara när man går hela vägen. */
    const EXAM = {
      titel: "Prov · Derivator", kurs: "Matematik, nivå 2c", klass: "NA25",
      datum: "2026-09-03", tid_min: 90, hjalpmedel: "Räknare i del C.",
      uppgifter: [
        { del: "B", formaga: "P", typ: "rutin", poang: [2, 0, 0],
          text: "Ange derivatan till $f(x) = 3x^2$.", losning: "$6x$",
          bedomning: "+2 E" },
        { del: "C", formaga: "PL", typ: "problem", poang: [0, 0, 0],
          text: "Figuren visar vinkeln $v$ i enhetscirkeln.", losning: "",
          bedomning: "", figur: { typ: "enhetscirkel", vinkel: 40 },
          deluppgifter: [
            { poang: [3, 0, 0], text: "Bestäm vinkeln.", losning: "40°",
              bedomning: "+3 E" },
            { poang: [0, 1, 0], text: "Motivera avläsningen.", losning: "…",
              bedomning: "+1 C" }] },
      ],
    };
    const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");
    await L.fejkatMoln(page);
    await page.route("**/api/exams/generate", route => route.fulfill({
      status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: 9, exam: EXAM, typ: "prov", status: "utkast", errors: [], rounds: 1,
        granser: { E: 3, C: 5, A: 6 }, summor: { totalt: 6 } } }]) }));
    await L.oppna(page);
    await L.valjKlass(page, "NA25");
    await L.skriv(page, { typ: "Prov", moment: "derivator" });
    await L.vantaPapper(page, 60_000);

    // Figuren står på arket — inte bara i PDF:en.
    await expect(page.locator("#dokument .prfig")).toHaveCount(1);
    // …och deluppgifterna bär provets egna poäng, inte totalen delad jämnt.
    const po = await page.locator("#dokument .prdel[data-avdelad] .prpo")
      .allTextContents();
    expect(po).toEqual(["3 p", "1 p"]);

    /* Städa utkastet. Provet här är fejkat (id 9 finns bara i den här filens
       route), och utkastet ligger kvar i den delade basen till nästa spec —
       som återställer det, trycker Godkänn och får 404 från ett prov servern
       aldrig har sett. Sviten delar bas med flit; då får den som smutsar ner
       också torka. */
    const hogen = await (await page.request.get("/api/dokument")).json();
    if (hogen.utkast && hogen.utkast.id) {
      await page.request.delete(`/api/dokument/${hogen.utkast.id}`);
    }
  });

test("tavlans spaltlinje är dragen, inte streckad", async ({ page }) => {
  await L.fejkatMoln(page);
  await L.oppna(page);
  /* Förlagan tog upp linjen i sitt eget stilblad — «motorn ritar den streckad
     och blek» — och det är motorn som ska rätta sig, inte dokumentet. */
  const linjen = await page.evaluate(() => {
    const vard = document.createElement("div");
    vard.id = "tavprov";
    document.body.appendChild(vard);
    window.WBLayout.renderWhiteboard({ title: "T", boards: [{
      name: "hoger", width: 1200, height: 400, chrome: "aluminium",
      padding: { top: 24, right: 26, bottom: 24, left: 30 },
      columns: [
        { weight: 1, sections: [{ kind: "heading", text: "Teori", size: 26 }] },
        { weight: 1, sections: [{ kind: "heading", text: "Exempel", size: 26 }] },
      ] }] }, vard);
    const svgar = [...vard.querySelectorAll("svg.wb-svg")];
    const delare = svgar.find(s => (s.getAttribute("style") || "").includes("width:8px"));
    if (!delare) return null;
    const p = delare.querySelector("path");
    return { dash: p.getAttribute("stroke-dasharray"),
             bredd: p.getAttribute("stroke-width"),
             opacitet: (delare.getAttribute("style").match(/opacity:([\d.]+)/) || [])[1] };
  });
  expect(linjen, "ingen spaltlinje ritades").not.toBeNull();
  expect(linjen.dash).toBeNull();
  expect(Number(linjen.bredd)).toBeGreaterThan(1.5);
  expect(Number(linjen.opacitet)).toBeGreaterThan(0.5);
});
