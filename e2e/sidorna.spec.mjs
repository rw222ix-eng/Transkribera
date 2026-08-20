import { expect, test } from "@playwright/test";

/* EGNA FILER — sidorna läraren lägger i dörren
 *
 * Dörren «Egna filer» (plan-sidor.js) laddar upp bokssidor och foton, låter
 * servern bildtolka dem och skriver tolkningen under varje litet papper. Två
 * fel bodde i den kedjan, och båda visade sig först på lektionen:
 *
 *   1. Svaret lästes index för index, som om servern gav EN post per uppladdad
 *      fil. Den ger en post per SIDA: varje PDF expanderas till
 *      «kapitel3.pdf — sida N» (routes_planning.py). Ett kapitel plus ett foto
 *      betydde alltså att fotot fick en PDF-sidas beskrivning under sig — fel
 *      tolkning under fel papper, och läraren har ingen chans att se varför.
 *   2. Allt som gick fel i uppladdningen blev tystnad: en catch svalde felet
 *      och kedjan gick vidare utan sidorna medan planen stod och lovade
 *      «Tolkar dina sidor · N filer». En HEIC rakt ur telefonens kamerarulle
 *      fäller HELA begäran med 400 (servern tar PNG/JPG/WebP/PDF), så ETT
 *      felaktigt format tog alla sidor med sig — utan ett ord.
 *
 * Servern fejkas här: det som prövas är klientens läsning av svaret och dess
 * uppträdande när svaret uteblir.
 */

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

const PDF = { name: "kapitel3.pdf", mimeType: "application/pdf",
              buffer: Buffer.from("%PDF-1.4 fejk") };
const FOTO = { name: "uppgift.jpg", mimeType: "image/jpeg",
               buffer: Buffer.from("fejkat foto") };
const HEIC = { name: "IMG_0421.HEIC", mimeType: "image/heic",
               buffer: Buffer.from("fejkad telefonbild") };
const PNG = { name: "tavlan.png", mimeType: "image/png",
              buffer: Buffer.from("fejkad png") };

/* Kapitlet blir tre sidor hos servern, fotot en. Beskrivningarna är olika med
   flit: de ÄR påståendet — vilken text som hamnar under vilket papper. */
const SVAR = {
  id: "abc123def456",
  filer: [
    { namn: "kapitel3.pdf — sida 1", beskrivning: "Logaritmlagar: definition." },
    { namn: "kapitel3.pdf — sida 2", beskrivning: "Exempel 3: lösta uppgifter." },
    { namn: "kapitel3.pdf — sida 3", beskrivning: "Blandade övningar 3140–3160." },
    { namn: "uppgift.jpg", beskrivning: "Elevens uppgift 1204 på rutat papper." },
  ],
};

/** Fejkar uppladdningsrutten. `fel` ger i stället serverns 400-svar. */
async function fejkaUnderlag(page, { svar = SVAR, fel = null } = {}) {
  const anrop = [];
  await page.route("**/api/planning/underlag", route => {
    anrop.push(route.request().postDataJSON());
    if (fel) {
      return route.fulfill({ status: 400, contentType: "application/json",
                             body: JSON.stringify({ error: fel }) });
    }
    return route.fulfill({ status: 200, contentType: "text/event-stream",
                           body: strom([{ type: "done", result: svar }]) });
  });
  return anrop;
}

/* Filerna läses som data-URL:er av en FileReader — sakra() skickar det som
   hunnit läsas, så uppladdningen får inte startas innan datat finns. */
const oppnaPlaneringen = async (page, filer) => {
  await page.goto("/");
  await page.waitForFunction(() => window.Sidor && window.API && window.API.pa);
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.setInputFiles("#sidfil", filer);
};

const tolkningarna = page =>
  page.locator("#sidminis .sidnamn").allTextContents();

test("tolkningen under fotot är fotots — inte PDF:ens andra sida", async ({ page }) => {
  await fejkaUnderlag(page);
  await oppnaPlaneringen(page, [PDF, FOTO]);
  await expect(page.locator("#sidminis .sidmini")).toHaveCount(2);

  const pid = await page.evaluate(() => window.Sidor.sakra());
  expect(pid).toBe("abc123def456");

  const namn = await tolkningarna(page);
  expect(namn).toHaveLength(2);
  // Kapitlet får sin FÖRSTA sidas beskrivning …
  expect(namn[0]).toContain("Logaritmlagar");
  // … och fotot sin egen. Förr stod «Exempel 3» här, ur PDF:ens sida 2.
  expect(namn[1]).toContain("Elevens uppgift 1204");
});

test("en HEIC stoppas i dörren — de andra sidorna går upp ändå", async ({ page }) => {
  const anrop = await fejkaUnderlag(page, {
    svar: { id: "abc123def456",
            filer: [{ namn: "tavlan.png", beskrivning: "Tavlan från lektionen." }] },
  });
  await oppnaPlaneringen(page, [HEIC, PNG]);

  // Bara PNG:en ligger i raden, och noten säger vilken fil som inte kunde läsas.
  await expect(page.locator("#sidminis .sidmini")).toHaveCount(1);
  await expect(page.locator("#sidnot")).toContainText("IMG_0421.HEIC");
  await expect(page.locator("#sidnot")).toContainText("JPG, PNG eller PDF");

  await page.evaluate(() => window.Sidor.sakra());
  // HEIC:en når aldrig servern — hade den gjort det hade ALLA sidor fallit.
  expect(anrop).toHaveLength(1);
  expect(anrop[0].filer.map(f => f.namn)).toEqual(["tavlan.png"]);
  expect(anrop[0].filer[0].data.startsWith("data:image/png;base64,")).toBe(true);
});

test("en uppladdning som faller ger serverns mening, inte tystnad", async ({ page }) => {
  const MENING = "IMG_0421.HEIC: formatet stöds inte (PNG, JPG, WebP eller PDF)";
  await fejkaUnderlag(page, { fel: MENING });
  await oppnaPlaneringen(page, [PDF, FOTO]);
  await expect(page.locator("#sidminis .sidmini")).toHaveCount(2);

  /* sakra() ska AVVISA. Förr svarade den null på allt som gick fel, och
     jobbkedjan i plan.js skrev tavlan utan sidorna som om inget hänt —
     Fraga.kor visar felets mening bara om löftet faktiskt avvisar. */
  const fel = await page.evaluate(() =>
    window.Sidor.sakra().then(() => null, e => e.message));
  expect(fel).toBe(MENING);
});
