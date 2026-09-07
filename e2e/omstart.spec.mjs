import { expect, test } from "@playwright/test";

/* «BÖRJA OM» OCH SERVERNS NEJ — två fynd ur panelen 2026-09-07
 *
 * Läraren öppnar planeringen från ett kalenderkort («+ Mer»). Kortet sätter
 * klass, kurs, dag och tid, och remsan högst upp säger «Planerar Matematik,
 * nivå 1c · NA26F · tis 8 sep 12:20–13:40».
 *
 *   1. «Börja om» ska rensa UTKASTET (typ, källor, upplägg) men lämna
 *      lektionen kvar. Förut nollade knappen också de fyra lektionsfälten
 *      medan remsan stod kvar, och nästa Skriv gick i väg med tom kurs:
 *      servern svarade 400 «välj en kurs» (routes_exam generate).
 *   2. Svarar servern 400 ska felet STÅ i skrivrutan och i en toast. Förut
 *      försvann statusraden tyst, och läraren trodde att jobbet körde.
 */

const SCHEMA = {
  schema: [
    // Tisdag (dag 2) — klockan fryses på tisdag v37, så kortet ligger i veckan.
    { dag: 2, tid: "12:20–13:40", kurs: "Matematik, nivå 1c", klass: "NA26F", sal: "P807" },
  ],
  lov: [],
  poster: [],
};

const json = (route, kropp) => route.fulfill({
  status: 200, contentType: "application/json", body: JSON.stringify(kropp) });

/** Datagrunden fejkad; `generate` avgör vad provrutten svarar. */
async function fejka(page, { generate } = {}) {
  const anrop = [];
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/bocker", route => json(route, []));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
  await page.route("**/api/exams/**", route => {
    const vag = new URL(route.request().url()).pathname;
    anrop.push({ vag, kropp: route.request().postDataJSON() });
    if (vag.endsWith("/generate") && generate) return generate(route);
    return json(route, {});
  });
  return anrop;
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.PlanKo && window.Dokument);

/** Öppnar planeringen från kortet. «+ Mer» finns bara på ett kort som redan
 *  bär papper; klicket på kortets överkant går samma väg (plankon.fyll sätter
 *  de fyra fälten), så det är den vägen som prövas. */
async function franKortet(page, opts) {
  const anrop = await fejka(page, opts);
  await page.clock.install({ time: new Date("2026-09-08T08:00:00") });  // tisdag v37
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await expect(page.locator("#schemagrid .lekt")).toHaveCount(1);
  await page.locator("#schemagrid .lekt .lekttopp").click();
  await expect(page.locator("#p-klass")).toHaveValue("NA26F");
  await expect(page.locator("#p-kurs")).toHaveValue("Matematik, nivå 1c");
  await expect(page.locator("#p-datum")).toHaveValue("2026-09-08");
  await expect(page.locator("#p-tid")).toHaveValue("12:20–13:40");
  return anrop;
}

/** Ställer in ett prov och trycker Skriv — utan nivåvarningen (momentet
 *  hör till kursen). */
async function skrivProv(page) {
  await page.evaluate(() => {
    window.SattLage("Prov");
    const f = document.querySelector("#moment");
    f.value = "algebraiska uttryck";
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  });
  await page.locator("#skriv").click();
  /* Nivåvarningen (nivavarning.spec.mjs) stoppar första klicket när momentet
     inte hör till kursen. Knappen är beviset: släckt betyder att anropet gick. */
  if (!(await page.locator("#skriv").isDisabled())) {
    const varning = page.locator(".toast").filter({ hasText: "Tryck igen för att skriva ändå" });
    if (await varning.count()) await page.locator("#skriv").click();
  }
}

test("«Börja om» behåller lektionen kortet satte", async ({ page }) => {
  const anrop = await franKortet(page);
  // Något att rensa: ett moment och en typ som inte är förvalet.
  await page.evaluate(() => {
    window.SattLage("Prov");
    const f = document.querySelector("#moment");
    f.value = "algebraiska uttryck";
    f.dispatchEvent(new Event("input", { bubbles: true }));
  });

  await page.locator(".omstartknapp").click();

  // Utkastet är rensat …
  await expect(page.locator("#moment")).toHaveValue("");
  // … men lektionen står kvar, i fälten OCH i remsan.
  await expect(page.locator("#p-klass")).toHaveValue("NA26F");
  await expect(page.locator("#p-kurs")).toHaveValue("Matematik, nivå 1c");
  await expect(page.locator("#p-datum")).toHaveValue("2026-09-08");
  await expect(page.locator("#p-tid")).toHaveValue("12:20–13:40");
  await expect(page.locator("#vy-planering .konrad")).toBeVisible();
  await expect(page.locator("#vy-planering .konrad")).toContainText("NA26F");
  await expect(page.locator(".toast").last()).toContainText("lektionen står kvar");

  // Och nästa Skriv bär kursen — det var den tomma kursen som gav 400.
  await skrivProv(page);
  await expect.poll(() => anrop.some(a => a.vag.endsWith("/generate"))).toBe(true);
  const gen = anrop.find(a => a.vag.endsWith("/generate"));
  expect(gen.kropp.kurs).toBe("Matematik, nivå 1c");
  expect(gen.kropp.klass).toBe("NA26F");
});

test("«Börja om» utan lektion tömmer fälten som förut", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => {
    const e = document.querySelector("#p-klass");
    e.value = "NA26F";
    e.dispatchEvent(new Event("change", { bubbles: true }));
  });

  await page.locator(".omstartknapp").click();

  await expect(page.locator("#p-klass")).toHaveValue("");
  await expect(page.locator(".toast").last()).toHaveText("Allt rensat — välj lektionen i veckan igen");
});

test("serverns 400 står i skrivrutan och i en toast", async ({ page }) => {
  await franKortet(page, {
    generate: route => route.fulfill({ status: 400, contentType: "application/json",
      body: JSON.stringify({ error: "välj en kurs" }) }),
  });

  await skrivProv(page);

  const ruta = page.locator("#skrivstatus");
  await expect(ruta).toBeVisible();
  /* Felet står i SAMMA rad som förloppet stod i (fraga.js felade), inte i
     en liten textrad under en rad som vikts in. */
  const rad = ruta.locator(".fsmal[data-fel] .fsmaltext");
  await expect(rad).toHaveText("välj en kurs", { timeout: 10_000 });
  await expect(rad).toBeVisible();
  await expect(ruta.locator(".fatgard button", { hasText: "Försök igen" })).toBeVisible();
  await expect(page.locator(".toast").last()).toContainText("välj en kurs");
  // Skriv går att trycka igen — inget jobb «kör».
  await expect(page.locator("#skriv")).toBeEnabled();
});
