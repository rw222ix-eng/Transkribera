import { expect, test } from "@playwright/test";

/* ELEV FÖR ELEV — poängen per nivå, betyget live, klassen på köpet
 *
 * Klassrättningen kan bara en summa per uppgift. Den räcker för planeringen och
 * inte för eleven: ett betyg går inte att räkna ur en klumpsumma, för C kräver
 * sin andel av C- och A-poängen. Fyra saker måste hålla:
 *
 *   1. Klasslistan frågas EN gång och sparas.
 *   2. Hela rättningen går på tangentbordet — siffertangent sätter poäng,
 *      Enter går till nästa elev.
 *   3. Betyget står på skärmen medan man klickar, och F skrivs ut som alla
 *      andra betyg.
 *   4. Klassens siffra hamnar på kortet i Sparat utan att någon skrivit in den
 *      — det är hela poängen med att räkna aggregatet ur eleverna.
 *
 * Och som alltid: utan server går allt ändå, med prototypens egna elever.
 */

const SCHEMA = { schema: [], lov: [], poster: [] };

const UPPGIFTER = [
  { nr: 1, t: "Beräkna arean av triangeln.", p: 2, peca: [2, 0, 0] },
  { nr: 2, t: "Avgör om påståendet är sant.", p: 3, peca: [0, 2, 1] },
];

const papper = (extra = {}) => ({
  typ: "Prov", moment: "derivata", klass: "NA25", kurs: "Matematik, nivå 2c",
  datum: "2026-09-03", tid: "09:05–10:20", gy: [], kalla: false, kallor: [],
  bilder: {}, referenser: [], forlaga: null, resultat: null, fokus: "",
  kontext: "start", niva: false, svarighet: 0, andrat: [],
  anteckning: "Godkänt", uppgifter: UPPGIFTER, ...extra,
});

const rad = (id, dok) => ({
  id, status: "godkant", markor: 0, sort: id, foljd: null,
  versioner: [dok], dokument: { ...dok, id },
});

/* Serverns rader: samma rader som modalen bygger själv, med radens maxpoäng
   per nivå. 5 p totalt — 2 E, 2 C, 1 A. */
const RADER = [
  { nyckel: "1", kod: "1", nr: "1", text: UPPGIFTER[0].t, p: 2,
    peca: [2, 0, 0], formaga: "Räkning i standardfall" },
  { nyckel: "2", kod: "2", nr: "2", text: UPPGIFTER[1].t, p: 3,
    peca: [0, 2, 1], formaga: "Resonemang" },
];

/* Kravgränserna ur exakt samma regel som försättsbladet trycker. */
const GRANSER = {
  total: 5, E: { minst: 2 }, C: { minst: 3, varav_ca: 1 },
  A: { minst: 4, varav_a: 1 },
};

const ELEVER = [{ id: 11, namn: "Anna Andersson", sort: 0, aktiv: true },
                { id: 12, namn: "Bo Bergström", sort: 1, aktiv: true }];

/* Hon har slutat men skrev PROVET. db.list_elever skickar med henne med flit,
   och save_elever svarar med samma lista — inaktiva och allt. */
const SLUTAT = { id: 13, namn: "Cissi Colding", sort: 2, aktiv: false };
const SKREV_SLUTAT = { 13: { 1: [2, null, null], 2: [null, 2, 1] } };

const TOMT = { group_id: 1, klass: "NA25", rader: RADER, granser: GRANSER,
               elever: [], resultat: {}, summor: {}, betyg: {}, feedback: {} };

/* CI-profilen som app/ci_profil.py räknar den: svagast först, och `styrka`
   satt av servern (frontenden ska aldrig sätta sin egen tröskel). */
