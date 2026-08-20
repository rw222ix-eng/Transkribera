import { expect, test } from "@playwright/test";

/* AVBRYT SKA SLÄPPA DEN SOM HÅLLER LÅSET
 *
 * Fraga.kor() har två lägen. Skrivvägen (plan.js) kör det STORA förloppsläget
 * med `smal: true` och skickar `efterStopp` för att sätta tillbaka «Skriv»,
 * nollställa bladkön och skriva om #plannot. Granskningen (granska.js) kör det
 * enkla läget och släpper sitt formulärlås i samma återanrop.
 *
 * Bara det enkla läget ropade det. Läraren tryckte alltså Avbryt i
 * förloppsraden, förloppet stannade — och skrivknappen satt kvar disabled med
 * bladkön pekande på förra mottagaren, så nästa blad gick till fel elev. Enda
 * vägen tillbaka var att ladda om sidan.
 *
 * Testet kör komponenten direkt i appens egen sida: den ligger laddad där, och
 * ett jobb som ALDRIG svarar är det enda som gör Avbryt meningsfullt att
 * trycka på. Ingen server-rutt är inblandad — kontraktet är komponentens.
 *
 * Vaktens snabba tvilling (strukturell, går på en sekund):
 * tests/test_fragekomponenten.py.
 */

async function avbryt(page, lage) {
  return page.evaluate(async (lage) => {
    const vard = document.createElement("div");
    document.body.appendChild(vard);
    const bok = { stopp: 0, fel: 0, klar: 0 };
    window.Fraga.kor(vard, {
      ...lage,
      omfang: "materialet",
      /* Ett jobb som aldrig svarar — då står förloppet still tills någon
         trycker Avbryt, precis som när Claude tänker länge. */
      jobb: () => new Promise(() => {}),
      svar: "klart",
      efterStopp: () => { bok.stopp++; },
      efterFel: () => { bok.fel++; },
      efterKlar: () => { bok.klar++; },
    });
    await new Promise(r => setTimeout(r, 400));
    vard.querySelector(".fstopp").click();
    /* Avbrytandet gör två saker: ropar återanropet och river anropet. Det
       andra är asynkront (AbortError landar i jobbets .catch), så pausen finns
       för att fånga ett efterFel som inte får komma. */
    await new Promise(r => setTimeout(r, 400));
    bok.lage = vard.querySelector(".fsvar").dataset.lage;
    vard.remove();
    return bok;
  }, lage);
}

test.describe("Avbryt i frågekomponenten", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForFunction(() => window.Fraga && window.Fraga.kor);
  });

  test("det stora förloppsläget (skrivvägen) släpper låset", async ({ page }) => {
    const bok = await avbryt(page, { smal: true });
    expect(bok.stopp).toBe(1);
    expect(bok.lage).toBe("stoppad");
    // Ett avbrott är varken klart eller fel — annars skriver plan.js «Det gick
    // inte att skriva dokumentet» över en ruta läraren själv stängde.
    expect(bok.fel).toBe(0);
    expect(bok.klar).toBe(0);
  });

  test("det enkla läget (granskningen) släpper låset", async ({ page }) => {
    const bok = await avbryt(page, { enkel: true });
    expect(bok.stopp).toBe(1);
    expect(bok.lage).toBe("stoppad");
    expect(bok.fel).toBe(0);
    expect(bok.klar).toBe(0);
  });
});
