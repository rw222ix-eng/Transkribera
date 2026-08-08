import { expect, test } from "@playwright/test";
import * as L from "./larardag.mjs";

/* SCENARIOMATRISEN — tio skriptade lärardagar (Etapp 4.1)
 *
 * «Som om hundratals lärare använt appen och rapporterat buggarna» betyder för
 * en lokal enanvändarapp hundratals SESSIONER, inte samtidiga användare. Det
 * här är sessionerna: hela arbetsdagar körda mot den riktiga servern med bara
 * molnet fejkat (se larardag.mjs). Papperen skrivs på riktigt, provet
 * kompileras av riktiga Tectonic, godkännandet skriver i den riktiga basen.
 *
 * Kravet per dag är detsamma:
 *   · inga konsolfel och inga JS-fel,
 *   · inga halvskrivna dokument — det som ser sparat ut ÄR sparat,
 *   · varje besked svenskt och åtgärdbart.
 *
 * Dagarna delar bas (servern startas en gång för hela sviten), så de mäter
 * alltid FÖRE och EFTER — aldrig absoluta antal.
 */

test.describe.configure({ mode: "serial" });

// ── Dag 1 ────────────────────────────────────────────────────────────────
test("dag 1 — vanlig dag: spela in, transkribera, granska, planera, godkänn",
  async ({ page }) => {
    const fel = L.vakt(page);
    const anrop = L.spana(page);
    await L.fejkatMoln(page);
    await L.oppna(page);

    // Morgonen: gårdagens inspelning läggs i kön. Schemat gör klass och kurs
    // till fakta — filnamnet bär datum och tid, och tisdag 09:05 är NA25.
    await L.transkribera(page);
    await expect(page.locator("#klarruta")).toBeVisible({ timeout: 20_000 });
    await expect(page.locator("#korkvar")).toContainText("OpenAI");

    // Granskningen efter körningen: serverns insikter, inte regexgissningen.
    await expect(page.locator("#forslagnot")).toContainText("kalender", { timeout: 20_000 });

    // Eftermiddagen: en av veckans lektioner planeras.
    const fore = await L.antalSparade(page);
    await L.valjKlass(page, "NA25");
    await L.skriv(page, { moment: "derivatans definition" });
    await L.vantaPapper(page);
    await expect(page.locator("#dokument .tavruta")).toBeVisible();
    // Tavlan kom ur servern, inte ur appens egen innehållsbank.
    expect(L.traff(anrop, "/api/planning/generate")).toHaveLength(1);

    // Godkännandet skriver in tavlan: dokumentet, planeringen och bilden.
    await page.locator("#godkann").click();
    await expect.poll(() => L.antalSparade(page), { timeout: 60_000 })
      .toBeGreaterThan(fore);
    await expect.poll(() => L.traff(anrop, "/approve").length, { timeout: 30_000 })
      .toBeGreaterThan(0);

    // Och det överlever att datorn stängs av: pappret kommer ur servern.
    const sparade = await L.efterOmladdning(page);
    expect(sparade.length).toBeGreaterThan(fore);
    expect(sparade.some(v => (v.dokument || v).typ === "Tavla")).toBe(true);
    L.rent(fel);
  });

// ── Dag 2 ────────────────────────────────────────────────────────────────
test("dag 2 — tre lektioner, två klasser: kön bär dem i tur och ordning",
  async ({ page }) => {
    test.setTimeout(180_000);
    const fel = L.vakt(page);
    await L.fejkatMoln(page);
    await L.oppna(page);

    // Måndagens tre lektioner: NA25 (Ma2c), TE25prk (Ma1c), IN24prk (Ma2a).
    await L.valjKlass(page, "NA25");
    await L.valjKlass(page, "TE25prk");
    const kon = await page.evaluate(() => window.PlanKo.valda());
    expect(kon.length).toBe(2);
    // Kön går i tidsordning oavsett klickordning.
    const tider = kon.map(p => `${p.datum} ${p.tid}`);
    expect([...tider].sort()).toEqual(tider);

    await L.skriv(page, { moment: "derivatans definition" });
    await L.vantaPapper(page);
    const fore = await L.antalSparade(page);
    await page.locator("#godkann").click();
    await expect.poll(() => L.antalSparade(page), { timeout: 60_000 }).toBeGreaterThan(fore);

    /* Kön avancerar på GODKÄNNANDE. Den farligaste buggen i flerklassflödet är
       tyst: att förra klassens moment, förlaga eller boksidor följer med in i
       nästa dokument. Kursen är en annan här, alltså ska fältet vara nollat. */
    await expect.poll(() => page.evaluate(() => {
      const p = window.PlanKo.valda();
      return window.PlanKo.arNu(p[1]);
    }), { timeout: 20_000 }).toBe(true);
    const efter = await page.evaluate(() => ({
      klass: document.querySelector("#p-klass").value,
      moment: document.querySelector("#moment").value,
    }));
    expect(efter.klass).toBe("TE25prk");
    expect(efter.moment).not.toContain("derivatans definition");
    L.rent(fel);
  });

