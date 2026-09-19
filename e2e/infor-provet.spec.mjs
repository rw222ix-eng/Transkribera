import { expect, test } from "@playwright/test";
import * as L from "./larardag.mjs";

/* ARBETSBLADET INFÖR PROVET
 *
 * Lärarens beställning: proven blir klara minst en vecka före provdagen, och
 * veckan innan ska klassen träna på provets UPPGIFTSTYPER — aldrig på provets
 * uppgifter. Raden i steg 3 är hela frontenden av det.
 *
 * Fem påståenden prövas, i den ordning de kan gå sönder:
 *
 *   1. Raden finns för Arbetsblad och INTE för Prov. Ett prov som förbereder
 *      ett annat prov är inte en sak.
 *   2. Förvalet tar närmaste godkända provet, men bara inom tre veckor — och
 *      frågar servern med dagens datum (testdatum-röta: en rutt som läser sin
 *      egen klocka går inte att skriva ett test på som håller nästa termin).
 *   3. Brickorna kommer ur provets uppgiftstyper, och «Blandat (hela provet)»
 *      är både förvalet och nollställaren.
 *   4. Begäran bär `infor_prov_id` och `infor_nummer` när ett prov är valt —
 *      och INGENTING när inget är valt (kassettregeln).
 *   5. Provets centrala innehåll ärvs till Gy25-brickorna, så läraren slipper
 *      kryssa i samma punkter en andra gång.
 *
 * Backendens tre rutter (`nasta`, `uppgiftstyper`, provet självt) är fejkade:
 * specen mäter panelen och kroppen, inte servern. De har sina egna tester.
 */

const IDAG = "2026-09-08";                 // L.SKOLDAG, klockan är fryst där
const KLASS = "TE26A", KURS = "Matematik, nivå 2c";
const GRUPP_ID = 3, KURS_ID = 9;

/** Ett godkänt prov som `nasta` skulle svara med. */
const prov = (id, datum, titel) => ({
  id, titel, datum, antal_uppgifter: 4,
  group_id: GRUPP_ID, course_id: KURS_ID, klass: KLASS, kurs: KURS,
});
const NARA = prov(88, "2026-09-22", "PROV 1 · Andragradsekvationer");
const FJARRAN = prov(91, "2026-12-01", "PROV 3 · Statistik");

/* Grupperingen servern gör: delmoment först, avsnitt som reserv. Nummer 1 och
   2 delas av två grupper med flit — unionen ska klara det utan dubbletter. */
const TYPER = {
  typer: [], grupper: [
    { etikett: "Lösa andragradsekvationer", nummer: [1, 2] },
    { etikett: "Tolka en parabel", nummer: [2, 3] },
    { etikett: "Problemlösning med modell", nummer: [4] },
  ],
};

/* Provet som `inforArv` läser punkterna ur när det inte ligger i högen. */
const EXAMEN = {
  exam: {
    titel: NARA.titel,
    uppgifter: [
      { text: "Lös $x^2 = 9$.", innehall: ["G25-M2C-ALG-6"] },
      { text: "Rita parabeln.", innehall: ["G25-M2C-ALG-5", "G25-M2C-ALG-6"] },
    ],
  },
};

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

const BLAD = {
  titel: "Inför provet", kurs: KURS, klass: KLASS,
  uppgifter: [
    { del: "B", formaga: "P", typ: "rutin", poang: [2, 0, 0],
      text: "Lös $x^2 - 4 = 0$.", losning: "$x = \\pm 2$", bedomning: "+2 E" },
  ],
};

/**
 * Fejkar de tre läsrutterna och generatorn, och samlar begäran.
 *
 * Returnerar `{ generate, nasta }`: kropparna som gick till generatorn och
 * URL:erna `nasta` frågades på. Den senare är hela poängen med krav 2 —
 * `idag=` måste FINNAS i frågan, annars läser servern sin egen klocka.
 */
async function fejka(page, { kommande = [NARA, FJARRAN] } = {}) {
  const generate = [], nasta = [];
  await page.route("**/api/groups", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify([{ id: GRUPP_ID, namn: KLASS }]) }));
  await page.route("**/api/courses", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify([{ id: KURS_ID, namn: KURS }]) }));
  await page.route("**/api/exams/nasta*", route => {
    nasta.push(route.request().url());
    return route.fulfill({ status: 200, contentType: "application/json",
      body: JSON.stringify({ prov: kommande[0] || null, kommande }) });
  });
  await page.route("**/api/exams/*/uppgiftstyper", route => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(TYPER) }));
  await page.route(/\/api\/exams\/\d+$/, route => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(EXAMEN) }));
  await page.route("**/api/exams/generate", route => {
    generate.push(route.request().postDataJSON());
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: 401, exam: BLAD, typ: "arbetsblad", status: "utkast",
        errors: [], rounds: 1 } }]) });
  });
  return { generate, nasta };
}

