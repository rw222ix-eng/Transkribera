import { expect, test } from "@playwright/test";

/* KALENDERN OCH DATUMMATTEN (Etapp 2)
 *
 * Hela appen hänger på veckan: veckovyn, terminsvyn, planeringskön, «Nästa
 * skolvecka», dokumentens datum och profilens takt. Datummatte är samtidigt
 * det som tystast går sönder — ett årsskifte, ett lov eller en vecka 53 syns
 * inte i något annat test förrän dagen är där, och då står läraren i fel vecka
 * med fel material.
 *
 * Klockan fryses därför (page.clock.install FÖRE sidladdningen — appen läser
 * datum redan i sitt första andetag) och veckan matas in ur en fejkad
 * /api/schema. Ingenting här kräver att sviten körs en viss dag.
 */

/** Måndagen i en vecka som helt ligger i ett lov, plus veckan efter. */
const SCHEMA = {
  schema: [
    { dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 2c", klass: "NA25", sal: "P807" },
    { dag: 3, tid: "10:40–11:55", kurs: "Matematik, nivå 2c", klass: "NA25", sal: "P807" },
  ],
  lov: [],
  poster: [],
};

const json = (route, kropp) => route.fulfill({
  status: 200, contentType: "application/json", body: JSON.stringify(kropp) });

async function fejka(page, schema = SCHEMA) {
  await page.route("**/api/schema", route => json(route, schema));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern());

/** Fryser klockan vid ett datum (lokal tid, mitt på dagen). */
async function vid(page, datum) {
  await page.clock.install({ time: new Date(`${datum}T09:00:00`) });
}

/** Väntar tills veckan slutat glida — 175 + 20 + 300 ms i klass.js, plus
 *  flaggan som släpps efter 330 ms. Ett riktat hopp under glidet kastas. */
const stillaVecka = page => page.waitForTimeout(700);

// ── ISO-veckor: den rena matten ─────────────────────────────────────────
// Vecka 53 finns, och den tillhör året den BÖRJADE i. Ett fel här flyttar
// hela terminsvyn ett steg fel över nyår.

test("veckonumren följer ISO också över årsskiftet", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  const svar = await page.evaluate(() => ({
    nyarsdag26: window.Kalender.veckonr("2026-01-01"),   // torsdag → v1
    sista26: window.Kalender.veckonr("2026-12-31"),      // torsdag → v53
    nyarsdag27: window.Kalender.veckonr("2027-01-01"),   // fredag → fortfarande v53
    forsta27: window.Kalender.veckonr("2027-01-04"),     // måndag → v1
    langt20: window.Kalender.veckonr("2020-12-28"),      // måndag → v53
    nyar21: window.Kalender.veckonr("2021-01-01"),       // fredag → v53
    tidig20: window.Kalender.veckonr("2019-12-30"),      // måndag → v1 (2020)
  }));
  expect(svar).toEqual({
    nyarsdag26: 1, sista26: 53, nyarsdag27: 53, forsta27: 1,
    langt20: 53, nyar21: 53, tidig20: 1,
  });
});

test("måndagen är veckans måndag, också på en söndag", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  const m = await page.evaluate(() => [
    window.Kalender.mandagen("2026-09-06"),   // söndag → veckan som slutar
    window.Kalender.mandagen("2026-09-07"),   // måndag → sig själv
    window.Kalender.mandagen("2027-01-03"),   // söndag i v53 → 28 dec
  ]);
  expect(m).toEqual(["2026-08-31", "2026-09-07", "2026-12-28"]);
});

test("veckovyn går från v53 till v1 utan att tappa året", async ({ page }) => {
  await fejka(page);
  await vid(page, "2026-12-30");            // onsdag i vecka 53
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();

  await expect(page.locator("#schemavecka")).toHaveText("Vecka 53");
  await page.locator("#schemafram").click();
  await expect(page.locator("#schemavecka")).toHaveText("Vecka 1");
  await page.locator("#schemabak").click();
  await expect(page.locator("#schemavecka")).toHaveText("Vecka 53");
});

// ── Lovet ───────────────────────────────────────────────────────────────

const MED_LOV = {
  ...SCHEMA,
  lov: [{ namn: "Höstlov", typ: "lov", fran: "2026-10-26", till: "2026-10-30" }],
};

