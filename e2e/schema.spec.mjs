import { expect, test } from "@playwright/test";

/* DATAGRUNDEN — schemat, loven, posterna och arkivet
 *
 * Frontenden är designprototypen: veckoschemat, loven och inspelningskorten
 * står hårdkodade i kalender.js och app.html så att den går att visa utan
 * server. Etapp 0.1 bytte datakällan, inte designen — och det som måste hålla
 * är därför exakt två saker:
 *
 *   1. Med server är det SERVERNS data som ritas. Står prototypens lektioner
 *      kvar ser appen rätt ut och visar fel vecka, vilket är värre än en tom.
 *   2. Utan server står prototypen kvar. Designprojektet har ingen server.
 *
 * Servern som sviten startar är äkta men tom, så svaren fejkas med page.route
 * i stället för att skrivas in i användarens riktiga databas.
 */

const SCHEMA = {
  schema: [
    { dag: 1, tid: "08:15–09:00", kurs: "Matematik, nivå 2c", klass: "NA24", sal: "C112" },
    { dag: 3, tid: "10:15–11:00", kurs: "Matematik, nivå 1c", klass: "TE25", sal: "C112" },
  ],
  lov: [{ fran: "2026-10-26", till: "2026-10-30", namn: "Höstlov", typ: "lov" }],
  poster: [{ datum: "2026-08-20", tid: "13:00–14:30", titel: "Ämneslagsmöte", klass: "" }],
};

const LEKTIONER = [
  { history_id: "h2", datum: "2026-08-05", ts: "2026-08-05T10:15:00", name: "Andragradsekvationer",
    dur: "41:02", lang: "Svenska", group: "NA24", course: "Matematik, nivå 2c" },
  { history_id: "h1", datum: "2026-07-29", ts: "2026-07-29T08:15:00", name: "Enhetscirkeln",
    dur: "38:20", lang: "Engelska", group: "TE25", course: "Matematik, nivå 1c" },
];

const HISTORIK = [
  { id: "h2", name: "Andragradsekvationer", lang: "Svenska", target_lang: "Svenska", video: null },
  { id: "h1", name: "Enhetscirkeln", lang: "Engelska", target_lang: "Svenska",
    video: { path: "C:/x/e.mp4" } },
];

/** Servern svarar med `svar` på datagrundens rutter. */
async function fejkaDatagrunden(page, svar = {}) {
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, svar.schema ?? SCHEMA));
  await page.route("**/api/lessons", route => json(route, svar.lektioner ?? LEKTIONER));
  await page.route("**/api/history", route => json(route, svar.historik ?? HISTORIK));
}

/** Väntar tills kalendern hämtat schemat och arkivet ritats om. */
async function hydrerad(page) {
  await page.waitForFunction(() => window.Kalender && window.Kalender.franServern());
  await page.waitForFunction(() =>
    !document.querySelector('#inspelningar .kort .namn')
    || ![...document.querySelectorAll('#inspelningar .kort .namn')]
        .some(n => n.textContent.includes("Trigonometriska")));
}

test("veckoschemat kommer från servern, inte ur kalender.js", async ({ page }) => {
  await fejkaDatagrunden(page);
  /* Klockan fryses: kalenderposten nedan ligger den 20 augusti, och veckan
     appen öppnar är den som schemat och LOVEN pekar ut. Utan frysning berodde
     testet på vilken dag sviten råkade köras — det gick igenom i augusti 2026
     och började falla dagen efter. */
  await page.clock.install({ time: new Date("2026-08-20T09:00:00") });
  await page.goto("/");
  await hydrerad(page);

  const schema = await page.evaluate(() => window.Kalender.schema);
  expect(schema).toEqual(SCHEMA.schema);
  // Prototypens klasser får inte ligga kvar bredvid lärarens riktiga.
  expect(schema.some(s => s.klass === "9A")).toBe(false);

  // Och veckan RITAS ur det: schemats två lektioner får sin sal, och
  // kalenderposten står som «Ur kalendern» — tre kort, tre olika ursprung.
  await page.getByRole("tab", { name: "Planering" }).click();
  const rutnat = page.locator("#schemagrid");
  await expect(rutnat.locator(".lekt")).toHaveCount(3);
  await expect(rutnat.locator(".lektsal")).toHaveText(["C112", "C112"]);
  await expect(rutnat.locator(".lekt", { hasText: "Ämneslagsmöte" })).toContainText("Ur kalendern");
});

