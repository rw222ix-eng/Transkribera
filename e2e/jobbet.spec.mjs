import { expect, test } from "@playwright/test";
import * as L from "./larardag.mjs";

/* JOBBET SOM STOD KVAR
 *
 * Läraren startade ett prov, stängde fliken och kom tillbaka. Förr fanns
 * ingenting: körningen dog med strömmen, och den var ändå betald. Nu ligger
 * jobbet i databasen (app/web/sse.py, app/db.py `jobb`) och strömmen är ett
 * fönster mot det — och det ÄR appens jobb att säga att något pågår när hon
 * kommer tillbaka.
 *
 * Två halvor prövas, och de prövas olika:
 *
 * 1. SERVERNS halva mot den riktiga servern: ett skrivet prov ska ha lämnat ett
 *    jobb efter sig, med sin typ, sin status och sin historik. Bara molnet är
 *    fejkat (kassett, e2e/testserver.py).
 * 2. KLIENTENS halva mot en påhittad körning. Med FEJK_CLAUDE är ett prov klart
 *    på sekunder, och «ladda om mitt i» blir ett lopp mot en körning som redan
 *    hunnit bli klar — ett flakigt test som mäter maskinens hastighet. Här
 *    svarar därför /api/jobb/* med ett jobb som står still, och det som mäts är
 *    det som faktiskt kunde gå sönder: att remsan kommer fram, att den bär
 *    serverns rad, att mätaren rör sig och att Avbryt går vägen om servern.
 *
 * Pytest-tvillingen (tests/test_jobb.py) prövar samma sak från andra hållet.
 */

test.afterEach(async ({ page }) => {
  const hogen = await (await page.request.get("/api/dokument")).json()
    .catch(() => ({}));
  if (hogen && hogen.utkast && hogen.utkast.id) {
    await page.request.delete(`/api/dokument/${hogen.utkast.id}`).catch(() => {});
  }
});

test("ett skrivet prov lämnar ett jobb med sin historik efter sig", async ({ page }) => {
  await L.fejkatMoln(page);
  await L.oppna(page);
  await L.valjKlass(page, "NA25");
  await L.skriv(page, { typ: "Prov", moment: "derivator" });
  await L.vantaPapper(page, 60_000);

  const lista = await (await page.request.get("/api/jobb/aktiva")).json();
  const provet = lista.jobb.find(j => j.typ === "prov");
  expect(provet, `inget prov-jobb i ${JSON.stringify(lista.jobb)}`).toBeTruthy();
  expect(provet.status).toBe("done");
  /* Pappret går att hitta ur jobbet — det är hela nyttan med `resultat_ref`
     för den som kommer tillbaka efter att jobbet blivit klart utan henne. */
  expect(provet.resultat_ref).toBeTruthy();

  /* Och historiken går att spela upp igen, i ordning, med sina steg. */
  const svar = await page.request.get(`/api/jobb/${provet.id}/strom?fran=0`);
  const rader = (await svar.text()).split("\n")
    .filter(r => r.startsWith("data:"))
    .map(r => JSON.parse(r.slice(5)));
  expect(rader.length).toBeGreaterThan(2);
  expect(rader[rader.length - 1].type).toBe("done");
  /* Numren är sammanhängande — ett hopp betyder en tappad rad, och då kan
     ingen klient veta var den ska ta vid. */
  expect(rader.map(r => r.seq)).toEqual(rader.map((_, i) => i + 1));
  /* De strukturerade stegen finns, och de räknas mot samma tak. */
  const steg = rader.filter(r => r.type === "progress" && r.steg);
  expect(steg.length, "inga domänsteg i historiken").toBeGreaterThan(0);
  for (const s of steg) expect(s.steg).toBeLessThanOrEqual(s.av);
});

/* REMSAN ÄR EN VÄG, INTE ETT KVITTO
 *
 * Lärarens fynd 2026-09-06: hon klickade på remsans text för att komma DIT
 * jobbet skrivs, och ingenting hände. Texten säger vad som pågår; det enda
 * stället där det syns på riktigt är planeringens statusruta, en flik bort.
 */
