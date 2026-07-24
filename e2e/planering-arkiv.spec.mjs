// Task 4 (Plan 3): e2e för planeringsarkivet i den nya Svelte-frontenden
// (/next/) — bevisar att en godkänd tavla dyker upp i arkivlistan direkt,
// utan reload (approveBoard() anropar loadArkiv(), se planering/actions.js),
// att ordsökningen ("Sök ord") ger träff utan att läcka de råa
// \x02/\x03-styrtecknen ur snippet-kontraktet (Snippet.svelte splittrar på
// dem och slår in träffen i <mark>), att Rensa återställer hela listan, och
// — deterministiskt i fejkläget, se e2e/serve_test_app.py där
// llm_client.generate = fake_generate strömmar ett fast svar ordvis oavsett
// fråga — att "Fråga AI"-flödet visar frågan, svaret och källraden. Se
// .superpowers/sdd/task-4-brief.md.
//
// Generera+godkänn-flödet (Moment/"Skriv tavlan"/tavel-iframen/"Godkänn och
// spara") är hämtat rakt av från e2e/planering-tavla.spec.mjs; failOnConsoleError
// och "/next/"-navigeringen är samma mönster som e2e/next-foundation.spec.mjs.
//
// Ett unikt, påhittat moment-ord används som tavelns titel och sökord, så
// sök-/frågeträffen entydigt pekar på just den här tavlan oavsett vilka andra
// planeringar som redan ligger i arkivet från tidigare specs i samma körning
// (samma delade fejkserver, workers: 1 — se playwright.config.ts).
import { test, expect, failOnConsoleError } from "./helpers/app";

const MOMENT = "Arkivprobet — unikt sökord för e2e";
// fake_generate_board (e2e/serve_test_app.py) sätter board.title = moment
// rakt av, och /approve sparar titel = board.title — så arkivets rad heter
// exakt detta.
const TITEL = MOMENT;

test("Planeringsarkiv (/next/): lista, ordsök utan styrtecken, Rensa och Fråga AI", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.goto("/next/");

  // 1) ARKIV-sektionen renderar (mono-eyebrow + rubrik) — ArkivView.svelte.
  await expect(page.getByText("ARKIV", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sparade tavlor och prov" })).toBeVisible();

  // 2) Skriv och godkänn en tavla (samma selektorer som planering-tavla.spec.mjs).
  await page.getByLabel("Moment").fill(MOMENT);
  const cta = page.getByRole("button", { name: "Skriv tavlan" });
  await expect(cta).toBeEnabled();
  await cta.click();
  const boardFrame = page.frameLocator('iframe[title^="Lektionstavla"]');
  await expect(boardFrame.getByText("Symmetrilinjen:")).toBeVisible({ timeout: 15000 });
  const approve = page.getByRole("button", { name: "Godkänn och spara" });
  await expect(approve).toBeEnabled({ timeout: 15000 });
  await approve.click();
  await expect(page.getByText(/Sparad:/)).toBeVisible({ timeout: 15000 });

  // 3) approveBoard() (planering/actions.js) anropar loadArkiv() efter ett
  // lyckat spara (samma "planeringen syns direkt i arkivet" som den gamla
  // appen, app.js:970) — den nyss godkända tavlan ska synas direkt, utan
  // reload.
  const row = page.locator(".arkiv .row", { hasText: TITEL });
  await expect(row).toBeVisible({ timeout: 10000 });
  const totalBefore = await page.locator(".arkiv .row").count();

  // 4) Fråga AI (default-läget, se stores.svelte.js: mode: 'ask'). Skanningen
  // (scan_plan/scan_result/deep_read/log/token/done, se serve_test_app.py)
  // är helt deterministisk i fejkläget — svaret beror aldrig på frågans
  // innehåll, bara på att minst en arkivpost matchar frågans innehållsord.
  const searchField = page.getByLabel("Sök i arkivet");
  await searchField.fill("Arkivprobet");
  await page.getByRole("button", { name: "Fråga", exact: true }).click();
  await expect(page.locator(".svar .fraga")).toHaveText("Arkivprobet");
  await expect(page.locator(".svar .text")).toContainText(
    "Det gick vi igenom på tavlan Brak och andelar.",
    { timeout: 15000 },
  );
  await expect(page.locator(".svar .kallor")).toContainText(TITEL);

  // 5) Sök ord: samma sökfält (query-state delas mellan lägena), men
  // ordsökning i stället för AI-svar. Oavsett vad servern faktiskt lägger i
  // snippet-fältet (se rapporten för vad /api/planning/archive/search
  // verkligen svarar) ska sidans synliga text ALDRIG innehålla de råa
  // \x02/\x03-styrtecknen — det är kontraktet Snippet.svelte bygger på.
  await page.getByRole("button", { name: "Sök ord", exact: true }).click();
  await page.getByRole("button", { name: "Sök", exact: true }).click();
  await expect(row).toBeVisible({ timeout: 10000 });

  const bodyText = await page.evaluate(() => document.body.innerText);
  expect(bodyText).not.toContain(String.fromCharCode(0x02));
  expect(bodyText).not.toContain(String.fromCharCode(0x03));

  // 6) Rensa återställer hela listan (och döljer sig själv igen).
  const rensa = page.getByRole("button", { name: "Rensa", exact: true });
  await expect(rensa).toBeVisible();
  await rensa.click();
  await expect(page.locator(".arkiv .row")).toHaveCount(totalBefore);
  await expect(rensa).toBeHidden();

  // 7) Inga konsolfel under hela flödet.
  expect(errors, errors.join("\n")).toEqual([]);
});
