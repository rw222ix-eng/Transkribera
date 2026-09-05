import { expect, test } from "@playwright/test";

/* ITERATIONEN I CANVAS
 *
 * «Gör uppgift 3 svårare» kördes av en regexhög i webbläsaren: den satte
 * x.svarighet = 1 och bytte några tal. Papperet SÅG omskrivet ut utan att
 * någon skrivit om det. Etapp 0.5 kopplade in refine-rutterna.
 *
 * Det som INTE fick ändras är hela poängen med canvas: nålarna, diffen och
 * källomviktningen. Ett klick på en källa skriver «Ta mer ur boken …» i
 * fältet — och det är hela meningen som blir prompten, för viktningen är
 * något läraren skrev, inte ett dolt reglage.
 */

const SCHEMA = {
  schema: [{ dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 2c",
             klass: "NA25", sal: "P807" }],
  lov: [], poster: [],
};

function tavla(rubrik) {
  const brade = (namn, bredd) => ({
    name: namn, width: bredd, height: 780, chrome: "aluminium",
    padding: { top: 24, right: 26, bottom: 24, left: 30 },
    sections: [{ kind: "heading", text: rubrik, size: 30 },
               { kind: "text", text: "Ändringskvoten när h går mot noll.", size: 19 }],
  });
  return { title: rubrik, boards: [brade("teori", 900), brade("exempel", 1800)] };
}

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

async function fejka(page, { refine, andrade, brade } = {}) {
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
    if (vag.endsWith("/refine")) {
      /* `andrade` är serverns egen diff av dokumentets JSON (Etapp: ärliga
         markeringar). Skickas den inte alls förblir svaret det gamla — och
         klienten ska då falla tillbaka på sin regexp, precis som förr. */
      const klar = { id: "abc123def456",
                     board: brade ? brade("Omskriven tavla") : tavla("Omskriven tavla"),
                     errors: [], rounds: 1 };
      if (andrade) klar.andrade = andrade;
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: refine || strom([{ type: "done", result: klar }]) });
    }
    if (vag.endsWith("/render-report")) return json(route, { ok: true, repaired: false });
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: "abc123def456",
        board: brade ? brade("Derivatans definition") : tavla("Derivatans definition"),
        errors: [], rounds: 1 } }]) });
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
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

test("en ändring i canvas går till servern och tavlan ritas om", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skrivTavla(page);
  await expect(page.locator("#dokument .tavruta")).toContainText("Derivatans definition");

  await oppnaCanvas(page);
  await page.locator("#g-falt").fill("Byt exempel 2 mot ett ur fysiken");
  await page.locator("#g-form").evaluate(f => f.requestSubmit());

  await expect.poll(() => anrop.some(a => a.vag.endsWith("/refine")),
                    { timeout: 20_000 }).toBe(true);
  expect(anrop.find(a => a.vag.endsWith("/refine")).kropp.message)
    .toBe("Byt exempel 2 mot ett ur fysiken");
  // Den omskrivna tavlan ersätter den gamla i pappret.
  await expect(page.locator(".gark .tavruta, #arkskal .tavruta").first())
    .toContainText("Omskriven tavla", { timeout: 20_000 });
});

test("nålen och ändringsräknaren står kvar", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skrivTavla(page);
  await oppnaCanvas(page);

  await page.locator("#g-falt").fill("Gör ingången kortare");
  await page.locator("#g-form").evaluate(f => f.requestSubmit());

  await expect(page.locator("#g-antal")).toHaveText("1 ändring", { timeout: 20_000 });
  await expect(page.locator(".gvarv .gnotnr").first()).toHaveText("1");
  await expect(page.locator(".gvarv .gfraga").first()).toHaveText("Gör ingången kortare");
});

