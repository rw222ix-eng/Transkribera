import { expect, test } from "@playwright/test";

/* BOKEN — hyllan, registret och uppgifterna på sidorna
 *
 * Bokdörren var helt påhittad: tre böcker, ett register med tjugofyra
 * avsnitt och uppgiftsnummer räknade ur ett antal. Etapp 0.8 gav den en
 * riktig bok — en skannad PDF som läses av en modell — och fyra saker måste
 * hålla:
 *
 *   1. Hyllan och registret är lärarens egna, inte prototypens.
 *   2. Remsan slutar där boken slutar, och avsnitten ligger på sina sidor.
 *   3. Uppgifterna på ett uppslag är de som STÅR där; är sidorna inte lästa
 *      läses de, och listan står tom under tiden i stället för att gissa.
 *   4. Importen är fyra steg som beskriver något som händer.
 *
 * Och som alltid: utan server står prototypens bokhylla kvar.
 */

const SCHEMA = { schema: [], lov: [], poster: [] };

/* Grovplaneringen: en schemarad så att klassen och kursen finns att välja i
   steg 1, och en innehallsrad som säger vad BA26B ska göra på s. 10–13. */
const GROVT = {
  ...SCHEMA,
  schema: [{ dag: 3, tid: "09:05–10:20", kurs: "Matematik, nivå 1a",
             klass: "BA26B", sal: "P807" }],
  innehall: [{ datum: "2026-08-26", tid: "09:05–10:20", klass: "BA26B",
               kurs: "Matematik, nivå 1a", fran: 10, till: 13,
               uppg: "1103–1105, 1107", hjalpmedel: "" }],
};

const AVSNITT = [
  { nr: "1.1", titel: "Repetition", kap: "Kapitel 1 · Algebra",
    vag: "Algebraiska uttryck och Ekvationer", sid: "10–14", uppg: "…" },
  { nr: "1.2", titel: "Linjära modeller", kap: "Kapitel 1 · Algebra",
    vag: "Räta linjens ekvation", sid: "15–23", uppg: 34 },
];

const BOK = {
  id: 3, namn: "Matematik 5000+ Kurs 2c", kurs: "Matematik, nivå 2c",
  sidor: 120, sidoffset: 2, status: "klar", lasta: 9, avsnitt: AVSNITT,
};

const UPPG = [
  { nr: 1215, sida: 15, niva: 1 }, { nr: 1216, sida: 15, niva: 1 },
  { nr: 1221, sida: 16, niva: 2 }, { nr: 1225, sida: 16, niva: 3 },
];

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

async function fejka(page, { bocker = [BOK], uppslag = null, las = null, profil = {}, schema = SCHEMA } = {}) {
  const anrop = [];
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, schema));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, profil));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
  await page.route("**/api/planning/**", route => {
    anrop.push({ vag: new URL(route.request().url()).pathname,
                 kropp: route.request().postDataJSON() });
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: "abc123def456", errors: [], rounds: 1,
        board: { title: "Linjära modeller", boards: [{
          name: "teori", width: 900, height: 780, chrome: "aluminium",
          padding: { top: 24, right: 26, bottom: 24, left: 30 },
          sections: [{ kind: "heading", text: "Linjära modeller", size: 30 }] }] } } }]) });
  });
  await page.route("**/api/upload**", route => {
    anrop.push({ vag: "/api/upload", kropp: null });
    return json(route, { path: "C:/bas/downloads/bok.pdf", name: "bok.pdf" });
  });
  await page.route("**/api/bocker**", route => {
    const r = route.request();
    const url = new URL(r.url());
    anrop.push({ vag: url.pathname, metod: r.method(),
                 sok: url.search, kropp: r.method() === "POST" ? r.postDataJSON() : null });
    if (url.pathname.endsWith("/uppslag")) {
      return json(route, uppslag || { fran: 15, till: 16, uppgifter: UPPG,
                                      olasta: [], utan_fakta: [], sidor: [] });
    }
    if (url.pathname.endsWith("/las")) {
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: las || strom([{ type: "log", msg: "Slår upp s. 15–16 …" },
                            { type: "done", result: { uppgifter: UPPG, lasta: 0 } }]) });
    }
    if (r.method() === "POST") {
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "log", msg: "Läser Matematik 5000+ Kurs 2c …" },
                     { type: "progress", pct: 56 },
                     { type: "log", msg: "Hittar kapitel och avsnitt …" },
                     { type: "done", result: { ...BOK, register: true } }]) });
    }
    return json(route, { bocker });
  });
  return anrop;
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Bok && window.Bok.franServern());

