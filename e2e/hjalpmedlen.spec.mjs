import { expect, test } from "@playwright/test";
import * as L from "./larardag.mjs";

/* HJÄLPMEDLEN PER PROVDEL ÄR ETT VAL I PLANERINGEN
 *
 * Spåret 2026-09-06: Rickard skrev «formelblad ska vara tillåtet på del A och
 * B» tre gånger på två prov samma dag (13:17, 14:32, 15:31), och första gången
 * kostade det ett bortkastat omskrivningsvarv. Regeln fanns nämligen inte att
 * välja: den stod hårdkodad i prompten och i blad.js («Del A utan digitala
 * hjälpmedel, Del B räknare»), så enda vägen dit var att be modellen skriva om
 * hela pappret — och det ändrade bara PDF:ens försättsblad.
 *
 * Tre påståenden prövas, i den ordning felet uppstod:
 *
 *   1. Raderna finns i panelen, och del B:s rad följer upplägget: «En del» är
 *      ett prov med en enda hjälpmedelsregel.
 *   2. Valet NÅR SERVERN — men bara när det avviker. Ett orört val ska ge
 *      exakt den begäran som gick i väg innan raden fanns (kassettregeln;
 *      tests/test_hjalpmedel.py bevakar prompten, det här bevakar kroppen).
 *   3. Skärmen visar valet. Tiger dokumentet om hjälpmedlen är det
 *      planeringens val som står i provtabellen, inte husets gamla fras.
 *
 * Bara /api/exams/generate är fejkad — resten är den riktiga servern, precis
 * som i formerna.spec.mjs. Provet som kommer tillbaka har TOMT `hjalpmedel`
 * med flit: det är då skärmen ska falla tillbaka på planeringens val.
 */

const PROV = {
  titel: "Prov", kurs: "Matematik, nivå 2c", klass: "NA25", tid_min: 90,
  hjalpmedel: "",
  uppgifter: [
    { del: "B", formaga: "P", typ: "rutin", poang: [2, 0, 0],
      text: "Beräkna $3^2$.", losning: "$9$", bedomning: "+2 E" },
    { del: "C", formaga: "PL", typ: "problem", poang: [0, 2, 0],
      text: "Bestäm skärningspunkten mellan linjerna.", losning: "$(1, 2)$",
      bedomning: "+2 C" },
  ],
};

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

/** Fejkar generatorrutten och samlar kropparna. */
async function fejkaGenerate(page) {
  const anrop = [];
  await page.route("**/api/exams/generate", route => {
    anrop.push(route.request().postDataJSON());
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: 7, exam: PROV, typ: "prov", status: "utkast", errors: [], rounds: 1,
        granser: { total: 4, E: { minst: 1 },
                   C: { minst: 2, varav_ca: 1 },
                   A: { minst: 3, varav_a: 1 } },
        summor: { total: 4, e: 2, c: 2, a: 0 } } }]) });
  });
  return anrop;
}

/** Planeringen öppnad på ett prov, med klass, kurs och moment ifyllda —
 *  samma gest som larardag.skriv gör, men utan att trycka Skriv: hela poängen
 *  här är vad som händer i panelen INNAN knappen. */
async function provpanelen(page) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => {
    window.SattLage("Prov");
    const satt = (id, v) => {
      const e = document.querySelector(id);
      if (!e) return;
      if (e.tagName === "SELECT"
          && ![...e.options].some(o => o.value === v || o.textContent === v)) {
        e.appendChild(Object.assign(document.createElement("option"),
                                    { textContent: v }));
      }
      e.value = v;
      e.dispatchEvent(new Event("change", { bubbles: true }));
    };
    satt("#p-kurs", "Matematik, nivå 2c");
    satt("#p-klass", "NA25");
    const f = document.querySelector("#moment");
    f.value = "andragradsekvationer";
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  });
  await expect(page.locator('.typrad[data-id="delprov"]')).toHaveCount(1);
}

