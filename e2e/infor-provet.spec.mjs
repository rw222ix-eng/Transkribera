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
 *   7. Tavlan har samma rad (läraren 2026-09-27: genomgången förklarar det
 *      provet kräver, boken i andra hand). Eget förval med sex veckors
 *      fönster, eget läge som inte läcker till bladet, inget arv ur provet,
 *      och samma kassettregel för /api/planning/generate.
 *   8. Gruppuppgiften har samma rad (Rickard 2026-09-27: «gruppuppgift,
 *      baserat på provet»). Tavlans fönster och nollbricka, inget arv, och
 *      kroppen bär fälten bara när ett prov är valt.
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
/* 37 dagar bort: utanför bladets tre veckor, innanför tavlans sex. */
const MELLAN = prov(93, "2026-10-15", "PROV 2 · Funktioner");
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

/* Gruppuppgiftens upplägg på pappret, som servern skriver in det. */
const GRUPPEN = { elever: 3, langd_min: 60, redovisning: "genomgång" };

/* Tavlan som /api/planning/generate svarar med. Tom, men giltig: specen mäter
   kroppen och metaraden, inte ritningen. */
const TAVLA = {
  title: "Andragradsfunktioner",
  boards: [{ width: 900, height: 780, name: "vanster", sections: [] },
           { width: 1800, height: 780, name: "hoger", sections: [] }],
};

/**
 * Fejkar de tre läsrutterna och generatorerna, och samlar begäran.
 *
 * Returnerar `{ generate, nasta, tavla, examen }`: kropparna som gick till
 * bladets och tavlans generator, URL:erna `nasta` frågades på och läsningarna
 * av provet självt. `nasta` är hela poängen med krav 2: `idag=` måste FINNAS
 * i frågan, annars läser servern sin egen klocka. `examen` är beviset på att
 * tavlan inte ärver ur provet (krav 7).
 */
async function fejka(page, { kommande = [NARA, FJARRAN] } = {}) {
  const generate = [], nasta = [], tavla = [], examen = [];
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
  await page.route(/\/api\/exams\/\d+$/, route => {
    examen.push(route.request().url());
    return route.fulfill({
      status: 200, contentType: "application/json", body: JSON.stringify(EXAMEN) });
  });
  await page.route("**/api/planning/generate", route => {
    tavla.push(route.request().postDataJSON());
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: "p1", board: TAVLA, errors: [], rounds: 1 } }]) });
  });
  await page.route("**/api/exams/generate", route => {
    const kropp = route.request().postDataJSON();
    generate.push(kropp);
    /* Gruppuppgiften (krav 8) får tillbaka sin egen typ och sitt upplägg. */
    const grupp = kropp.typ === "gruppuppgift";
    return route.fulfill({ status: 200, contentType: "text/event-stream",
      body: strom([{ type: "done", result: {
        id: grupp ? 402 : 401,
        exam: grupp ? { ...BLAD, grupp: GRUPPEN } : BLAD,
        typ: grupp ? "gruppuppgift" : "arbetsblad", status: "utkast",
        errors: [], rounds: 1 } }]) });
  });
  return { generate, nasta, tavla, examen };
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

