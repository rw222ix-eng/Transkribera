// Paritetslucka 1 (viktigast): automatisk insiktsextraktion. När HELA
// transkriberingskön är klar analyseras varje ny lektion med den lokala
// modellen i bakgrunden — utan knapp — och Agenda/Terminstrender/Inför nästa
// lektion i Inspelningar-vyn fylls på. Portad från gamla appens
// autoExtractLessons (app.js:2337-2352) till frontend/src/lib/transkribera/
// actions.js (extractQueue/extractLessonsQueued), utlöst i startRun():s
// done-gren när kön är tom.
//
// KÄRNKRAVET som testas här: att en färdig kö POSTar
// /api/lessons/{id}/extract EN GÅNG PER lektion — räknat, inte antaget — och
// att de POSTerna sker SEKVENTIELLT (nästa startar först när den föregåendes
// SSE-ström nått 'done'/'error'), aldrig parallellt. GPU-arbitern serialiserar
// bara mot Whisper i produktion (FakeArbiter i serve_test_app.py beviljar
// alltid GPU:n) — utan klientens egen sekvensiering skulle två POST:er kunna
// gå ut samtidigt helt obehindrat i fejkmiljön.
//
// TESTMILJÖN HAR BARA EN RIKTIG LEKTION ATT SKAPA (en enda .wav-fixtur,
// e2e/serve_test_app.py), så en äkta TVÅ-lektioners kö går inte att bygga via
// UI:t. I stället körs EN riktig transkribering (äkta /api/transcribe, äkta
// done-event, äkta historik-id) och window.fetch dubbleras sedan för att:
//   1. lägga till EN extra rad i /api/lessons-svaret (samma history_id som
//      den riktiga lektionen, ett hittepå-id) — enda vägen att få
//      extraktionens EGEN /api/lessons-slagning att hitta två lektioner utan
//      en andra riktig fixturfil, och
//   2. fullt kontrollera de två POST /api/lessons/*/extract-anropens SSE-svar,
//      så sekvensordningen går att bevisa deterministiskt — samma
//      window.fetch-dubblerings-mönster som bromsaStrommen i
//      transkribera-korning.spec.mjs.
// KÖNS EGEN /api/transcribe rörs INTE av dubbleringen — den går till den
// riktiga (fejk-inferens-)backenden precis som i alla andra specar, så
// triggern ("kön är tom, körningen klar") är helt äkta.
//
// TÄCKER OCKSÅ att panelerna laddas om när extraktionen är klar (GET
// /api/agenda, den enda panelen utan klassfilter och alltså den enda som
// alltid hämtar) och att flödet är TYST: inga konsolfel, och guidens EGEN
// statusrad ("Klar"/klarbeskedet) rörs inte av bakgrundsjobbet.
//
// TÄCKER INTE: generationsvakten mot en ANDRA, överlappande extraktions-
// sekvens (extractGen i actions.js) — det skulle kräva en riktig andra kö
// mitt i den första sekvensens SSE-fönster, vilket samma enda-fixtur-
// begränsning som ovan gör opraktiskt att bygga deterministiskt. Panelernas
// EGNA hämtningar (Agenda/Terminstrender/Inför nästa lektion) har täckning i
// inspelningar-paneler.spec.mjs.
import { test, expect, failOnConsoleError } from "./helpers/app";

/** Förkontroll: utan demofilen blir felet annars en obegriplig timeout. */
async function kravExempel(request) {
  const sample = await request.get("/api/sample");
  expect(
    sample.status(),
    'Saknad testfixtur: "Mamma waw isolerad.wav" i repo-roten (se e2e/serve_test_app.py). ' +
      "/api/sample svarade " + sample.status() + ".",
  ).toBe(200);
  return sample.json();
}