test("appen öppnar veckan efter lovet — och tillbaka i lovet erbjuds vägen fram",
  async ({ page }) => {
    await fejka(page, MED_LOV);
    await vid(page, "2026-10-28");          // onsdag mitt i höstlovet
    await page.goto("/");
    await hydrerad(page);
    await page.getByRole("tab", { name: "Planering" }).click();

    // Under ett lov planerar man inte lovet: veckan som öppnas är den efter
    // (måndag 2 november, vecka 45).
    await expect(page.locator("#schemavecka")).toHaveText("Vecka 45");
    await expect(page.locator(".skdag")).toHaveCount(5);

    // Går man ändå tillbaka in i lovveckan står den tom — och knappen blir
    // vägen fram i stället för vägen hem.
    const knapp = page.locator("#schemanu");
    await expect(knapp).toHaveText("Den här veckan");
    await knapp.click();
    await expect(page.locator("#schemavecka")).toHaveText("Vecka 44");
    await expect(page.locator("#schemasum")).toContainText("lov");
    await expect(knapp).toHaveText("Nästa skolvecka");
    /* Veckan glider in (175 + 20 + 300 ms) och ett riktat hopp UNDER glidet
       kastas med flit — bara stegklick köas (klass.js byt). Etiketten byts
       redan mitt i glidet, så knappen ser klickbar ut innan den är det. */
    await stillaVecka(page);
    await knapp.click();
    await expect(page.locator("#schemavecka")).toHaveText("Vecka 45");
  });

test("en bokning som ligger på en lovdag visas — med varning, aldrig gömd",
  async ({ page }) => {
    await fejka(page, {
      ...MED_LOV,
      poster: [{ datum: "2026-10-28", tid: "09:00", titel: "Utvecklingssamtal",
                 klass: "NA25", slag: "annat", antal: 1 }],
    });
    await vid(page, "2026-10-28");
    await page.goto("/");
    await hydrerad(page);
    await page.getByRole("tab", { name: "Planering" }).click();
    // Appen öppnar veckan efter lovet; bokningen ligger i lovveckan.
    await page.locator("#schemanu").click();
    await expect(page.locator("#schemavecka")).toHaveText("Vecka 44");

    const krock = page.locator("[data-lovkrock]");
    await expect(krock).toHaveCount(1);
    await expect(krock).toContainText("Utvecklingssamtal");
    await expect(krock).toContainText("höstlov");
  });

test("nästa skolvecka hoppar över ett lov som är längre än en vecka",
  async ({ page }) => {
    await fejka(page, {
      ...SCHEMA,
      lov: [{ namn: "Jullov", typ: "lov", fran: "2026-12-21", till: "2027-01-08" }],
    });
    await vid(page, "2026-12-23");
    await page.goto("/");
    await hydrerad(page);
    const m = await page.evaluate(() => window.Kalender.nastaSkolvecka("2026-12-23"));
    expect(m).toBe("2027-01-11");           // första måndagen efter jullovet
  });

// ── Termbandet ──────────────────────────────────────────────────────────
// Bandet svarar på EN fråga: vilka veckor framåt saknar material. Klickar man
// på en vecka ska man landa i den — inte i en vecka bredvid, och inte i
// terminsläget igen.

test("ett klick i termbandet landar i rätt vecka", async ({ page }) => {
  await fejka(page);
  await vid(page, "2026-09-09");             // onsdag, vecka 37
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.locator("#schemalage button", { hasText: "Termin" }).click();

  const rutor = page.locator(".tbv");
  await expect(rutor.first()).toBeVisible();
  // Veckonumret i bandet och veckan man landar i måste vara samma vecka.
  const mal = rutor.nth(3);
  const nr = (await mal.locator(".tbnr").textContent()).trim();
  await mal.click();

  await expect(page.locator("#ark-klass")).toHaveAttribute("data-lage", "vecka");
  await expect(page.locator("#schemavecka")).toHaveText(`Vecka ${nr.replace("v", "")}`);
});

