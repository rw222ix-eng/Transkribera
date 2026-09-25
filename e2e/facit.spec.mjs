import { expect, test } from "@playwright/test";

/* FACITBLADEN — kort text, hela A4:an
 *
 * Läraren, med ett facit på skärmen: «alla de här facitbladen … de ska bara
 * ange svaret och en typ av lösning. Annars blir det så jävla mycket text och
 * det är svårläst.» Och strax därpå: «Texten på facit ska fylla hela
 * A4-bladet … dynamiskt justera texten … en minimistorlek på texten, typ
 * storlek 12 — texten kan bara bli större från 12.»
 *
 * Två krav som drar åt olika håll, och därför lätta att förstöra var för sig:
 *
 *   1. Facit trycker inte hela uppgiftstexten en gång till. Kvar står det som
 *      IDENTIFIERAR uppgiften — brickan och matematiken — medan
 *      instruktionsprosan («Gruppen ska enas om ett gemensamt svar …») hör till
 *      elevens papper och stannar där.
 *   2. Det som blir över i höjd går till GRADEN, inte till vitt papper. Ratten
 *      är CSS-variabeln --fsk (losning.css), och blad.js skruvar upp den efter
 *      pagineringen: aldrig under basen, aldrig över kanten, aldrig över taket.
 *
 * Ordningen mellan stegen är det som lättast går sönder: skalas arket FÖRE
 * pagineringen delas ett blad som renderaren själv blåst upp, och läraren får
 * två papper där ett räckte.
 */

const SCHEMA = { schema: [], lov: [], poster: [] };

/* Gruppuppgiften läraren hade framme: instruktionsprosan i mitten är precis
   det som inte ska följa med till facit. */
const LANG = "Beräkna utan räknare. Gruppen ska enas om ett gemensamt svar på "
  + "varje uttryck innan ni skriver ner det. A: $7 + 3 \\cdot 6$ "
  + "B: $\\frac{9 \\cdot 8 + 24}{12}$";

function papper(extra = {}) {
  return {
    typ: "Arbetsblad", moment: "prioriteringsregler", klass: "BA26B",
    kurs: "Matematik, nivå 1a", datum: "2026-09-14", tid: "",
    gy: [], kalla: false, kallor: [], inst: { antal: 3, niva: "Blandat" },
    bilder: {}, referenser: [], forlaga: null, resultat: null, fokus: "",
    kontext: "start", niva: false, svarighet: 0, andrat: [],
    provId: 12, losningsblad: true, uppgifter: [],
    ...extra,
  };
}

const rad = (id, dok) => ({
  id, status: "godkant", markor: 0, sort: id, foljd: null,
  versioner: [dok], dokument: { ...dok, id },
});

async function fejka(page, sparade) {
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade, utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

/** Öppnar förhandsvisningen på pappret — samma väg läraren tar, så att
 *  pagineringen och skalningen körs på riktigt och inte i ett provrör. */
async function visa(page) {
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => window.Dokument.visa(0));
  await expect(page.locator("#forhandsskal")).toBeVisible();
  await expect(page.locator("#fh-ark .ark[data-form='fa']").first()).toBeVisible();
}

/** Skalan arket landade på. Väntar ut formge(), som körs fyra gånger — sist när
 *  typsnitten laddats, och det är den mätningen som gäller. */
function skalan(page, n = 0) {
  return page.evaluate(i => {
    const ark = document.querySelectorAll("#fh-ark .ark[data-form='fa']")[i];
    return ark ? Number(ark.style.getPropertyValue("--fsk")) : 0;
  }, n);
}

test("facit upprepar inte uppgiftstexten — brickan och matematiken räcker",
  async ({ page }) => {
    await fejka(page, []);
    await page.goto("/");
    await hydrerad(page);

    const text = await page.evaluate(lang => {
      const d = document.createElement("div");
      d.id = "facitprov";
      d.innerHTML = window.BladBygg.arkfacit(
        { moment: "prioriteringsregler" },
        [{ nr: 1, p: 2, t: lang, f: "$25$ respektive $8$" }]);
      document.body.appendChild(d);
      return d.querySelector(".prtext").textContent;
    }, LANG);

    // Instruktionsprosan hör till elevens ark och följer inte med.
    expect(text).not.toContain("Gruppen ska enas");
    // Men uppgiften går fortfarande att känna igen: verbet och matematiken.
    expect(text).toContain("Beräkna");
    // Och det är KORTARE — annars var kortandet ingen kortning.
    expect(text.length).toBeLessThan(LANG.length * 0.7);

    /* Ett klipp mitt i en formel är obalanserade dollartecken, och då sätts
       resten av arket som matematik. Räkna spännen i stället för tecken: varje
       $…$ ska ha blivit ett eget mat-spann. */
    const spann = await page.locator("#facitprov .prtext .mat").count();
    expect(spann).toBeGreaterThan(0);
  });

