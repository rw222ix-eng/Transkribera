import { expect, test } from "@playwright/test";
import { forbiNivavarningen } from "./larardag.mjs";

/* PDF:EN SKA VARA SKÄRMEN
 *
 * Lärarens ord: «exporten av alla pdf:er ska renderas korrekt — jag vill ha
 * pdf-filerna EXAKT som de ser ut i appen». Fram till nu sattes prov,
 * arbetsblad, diagnos, gruppuppgift och anteckningar om i LaTeX vid
 * godkännandet. Snarlikt, aldrig identiskt: brickorna satt ihop, tabellerna
 * hade andra linjer, och lärarens egna inlagda bilder — som bara finns i
 * webbläsarens dokument (v.bilder) och aldrig i provets JSON — kom inte med
 * alls.
 *
 * Klienten ritar därför av bladen och skickar bilderna med godkännandet
 * (blad-bild.js `dokument`), och servern lägger dem på A4. Fyra krav bor här:
 *
 *   1. ALLA ARKLÄGEN följer med, inte bara det som råkar stå framme. Facit är
 *      ett eget dokument (`losningsblad`) och blir en egen fil.
 *   2. Provets facit gör det INTE: knappen där hämtar bedömningsanvisningen,
 *      som är lärarens rättningsdokument och aldrig ett blad på skärmen.
 *   3. Markeringarna stannar på skärmen. Ett papper ur skrivaren är lärarens,
 *      inte appens anteckningsbok.
 *   4. Lärarens inlagda bild ÄR med — den satt i DOM:en hela tiden.
 *
 * Krav 3 och 4 går inte att pröva i PNG-datan (en prick är några pixlar, och
 * ingen av dem stavas «aprick»). Det som prövas är i stället XML:en som går
 * in i bilden: bildproducenten serialiserar sin klon till en sträng, och den
 * strängen ÄR pappret. Fångas den fångas allt som ritas.
 */

const SCHEMA = {
  schema: [{ dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 2c",
             klass: "NA25", sal: "P807" }],
  lov: [], poster: [],
};

/** Prov-JSON som app/exam_spec.py definierar den — två uppgifter räcker. */
const EXAM = {
  titel: "Prov · Derivator",
  kurs: "Matematik, nivå 2c", klass: "NA25", datum: "2026-09-03", tid_min: 90,
  hjalpmedel: "Del B utan räknare. Del C med räknare.",
  uppgifter: [
    { del: "B", formaga: "B", typ: "rutin", poang: [2, 0, 0],
      text: "Ange derivatan till $f(x) = 3x^2$.",
      losning: "$f'(x) = 6x$", bedomning: "+2 E för korrekt derivata." },
    { del: "C", formaga: "PL", typ: "problem", poang: [1, 2, 1],
      text: "Bestäm största värdet för $f(x) = -x^2 + 4x$.",
      losning: "$f(2) = 4$", bedomning: "+1 E ansats, +2 C metod." },
  ],
};

/** Anteckningar som app/notes_gen.py definierar dem. */
const NOTES = {
  titel: "Derivator — så gör vi",
  sektioner: [{ rubrik: "Det här ska med",
                stycken: ["Ändringskvoten när $h$ går mot noll."] }],
};

/* En riktig, minimal PNG — den läraren «lagt in» på en uppgift. Röd, 1×1. */
const BILD = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAf"
  + "Fcn/AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