// ── Dag 3 ────────────────────────────────────────────────────────────────
test("dag 3 — provdag: skriv provet, godkänn till PDF, tryck med anpassad kopia",
  async ({ page }) => {
    test.setTimeout(240_000);
    const fel = L.vakt(page);
    const anrop = L.spana(page);
    await L.fejkatMoln(page);
    await L.oppna(page);

    await L.valjKlass(page, "NA25");
    await L.skriv(page, { typ: "Prov", moment: "derivator" });
    await L.vantaPapper(page, 60_000);
    // Arket bär serverns uppgifter, i frontendens form.
    await expect(page.locator("#dokument .pruppg").first()).toBeVisible();
    const uppgifter = await page.locator("#dokument .pruppg").count();
    expect(uppgifter).toBeGreaterThan(3);

    const fore = await L.antalSparade(page);
    await page.locator("#godkann").click();
    await expect.poll(() => L.antalSparade(page), { timeout: 120_000 }).toBeGreaterThan(fore);
    // Godkännandet byggde PDF:en på riktigt (Tectonic, bunden i bin/tectonic).
    expect(L.traff(anrop, "/approve").length).toBeGreaterThan(0);

    // Utskriftsrutan: provet, facit och en anpassad kopia — förlängd tid och
    // färre uppgifter, märkt bara med dokumentkod i sidfoten.
    await page.getByRole("tab", { name: "Planering" }).click();
    await page.evaluate(() => window.Tryck.oppna());
    await expect(page.locator("#tryckruta")).toBeVisible();
    await page.locator("#tryckanpassad").click();
    await page.locator("#tryckskicka").click();

    await expect.poll(() => L.traff(anrop, "/api/tryck").length,
                      { timeout: 120_000 }).toBe(1);
    const paket = L.traff(anrop, "/api/tryck")[0].kropp;
    expect(paket.dokument.some(d => d.anpassad)).toBe(true);
    // Tavlan hade legat först om det funnits en; provet ska i alla fall inte
    // ligga efter sitt eget facit.
    await expect(page.locator(".toast").last()).toContainText(/ordning|utskrift|PDF/i,
                                                              { timeout: 60_000 });
    L.rent(fel);
  });