test("skalan växer på ett halvtomt facit — men aldrig under basen",
  async ({ page }) => {
    /* Tre korta svar på ett A4. Utan ratten satt de i samma grad som fjorton
       skulle ha gjort, och två tredjedelar av pappret var vitt. */
    await fejka(page, [rad(1, papper({ uppgifter: [
      { nr: 1, p: 2, t: "Beräkna $7 + 3 \\cdot 6$.", f: "$25$" },
      { nr: 2, p: 2, t: "Beräkna $12 - 4 \\cdot 2$.", f: "$4$" },
      { nr: 3, p: 2, t: "Beräkna $(6 + 2) \\cdot 3$.", f: "$24$" },
    ] }))]);
    await page.goto("/");
    await hydrerad(page);
    await visa(page);

    await expect.poll(() => skalan(page), { timeout: 20_000 }).toBeGreaterThan(1);

    const matt = await page.evaluate(() => {
      const ark = document.querySelector("#fh-ark .ark[data-form='fa']");
      const grad = sel => parseFloat(getComputedStyle(ark.querySelector(sel)).fontSize);
      return {
        spill: ark.scrollHeight - ark.clientHeight,
        vag: grad(".lobedsvar"),
        titel: grad(".lotitel"),
        nr: grad(".prnr"),
        blad: document.querySelectorAll("#fh-ark .ark[data-form='fa']").length,
      };
    });

    // Aldrig över kanten: ett svar under nederkanten är värre än vitt papper.
    expect(matt.spill).toBeLessThanOrEqual(0);
    // Aldrig under lärarens tolva, och basen (15,5 px, svaret i
    // bedömningsanvisningens form sedan 2026-09-25) är golvet, inte taket.
    expect(matt.vag).toBeGreaterThanOrEqual(15.5);
    expect(matt.vag).toBeGreaterThanOrEqual(12);
    // EN ratt: rubrik och marginalsiffra växer med svaret, inte var för sig.
    expect(matt.titel).toBeGreaterThan(25);
    expect(matt.nr).toBeGreaterThan(23);
    // Tre svar är ett blad. Skalningen får inte hitta på en sida till.
    expect(matt.blad).toBe(1);
  });

test("ett fullt facit paginerar fortfarande — och sida två får sin egen grad",
  async ({ page }) => {
    /* Fjorton uppgifter med utskriven lösningsgång ryms inte på ett A4.
       Pagineringen mäter i BASGRADEN och delar därför på samma ställe som
       förut; sedan fyller varje blad sig självt, och sida två — den halvtomma —
       får en större grad än sida ett. */
    /* Arbetsbladets facit trycker inte uppgiftstexten sedan 2026-09-25, så
       höjden ligger i stegen: svaret och fyra led per uppgift. */
    const vag = k => [[`Ledet ${k}`, "1 p"], ["Svaret sätts in", "1 p"]];
    const uppgifter = Array.from({ length: 14 }, (_, k) => ({
      nr: k + 1, p: 3,
      f: [`$x = ${k + 1}$`, `$${k + 2}x + ${k} = ${(k + 2) * (k + 1) + k}$`,
          `$${k + 2}x = ${(k + 2) * (k + 1)}$`, `$x = ${k + 1}$`,
          `Kontroll: $${k + 2} \\cdot ${k + 1} + ${k} = ${(k + 2) * (k + 1) + k}$`].join("\n"),
      t: `Lös ekvationen $${k + 2}x + ${k} = ${(k + 2) * (k + 1) + k}$ och `
         + "kontrollera svaret genom insättning i det ursprungliga ledet.",
      vag: vag(k + 1),
    }));
    await fejka(page, [rad(1, papper({ uppgifter }))]);
    await page.goto("/");
    await hydrerad(page);
    await visa(page);

    await expect.poll(
      () => page.locator("#fh-ark .ark[data-form='fa']").count(),
      { timeout: 20_000 }).toBeGreaterThan(1);

    const arken = await page.evaluate(() =>
      Array.from(document.querySelectorAll("#fh-ark .ark[data-form='fa']"))
        .map(a => ({ fsk: Number(a.style.getPropertyValue("--fsk")),
                     spill: a.scrollHeight - a.clientHeight,
                     uppg: a.querySelectorAll(".pruppg").length })));

    // Inget blad spiller, och inget blad är tomt.
    arken.forEach(a => {
      expect(a.spill).toBeLessThanOrEqual(0);
      expect(a.uppg).toBeGreaterThan(0);
      expect(a.fsk).toBeGreaterThanOrEqual(1);
    });
    // Sista bladet bär resten och har därför luft kvar — den går till graden.
    expect(arken[arken.length - 1].fsk).toBeGreaterThan(arken[0].fsk);
  });