const oppnaBoken = async page => {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => { window.PlanSteg.las(2, false); window.PlanSteg.gaTill(2); });
};

test("hyllan och registret är lärarens egna", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);

  const reg = await page.evaluate(() => window.Bok.registerForBok("Matematik 5000+ Kurs 2c"));
  expect(reg.map(a => a.nr)).toEqual(["1.1", "1.2"]);
  // Prototypens tre böcker får inte ligga kvar bredvid lärarens egen.
  const hyllan = await page.evaluate(() => window.Bok.bocker.map(b => b.namn));
  expect(hyllan).toEqual(["Matematik 5000+ Kurs 2c"]);
  expect(await page.evaluate(() => window.Bok.bokId("Matematik 5000+ Kurs 2c"))).toBe(3);
  // Remsan slutar där boken slutar: 120 PDF-sidor minus omslag och förord.
  expect(await page.evaluate(() => window.Uppslag.sista())).toBe(118);
});

test("en kurs utan bok får inte en ANNAN boks register", async ({ page }) => {
  /* Fyndet ur den skarpa inläsningen (2026-08-13): fallbacken var första boken
     i hyllan, så Matematik nivå 2c — en kurs helt utan bok — fick 1c-bokens
     avsnitt, och «nästa i boken» pekade på en sida i fel kurs. Med EN bok i
     hyllan syntes det inte; det krävdes tre. */
  const ETTA = { ...BOK, id: 7, namn: "Liber Ma 1c", kurs: "Matematik, nivå 1c" };
  const TVAA = { ...BOK, id: 8, namn: "Origo 2a", kurs: "Matematik, nivå 2a" };
  await fejka(page, { bocker: [ETTA, TVAA] });
  await page.goto("/");
  await hydrerad(page);

  expect(await page.evaluate(() => window.Bok.registerFor("Matematik, nivå 1c")))
    .toHaveLength(2);
  expect(await page.evaluate(() => window.Bok.registerFor("Matematik, nivå 2c")))
    .toEqual([]);
  expect(await page.evaluate(() => window.Bok.namnFor("Matematik, nivå 2c"))).toBe("");
  expect(await page.evaluate(() => window.Bok.nasta("Matematik, nivå 2c", ""))).toBe(null);
});

test("en bok UTAN kurs får däremot stå in — den gör inget anspråk", async ({ page }) => {
  await fejka(page, { bocker: [{ ...BOK, kurs: null }] });
  await page.goto("/");
  await hydrerad(page);
  expect(await page.evaluate(() => window.Bok.registerFor("Matematik, nivå 2c")))
    .toHaveLength(2);
});

test("uppgifterna på uppslaget är de som står där", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await oppnaBoken(page);
  await page.evaluate(() => window.Uppslag.satt(15, 16));

  const chips = page.locator("#uppgnivaer .uppgchip");
  await expect.poll(() => chips.count()).toBe(4);
  await expect(chips.first()).toHaveText("1215");
  // Numren är bokens egna — inte 1501, 1502 … ur en uträkning.
  await expect(page.locator("#uppgant")).toContainText("av 4 att räkna");
});

