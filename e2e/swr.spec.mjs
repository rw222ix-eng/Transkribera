import { expect, test } from "@playwright/test";

/* CACHAT FÖRST, FÄRSKT STRAX EFTER (api.js jsonSWR)
 *
 * Appen är en enda sida, och andra gången läraren öppnar den är svaret på
 * schemat nästan alltid detsamma som förra gången. SWR-
 * lagret ritar därför det cachade svaret SYNKRONT och hämtar färskt i bakgrunden.
 *
 * Det är svårt att se att det fungerar med nät: en snabb server ser precis ut
 * som en cache. Testerna nedan HÅLLER FAST rutten — begäran går i väg men
 * svarar aldrig — och frågar vad appen har under tiden. Har den svaret ändå
 * kom det ur cachen, för det kan inte ha kommit någon annanstans ifrån.
 * (Arkivlistan, /api/lessons och /api/history, prövades också här. Den togs
 * bort med arkivet 2026-10-07.)
 *
 * Det andra som måste hålla är gränsen mot prototypen: Claude Design kör samma
 * filer utan server, och lärarens riktiga listor får aldrig ritas där. Svarar
 * sonderingen (/api/var-kors) inte ska cachen vara borta, inte bara oanvänd.
 */

const SWR = "swr1:";

/** Öppna appen och vänta tills den är LADDAD — samma villkor som offline.spec. */
async function laddad(page) {
  await page.goto("/");
  await page.waitForFunction(() =>
    window.Kalender && window.Kalender.franServern() && window.Dokument
      && window.API && window.API.pa, null, { timeout: 30_000 });
}

/** Håller fast en rutt: begäran går i väg, svaret kommer aldrig inom testets tid. */
async function hallFast(page, monster) {
  await page.route(monster, async route => {
    await new Promise(r => setTimeout(r, 30_000));
    await route.abort().catch(() => {});
  });
}

/** Skriver en post i swr-cachen i lagrets eget format: «<ms>|<json>». */
async function saCache(page, vag, data) {
  await page.evaluate(([nyckel, json]) => {
    localStorage.setItem(nyckel, Date.now() + "|" + json);
    localStorage.setItem("swr1:$server", "1");
  }, [SWR + vag, JSON.stringify(data)]);
}

test("veckan står där innan /api/schema svarat", async ({ page }) => {
  await laddad(page);
  const harSchema = await page.evaluate(() => !!localStorage.getItem("swr1:/api/schema"));
  expect(harSchema, "schemat cachades aldrig vid första besöket").toBe(true);

  await hallFast(page, "**/api/schema");
  await page.goto("/");

  /* franServern() är kalenderns egen fråga «har det här kommit ur servern?».
     Med rutten fastspänd kan svaret bara vara sant om cachen gav det. */
  await page.waitForFunction(() => window.Kalender && window.Kalender.franServern(),
    null, { timeout: 8_000 });
});

test("cachen ritas aldrig när ingen server svarar", async ({ page }) => {
  await laddad(page);
  await saCache(page, "/api/dokument", [{ id: 7 }]);

  /* Sonderingen spärras: det här ÄR prototypläget (Claude Design har ingen
     server alls). Lärarens riktiga papper får inte ligga kvar i cachen och
     kunna synas nästa gång. */
  await page.route("**/api/var-kors", route => route.abort());
  await page.goto("/");
  await page.waitForFunction(() => !!(window.API && window.API.redo));
  await page.evaluate(() => window.API.redo);          // sonderingen klar, på ett eller annat sätt
  expect(await page.evaluate(() => window.API.pa)).toBe(false);

  const kvar = await page.evaluate(() =>
    Object.keys(localStorage).filter(k => k.indexOf("swr1:") === 0));
  expect(kvar, `cachen låg kvar i prototypläget: ${kvar.join(", ")}`).toEqual([]);
});

test("en skrivning glömmer det cachade svaret", async ({ page }) => {
  await laddad(page);
  await saCache(page, "/api/dokument", [{ id: 7 }]);
  await saCache(page, "/api/dokument/7", { id: 7 });

  /* Rutten fejkas: det som prövas är att json() glömmer, inte vad servern gör. */
  await page.route("**/api/dokument/7", route =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" }));

  const kvar = await page.evaluate(async () => {
    await window.API.json("/api/dokument/7", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    return Object.keys(localStorage).filter(k => k.indexOf("swr1:/api/dokument") === 0);
  });
  expect(kvar, `skrivningen lämnade kvar cachade svar: ${kvar.join(", ")}`).toEqual([]);
});

test("cachen håller sig under sitt tak", async ({ page }) => {
  await laddad(page);
  /* Taket är ~1 M tecken. Lådan rymmer 5 MB och figurcachen bor i samma låda —
     ett SWR-lager som äter upp den hade tagit figurerna med sig. */
  const stort = await page.evaluate(async () => {
    const bit = JSON.stringify("x".repeat(50_000));
    for (let i = 0; i < 30; i++) {
      try { localStorage.setItem("swr1:/api/fyllnad" + i, (Date.now() + i) + "|" + bit); }
      catch (e) { break; }                 // lådan tog slut före taket: gott nog
    }
    /* En riktig skrivning städar: hämta något och låt lagret lägga svaret. */
    await window.API.jsonSWR("/api/var-kors", {});
    return Object.keys(localStorage)
      .filter(k => k.indexOf("swr1:") === 0 && k !== "swr1:$server")
      .reduce((s, k) => s + k.length + (localStorage.getItem(k) || "").length, 0);
  });
  expect(stort).toBeLessThanOrEqual(1_000_000);
});