/** Fejkad datagrund + fejkade generate/approve. `anrop` bär kropparna. */
async function fejka(page, { typ = "prov" } = {}) {
  const anrop = [];
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
  await page.route("**/api/planning/**", route => json(route, { ok: true }));
  const sse = (route, kropp) => route.fulfill({
    status: 200, contentType: "text/event-stream", body: strom(kropp) });
  await page.route("**/api/anteckningar/**", route => {
    const vag = new URL(route.request().url()).pathname;
    anrop.push({ vag, kropp: route.request().postDataJSON() });
    if (vag.endsWith("/approve")) {
      return sse(route, [{ type: "done", result: {
        id: 11, pdf: "C:/Transkriberingar/anteckningar/d.pdf",
        tex: "C:/Transkriberingar/anteckningar/d.tex", errors: [] } }]);
    }
    return sse(route, [{ type: "done", result: {
      id: 11, anteckningar: NOTES, typ: "anteckningar", status: "utkast",
      versions: [], errors: [], rounds: 1 } }]);
  });
  await page.route("**/api/exams/**", route => {
    const vag = new URL(route.request().url()).pathname;
    anrop.push({ vag, kropp: route.request().postDataJSON() });
    if (vag.endsWith("/approve")) {
      return sse(route, [{ type: "done", result: {
        id: 9, pdf: "C:/Transkriberingar/prov/derivator.pdf",
        tex: "C:/Transkriberingar/prov/derivator.tex", errors: [] } }]);
    }
    return sse(route, [{ type: "done", result: {
      id: 9, exam: EXAM, typ, status: "utkast", errors: [], rounds: 1,
      granser: { E: 3, C: 5, A: 6 }, summor: { totalt: 6 } } }]);
  });
  return anrop;
}