test("bokens genomräknade exempel står kvar men räknas inte", async ({ page }) => {
  /* Fyndet ur den skarpa avläsningen: 1101 (s. 11) och 1102 (s. 12) i Matematik
     5000+ 1a är GENOMRÄKNADE EXEMPEL — numrerade som uppgifter, lösta med svar i
     teoritexten. Faktapassets gamla regel var tvetydig där och modellen tog med
     1101 men hoppade 1102, så panelen visade ett ensamt «1101». Numret ska synas
     — annars ser listan ut att ha tappat resten — men det är ingenting klassen
     ska räkna, och ingenting som ska följa med till pappret. */
  await fejka(page, { uppslag: { fran: 11, till: 12, olasta: [], utan_fakta: [],
    sidor: [], uppgifter: [
      { nr: 1101, sida: 11, niva: 1, exempel: 1 },
      { nr: 1102, sida: 12, niva: 1, exempel: 1 },
      { nr: 1103, sida: 12, niva: 1, exempel: 0 },
      { nr: 1104, sida: 12, niva: 2, exempel: 0 }] } });
  await page.goto("/");
  await hydrerad(page);
  await oppnaBoken(page);
  await page.evaluate(() => { window.Uppslag.satt(11, 12); window.Kallor.satt("bok", true, true); });

  await expect.poll(() => page.locator("#uppgnivaer .uppgchip").count()).toBe(4);
  const ex = page.locator("#uppgnivaer .uppgchip[data-exempel]");
  await expect(ex).toHaveText(["1101", "1102"]);
  await expect(ex.first()).toBeDisabled();
  await expect(ex.first()).toHaveAttribute("data-tip", /genomräknat exempel/);
  // Två uppgifter att räkna — inte fyra.
  await expect(page.locator("#uppgant")).toHaveText("2 av 2 att räkna");
  // Och exemplen följer inte med pappret, varken som valda eller bortvalda.
  const urval = await page.evaluate(() => window.Uppgifter.urval({}));
  expect(urval.uppg).toEqual([1103, 1104]);
  expect(urval.remsa).toBe("1103, 1104");
  expect(urval.bort).toEqual([]);
});

test("ett uppslag över två avsnitt delas i block — boken börjar om på nivå 1",
  async ({ page }) => {
    /* Sidorna 14–16 korsar gränsen 1.1/1.2. Utan uppdelningen hamnade 1.2:s
       nivå 1 på samma rad som 1.1:s, och «1114, 1215» såg ut som en fortsättning
       fast det är två olika avsnitts lätta uppgifter. */
    await fejka(page, { uppslag: { fran: 14, till: 16, olasta: [], utan_fakta: [],
      sidor: [], uppgifter: [
        { nr: 1114, sida: 14, niva: 1 }, { nr: 1118, sida: 14, niva: 3 },
        { nr: 1215, sida: 15, niva: 1 }, { nr: 1221, sida: 16, niva: 2 }] } });
    await page.goto("/");
    await hydrerad(page);
    await oppnaBoken(page);
    await page.evaluate(() => window.Uppslag.satt(14, 16));

    const grupper = page.locator("#uppgnivaer .uppgavsnitt");
    await expect.poll(() => grupper.count()).toBe(2);
    await expect(grupper.nth(0).locator(".uppgavsnittnamn")).toHaveText("1.1 Repetition · s. 14");
    await expect(grupper.nth(1).locator(".uppgavsnittnamn"))
      .toHaveText("1.2 Linjära modeller · s. 15–16");
    // Varje block bär sina egna nivårader, och 1.1 har ingen nivå 2.
    await expect(grupper.nth(0).locator(".uppgnivanamn")).toHaveText(["Nivå 1", "Nivå 3"]);
    await expect(grupper.nth(0).locator(".uppgchip")).toHaveText(["1114", "1118"]);
    await expect(grupper.nth(1).locator(".uppgchip")).toHaveText(["1215", "1221"]);
  });

