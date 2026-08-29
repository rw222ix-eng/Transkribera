import { expect, test } from "@playwright/test";

/* CACHAT FÖRST, FÄRSKT STRAX EFTER (api.js jsonSWR)
 *
 * Appen är en enda sida med vyer som växlas, och andra gången läraren går till
 * arkivet eller schemat är svaret nästan alltid detsamma som förra gången. SWR-
 * lagret ritar därför det cachade svaret SYNKRONT och hämtar färskt i bakgrunden.
 *
 * Det är svårt att se att det fungerar med nät: en snabb server ser precis ut
 * som en cache. Testerna nedan HÅLLER FAST list-rutterna — begäran går i väg men
 * svarar aldrig — och frågar vad som står på skärmen under tiden. Ritas listan
 * ändå kom den ur cachen, för den kan inte ha kommit någon annanstans ifrån.
 *
 * Det andra som måste hålla är gränsen mot prototypen: Claude Design kör samma
 * filer utan server, och lärarens riktiga listor får aldrig ritas där. Svarar
 * sonderingen (/api/var-kors) inte ska cachen vara borta, inte bara oanvänd.
 */

const SWR = "swr1:";

/* Namnet får inte finnas bland prototypkorten i app.html — annars bevisar en
   träff bara att den statiska sidan laddade. «Derivatans definition» står där. */
const NAMN = "Kedjeregeln ur cachen";
const LEKTION = {
  id: 1, history_id: 1, name: NAMN, dur: "42:10",
  group: "NA25", course: "Matematik 3c", datum: "2026-08-24", lang: "Svenska",
};

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

test("andra besöket ritar arkivet ur cachen, med listrutterna fastspända", async ({ page }) => {
  await laddad(page);

  /* Basen i sviten är tom, så servern har inga lektioner att cacha. Cachen sås
     därför för hand — i lagrets eget format — med en lektion som INTE står i
     app.html. Syns kortet på andra besöket kan det bara ha kommit ur cachen. */
  await saCache(page, "/api/lessons", [LEKTION]);
  await saCache(page, "/api/history", [{ id: 1, video: false, lang: "Svenska", target_lang: "Svenska" }]);

  /* Svaren räknas: hade någon av dem kommit fram vore beviset borta, för då
     kunde kortet ha ritats därifrån. */
  let svarat = 0;
  page.on("response", r => { if (/\/api\/(lessons|history)\b/.test(r.url())) svarat++; });

  await hallFast(page, "**/api/lessons");
  await hallFast(page, "**/api/history");
  await page.goto("/");

  /* Arkivet ligger i en vy som inte är den appen öppnar på — därför räknas
     korten i DOM:en i stället för att synlighet mäts. Det som prövas är när
     listan RITAS, inte vilken flik som råkar ligga framme. */
  await expect(page.locator(".kort .namn", { hasText: NAMN })).toHaveCount(1, { timeout: 8_000 });
  /* Och prototypkorten ska vara borta: listan ur cachen ÄGER arkivet, precis
     som serverns svar gör det. */
  await expect(page.locator(".kort .namn", { hasText: "Derivatans definition" })).toHaveCount(0);
  expect(svarat, "listrutterna svarade — testet bevisar då ingenting").toBe(0);
});

test("högen ritas ur cachen medan /api/dokument står fast", async ({ page }) => {
  await laddad(page);

  /* Samma bevisföring som arkivtestet: momentet finns inte i prototypens hög
     (plan.js har «derivatans definition»), så syns pappret med rutten fastspänd
     kan det bara ha kommit ur cachen. Läses via window.Dokument.sparade() —
     högen har ingen egen vy längre, korten ligger på sina lektioner i veckan.
     Sådden väntar in förstabesökets EGEN cachning av rutten: svaret kunde annars
     ligga i flykt och skriva över sådden efteråt. */
  await page.waitForFunction(() => !!localStorage.getItem("swr1:/api/dokument"),
    null, { timeout: 8_000 });
  await saCache(page, "/api/dokument", {
    sparade: [{ id: 9, dokument: {
      typ: "Prov", moment: NAMN, klass: "NA25", kurs: "Matematik 3c",
      datum: "2026-08-24", tid: "08:15–09:00", gy: [], inst: {},
    } }],
  });

  let svarat = 0;
  page.on("response", r => { if (/\/api\/dokument(\?|$)/.test(r.url())) svarat++; });
  await hallFast(page, "**/api/dokument");
  await page.goto("/");

  await page.waitForFunction(namn => window.Dokument
    && (window.Dokument.sparade() || []).some(v => v && v.moment === namn),
  NAMN, { timeout: 8_000 });
  expect(svarat, "/api/dokument svarade — testet bevisar då ingenting").toBe(0);
});

test("ett strömjobb glömmer det cachade svaret", async ({ page }) => {
  await laddad(page);
  /* Refine och approve går som strömmar, förbi json() — utan glömskan i strom()
     hade nästa öppning ritat provet som det såg ut före omskrivningen. */
  await saCache(page, "/api/exams/33", { exam: { uppgifter: [] } });
  await page.route("**/api/exams/33/refine", route => route.fulfill({
    status: 200, contentType: "text/event-stream",
    body: 'data: {"type":"done","result":{}}\n\n',
  }));
  const kvar = await page.evaluate(async () => {
    await window.API.strom("/api/exams/33/refine", {});
    return Object.keys(localStorage).filter(k => k.indexOf("swr1:/api/exams") === 0);
  });
  expect(kvar, `strömmen lämnade kvar cachade svar: ${kvar.join(", ")}`).toEqual([]);
});

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
  await saCache(page, "/api/lessons", [LEKTION]);

  /* Sonderingen spärras: det här ÄR prototypläget (Claude Design har ingen
     server alls). Lärarens riktiga lektion får inte synas, och den får inte
     ligga kvar och kunna synas nästa gång heller. */
  await page.route("**/api/var-kors", route => route.abort());
  await page.goto("/");
  await page.waitForFunction(() => !!(window.API && window.API.redo));
  await page.evaluate(() => window.API.redo);          // sonderingen klar, på ett eller annat sätt
  expect(await page.evaluate(() => window.API.pa)).toBe(false);

  await expect(page.locator(".kort .namn", { hasText: NAMN })).toHaveCount(0);
  const kvar = await page.evaluate(() =>
    Object.keys(localStorage).filter(k => k.indexOf("swr1:") === 0));
  expect(kvar, `cachen låg kvar i prototypläget: ${kvar.join(", ")}`).toEqual([]);
});

test("en skrivning glömmer det cachade svaret", async ({ page }) => {
  await laddad(page);
  await saCache(page, "/api/dokument", [{ id: 7 }]);
  await saCache(page, "/api/dokument/7/elevresultat", { rader: [] });

  /* Rutten fejkas: det som prövas är att json() glömmer, inte vad servern gör. */
  await page.route("**/api/dokument/7/elevresultat", route =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" }));

  const kvar = await page.evaluate(async () => {
    await window.API.json("/api/dokument/7/elevresultat", {
      method: "PUT",
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
