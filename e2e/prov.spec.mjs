import { expect, test } from "@playwright/test";
import { forbiNivavarningen } from "./larardag.mjs";

/* PROVET OCH ARBETSBLADET PÅ RIKTIGT
 *
 * Arken sattes ur appens egen uppgiftsbank (innehall.js) — samma avsnitt gav
 * samma prov varje gång, och «8 uppgifter» betydde bara att listan kapades.
 * Etapp 0.4 kopplade in provgeneratorn. Fyra saker måste hålla:
 *
 *   1. Arket som ritas bär SERVERNS uppgifter, i frontendens form: nummer,
 *      poäng, nivå, svarsyta och facit.
 *   2. Poängen på en uppgift med deluppgifter är delarnas summa — den ligger
 *      aldrig på båda ställena.
 *   3. Arbetsbladets facitläge styr vad som skrivs ut, precis som förut.
 *   4. Godkännandet bygger PDF:en, och ett misslyckande säger det rakt ut.
 */

const SCHEMA = {
  schema: [{ dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 2c",
             klass: "NA25", sal: "P807" }],
  lov: [], poster: [],
};

/** Prov-JSON som app/exam_spec.py definierar den. */
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
      losning: "$f(2) = 4$", bedomning: "+1 E ansats, +2 C metod, +1 A motivering." },
    { del: "C", formaga: "P", typ: "redovisning", poang: [0, 0, 0],
      text: "Derivera funktionerna.",
      losning: "", bedomning: "",
      deluppgifter: [
        { poang: [2, 0, 0], text: "$g(x) = x^3$", losning: "$3x^2$", bedomning: "+2 E" },
        { poang: [0, 3, 0], text: "$h(x) = (2x+1)^4$", losning: "$8(2x+1)^3$", bedomning: "+3 C" },
      ] },
  ],
};

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

async function fejka(page, { generate, approve } = {}) {
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
  await page.route("**/api/exams/**", route => {
    const vag = new URL(route.request().url()).pathname;
    anrop.push({ vag, kropp: route.request().postDataJSON() });
    if (vag.endsWith("/approve")) {
      /* Fälten är rutten's egna: `pdf` och `tex` (routes_exam approve). Mocken
         sa förut `pdf_path` — DB-kolumnens namn — och då fick klientens fel
         fält aldrig något att falla på. Namnen hålls mot riktiga rutten av
         test_routes_exam::test_approve_svaret_bar_falten_plan_js_laser. */
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: approve || strom([{ type: "done",
          result: { id: 9, pdf: "C:/Transkriberingar/prov/derivator.pdf",
                    tex: "C:/Transkriberingar/prov/derivator.tex", errors: [] } }]) });
    }
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: generate || strom([
        { type: "log", msg: "Skriver provet …" },
        { type: "done", result: {
          id: 9, exam: EXAM, typ: "prov", status: "utkast", errors: [], rounds: 1,
          granser: { E: 4, C: 7, A: 9 }, summor: { totalt: 11 } } },
      ]) });
  });
  return anrop;
}