async function skriv(page, typ, moment = "derivator", onskemal = null) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(([t, m, ons]) => {
    window.SattLage(t);
    const satt = (id, v) => {
      const e = document.querySelector(id);
      e.value = v;
      e.dispatchEvent(new Event("change", { bubbles: true }));
    };
    satt("#p-kurs", "Matematik, nivå 2c");
    satt("#p-klass", "NA25");
    const f = document.querySelector("#moment");
    f.value = m;
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
    /* Anteckningarnas källa är rutan i typvalen, inte momentet — den fylls
       EFTER gaTill, för raderna ritas om när typen byts (larardag.mjs). */
    if (ons != null) {
      const ruta = document.querySelector(".typfritext");
      if (ruta) {
        ruta.value = ons;
        ruta.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
  }, [typ, moment, onskemal]);
  await page.locator("#skriv").click();
  /* «derivator» är 3c-innehåll i en 2c-kurs — första klicket blir varningen.
     Se nivavarning.spec.mjs; här prövas godkännandet, inte ämnesplanen. */
  await forbiNivavarningen(page);
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

/** Kroppen godkännandet skickade — väntar ut avritningen, som tar sin tid. */
async function bladenIApprove(page, anrop, slut = "/approve") {
  await expect.poll(() => anrop.some(a => a.vag.endsWith(slut)),
                    { timeout: 30_000 }).toBe(true);
  return (anrop.find(a => a.vag.endsWith(slut)).kropp || {}).blad;
}

const arPng = s => typeof s === "string" && s.startsWith("data:image/png;base64,");

test("arbetsbladets godkännande bär med sig BÅDA arklägena", async ({ page }) => {
  const anrop = await fejka(page, { typ: "arbetsblad" });
  await page.goto("/");
  await hydrerad(page);
  await skriv(page, "Arbetsblad", "primitiva funktioner");
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  await page.locator("#godkann").click();
  const blad = await bladenIApprove(page, anrop);

  // Elevernas ark …
  expect(blad.uppgift.length).toBeGreaterThan(0);
  expect(blad.uppgift.every(arPng)).toBe(true);
  /* … och facit. Det är det som INTE stod framme på skärmen: växlaren visade
     arbetsbladet. Ritas bara det som visas blir facit-filen bladets kopia. */
  expect(blad.facit.length).toBeGreaterThan(0);
  expect(blad.facit.every(arPng)).toBe(true);
  // Två olika papper, inte samma bild två gånger.
  expect(blad.facit[0]).not.toBe(blad.uppgift[0]);
});

test("provets godkännande skickar bladen — men inget facit", async ({ page }) => {
  /* Provets lösningsförslag har ingen egen fil på servern: knappen hämtar
     bedömningsanvisningen, som bär kravgränser, bedömning och kommenterade
     elevlösningar och aldrig varit ett av bladen i högen. Den sätts i LaTeX
     som förut — och då finns det ingen bild att skicka. */
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skriv(page, "Prov");
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  await page.locator("#godkann").click();
  const blad = await bladenIApprove(page, anrop);
  expect(blad.uppgift.length).toBeGreaterThan(0);
  expect(blad.uppgift.every(arPng)).toBe(true);
  expect(blad.facit).toEqual([]);
});

test("anteckningarna går samma väg", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skriv(page, "Anteckningar", "kursstart",
              "Boken, rutinerna och provdatumen.");
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  await page.locator("#godkann").click();
  const blad = await bladenIApprove(page, anrop, "/anteckningar/11/approve");
  expect(blad.uppgift.length).toBeGreaterThan(0);
  expect(blad.uppgift.every(arPng)).toBe(true);
  // Pappret ÄR lärarens ark — det finns ingen andra hälft att vända på.
  expect(blad.facit).toEqual([]);
});

test("gruppuppgiftens facit läggs SIST i samma fil", async ({ page }) => {
  /* Gruppuppgiften har ingen fil bredvid: gruppuppgift.tex.j2 skriver alltid
     ut «Facit och bedömning» på sista sidan, och det är lärarens ark i samma
     dokument. Växlaren erbjuder det som ett eget läge på skärmen — men i
     mappen är det en sida, inte en fil. Hamnade det i `facit` hade servern
     lagt det i en fil ingen rutt hämtar, och gruppens papper hade kommit ur
     skrivaren utan facit. */
  const anrop = await fejka(page, { typ: "gruppuppgift" });
  await page.goto("/");
  await hydrerad(page);
  await skriv(page, "Gruppuppgift", "primitiva funktioner");
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  const utan = await page.evaluate(() =>
    document.querySelectorAll('#arkskal .ark[data-form="fa"]').length);
  expect(utan, "gruppuppgiften bar redan sitt facit — testet mäter inget")
    .toBe(0);

  await page.locator("#godkann").click();
  const blad = await bladenIApprove(page, anrop);
  expect(blad.facit).toEqual([]);
  // Facitarket ligger som en sida till i dokumentets egen fil.
  expect(blad.uppgift.length).toBeGreaterThan(1);
  expect(blad.uppgift.every(arPng)).toBe(true);
  expect(blad.uppgift.at(-1)).not.toBe(blad.uppgift[0]);
});

/* ── Vad som faktiskt går in i bilden ────────────────────────────────
   Avritningen serialiserar sin klon till XML och lägger den i ett
   <foreignObject>. Fångar man serialiseringen har man pappret, tagg för tagg —
   och kan pröva det som är osynligt i en PNG. */
async function xmlUr(page, v) {
  return page.evaluate(async dok => {
    const fangat = [];
    const org = XMLSerializer.prototype.serializeToString;
    XMLSerializer.prototype.serializeToString = function (nod) {
      const s = org.call(this, nod);
      fangat.push(s);
      return s;
    };
    try {
      await window.BladBild.dokument(dok, { skala: 1 });
    } finally {
      XMLSerializer.prototype.serializeToString = org;
    }
    return fangat.filter(s => s.indexOf("bladtrav") >= 0);
  }, v);
}

/** Ett arbetsblad som ligger i lärarens hög, med två uppgifter. */
function papper(extra = {}) {
  return {
    typ: "Arbetsblad", moment: "primitiva funktioner", klass: "NA25",
    kurs: "Matematik, nivå 2c", datum: "2026-09-14", tid: "",
    gy: [], kalla: false, kallor: [],
    inst: { antal: 2, niva: "Blandat", facit: "Separat facit",
            illustration: true },
    bilder: {}, referenser: [], forlaga: null, resultat: null, fokus: "",
    kontext: "start", niva: false, svarighet: 0, andrat: [],
    provId: 12, uppgifter: [
      { nr: 1, p: 2, t: "Beräkna $7 + 3 \\cdot 6$.", f: "$25$", niva: "E" },
      { nr: 2, p: 3, t: "Bestäm primitiv funktion till $2x$.", f: "$x^2 + C$",
        niva: "C" },
    ],
    ...extra,
  };
}

test("markeringarna stannar på skärmen", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);

  /* Pappret läraren just fått tillbaka ur en omskrivning: rubriken och första
     uppgiften är märkta, och prickarna sitter i deras kant (prickar.js). */
  const v = papper({ andrat: ["rubrik", "uppg1"], andradVid: Date.now() });
  const xml = await xmlUr(page, v);
  expect(xml.length).toBeGreaterThan(0);

  // Först: markeringen finns FAKTISKT på skärmens papper. Annars provar det
  // här testet ingenting alls — ett papper utan prickar har inga att riva.
  const pa = await page.evaluate(dok => {
    const bo = document.createElement("div");
    bo.style.cssText = "position:fixed;left:-30000px;top:0;width:900px";
    document.body.appendChild(bo);
    window.Blad.rita(bo, dok);
    const n = { prickar: bo.querySelectorAll(".aprick").length,
                andrade: bo.querySelectorAll(".andrad").length };
    bo.remove();
    return n;
  }, v);
  expect(pa.prickar).toBeGreaterThan(0);
  expect(pa.andrade).toBeGreaterThan(0);

  // Och sedan: ingenting av det gick in i bilden.
  for (const s of xml) {
    expect(s).not.toContain("aprick");
    expect(s).not.toContain("andrad");
    expect(s).not.toContain("data-lugn");
  }
});

