import { expect, test } from "@playwright/test";

/* APPEN GISSAR MÅLET UR MENINGEN
 *
 * Läraren 2026-09-12: «När jag skriver generellt i chattfönstret, typ ändra
 * exempel 3, då tas saker bort från vänstra tavlan.» Spåret 2026-09-06 (2a)
 * mätte samma sak: ett rubrikvarv på tavla c94275cfc2d2 rörde 18 rutor, och
 * hon skrev «Helvete. Alltså, vad fan händer?».
 *
 * Mål-låset på servern slår bara till när en ruta är MARKERAD. Här prövas de
 * två halvorna som bara syns i gränssnittet:
 *
 *   1. Skriver hon «ändra exempel 3» utan att klicka sätter appen målet själv
 *      och säger att den gissade — chipet står där innan meningen går i väg.
 *   2. Begäran BÄR målet (`mal`/`malen`), och då tar servern den riktade vägen
 *      i stället för helomskrivningen. Kroppens form är oförändrad: ett mål
 *      ⇒ `mal`, flera ⇒ `mal` + `malen` (kassettregeln).
 *
 * Och gissningen är en gissning: tar hon bort chipet går varvet som förut.
 */

const SCHEMA = {
  schema: [{ dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 2c",
             klass: "NA25", sal: "P807" }],
  lov: [], poster: [],
};

/* En tavla i dramaturgins form: vänstern bär rubrik → agenda → divider →
   öppningsfråga → mening, högern tre exempel i var sin kolumn. Rubrikerna är
   UNDERSTRUKNA med flit — motorn ritar då en extra `.wb-element` som inte
   finns i JSON:en (blad.js jsonrutor), och en gissning som svepte med den hade
   släckt hela mål-låset på servern. */
const exempelkolumn = nr => ({
  weight: 1,
  sections: [
    { kind: "heading", text: `Exempel ${nr}`, size: 22,
      underline: { color: "red", amplitude: 2, thickness: 3, reserve: 14 } },
    { kind: "text", text: `Uppgift ${nr}: derivera funktionen.`, size: 19 },
    { kind: "math", latex: `f(x)=x^${nr}`, size: 21 },
  ],
});

const TAVLA = {
  title: "Derivatans definition",
  boards: [
    { name: "teori", width: 900, height: 780, chrome: "aluminium",
      padding: { top: 24, right: 26, bottom: 24, left: 30 },
      sections: [
        { kind: "heading", text: "Derivatans definition", size: 30,
          underline: { color: "red", amplitude: 2, thickness: 3, reserve: 18 } },
        { kind: "list", bullet: "–", size: 19,
          items: ["Ändringskvot", "Gränsvärde", "Räkna själva"] },
        { kind: "divider", width: 380 },
        { kind: "heading", text: "Vad är en lutning?", size: 22 },
        { kind: "text", text: "Ändringskvoten när h går mot noll.", size: 19 },
      ] },
    { name: "exempel", width: 1800, height: 780, chrome: "aluminium",
      padding: { top: 24, right: 26, bottom: 24, left: 30 },
      sections: [],
      columns: [exempelkolumn(1), exempelkolumn(2), exempelkolumn(3)] },
  ],
};

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

async function fejka(page) {
  const anrop = [];
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
  await page.route("**/api/planning/**", route => {
    const vag = new URL(route.request().url()).pathname;
    anrop.push({ vag, kropp: route.request().postDataJSON() });
    if (vag.endsWith("/render-report")) {
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "done", result: { ok: true, repaired: false } }]) });
    }
    if (vag.endsWith("/refine")) {
      /* Svaret är tavlan oförändrad: det som prövas här är vad KLIENTEN
         skickar, inte vad servern gör med det (det står i pytest). */
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "done", result: {
          id: "abc123def456", board: TAVLA, errors: [], rounds: 1,
          andrade: [] } }]) });
    }
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([
        { type: "done", result: { id: "abc123def456", board: TAVLA,
                                  errors: [], rounds: 1 } },
      ]) });
  });
  return anrop;
}

async function skrivTavla(page) {
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
}