test("två uppgiftsblock i SAMMA avsnitt delas också — avsnittsnamnet skrivs en gång",
  async ({ page }) => {
    /* Lärarens Liber: «1.1 Kvadratrötter och kubikrötter» har ett block efter
       vardera teoridelen, och det andra börjar om på NIVÅ 1. Rubriken skiljer
       dem på sidorna, för avsnittet är detsamma. */
    await fejka(page, { uppslag: { fran: 15, till: 18, olasta: [], utan_fakta: [],
      sidor: [], uppgifter: [
        { nr: 1201, sida: 15, niva: 1 }, { nr: 1205, sida: 16, niva: 2 },
        { nr: 1208, sida: 16, niva: 3 },
        { nr: 1209, sida: 18, niva: 1 }, { nr: 1212, sida: 18, niva: 2 }] } });
    await page.goto("/");
    await hydrerad(page);
    await oppnaBoken(page);
    await page.evaluate(() => window.Uppslag.satt(15, 18));

    const grupper = page.locator("#uppgnivaer .uppgavsnitt");
    await expect.poll(() => grupper.count()).toBe(2);
    await expect(grupper.nth(0).locator(".uppgavsnittnamn"))
      .toHaveText("1.2 Linjära modeller · s. 15–16");
    await expect(grupper.nth(1).locator(".uppgavsnittnamn")).toHaveText("s. 18");
    await expect(grupper.nth(1).locator(".uppgchip")).toHaveText(["1209", "1212"]);
  });

test("ett uppslag inom ETT block får ingen rubrik", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await oppnaBoken(page);
  await page.evaluate(() => window.Uppslag.satt(15, 16));
  await expect.poll(() => page.locator("#uppgnivaer .uppgchip").count()).toBe(4);
  // Rubriken hade bara upprepat det som redan står över remsan.
  await expect(page.locator("#uppgnivaer .uppgavsnitt")).toHaveCount(0);
});

test("olästa sidor läses, och listan gissar inte under tiden", async ({ page }) => {
  let vanda = false;
  const anrop = await fejka(page, {
    uppslag: { fran: 15, till: 16, uppgifter: [],
               olasta: [15, 16], utan_fakta: [15, 16], sidor: [] },
  });
  // Andra gången uppslaget frågas är sidorna lästa. Notera att `olasta` står
  // kvar: faktapasset skriver aldrig sidtexten, och det är precis så servern
  // svarar. Panelen ska ändå nöja sig — den läser `utan_fakta`.
  await page.unroute("**/api/bocker**");
  await page.route("**/api/bocker**", route => {
    const r = route.request();
    const url = new URL(r.url());
    anrop.push({ vag: url.pathname, metod: r.method(), sok: url.search });
    if (url.pathname.endsWith("/uppslag")) {
      const klart = vanda;
      return route.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify({ fran: 15, till: 16, uppgifter: klart ? UPPG : [],
                               olasta: [15, 16],
                               utan_fakta: klart ? [] : [15, 16], sidor: [] }) });
    }
    if (url.pathname.endsWith("/las")) {
      vanda = true;
      return route.fulfill({ status: 200, contentType: "text/event-stream",
        body: strom([{ type: "log", msg: "Slår upp s. 15–16 …" },
                     { type: "done", result: { uppgifter: UPPG, lasta: 0 } }]) });
    }
    return route.fulfill({ status: 200, contentType: "application/json",
                           body: JSON.stringify({ bocker: [BOK] }) });
  });
  await page.goto("/");
  await hydrerad(page);
  await oppnaBoken(page);
  await page.evaluate(() => window.Uppslag.satt(15, 16));

  // Läsningen begärs, och den är faktapasset — inte hela sidtexten.
  await expect.poll(() => anrop.some(a => a.vag.endsWith("/las"))).toBe(true);
  // Och när den är klar står bokens riktiga nummer i listan.
  await expect.poll(() => page.locator("#uppgnivaer .uppgchip").count(),
                    { timeout: 15_000 }).toBe(4);
  // ETT läsanrop, inte hundra: hämta → läs → hämta gick i evig slinga så länge
  // panelen triggade på `olasta`, som faktapasset aldrig tömmer.
  await page.waitForTimeout(1500);
  expect(anrop.filter(a => a.vag.endsWith("/las")).length).toBe(1);
});

