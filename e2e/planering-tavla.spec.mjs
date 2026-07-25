// Task 8: e2e för tavelflödet i den nya Svelte-frontenden (/next/).
// Bevisar hela vägen skriv → förhandsvisning → ändra-raden → godkänn & spara
// mot den riktiga backenden (fejkad LLM/GPU, se e2e/serve_test_app.py) — inte
// bara att grunden monteras (det gör next-foundation.spec.mjs). Se
// .superpowers/sdd/task-8-brief.md. Fixtures/mönster återanvända från
// e2e/tests/10-tavla.spec.ts (frameLocator på tavel-iframen) och
// e2e/next-foundation.spec.mjs (failOnConsoleError, "/next/").
//
// Task 4 (parity): Skriv ut/Förstora/live-uppbyggnad lades till i
// BoardPreview.svelte och PlaneringView.svelte utan egen e2e-täckning — se
// .superpowers/sdd/task-4-brief.md. fake_generate_board/fake_refine_board
// (e2e/serve_test_app.py) strömmar numera tavlans JSON via token_cb (med en
// kort paus per bit) i stället för att svälja den, så live-räknaren blir
// observerbar utan att göra testet flaky.
import { test, expect, failOnConsoleError } from "./helpers/app";

test("Planering (/next/): skriv tavlan, förhandsvisa, ändra-raden, godkänn & spara", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.goto("/next/");

  // Skalet startar på Transkribera-fliken (som gamla appen) — gå till
  // Planering först. Se docs/superpowers/plans/2026-07-25-transkribera-A1-skal-och-kalla.md.
  await page.getByRole("button", { name: "Planering", exact: true }).click();

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

  // OBS: live-räknaren ("Ritar live — …", se punkt 4c nedan) kan INTE synas
  // under just den här första körningen — BoardPreview.svelte monterar
  // iframen först när plan.board eller plan.liveSections är satt, och
  // liveTick() kräver att iframens contentWindow.WBHost redan finns. Vid
  // allra första genereringen finns varken det ena eller det andra ännu, så
  // liveTick() nollar sig självt tyst. Från och med nästa körning (refine
  // nedan) finns iframen redan kvar (plan.board nollas inte av resetRun()),
  // så då kan den verkligen ritas live — se 4c.
  const boardFrameEl = page.locator('iframe[title^="Lektionstavla"]');
  await expect(boardFrameEl).toBeVisible({ timeout: 15000 });
  const boardFrame = page.frameLocator('iframe[title^="Lektionstavla"]');
  await expect(boardFrame.getByText("Symmetrilinjen:")).toBeVisible({ timeout: 15000 });

  // 3b) Skriv ut och Förstora syns så snart tavlan finns (BoardPreview.svelte).
  await expect(page.getByRole("button", { name: "Skriv ut" })).toBeVisible();
  const zoomBtn = page.getByRole("button", { name: "Förstora" });
  await expect(zoomBtn).toBeVisible();

  // 3c) Förstora byter etikett till Stäng UTAN att flytta iframen i DOM:en
  // (CSS position: fixed på figure.preview.zoomed, inte ommontering av
  // elementet) — annars laddas tavelmotorns dokument om och tavlan töms.
  // Kontrollera därför att iframens innehåll fortfarande syns efter
  // växlingen: det är regressionsvakten mot just den ommonteringsbuggen.
  await zoomBtn.click();
  await expect(page.getByRole("button", { name: "Stäng" })).toBeVisible();
  await expect(boardFrame.getByText("Symmetrilinjen:")).toBeVisible();

  // 3d) Escape stänger förstoringen igen och återställer etiketten.
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Förstora" })).toBeVisible();

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

  // 4c) Live-uppbyggnad: den gamla tavlan är redan monterad i iframen (se
  // OBS ovan), så nu strömmar fake_refine_board (e2e/serve_test_app.py)
  // den uppdaterade JSON:en i bitar via token_cb och live-räknaren i
  // PlaneringView ("Ritar live — N sektion(er) hittills …") hinner synas
  // medan fasen fortfarande är "running" — innan done-eventet växlar
  // tillbaka till den färdiga (ändrade) tavlan.
  await expect(page.getByText(/Ritar live —/)).toBeVisible({ timeout: 5000 });

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