const raden = (page, id) => page.locator(`.typrad[data-id="${id}"]`);
const valt = (page, id) => raden(page, id).locator('[aria-pressed="true"]');
const knapp = (page, id, text) =>
  raden(page, id).locator("button", { hasText: text });

/** Sätter båda raderna för hand.
 *
 *  Också när valen ÄR förvalet, och det är inte överflödigt: panelen ärver
 *  upplägget från det senaste pappret i basen (plan.js Object.assign över
 *  `v.inst` vid sidladdning), så ett prov med formelblad i ett tidigare test
 *  står kvar i raderna. Testet som mäter förvalets fraser måste därför säga
 *  vad det menar. */
async function sattHjalpmedel(page, a, b) {
  await knapp(page, "hjalpmedelA", a).first().click();
  await expect(valt(page, "hjalpmedelA")).toHaveText(a);
  if (b === undefined) return;
  // `.first()`: «Räknare» är också början på «Räknare och formelblad», och
  // knapparna står i stigande ordning — den första träffen är den exakta.
  await knapp(page, "hjalpmedelB", b).first().click();
  await expect(valt(page, "hjalpmedelB")).toHaveText(b);
}

/** Trycker Skriv och väntar ut begäran (nivåvarningen kan stå i vägen —
 *  larardag.forbiNivavarningen förklarar varför det är två klick). */
async function skriv(page) {
  const svar = page.waitForResponse(
    r => new URL(r.url()).pathname.endsWith("/api/exams/generate"),
    { timeout: 60_000 });
  await page.locator("#skriv").click();
  await L.forbiNivavarningen(page);
  return svar;
}

/* ── 1 · Raderna i panelen ──────────────────────────── */

test("hjälpmedelsraderna står i provets upplägg, en per del", async ({ page }) => {
  await L.fejkatMoln(page);
  await L.oppna(page);
  await provpanelen(page);

  await expect(raden(page, "hjalpmedelA")).toHaveCount(1);
  await expect(raden(page, "hjalpmedelB")).toHaveCount(1);
  // Förvalet ÄR dagens papper — raden får inte flytta ett prov av sig själv.
  await expect(valt(page, "hjalpmedelA")).toHaveText("Inga digitala");
  await expect(valt(page, "hjalpmedelB")).toHaveText("Räknare");
  await expect(raden(page, "hjalpmedelA").locator(".typnamn"))
    .toHaveText("Hjälpmedel på del A");

  // «En del» har en enda regel: del B-raden finns inte, och den kvarvarande
  // raden heter bara «Hjälpmedel».
  await knapp(page, "delprov", "En del").click();
  await expect(raden(page, "hjalpmedelB")).toHaveCount(0);
  await expect(raden(page, "hjalpmedelA").locator(".typnamn"))
    .toHaveText("Hjälpmedel");
});

test("formelblad som tillåtet hjälpmedel erbjuder bilagan", async ({ page }) => {
  await L.fejkatMoln(page);
  await L.oppna(page);
  await provpanelen(page);
  /* Bilagekrysset är förvalt PÅ, så testet börjar med att slå av det: det är
     kombinationen «tillåtet men skrivs inte ut» noten finns för. */
  await raden(page, "bilagor").locator('[data-del="formelblad"]').click();
  await knapp(page, "hjalpmedelA", "Formelblad").first().click();

  const not = raden(page, "hjalpmedelA").locator(".typnot");
  await expect(not).toContainText("skrivs inte ut");
  await not.locator("button", { hasText: "Lägg till formelbladet" }).click();
  await expect(raden(page, "bilagor").locator('[data-del="formelblad"]'))
    .toHaveAttribute("aria-pressed", "true");
  await expect(raden(page, "hjalpmedelA").locator(".typnot")).toHaveCount(0);
});

/* ── 2 · Begäran ───────────────────────────────────── */