test("importen är fyra steg som beskriver något som händer", async ({ page }) => {
  const anrop = await fejka(page, { bocker: [] });
  await page.goto("/");
  await hydrerad(page);
  await oppnaBoken(page);

  /* Kursen som planeras — knappen sitter i lektionens bokdörr. Den MÅSTE följa
     med: utan kurs hamnar boken i hyllan men registret läggs aldrig under någon
     kurs (bok.js taEmot), och «nästa i boken» står tomt om en bok som har ett
     register. */
  await page.evaluate(() => {
    const f = document.querySelector("#p-kurs");
    f.innerHTML = '<option value="Matematik, nivå 2c">Matematik, nivå 2c</option>';
    f.value = "Matematik, nivå 2c";
  });
  await page.setInputFiles("#bokfil", {
    name: "Matematik 5000+ Kurs 2c.pdf", mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 minimal"),
  });

  await expect.poll(() => anrop.some(a => a.vag === "/api/upload"), { timeout: 15_000 }).toBe(true);
  await expect.poll(() => anrop.some(a => a.vag === "/api/bocker" && a.metod === "POST")).toBe(true);
  const post = anrop.find(a => a.vag === "/api/bocker" && a.metod === "POST");
  expect(post.kropp.path).toBe("C:/bas/downloads/bok.pdf");
  expect(post.kropp.namn).toBe("Matematik 5000+ Kurs 2c");
  expect(post.kropp.kurs).toBe("Matematik, nivå 2c");
  // Hyllan läses om när boken är inne.
  await expect.poll(() => anrop.filter(a => a.vag === "/api/bocker" && a.metod === "GET").length,
                    { timeout: 15_000 }).toBeGreaterThan(1);
});

/* ── Bladet säger till ──
   «Klickade på appen på skrivbordet, valde en sida i boken. Sidan fanns inte
   inskannad och jag såg ingen indikation på att det laddade in.» (2026-09-06)
   Sidan renderades ur PDF:en vid begäran, renderingen föll (pdfium var
   förstört i appens process, se app/pdfvakt.py) och `onerror` tog bort bilden
   utan ett ord. De två testerna nedan håller båda halvorna: att hämtningen
   syns, och att felet blir en svensk mening med en väg tillbaka. */

test("bladet säger att sidan läses in", async ({ page }) => {
  await fejka(page);
  // Bilden dröjer: rutten svarar först efter en stund, precis som en
  // pdfium-rendering av en bok på ett par hundra megabyte.
  await page.route("**/api/bocker/*/sida/*.png**", async route => {
    await new Promise(r => setTimeout(r, 3000));
    return route.fulfill({ status: 404, contentType: "application/json",
                           body: JSON.stringify({ error: "källfilen saknas" }) });
  });
  await page.goto("/");
  await hydrerad(page);
  await oppnaBoken(page);
  await page.evaluate(() => window.Uppslag.satt(15, 16));

  await expect(page.locator(".bkblad", { hasText: "första sidan" })
                   .locator(".bkstatus")).toHaveText(/Läser in s\. 15/);
});

test("en sida som inte gick att läsa säger varför, och går att försöka igen",
     async ({ page }) => {
  await fejka(page);
  let forsok = 0;
  await page.route("**/api/bocker/*/sida/*.png**", route => {
    forsok++;
    return route.fulfill({ status: 500, contentType: "application/json",
      body: JSON.stringify({ error: "kunde inte rendera sidan: PDF:en gick "
        + "inte att öppna: Liber Ma 1c komplett.pdf — Data format error." }) });
  });
  await page.goto("/");
  await hydrerad(page);
  await oppnaBoken(page);
  await page.evaluate(() => window.Uppslag.satt(15, 16));

  const not = page.locator(".bkblad", { hasText: "första sidan" }).locator(".bkstatus");
  await expect(not).toContainText("Sidan kunde inte läsas: kunde inte rendera sidan");
  await expect(not).toContainText("Data format error");
  /* Steget öppnas här med PlanSteg.gaTill, och då står `.plansteg` kvar med
     display:none — hela bokdörren mäter noll. Därför prövas innehållet och
     klicket, inte pixlarna, precis som i sviten i övrigt. */
  const igen = not.locator("button.bkigen");
  await expect(igen).toHaveCount(1);
  await expect(igen).toHaveText("Försök igen");
  const fore = forsok;
  await igen.dispatchEvent("click");
  await expect.poll(() => forsok).toBeGreaterThan(fore);
});