/** Planeringen öppnad på en typ, med klass och kurs satta. */
async function panelen(page, typ) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(([t, kl, ku]) => {
    window.SattLage(t);
    /* Klassen och kursen finns inte i en tom testbas — optionen läggs till,
       precis som hjalpmedlen.spec.mjs gör, för väljaren tar bara värden den
       har. */
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
    satt("#p-kurs", ku);
    satt("#p-klass", kl);
    const f = document.querySelector("#moment");
    f.value = "andragradsekvationer";
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  }, [typ, KLASS, KURS]);
}

/* Lokatorer på data-attribut och inte på rubriktext: `.typnamn` finns i varje
   rad, och två rader med samma ord i namnet är lätt gjort. */
const raden = (page, id) => page.locator(`.typrad[data-id="${id}"]`);
const brickan = (page, text) =>
  raden(page, "inforNummer").locator(".gychip", { hasText: text });

/** Trycker Skriv och väntar ut begäran. */
async function skriv(page) {
  const svar = page.waitForResponse(
    r => new URL(r.url()).pathname.endsWith("/api/exams/generate"),
    { timeout: 60_000 });
  await page.locator("#skriv").click();
  await L.forbiNivavarningen(page);
  return svar;
}

/* ── 1 · Raden hör till arbetsbladet ────────────────── */

test("«Inför provet» står i arbetsbladets upplägg, aldrig i provets",
  async ({ page }) => {
    await fejka(page);
    await L.oppna(page);

    await panelen(page, "Arbetsblad");
    await expect(raden(page, "inforProv")).toHaveCount(1);
    await expect(raden(page, "inforProv").locator(".typnamn"))
      .toHaveText("Inför provet");

    await panelen(page, "Prov");
    await expect(raden(page, "inforProv")).toHaveCount(0);
    await expect(raden(page, "inforNummer")).toHaveCount(0);
  });

/* ── 2 · Förvalet ──────────────────────────────────── */

test("närmaste provet inom tre veckor förväljs, och frågan bär dagens datum",
  async ({ page }) => {
    const { nasta } = await fejka(page);
    await L.oppna(page);
    await panelen(page, "Arbetsblad");

    const chip = raden(page, "inforProv").locator(".lchip");
    await expect(chip).toHaveCount(1);
    await expect(chip).toContainText("PROV 1");
    await expect(chip).toContainText("22 sep");
    await expect(raden(page, "inforProv").locator(".typnot"))
      .toContainText("Förbereder inför provet 22 sep");

    /* Kontraktets tre parametrar. `idag` är den som inte får glömmas: utan
       den läser rutten sin egen klocka och testet ruttnar nästa termin. */
    await expect.poll(() => nasta.length).toBeGreaterThan(0);
    const q = new URL(nasta[0]).searchParams;
    expect(q.get("group_id")).toBe(String(GRUPP_ID));
    expect(q.get("course_id")).toBe(String(KURS_ID));
    expect(q.get("idag")).toBe(IDAG);
  });

test("ett prov längre bort än tre veckor förväljs inte", async ({ page }) => {
  await fejka(page, { kommande: [FJARRAN] });
  await L.oppna(page);
  await panelen(page, "Arbetsblad");

  /* Raden finns — läraren ska kunna välja provet själv — men brickan är tom
     och typraden om vad som ska tränas finns inte. */
  await expect(raden(page, "inforProv")).toHaveCount(1);
  await expect(raden(page, "inforProv").locator(".lchip")).toHaveCount(0);
  await expect(raden(page, "inforNummer")).toHaveCount(0);
  await expect(raden(page, "inforProv").locator(".tkvalj"))
    .toHaveText("Välj prov …");
});

/* ── 3 · Brickorna ─────────────────────────────────── */

test("brickorna kommer ur provets uppgiftstyper, blandat är förvalet",
  async ({ page }) => {
    await fejka(page);
    await L.oppna(page);
    await panelen(page, "Arbetsblad");

    await expect(brickan(page, "Blandat (hela provet)"))
      .toHaveAttribute("aria-pressed", "true");
    await expect(brickan(page, "Lösa andragradsekvationer")).toHaveCount(1);
    await expect(brickan(page, "Tolka en parabel")).toHaveCount(1);
    await expect(brickan(page, "Problemlösning med modell")).toHaveCount(1);

    // En typ vald: blandat slocknar av sig självt.
    await brickan(page, "Lösa andragradsekvationer").click();
    await expect(brickan(page, "Lösa andragradsekvationer"))
      .toHaveAttribute("aria-pressed", "true");
    await expect(brickan(page, "Blandat (hela provet)"))
      .toHaveAttribute("aria-pressed", "false");

    // Och tillbaka: blandat är nollställaren.
    await brickan(page, "Blandat (hela provet)").click();
    await expect(brickan(page, "Lösa andragradsekvationer"))
      .toHaveAttribute("aria-pressed", "false");
    await expect(brickan(page, "Blandat (hela provet)"))
      .toHaveAttribute("aria-pressed", "true");
  });