test("ett klick på en källa skriver in viktningen — och den går med som prompt",
  async ({ page }) => {
    const anrop = await fejka(page);
    await page.goto("/");
    await hydrerad(page);
    // En förlaga är en källa: den syns i kvittot under dörrarna och följer
    // därmed med in i canvas som en klickbar bricka.
    await page.evaluate(() => {
      window.Dokument.sattForlaga({
        typ: "Arbetsblad", moment: "derivator", klass: "NA25",
        kurs: "Matematik, nivå 2c", datum: "2026-06-02", inst: {}, uppgifter: [],
      }, "samma nivå");
      window.Kallor.ritaKvitto();
    });
    await skrivTavla(page);
    await oppnaCanvas(page);

    const kallor = page.locator("#g-kallor .gkalla");
    await expect(kallor.first()).toBeVisible({ timeout: 10_000 });
    await kallor.first().click();
    const falt = page.locator("#g-falt");
    await expect(falt).toHaveValue(/Ta mer ur /);
    await falt.fill((await falt.inputValue()) + " och stryk sista exemplet");
    await page.locator("#g-form").evaluate(f => f.requestSubmit());

    await expect.poll(() => anrop.some(a => a.vag.endsWith("/refine")),
                      { timeout: 20_000 }).toBe(true);
    const msg = anrop.find(a => a.vag.endsWith("/refine")).kropp.message;
    expect(msg).toContain("Ta mer ur ");
    expect(msg).toContain("stryk sista exemplet");
  });

test("ett fel i omskrivningen blir ett besked, inte en tyst ändring", async ({ page }) => {
  const jsfel = [];
  await fejka(page);
  await page.goto("/");
  page.on("pageerror", e => jsfel.push(e.message));
  await hydrerad(page);
  await skrivTavla(page);
  await page.unroute("**/api/planning/**");
  await page.route("**/api/planning/**", route => route.fulfill({
    status: 409, contentType: "application/json",
    body: JSON.stringify({ error: "GPU:n är upptagen — försök igen strax." }) }));
  await oppnaCanvas(page);

  await page.locator("#g-falt").fill("Gör den svårare");
  await page.locator("#g-form").evaluate(f => f.requestSubmit());

  const ruta = page.locator(".gvarv .fsvar").first();
  await expect(ruta).toHaveAttribute("data-lage", "stoppad", { timeout: 20_000 });
  await expect(ruta).toContainText("upptagen");
  await expect(ruta.getByRole("button", { name: "Försök igen" })).toBeVisible();
  expect(jsfel, jsfel.join(" | ")).toEqual([]);
});

test("utan server kör canvas prototypens omskrivning som förut", async ({ page }) => {
  await page.route("**/api/var-kors", route => route.abort());
  const natanrop = [];
  await page.route("**/api/planning/**", route => { natanrop.push(route.request().url()); route.abort(); });
  await page.goto("/");
  await page.waitForFunction(() => document.documentElement.hasAttribute("data-server") === false);
  await skrivTavla(page);
  await oppnaCanvas(page);
  await page.locator("#g-falt").fill("Gör uppgift 3 svårare");
  await page.locator("#g-form").evaluate(f => f.requestSubmit());
  await expect(page.locator("#g-antal")).toHaveText("1 ändring", { timeout: 20_000 });
  expect(natanrop).toEqual([]);
});

// ── Elementet läraren pekade på ─────────────────────────────────────────────
// Klicket i pappret fastnade i webbläsaren: bara meningen gick till servern, så
// modellen fick gissa vilken av tjugo rutor «gör den kortare» gällde. Och
// markeringen gick inte att klicka bort igen.

async function valjElement(page, n = 0) {
  await page.locator("#g-valj").click();          // «Välj element» på
  const el = page.locator("#granskaskal .gdok [data-el]").nth(n);
  await el.click();
  return el;
}