test("uppslaget följer med skrivningen", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await oppnaBoken(page);
  await page.evaluate(() => {
    window.Uppslag.satt(15, 16);
    window.Kallor.satt("bok", true, true);
    window.SattLage("Tavla");
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  });
  await page.locator("#skriv").click();

  await expect.poll(() => anrop.some(a => a.vag.endsWith("/generate")),
                    { timeout: 15_000 }).toBe(true);
  const gen = anrop.find(a => a.vag.endsWith("/generate"));
  // Sidorna OCH lärarens urval: «lägg till vilka uppgifter vi ska göra» kan
  // inte besvaras utan numren, och de stannade förr i webbläsaren.
  expect(gen.kropp.bok).toMatchObject({ id: 3, fran: 15, till: 16 });
  expect(gen.kropp.bok.remsa).toBe("1215, 1216, 1221, 1225");
});

test("utan server står prototypens bokhylla kvar", async ({ page }) => {
  await page.route("**/api/var-kors", route => route.abort());
  const natanrop = [];
  await page.route("**/api/bocker**", route => { natanrop.push(route.request().url()); route.abort(); });
  await page.goto("/");
  await page.waitForFunction(() => document.documentElement.hasAttribute("data-server") === false);

  expect(await page.evaluate(() => window.Bok.franServern())).toBe(false);
  const reg = await page.evaluate(() => window.Bok.registerForBok("Matematik 5000+ 3c"));
  expect(reg.length).toBeGreaterThan(20);          // prototypens 24 avsnitt
  expect(natanrop).toEqual([]);
});

test("klassprofilens bok är KURSENS, inte hyllans första", async ({ page }) => {
  /* Fyndet ur den skarpa körningen (2026-08-18): en lektion i Matematik, nivå
     2a fick «Matematik 5000+ 1a» förvald. Profilens karta över kursernas
     böcker var hårdkodad på prototypens tre kurser, så lärarens kurser fann
     ingen bok där: en ny klass ärvde hyllans FÖRSTA bok (bok.js taEmot sätter
     `window.Bok.namn` till den), och profilens självläkning — den som just ska
     rätta en bok ur fel kurs — stod still av samma skäl. Hyllan äger frågan
     nu, och det gäller båda hållen: minnet läks OCH den nya klassen ärver
     rätt. */
  const ETTA = { ...BOK, id: 7, namn: "Matematik 5000+ 1a", kurs: "Matematik, nivå 1a" };
  const TVAA = { ...BOK, id: 8, namn: "Origo 2a", kurs: "Matematik, nivå 2a" };
  const minne = {
    IndA: {
      kurs: "Matematik, nivå 2a", kursN: 1, kursNu: "Matematik, nivå 2a",
      bok: "Matematik 5000+ 1a", bokN: 0, senasteSida: 40,
      sidorPerLektion: 4, taktN: 0, typer: {}, par: 0, n: 1,
      kurser: { "Matematik, nivå 2a": { bok: "Matematik 5000+ 1a", bokN: 0,
                                        senasteSida: 40, sidorPerLektion: 4, taktN: 0 } },
    },
  };
  await fejka(page, { bocker: [ETTA, TVAA], profil: minne });
  await page.goto("/");
  await hydrerad(page);

  await expect.poll(() => page.evaluate(() => window.Profil.minne().IndA.bok))
    .toBe("Origo 2a");
  // Kursfacket läks med — det är det förvalen läser när klassen byter kurs.
  expect(await page.evaluate(() => window.Profil.minne().IndA.kurser["Matematik, nivå 2a"].bok))
    .toBe("Origo 2a");
  // Sidan följer inte med in i en annan bok: s. 40 i 1a är inte s. 40 i 2a.
  expect(await page.evaluate(() => window.Profil.minne().IndA.senasteSida)).toBe(0);
  // En klass appen aldrig sett ärver kursens bok, inte hyllans första.
  expect(await page.evaluate(() => window.Profil.forKlass("NA26F").bok)).toBe("");
});

