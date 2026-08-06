import { expect, test } from "@playwright/test";

/* RÄTTNINGEN — vad klassen tog på provet
 *
 * Siffrorna låg i minnet: «Rättat · 68 %» försvann vid omladdning och källdörr
 * 5 («Läser provets utfall») hade inget att läsa. Etapp 0.7 gav rättningen en
 * backend utan att röra modalen, och fyra saker måste hålla:
 *
 *   1. Raderna är serverns — med provets EGNA förmågor, inte gissningen ur
 *      uppgiftstexten.
 *   2. Siffrorna når servern, och serverns svar är det som står på pappret.
 *   3. Ångra tar bort rättningen där den ligger, inte bara ur vyn.
 *   4. Utfallet följer med in i nästa skrivning — det var hela poängen.
 *
 * Och som alltid: utan server räknar modalen själv, precis som i Claude Design.
 */

const SCHEMA = { schema: [], lov: [], poster: [] };

const UPPGIFTER = [
  { nr: 1, t: "Förklara med egna ord vad derivatan innebär.", p: 2 },
  { nr: 2, t: "Beräkna derivatan.", p: 5, del: ["enkelt fall", "ett mellansteg"] },
  { nr: 3, t: "Visa att sambandet gäller generellt.", p: 3 },
];

const papper = (extra = {}) => ({
  typ: "Prov", moment: "derivata", klass: "NA25", kurs: "Matematik, nivå 2c",
  datum: "2026-09-03", tid: "09:05–10:20", gy: [], kalla: false, kallor: [],
  inst: { antal: 3, nivamix: "Balanserat", delprov: "En del", provtid: "90 min" },
  bilder: {}, referenser: [], forlaga: null, resultat: null, fokus: "",
  kontext: "start", niva: false, svarighet: 0, andrat: [],
  anteckning: "Godkänt", uppgifter: UPPGIFTER, ...extra,
});

const rad = (id, dok) => ({
  id, status: "godkant", markor: 0, sort: id, foljd: null,
  versioner: [dok], dokument: { ...dok, id },
});

/* Serverns rader (app/rattning.py): samma rader som modalen bygger själv, men
   med provets förmågor ur exam_spec — «Problemlösning», inte gissningen
   «Räkning i standardfall» som texten «Beräkna» ger. */
const RADER = [
  { nyckel: "1", kod: "1", nr: "1", text: UPPGIFTER[0].t, p: 2, formaga: "Begrepp" },
  { grupp: true, nr: "2", text: "Beräkna derivatan." },
  { nyckel: "2a", kod: "2a", nr: "a)", text: "enkelt fall", p: 2, formaga: "Problemlösning" },
  { nyckel: "2b", kod: "2b", nr: "b)", text: "ett mellansteg", p: 3, formaga: "Problemlösning" },
  { nyckel: "3", kod: "3", nr: "3", text: UPPGIFTER[2].t, p: 3, formaga: "Resonemang" },
];

/* Serverns svar på ett sparande: den har räknat om siffrorna och lämnar
   tillbaka dem i pappersform. */
const SPARAT = {
  rader: RADER, elever: 22, varden: { "1": 40, "2a": 12 },
  rattat: {
    elever: 22, varden: { "1": 40, "2a": 12 }, andel: 0.42,
    svaga: [{ kod: "2a", formaga: "Problemlösning", text: "enkelt fall", andel: 0.27 }],
  },
};

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

async function fejka(page, { sparade = [], sparad = null } = {}) {
  const anrop = [];
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade, utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, rad(1, papper())));
  await page.route("**/api/planning/**", route => {
    anrop.push({ metod: "POST", vag: new URL(route.request().url()).pathname,
                 kropp: route.request().postDataJSON() });
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: "abc123def456", errors: [], rounds: 1,
        board: { title: "Derivata", boards: [{
          name: "teori", width: 900, height: 780, chrome: "aluminium",
          padding: { top: 24, right: 26, bottom: 24, left: 30 },
          sections: [{ kind: "heading", text: "Derivata", size: 30 }] }] } } }]) });
  });
  // Rättningen registreras SIST: Playwright provar de senast tillagda först,
  // och den generella dokumentvägen ovan matchar annars den här också.
  await page.route("**/api/dokument/*/rattning", route => {
    const r = route.request();
    anrop.push({ metod: r.method(), vag: new URL(r.url()).pathname,
                 kropp: r.method() === "PUT" ? r.postDataJSON() : null });
    if (r.method() === "PUT") return json(route, SPARAT);
    if (r.method() === "DELETE") return json(route, { ok: true });
    return json(route, sparad || { rader: RADER, elever: 22, varden: {}, rattat: null });
  });
  return anrop;
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

/** Öppnar rättningen på det första sparade pappret (chipet i veckan gör
 *  samma sak: window.Rattning.oppna(provet)). */
const oppna = page => page.evaluate(() =>
  window.Rattning.oppna(window.Dokument.sparade()[0]));