test("terminsläget och veckoläget är samma panel i två zoomlägen", async ({ page }) => {
  await fejka(page);
  await vid(page, "2026-09-09");
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();

  const panel = page.locator("#ark-klass");
  await page.locator("#schemalage button", { hasText: "Termin" }).click();
  await expect(panel).toHaveAttribute("data-lage", "termin");
  await page.locator("#schemalage button", { hasText: "Vecka" }).click();
  await expect(panel).toHaveAttribute("data-lage", "vecka");
  await expect(page.locator("#schemavecka")).toContainText("Vecka");
});


// ── Klassprofilen ───────────────────────────────────────────────────────
// Profilen låg i localStorage innan den flyttade till servern, och den lokala
// kopian läses fortfarande som första snabba svar. En trasig eller uråldrig
// post där får aldrig ta appen med sig i fallet.

test("en korrupt klassprofil i localStorage läks i stället för att fälla appen",
  async ({ page }) => {
    const jsfel = [];
    await fejka(page);
    await page.addInitScript(() => {
      localStorage.setItem("transkribera.klassprofil.v1", "{trasig json,,,");
    });
    page.on("pageerror", e => jsfel.push(e.message));
    await page.goto("/");
    await hydrerad(page);
    expect(jsfel, jsfel.join(" | ")).toEqual([]);
    const minne = await page.evaluate(() => window.Profil.minne());
    expect(typeof minne).toBe("object");
  });

test("en klassprofil av fel form skriver inte sönder planeringen",
  async ({ page }) => {
    const jsfel = [];
    await fejka(page);
    await page.addInitScript(() => {
      // Gammal form: strängar där appen numera har objekt, och en klass som
      // inte finns i schemat längre.
      localStorage.setItem("transkribera.klassprofil.v1", JSON.stringify({
        "9A": "det här var en sträng en gång",
        "borta": { kurs: 42, typer: null, senasteSida: "hundra" },
      }));
    });
    page.on("pageerror", e => jsfel.push(e.message));
    await page.goto("/");
    await hydrerad(page);
    await page.getByRole("tab", { name: "Planering" }).click();
    await expect(page.locator("#schemavecka")).toContainText("Vecka");
    expect(jsfel, jsfel.join(" | ")).toEqual([]);
  });

// ── Rutan som kalendern har fyllt med något annat ───────────────────────
// Schemaraden är serien: att den finns betyder att det brukar vara lektion
// måndag 08:10 — inte att det är lektion just den måndagen. Står det «Hämta
// läromedel» i lektionens timme ritade appen både ett tomt lektionskort och
// postens eget kort, och det tomma kortet erbjöd en sidsträcka gissad ur
// klassprofilen på en dag klassen bara hämtar böcker.

const BOKHAMTNING = {
  schema: [{ dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 2c",
             klass: "NA25", sal: "P807" }],
  lov: [],
  poster: [{ datum: "2026-11-02", tid: "09:05–10:20", klass: "NA25",
             titel: "📚 Hämta läromedel i läromedelscentralen, hela passet",
             slag: "annat", antal: 1 }],
  innehall: [],
};

test("posten i lektionens timme ersätter lektionskortet — ett kort, inga gissade sidor",
  async ({ page }) => {
    await fejka(page, BOKHAMTNING);
    await vid(page, "2026-11-02");
    await page.goto("/");
    await hydrerad(page);
    await page.getByRole("tab", { name: "Planering" }).click();
    await stillaVecka(page);

    // ETT kort för timmen, och det bär kalenderns egen rubrik.
    const kort = page.locator("#schemagrid article.lekt");
    await expect(kort).toHaveCount(1);
    await expect(kort).toContainText("Hämta läromedel");
    // Ingen streckad kant och ingen «Tavla saknas»: det är ingen lucka.
    await expect(kort).not.toHaveAttribute("data-tom", "");
    await expect(kort.locator(".lektsaknas")).toHaveCount(0);

    // Och förvalen rör inte bokdörren när lektionen väljs: spannet står kvar
    // som det stod, i stället för att flyttas till «sidorna efter förra
    // lektionen» på en dag klassen bara hämtar böcker.
    const fore = await page.evaluate(() => JSON.stringify(window.Uppslag.spann()));
    await kort.click();
    await page.waitForTimeout(500);
    const efter = await page.evaluate(() => JSON.stringify(window.Uppslag.spann()));
    expect(efter).toBe(fore);
  });