/* ── FACITRADEN EFTER GRANSKNINGEN 2026-09-24 NATT ──
   «Svar: 3» stod under etiketten SVAR, «$n =$» som enhet hamnade efter
   svaret, och «%» efter «2,5 per år (…)». Samma regler som
   bedömningsanvisningens svaret(): ett led före svaret, en enhet bara efter
   ett tal. */
test("facitraden: inget dubbelt Svar, ledet före, enheten bara efter ett tal",
  async ({ page }) => {
    await fejka(page, []);
    await page.goto("/");
    await hydrerad(page);
    const rader = await page.evaluate(() => {
      const d = document.createElement("div");
      d.innerHTML = window.BladBygg.arkfacit({ moment: "x" }, [
        { nr: 1, p: 1, t: "Hur många burkar?", f: "Svar: 3\n$20/8 = 2{,}5$", enhet: "burkar" },
        { nr: 2, p: 1, t: "Ange $n$.", f: "$5$", enhet: "$n =$" },
        { nr: 3, p: 1, t: "Hur snabbt?", f: "2,5 per år (ungefär)", enhet: "%" },
        { nr: 4, p: 1, t: "Hur långt?", f: "$12$", enhet: "m" },
      ]);
      document.body.appendChild(d);
      /* Matten är spann med data-tex tills Matte.satt kört: jämför källan. */
      const ut = [...d.querySelectorAll(".lossvar")].map(s => s.innerHTML);
      d.remove();
      return ut;
    });
    expect(rader[0]).not.toMatch(/^Svar/i);
    expect(rader[0]).toContain("burkar");
    expect(rader[1].indexOf("n =")).toBeGreaterThan(-1);
    expect(rader[1].indexOf("n =")).toBeLessThan(rader[1].indexOf('"5'));
    expect(rader[2]).not.toContain("%");
    expect(rader[3]).toContain("m");
  });

/* ── DELUPPGIFTERNA PÅ BLADET SOM PÅ PROVET (2026-09-25) ──
   Två kortsvar a) och b) fick en enda «Svar:» under båda, och
   deluppgifternas text stod i mindre grad än frågan. */
test("bladets kortsvar: en svarsrad per deluppgift, frågans grad",
  async ({ page }) => {
    await fejka(page, [rad(1, papper({ losningsblad: false, uppgifter: [
      { nr: 1, p: 2, ut: "kort", t: "Utan räknare. Skriv som en potens.",
        f: "", del: ["$\\sqrt[3]{5}$", "$\\dfrac{b^{2}}{b^{8}}$"],
        vag: [["a) $5^{1/3}$", "1 p"], ["b) $b^{-6}$", "1 p"]] },
      { nr: 2, p: 2, ut: "rakna", t: "Lös ekvationerna.", f: "",
        del: ["$2x = 8$", "$x + 1 = 3$"],
        vag: [["a) $x = 4$", "1 p"], ["b) $x = 2$", "1 p"]] },
      /* Deluppgiftens egen typ (franProv `delut`): a) kortsvar, b) lösning. */
      { nr: 3, p: 2, ut: "rakna", t: "En boll kastas.", f: "",
        del: ["Beräkna höjden.", "Bestäm tiden."], delut: ["kort", "rakna"],
        vag: [["a) $6$ m", "1 p"], ["b) $2$ s", "1 p"]] },
    ] }))]);
    await page.goto("/");
    await hydrerad(page);
    await page.getByRole("tab", { name: "Planering" }).click();
    await page.evaluate(() => window.Dokument.visa(0));
    await expect(page.locator("#forhandsskal")).toBeVisible();
    const kort = page.locator("#fh-ark .gukort");
    await expect(kort).toHaveCount(3);
    const matt = await kort.evaluateAll(k => k.map(x => ({
      rader: x.querySelectorAll(".gusvarsrad").length,
      iDel: x.querySelectorAll(".gudel .gusvarsrad").length,
      losblad: x.querySelectorAll(".gulos").length,
      grad: [x.querySelector(".gufraga"), x.querySelector(".gudel")]
        .map(e => parseFloat(getComputedStyle(e).fontSize)),
    })));
    expect(matt[0].rader).toBe(2);
    expect(matt[0].iDel).toBe(2);
    expect(matt[1].rader).toBe(0);
    expect(matt[1].losblad).toBe(1);
    expect(matt[2].iDel).toBe(1);
    expect(matt[2].losblad).toBe(1);
    expect(matt[0].grad[0]).toBe(matt[0].grad[1]);
  });