test("elementet läraren pekade på följer med till servern", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skrivTavla(page);
  await oppnaCanvas(page);

  const el = await valjElement(page);
  const vantat = await el.evaluate(e => ({
    namn: e.dataset.namn,
    text: (e.textContent || "").replace(/\s+/g, " ").trim().slice(0, 300),
  }));
  // Målrutan visar vad ändringen gäller, med elementets eget namn.
  await expect(page.locator("#g-mal")).toHaveAttribute("data-satt", "");
  await expect(page.locator("#g-mal .gmaltext")).toHaveText(vantat.namn);

  await page.locator("#g-falt").fill("Gör den kortare");
  await page.locator("#g-form").evaluate(f => f.requestSubmit());
  await expect.poll(() => anrop.some(a => a.vag.endsWith("/refine")),
                    { timeout: 20_000 }).toBe(true);
  const kropp = anrop.find(a => a.vag.endsWith("/refine")).kropp;
  expect(kropp.message).toBe("Gör den kortare");
  expect(kropp.mal.namn).toBe(vantat.namn);
  // Innehållet är det som pekar ut rutan i dokumentets JSON — namnet finns inte där.
  expect(kropp.mal.innehall).toBe(vantat.text);
});

test("ett andra klick på samma element tar bort markeringen", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skrivTavla(page);
  await oppnaCanvas(page);

  const el = await valjElement(page);
  await expect(page.locator("#g-mal")).toHaveAttribute("data-satt", "");
  await expect(el).toHaveAttribute("data-mal", "");

  await el.click();                               // samma element igen
  await expect(page.locator("#g-mal")).not.toHaveAttribute("data-satt", "");
  await expect(el).not.toHaveAttribute("data-mal", "");
  // Och då gäller ändringen arket igen, inte den gamla rutan.
  await expect(page.locator("#g-falt")).toHaveAttribute("placeholder", /dokumentet|provet|lösningsförslaget/);
});

test("utan klick skickas inget mål — önskemålet gäller hela pappret", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skrivTavla(page);
  await oppnaCanvas(page);

  await page.locator("#g-falt").fill("Byt ut alla exemplen");
  await page.locator("#g-form").evaluate(f => f.requestSubmit());
  await expect.poll(() => anrop.some(a => a.vag.endsWith("/refine")),
                    { timeout: 20_000 }).toBe(true);
  expect(anrop.find(a => a.vag.endsWith("/refine")).kropp.mal).toBeUndefined();
});

/* ── ÄRLIGA MARKERINGAR ───────────────────────────────────────────
 * Vilka rutor som märks kom förr ur en regexp på lärarens mening — en
 * avläsning av önskemålet, inte av resultatet. Servern diffar nu dokumentets
 * JSON och skickar `andrade`; finns fältet styr det, annars gäller regexpen.
 */

const markerade = page => page.evaluate(() => Array.from(
  document.querySelectorAll("#granskaskal .gdok .andrad, #arkskal .andrad"),
  el => el.dataset.el).filter(Boolean));

test("serverns lista styr vilka rutor som märks", async ({ page }) => {
  await fejka(page, { andrade: ["tav2"] });
  await page.goto("/");
  await hydrerad(page);
  await skrivTavla(page);
  await oppnaCanvas(page);

  // Meningen nämner «uppgift 3» och «svårare» — regexpen hade målat uppg3 och
  // uppg5. Servern säger tav2, och det är servern som skrev om tavlan.
  await page.locator("#g-falt").fill("Gör uppgift 3 svårare");
  await page.locator("#g-form").evaluate(f => f.requestSubmit());
  await expect(page.locator("#g-antal")).toHaveText("1 ändring", { timeout: 20_000 });

  await expect.poll(() => markerade(page), { timeout: 20_000 })
    .toEqual(expect.arrayContaining(["tav2"]));
  expect(await markerade(page)).not.toContain("tav0");
  expect(await markerade(page)).not.toContain("uppg3");
});

test("en omskrivning som inte ändrade något märker ingen ruta", async ({ page }) => {
  await fejka(page, { andrade: [] });
  await page.goto("/");
  await hydrerad(page);
  await skrivTavla(page);
  await oppnaCanvas(page);

  await page.locator("#g-falt").fill("Gör den svårare");
  await page.locator("#g-form").evaluate(f => f.requestSubmit());
  // Varvet räknas ändå — läraren frågade, och frågan står i panelen.
  await expect(page.locator("#g-antal")).toHaveText("1 ändring", { timeout: 20_000 });
  expect(await markerade(page)).toEqual([]);
});