// ── Dag 4 ────────────────────────────────────────────────────────────────
test("dag 4 — rättningsdag: siffrorna in, utfallet blir källdörr 5",
  async ({ page }) => {
    test.setTimeout(180_000);
    const fel = L.vakt(page);
    const anrop = L.spana(page);
    await L.fejkatMoln(page);
    await L.oppna(page);

    /* Provet ligger i Sparat sedan provdagen — dagarna delar bas, precis som en
       lärares dator gör mellan två morgnar. Kördes bara den här dagen skrivs
       det först; en dag ska gå att köra ensam. */
    /* Pappret läggs i högen med en gång och får sitt id först när servern
       svarat — ett id som ännu är undefined är alltså inte «inget prov», det
       är ett prov som inte hunnit bli skrivet. Dagen väntar på id:t. */
    const provet = () => page.evaluate(() => {
      const p = window.Dokument.sparade().find(
        v => (v.dokument || v).typ === "Prov" && v.id);
      return p ? p.id : null;
    });
    if (await provet() === null) {
      await L.valjKlass(page, "NA25");
      await L.skriv(page, { typ: "Prov", moment: "derivator" });
      await L.vantaPapper(page, 60_000);
      await page.locator("#godkann").click();
      await expect.poll(provet, { timeout: 120_000 }).not.toBeNull();
    }
    const provId = await provet();
    await page.evaluate(id => window.Rattning.oppna(
      window.Dokument.sparade().find(v => v.id === id)), provId);

    // Raderna är serverns: en per uppgift och deluppgift, med provets egna
    // förmågor.
    const rader = page.locator("#rattninglista .rattrad");
    await expect(rader.first()).toBeVisible({ timeout: 20_000 });
    const antal = await rader.count();
    expect(antal).toBeGreaterThan(2);

    await page.locator("#rattelever").fill("22");
    const nycklar = await rader.evaluateAll(
      els => els.map(e => e.getAttribute("data-nyckel")));
    await page.locator(`.rattrad[data-nyckel="${nycklar[0]}"] .rattfalt`).fill("40");
    await page.locator(`.rattrad[data-nyckel="${nycklar[1]}"] .rattfalt`).fill("12");
    await page.locator("#rattningspara").click();

    await expect.poll(() => anrop.filter(a => a.metod === "PUT"
      && a.vag.endsWith("/rattning")).length, { timeout: 30_000 }).toBe(1);

    // Rättningen överlever omstarten — «Rättat · NN %» ska inte vara ett
    // minnesvärde.
    const sparade = await L.efterOmladdning(page);
    const rad = sparade.find(v => v.id === provId);
    expect(rad.rattat || (rad.dokument || {}).rattat).toBeTruthy();

    // Källdörr 5: utfallet följer med in i nästa skrivning — omprovet ska ta om
    // det klassen föll på, inte gå igenom momentet en gång till.
    await page.evaluate(id => window.Dokument.sattResultat(
      window.Dokument.sparade().find(v => v.id === id)), provId);
    await L.valjKlass(page, "NA25");
    await L.skriv(page, { moment: "det klassen föll på" });
    await L.vantaPapper(page);
    const gen = L.traff(anrop, "/api/planning/generate").pop();
    expect(gen.kropp.utfall_dokument_id).toBe(provId);
    L.rent(fel);
  });

// ── Dag 5 ────────────────────────────────────────────────────────────────
test("dag 5 — pardokument: arbetsbladet skrivs PÅ tavlan man godkände",
  async ({ page }) => {
    test.setTimeout(180_000);
    const fel = L.vakt(page);
    const anrop = L.spana(page);
    await L.fejkatMoln(page);
    await L.oppna(page);

    await L.valjKlass(page, "NA24");
    // Två typer i följd: tvåan skrivs PÅ ettan, inte vid sidan av.
    await L.skriv(page, { typ: ["Tavla", "Arbetsblad"], moment: "primitiva funktioner" });
    await L.vantaPapper(page);

    // Raden säger redan före godkännandet att tvåan väntar.
    expect(await page.evaluate(() => window.Lagen())).toEqual(["Tavla", "Arbetsblad"]);
    await expect(page.locator("#foljerad")).toBeVisible();

    const fore = await L.antalSparade(page);
    await page.locator("#godkann").click();
    await expect.poll(() => L.antalSparade(page), { timeout: 60_000 }).toBeGreaterThan(fore);

    // Parförslaget öppnas FÖRST här — när det första ligger i Sparat och det
    // finns något att bygga på.
    const notis = page.locator("#foljeskal");
    await expect(notis).toBeVisible({ timeout: 30_000 });
    await expect(notis).toContainText("Arbetsblad");
    await page.locator("#foljeja").click();

    // «Andra hand»: steget är inte längre ett val — typen är bestämd sedan
    // första rundan, och raden säger vad den bygger på.
    await expect(page.locator("#andrahandtext")).toContainText("skrivs på tavlan");
    const skrivet = L.vantarGenerering(page);
    await page.locator("#skriv").click();
    await skrivet;
    await L.vantaPapper(page, 60_000);
    const gen = L.traff(anrop, "/api/exams/generate").pop();
    expect(gen.kropp.typ).toBe("arbetsblad");
    expect(gen.kropp.klass).toBeTruthy();

    // Och tvåan hamnar på samma lektion som ettan.
    const fore2 = await L.antalSparade(page);
    await page.locator("#godkann").click();
    await expect.poll(() => L.antalSparade(page), { timeout: 120_000 })
      .toBeGreaterThan(fore2);
    L.rent(fel);
  });