test("Transkribera (/next/): en färdig kö extraherar sekventiellt och laddar om panelerna", async ({
  page,
  request,
}) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await kravExempel(request);

  // BASLINJEN: id:n som redan finns INNAN den här körningen, så den nya,
  // riktiga lektionsraden går att peka ut EXAKT — inte gissa position.
  // Servern garanterar ingen viss sorteringsordning som håller stabil över
  // hela testsvitens körning (flera specar skapar och raderar lektioner i
  // samma delade fejkserver, se playwright.config.ts).
  const baslinje = await (await request.get("/api/lessons")).json();
  const kandaId = baslinje.map((l) => l.id);

  await page.addInitScript((kandaId) => {
    window.__e2eExtrakt = { anrop: [], strommar: [], injicerad: false };
    const kanda = new Set(kandaId);
    const riktig = window.fetch.bind(window);
    const kodare = new TextEncoder();

    window.fetch = (input, init) => {
      const url = String(typeof input === "string" ? input : input.url).split("?")[0];
      const metod = ((init && init.method) || "GET").toUpperCase();

      // 1) Injicerar EN extra rad i /api/lessons-svaret — samma history_id
      //    som den nya, riktiga lektionen, ett hittepå-id (9999001). Se
      //    filhuvudets kommentar för varför.
      if (/\/api\/lessons$/.test(url) && metod === "GET") {
        return riktig(input, init).then(async (resp) => {
          const rader = await resp.json().catch(() => null);
          if (Array.isArray(rader) && !window.__e2eExtrakt.injicerad) {
            const ny = rader.find((r) => !kanda.has(r.id));
            if (ny) {
              window.__e2eExtrakt.injicerad = true;
              rader.push(Object.assign({}, ny, { id: 9999001 }));
            }
          }
          return new Response(JSON.stringify(rader), {
            status: resp.status,
            headers: { "Content-Type": "application/json" },
          });
        });
      }

      // 2) Fullt kontrollerade SSE-svar för de två extraktionsanropen — testet
      //    styr när varje POST "blir klar" i stället för att förlita sig på
      //    den riktiga backendens (obeviljat snabba) svarstid.
      const m = /\/api\/lessons\/(\d+)\/extract$/.exec(url);
      if (m && metod === "POST") {
        let styrning;
        const strom = new ReadableStream({ start(c) { styrning = c; } });
        window.__e2eExtrakt.anrop.push({ id: m[1], t: performance.now() });
        window.__e2eExtrakt.strommar.push({
          id: m[1],
          skicka(ev) { styrning.enqueue(kodare.encode("data: " + JSON.stringify(ev) + "\n\n")); },
          stang() { styrning.close(); },
        });
        return Promise.resolve(new Response(strom, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }));
      }

      return riktig(input, init);
    };
  }, kandaId);

  await page.goto("/next/");

  // En riktig kö, ETT objekt — kökedjan (flera poster i rad) har egen
  // täckning i transkribera-korning.spec.mjs; den här specen prövar vad som
  // händer EFTER att kön tömts, inte kedjan i sig.
  await page.getByRole("button", { name: "ett exempel", exact: true }).click();
  const start = page.getByRole("button", { name: "Starta transkribering", exact: true });
  await expect(start).toBeEnabled({ timeout: 20_000 });
  await start.click();

  const status = page.locator(".kort .status");
  await expect(status).toHaveText("Klar", { timeout: 30_000 });

  // Guidens EGEN klarbesked ska stå orört av vad som händer i bakgrunden —
  // extraktionen får varken blockera det eller skriva över det.
  await expect(page.getByText("Klart — lektionen är sparad.")).toBeVisible();

  // Väntar in FÖRSTA extraktionsanropet — bevis att triggern verkligen
  // fyrade så snart kön tömdes.
  await page.waitForFunction(() => window.__e2eExtrakt?.anrop.length >= 1, { timeout: 15_000 });

  // KÄRNAN: anrop nr 2 får INTE ha startat än. Postar koden i stället
  // parallellt (t.ex. Promise.all över lektions-id:na i stället för en
  // rekursiv kedja) skulle båda redan ligga i anrop-listan här.
  expect(
    await page.evaluate(() => window.__e2eExtrakt.anrop.length),
    "Extraktionens andra anrop startade innan det första var klart — inte sekventiellt",
  ).toBe(1);

  // Släpp det FÖRSTA anropets ström.
  await page.evaluate(() => {
    const s = window.__e2eExtrakt.strommar[0];
    s.skicka({ type: "done" });
    s.stang();
  });

  // Väntar in det ANDRA anropet.
  await page.waitForFunction(() => window.__e2eExtrakt?.anrop.length >= 2, { timeout: 15_000 });

  const [forsta, andra] = await page.evaluate(() => window.__e2eExtrakt.anrop);
  expect(
    andra.t,
    "Andra anropets tidsstämpel låg inte efter första — sekvensen gick inte i ordning",
  ).toBeGreaterThan(forsta.t);

  // Panelerna ska INTE ha laddats om ännu — extraktionen är inte klar (den
  // andra lektionen väntar fortfarande på sitt eget svar).
  const agendaOm = page.waitForRequest(
    (r) => r.method() === "GET" && new URL(r.url()).pathname === "/api/agenda",
    { timeout: 15_000 },
  );

  // Släpp det ANDRA (och sista) anropets ström.
  await page.evaluate(() => {
    const s = window.__e2eExtrakt.strommar[1];
    s.skicka({ type: "done" });
    s.stang();
  });

  // Panelerna laddas om — extraktionens enda synliga effekt utåt (den är
  // TYST i övrigt: ingen toast, ingen skrivning på guidens statusrad).
  await agendaOm;

  // Exakt två anrop, aldrig fler. En tredje POST vore antingen en dubblett
  // eller ett tecken på att generationsvakten öppnat en ny sekvens av misstag.
  expect(await page.evaluate(() => window.__e2eExtrakt.anrop.length)).toBe(2);

  // TYSTNADEN: klarbeskedet står kvar orört, och inga konsolfel någonstans i
  // flödet.
  await expect(status).toHaveText("Klar");
  expect(errors, errors.join("\n")).toEqual([]);
});