async function skriv(page, typ, moment = "derivator") {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(([t, m]) => {
    window.SattLage(t);
    // Klass och kurs kommer normalt ur lektionen man klickat i veckan.
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
  }, [typ, moment]);
  await page.locator("#skriv").click();
  /* «derivator» är 3c-innehåll och kursen här är 2c — plan.js varnar för det
     innan den anropar, och första klicket blir alltså varningen. Se
     larardag.mjs och nivavarning.spec.mjs; provet som prövas här är rutten, inte
     ämnesplanen. */
  await forbiNivavarningen(page);
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

test("provet på arket är serverns uppgifter, i arkets form", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skriv(page, "Prov");
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  const gen = anrop.find(a => a.vag.endsWith("/generate"));
  expect(gen.kropp.kurs).toBe("Matematik, nivå 2c");
  expect(gen.kropp.typ).toBe("prov");

  // Uppgifterna översatta till arkets form: nivå ur poängvektorn, svarsyta ur
  // uppgiftstypen, poängen summerad över deluppgifterna.
  const arket = await page.locator("#dokument .pruppg").allTextContents();
  expect(arket.length).toBe(3);
  expect(arket[0]).toContain("2 p");
  expect(arket[1]).toContain("4 p");          // 1+2+1
  expect(arket[2]).toContain("5 p");          // 2 + 3 ur deluppgifterna
  // Kravet står som på pappret: «Endast svar krävs.» på rutinuppgiften,
  // «Fullständig lösning krävs.» på de två andra. Skärmen skrev förut ordet
  // «lösblad» litet i marginalen — samma sak sagd med andra ord på en annan
  // plats än lärarens förlaga, som appen numera sätter provet efter.
  await expect(page.locator("#dokument .pruppg .prkrav")).toHaveCount(3);
  await expect(page.locator(
    "#dokument .pruppg .prkrav", { hasText: "Fullständig lösning krävs." }
  )).toHaveCount(2);
  // Deluppgifterna står som a) och b).
  await expect(page.locator("#dokument .pruppg .prdel[data-avdelad] li")).toHaveCount(2);
});

test("prototypens uppgifter kommer inte tillbaka vid en ändring", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skriv(page, "Prov");
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  const fore = await page.locator("#dokument .pruppg .prtext").allTextContents();
  expect(fore[0]).toContain("derivatan");
  // nyVersion räknar om uppgifterna vid varje ändring — serverns lista måste
  // överleva den.
  await page.evaluate(() => window.Blad.uppgifter({
    typ: "Prov", provId: 9, moment: "derivator",
    uppgifter: [{ nr: 1, p: 2, t: "Serverns uppgift", niva: "E", ut: "kort" }],
    inst: { antal: 6 } }));
  const efter = await page.evaluate(() => window.Blad.uppgifter({
    typ: "Prov", provId: 9, moment: "derivator",
    uppgifter: [{ nr: 1, p: 2, t: "Serverns uppgift", niva: "E", ut: "kort" }],
    inst: { antal: 6 } }));
  expect(efter).toHaveLength(1);
  expect(efter[0].t).toBe("Serverns uppgift");
});

test("arbetsbladet går på samma rutt men med sin egen typ", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skriv(page, "Arbetsblad", "primitiva funktioner");
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
  expect(anrop.find(a => a.vag.endsWith("/generate")).kropp.typ).toBe("arbetsblad");
});

test("godkännandet bygger PDF:en och säger till", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skriv(page, "Prov");
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  await page.locator("#godkann").click();
  await expect.poll(() => anrop.some(a => a.vag.endsWith("/approve"))).toBe(true);
  /* «PDF» ensamt räcker inte: den misslyckade toasten säger också «PDF». Just
     den luckan lät klienten läsa fel fält ur svaret utan att något sa ifrån —
     kvittot för LYCKAT bygge måste vara det som prövas. */
  await expect(page.locator(".toast").last())
    .toContainText("utskriven som PDF", { timeout: 15_000 });
  // …och sökvägen ska ha nått dokumentet i Sparat, inte bara toasten.
  await expect.poll(() => page.evaluate(
    () => window.Dokument.sparade().map(d => d.pdf).filter(Boolean)[0] || ""))
    .toContain(".pdf");
});

test("en PDF som inte går att bygga sägs rakt ut", async ({ page }) => {
  await fejka(page, {
    approve: strom([{ type: "done", result: { id: 9, pdf: null,
      tex: "C:/Transkriberingar/prov/derivator.tex",
      errors: ["Tectonic: Undefined control sequence"] } }]),
  });
  await page.goto("/");
  await hydrerad(page);
  await skriv(page, "Prov");
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });
  await page.locator("#godkann").click();
  await expect(page.locator(".toast").last()).toContainText("tex", { timeout: 15_000 });
});