// ── Dag 6 ────────────────────────────────────────────────────────────────
test("dag 6 — lovdag: ingenting att planera, och vägen ut är nästa skolvecka",
  async ({ page }) => {
    const fel = L.vakt(page);
    await L.fejkatMoln(page);
    await L.oppna(page, { tid: L.LOVDAG });
    await page.getByRole("tab", { name: "Planering" }).click();

    /* Under ett lov planerar man inte lovet: appen öppnar veckan EFTER
       (höstlovet 26–30 oktober ligger i vecka 44, alltså öppnas vecka 45). */
    await expect(page.locator("#schemavecka")).toHaveText("Vecka 45");
    await expect(page.locator("#schemagrid .lekt[data-valjbar]").first()).toBeVisible();

    // Går man tillbaka in i lovveckan står den tom, och knappen byter uppgift.
    const knapp = page.locator("#schemanu");
    await knapp.click();
    await expect(page.locator("#schemavecka")).toHaveText("Vecka 44");
    await expect(page.locator("#schemasum")).toContainText("lov");
    await expect(page.locator("#schemagrid .lekt[data-valjbar]")).toHaveCount(0);
    await expect(knapp).toHaveText("Nästa skolvecka");
    await page.waitForTimeout(700);          // veckan glider in (klass.js byt)
    await knapp.click();
    await expect(page.locator("#schemavecka")).toHaveText("Vecka 45");
    L.rent(fel);
  });

// ── Dag 7 ────────────────────────────────────────────────────────────────
test("dag 7 — dagen då allt går fel: varje stopp är ett svenskt besked",
  async ({ page }) => {
    test.setTimeout(180_000);
    const fel = L.vakt(page);
    await L.fejkatMoln(page, {
      // 429 mitt i körningen: molnet svarar med serverns egen felmening.
      transkribering: route => route.fulfill({
        status: 200, contentType: "text/event-stream",
        body: 'data: {"type":"progress","pct":30}\n\n'
            + 'data: {"type":"error","message":"OpenAI svarade 429 (för många '
            + 'anrop). Vänta en minut och försök igen."}\n\n' }),
    });
    await L.oppna(page);
    await L.transkribera(page);

    /* Felet kommer ur serverns `message`-fält (app/web/sse.py). Läste klienten
       bara `error` blev varenda jobb som föll mitt i strömmen ett «Okänt fel»
       hos läraren — och det som stod där var i själva verket den åtgärdbara
       meningen. */
    const varning = page.locator("#korvarningar .varnruta");
    await expect(varning).toBeVisible({ timeout: 20_000 });
    await expect(varning).toContainText("429");
    await expect(varning).not.toContainText("Okänt fel");
    await expect(page.locator("#klarruta")).toBeHidden();

    // GPU:n är upptagen när tavlan ska skrivas: ett besked med en väg vidare,
    // och inget halvskrivet dokument.
    await page.route("**/api/planning/generate", route => route.fulfill({
      status: 409, contentType: "application/json",
      body: JSON.stringify({ error: "GPU:n är upptagen — försök igen strax." }) }));
    await L.valjKlass(page, "NA25");
    const innan = await L.antalSparade(page);
    await L.skriv(page, { moment: "derivatans definition" });
    const ruta = page.locator("#skrivstatus .fsvar");
    await expect(ruta).toHaveAttribute("data-lage", "stoppad", { timeout: 30_000 });
    await expect(ruta).toContainText("upptagen");
    /* «Inget halvskrivet dokument» mäts i högen, inte på skärmen: utkastet från
       en tidigare dag återställs ur servern vid sidladdning (Etapp 0.2) och
       ligger alltså kvar synligt — det är inte det som är fel. Fel vore ett
       papper som lades i Sparat trots att skrivningen aldrig blev av. */
    expect(await L.antalSparade(page)).toBe(innan);

    /* Vägen vidare är kortets egen knapp — Skriv-knappen är släckt så länge
       körningen står stoppad, och det är meningen: läraren ska inte kunna
       starta två körningar på samma stopp. */
    const igen = ruta.getByRole("button", { name: "Försök igen" });
    await expect(igen).toBeVisible();

    // Nätet dör mitt i nästa försök — samma krav.
    await page.unroute("**/api/planning/generate");
    await page.route("**/api/planning/generate", route => route.abort("internetdisconnected"));
    await igen.click();
    await expect(ruta).toHaveAttribute("data-lage", "stoppad", { timeout: 30_000 });
    expect(await L.antalSparade(page)).toBe(innan);

    // Och när molnet är tillbaka går dagen vidare — appen är inte fastlåst.
    await page.unroute("**/api/planning/generate");
    const skrivet = L.vantarGenerering(page);
    await ruta.getByRole("button", { name: "Försök igen" }).click();
    await skrivet;
    await L.vantaPapper(page, 60_000);
    // Dagens egna sabotage får synas i konsolen — appens egna fel får inte.
    L.rent(fel, { tillat: [/api\/planning\/generate/] });
  });