test("arkivets kort är lärarens lektioner, inte app.html:s", async ({ page }) => {
  await fejkaDatagrunden(page);
  await page.goto("/");
  await hydrerad(page);

  const namn = await page.locator("#inspelningar .kort .namn").allTextContents();
  expect(namn).toEqual(["Andragradsekvationer", "Enhetscirkeln"]);

  // Varje kort ligger i sin ISO-vecka, med sin klass och sin kurs.
  const kort = page.locator('#inspelningar .kort', { hasText: "Enhetscirkeln" });
  await expect(kort).toHaveAttribute("data-datum", "2026-07-29");
  await expect(kort).toHaveAttribute("data-klass", "TE25");
  await expect(kort.locator(".sprakmark")).toHaveText("Engelska → svenska");
  // Historikens `video` avgör tummen — inte en gissning ur filnamnet.
  await expect(kort.locator('.tumme[data-typ="video"]')).toHaveCount(1);
  await expect(page.locator('#inspelningar .kort', { hasText: "Andragradsekvationer" })
    .locator('.tumme[data-typ="ljud"]')).toHaveCount(1);
});

test("filtren erbjuder lärarens klasser och kurser", async ({ page }) => {
  await fejkaDatagrunden(page);
  await page.goto("/");
  await hydrerad(page);

  const val = s => page.locator(s).evaluate(el => [...el.options].map(o => o.textContent));
  expect(await val("#f-klass")).toEqual(["Alla klasser", "NA24", "TE25"]);
  expect(await val("#f-kurs")).toEqual(["Alla kurser", "Matematik, nivå 1c", "Matematik, nivå 2c"]);
});

test("tomt schema ger en tom vecka — appen hittar inte på lektioner", async ({ page }) => {
  await fejkaDatagrunden(page, {
    schema: { schema: [], lov: [], poster: [] }, lektioner: [], historik: [] });
  await page.goto("/");
  await page.waitForFunction(() => window.Kalender && window.Kalender.franServern());

  expect(await page.evaluate(() => window.Kalender.schema)).toEqual([]);
  await expect(page.locator("#inspelningar .kort")).toHaveCount(0);
  // Prototypens 9A/9B får inte smyga tillbaka som "bättre än inget".
  expect(await page.evaluate(() => window.Kalender.poster)).toEqual([]);
});

test("en post läraren godtar skickas till servern", async ({ page }) => {
  await fejkaDatagrunden(page);
  const skickat = [];
  await page.route("**/api/kalenderposter", route => {
    skickat.push(JSON.parse(route.request().postData() || "{}"));
    route.fulfill({ status: 200, contentType: "application/json",
                    body: route.request().postData() });
  });
  await page.goto("/");
  await hydrerad(page);

  await page.evaluate(() => window.Kalender.lagg({
    datum: "2026-09-03", tid: "08:15–09:00", titel: "Prov Matematik 3c", klass: "NA24",
    slag: "prov" }));
  await expect.poll(() => skickat.length).toBe(1);
  expect(skickat[0].titel).toBe("Prov Matematik 3c");
  expect(skickat[0].slag).toBe("prov");
});

test("synkknappen läser om schemat ur Google", async ({ page }) => {
  await fejkaDatagrunden(page);
  await page.route("**/api/schema/synk", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({
      synkad: "2026-08-06T09:00:00",
      schema: [{ dag: 2, tid: "09:15–10:00", kurs: "Matematik, nivå 2c", klass: "NA24", sal: "C201" }],
      lov: SCHEMA.lov, poster: [], konto: "larare@skolan.se", bedomda: 2, osakra: 2 }) }));
  await page.goto("/");
  await hydrerad(page);

  await page.locator("#vy-planering").waitFor({ state: "attached" });
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.locator("#synkrad [data-synk]").click();

  await expect.poll(() => page.evaluate(() => window.Kalender.schema.length)).toBe(1);
  expect(await page.evaluate(() => window.Kalender.schema[0].sal)).toBe("C201");
  /* Beskedet ska säga VAD som lästes om och UR VEMS kalender — ett blankt
     «synkad» såg likadant ut när schemat kom ur fel konto (klass.js). */
  await expect(page.locator(".toast")).toContainText("synkad ur larare@skolan.se");
  await expect(page.locator(".toast")).toContainText("1 lektion i veckoschemat");
  // Det reglerna inte kunde avgöra läste Claude — det ska stå, inte döljas.
  await expect(page.locator(".toast")).toContainText("2 poster tolkade av Claude");
});

test("utan server står prototypen kvar", async ({ page }) => {
  // Designprojektet har ingen server: sonderingen faller, och då är veckan,
  // loven och korten prototypens egna igen.
  await page.route("**/api/var-kors", route => route.abort());
  await page.goto("/");
  await page.waitForFunction(() => window.API && window.API.redo !== null);
  await page.waitForFunction(() => document.documentElement.hasAttribute("data-server") === false);

  expect(await page.evaluate(() => window.Kalender.franServern())).toBe(false);
  expect(await page.evaluate(() => window.Kalender.schema.length)).toBeGreaterThan(0);
  await expect(page.locator("#inspelningar .kort", { hasText: "Trigonometriska ettan" }))
    .toHaveCount(1);
});