test("provet i lektionens timme går fortfarande sin egen väg",
  async ({ page }) => {
    await fejka(page, { ...BOKHAMTNING,
      poster: [{ datum: "2026-11-02", tid: "09:05–10:20", klass: "NA25",
                 titel: "NA25: PROV 1 (kap 1)", slag: "prov", antal: 1 }] });
    await vid(page, "2026-11-02");
    await page.goto("/");
    await hydrerad(page);
    await page.getByRole("tab", { name: "Planering" }).click();
    await stillaVecka(page);
    const kort = page.locator("#schemagrid article.lekt");
    await expect(kort).toHaveCount(1);
    await expect(kort).toContainText("Prov bokat");
    await expect(kort.getByRole("button", { name: "Skriv provet" })).toBeVisible();
  });

// ── Lektionens innehåll står på kortet ──────────────────────────────────
// Lärarens grovplanering ligger i kalendern rad för rad: sidorna, uppgifterna
// och hjälpmedlen per lektion. Förvalen har alltid läst den — men veckan sa
// ingenting, så en lektion med sidor i kalendern stod som en anonym ruta med
// tid och klass. Bara den timme läraren råkat lägga en EGEN post i fick text.

/* Hyllan i testet: EN bok, märkt med Ma 2c. Registret är bokens egen
   innehållsförteckning — det är den som översätter sidnummer till avsnitt. */
const HYLLAN = [{
  id: 1, namn: "Origo 2c", kurs: "Matematik, nivå 2c", sidor: 320, sidoffset: 0,
  avsnitt: [
    { nr: "5.3", titel: "Deriveringsregler", kap: "Kapitel 5 · Derivata", vag: "Produkt, kvot och kedja", sid: "198–206", uppg: 26 },
    { nr: "5.4", titel: "Extrempunkter och andraderivatan", kap: "Kapitel 5 · Derivata", vag: "Teckenschema", sid: "207–215", uppg: 24 },
  ],
}];