// ── Dag 8 ────────────────────────────────────────────────────────────────
test("dag 8 — boken: slå upp ett uppslag och skriv tavlan ur det",
  async ({ page }) => {
    test.setTimeout(180_000);
    const fel = L.vakt(page);
    const anrop = L.spana(page);
    await L.fejkatMoln(page);
    // Bokens OCR är ett molnpass som kostar minuter och pengar — den fejkas
    // här, precis som transkriberingen. Det som prövas är att UPPSLAGET når
    // generatorn på servern.
    const BOK = { id: 3, namn: "Matematik 5000+ Kurs 2c", kurs: "Matematik, nivå 2c",
                  sidor: 120, sidoffset: 2, status: "klar", lasta: 9,
                  avsnitt: [{ nr: "1.2", titel: "Linjära modeller",
                              kap: "Kapitel 1 · Algebra", vag: "Räta linjens ekvation",
                              sid: "15–23", uppg: 34 }] };
    const UPPG = [{ nr: 1215, sida: 15, niva: 1 }, { nr: 1221, sida: 16, niva: 2 }];
    await page.route("**/api/bocker**", route => {
      const url = new URL(route.request().url());
      const svar = url.pathname.endsWith("/uppslag")
        ? { fran: 15, till: 16, uppgifter: UPPG, olasta: [], sidor: [] }
        : { bocker: [BOK] };
      return route.fulfill({ status: 200, contentType: "application/json",
                             body: JSON.stringify(svar) });
    });
    await L.oppna(page);
    await page.waitForFunction(() => window.Bok && window.Bok.franServern());

    /* Klassprofilen minns en bok som INTE står på hyllan — prototypens förval
       (profil.js BOK_FOR), eller en bok läraren tagit bort. Det är läget efter
       några planeringar, och det är det farliga: profilen la tillbaka namnet i
       hyllan, uppslaget fick ett namn utan id på servern, och `bokval()` kastade
       tyst bort hela boken. Kvittot sa «Boken · s. 15–16» medan prompten skrevs
       utan en enda sida. */
    await page.evaluate(() => {
      const m = window.Profil.minne();
      m.NA25 = { kurs: "Matematik, nivå 2c", kursNu: "Matematik, nivå 2c",
                 bok: "Matematik 5000+ 3c", bokN: 5, senasteSida: 12,
                 sidorPerLektion: 4, n: 5, typer: { Tavla: 5 } };
    });

    await L.valjKlass(page, "NA25");
    // Boken som slås upp är hyllans, inte minnets.
    expect(await page.evaluate(() => window.Uppslag.spann().bok))
      .toBe("Matematik 5000+ Kurs 2c");
    await page.getByRole("tab", { name: "Planering" }).click();
    await page.evaluate(() => { window.PlanSteg.las(2, false); window.PlanSteg.gaTill(2); });
    /* Bokdörren måste stå ÖPPEN — uppslaget följer med till servern bara när
       läraren valt boken som källa (plan.js bokval). Är den stängd skrivs
       tavlan utan sidorna, och det syns inte på pappret. */
    const dorr = page.locator('.kalla[data-dorr="bok"]');
    if (await dorr.getAttribute("aria-pressed") !== "true") await dorr.click();
    await page.evaluate(() => window.Uppslag.satt(15, 16));
    await expect.poll(() => page.locator("#uppgnivaer .uppgchip").count(),
                      { timeout: 20_000 }).toBe(2);

    await L.skriv(page, { moment: "linjära modeller" });
    await L.vantaPapper(page, 60_000);
    // Uppslaget följde med till servern: den läser sidorna själv och lägger dem
    // i prompten (routes_planning bok_las_text).
    const gen = L.traff(anrop, "/api/planning/generate").pop();
    expect(gen.kropp.bok, "uppslaget nådde aldrig servern").toBeTruthy();
    expect(gen.kropp.bok).toEqual({ id: 3, fran: 15, till: 16 });
    L.rent(fel);
  });

