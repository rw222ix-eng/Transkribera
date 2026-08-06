import { expect, test } from "@playwright/test";

/* MOLNVÄGEN
 *
 * Transkriberingen ligger inte längre på datorn: ljudet går till OpenAI
 * (gpt-transcribe) och bara tidsstämplarna räknas fram här. Två saker måste
 * därför hålla, och båda går att förstöra utan att något syns:
 *
 * 1. Frontenden hittar servern och kör på riktigt i stället för prototypens
 *    klocka — annars ser allt ut att fungera medan ingenting transkriberas.
 * 2. Texten som läraren läser under körningen säger vart ljudet tar vägen.
 *    Den stod en gång «ljudet körs på din GPU — du kan gå». Den meningen får
 *    aldrig komma tillbaka, för nu är den falsk.
 *
 * Själva molnanropet spärras: sviten ska inte kosta pengar och inte behöva en
 * nyckel. Det som testas är kedjan fram till och från anropet.
 */

/** SSE-svar som serverns /api/transcribe skulle ha strömmat. */
function strom(handelser) {
  return handelser.map(h => `data: ${JSON.stringify(h)}\n\n`).join("");
}

const KORNING = strom([
  { type: "log", msg: "Delar upp ljudet vid naturliga pauser ..." },
  { type: "progress", pct: 8 },
  { type: "log", msg: "Skickar 3 delar till gpt-transcribe ..." },
  { type: "delta", text: "Vi tittar på derivatans definition. " },
  { type: "progress", pct: 45 },
  { type: "kostnad", usd: 0.07, minuter: 15.1 },
  { type: "log", msg: "Sätter tidsstämplar lokalt (cuda) ..." },
  { type: "progress", pct: 60 },
  { type: "progress", pct: 98 },
  { type: "done", result: {
      id: "h1", files: [], folder: "C:/Transkriberingar/x", media: "C:/x/lektion.wav",
      transcript: [{ start: 0.4, end: 3.2, text: "Vi tittar på derivatans definition." }] } },
]);

async function koaEnFil(page) {
  await page.evaluate(() => {
    laggTill("lektion.wav", "12:04", "C:/downloads/lektion.wav");
  });
}

test("appen ser servern och kör den riktiga vägen", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-server", "");
  const varKors = await page.evaluate(() => window.API.varKors);
  expect(varKors.moln.transkribering.modell).toBe("gpt-transcribe");
  expect(varKors.moln.transkribering.pris_per_minut).toBe(0.0045);
});

test("körningen säger att ljudet går till OpenAI — aldrig att det stannar", async ({ page }) => {
  await page.route("**/api/transcribe", route =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body: KORNING }));
  await page.goto("/");
  await page.waitForFunction(() => window.API && window.API.pa);
  await koaEnFil(page);

  await page.locator("#starta").click();

  const fot = page.locator("#korkvar");
  await expect(fot).toContainText("OpenAI");
  await expect(fot).not.toContainText("din GPU");

  // Molnsteget är märkt som moln, och de lokala stegen är det inte.
  const moln = page.locator('#progresslista .fas[data-moln], #progresslista .fas').filter({
    hasText: "Skickar ljudet till OpenAI" });
  await expect(moln).toHaveCount(1);
  await expect(page.locator("#progresslista")).toContainText("Sätter tidsstämplar mot ljudet");

  // Kostnaden är OpenAI:s egen siffra, inte en gissning ur filens längd.
  await expect(fot).toContainText("$0.07", { timeout: 15_000 });
  await expect(page.locator("#klarruta")).toBeVisible();
  await expect(page.locator("#klartext")).toContainText("gpt-transcribe");
});

test("transkriptet från servern blir appens transkript", async ({ page }) => {
  await page.route("**/api/transcribe", route =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body: KORNING }));
  await page.goto("/");
  await page.waitForFunction(() => window.API && window.API.pa);
  await koaEnFil(page);
  await page.locator("#starta").click();
  await expect(page.locator("#klarruta")).toBeVisible({ timeout: 15_000 });

  const rader = await page.evaluate(() => window.transkript);
  expect(rader[0][1]).toContain("derivatans definition");
  expect(rader[0][0]).toBe("00:00");        // tidsstämpeln följer med in i appen
});

test("en ström som tar slut utan svar blir ett besked, inte ett JS-fel", async ({ page }) => {
  // Servern kan dö mitt i, eller anslutningen brytas. Då finns inget done-event
  // — och det får inte bli «Cannot read properties of null» i konsolen.
  const jsfel = [];
  page.on("pageerror", e => jsfel.push(e.message));
  await page.route("**/api/transcribe", route =>
    route.fulfill({ status: 200, contentType: "text/event-stream",
                    body: strom([{ type: "progress", pct: 45 }]) }));
  await page.goto("/");
  await page.waitForFunction(() => window.API && window.API.pa);
  await koaEnFil(page);
  await page.locator("#starta").click();

  await expect(page.locator("#korvarningar .varnruta")).toContainText("slutade svara");
  expect(jsfel).toEqual([]);
});

test("nätet som dör mitt i körningen blir ett besked, inte en bar som står still",
  async ({ page, context }) => {
    /* Regressionen från 746ef20 fast på riktigt: strömmen bryts på
       transportnivå mitt i en körning. Kravet är detsamma som när den tar slut
       utan done — ett besked med en väg vidare, ingen klarruta, inget JS-fel.
       Wifi som glappar mitt i en 70-minuterslektion är inte ett kantfall. */
    const jsfel = [];
    page.on("pageerror", e => jsfel.push(e.message));
    let bryt;
    const brutet = new Promise(r => { bryt = r; });
    await page.route("**/api/transcribe", async route => {
      await brutet;
      await route.abort("internetdisconnected");
    });
    await page.goto("/");
    await page.waitForFunction(() => window.API && window.API.pa);
    await koaEnFil(page);
    await page.locator("#starta").click();

    // Körningen är igång: fasen syns innan nätet försvinner.
    await expect(page.locator("#progresslista")).toContainText("Skickar ljudet till OpenAI");
    await context.setOffline(true);
    bryt();

    await expect(page.locator("#korvarningar .varnruta")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("#klarruta")).toBeHidden();
    expect(jsfel, jsfel.join(" | ")).toEqual([]);
    await context.setOffline(false);
  });

test("ett fel från servern blir en varning läraren kan agera på", async ({ page }) => {
  await page.route("**/api/transcribe", route =>
    route.fulfill({ status: 400, contentType: "application/json",
                    body: JSON.stringify({ error: "Ingen OpenAI-nyckel. Lägg in den under Inställningar.",
                                           kod: "nyckel_saknas" }) }));
  await page.goto("/");
  await page.waitForFunction(() => window.API && window.API.pa);
  await koaEnFil(page);
  await page.locator("#starta").click();

  const varning = page.locator("#korvarningar .varnruta");
  await expect(varning).toBeVisible();
  await expect(varning).toContainText("OpenAI-nyckel");
  // Tom utdata är aldrig ett godtagbart utfall — klarrutan får inte visas.
  await expect(page.locator("#klarruta")).toBeHidden();
});