test("ett orört val skickar inga hjälpmedelsfält alls", async ({ page }) => {
  const anrop = await fejkaGenerate(page);
  await L.fejkatMoln(page);
  await L.oppna(page);
  await provpanelen(page);
  await sattHjalpmedel(page, "Inga digitala", "Räknare");
  await skriv(page);

  await expect.poll(() => anrop.length).toBe(1);
  /* KASSETTREGELN. Nycklarna ska inte FINNAS: servern lägger sitt promptblock
     på ett ifyllt fält, och en tom sträng hade varit ett svar. */
  expect("hjalpmedel_a" in anrop[0]).toBe(false);
  expect("hjalpmedel_b" in anrop[0]).toBe(false);
});

test("lärarens val följer med begäran, en nyckel per del", async ({ page }) => {
  const anrop = await fejkaGenerate(page);
  await L.fejkatMoln(page);
  await L.oppna(page);
  await provpanelen(page);
  // Det hon bad om tre gånger: formelbladet tillåtet på BÅDA delarna.
  await sattHjalpmedel(page, "Formelblad", "Räknare och formelblad");
  await skriv(page);

  await expect.poll(() => anrop.length).toBe(1);
  expect(anrop[0].hjalpmedel_a).toBe("Formelblad");
  expect(anrop[0].hjalpmedel_b).toBe("Räknare och formelblad");
});

test("En del skickar bara sin enda regel", async ({ page }) => {
  const anrop = await fejkaGenerate(page);
  await L.fejkatMoln(page);
  await L.oppna(page);
  await provpanelen(page);
  await knapp(page, "delprov", "En del").click();
  await sattHjalpmedel(page, "Räknare");
  await skriv(page);

  await expect.poll(() => anrop.length).toBe(1);
  expect(anrop[0].hjalpmedel_a).toBe("Räknare");
  expect("hjalpmedel_b" in anrop[0]).toBe(false);
  expect(anrop[0].delar).toBe(false);
});

/* ── 3 · Pappret på skärmen ─────────────────────────── */

/** Provtabellens cell för en delrad.
 *
 *  En LOKATOR och inte en avläst sträng, med flit: förhandsvisningen ritas om
 *  när svaret landar, och det gamla pappret ligger kvar i DOM:en tills dess
 *  (utkastet återställs ur servern vid sidladdning — se larardag.vantaPapper).
 *  En engångsavläsning mätte därför det FÖRRA testets papper och blev grön av
 *  fel skäl; en lokator väntar ut omritningen. */
const delcell = (page, namn) => page
  .locator("#dokument [data-form='pr1'] .prmeta tr")
  .filter({ has: page.locator("th", { hasText: new RegExp(`^${namn}$`) }) })
  .locator("td");

test("skärmens provtabell bär planeringens hjälpmedel när dokumentet tiger",
  async ({ page }) => {
    const anrop = await fejkaGenerate(page);
    await L.fejkatMoln(page);
    await L.oppna(page);
    await provpanelen(page);
    await sattHjalpmedel(page, "Formelblad", "Räknare och formelblad");
    await skriv(page);
    await expect.poll(() => anrop.length).toBe(1);
    await L.vantaPapper(page);

    await expect(delcell(page, "Del A"))
      .toContainText("Formelbladet är tillåtet, inga digitala hjälpmedel.");
    await expect(delcell(page, "Del B"))
      .toContainText("Räknare, digitala hjälpmedel och formelblad tillåtna.");
  });

test("förvalet ritar precis de fraser pappret alltid burit", async ({ page }) => {
  const anrop = await fejkaGenerate(page);
  await L.fejkatMoln(page);
  await L.oppna(page);
  await provpanelen(page);
  await sattHjalpmedel(page, "Inga digitala", "Räknare");
  await skriv(page);
  await expect.poll(() => anrop.length).toBe(1);
  await L.vantaPapper(page);

  await expect(delcell(page, "Del A")).toContainText("Utan digitala hjälpmedel.");
  await expect(delcell(page, "Del B"))
    .toContainText("Räknare och digitala hjälpmedel tillåtna.");
});