const ELEVPROFIL = {
  elev_id: 11, kurs: "Matematik, nivå 2c", dokument: 2, utan_ci: 0, matt: true,
  punkter: [
    { kod: "G25-M2C-ALG-6", kort: "Andragradsekvationer", andel: 0.25,
      styrka: "svag", tagna: 1, max: 4, dokument: 2, niva: {} },
    { kod: "G25-M2C-STA-1", kort: "Lägesmått och spridning", andel: 0.9,
      styrka: "stark", tagna: 9, max: 10, dokument: 1, niva: {} },
  ],
};
const KLASSPROFIL = { ...ELEVPROFIL, group_id: 1, elev_id: undefined,
  punkter: [{ kod: "G25-M2C-GEO-2", kort: "Sats och bevis", andel: 0.4,
              styrka: "svag", tagna: 8, max: 20, dokument: 2, niva: {} }] };

/* `klass` är vad PUT /elever svarar — serverns hela klasslista, inte bara de
   aktiva. `resultat` är poängen som redan ligger i basen. */
async function fejka(page, { elever = [], resultat = {}, klass = ELEVER } = {}) {
  const anrop = [];
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route =>
    json(route, { sparade: [rad(1, papper())], utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, rad(1, papper())));
  await page.route("**/api/groups/*/elever", route => {
    const r = route.request();
    anrop.push({ metod: r.method(), vag: new URL(r.url()).pathname,
                 kropp: r.method() === "PUT" ? r.postDataJSON() : null });
    return json(route, { elever: klass });
  });
  /* Elevresultatet registreras SIST: Playwright provar de senast tillagda
     först, och den generella dokumentvägen ovan matchar annars den här med. */
  await page.route("**/api/dokument/*/elevresultat", route => {
    const r = route.request();
    anrop.push({ metod: r.method(), vag: new URL(r.url()).pathname,
                 kropp: r.method() === "PUT" ? r.postDataJSON() : null });
    if (r.method() === "DELETE") return json(route, { ok: true });
    if (r.method() === "PUT") {
      return json(route, { ...TOMT, elever: ELEVER,
        resultat: r.postDataJSON().resultat,
        rattat: { elever: 2, varden: { "1": 3, "2": 3 }, andel: 0.6, svaga: [] } });
    }
    return json(route, { ...TOMT, elever, resultat });
  });
  /* CI-profilen (Etapp 3): elevens och klassens centrala innehåll, svagast
     först. Registreras efter elevresultatet av samma skäl — Playwright provar
     de senast tillagda mönstren först. */
  await page.route("**/ci-profil*", route => {
    const vag = new URL(route.request().url()).pathname;
    anrop.push({ metod: "GET", vag });
    return json(route, vag.includes("/groups/") ? KLASSPROFIL : ELEVPROFIL);
  });
  return anrop;
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

const oppna = page => page.evaluate(() =>
  window.Elever.oppna(window.Dokument.sparade()[0]));

/** Rättar en elev med enbart tangentbordet: fokus på första knappen, sedan en
 *  siffra per nivågrupp. Varje siffra flyttar fokus till nästa grupp själv. */
async function knappa(page, siffror) {
  await page.locator("#elevrader .elevknapp").first().focus();
  for (const s of siffror) await page.keyboard.press(String(s));
}

test("klasslistan frågas en gång och sparas", async ({ page }) => {
  const anrop = await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  await oppna(page);

  // Ingen klass ännu: textarean, inte rättningen.
  await expect(page.locator("#elevklass")).toBeVisible();
  await expect(page.locator("#elevvy")).toBeHidden();
  await page.locator("#elevnamnfalt").fill("Anna Andersson\nBo Bergström");
  await page.locator("#elevsparaklass").click();

  const put = anrop.find(a => a.metod === "PUT" && a.vag.endsWith("/elever"));
  expect(put.kropp.namn).toEqual(["Anna Andersson", "Bo Bergström"]);
  // Och sedan visas den aldrig oombedd igen.
  await expect(page.locator("#elevklass")).toBeHidden();
  await expect(page.locator("#elevnamn")).toHaveText("Anna Andersson");
  await expect(page.locator("#elevmeta")).toContainText("Elev 1 av 2");
});

test("den som slutat men skrev provet överlever att klasslistan sparas om", async ({ page }) => {
  /* Poängen finns kvar i basen vad läraren än gör med klasslistan: de PUT:as
     tillbaka och räknas in i klassandelen. Göms hon i bandet är de räknade men
     osynliga — går varken att öppna, rätta eller rensa. Urvalet måste därför
     vara detsamma när listan LÄSES och när den SPARAS OM. */
  await fejka(page, { elever: [...ELEVER, SLUTAT], resultat: SKREV_SLUTAT,
                      klass: [...ELEVER, SLUTAT] });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  await oppna(page);

  await expect(page.locator("#elevband .elevprick")).toHaveCount(3);
  await expect(page.locator("#elevband .elevprick[data-slutat]")).toHaveText("Cissi Colding");

  // Ändra klasslistan → Spara, utan att röra namnen.
  await page.locator("#elevbytklass").click();
  // Fältet bär bara de aktiva — annars hade ett Spara väckt henne till liv igen.
  await expect(page.locator("#elevnamnfalt")).toHaveValue("Anna Andersson\nBo Bergström");
  await page.locator("#elevsparaklass").click();

  await expect(page.locator("#elevklass")).toBeHidden();
  await expect(page.locator("#elevband .elevprick")).toHaveCount(3);
  await expect(page.locator("#elevband .elevprick[data-slutat]")).toHaveText("Cissi Colding");
  // Och hon går att öppna: poängen syns och kan rensas.
  await page.locator("#elevband .elevprick[data-slutat]").click();
  await expect(page.locator("#elevnamn")).toHaveText("Cissi Colding · har slutat");
  await expect(page.locator("#elevsumma")).toHaveText("5 av 5 p");
  await expect(page.locator("#elevtom")).toBeEnabled();
});

test("Excel-inklistringen varnar inte falskt — men en kortare lista varnar", async ({ page }) => {
  const anrop = await fejka(page, { elever: ELEVER });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  await oppna(page);
  const puts = () => anrop.filter(a => a.metod === "PUT" && a.vag.endsWith("/elever"));

  /* Först den varning som SKA komma: fältet ersätter listan, och en halv
     inklistring får inte tyst inaktivera resten av klassen. */
  await page.locator("#elevbytklass").click();
  await page.locator("#elevnamnfalt").fill("Anna Andersson");
  await page.locator("#elevsparaklass").click();
  await expect(page.locator("#elevklassnot")).toContainText("Bo Bergström");
  expect(puts()).toHaveLength(0);

  /* Och så den som INTE ska komma. Ur Excel följer personnummer och klasskod
     med i egna kolumner; servern (klasslista._namnkolumn) plockar bort dem och
     lagrar «Anna Andersson». Räknar klienten diffen på en egen, förenklad
     städning matchar ingen enda lagrad elev, och noten påstår att hela klassen
     försvinner — trycker läraren igen sparas allt korrekt, alltså en varning
     som lär läraren att varningar ljuger. */
  await page.locator("#elevnamnfalt").fill(
    "Anna Andersson\t20050101-1234\tNA25\nBo Bergström\t20050202-2345\tNA25");
  await page.locator("#elevsparaklass").click();

  await expect(page.locator("#elevklass")).toBeHidden();
  expect(puts()).toHaveLength(1);
  // Raderna skickas OSTÄDADE — städningen är serverns, klienten bara speglar den.
  expect(puts()[0].kropp.namn).toEqual([
    "Anna Andersson\t20050101-1234\tNA25", "Bo Bergström\t20050202-2345\tNA25"]);
  await expect(page.locator("#elevband .elevprick")).toHaveCount(2);
  // Ingen falsk «2 rader ströks» heller: två inklistrade rader blev två elever.
  await expect(page.locator("#elevnot")).not.toContainText("ströks");
});

test("hela rättningen går på tangentbordet och betyget står live", async ({ page }) => {
  await fejka(page, { elever: ELEVER });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  await oppna(page);
  await expect(page.locator("#elevvy")).toBeVisible();

  // En knappgrupp per nivå som HAR poäng: uppgift 1 bara E, uppgift 2 C och A.
  await expect(page.locator('.elevrad[data-nyckel="1"] .elevgrupp')).toHaveCount(1);
  await expect(page.locator('.elevrad[data-nyckel="2"] .elevgrupp')).toHaveCount(2);
  // Betyget hålls tillbaka tills allt är ifyllt — halvt prov, inget betyg.
  await expect(page.locator("#elevbetyg")).toHaveText("—");

  await knappa(page, [2, 2, 1]);                  // 5 av 5 p
  await expect(page.locator("#elevbetyg")).toHaveText("A");
  await expect(page.locator("#elevsumma")).toHaveText("5 av 5 p");

  // Enter går till nästa elev.
  await page.keyboard.press("Enter");
  await expect(page.locator("#elevnamn")).toHaveText("Bo Bergström");
  await expect(page.locator("#elevbetyg")).toHaveText("—");

  // F skrivs ut som alla andra betyg — inget tomt fält, ingen omskrivning.
  await knappa(page, [1, 0, 0]);
  await expect(page.locator("#elevbetyg")).toHaveText("F");
});

test("klassbilden visar hela klassen — också det osparade", async ({ page }) => {
  await fejka(page, { elever: ELEVER });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  await oppna(page);
  await knappa(page, [2, 2, 1]);                  // Anna: 5 av 5 → A, osparat

  await page.locator("#elevvisaoversikt").click();
  await expect(page.locator("#elevoversikt")).toBeVisible();
  await expect(page.locator("#elevvy")).toBeHidden();
  const rader = page.locator("#elevtabellrader tr");
  await expect(rader).toHaveCount(2);
  await expect(rader.nth(0)).toContainText("Anna Andersson");
  // Bilden läser skärmens siffror, inte serverns — inget är sparat än.
  await expect(rader.nth(0).locator(".etbetyg")).toHaveText("A");
  await expect(rader.nth(1).locator(".etbetyg")).toHaveText("skrev inte");
  await expect(page.locator("#elevoversiktnot")).toContainText("1 av 2");

  // Raden är en väg in: klick öppnar eleven i rättningsvyn.
  await rader.nth(1).click();
  await expect(page.locator("#elevvy")).toBeVisible();
  await expect(page.locator("#elevnamn")).toHaveText("Bo Bergström");
});

test("klassens siffra hamnar på kortet utan att någon skrivit in den", async ({ page }) => {
  const anrop = await fejka(page, { elever: ELEVER });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  await oppna(page);

  await knappa(page, [2, 2, 1]);
  await page.keyboard.press("Enter");
  await knappa(page, [1, 0, 0]);
  await page.locator("#elevspara").click();

  /* Elevbytet autosparar tyst (förlustskyddet), så första PUT:en bär bara
     Anna. Kontraktet här är Spara-knappens: SISTA anropet bär hela klassen. */
  const puts = anrop.filter(a => a.metod === "PUT" && a.vag.endsWith("/elevresultat"));
  const put = puts[puts.length - 1];
  expect(put.vag).toBe("/api/dokument/1/elevresultat");
  expect(put.kropp.resultat["11"]).toEqual({ "1": [2, null, null], "2": [null, 2, 1] });
  expect(put.kropp.resultat["12"]).toEqual({ "1": [1, null, null], "2": [null, 0, 0] });

  /* Klassrättningen räknades ur elevernas och skrevs rakt på pappret. Det är
     den chipet «Rättat · NN %» läser (klass.js) — chipet självt sitter på
     lektionen i klassvyn och kräver en lektion att sitta på, så det som mäts
     här är siffran det visar. */
  await expect.poll(() => page.evaluate(() =>
    (window.Dokument.sparade()[0].rattat || {}).andel)).toBe(0.6);
  expect(await page.evaluate(() =>
    `Rättat · ${Math.round(window.Dokument.sparade()[0].rattat.andel * 100)} %`))
    .toBe("Rättat · 60 %");

  // Ångra tar bort den där den ligger, inte bara ur vyn.
  await page.locator(".toast button", { hasText: "Ångra" }).click();
  await expect.poll(() => anrop.some(a => a.metod === "DELETE")).toBe(true);
  await expect.poll(() => page.evaluate(() =>
    window.Dokument.sparade()[0].rattat)).toBe(null);
});

test("utan server går elevläget ändå, med prototypens klass", async ({ page }) => {
  await page.route("**/api/var-kors", route => route.abort());
  const natanrop = [];
  await page.route("**/api/**", route => {
    natanrop.push(route.request().url());
    route.abort();
  });
  await page.goto("/");
  await page.waitForFunction(() =>
    document.documentElement.hasAttribute("data-server") === false);
  await page.evaluate(u => window.Elever.oppna({
    typ: "Prov", moment: "derivata", klass: "NA25", uppgifter: u,
  }), UPPGIFTER);

  await expect(page.locator("#elevvy")).toBeVisible();
  await expect(page.locator("#elevband .elevprick")).toHaveCount(6);
  await knappa(page, [2, 2, 1]);
  await expect(page.locator("#elevbetyg")).toHaveText("A");
  await page.locator("#elevspara").click();
  await expect(page.locator(".toast")).toContainText("Sparat");
  expect(natanrop.filter(u => u.includes("elevresultat"))).toEqual([]);
});

test("CI-profilen står under rättningen — svagast först, och klassen bredvid", async ({ page }) => {
  await fejka(page, { elever: ELEVER });
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  await oppna(page);

  /* Rättningen ovanför säger hur det gick på DET HÄR pappret. Profilen säger
     vad som brister i kursen — och den ska stå där läraren redan tittar. */
  const rader = page.locator("#elevcilista .elevcirad");
  await expect(rader).toHaveCount(2, { timeout: 15_000 });
  await expect(rader.first().locator(".elevcinamn")).toHaveText("Andragradsekvationer");
  await expect(rader.first()).toHaveAttribute("data-styrka", "svag");
  await expect(rader.first().locator(".elevciandel")).toHaveText("25 %");
  await expect(rader.last()).toHaveAttribute("data-styrka", "stark");
  await expect(page.locator("#elevcinot")).toContainText("1 punkt under 50 %");
  await expect(page.locator("#elevcinot")).toContainText("2 rättade papper");

  // Klassen är samma aggregat, annat urval — underlaget för gemensam repetition.
  await page.locator('[data-seg="civem"] button', { hasText: "Klassen" }).click();
  await expect(page.locator("#elevcilista .elevcirad")).toHaveCount(1);
  await expect(page.locator("#elevcilista .elevcinamn")).toHaveText("Sats och bevis");
});

test("utan CI-data står det så — aldrig noll procent", async ({ page }) => {
  await fejka(page, { elever: ELEVER });
  /* Papper rättade före Etapp 1 bär inga koder. Ett «0 %» där hade sett ut som
     ett mätvärde på en elev som aldrig prövats på punkten. */
  await page.route("**/ci-profil*", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ punkter: [], dokument: 1, utan_ci: 4, matt: false }) }));
  await page.goto("/");
  await hydrerad(page);
  await expect.poll(() => page.evaluate(() => window.Dokument.sparade().length)).toBe(1);
  await oppna(page);

  await expect(page.locator("#elevcilista .elevcirad")).toHaveCount(0);
  await expect(page.locator("#elevcinot")).toContainText("Ingen CI-data", { timeout: 15_000 });
});