/* ── MARKERINGEN SOM LUGNAR SIG ─────────────────────────────────────
 * `.andrad` blinkade och låg sedan kvar för evigt — efter fem omskrivningar
 * lyste halva pappret. Nu är markeringen tydlig några sekunder och krymper till
 * en prick i kanten, med före/efter i en bubbla och en väg till varvets rad.
 *
 * Testerna frågar efter TILLSTÅNDET (`data-lugn`, `.aprick`) och aldrig efter
 * en animationstid: sviten kör med reducerad rörelse, så övergångarna finns
 * inte ens — men attributet ska sitta där ändå, för det sätts av en timer.
 */

async function skrivOm(page, mening) {
  await page.locator("#g-falt").fill(mening || "Skriv om rubriken");
  await page.locator("#g-form").evaluate(f => f.requestSubmit());
  await expect(page.locator("#g-antal")).toHaveText("1 ändring", { timeout: 20_000 });
}

/* `tav2` och inte `tav0`: tavlans FÖRSTA ruta är lektionens egen titelrad, som
   `tavlaSpec` injicerar ur planeringen — den ändras aldrig av en omskrivning.
   Rubriken som modellen faktiskt skriver om är andra brädets, tav2. */
const RUTA = '#granskaskal .gdok [data-el="tav2"]';
const prick = page => page.locator(RUTA + " .aprick").first();

test("markeringen krymper till en prick i kanten", async ({ page }) => {
  await fejka(page, { andrade: ["tav2"] });
  await page.goto("/");
  await hydrerad(page);
  await skrivTavla(page);
  await oppnaCanvas(page);
  await skrivOm(page);

  const el = page.locator(RUTA).first();
  await expect(el).toHaveClass(/andrad/, { timeout: 20_000 });
  // Prickens fäste finns från början; det som byts är akten.
  await expect(el.locator(".aprick")).toHaveCount(1);
  await expect(el).toHaveAttribute("data-lugn", "", { timeout: 20_000 });
});

test("hovra pricken visar före och efter", async ({ page }) => {
  await fejka(page, { andrade: ["tav2"] });
  await page.goto("/");
  await hydrerad(page);
  await skrivTavla(page);
  await oppnaCanvas(page);
  await skrivOm(page);

  const p = prick(page);
  await expect(p).toBeVisible({ timeout: 20_000 });
  await p.hover();
  const bubbla = page.locator(".aprickbubbla");
  await expect(bubbla).toBeVisible({ timeout: 10_000 });
  // Samma kapade par som panelens `.gdiff` — gamla rubriken överstruken, nya under.
  await expect(bubbla.locator(".gfore")).toContainText("Derivatans definition");
  await expect(bubbla.locator(".gefter")).toContainText("Omskriven tavla");
});

test("klick på pricken öppnar varvets rad i granskningen", async ({ page }) => {
  await fejka(page, { andrade: ["tav2"] });
  await page.goto("/");
  await hydrerad(page);
  await skrivTavla(page);
  await oppnaCanvas(page);
  await skrivOm(page);

  const rad = page.locator('.gvarv[data-id="1"]');
  await rad.evaluate(r => r.removeAttribute("data-pa"));   // börja från oval
  await prick(page).click();
  await expect(rad).toHaveAttribute("data-pa", "", { timeout: 10_000 });
});