test("kalenderraden citerar HELA lärarens lista — också det som inte står på sidorna",
  async ({ page }) => {
    /* Fyndet ur den skarpa körningen (2026-08-18): i kalendern stod «uppg.
       1101–1103, 1105–1119», och raden i panelen sa «… i kalendern: 1101–1103,
       1105–1115». Den skrevs ur skärningen mellan lärarens lista och de
       uppgifter som HUNNIT läsas ur sidorna, så en sida som inte var inläst
       kortade av hennes egen mening utan att säga det. */
    await fejka(page, { uppslag: { fran: 2, till: 6, olasta: [], utan_fakta: [],
      sidor: [], uppgifter: [
        { nr: 1101, sida: 2, niva: 1 }, { nr: 1102, sida: 2, niva: 1 },
        { nr: 1103, sida: 3, niva: 2 }, { nr: 1105, sida: 4, niva: 2 },
        { nr: 1115, sida: 6, niva: 3 }] } });
    await page.goto("/");
    await hydrerad(page);
    await oppnaBoken(page);
    await page.evaluate(() => window.Uppslag.satt(2, 6));
    await expect.poll(() => page.locator("#uppgnivaer .uppgchip").count()).toBe(5);

    await page.evaluate(() => window.Uppgifter.franKalendern("1101–1103, 1105–1119"));
    const rad = page.locator("#uppgforslag");
    await expect(rad).toContainText("i kalendern: 1101–1103, 1105–1119.");
    /* …och det som inte gick att hitta sägs rakt ut i stället för att tystas
       bort — men i två meningar, för det är två olika saker. 1106–1114 ligger
       MELLAN lästa nummer (1105 och 1115) på lästa sidor: de står i boken, och
       det var avläsningen som missade dem. 1116–1119 ligger efter det sista
       numret på uppslaget och finns helt enkelt inte där. */
    await expect(rad).toContainText("1106–1114 kunde inte läsas från sidan.");
    await expect(rad).toContainText("1116–1119 står inte på s. 2–6.");
  });

test("en lucka servern SETT sägs som en lucka, inte som en uppgift som saknas",
  async ({ page }) => {
    /* Uppslagsrutten räknar fram luckorna ur det den läst (app/bok.py luckor).
       Säger servern att 1102 saknas mitt i följden ska raden säga DET — «står
       inte på s. 11–12» hade skickat läraren att leta efter en uppgift hon
       skrivit rätt, och tro att hon mindes fel. */
    await fejka(page, { uppslag: { fran: 11, till: 12, olasta: [], utan_fakta: [],
      sidor: [], luckor: [1102], uppgifter: [
        { nr: 1101, sida: 11, niva: 1 }, { nr: 1103, sida: 12, niva: 1 },
        { nr: 1104, sida: 12, niva: 2 }] } });
    await page.goto("/");
    await hydrerad(page);
    await oppnaBoken(page);
    await page.evaluate(() => window.Uppslag.satt(11, 12));
    await expect.poll(() => page.locator("#uppgnivaer .uppgchip").count()).toBe(3);

    await page.evaluate(() => window.Uppgifter.franKalendern("1101–1104, 1130"));
    const rad = page.locator("#uppgforslag");
    await expect(rad).toContainText("1102 kunde inte läsas från sidan.");
    // 1130 ligger utanför följden — det är en annan sak, och sägs som förut.
    await expect(rad).toContainText("1130 står inte på s. 11–12.");
  });

