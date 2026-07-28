// Paritetslucka 2: säkerhetskopieringsknappen i Inspelningar-vyn
// (InspelningarView.svelte), portad från gamla appens backupNow
// (app.js:2059-2066, knappen app.js:4886). Se saveBackup i
// frontend/src/lib/inspelningar/actions.js.
//
// POST /api/backup är en riktig, ofarlig endpoint (zippar
// transkribera.db + history.json + settings.json under base/exports/ — rör
// aldrig Transkriberingar/ eller någon lektionsrad) och körs i det FÖRSTA
// testet mot den RIKTIGA backenden, precis som inspelningar-kartotek.spec.mjs
// gör för sina POST/PATCH/DELETE.
//
// POST /api/reveal öppnar däremot lärarens Utforskare (os.startfile,
// server.py) och MÅSTE stubbas — annars öppnar testet ett riktigt
// Utforskarfönster mitt i körningen. Samma mönster som stubbaOpen i
// inspelningar-paneler.spec.mjs (för POST /api/open, samma _open_path).
//
// TÄCKER: att knappen POSTar /api/backup och kvitterar antalet filer på vyns
// DELADE statusrad (insp.fel/data-testid="insp-statusrad"), och att ett
// serverfel SYNS där i stället för att sväljas tyst.
// TÄCKER INTE: zip-filens innehåll (äger av tests/test_backup.py) eller att
// /api/reveal verkligen öppnar ett fönster (tests/test_open_endpoints.py).
import { test, expect, failOnConsoleError } from "./helpers/app";

/** Stubbar POST /api/reveal — se filhuvudets kommentar. */
async function stubbaReveal(page) {
  await page.route("**/api/reveal", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" }),
  );
}

/** Öppnar Inspelningar-fliken. Hämtningarna är grindade på nav.tab
 *  (InspelningarView.svelte), inte på montering — ett flikbyte krävs. */
async function oppnaInspelningar(page) {
  await page.goto("/next/");
  await page.getByRole("tab", { name: "Inspelningar", exact: true }).click();
  const vy = page.locator(".pane:not([hidden]) section.view");
  await expect(vy).toBeVisible();
  return vy;
}

test("Inspelningar (/next/): Säkerhetskopiera POSTar /api/backup och kvitterar antalet filer", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);
  await stubbaReveal(page);

  const vy = await oppnaInspelningar(page);
  const knapp = vy.getByRole("button", { name: "Säkerhetskopiera", exact: true });
  await expect(knapp).toBeVisible();
  await expect(knapp).toBeEnabled();

  const backupSvar = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/backup" && r.request().method() === "POST",
  );
  await knapp.click();
  const svar = await backupSvar;
  expect(svar.ok(), "POST /api/backup svarade " + svar.status()).toBeTruthy();
  const kropp = await svar.json();
  expect(Array.isArray(kropp.files), "Servern angav inte files[] i svaret").toBeTruthy();
  expect(kropp.files.length, "Backupen innehöll inga filer — transkribera.db saknas?").toBeGreaterThan(0);

  // Kvittot — INGEN toast, vyns delade statusrad (samma nod som redigeringens
  // och raderingens fel, se inspelningar-kartotek.spec.mjs). Talet böjs.
  const vantatKvitto = kropp.files.length === 1
    ? "Säkerhetskopia skapad — 1 fil."
    : `Säkerhetskopia skapad — ${kropp.files.length} filer.`;
  const statusrad = vy.locator('[data-testid="insp-statusrad"]');
  await expect(statusrad).toHaveText(vantatKvitto);
  await expect(vy.getByRole("status")).toHaveText(vantatKvitto);

  // Dubbelklickvakten släpper igen efteråt — knappen är inte permanent låst.
  await expect(knapp).toBeEnabled();
  await expect(knapp).toHaveText("Säkerhetskopiera");

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Inspelningar (/next/): ett backup-fel syns på statusraden", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  const SERVERTEXT = "diskfullt";
  await page.route("**/api/backup", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: SERVERTEXT }),
    }),
  );

  const vy = await oppnaInspelningar(page);
  const knapp = vy.getByRole("button", { name: "Säkerhetskopiera", exact: true });
  await knapp.click();

  // SERVERNS text, inte en generisk reservtext — precis som raderingens 409
  // i inspelningar-kartotek.spec.mjs.
  const statusrad = vy.locator('[data-testid="insp-statusrad"]');
  await expect(statusrad).toHaveText("Kunde inte skapa säkerhetskopian: " + SERVERTEXT);
  await expect(knapp).toBeEnabled();

  await page.unroute("**/api/backup");

  // Chromes egen "Failed to load resource … 500" är testets EGEN injektion,
  // inte ett appfel — samma filter som inspelningar-kartotek.spec.mjs
  // (appfel) använder för sin 409:a.
  const appfel = errors.filter((e) => !/Failed to load resource/.test(e));
  expect(appfel, appfel.join("\n")).toEqual([]);
});