test("bilden av tavlan bär inga markeringar", async ({ page }) => {
  await fejka(page, { andrade: ["tav2"] });
  await page.goto("/");
  await hydrerad(page);
  await skrivTavla(page);
  await oppnaCanvas(page);
  await skrivOm(page);

  // Bildproducenterna river markeringarna ur SIN kopia — pappret på skärmen
  // behåller sina. En kvarglommd prick hade blivit en ostylad knapp i PDF:en.
  const kvar = await page.evaluate(() => {
    const el = document.querySelector('#granskaskal .gdok [data-el="tav2"]');
    const kopia = window.Prickar.riv(el.cloneNode(true));
    return { prickar: kopia.querySelectorAll(".aprick").length,
             andrad: kopia.classList.contains("andrad"),
             pappret: el.querySelectorAll(".aprick").length };
  });
  expect(kvar).toEqual({ prickar: 0, andrad: false, pappret: 1 });
});

/* ── HELA SAMMANHANGET, OCH SNABBKNAPPARNA ─────────────────────────────────
 * Omskrivningen fick en enda mening och inget minne: tredje varvets «kortare
 * än så» hade inget «så» att gå efter. Nu följer lärarens tidigare önskemål
 * med, och rutans text SÅ SOM DEN SYNS (KaTeX skriver sin källa en gång till,
 * och det är den bilden läraren beskriver).
 *
 * Snabbknapparna går genom SAMMA väg som fritext — det är hela poängen med
 * dem, och det testet vaktar: ingen egen kodväg, ingen egen prompt.
 */

test("varvhistoriken följer med till servern", async ({ page }) => {
  const anrop = await fejka(page, { andrade: ["tav2"] });
  await page.goto("/");
  await hydrerad(page);
  await skrivTavla(page);
  await oppnaCanvas(page);

  await page.locator("#g-falt").fill("Byt exempel 2 mot ett ur fysiken");
  await page.locator("#g-form").evaluate(f => f.requestSubmit());
  await expect(page.locator("#g-antal")).toHaveText("1 ändring", { timeout: 20_000 });

  await page.locator("#g-falt").fill("Kortare än så");
  await page.locator("#g-form").evaluate(f => f.requestSubmit());
  await expect(page.locator("#g-antal")).toHaveText("2 ändringar", { timeout: 20_000 });

  const varv = anrop.filter(a => a.vag.endsWith("/refine"));
  expect(varv[0].kropp.historik).toBeUndefined();      // första varvet har inget
  expect(varv[1].kropp.historik).toEqual(["Byt exempel 2 mot ett ur fysiken"]);
  // Den nya meningen står som önskemål, inte som «redan gjort».
  expect(varv[1].kropp.message).toBe("Kortare än så");
});

test("elementets renderade text går med — det är den läraren ser", async ({ page }) => {
  const anrop = await fejka(page, { andrade: ["tav2"] });
  await page.goto("/");
  await hydrerad(page);
  await skrivTavla(page);
  await oppnaCanvas(page);

  const el = await valjElement(page);
  const sett = await el.evaluate(e => (e.textContent || "").replace(/\s+/g, " ").trim());
  await page.locator("#g-falt").fill("Gör den kortare");
  await page.locator("#g-form").evaluate(f => f.requestSubmit());
  await expect.poll(() => anrop.some(a => a.vag.endsWith("/refine")),
                    { timeout: 20_000 }).toBe(true);
  const mal = anrop.find(a => a.vag.endsWith("/refine")).kropp.mal;
  expect(mal.renderat).toBe(sett.slice(0, 600));
});

test("snabbknapparna visas bara när ett element är valt", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await skrivTavla(page);
  await oppnaCanvas(page);

  const rad = page.locator("#g-snabb");
  await expect(rad).toBeHidden();
  await valjElement(page);
  await expect(rad).toBeVisible();
  await expect(rad.locator(".gsnabbknapp")).toHaveText(
    ["Kortare", "Enklare", "Svårare", "Byt sammanhang"]);

  // Krysset i målrutan tar bort valet — och knapparna med det.
  await page.locator("#g-malx").click();
  await expect(rad).toBeHidden();
});

