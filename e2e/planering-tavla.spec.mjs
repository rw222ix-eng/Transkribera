// Task 8: e2e för tavelflödet i den nya Svelte-frontenden (/next/).
// Bevisar hela vägen skriv → förhandsvisning → ändra-raden → godkänn & spara
// mot den riktiga backenden (fejkad LLM/GPU, se e2e/serve_test_app.py) — inte
// bara att grunden monteras (det gör next-foundation.spec.mjs). Se
// .superpowers/sdd/task-8-brief.md. Fixtures/mönster återanvända från
// e2e/tests/10-tavla.spec.ts (frameLocator på tavel-iframen) och
// e2e/next-foundation.spec.mjs (failOnConsoleError, "/next/").
import { test, expect, failOnConsoleError } from "./helpers/app";

test("Planering (/next/): skriv tavlan, förhandsvisa, ändra-raden, godkänn & spara", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.goto("/next/");

  // 1) Masthead: mono-eyebrowen + rubriken (serif-kursiverade "tavla" ingår i
  // den tillgängliga rubriktexten "Dagens tavla").
  await expect(page.getByText("PLANERING", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: /tavla/i })).toBeVisible();

  // 2) CTA:n är avstängd tills ett moment är ifyllt.
  const moment = page.getByLabel("Moment");
  const cta = page.getByRole("button", { name: "Skriv tavlan" });
  await expect(cta).toBeDisabled();
  await moment.fill("Andragradsfunktioner — minimipunkt");
  await expect(cta).toBeEnabled();

  // 3) Klick startar SSE-jobbet: en loggrad dyker upp, och tavel-iframen visar
  // riktigt renderat innehåll (fejk-tavlan är FEW_SHOTS[1] ur lesson_board.py).
  await cta.click();
  await expect(page.getByText(/Genererar lektionstavlan/)).toBeVisible({ timeout: 15000 });

  const boardFrameEl = page.locator('iframe[title^="Lektionstavla"]');
  await expect(boardFrameEl).toBeVisible({ timeout: 15000 });
  const boardFrame = page.frameLocator('iframe[title^="Lektionstavla"]');
  await expect(boardFrame.getByText("Symmetrilinjen:")).toBeVisible({ timeout: 15000 });

  // 4) Ändra-raden (chatten) visas nu när tavlan (plan.id) finns.
  await expect(page.getByText("Ändra", { exact: true })).toBeVisible();
  const changeField = page.getByLabel("Ändra tavlan");
  await expect(changeField).toBeVisible();

  // 4b) refineBoard(): skicka en ändring och vänta på att tavlans titel får
  // ändrings-suffixet. fake_refine_board (e2e/serve_test_app.py) lägger
  // deterministiskt till " (ändrad)" på titeln — asserten speglar exakt det.
  await changeField.fill("Lägg till ett exempel med bråk");
  await page.getByRole("button", { name: "Skicka" }).click();
  await expect(page.getByText(/Uppdaterar tavlan/)).toBeVisible({ timeout: 15000 });
  await expect(page.locator("figure.preview .title")).toHaveText(
    "Andragradsfunktioner — minimipunkt (ändrad)",
    { timeout: 15000 },
  );

  // 5) Godkänn och spara ger ett Sparad-kvitto.
  const approve = page.getByRole("button", { name: "Godkänn och spara" });
  await expect(approve).toBeEnabled({ timeout: 15000 });
  await approve.click();
  await expect(page.getByText(/Sparad:/)).toBeVisible({ timeout: 15000 });

  // 6) Inga konsolfel under hela flödet.
  expect(errors, errors.join("\n")).toEqual([]);
});
