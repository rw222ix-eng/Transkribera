import { expect, test } from "@playwright/test";

/* PROVETS CENTRALA INNEHÅLL STÅR REDAN I KALENDERN
 *
 * Läraren skriver in Gy25-punkterna i provhändelsens beskrivning när hon lägger
 * terminen — «Logaritmer», «Andragradsekvationer», en rad per punkt. Synken
 * känner igen dem och lagrar KODERNA (aldrig texten, se
 * calendar_google.centralt_innehall_ur_text och _PROVETS_CI_MIGRATION i
 * app/db.py). Skapar hon sedan provet i appen ska punkterna redan vara
 * ikryssade: hon har svarat på frågan en gång.
 *
 * Det som prövas här är förvalet och dess GRUND — noten som säger varifrån
 * punkterna kom och hur många rader som inte kändes igen. Fyra punkter av sex
 * ser precis lika färdigt ut som sex, och läraren är den enda som kan se
 * skillnaden; utan noten är förvalet ett påstående i stället för ett förslag.
 *
 * Varje påstående om förvalet har sitt motstycke i frånvaro: en post utan
 * koder, en annan klass, en annan typ. Ett förval som alltid slår till är lika
 * trasigt som ett som aldrig gör det.
 */

/* Kalenderposterna som synken lämnat dem. `ci` är koderna, `ci_okant` raderna
   som såg ut att påstå något men inte kändes igen. Den tomma listan på det
   andra provet är ett SVAR — «beskrivningen är läst, den nämnde inget centralt
   innehåll» — och inte samma sak som en post utan nyckeln. */
const POSTER = [
  { datum: "2026-10-01", tid: "09:05–10:20", titel: "NA25: PROV 1 (kap 1 och 2)",
    klass: "NA25", slag: "prov", kalla: "schema",
    ci: ["G25-M2C-ALG-2", "G25-M2C-ALG-6", "G25-M2C-ALG-7"], ci_okant: 2 },
  { datum: "2026-10-15", tid: "09:05–10:20", titel: "NA25: PROV 2",
    klass: "NA25", slag: "prov", kalla: "schema", ci: [] },
  { datum: "2026-10-20", tid: "09:05–10:20", titel: "NA25: Diagnos 2",
    klass: "NA25", slag: "diagnos", kalla: "schema",
    ci: ["G25-M2C-STA-2"] },
  { datum: "2026-11-10", tid: "09:00–12:00", titel: "NP MAT nivå 2c NA25",
    klass: "NA25", slag: "np", kalla: "schema" },
];

const SCHEMA = { schema: [], lov: [], poster: POSTER, innehall: [] };

async function fejka(page, { poster = POSTER } = {}) {
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, { ...SCHEMA, poster }));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
  await page.route("**/api/bocker**", route => json(route, { bocker: [] }));
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

/** Ställer lektionens klass, kurs och dag utan att gå via veckorutan. */
const staller = (page, { klass, kurs, datum }) => page.evaluate(v => {
  const satt = (id, varde) => {
    const f = document.querySelector(id);
    if (f.tagName === "SELECT" && ![...f.options].some(o => o.value === varde
                                                      || o.textContent === varde)) {
      f.appendChild(Object.assign(document.createElement("option"),
                                  { textContent: varde }));
    }
    f.value = varde;
    f.dispatchEvent(new Event("change", { bubbles: true }));
  };
  satt("#p-klass", v.klass);
  satt("#p-kurs", v.kurs);
  satt("#p-datum", v.datum);
}, { klass, kurs, datum });

async function planeringen(page, datum = "2026-10-01") {
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await staller(page, { klass: "NA25", kurs: "Matematik, nivå 2c", datum });
}

const valda = page => page.evaluate(() => window.GyVal.valda());

/* Stapeln viker ihop de steg man inte står i. Gy-väljaren och dess not bor i
   steg 4 («Upplägg — och skriv»), så en gömd not kan vara gömd av fel skäl —
   och då är «inte synlig» ett grönt test utan innehåll. */
const tillUpplagget = page => page.evaluate(() => {
  window.PlanSteg.las(4, false);
  window.PlanSteg.gaTill(4);
});

/** Väljer typen och fäller upp steget noten står i. */
async function skriver(page, typ) {
  await page.evaluate(t => window.SattLage(t), typ);
  await tillUpplagget(page);
}

/* ── 1 · Förvalet ───────────────────────────────────── */

test("provets punkter är ikryssade innan läraren rört väljaren", async ({ page }) => {
  await fejka(page);
  await planeringen(page);
  await skriver(page, "Prov");

  /* De tre koderna i beskrivningen, översatta till etiketterna läraren ser.
     Översättningen sker i den nivå väljaren står på — kursen i steg 1 pekade ut
     den — och det är samma väg valet går tillbaka som koder när provet skrivs. */
  expect((await valda(page)).sort()).toEqual(
    ["Andragradsekvationer", "Logaritmer", "Rotekvationer"]);
  await expect(page.locator("#gychips")).toContainText("Logaritmer");
});

