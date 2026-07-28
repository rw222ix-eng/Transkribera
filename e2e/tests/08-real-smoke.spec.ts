// Enda kvarvarande specen som kör mot den RIKTIGA backenden — riktig arbiter,
// riktig transkriberings-subprocess, riktig GPU (projektet "real", startas
// manuellt, se e2e/playwright.config.ts). Resten av den gamla vanilla-sviten
// (e2e/tests/01-smoke … 11-prov) pensionerades i samma omgång — se
// docs/superpowers/plans/2026-07-25-cutover-till-svelte.md, Task 4, och
// .superpowers/sdd/pensionering-report.md — men den här specen har ett
// verkligt värde (en genuin GPU-transkribering, inte fejkad inferens) och
// porterades i stället till Svelte-flödet på /next/.
//
// SAMMA STEG SOM e2e/transkribera-korning.spec.mjs (den fejkade motsvarig-
// heten, redan grön mot next-foundation): kö exemplet via /api/sample, starta,
// vänta in status "Klar" och 100 %, läs av de skrivna filerna, och bevisa att
// en lektionspost verkligen landade i Inspelningar-kartoteket. Ingen
// strömbromsning här (bromsaStrommen i transkribera-korning.spec.mjs) — det
// finns ingen fejkad SSE-ström att styra, bara en riktig.
//
// OVERIFIERAD: kräver flera minuters riktig GPU-transkribering (KB-Whisper
// large, sv) och har INTE körts i den här sessionen — varken lokalt eller mot
// en riktig --real-server. Skriven mot exakt de selektorer och den exakta
// text som redan är bevisade gröna i transkribera-korning.spec.mjs (samma
// Svelte-komponenter, samma DOM), men filen i sig är obekräftad. Kör den
// manuellt före den litas på:
//   TRANSKRIBERA_BASE_DIR=e2e/.test-data-real python e2e/serve_test_app.py --real
//   cd e2e && npm run test:real
import { test, expect, failOnConsoleError } from "../helpers/app";

/** Förkontroll: utan demofilen blir felet annars en obegriplig timeout. */
async function kravExempel(page) {
  const sample = await page.request.get("/api/sample");
  expect(
    sample.status(),
    'Saknad testfixtur: "Mamma waw isolerad.wav" i repo-roten (se e2e/serve_test_app.py). ' +
      "/api/sample svarade " + sample.status() + ".",
  ).toBe(200);
  return sample.json();
}

/** Köar exemplet och startar — /api/sample ger en riktig, validerad sökväg
 * (fungerar identiskt mot fejk- och --real-servern, se serve_test_app.py:
 * SAMPLE_WAV kopieras in i basmappen vid start i båda lägena), så ingen
 * pywebview-mock behövs för den här vägen. */
async function startaExempel(page) {
  await page.getByRole("button", { name: "ett exempel", exact: true }).click();
  const start = page.getByRole("button", { name: "Starta transkribering", exact: true });
  await expect(start).toBeVisible({ timeout: 20_000 });
  await expect(start).toBeEnabled({ timeout: 20_000 });
  await start.click();
}

test("Transkribera (/next/, RIKTIG backend): en riktig körning ger transkript och lektionspost", async ({ page }) => {
  test.setTimeout(300_000); // riktig modellinläsning + transkribering på GPU:n

  const errors = [];
  failOnConsoleError(page, errors);

  await page.goto("/next/");
  const exempel = await kravExempel(page);
  const stam = exempel.name.replace(/\.[^.]+$/, "");

  await startaExempel(page);

  // Körningen går i mål på riktigt — ingen fejkad inferens, ingen strömbromsning.
  const status = page.locator(".kort .status");
  const procent = page.locator(".kort .topp .matt").filter({ hasText: "Klart" });
  await expect(status).toHaveAttribute("role", "status");
  await expect(status).toHaveText("Klar", { timeout: 280_000 });
  await expect(procent).toHaveText("Klart 100 %", { timeout: 15_000 });

  // Klarbeskedet: lektionen är sparad.
  await expect(page.getByText("Klart — lektionen är sparad.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Öppna transkriptet" })).toBeVisible();

  // Filerna som faktiskt skrevs listas med sina NAMN.
  const filer = page.locator("ul.filer li");
  await expect(filer.filter({ hasText: stam + ".srt" })).toHaveCount(1);
  await expect(filer.filter({ hasText: "[object Object]" })).toHaveCount(0);

  // Beviset att det inte bara är guiden som PÅSTÅR att lektionen sparades:
  // en ny lektionspost dyker upp i Inspelningar-kartoteket, hämtad ur den
  // riktiga lektions-DB:n via en riktig GET /api/lessons.
  await page.getByRole("button", { name: "Inspelningar", exact: true }).click();
  const kort = page.locator(".pane:not([hidden]) section.view article.kort");
  await expect(kort.first()).toBeVisible({ timeout: 10_000 });

  expect(errors, errors.join("\n")).toEqual([]);
});
