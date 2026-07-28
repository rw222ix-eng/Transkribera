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
//
// Plan 4 (parity-uppföljning) lägger till täckning för veckogruppering+antal
// (ArkivList.svelte + week.js) och följdfrågor (ArkivAnswer.svelte +
// actions.js: sendFollow) — se .superpowers/sdd/task-3-brief.md. Testet fyller
// aldrig i "Datum" (BuildPanel.svelte) — plan.datum är '' som default
// (planering/stores.svelte.js) — så godkännandet sparas utan datum och
// week.js: weekInfo() lägger posten i gruppen "Tidigare" (inget
// datumintervall). Enligt testMatch-ordningen i playwright.config.ts körs
// next-foundation.spec.mjs → planering-arkiv.spec.mjs → planering-tavla.spec.mjs,
// och bara next-foundation-specen körs före den här utan att godkänna något
// — så den här tavlan är garanterat den ENDA arkivposten när vecko-/
// totalräkningen kontrolleras, alltså "1 post" på båda ställena.
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

  // Skalet startar på Transkribera-fliken (som gamla appen) — gå till
  // Planering först. Se docs/superpowers/plans/2026-07-25-transkribera-A1-skal-och-kalla.md.
  await page.getByRole("tab", { name: "Planering", exact: true }).click();

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

  // 3b) Veckogruppering (ArkivList.svelte + week.js: groupByWeek/weekInfo).
  // Utan ifyllt datum hamnar posten i gruppen "Tidigare" — labeln har då
  // inget datumintervall (w.range är tomt, se ArkivList.svelte: {#if
  // w.range}), bara en post-räkning i samma "N post"/"N poster"-form som
  // rubrikens totalräkning. Den här tavlan är den enda arkivposten hittills
  // i körningen (se resonemanget om testMatch-ordningen ovan).
  const weekHeader = page.locator(".arkiv .week .whead");
  await expect(weekHeader.locator(".wlabel")).toHaveText("Tidigare");
  await expect(weekHeader.locator(".wrange")).toHaveCount(0);
  await expect(weekHeader.locator(".wcount")).toHaveText("1 post");

  // 3c) Rubrikradens totalräkning (ArkivView.svelte: arkiv.items.length).
  await expect(page.locator(".arkiv .rubrikrad .total")).toHaveText("1 post");

  // 4) Fråga AI (default-läget, se stores.svelte.js: mode: 'ask'). Skanningen
  // (scan_plan/scan_result/deep_read/log/token/done, se serve_test_app.py)
  // är helt deterministisk i fejkläget — svaret beror aldrig på frågans
  // innehåll, bara på att minst en arkivpost matchar frågans innehållsord.
  //
  // KOSTNADSFRI AVGRÄNSNING: getByRole (plan B3a lade ett EGET sökfält med
  // SAMMA aria-label, "Sök i arkivet", i Inspelningar-fliken —
  // Sokfalt.svelte). App.svelte håller alla flikar monterade och göms bara med
  // hidden, så båda fälten ligger i DOM:en samtidigt — men en dold panel är
  // display:none och alltså ute ur tillgänglighetsträdet, och getByRole
  // SJÄLVAVGRÄNSAR mot det, till skillnad från getByLabel. Ett osäkrat
  // page.getByLabel(...) fällde därför "strict mode violation" här oavsett
  // vilken flik som råkade vara synlig; page.getByRole("textbox", …) gör inte
  // det. Samma princip som .grupp-avgränsningen i
  // inspelningar-kartotek.spec.mjs (upptäckt av inspelningar-paneler.spec.mjs,
  // plan B5) löser med en container-klass — getByRole löser den här utan att
  // behöva någon.
  //
  // GER INGET UPP: "Sök i arkivet" är en medvetet DELAD etikett mellan
  // planeringsarkivets frågefält och inspelningsarkivets sökfält (båda söker
  // faktiskt i ett arkiv). Egenskapen en lokator ska bevisa är "bara ETT
  // NÅBART fält bär den här etiketten" — och det bevisar getByRole fortfarande,
  // eftersom rollnamnet självavgränsar mot allt som ligger utanför
  // tillgänglighetsträdet.
  const searchField = page.getByRole("textbox", { name: "Sök i arkivet" });
  await searchField.fill("Arkivprobet");
  await page.getByRole("button", { name: "Fråga", exact: true }).click();
  await expect(page.locator(".svar .fraga")).toHaveText("Arkivprobet");
  await expect(page.locator(".svar .text")).toContainText(
    "Det gick vi igenom på tavlan Brak och andelar.",
    { timeout: 15000 },
  );
  await expect(page.locator(".svar .kallor")).toContainText(TITEL);

  // 4b) Följdfråga (ArkivAnswer.svelte + actions.js: sendFollow) fortsätter
  // samtalet i stället för att söka om — den delar /api/planning/ask med
  // Fråga AI, så fejksvaret (fake_generate i serve_test_app.py) är samma
  // fasta text. Följdfrågefältet dyker upp så fort ett svar finns och
  // strömmen är klar (ArkivAnswer.svelte: {#if arkiv.answer && !arkiv.asking}).
  // Skicka-knappen scopas till .foljdrad — tavelpanelens "Ändra"-chatt
  // (ChangeChat.svelte) har EN EGEN "Skicka"-knapp som ligger kvar synlig på
  // sidan även efter godkännandet (den renderas så länge plan.id finns), så
  // en oscopad getByRole("button", {name: "Skicka"}) skulle vara tvetydig.
  // Följdfrågan måste innehålla ett innehållsord som faktiskt träffar arkivposten
  // (routes_planning.py: _score_archive/content_only via _ask_terms/db.content_terms)
  // — annars svarar servern deterministiskt med sin "0 träffar"-kanoniska text
  // (routes_planning.py: no_hit_job, "... den verkar inte nämna det du frågar
  // om ...") i stället för fake_generate-texten. Samma sökord som Fråga AI-
  // frågan ovan (MOMENT/TITEL) garanterar en träff.
  const followField = page.getByLabel("Ställ en följdfråga");
  await expect(followField).toBeVisible();
  await expect(followField).toHaveAttribute("placeholder", "Ställ en följdfråga …");
  const FOLJDFRAGA = "Kan du säga mer om Arkivprobet?";
  await followField.fill(FOLJDFRAGA);
  await page.locator(".foljdrad").getByRole("button", { name: "Skicka", exact: true }).click();

  // Det andra frågan/svarsparet läggs till EFTER det första, i en egen
  // .foljd-rad — och det FÖRSTA svaret (.svar .text, samma innehåll som
  // ovan) ska fortfarande synas oförändrat, eftersom sendFollow (till
  // skillnad från runAsk/clearSearch) aldrig anropar resetSearch().
  await expect(page.locator(".foljd .fq")).toHaveText(FOLJDFRAGA);
  await expect(page.locator(".foljd .fa")).toContainText(
    "Det gick vi igenom på tavlan Brak och andelar.",
    { timeout: 15000 },
  );
  await expect(page.locator(".svar .fraga")).toHaveText("Arkivprobet");
  await expect(page.locator(".svar .text")).toContainText(
    "Det gick vi igenom på tavlan Brak och andelar.",
  );

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