test("en snabbknapp skickar sin mening samma väg som fritext", async ({ page }) => {
  const anrop = await fejka(page, { andrade: ["tav2"] });
  await page.goto("/");
  await hydrerad(page);
  await skrivTavla(page);
  await oppnaCanvas(page);

  const el = await valjElement(page);
  const namn = await el.evaluate(e => e.dataset.namn);
  await page.locator("#g-snabb .gsnabbknapp", { hasText: "Svårare" }).click();

  await expect.poll(() => anrop.some(a => a.vag.endsWith("/refine")),
                    { timeout: 20_000 }).toBe(true);
  const kropp = anrop.find(a => a.vag.endsWith("/refine")).kropp;
  // En färdig svensk mening — och SAMMA kropp som fritexten bygger: målet med,
  // den renderade texten med. Ingen egen kodväg betyder ingen egen form.
  expect(kropp.message).toContain("svårare");
  expect(kropp.mal.namn).toBe(namn);
  expect(typeof kropp.mal.renderat).toBe("string");
  // …och varvet står i tråden som vilken ändring som helst.
  await expect(page.locator(".gvarv .gfraga").first()).toHaveText(kropp.message);
});


/* ── BARNEN I TAVELRADEN ────────────────────────────────────────────────────
 * Läraren 2026-09-05: «jag kan inte markera allt heller, allting är inte
 * markerbart». Sedan dramaturgin ligger figur, begreppsrader, formler och
 * Vanligt fel i EN `row`, och motorn strök wb-element på barnen — raden var en
 * enda klump. Nu bär barnen `wb-del` och ett eget id ur förälderns (`tav1.1`),
 * och den serien måste vara SAMMA som serverns (app/dokumentdiff.py).
 */

function tavlaMedRad(rubrik) {
  const brade = (namn, bredd) => ({
    name: namn, width: bredd, height: 780, chrome: "aluminium",
    padding: { top: 24, right: 26, bottom: 24, left: 30 },
    sections: [
      { kind: "heading", text: rubrik, size: 30 },
      { kind: "row", gap: 24, children: [
        { kind: "math", latex: "a^2 + b^2 = c^2", size: 22 },
        { kind: "math", latex: "f(x) = 2x", size: 22 },
        { kind: "text", text: "Vanligt fel:", size: 18 },
      ] },
    ],
  });
  return { title: rubrik, boards: [brade("teori", 900), brade("exempel", 1800)] };
}

test("ett barn i tavelraden går att markera, och nålen sitter på barnet",
  async ({ page }) => {
    const anrop = await fejka(page, { brade: tavlaMedRad, andrade: ["tav1.1"] });
    await page.goto("/");
    await hydrerad(page);
    await skrivTavla(page);
    await oppnaCanvas(page);
    await page.locator("#g-valj").click();

    const rad = page.locator('#granskaskal .gdok [data-el="tav1"]');
    const barn = page.locator('#granskaskal .gdok [data-el="tav1.1"]');
    await expect(rad).toHaveCount(1);
    await expect(barn).toHaveCount(1);          // formeln är en egen ruta
    await barn.click();
    await expect(barn).toHaveAttribute("data-mal", "");
    await expect(rad).not.toHaveAttribute("data-mal", "");

    await page.locator("#g-falt").fill("Skriv den med a i stället");
    await page.locator("#g-form").evaluate(f => f.requestSubmit());
    await expect.poll(() => anrop.some(a => a.vag.endsWith("/refine")),
                      { timeout: 20_000 }).toBe(true);
    // Id:t når servern — det är det som gör mål-låset möjligt.
    const kropp = anrop.find(a => a.vag.endsWith("/refine")).kropp;
    expect(kropp.mal.el).toBe("tav1.1");

    // Nålen sitter på BARNET och inte på raden, också efter omritningen.
    await expect(page.locator('[data-el="tav1.1"] > .gpin').first())
      .toBeVisible({ timeout: 20_000 });
    await expect(page.locator('[data-el="tav1"] > .gpin')).toHaveCount(0);
    // …och serverns egen diff märker barnet.
    await expect.poll(() => page.locator('[data-el="tav1.1"].andrad').count(),
                      { timeout: 20_000 }).toBeGreaterThan(0);
  });
