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

async function fejka(page, { refine, andrade } = {}) {
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
      const klar = { id: "abc123def456", board: tavla("Omskriven tavla"),
                     errors: [], rounds: 1 };
      if (andrade) klar.andrade = andrade;
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: refine || strom([{ type: "done", result: klar }]) });
    }
    if (vag.endsWith("/render-report")) return json(route, { ok: true, repaired: false });
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: "abc123def456", board: tavla("Derivatans definition"),
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
