import { expect, test } from "@playwright/test";

/* NÄR SERVERN DÖR UNDER SIDAN
 *
 * Morgonen 2026-08-30 satt läraren och klickade i en app vars serverprocess var
 * död. Sidan sa ingenting: listorna stod kvar, API.pa var fortfarande sant, och
 * det enda som syntes var att bokväljarens sidblad tömdes ett efter ett — deras
 * `onerror` tar bort varje bild som inte gick att hämta (uppslag.js). Felet såg
 * alltså ut som «förhandsvisningen har försvunnit», inte som «servern är borta».
 *
 * Sonderingen i api.js frågade bara EN gång, vid start. Nu frågar den vidare,
 * och testet spärrar API:et under en laddad sida för att härma en död server.
 * Att stänga av den riktiga servern går inte: sviten delar den med alla andra
 * filer.
 */

/** Appen laddad och kopplad till servern. */
async function laddad(page) {
  await page.goto("/");
  await page.waitForFunction(() => window.API && window.API.pa, null, { timeout: 30_000 });
}

test("en död server säger ifrån, och listen går bort när den svarar igen",
  async ({ page }) => {
    await laddad(page);
    await expect(page.locator("#serverborta")).toHaveCount(0);

    /* Härmar en död serverprocess: anropet når aldrig fram, vilket är det enda
       som skiljer den från en server som svarar med ett fel. */
    await page.route("**/api/**", route => route.abort());
    await page.evaluate(() => window.API.json("/api/schema").catch(() => {}));

    await expect(page.locator("#serverborta")).toContainText("SERVERN SVARAR INTE");
    await expect.poll(() => page.evaluate(() => window.API.borta)).toBe(true);
    // API.pa står kvar: faller den börjar appen rita prototypens påhittade
    // data ovanpå lärarens riktiga listor, mitt i passet.
    expect(await page.evaluate(() => window.API.pa)).toBe(true);

    await page.unroute("**/api/**");
    // Hjärtslaget går var tredje sekund när servern är borta.
    await expect(page.locator("#serverborta")).toHaveCount(0, { timeout: 15_000 });
  });

test("en server som startat om ber om en omladdning i stället för att göra den",
  async ({ page }) => {
    await laddad(page);
    await page.route("**/api/**", route => route.abort());
    await page.evaluate(() => window.API.json("/api/schema").catch(() => {}));
    await expect(page.locator("#serverborta")).toContainText("SERVERN SVARAR INTE");

    /* Samma port, ny process. Sidans jobb-id:n och strömmar hör till den gamla
       körningen — den enda ärliga vägen ut är en omladdning, och den är
       lärarens klick: den tar ett halvskrivet papper med sig om den kommer
       oombedd. */
    await page.route("**/api/var-kors", route => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ hus: { lage: "app", namn: "Superappen", port: "18751",
                                    pid: 999999, startad: "10:00", varna: false } }),
    }));

    await expect(page.locator("#serverborta")).toContainText("SERVERN STARTADE OM",
                                                             { timeout: 15_000 });
    await expect(page.locator("#serverborta button")).toHaveText("Ladda om");
    // Sidan står kvar tills hon trycker.
    expect(page.url()).toContain("/");
  });