test("noten säger varifrån punkterna kom och vad som inte kändes igen",
  async ({ page }) => {
    await fejka(page);
    await planeringen(page);
    await skriver(page, "Prov");

    const not = page.locator("#gykalender");
    await expect(not).toBeVisible();
    /* Rubriken utan klassnamnet: klassen står redan i steg 1. */
    await expect(not).toHaveText(
      "Ur kalendern: 3 punkter (PROV 1 (kap 1 och 2)) · 2 rader kändes inte igen");
  });

test("förvalet är ett förval — läraren kryssar om och noten ljuger inte",
  async ({ page }) => {
    await fejka(page);
    await planeringen(page);
    await skriver(page, "Prov");
    await page.evaluate(() => window.GyVal.vaxla("Logaritmer"));
    expect(await valda(page)).not.toContain("Logaritmer");
    /* Punkterna KOM ur kalendern, och det är fortfarande sant efter att hon
       ändrat: noten talar om ursprunget, inte om vad som står kryssat nu. */
    await expect(page.locator("#gykalender")).toBeVisible();
  });

/* Förvalet körs om när lektionen ändras — inte bara vid typbytet. Då måste
   omkörningen också respektera att läraren hunnit kryssa om, annars är
   «förvalet är ett förval» sant bara till nästa datumändring. */
test("kryssen överlever att provdagen flyttas", async ({ page }) => {
  await fejka(page);
  await planeringen(page);
  await skriver(page, "Prov");
  await page.evaluate(() => window.GyVal.vaxla("Logaritmer"));
  expect(await valda(page)).not.toContain("Logaritmer");

  // Provet flyttas till en dag med ETT eget innehåll i kalendern.
  await staller(page, { klass: "NA25", kurs: "Matematik, nivå 2c",
                        datum: "2026-10-20" });
  await expect.poll(() => valda(page)).not.toContain("Logaritmer");
  await expect.poll(() => valda(page)).not.toContain("Normalfördelning");
});

test("förvalet följer med när provdagen flyttas — om läraren inte rört kryssen",
  async ({ page }) => {
    await fejka(page);
    await planeringen(page, "2026-10-15");   // posten utan koder: inget förval
    await skriver(page, "Prov");
    expect(await valda(page)).toEqual([]);

    await staller(page, { klass: "NA25", kurs: "Matematik, nivå 2c",
                          datum: "2026-10-01" });
    await expect.poll(async () => (await valda(page)).sort())
      .toEqual(["Andragradsekvationer", "Logaritmer", "Rotekvationer"]);
    await expect(page.locator("#gykalender")).toContainText("Ur kalendern: 3 punkter");
  });

test("diagnosen tar kalenderns punkter framför hela kursen", async ({ page }) => {
  /* Diagnosen kryssar annars i ALLA nivåns punkter — det är dess definition.
     Men har läraren skrivit vad just den här diagnosen mäter är det hennes
     svar, och det går före. */
  await fejka(page);
  await planeringen(page, "2026-10-20");
  await skriver(page, "Diagnos");
  expect(await valda(page)).toEqual(["Normalfördelning"]);
  await expect(page.locator("#gykalender")).toContainText("Ur kalendern: 1 punkt");
});

/* ── 2 · Frånvaron ──────────────────────────────────── */

test("prov utan igenkänt innehåll rör inte väljaren", async ({ page }) => {
  /* Posten den 15 oktober ÄR läst — `ci` är en tom lista — och det betyder
     precis att beskrivningen inte nämnde något centralt innehåll. Då står
     dagens beteende kvar: tomt val, ingen not, ingenting påhittat. */
  await fejka(page);
  await planeringen(page, "2026-10-15");
  await skriver(page, "Prov");
  expect(await valda(page)).toEqual([]);
  await expect(page.locator("#gykalender")).toBeHidden();
});

test("en post utan ci-nyckeln alls är osynkad och säger ingenting", async ({ page }) => {
  /* Skillnaden mellan «läst utan träff» och «aldrig läst» bär hela vägen ut:
     posterna som skrevs före v22 saknar nyckeln, och ett förval som tolkade dem
     som tomma hade påstått något ingen kollat. */
  await fejka(page, { poster: [{ ...POSTER[0], ci: undefined, ci_okant: undefined }] });
  await planeringen(page);
  await skriver(page, "Prov");
  expect(await valda(page)).toEqual([]);
  await expect(page.locator("#gykalender")).toBeHidden();
});

test("provet som står på en annan klass rör inte den här", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await staller(page, { klass: "SA25", kurs: "Matematik, nivå 2c",
                        datum: "2026-10-01" });
  await skriver(page, "Prov");
  expect(await valda(page)).toEqual([]);
  await expect(page.locator("#gykalender")).toBeHidden();
});

test("noten hör till mätningen — en tavla på provdagen får den inte",
  async ({ page }) => {
    await fejka(page);
    await planeringen(page);
    await skriver(page, "Prov");
    await expect(page.locator("#gykalender")).toBeVisible();

    await skriver(page, "Tavla");
    await expect(page.locator("#gykalender")).toBeHidden();
  });

test("nationella provet ger inget förval — det är inte lärarens att skriva",
  async ({ page }) => {
    await fejka(page);
    await planeringen(page, "2026-11-10");
    await skriver(page, "Prov");
    expect(await valda(page)).toEqual([]);
    await expect(page.locator("#gykalender")).toBeHidden();
  });
