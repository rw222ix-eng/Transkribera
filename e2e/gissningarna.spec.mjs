import { expect, test } from "@playwright/test";

/* VECKOMATTEN SOM EGENSKAPER (Etapp 4.5)
 *
 * ISO-veckorna styr veckovyn, terminsvyn, «nästa skolvecka» och varje
 * dokuments plats, och de går sönder tyst. Kända datum är prövade
 * (kalendern.spec.mjs); här körs hela år mot en oberoende referens.
 *
 * Filnamnsgissningen (app.js gissaDatum/gissaTid) prövades också här. Den
 * togs bort med Transkribera-fliken 2026-10-07.
 *
 * Fallen genereras med en FAST seed: en röd körning går att köra om exakt.
 * Hypothesis finns bara i Python, och funktionerna bor i webbläsaren — så
 * generatorn är skriven här, med samma tanke: många fall, få påståenden, och
 * krympning görs för hand ur utskriften när något faller.
 */

const SCHEMA = { schema: [], lov: [], poster: [] };

const json = (route, kropp) => route.fulfill({
  status: 200, contentType: "application/json", body: JSON.stringify(kropp) });

async function fejka(page) {
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern());

// ── ISO-veckorna ─────────────────────────────────────────────────────────

test("veckonumren håller ISO över fyra hela år", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);

  const fel = await page.evaluate(() => {
    /* Oberoende referens: ISO 8601 räknat på torsdagen i samma vecka. Den
       skrivs här, inte i appen, så ett fel i appens implementation inte kan
       göra sig självt rätt. */
    const isoRef = iso => {
      const d = new Date(iso + "T12:00:00Z");
      const dag = (d.getUTCDay() + 6) % 7;                 // mån=0
      d.setUTCDate(d.getUTCDate() - dag + 3);              // torsdagen
      const forsta = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
      const fdag = (forsta.getUTCDay() + 6) % 7;
      forsta.setUTCDate(forsta.getUTCDate() - fdag + 3);
      return 1 + Math.round((d - forsta) / (7 * 86400000));
    };
    const brister = [];
    const start = new Date(Date.UTC(2024, 0, 1));
    for (let i = 0; i < 4 * 366; i++) {
      const d = new Date(start.getTime() + i * 86400000);
      const iso = d.toISOString().slice(0, 10);
      const nr = window.Kalender.veckonr(iso);
      if (nr !== isoRef(iso)) { brister.push(`${iso}: ${nr} ≠ ${isoRef(iso)}`); continue; }
      // Måndagen i veckan är en måndag, ligger bakåt och i samma vecka.
      const man = window.Kalender.mandagen(iso);
      const md = new Date(man + "T12:00:00Z");
      if (md.getUTCDay() !== 1) brister.push(`${iso}: ${man} är ingen måndag`);
      if (man > iso) brister.push(`${iso}: måndagen ${man} ligger framåt`);
      if ((new Date(iso + "T12:00:00Z") - md) / 86400000 > 6) {
        brister.push(`${iso}: måndagen ${man} ligger mer än sex dagar bort`);
      }
      if (window.Kalender.veckonr(man) !== nr) {
        brister.push(`${iso}: måndagen hamnar i en annan vecka`);
      }
      if (brister.length > 20) break;
    }
    return brister;
  });
  expect(fel).toEqual([]);
});

test("varje vecka har sju dagar med samma nummer — också vecka 53",
  async ({ page }) => {
    await fejka(page);
    await page.goto("/");
    await hydrerad(page);

    const fel = await page.evaluate(() => {
      const brister = [];
      // Fyra årsskiften i rad, inklusive 2026→2027 (v53) och 2020→2021 (v53).
      for (const start of ["2020-12-21", "2021-12-27", "2026-12-21", "2027-12-27"]) {
        const nr = window.Kalender.veckonr(start);
        for (let i = 0; i < 7; i++) {
          const d = new Date(start + "T12:00:00Z");
          d.setUTCDate(d.getUTCDate() + i);
          const iso = d.toISOString().slice(0, 10);
          if (window.Kalender.veckonr(iso) !== nr) {
            brister.push(`${iso} bytte vecka mitt i veckan (${start} = v${nr})`);
          }
          if (window.Kalender.mandagen(iso) !== start) {
            brister.push(`${iso} pekar på fel måndag (${window.Kalender.mandagen(iso)} ≠ ${start})`);
          }
        }
      }
      return brister;
    });
    expect(fel).toEqual([]);
  });