test("klick på remsans text går till planeringen", async ({ page }) => {
  await page.route("**/api/jobb/aktiva*", r => r.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      jobb: [], kor: [{ id: 4712, typ: "tavla", status: "running",
                        seq: 1, senaste: "Täckningsdomaren läser urvalet",
                        dokument_id: "c1c82511fd3d", fel: null, resultat_ref: null }],
    }),
  }));
  let forsta = true;
  await page.route("**/api/jobb/4712/strom*", r => {
    if (!forsta) return new Promise(() => {});
    forsta = false;
    return r.fulfill({
      contentType: "text/event-stream",
      body: 'data: {"type":"log","msg":"Täckningsdomaren läser urvalet","seq":1}\n\n',
    });
  });

  await L.oppna(page);
  const remsa = page.locator(".jater");
  await expect(remsa).toBeVisible({ timeout: 15_000 });
  // Klickbar på riktigt: en knapp för skärmläsaren och för tangentbordet.
  await expect(remsa.locator(".jtext")).toHaveAttribute("role", "button");

  await expect(page.locator("#vy-planering")).toBeHidden();
  await remsa.locator(".jtext").click();
  await expect(page.locator("#vy-planering")).toBeVisible();
  // Remsan står kvar: jobbet går fortfarande, och Avbryt ska finnas kvar.
  await expect(remsa).toBeVisible();
});

test("remsan tar upp ett jobb som fortfarande går, och Avbryt går till servern", async ({ page }) => {
  const avbrutna = [];

  await page.route("**/api/jobb/aktiva*", r => r.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      jobb: [], kor: [{ id: 4711, typ: "prov", status: "running",
                        seq: 2, senaste: "Skriver uppgift 3 av 12 …",
                        dokument_id: null, fel: null, resultat_ref: null }],
    }),
  }));
  /* En ström som ger historiken och sedan STÅR KVAR ÖPPEN — det är så en
     riktig körning ser ut, och det är skillnaden mellan «jobbet går» och
     «anslutningen tog slut». Andra anropet fullföljs aldrig: förfrågan hänger,
     precis som en tyst men levande SSE-ström gör. */
  let forsta = true;
  await page.route("**/api/jobb/4711/strom*", r => {
    if (!forsta) return new Promise(() => {});
    forsta = false;
    return r.fulfill({
      contentType: "text/event-stream",
      body: 'data: {"type":"progress","steg":2,"av":4,"text":"Skriver uppgifterna","seq":1}\n\n'
          + 'data: {"type":"log","msg":"Skriver uppgift 3 av 12 …","seq":2}\n\n'
          + 'data: {"type":"progress","steg":3,"av":4,"text":"Domarna granskar","seq":3}\n\n',
    });
  });
  await page.route("**/api/jobb/4711/avbryt", r => {
    avbrutna.push(r.request().method());
    return r.fulfill({ contentType: "application/json",
                       body: JSON.stringify({ ok: true, status: "avbrutet" }) });
  });

  await L.oppna(page);

  const remsa = page.locator(".jater");
  await expect(remsa).toBeVisible({ timeout: 15_000 });
  /* Typen står först — läraren ska veta VAD som pågår, inte bara att något gör
     det — och serverns egen rad står efter den. */
  await expect(remsa.locator(".jtext")).toContainText("Provet");
  await expect(remsa.locator(".jtext")).toContainText("Domarna granskar");
  /* Mätaren står på tredje steget av fyra, inte på en gissning. */
  const bredd = await remsa.locator(".jspar i").evaluate(el => el.style.width);
  expect(parseFloat(bredd)).toBeCloseTo(75, 0);

  await remsa.locator(".jstopp").click();
  await expect.poll(() => avbrutna).toEqual(["POST"]);
  await expect(remsa).toHaveCount(0, { timeout: 5_000 });
});