const INNEHALLET = {
  schema: [
    { dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 2c", klass: "NA25", sal: "P807" },
    { dag: 1, tid: "11:00–12:15", kurs: "Fysik 1a", klass: "TE25", sal: "I210" },
  ],
  lov: [],
  poster: [],
  innehall: [
    { datum: "2026-11-02", tid: "09:05–10:20", klass: "NA25", kurs: "Matematik, nivå 2c",
      fran: 207, till: 215, uppg: "3101–3110", hjalpmedel: "raknare" },
    { datum: "2026-11-02", tid: "11:00–12:15", klass: "TE25", kurs: "Fysik 1a",
      fran: 40, till: 44, uppg: "2201–2208", hjalpmedel: "" },
  ],
};

test("varje lektion säger vad den handlar om — avsnittet när boken vet, annars sidorna",
  async ({ page }) => {
    await fejka(page, INNEHALLET);
    await page.route("**/api/bocker", route => json(route, { bocker: HYLLAN }));
    await vid(page, "2026-11-02");
    await page.goto("/");
    await hydrerad(page);
    await page.getByRole("tab", { name: "Planering" }).click();
    await stillaVecka(page);

    const kort = page.locator("#schemagrid article.lekt");
    await expect(kort).toHaveCount(2);
    /* Boken för Ma 2c står på hyllan: s. 207–215 ÄR «5.4 Extrempunkter och
       andraderivatan», hela avsnittet — då står rubriken utan förbehåll. */
    await expect(kort.nth(0).locator(".lektinnehall")).toHaveText("5.4 Extrempunkter och andraderivatan, s. 207–215");
    /* Fysik 1a har ingen bok på hyllan. Då står sidorna för sig själva —
       sant, och mer än ingenting. Inget avsnitt ur en annan kurs lånas in. */
    await expect(kort.nth(1).locator(".lektinnehall")).toHaveText("s. 40–44");
  });

test("lärarens egen rubrik i timmen står ensam — raden sägs inte två gånger",
  async ({ page }) => {
    await fejka(page, { ...INNEHALLET,
      poster: [{ datum: "2026-11-02", tid: "09:05–10:20", klass: "NA25",
                 titel: "Tavla — 5.4 Extrempunkter", slag: "tavla", antal: 1 }] });
    await page.route("**/api/bocker", route => json(route, { bocker: HYLLAN }));
    await vid(page, "2026-11-02");
    await page.goto("/");
    await hydrerad(page);
    await page.getByRole("tab", { name: "Planering" }).click();
    await stillaVecka(page);

    const nu = page.locator("#schemagrid article.lekt").filter({ hasText: "NA25" });
    await expect(nu.locator(".lektbokat")).toHaveText("Tavla — 5.4 Extrempunkter");
    await expect(nu.locator(".lektinnehall")).toHaveCount(0);
  });

test("ett spann över två avsnitt namnger båda — med sina egna sidor", async ({ page }) => {
  /* Lektionen slutar ett avsnitt och börjar nästa: s. 200–210 är slutet på
     «5.3 Deriveringsregler» (s. 198–206) och början på «5.4 Extrempunkter»
     (s. 207–215). Kortet läste avsnittet på FÖRSTA sidan och stannade där —
     halva lektionen fanns inte i texten. */
  await fejka(page, { ...INNEHALLET,
    innehall: [{ datum: "2026-11-02", tid: "09:05–10:20", klass: "NA25",
                 kurs: "Matematik, nivå 2c", fran: 200, till: 210, uppg: "", hjalpmedel: "" }] });
  await page.route("**/api/bocker", route => json(route, { bocker: HYLLAN }));
  await vid(page, "2026-11-02");
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await stillaVecka(page);

  const nu = page.locator("#schemagrid article.lekt").filter({ hasText: "NA25" });
  await expect(nu.locator(".lektinnehall")).toHaveText(
    "del av 5.3 Deriveringsregler, s. 200–206 · del av 5.4 Extrempunkter och andraderivatan, s. 207–210");
});

test("täcker lektionen bara en del av avsnittet säger kortet det", async ({ page }) => {
  /* Avsnitt 1.1 i lärarens bok heter «Kvadratrötter och kubikrötter» och går
     över fem sidor. Lektionen på de tre första är kvadratrötterna — kortet
     påstod hela rubriken och sa alltså mer än kalendern gjorde. */
  await fejka(page, { ...INNEHALLET,
    innehall: [{ datum: "2026-11-02", tid: "09:05–10:20", klass: "NA25",
                 kurs: "Matematik, nivå 2c", fran: 207, till: 210, uppg: "", hjalpmedel: "" }] });
  await page.route("**/api/bocker", route => json(route, { bocker: HYLLAN }));
  await vid(page, "2026-11-02");
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await stillaVecka(page);

  const nu = page.locator("#schemagrid article.lekt").filter({ hasText: "NA25" });
  await expect(nu.locator(".lektinnehall"))
    .toHaveText("del av 5.4 Extrempunkter och andraderivatan, s. 207–210");
});

test("lärarens egna rubriker vinner över bokens avsnittsnamn", async ({ page }) => {
  /* Hon skriver rubriken framför sidspannet i kalenderhändelsen —
     «Kubikrötter: s. 207–210 · Potenser: s. 211–215» — och sedan hon öppnade
     för dem (2026-08-18) bärs orden hela vägen ut på kortet. Boken kan inte
     svara: avsnitt 5.4 heter «Extrempunkter och andraderivatan» och går över
     hela s. 207–215, så registret lovade dubbelt så mycket som hon skrivit. */
  await fejka(page, { ...INNEHALLET,
    innehall: [{ datum: "2026-11-02", tid: "09:05–10:20", klass: "NA25",
                 kurs: "Matematik, nivå 2c", fran: 207, till: 215, uppg: "", hjalpmedel: "",
                 delar: [{ fran: 207, till: 210, rubrik: "Kubikrötter" },
                         { fran: 211, till: 215, rubrik: "Potenser" }] }] });
  await page.route("**/api/bocker", route => json(route, { bocker: HYLLAN }));
  await vid(page, "2026-11-02");
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await stillaVecka(page);

  const nu = page.locator("#schemagrid article.lekt").filter({ hasText: "NA25" });
  await expect(nu.locator(".lektinnehall"))
    .toHaveText("Kubikrötter, s. 207–210 · Potenser, s. 211–215");

  /* Och momentet — det som går vidare in i prompten — blir hennes ord, inte
     avsnittsnamnet. Tavlan byggdes annars för hela 5.4. */
  await nu.click();
  await expect(page.locator("#moment")).toHaveValue("Kubikrötter · Potenser");
});