/** Trycker Skriv och väntar ut begäran. Tavlan går till planeringens rutt. */
async function skriv(page, vag = "/api/exams/generate") {
  const svar = page.waitForResponse(
    r => new URL(r.url()).pathname.endsWith(vag),
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

/* ── 7 · Tavlan ────────────────────────────────────── */

test("tavlan har raden, och förvalet når sex veckor där bladets når tre",
  async ({ page }) => {
    await fejka(page, { kommande: [MELLAN, FJARRAN] });
    await L.oppna(page);

    await panelen(page, "Tavla");
    await expect(raden(page, "inforProv")).toHaveCount(1);
    const chip = raden(page, "inforProv").locator(".lchip");
    await expect(chip).toHaveCount(1);
    await expect(chip).toContainText("PROV 2");
    await expect(chip).toContainText("15 okt");
    /* Nollställaren heter efter vad tom lista betyder på tavlan: servern
       väljer provets uppgifter på lektionens sidor, inte hela provet. */
    await expect(brickan(page, "Det som hör till lektionen"))
      .toHaveAttribute("aria-pressed", "true");
    await expect(brickan(page, "Blandat (hela provet)")).toHaveCount(0);
    await expect(raden(page, "inforNummer").locator(".typnot"))
      .toHaveText("Provets uppgifter på lektionens sidor styr tavlans exempel.");

    /* Samma prov ligger för långt bort för bladet, och tavlans val läcker
       inte dit: bladet har sitt eget prov i upplägget. */
    await panelen(page, "Arbetsblad");
    await expect(raden(page, "inforProv")).toHaveCount(1);
    await expect(raden(page, "inforProv").locator(".lchip")).toHaveCount(0);

    // Och tillbaka: tavlans prov står kvar.
    await panelen(page, "Tavla");
    await expect(raden(page, "inforProv").locator(".lchip")).toContainText("PROV 2");
  });

test("att ta bort provet från tavlan håller inte bladets förval borta",
  async ({ page }) => {
    await fejka(page);
    await L.oppna(page);

    await panelen(page, "Tavla");
    const tavlans = raden(page, "inforProv").locator(".lchip");
    await expect(tavlans).toContainText("PROV 1");
    await tavlans.click();
    await expect(tavlans).toHaveCount(0);

    /* Ett gemensamt läge hade burit tavlans «rörd» över till bladet, och då
       hade bladet stått utan prov fast det ligger två veckor bort. */
    await panelen(page, "Arbetsblad");
    await expect(raden(page, "inforProv").locator(".lchip")).toContainText("PROV 1");

    // Tavlans eget val står kvar: förvalet smyger inte tillbaka provet.
    await panelen(page, "Tavla");
    await expect(raden(page, "inforProv").locator(".lchip")).toHaveCount(0);
  });

test("tavlans begäran bär provet, och tavlan ärver inget ur det",
  async ({ page }) => {
    const { tavla, examen } = await fejka(page, { kommande: [MELLAN, FJARRAN] });
    await L.oppna(page);
    await panelen(page, "Tavla");

    /* Ingen arvsmening: tavlans bok är lektionens sidor, och provets
       punkter och sidor följer inte med (INFOR.Tavla.arv). */
    await expect(raden(page, "inforProv").locator(".typnot"))
      .toHaveText("Förbereder inför provet 15 okt · PROV 2 · Funktioner");
    await expect(brickan(page, "Det som hör till lektionen"))
      .toHaveAttribute("aria-pressed", "true");
    await skriv(page, "/api/planning/generate");

    await expect.poll(() => tavla.length).toBe(1);
    expect(tavla[0].infor_prov_id).toBe(MELLAN.id);
    /* Tom lista följer med: servern väljer då själv provets uppgifter på
       lektionens sidor. */
    expect(tavla[0].infor_nummer).toEqual([]);
    /* Bara provets egen läsning räknas: basen delas med testerna ovan, och
       deras blad (401) läses tillbaka när utkastet återställs. */
    expect(examen.filter(u => u.endsWith(`/api/exams/${MELLAN.id}`))).toEqual([]);

    /* Pappret bär provet: samma metarad som bladets. */
    await L.vantaPapper(page);
    await expect(page.locator("#dokmeta")).toContainText("Inför provet 15 okt");
  });

test("tavlans valda uppgifter följer med som infor_nummer", async ({ page }) => {
  const { tavla } = await fejka(page, { kommande: [MELLAN] });
  await L.oppna(page);
  await panelen(page, "Tavla");
  await expect(brickan(page, "Tolka en parabel")).toHaveCount(1);

  await brickan(page, "Lösa andragradsekvationer").click();
  await brickan(page, "Tolka en parabel").click();
  await expect(brickan(page, "Det som hör till lektionen"))
    .toHaveAttribute("aria-pressed", "false");
  await expect(raden(page, "inforNummer").locator(".typnot"))
    .toHaveText("3 av provets uppgifter styr tavlans exempel, samma sorter med nya tal.");
  await skriv(page, "/api/planning/generate");

  await expect.poll(() => tavla.length).toBe(1);
  expect(tavla[0].infor_prov_id).toBe(MELLAN.id);
  expect(tavla[0].infor_nummer).toEqual([1, 2, 3]);
});

test("tavla utan prov skickar inga infor-fält alls", async ({ page }) => {
  const { tavla } = await fejka(page, { kommande: [FJARRAN] });
  await L.oppna(page);
  await panelen(page, "Tavla");
  await expect(raden(page, "inforProv")).toHaveCount(1);
  await expect(raden(page, "inforProv").locator(".lchip")).toHaveCount(0);
  await expect(raden(page, "inforNummer")).toHaveCount(0);
  await skriv(page, "/api/planning/generate");

  await expect.poll(() => tavla.length).toBe(1);
  /* KASSETTREGELN, samma som bladets: nycklarna ska inte finnas. */
  expect("infor_prov_id" in tavla[0]).toBe(false);
  expect("infor_nummer" in tavla[0]).toBe(false);
});

/* ── 8 · Gruppuppgiften ────────────────────────────── */

test("gruppuppgiften har raden, med tavlans fönster och nollbricka",
  async ({ page }) => {
    const { examen } = await fejka(page, { kommande: [MELLAN, FJARRAN] });
    await L.oppna(page);
    await panelen(page, "Gruppuppgift");

    await expect(raden(page, "inforProv")).toHaveCount(1);
    const chip = raden(page, "inforProv").locator(".lchip");
    await expect(chip).toContainText("PROV 2");
    /* Inget arv: gruppuppgiftens sidor är lektionens, som tavlans. */
    await expect(raden(page, "inforProv").locator(".typnot"))
      .toHaveText("Förbereder inför provet 15 okt · PROV 2 · Funktioner");
    /* Tom lista är det som hör till lektionen, inte hela provet. */
    await expect(brickan(page, "Det som hör till lektionen"))
      .toHaveAttribute("aria-pressed", "true");
    await expect(brickan(page, "Blandat (hela provet)")).toHaveCount(0);
    await expect(raden(page, "inforNummer").locator(".typnot"))
      .toHaveText("Provets uppgifter på lektionens sidor styr gruppuppgiften.");
    expect(examen.filter(u => u.endsWith(`/api/exams/${MELLAN.id}`))).toEqual([]);

    /* Eget läge: bladets tre veckor når inte provet, och gruppuppgiftens val
       läcker inte dit. */
    await panelen(page, "Arbetsblad");
    await expect(raden(page, "inforProv").locator(".lchip")).toHaveCount(0);
  });

test("gruppuppgiftens begäran bär provet, lektionens moment och tom lista",
  async ({ page }) => {
    const { generate } = await fejka(page, { kommande: [MELLAN] });
    await L.oppna(page);
    await panelen(page, "Gruppuppgift");
    await expect(raden(page, "inforProv").locator(".lchip")).toContainText("PROV 2");
    await skriv(page);

    await expect.poll(() => generate.length).toBe(1);
    expect(generate[0].typ).toBe("gruppuppgift");
    expect(generate[0].infor_prov_id).toBe(MELLAN.id);
    expect(generate[0].infor_nummer).toEqual([]);
    /* Momentet går med under eget namn: `moment` styr undvik-listan. */
    expect(generate[0].infor_moment).toBe("andragradsekvationer");
    expect("moment" in generate[0]).toBe(false);

    await L.vantaPapper(page);
    await expect(page.locator("#dokmeta")).toContainText("Inför provet 15 okt");
  });

test("gruppuppgiftens valda uppgifter följer med som infor_nummer",
  async ({ page }) => {
    const { generate } = await fejka(page, { kommande: [MELLAN] });
    await L.oppna(page);
    await panelen(page, "Gruppuppgift");
    await expect(brickan(page, "Tolka en parabel")).toHaveCount(1);

    await brickan(page, "Lösa andragradsekvationer").click();
    await brickan(page, "Tolka en parabel").click();
    await expect(raden(page, "inforNummer").locator(".typnot"))
      .toHaveText("3 av provets uppgifter styr gruppuppgiften, samma sorter med nya tal.");
    await skriv(page);

    await expect.poll(() => generate.length).toBe(1);
    expect(generate[0].infor_nummer).toEqual([1, 2, 3]);
  });

test("gruppuppgift utan prov skickar inga infor-fält alls", async ({ page }) => {
  const { generate } = await fejka(page, { kommande: [FJARRAN] });
  await L.oppna(page);
  await panelen(page, "Gruppuppgift");
  await expect(raden(page, "inforProv")).toHaveCount(1);
  await expect(raden(page, "inforProv").locator(".lchip")).toHaveCount(0);
  await expect(raden(page, "inforNummer")).toHaveCount(0);
  await skriv(page);

  await expect.poll(() => generate.length).toBe(1);
  expect(generate[0].typ).toBe("gruppuppgift");
  /* KASSETTREGELN: kroppen är byte för byte den som gick före raden. */
  for (const k of ["infor_prov_id", "infor_nummer", "infor_moment", "starttid"]) {
    expect(k in generate[0], k).toBe(false);
  }
});