async function oppnaCanvas(page) {
  await page.locator("#granska").click();
  await expect(page.locator("#g-falt")).toBeVisible({ timeout: 10_000 });
  // Tavlan ritas om i sin verkliga storlek när canvasen syns — id:na finns
  // först då, och gissningen letar efter dem.
  await expect(page.locator("#granskaskal .gdok .whiteboard"))
    .toHaveCount(2, { timeout: 15_000 });
  await expect(page.locator("#granskaskal .gdok [data-el]").first())
    .toBeVisible({ timeout: 15_000 });
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

const chips = page => page.locator("#g-mal .gmalchip");
const refines = anrop => anrop.filter(a => a.vag.endsWith("/refine"));

test("«ändra exempel 3» utan ett enda klick sätter målet och säger att det är en gissning",
  async ({ page }) => {
    const anrop = await fejka(page);
    await page.goto("/");
    await hydrerad(page);
    await skrivTavla(page);
    await oppnaCanvas(page);

    // INGEN markering. Precis som läraren gör: skriver bara i rutan.
    await page.locator("#g-falt").fill("ändra exempel 3");

    await expect(chips(page)).toHaveCount(1);
    await expect(chips(page)).toHaveAttribute("data-gissat", "");
    await expect(chips(page)).toContainText("Exempel 3");
    await expect(page.locator("#g-mal")).toHaveAttribute("data-satt", "");

    /* Rutorna gissningen valde är markerade i pappret, och de ligger allihop
       på HÖGERTAVLAN — det var vänsterns rutor som försvann.
       `poll` och inte en avläsning: tavlan ritar om sig själv när typsnitten
       är klara (blad.js nar/fonts.ready), markeringen följer med omritningen
       och sätts tillbaka av granskningens egen vakt en bildruta senare. */
    const markerade = () => page.evaluate(() => Array.from(
      document.querySelectorAll("#granskaskal .gdok .whiteboard"),
      b => Array.from(b.querySelectorAll("[data-mal]"), el => el.dataset.el)));
    /* TRE rutor, inte fyra: kolumnen är rubrik + UNDERSTRYKNING + text +
       formel, och understrykningen ritar motorn själv — den finns inte i
       tavlans JSON och servern kan inte slå upp den (blad.js jsonrutor). Ett
       mål servern inte hittar släcker hela mål-låset, alltså hade den fjärde
       rutan tyst gjort varvet till en helomskrivning igen. */
    await expect.poll(() => markerade().then(v => v[1].length),
                      { timeout: 15_000 }).toBe(3);
    await expect.poll(() => markerade().then(v => v[0].length),
                      { timeout: 15_000 }).toBe(0);

    await page.locator("#g-form").evaluate(f => f.requestSubmit());
    await expect.poll(() => refines(anrop).length, { timeout: 20_000 }).toBe(1);
    const kropp = refines(anrop)[0].kropp;
    expect(kropp.message).toBe("ändra exempel 3");
    /* Flera mål ⇒ `mal` (första) PLUS `malen`. Formen är densamma som ett
       klick ger — kassetterna hänger på den.
       Id:na är tredje kolumnens: rubrik, text, formel. tav15 (rubrikens
       understrykning) är INTE med — se poll-kommentaren ovan. */
    expect(kropp.mal.el).toBe("tav14");
    expect(kropp.malen.map(m => m.el)).toEqual(["tav14", "tav16", "tav17"]);
  });

test("gissningen går att ta bort — då gäller hela pappret igen, som förut",
  async ({ page }) => {
    const anrop = await fejka(page);
    await page.goto("/");
    await hydrerad(page);
    await skrivTavla(page);
    await oppnaCanvas(page);

    await page.locator("#g-falt").fill("ändra exempel 2");
    await expect(chips(page)).toHaveAttribute("data-gissat", "");
    /* ETT kryss tar hela gissningen, inte en ruta i taget: «exempel 2» är tre
       rutor men ETT mål, och att behöva klicka bort dem var för sig hade gjort
       ett förslag till ett arbete. */
    await page.locator("#g-mal .gmalchip .gmalkryss").click();
    await expect(chips(page)).toHaveCount(0);
    await expect(page.locator("#granskaskal .gdok [data-mal]")).toHaveCount(0);

    // Meningen står kvar i rutan och går i väg som förut — utan mål.
    await page.locator("#g-form").evaluate(f => f.requestSubmit());
    await expect.poll(() => refines(anrop).length, { timeout: 20_000 }).toBe(1);
    expect(refines(anrop)[0].kropp.mal).toBeUndefined();
    expect(refines(anrop)[0].kropp.malen).toBeUndefined();
  });

test("«skriv om vänstertavlan» låser hela teoritavlan, och inget av exemplen",
  async ({ page }) => {
    /* En hel tavla har inget eget id i serien — målet blir alla dess rutor,
       och bara så länge de ryms under taket. Det är den formen serverns
       mål-lås kan använda (lesson_board.malvagar → dokumentdiff.tavelvag). */
    const anrop = await fejka(page);
    await page.goto("/");
    await hydrerad(page);
    await skrivTavla(page);
    await oppnaCanvas(page);

    await page.locator("#g-falt").fill("skriv om vänstertavlan, den är rörig");
    await expect(chips(page)).toHaveCount(1);
    await expect(chips(page)).toContainText("Vänstertavlan");

    await page.locator("#g-form").evaluate(f => f.requestSubmit());
    await expect.poll(() => refines(anrop).length, { timeout: 20_000 }).toBe(1);
    const kropp = refines(anrop)[0].kropp;
    // Fem rutor på vänstern: rubrik, agenda, divider, öppningsfråga, mening.
    // Understrykningen under rubriken är motorns egen och går inte med.
    expect(kropp.malen.length).toBe(5);
    expect(kropp.malen.map(m => m.el))
      .toEqual(["tav0", "tav2", "tav3", "tav4", "tav5"]);
  });

test("en mening utan mål rör ingenting — fail-open, som förr",
  async ({ page }) => {
    const anrop = await fejka(page);
    await page.goto("/");
    await hydrerad(page);
    await skrivTavla(page);
    await oppnaCanvas(page);

    await page.locator("#g-falt").fill("gör hela tavlan luftigare");
    await expect(chips(page)).toHaveCount(0);
    await expect(page.locator("#g-mal")).not.toHaveAttribute("data-satt", "");

    await page.locator("#g-form").evaluate(f => f.requestSubmit());
    await expect.poll(() => refines(anrop).length, { timeout: 20_000 }).toBe(1);
    expect(refines(anrop)[0].kropp.mal).toBeUndefined();
  });