const skriv = (page, falt, varde) =>
  page.locator(`.rattrad[data-nyckel="${falt}"] .rattfalt`).fill(String(varde));

test("raderna är serverns — förmågan är provets egen", async ({ page }) => {
  await fejka(page, { sparade: [rad(1, papper())] });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  await oppna(page);

  // Deluppgifterna får varsin rad, med gruppubriken över.
  await expect(page.locator("#rattninglista .rattrad")).toHaveCount(4);
  await expect(page.locator("#rattninglista .rattgrupp")).toHaveCount(1);
  // Serverns poäng: 5 p delat på två delar blir 2 + 3, resten på den sista.
  await expect(page.locator('.rattrad[data-nyckel="2b"] .rattmax')).toHaveText("66 p");

  await skriv(page, "1", 40);
  await skriv(page, "2a", 12);
  // Analysen namnger provets förmåga, inte den gissade («Räkning i standardfall»).
  await expect(page.locator("#rattsvaga")).toContainText("Problemlösning");
  await expect(page.locator("#rattsvaga")).not.toContainText("Räkning i standardfall");
});

test("siffrorna når servern och serverns svar står på pappret", async ({ page }) => {
  const anrop = await fejka(page, { sparade: [rad(1, papper())] });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  await oppna(page);

  await skriv(page, "1", 40);
  await skriv(page, "2a", 12);
  await page.locator("#rattningspara").click();

  await expect.poll(() => anrop.filter(a => a.metod === "PUT").length).toBe(1);
  const put = anrop.find(a => a.metod === "PUT");
  expect(put.vag).toBe("/api/dokument/1/rattning");
  expect(put.kropp.varden).toEqual({ "1": 40, "2a": 12 });
  expect(put.kropp.elever).toBe(22);

  // Serverns siffra vinner: den läste pappret ur databasen.
  await expect.poll(() => page.evaluate(() =>
    (window.Dokument.sparade()[0].rattat || {}).andel)).toBe(0.42);
});

test("ångra tar bort rättningen där den ligger", async ({ page }) => {
  const anrop = await fejka(page, { sparade: [rad(1, papper())] });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  await oppna(page);

  await skriv(page, "1", 40);
  await skriv(page, "2a", 12);
  await page.locator("#rattningspara").click();
  await page.locator(".toast button", { hasText: "Ångra" }).click();

  await expect.poll(() => anrop.some(a => a.metod === "DELETE")).toBe(true);
  await expect.poll(() => page.evaluate(() =>
    window.Dokument.sparade()[0].rattat)).toBe(null);
});

test("ett rättat prov öppnas med sina siffror kvar", async ({ page }) => {
  await fejka(page, {
    sparade: [rad(1, papper())],
    sparad: { rader: RADER, elever: 18, varden: { "1": 30 }, rattat: SPARAT.rattat },
  });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  await oppna(page);

  await expect(page.locator("#rattelever")).toHaveValue("18");
  await expect(page.locator('.rattrad[data-nyckel="1"] .rattfalt')).toHaveValue("30");
});

test("utfallet följer med in i nästa skrivning", async ({ page }) => {
  const anrop = await fejka(page, {
    sparade: [rad(1, papper({ rattat: SPARAT.rattat }))],
  });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);

  // Källdörr 5: det rättade provet väljs som utgångspunkt.
  await page.evaluate(() => window.Dokument.sattResultat(window.Dokument.sparade()[0]));
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => {
    window.SattLage("Tavla");
    const f = document.querySelector("#moment");
    f.value = "derivata";
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  });
  await page.locator("#skriv").click();

  await expect.poll(() => anrop.some(a => a.vag && a.vag.endsWith("/generate")),
                    { timeout: 15_000 }).toBe(true);
  const gen = anrop.find(a => a.vag && a.vag.endsWith("/generate"));
  // Id:t är den sanna vägen — servern läser sin egen rättning. Siffrorna
  // följer med för pappret som aldrig nått databasen.
  expect(gen.kropp.utfall_dokument_id).toBe(1);
  expect(gen.kropp.utfall.rattat.svaga[0].kod).toBe("2a");
});

test("utan server räknar modalen själv, som förut", async ({ page }) => {
  await page.route("**/api/var-kors", route => route.abort());
  const natanrop = [];
  await page.route("**/api/dokument/**", route => {
    natanrop.push(route.request().url());
    route.abort();
  });
  await page.goto("/");
  await page.waitForFunction(() => document.documentElement.hasAttribute("data-server") === false);
  await page.evaluate(u => window.Rattning.oppna({
    typ: "Prov", moment: "derivata", klass: "NA25", uppgifter: u,
  }), UPPGIFTER);

  await expect(page.locator("#rattninglista .rattrad")).toHaveCount(4);
  await skriv(page, "1", 40);
  await skriv(page, "2a", 12);
  // Prototypens gissning ur uppgiftstexten står kvar — den är sann om den.
  await expect(page.locator("#rattsvaga")).toContainText("Räkning i standardfall");
  expect(natanrop).toEqual([]);
});