/* ── ARBETSBLADETS FACIT I BEDÖMNINGSANVISNINGENS FORM (2026-09-25) ──
   Rickard: facit ska bli mycket tydligare för eleverna, i samma form som
   provens bedömningsanvisning. Svaret fett, ett steg per rad i samma grad,
   ingen uppgiftstext, inga poäng, en linje mellan uppgifterna. */
test("bladets facit: svaret fett, ett steg per rad, samma grad",
  async ({ page }) => {
    await fejka(page, [rad(1, papper({ uppgifter: [
      { nr: 1, p: 1, t: "Utan räknare. Beräkna priset för 15 km.",
        f: "225\n$P = 45 + 12 \\cdot 15 = 225$", enhet: "kr" },
      { nr: 2, p: 2, t: "Nora påstår något. Avgör om Nora har rätt.",
        f: "Nej. Talet ska vara minst 1.\n$52 \\cdot 10^{3} = 5{,}2 \\cdot 10^{4}$" },
      { nr: 3, p: 2, t: "Lös ekvationerna.", f: "",
        del: ["Lös $2x = 8$.", "Lös $x + 1 = 3$."],
        vag: [["a) $x = 4$\n$x = 8/2$", "1 p"], ["b) $x = 2$", "1 p"]] },
    ] }))]);
    await page.goto("/");
    await hydrerad(page);
    await visa(page);

    const ark = page.locator("#fh-ark .ark[data-form='fa']").first();
    await expect(ark.locator(".pruppg")).toHaveCount(3);
    const matt = await ark.evaluate(a => {
      const grad = el => parseFloat(getComputedStyle(el).fontSize);
      const u = [...a.querySelectorAll(".pruppg")];
      return {
        text: a.textContent,
        svar: u.map(x => [...x.querySelectorAll(".lobedsvar")].length),
        steg: u.map(x => [...x.querySelectorAll(".lobedsteg")].length),
        del: [...u[2].querySelectorAll(".lobeddel")].map(b => b.textContent),
        nej: u[1].querySelector(".lobedsvar").textContent,
        kr: u[0].querySelector(".lobedsvar").textContent,
        grad: [grad(a.querySelector(".lobedsvar")), grad(a.querySelector(".lobedsteg"))],
        vikt: getComputedStyle(a.querySelector(".lobedsvar")).fontWeight,
        linje: u.map(x => getComputedStyle(x).borderTopWidth),
        ref: a.querySelectorAll(".prtext, .losetikett, .prvarde").length,
      };
    });
    // Ingen uppgiftstext och inga poäng: eleven har bladet bredvid sig.
    expect(matt.text).not.toContain("Beräkna priset");
    expect(matt.text).not.toContain("1 p");
    expect(matt.ref).toBe(0);
    // Svaret först, fett; stegen en rad var.
    expect(matt.svar).toEqual([1, 1, 2]);
    expect(matt.steg).toEqual([1, 2, 1]);
    expect(matt.del).toEqual(["a)", "b)"]);
    expect(matt.nej).toBe("Nej");
    expect(matt.kr).toContain("kr");
    expect(Number(matt.vikt)).toBeGreaterThanOrEqual(700);
    // En grad för svar och steg.
    expect(matt.grad[0]).toBeCloseTo(matt.grad[1], 1);
    // Linjen står mellan uppgifterna, inte över den första.
    expect(matt.linje[0]).toBe("0px");
    matt.linje.slice(1).forEach(b => expect(parseFloat(b)).toBeGreaterThan(0));
  });