/* ── 4 · Begäran ───────────────────────────────────── */

test("valda typer följer med som infor_nummer, unionen utan dubbletter",
  async ({ page }) => {
    const { generate } = await fejka(page);
    await L.oppna(page);
    await panelen(page, "Arbetsblad");
    await expect(brickan(page, "Tolka en parabel")).toHaveCount(1);

    // Två grupper som delar uppgift 2 — unionen ska vara 1, 2, 3.
    await brickan(page, "Lösa andragradsekvationer").click();
    await brickan(page, "Tolka en parabel").click();
    await skriv(page);

    await expect.poll(() => generate.length).toBe(1);
    expect(generate[0].typ).toBe("arbetsblad");
    expect(generate[0].infor_prov_id).toBe(NARA.id);
    expect(generate[0].infor_nummer).toEqual([1, 2, 3]);
  });

test("blandat skickar tom lista — hela provet", async ({ page }) => {
  const { generate } = await fejka(page);
  await L.oppna(page);
  await panelen(page, "Arbetsblad");
  await expect(brickan(page, "Blandat (hela provet)"))
    .toHaveAttribute("aria-pressed", "true");
  await skriv(page);

  await expect.poll(() => generate.length).toBe(1);
  expect(generate[0].infor_prov_id).toBe(NARA.id);
  expect(generate[0].infor_nummer).toEqual([]);

  /* Och pappret bär provet vidare: metaraden över dokumentet (som canvasens
     #g-meta läser ordagrant) säger vilket prov bladet förbereder. Ett
     arbetsblad som öppnas i november ska kunna svara på det — provet kan då
     vara skrivet, rättat och bortglömt. */
  await L.vantaPapper(page);
  await expect(page.locator("#dokmeta")).toContainText("Inför provet 22 sep");
});

test("utan prov skickas inga infor-fält alls", async ({ page }) => {
  const { generate } = await fejka(page, { kommande: [FJARRAN] });
  await L.oppna(page);
  await panelen(page, "Arbetsblad");
  await expect(raden(page, "inforProv").locator(".lchip")).toHaveCount(0);
  await skriv(page);

  await expect.poll(() => generate.length).toBe(1);
  /* KASSETTREGELN. Nycklarna ska inte FINNAS: servern lägger sitt promptblock
     på ett ifyllt `infor_prov_id`, och ett null hade varit ett svar. */
  expect("infor_prov_id" in generate[0]).toBe(false);
  expect("infor_nummer" in generate[0]).toBe(false);
});

/* ── 5 · Arvet ur provet ───────────────────────────── */

test("provets centrala innehåll ärvs till Gy25-brickorna", async ({ page }) => {
  await fejka(page);
  await L.oppna(page);
  await panelen(page, "Arbetsblad");

  /* Provet taggade två punkter i 2c. Läraren ska inte behöva kryssa i dem en
     andra gång — och raden under väljaren säger att de följde med, för ett
     arv som inte står skrivet är ett arv i smyg. */
  const chips = page.locator("#gychips .gychip");
  await expect(chips.filter({ hasText: "Andragradsekvationer" })).toHaveCount(1);
  await expect(chips.filter({ hasText: "Andragradsfunktioner" })).toHaveCount(1);
  await expect(raden(page, "inforProv").locator(".typnot"))
    .toContainText("2 punkter ur provet");
});

/* ── 6 · Kopiefynden landar på rätt ruta ───────────── */

test("kopiefyndet hamnar på sin uppgift och går att laga", async ({ page }) => {
  await fejka(page);
  await L.oppna(page);

  /* Servern sätter `el: "uppgN"` och `kod: "kopia"` på kopiefyndet
     (routes_exam _kopiefynd). Klienten behöver INGEN ny regel för det —
     efterkontrollPerElement läser `el` rakt av, och `kopia` står inte i
     LAGAS_INTE, så «Laga fynden» tar med det. Det här testet är vakten över
     just den tystnaden: skulle kartan eller undantagslistan ändras syns det
     här och inte först i canvasen. */
  const ut = await page.evaluate(() => {
    const res = { efterkontroll: [
      { el: "uppg2", kod: "kopia", nr: 2,
        text: "Uppgift 2 är provets uppgift 1 med andra tal." },
      { el: "", kod: "tid", text: "Provtiden räcker inte." },
    ] };
    return {
      karta: window.API.efterkontrollPerElement(res),
      lagbara: window.API.efterkontrollLagbara(res).map(f => f.kod),
    };
  });
  expect(ut.karta.uppg2).toEqual([
    "Uppgift 2 är provets uppgift 1 med andra tal."]);
  expect(ut.lagbara).toEqual(["kopia"]);
});
