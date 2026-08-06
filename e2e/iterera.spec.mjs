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

async function fejka(page, { refine } = {}) {
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
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: refine || strom([{ type: "done", result: {
          id: "abc123def456", board: tavla("Omskriven tavla"), errors: [], rounds: 1 } }]) });
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
