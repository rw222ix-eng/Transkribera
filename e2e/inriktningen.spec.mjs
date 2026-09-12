import { expect, test } from "@playwright/test";
import * as L from "./larardag.mjs";

/* KLASSENS YRKE ÄR ETT FÄLT I KLASSPROFILEN
 *
 * Lärarens fynd 2026-09-12: «Superappen är asdålig på att komma upp med egna
 * förslag.» Exempel 3 på en tavla om division av bråk för en byggklass blev en
 * abstrakt tallinje («En halv meter list, 5 lika bitar. Vad visar märket?»).
 * Det hon skrev själv i stället var färgburkarna: 3/4 liter per burk, 4½ liter
 * vägg, sex burkar, och kontrollen 6 · 3/4 = 4½. Prompten visste inte vad
 * klassen går, och det var det enda den behövde veta.
 *
 * Tre påståenden prövas, i den ordning felet uppstod:
 *
 *   1. Fältet finns där klassprofilen redigeras, och det SKRIVS: raden är
 *      kortets enda som inte lärs, för det står ingenstans i det appen ser
 *      vilket program eleverna går.
 *   2. Det sparas som resten av profilen (PUT /api/klassprofil) och överlever
 *      en omladdning. Låg det bara i webbläsaren dog det med cachen.
 *   3. Det NÅR SERVERN med skrivjobbet, per klass. Och bara då: en klass utan
 *      inriktning ska ge exakt den begäran som gick i väg innan fältet fanns
 *      (kassettregeln; tests/test_inriktning.py bevakar prompten, det här
 *      bevakar kroppen).
 *
 * Bara generatorrutten fejkas. Resten är den riktiga servern, precis som i
 * hjalpmedlen.spec.mjs.
 */

const KLASS = "NA25";
const YRKE = "Bygg och anläggning";

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

const TAVLA = {
  title: "Division av bråk",
  boards: [{ width: 900, height: 780, name: "vanster", sections: [] },
           { width: 1800, height: 780, name: "hoger", sections: [] }],
};

/** Fejkar tavelgeneratorn och samlar kropparna. */
async function fejkaTavla(page) {
  const anrop = [];
  await page.route("**/api/planning/generate", route => {
    anrop.push(route.request().postDataJSON());
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: "p1", board: TAVLA, errors: [], rounds: 1 } }]) });
  });
  return anrop;
}

/** Öppnar klassprofilen för en klass: klassremsan filtrerar, Profil fäller ut.
 *  Panelen ligger under veckan och är ihopfälld som förval. */
async function oppnaProfilen(page, klass = KLASS) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.locator("#klassrad .klasschip", { hasText: klass }).first().click();
  await page.locator("#klassrad .profilknapp").click();
  await expect(page.locator("#klassprofil")).toBeVisible();
}

const faltet = page =>
  page.locator('#klassprofil .kprrad[data-id="inriktning"] input');

/* ── 1 · Raden i kortet ─────────────────────────────── */

test("inriktningen står i klassprofilen som ett skrivet fält", async ({ page }) => {
  await L.fejkatMoln(page);
  await L.oppna(page);
  await oppnaProfilen(page);

  const rad = page.locator('#klassprofil .kprrad[data-id="inriktning"]');
  await expect(rad.locator(".kprnamn")).toHaveText("Inriktning");
  await expect(faltet(page)).toHaveValue("");
  // Tom ruta säger vad den är till för, inte bara att den är tom.
  await expect(faltet(page)).toHaveAttribute("placeholder", /Bygg/);
  await expect(rad.locator(".kprstod")).toContainText("klassens program");
  // Den lärs inte, alltså finns ingen «Glöm»-knapp att trycka på: det man
  // skrivit tar man bort genom att sudda i rutan.
  await expect(rad.locator("[data-glom]")).toHaveCount(0);
});

/* ── 2 · Det sparas ────────────────────────────────── */

test("yrket sparas i klassprofilen och överlever en omladdning",
     async ({ page }) => {
  const anrop = L.spana(page);
  await L.fejkatMoln(page);
  await L.oppna(page);
  await oppnaProfilen(page);

  await faltet(page).fill(YRKE);
  await faltet(page).press("Enter");

  const putar = () => L.traff(anrop, "/api/klassprofil")
    .filter(a => a.metod === "PUT" && a.kropp && a.kropp[KLASS]);
  await expect.poll(() => putar().length).toBeGreaterThan(0);
  expect(putar().pop().kropp[KLASS].inriktning).toBe(YRKE);

  /* …och det ligger i DATABASEN, inte bara i webbläsaren. localStorage töms
     först, annars svarar den på frågan i serverns ställe: minnet av en klass
     låg där en gång och dog med webbläsarprofilen, och det är just det som är
     lagat (profil.js «UR SERVERN»). `L.oppna` går inte att köra en gång till:
     klockan är redan fryst, och Playwright installerar den en gång per
     sida. */
  await page.evaluate(() => { try { localStorage.clear(); } catch (e) {} });
  await L.efterOmladdning(page);
  await expect.poll(() => page.evaluate(
    k => (window.Profil.minne()[k] || {}).inriktning, KLASS)).toBe(YRKE);
  await oppnaProfilen(page);
  await expect(faltet(page)).toHaveValue(YRKE);
});

/* ── 3 · Det når servern ───────────────────────────── */

test("yrket följer med tavlans skrivjobb, per klass", async ({ page }) => {
  const anrop = await fejkaTavla(page);
  await L.fejkatMoln(page);
  await L.oppna(page);
  await oppnaProfilen(page);
  await faltet(page).fill(YRKE);
  await faltet(page).press("Enter");

  await L.skriv(page, { typ: "Tavla", moment: "division av bråk",
                        klass: KLASS, kurs: "Matematik, nivå 2c" });
  await expect.poll(() => anrop.length).toBe(1);
  expect(anrop[0].inriktning).toBe(YRKE);
});

test("en klass utan inriktning skickar ingen nyckel alls", async ({ page }) => {
  const anrop = await fejkaTavla(page);
  await L.fejkatMoln(page);
  await L.oppna(page);
  /* KASSETTREGELN. Nyckeln ska inte FINNAS: servern lägger sin promptrad på
     ett ifyllt fält, och en tom sträng hade varit ett svar. Klassen är en
     annan än den ovan, för profilen är per klass och delar bas med resten av
     sviten. */
  await L.skriv(page, { typ: "Tavla", moment: "derivatans definition",
                        klass: "NA24",
                        kurs: "Matematik – fortsättning, nivå 1c" });
  await expect.poll(() => anrop.length).toBe(1);
  expect("inriktning" in anrop[0]).toBe(false);
});