test("ett prov som inte gick att skriva blir ett besked", async ({ page }) => {
  const jsfel = [];
  await fejka(page, {
    generate: strom([{ type: "done", result: {
      id: null, exam: null, errors: ["balansen gick inte ihop"], rounds: 3 } }]),
  });
  await page.goto("/");
  page.on("pageerror", e => jsfel.push(e.message));
  await hydrerad(page);
  await skriv(page, "Prov");

  const ruta = page.locator("#skrivstatus .fsvar");
  await expect(ruta).toHaveAttribute("data-lage", "stoppad", { timeout: 15_000 });
  await expect(page.locator("#dokument")).toBeHidden();
  expect(jsfel, jsfel.join(" | ")).toEqual([]);
});

test("gruppuppgiften går samma väg och bär sitt upplägg", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => {
    window.SattLage("Gruppuppgift");
    const satt = (id, v) => {
      const e = document.querySelector(id);
      e.value = v;
      e.dispatchEvent(new Event("change", { bubbles: true }));
    };
    satt("#p-kurs", "Matematik, nivå 2c");
    satt("#p-klass", "NA25");
    const f = document.querySelector("#moment");
    f.value = "derivator";
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  });
  await page.locator("#skriv").click();
  await forbiNivavarningen(page);          // «derivator» i 2c — se helpern
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  const gen = anrop.find(a => a.vag.endsWith("/generate"));
  expect(gen.kropp.typ).toBe("gruppuppgift");
  // Upplägget är väljarnas, inte modellens: namnrader, tid och redovisning.
  expect(gen.kropp.grupp.elever).toBeGreaterThanOrEqual(2);
  expect(gen.kropp.grupp.elever).toBeLessThanOrEqual(5);
  expect(gen.kropp.grupp.langd_min).toBeGreaterThan(0);
  expect(["muntligt", "skriftligt", "poster"]).toContain(gen.kropp.grupp.redovisning);
  // Fyra rutor är formen, inte en väljare.
  expect(gen.kropp.antal).toBe(4);
});


/* ══════ LÄRARENS SEX ANMÄRKNINGAR 2026-08-22 ══════
   Hon läste igenom ett skarpt prov och hittade fyra saker där SKÄRMEN sa något
   annat än PDF:en. Provet nedan är byggt för att fånga just dem: en C-uppgift
   som ligger i Del A (nivå ≠ del), en enhet som bär TeX, och två delar som ska
   numreras 1…k och k+1…n. */
const EXAM_DELAR = {
  titel: "Prov · Area och tillväxt",
  kurs: "Matematik, nivå 2c", klass: "NA25", datum: "2026-09-03", tid_min: 80,
  hjalpmedel: "Del B utan digitala verktyg. Del C med räknare.",
  uppgifter: [
    { del: "B", formaga: "B", typ: "rutin", poang: [2, 0, 0],
      text: "Ange arean av en kvadrat med sidan $4$ cm.", enhet: "cm$^2$",
      losning: "$16$", bedomning: "+2 E" },
    { del: "B", formaga: "P", typ: "rutin", poang: [1, 0, 0],
      text: "Derivera $f(x) = 5x$.", enhet: "$f'(x) =$",
      losning: "$5$", bedomning: "+1 E" },
    /* HÄR SATT BUGGEN: en C-tung uppgift i den räknarfria delen. Skärmen delade
       på NIVÅN och sköt den till Del B, medan PDF:en (som grupperar på `del`)
       lade den i Del A — «Del A: uppgift 1, 2 och 7». */
    { del: "B", formaga: "R", typ: "resonemang", poang: [0, 2, 1],
      text: "Har Jaana rätt? Motivera utan räknare.",
      losning: "Nej.", bedomning: "+2 C, +1 A" },
    { del: "C", formaga: "PL", typ: "problem", poang: [1, 2, 0],
      text: "Bestäm största volymen med hjälp av ditt digitala verktyg.",
      enhet: "cm$^3$", losning: "$2000$", bedomning: "+1 E, +2 C" },
    { del: "C", formaga: "M", typ: "problem", poang: [0, 0, 2],
      text: "Undersök modellens giltighet.",
      losning: "Den bryter samman.", bedomning: "+2 A" },
  ],
};

