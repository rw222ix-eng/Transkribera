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

/** Servern svarar med `svar` på datagrundens rutter. */
async function fejkaDatagrunden(page, svar = {}) {
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, svar.schema ?? SCHEMA));
}

/** Väntar tills kalendern hämtat schemat. */
async function hydrerad(page) {
  await page.waitForFunction(() => window.Kalender && window.Kalender.franServern());
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

/* Extralektionen. Läraren lägger in en timme som schemat inte har — TE25 en
   torsdag, fast serien ligger på onsdagar. Posten bär klass OCH klockslag, och
   då är den en lektion: den ska gå att välja och planera som alla andra. Förut
   blev den ett dött «Ur kalendern»-kort, och det gick inte att göra vare sig
   tavla eller arbetsblad till den. */
test("en kalenderpost med klass och tid är en lektion, inte bara en notis", async ({ page }) => {
  await fejkaDatagrunden(page, {
    schema: Object.assign({}, SCHEMA, {
      poster: SCHEMA.poster.concat([{
        datum: "2026-08-20", tid: "10:00–11:00", titel: "TE25: Extra räknestuga",
        klass: "TE25" }]),
    }),
  });
  // Samma frysning som ovan: posten ligger torsdagen den 20 augusti.
  await page.clock.install({ time: new Date("2026-08-20T09:00:00") });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();

  const rutnat = page.locator("#schemagrid");
  const extra = rutnat.locator(".lekt", { hasText: "Extra räknestuga" });
  // Ett riktigt lektionskort: klassen, kalenderns egen rubrik, och valbart.
  await expect(extra).toHaveAttribute("data-valjbar", "");
  await expect(extra.locator(".lektklass")).toHaveText("TE25");
  await expect(extra.locator(".lektbokat")).toContainText("Extra räknestuga");
  await expect(extra).not.toContainText("Ur kalendern");
  await extra.click();
  await expect(extra).toHaveAttribute("data-vald", "");

  /* Tre valbara kort: schemats två lektioner plus den extra timmen. Posten UTAN
     klass är ingen lektion och ska fortsatt vara ett postkort man inte kan
     välja, så totalen är fyra. */
  await expect(rutnat.locator(".lekt[data-valjbar]")).toHaveCount(3);
  await expect(rutnat.locator(".lekt")).toHaveCount(4);
  const motet = rutnat.locator(".lekt", { hasText: "Ämneslagsmöte" });
  await expect(motet).toContainText("Ur kalendern");
  await expect(motet).not.toHaveAttribute("data-valjbar", "");
});

test("planeringens väljare erbjuder lärarens klasser och kurser", async ({ page }) => {
  await fejkaDatagrunden(page);
  await page.goto("/");
  await hydrerad(page);

  const val = s => page.locator(s).evaluate(el => [...el.options].map(o => o.textContent));
  await expect.poll(() => val("#p-klass")).toEqual(["Ingen klass", "NA24", "TE25"]);
  expect(await val("#p-kurs")).toEqual(["Ingen kurs", "Matematik, nivå 1c", "Matematik, nivå 2c"]);
});

test("tomt schema ger en tom vecka — appen hittar inte på lektioner", async ({ page }) => {
  await fejkaDatagrunden(page, { schema: { schema: [], lov: [], poster: [] } });
  await page.goto("/");
  await page.waitForFunction(() => window.Kalender && window.Kalender.franServern());

  expect(await page.evaluate(() => window.Kalender.schema)).toEqual([]);
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

/* Sidorna står PÅ lektionen i lärarens kalender — «s. 24–29 · uppg. 2401–2412»
   i beskrivningen — och de gäller den dagen, inte serien. Klickar hon lektionen
   ska planeringen utgå från dem i stället för att räkna fram nästa spann ur
   klassprofilen: läraren har redan svarat på frågan. */
const INNEHALL = [{
  datum: "2026-08-17", tid: "08:15–09:00", klass: "NA24",
  kurs: "Matematik, nivå 2c", fran: 24, till: 29, uppg: "2401–2412",
}];

test("sidorna på lektionen i kalendern blir planeringens förval", async ({ page }) => {
  await fejkaDatagrunden(page);
  await page.route("**/api/schema/synk", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({
      synkad: "2026-08-17T07:00:00", schema: SCHEMA.schema, lov: SCHEMA.lov,
      poster: [], innehall: INNEHALL, konto: "larare@skolan.se",
      bedomda: 0, osakra: 0 }) }));
  // Måndag morgon: veckans lektioner ligger framför läraren, inte bakom.
  await page.clock.install({ time: new Date("2026-08-17T07:00:00") });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.locator("#synkrad [data-synk]").click();
  await expect.poll(() => page.evaluate(() => window.Kalender.innehall.length)).toBe(1);
  /* Synkens kvittotoast ligger fast längst ner i mitten, och med fryst klocka
     försvinner den aldrig av sig själv — låt dess fem sekunder gå ut först. */
  await page.clock.runFor(6000);

  await page.locator("#schemagrid .lekt[data-valjbar]").filter({ hasText: "NA24" })
    .first().click();

  // Uppslaget står på kalenderns sidor — inte på gissningen ur klassprofilen …
  await expect.poll(() => page.evaluate(() => window.Uppslag.spann().fran)).toBe(24);
  expect(await page.evaluate(() => window.Uppslag.spann().till)).toBe(29);
  // … och bokdörren är öppen, så att sidorna följer med i det som skrivs
  // (plan.js bokval() läser Uppslag bara när dörren är öppen).
  await expect(page.locator('.kalla[data-dorr="bok"]'))
    .toHaveAttribute("aria-pressed", "true");
});

test("utan innehåll i kalendern gissar appen som förut", async ({ page }) => {
  await fejkaDatagrunden(page);
  await page.clock.install({ time: new Date("2026-08-17T07:00:00") });
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.locator("#schemagrid .lekt[data-valjbar]").filter({ hasText: "NA24" })
    .first().click();

  // Ett spann sätts — men det är klassprofilens, och det är inte kalenderns.
  const spann = await page.evaluate(() => window.Uppslag.spann());
  expect(spann.fran).toBeGreaterThan(0);
  expect([spann.fran, spann.till]).not.toEqual([24, 29]);
});

test("utan server står prototypen kvar", async ({ page }) => {
  // Designprojektet har ingen server: sonderingen faller, och då är veckan
  // och loven prototypens egna igen.
  await page.route("**/api/var-kors", route => route.abort());
  await page.goto("/");
  await page.waitForFunction(() => window.API && window.API.redo !== null);
  await page.waitForFunction(() => document.documentElement.hasAttribute("data-server") === false);

  expect(await page.evaluate(() => window.Kalender.franServern())).toBe(false);
  expect(await page.evaluate(() => window.Kalender.schema.length)).toBeGreaterThan(0);
});
