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

async function fejka(page, { bocker = [BOK], uppslag = null, las = null, profil = {} } = {}) {
  const anrop = [];
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
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