// ── Dag 9 ────────────────────────────────────────────────────────────────
test("dag 9 — bara transkribering: tre filer i kö, en av dem förbannad",
  async ({ page }) => {
    test.setTimeout(180_000);
    const fel = L.vakt(page);
    let n = 0;
    await L.fejkatMoln(page, {
      transkribering: route => {
        n += 1;
        // Fil två är trasig: ffprobe hittar inget ljudspår. Kön ska ta sig
        // igenom den och köra vidare — inte stanna på den.
        if (n === 2) {
          return route.fulfill({
            status: 200, contentType: "text/event-stream",
            body: 'data: {"type":"error","message":"Filen saknar ljudspår — '
                + 'kontrollera att inspelningen blev av."}\n\n' });
        }
        return route.fulfill({ status: 200, contentType: "text/event-stream",
                               body: L.korning() });
      },
    });
    await L.oppna(page);

    for (const namn of ["NA25 2026-09-08 09.05.m4a",
                        "TE25prk 2026-09-08 13.45.m4a",
                        "IN24prk 2026-09-08 14.40.m4a"]) {
      await page.evaluate(f => laggTill(f, "00:45:00", "C:/inspelningar/" + f), namn);
    }
    await expect(page.locator("#ko-steg1 .korad")).toHaveCount(3);
    await page.locator("#starta").click();

    // Den trasiga filen ger ett besked med filens namn — inte «Okänt fel», och
    // inte en bar som står still.
    const varning = page.locator("#korvarningar .varnruta");
    await expect(varning).toBeVisible({ timeout: 40_000 });
    await expect(varning).toContainText("ljudspår");
    // …och de andra två blev ändå klara.
    await expect(page.locator("#klarruta")).toBeVisible({ timeout: 60_000 });
    expect(n).toBe(3);
    L.rent(fel);
  });

// ── Dag 10 ───────────────────────────────────────────────────────────────
test("dag 10 — terminsvyn: hitta veckan som saknar material och planera den",
  async ({ page }) => {
    test.setTimeout(180_000);
    const fel = L.vakt(page);
    await L.fejkatMoln(page);
    await L.oppna(page);
    await page.getByRole("tab", { name: "Planering" }).click();

    // Samma panel, andra zoomläget.
    await page.locator("#schemalage button", { hasText: "Termin" }).click();
    await expect(page.locator("#ark-klass")).toHaveAttribute("data-lage", "termin");

    // Bandet svarar på EN fråga: vilka veckor framåt saknar material. Klicket
    // ska landa i veckan bandet pekade på.
    const rutor = page.locator(".tbv");
    await expect(rutor.first()).toBeVisible();
    const mal = rutor.nth(2);
    const nr = (await mal.locator(".tbnr").textContent()).trim().replace("v", "");
    await mal.click();
    await expect(page.locator("#ark-klass")).toHaveAttribute("data-lage", "vecka");
    await expect(page.locator("#schemavecka")).toHaveText(`Vecka ${nr}`);

    // Och veckan går att planera direkt — det var poängen med att klicka dit.
    await page.locator("#schemagrid .lekt[data-valjbar]").first().click();
    await L.skriv(page, { moment: "repetition inför provet" });
    await L.vantaPapper(page, 60_000);
    const fore = await L.antalSparade(page);
    await page.locator("#godkann").click();
    await expect.poll(() => L.antalSparade(page), { timeout: 60_000 }).toBeGreaterThan(fore);
    L.rent(fel);
  });