test("lärarens inlagda bild följer med till PDF:en", async ({ page }) => {
  /* Bilden bor i webbläsarens dokument (v.bilder) och har aldrig funnits i
     provets JSON. LaTeX-vägen kunde därför inte sätta den — pappret läraren
     såg hade en bild, filen hon skrev ut hade en tom ruta. I DOM:en sitter
     den redan, så avritningen får den gratis. */
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);

  const v = papper({ bilder: { uppg1: BILD } });
  const xml = await xmlUr(page, v);
  expect(xml.length).toBeGreaterThan(0);
  // Bilden ligger som data-URI i taggen — den enda formen som överlever in i
  // ett <foreignObject> (en http-adress hämtas aldrig därifrån).
  expect(xml.some(s => s.indexOf(BILD.slice(0, 60)) >= 0)).toBe(true);
});

/* ── SÄTTNINGEN I BILDEN ÄR SÄTTNINGEN PÅ SKÄRMEN ──────────────────
   Avritningen bakar in arkens egna stilark men INTE styles.css: appens
   variabler hör inte till pappret. Det tog med sig en sak som gör det:
   `letter-spacing:-0.006em`, som styles.css sätter på `body` och som arken
   ärver utan att någonsin skriva den själva. Utan den blev varje rad en halv
   procent bredare i bilden — fyra pixlar, alltså ett ord — och bröt på ett
   annat ställe än på skärmen. På ett facit, som blad.js skruvar upp tills
   A4:an är exakt full, sköt varje extra rad den sista UNDER arkets nederkant:
   läraren fick ett facit med sista svaret avklippt.

   Mätningen: SVG:en avritningen bygger ritas i en iframe — ett eget dokument,
   precis som <foreignObject> är — och SATSYTANS höjd jämförs med originalets.
   Bryter texten likadant är höjderna lika på pixeln.

   Satsytan, inte `scrollHeight`: arket har fast höjd (794×1123) och göms det
   som spiller, så scrollHeight visar 1123 vare sig innehållet ryms eller
   svämmar över. Avståndet från arkets överkant till sista postens underkant
   växer däremot med varje rad som brutits om — och när det passerar arkets
   höjd är det precis den avklippta sista raden läraren såg. */