test("delarna är dokumentets, numreringen löper och enheten är matematik",
  async ({ page }) => {
    await fejka(page, { generate: strom([{ type: "done", result: {
      id: 9, exam: EXAM_DELAR, typ: "prov", status: "utkast", errors: [],
      rounds: 1, granser: { total: 8, E: { minst: 2 }, C: { minst: 4, varav_ca: 2 },
                            A: { minst: 6, varav_a: 1 } },
      summor: { total: 8, e: 4, c: 4, a: 3 } } }]) });
    await page.goto("/");
    await hydrerad(page);
    await skriv(page, "Prov");
    await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

    /* DELARNA. Del A ska bära uppgift 1–3 och Del B uppgift 4–5 — trots att
       uppgift 3 är C/A-tung. Delen handlar om HJÄLPMEDEL, nivån om svårighet. */
    const nrPa = form => page.locator(`#dokument .ark[data-form='${form}'] .prnr`)
      .evaluateAll(el => el.map(e => e.firstChild.nodeValue.trim()));
    expect(await nrPa("pr1b")).toEqual(["1.", "2.", "3."]);
    expect(await nrPa("pr1c")).toEqual(["4.", "5."]);
    // Provtabellen på försättsbladet säger samma spann.
    const rader = await page.locator("#dokument .prmeta tr").allTextContents();
    expect(rader.join(" ")).toContain("Uppgift 1–3");
    expect(rader.join(" ")).toContain("Uppgift 4–5");

    /* ENHETEN ÄR MATEMATIK. «cm$^2$» trycktes ordagrant på svarsraden, med
       dollartecken och allt, medan PDF:en satte cm². */
    const enheter = page.locator("#dokument .prenhet");
    await expect(enheter.first()).toHaveText(/^cm/);
    expect(await enheter.first().textContent()).not.toContain("$");
    await expect(enheter.first().locator(".mat")).toHaveCount(1);
    // KaTeX har renderat den — rutan är inte tom.
    expect(await enheter.first().locator(".mat").innerHTML()).not.toBe("");

    /* OBS-RUTAN ÄR BORTA och VÄNDMÄRKET är papprets: kursivt «Vänd» i nedre
       högra hörnet, inte «Fortsätter på nästa sida» centrerat. */
    await expect(page.locator("#dokument .probs")).toHaveCount(0);
    const vand = page.locator("#dokument .prslut[data-vand]");
    if (await vand.count()) {
      await expect(vand.first()).toHaveText("Vänd");
      const stil = await vand.first().evaluate(el => {
        const s = getComputedStyle(el);
        return { stil: s.fontStyle, just: s.justifyContent };
      });
      expect(stil.stil).toBe("italic");
      expect(stil.just).toBe("flex-end");
    }
    // Delens sista ark bär slutraden i stället.
    await expect(page.locator("#dokument .prslut[data-slut]").first())
      .toContainText("Slut på del");
  });

test("«Föreslå antal» räknar antalet uppgifter ur provtiden", async ({ page }) => {
  /* Lärarens beställning: diagnosen dimensioneras redan ur en lektion, och
     provet ska kunna göra samma sak. Räkningen bor på servern (den behöver
     skelettet); knappen sätter steppern och säger vad det kostar i poäng. */
  await fejka(page);
  await page.route("**/api/exams/foreslag-antal*", route => {
    const u = new URL(route.request().url());
    expect(u.searchParams.get("tid")).toBeTruthy();
    expect(u.searchParams.get("typ")).toBe("prov");
    return route.fulfill({ status: 200, contentType: "application/json",
      body: JSON.stringify({ antal: 11, poang: 24, tid: 95, takt: 3.5 }) });
  });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => {
    window.SattLage("Prov");
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  });
  const antalrad = page.locator('.typrad[data-id="antal"]');
  // Takten står framme, med lärarens tal.
  await expect(page.locator('.typrad[data-id="nartid"] .taktfalt'))
    .toHaveValue("3,5");
  await expect(antalrad.locator(".steppervarde")).toHaveText("6");
  await antalrad.locator("[data-foreslag]").click();
  await expect(antalrad.locator(".steppervarde"))
    .toHaveText("11", { timeout: 5_000 });
});
