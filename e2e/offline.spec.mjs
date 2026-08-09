import { expect, test } from "@playwright/test";

/* OFFLINE-INTEGRITETEN
 *
 * Transkribera är en skrivbordsapp. Den ska rendera rätt på ett tåg.
 *
 * Prototypen i Claude Design hämtade sju saker från nätet: Switzer från
 * Fontshare, tre teckensnittsfamiljer och tavlans handstil från Google Fonts,
 * KaTeX från jsdelivr, samt figurmotorns hela Typst-kedja — kompilator-wasm,
 * ritar-wasm, typsts standardsnitt och CeTZ-paketet. Alla ligger nu lokalt.
 *
 * Ingen av dem gick sönder synligt när de saknades: sättningen föll tillbaka på
 * Arial, matematiken blev oformaterad text och figurerna uteblev tyst. Just
 * därför behövs ett test — ett återinfört CDN-anrop syns inte i en skärmbild
 * med nät, och den som testar har alltid nät.
 *
 * Testet spärrar allt som inte är den lokala servern. Ett kvarglömt nätanrop
 * blir då ett fel i stället för en tyst lyckad hämtning.
 */

/** Släpper igenom localhost, data: och blob: — spärrar och loggar allt annat. */
async function spärraNätet(page, utifrån) {
  await page.route("**/*", route => {
    const url = route.request().url();
    if (url.startsWith("http://127.0.0.1:") || url.startsWith("http://localhost:")
        || url.startsWith("data:") || url.startsWith("blob:")) {
      return route.continue();
    }
    utifrån.push(url);
    return route.abort();
  });
}

/** Öppna appen och vänta tills den är LADDAD — inte tills nätet råkar tiga.
 *
 * `waitUntil: "networkidle"` stod här och väntade på 500 ms utan en enda öppen
 * förbindelse. Det är ett tajmingvillkor, inte ett tillståndsvillkor: på CI:s
 * tvåkärniga runner blev servern så trängd att enskilda rutter tog tiotals
 * sekunder, och stiltjen infann sig aldrig inom testets gräns. Playwright
 * avråder själv från flaggan.
 *
 * Appens eget redoläge är vad testerna faktiskt menar, och det är samma villkor
 * som `larardag.oppna` väntar på. Den korta pausen efteråt fångar efterspelet:
 * bilder och typsnitt som hämtas när dokumentet redan är igång — det är just
 * dem ett återinfört CDN-anrop skulle gömma sig bland. */
async function laddad(page) {
  await page.goto("/");
  await page.waitForFunction(() =>
    window.Kalender && window.Kalender.franServern() && window.Dokument
      && window.API && window.API.pa, null, { timeout: 30_000 });
  await page.waitForTimeout(500);
}

test("appen laddar utan ett enda anrop utanför datorn", async ({ page }) => {
  const utifrån = [];
  await spärraNätet(page, utifrån);

  const jsfel = [];
  page.on("pageerror", e => jsfel.push(e.message));

  const misslyckade = [];
  page.on("response", r => { if (r.status() >= 400) misslyckade.push(`${r.status()} ${r.url()}`); });

  await laddad(page);

  expect(utifrån, `appen hämtade från nätet: ${utifrån.join(", ")}`).toEqual([]);
  expect(jsfel, `JS-fel vid start: ${jsfel.join(" | ")}`).toEqual([]);

  // .image-slots.state.json är Claude Designs bildväljare som letar efter sitt
  // tillståndsdokument. Den 404:ar i designprojektet också och påverkar inget —
  // men den ska vara den ENDA som gör det, annars döljer undantaget en riktig
  // trasig sökväg.
  const oväntade = misslyckade.filter(m => !m.includes(".image-slots.state.json"));
  expect(oväntade, `trasiga hämtningar: ${oväntade.join(" | ")}`).toEqual([]);
});

test("typsnitten kommer från appen, inte från Google", async ({ page }) => {
  const utifrån = [];
  await spärraNätet(page, utifrån);
  await laddad(page);

  const laddade = await page.evaluate(() =>
    [...document.fonts].filter(f => f.status === "loaded").map(f => `${f.family} ${f.weight}`));
  expect(laddade.some(f => f.startsWith("Switzer")), `laddade snitt: ${laddade}`).toBe(true);
});

test("displayserifen är Georgia — inte Cormorant Garamond", async ({ page }) => {
  /* Detta är INTE en bugg som ska rättas. Prototypens @import för Cormorant
     Garamond står efter fyra @font-face-regler, och CSS kräver att @import
     kommer först — så webbläsaren slänger den, och hela designen är ritad och
     godkänd mot Georgia (tredje namnet i --serif). Buntar man Cormorant lokalt
     byter 14 rubrikytor utseende på en gång. Testet finns för att den
     ändringen ska kräva ett beslut, inte ett misstag. Se app/web/ui/typsnitt.css. */
  await laddad(page);

  const cormorantLaddad = await page.evaluate(() =>
    [...document.fonts].some(f => f.family === "Cormorant Garamond" && f.status === "loaded"));
  expect(cormorantLaddad).toBe(false);

  const stack = await page.locator(".rubrik").first().evaluate(el => getComputedStyle(el).fontFamily);
  expect(stack).toContain("Georgia");
});

test("figurmotorn kompilerar en figur med nätet avstängt", async ({ page }) => {
  /* Figurerna är CeTZ-källa som kompileras till SVG i webbläsaren av Typst.
     Kedjan har fyra delar som alla låg på nätet i prototypen: bundlen, två
     wasm-moduler, typsts standardsnitt och CeTZ-paketet (som i sin tur drar in
     oxifmt). Missar man en enda dör kompileringen — och figurerna är själva
     poängen med prov- och arbetsbladen. */
  const utifrån = [];
  await spärraNätet(page, utifrån);
  await page.goto("/", { waitUntil: "domcontentloaded" });

  // Cachen töms först: en träff i localStorage skulle bevisa att figuren en gång
  // kompilerades, inte att den kan kompileras nu.
  await page.evaluate(() => Object.keys(localStorage)
    .filter(k => k.startsWith("figurcache:")).forEach(k => localStorage.removeItem(k)));

  const svg = await page.evaluate(async () => {
    const källa = 'circle((0,0), radius: 1.6)\nline((-1.6,0),(1.6,0))\ncontent((0,-2.1), [A])';
    try { return { ok: true, svg: await window.Figur.svg(källa) }; }
    catch (e) { return { ok: false, fel: String(e) }; }
  });

  expect(svg.ok, `kompileringen misslyckades: ${svg.fel}`).toBe(true);
  expect(svg.svg).toContain("<svg");
  expect(utifrån, `figurmotorn gick ut på nätet: ${utifrån.join(", ")}`).toEqual([]);
});