async function hojdparitet(page, v) {
  return page.evaluate(async dok => {
    /* Fånga SVG:en. Den byggs som en data-URI på ett <img> inne i
       BladBild.rastrera och lämnar aldrig modulen på något annat sätt. */
    const bild = Object.getOwnPropertyDescriptor(
      HTMLImageElement.prototype, "src");
    const fangat = [];
    Object.defineProperty(HTMLImageElement.prototype, "src", {
      configurable: true,
      get() { return bild.get.call(this); },
      set(varde) { fangat.push(varde); bild.set.call(this, varde); },
    });
    const bo = document.createElement("div");
    bo.style.cssText = "position:fixed;left:-30000px;top:0;width:900px";
    document.body.appendChild(bo);
    /* Bredden på en KÄND textrad, mätt med ett Range: det är glyfernas
       framflyttning och ingenting annat. Ombrytningen är följden av den, och
       att mäta följden hade gjort provet beroende av att just den här texten
       råkar hamna på gränsen. Probet är `.prtext` — arkets löptext, som INTE
       skriver någon egen `letter-spacing` och därför ärver den som frågan
       gäller. Rubrikerna duger inte: de sätter sin egen. */
    const bredden = ark => {
      const el = ark && ark.querySelector(".prtext");
      if (!el) return -1;
      const r = el.ownerDocument.createRange();
      r.selectNodeContents(el);
      return Math.round(r.getBoundingClientRect().width * 10) / 10;
    };
    let svg = "";
    let egen = 0;
    try {
      const trav = window.Blad.rita(bo, dok);
      await new Promise(r => setTimeout(r, 900));
      egen = bredden(trav.querySelector(".ark"));
      await window.BladBild.png(trav.querySelector(".blad"), { skala: 1 });
      const url = fangat.filter(
        s => String(s).indexOf("data:image/svg+xml") === 0).pop();
      if (!url) throw new Error("ingen SVG fångades — " + fangat.length
                                + " src-sättningar");
      svg = decodeURIComponent(url.slice(url.indexOf(",") + 1));
    } finally {
      Object.defineProperty(HTMLImageElement.prototype, "src", bild);
      bo.remove();
    }
    /* Samma SVG i ett eget dokument — utan appens styles.css, precis som i
       bilden — och arket mäts där. */
    const ram = document.createElement("iframe");
    ram.style.cssText = "position:fixed;left:-30000px;top:0;width:1000px;"
      + "height:1400px;border:0";
    document.body.appendChild(ram);
    ram.srcdoc = '<!doctype html><body style="margin:0">' + svg + "</body>";
    await new Promise(r => { ram.onload = r; });
    await new Promise(r => setTimeout(r, 500));
    const iBild = bredden(ram.contentDocument.querySelector(".ark"));
    ram.remove();
    return { egen, iBild };
  }, v);
}

test("bilden bryter raderna där skärmen bryter dem", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);

  /* Långa svar, så en halv procents bredd blir ett ombrutet ord. Korta svar
     hade inte avslöjat något: bryts ingen rad om är höjden lika ändå. */
  const lang = i => "Sätt in värdena i formeln och förenkla steg för steg "
    + `innan du svarar, annars försvinner faktorn $${i}x$ i mellanledet och `
    + "svaret blir en tiopotens fel — kontrollera alltid rimligheten mot "
    + "uppgiftens egen storleksordning innan du skriver ner det.";
  const v = papper({
    inst: { antal: 6, niva: "Blandat", facit: "Separat facit" },
    uppgifter: [1, 2, 3, 4, 5, 6].map(i => ({
      nr: i, p: 2, t: `Beräkna $${i}x + ${i}$ när $x = ${i}$.`, f: lang(i),
      niva: "E" })),
    losningsblad: true,
  });
  const { egen, iBild } = await hojdparitet(page, v);
  expect(egen).toBeGreaterThan(0);
  expect(iBild).toBe(egen);
});

test("bokens lösningsförslag följer INTE med till elevernas ark",
  async ({ page }) => {
    /* Bokuppgifternas svarsfacit står i samma trav på skärmen — läraren ser
       dem i förhandsvisningen — men är HENNES papper och laddas ner som egna
       filer (BladBild.boklos). Följde de med i elevernas ark hade eleverna
       fått lösningarna på köpet. */
    await fejka(page);
    await page.goto("/");
    await hydrerad(page);

    const v = papper({ bokuppg: {
      bok: "Matematik 5000+ 2c", sidor: "112–114", avsnitt: "derivatan",
      losning: { poster: [{ nr: 5211, niva: 1 }, { nr: 5223, niva: 2 }] } } });
    const bok = await page.evaluate(dok => {
      const bo = document.createElement("div");
      bo.style.cssText = "position:fixed;left:-30000px;top:0;width:900px";
      document.body.appendChild(bo);
      window.Blad.rita(bo, dok);
      const n = bo.querySelectorAll('.ark[data-form^="lo-bok"], '
        + '.ark[data-form="fe-bok"]').length;
      bo.remove();
      return n;
    }, v);
    test.skip(bok === 0, "dokumentet fick inga bokark att hålla utanför");

    const xml = await xmlUr(page, v);
    for (const s of xml) expect(s).not.toContain("lo-bok");
  });
