import { expect, test } from "@playwright/test";

/* SVITENS EGEN BAS
 *
 * Fram till Etapp 1 körde e2e-sviten mot REPOROTEN: `create_app` utan base_dir
 * pekar dit, så varje POST i ett test skrev i lärarens riktiga
 * transkribera.db, history.json och Transkriberingar/. Det gick alltså inte
 * att skriva ett enda skrivande e2e-test — och det är just de testerna som
 * fångar de fel som kostar en lektion.
 *
 * De två testerna här är beviset: servern skriver i sin egen temporära bas,
 * och ett papper som skrivs dit ligger kvar över en omladdning. Båda skriver
 * på riktigt, utan en enda page.route.
 */

test("servern skriver i svitens egen bas, inte i repot", async ({ request }) => {
  // Säkerhetskopian är den ärligaste frågan «var skriver du?»: den svarar med
  // sökvägen den faktiskt skrev till.
  const res = await request.post("/api/backup", { data: {} });
  expect(res.ok()).toBe(true);
  const kvitto = await res.json();
  expect(kvitto.path.replace(/\\/g, "/")).toContain("transkribera-e2e");
  expect(kvitto.path).not.toContain("Transkribera\\exports");
  expect(kvitto.bytes).toBeGreaterThan(0);
});

test("ett papper som skrivs till servern ligger kvar efter omladdning",
  async ({ page }) => {
    /* Serverns hög måste vara inne INNAN den mäts. Prototypens elva papper
       ligger framme tills /api/dokument svarat, och räknar man dem som
       utgångsläge mäter man fel hög: hydreringen byter ut listan mitt i
       testet och «elva plus ett» blir plötsligt noll. Felet syntes först när
       apan (zz-apan.spec.mjs) hade tömt basen — kapplöpningen fanns hela
       tiden. */
    const hog = page.waitForResponse(r =>
      new URL(r.url()).pathname === "/api/dokument" && r.request().method() === "GET");
    await page.goto("/");
    await page.waitForFunction(() => window.Dokument && window.API && window.API.pa);
    await hog;
    await page.waitForTimeout(150);          // listan ritas om efter svaret
    const fore = await page.evaluate(() => window.Dokument.sparade().length);

    const moment = "e2e-bevis " + Date.now();
    await page.evaluate(m => window.Dokument.arbetsbladAv(
      [{ t: "Beräkna arean", p: 3 }], m, { klass: "NA25", kurs: "Matematik, nivå 2c" }),
      moment);
    await expect.poll(() => page.evaluate(
      () => window.Dokument.sparade().length)).toBe(fore + 1);

    const hog2 = page.waitForResponse(r =>
      new URL(r.url()).pathname === "/api/dokument" && r.request().method() === "GET");
    await page.reload();
    await page.waitForFunction(() => window.Dokument && window.API && window.API.pa);
    await hog2;
    await expect.poll(() => page.evaluate(
      m => window.Dokument.sparade().some(v => v.moment === m), moment),
      { timeout: 15_000 }).toBe(true);
  });