test("lektionen utan bokplanering får ändå uppgifterna ur din grovplanering",
  async ({ page }) => {
    /* Fyndet ur den skarpa körningen: BA26B:s lektion har ingen bokplanering i
       kalendern, så läraren väljer bok och s. 10–13 själv i sidremsan — och
       panelen föll då tillbaka på modellens hoppa-över-förslag. Men hennes
       GROVPLANERING har en rad som täcker precis de sidorna, med uppgifterna
       skrivna. Sidorna är nyckeln, inte dagen (kalender.js uppgifterForSpann). */
    await fejka(page, { schema: GROVT, uppslag: {
      fran: 10, till: 13, olasta: [], utan_fakta: [], sidor: [], uppgifter: [
        { nr: 1103, sida: 10, niva: 1 }, { nr: 1104, sida: 11, niva: 1 },
        { nr: 1105, sida: 11, niva: 2 }, { nr: 1106, sida: 12, niva: 2 },
        { nr: 1107, sida: 13, niva: 3 }, { nr: 1108, sida: 13, niva: 3 }] } });
    await page.goto("/");
    await hydrerad(page);
    await oppnaBoken(page);

    /* Steg 1 är ifyllt innan förvalen sätts (plankon.js fyll) — klassen och
       kursen är det uppslaget slår på. */
    await page.evaluate(() => {
      const satt = (id, v) => {
        const f = document.querySelector(id);
        if (![...f.options].some(o => o.value === v || o.textContent === v)) {
          f.appendChild(Object.assign(document.createElement("option"), { textContent: v }));
        }
        f.value = v;
        f.dispatchEvent(new Event("change", { bubbles: true }));
      };
      satt("#p-klass", "BA26B");
      satt("#p-kurs", "Matematik, nivå 1a");
    });
    // Lärarens eget spannval i remsan — ingen lektionsrad bakom det.
    await page.evaluate(() => window.Uppslag.satt(10, 13));
    await expect.poll(() => page.locator("#uppgnivaer .uppgchip").count()).toBe(6);

    // Hennes urval gäller: allt annat på sidorna är bortvalt, inte modellens två.
    await expect(page.locator("#uppgnivaer .uppgchip:not([data-bort])"))
      .toHaveText(["1103", "1104", "1105", "1107"]);
    await expect(page.locator("#uppgnivaer .uppgchip[data-bort]"))
      .toHaveText(["1106", "1108"]);
    /* Och raden ljuger inte om varifrån det kom: det här är en ANNAN dags rad,
       inte något hon skrev på den här lektionen. */
    await expect(page.locator("#uppgforslag"))
      .toHaveText("Ur din planering (26 augusti): 1103–1105, 1107.");

    /* Lektionens EGEN kalenderrad vinner ändå — profil.js sätter spannet först
       och ropar franKalendern efter, och då är det hon skrev på lektionen som
       citeras. */
    await page.evaluate(() => window.Uppgifter.franKalendern("1104, 1106"));
    await expect(page.locator("#uppgforslag"))
      .toHaveText("Uppgifterna du skrivit på lektionen i kalendern: 1104, 1106.");
    await expect(page.locator("#uppgnivaer .uppgchip:not([data-bort])"))
      .toHaveText(["1104", "1106"]);
  });

test("grovplaneringen slår bara till på sidor den faktiskt täcker", async ({ page }) => {
  /* Raden gäller s. 10–13. Drar läraren remsan till 15–16 finns inget svar i
     planeringen, och då är modellens förslag tillbaka — inte grannsidornas
     uppgifter. */
  await fejka(page, { schema: GROVT });
  await page.goto("/");
  await hydrerad(page);
  await oppnaBoken(page);
  await page.evaluate(() => {
    const f = document.querySelector("#p-klass");
    f.appendChild(Object.assign(document.createElement("option"), { textContent: "BA26B" }));
    f.value = "BA26B";
    f.dispatchEvent(new Event("change", { bubbles: true }));
    window.Uppslag.satt(15, 16);
  });
  await expect.poll(() => page.locator("#uppgnivaer .uppgchip").count()).toBe(4);
  await expect(page.locator("#uppgforslag")).not.toContainText("Ur din planering");
});

test("är sidorna inte inlästa säger raden DET — inte att uppgifterna saknas",
  async ({ page }) => {
    await fejka(page, { uppslag: { fran: 2, till: 6, olasta: [5, 6], utan_fakta: [],
      sidor: [], uppgifter: [
        { nr: 1101, sida: 2, niva: 1 }, { nr: 1105, sida: 4, niva: 2 }] } });
    await page.goto("/");
    await hydrerad(page);
    await oppnaBoken(page);
    await page.evaluate(() => window.Uppslag.satt(2, 6));
    await expect.poll(() => page.locator("#uppgnivaer .uppgchip").count()).toBe(2);

    await page.evaluate(() => window.Uppgifter.franKalendern("1101, 1105, 1119"));
    await expect(page.locator("#uppgforslag")).toContainText("1119 har inte lästs in än.");
  });
