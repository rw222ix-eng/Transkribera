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
//
// Paritetslucka 3 (PNG-exporten): lade till "Spara som PNG" i
// BoardPreview.svelte, portad från gamla appens wbExportPng (app.js:819-868).
// De två testerna nedan täcker GRINDNINGEN (knappen är gömd innan en tavla är
// ritad, precis som Skriv ut/Förstora ovan — figure.idle döljer hela
// verktygsraden) och SERVERFALLBACKEN (POST /api/planning/export) — INTE
// File System Access-vägen: window.showSaveFilePicker öppnar en äkta OS-
// dialog som Playwright inte kan styra, så den stängs av deterministiskt med
// `delete window.showSaveFilePicker` innan navigeringen, exakt som gamla
// appens egen kod faller tillbaka på servern när API:n saknas
// (app.js:825/849-850). Det andra testet bevisar att ett exportfel SYNS
// (kravet "Ingen tom .catch") genom att fejka ett 500-svar från endpointen.
import { test, expect, failOnConsoleError } from "./helpers/app";

/** Skriver en tavla, precis som steg 1-3 i huvudtestet ovan, men utan
 *  ändra-raden och godkännandet — de behövs inte för exporttesterna. */
async function skrivTavla(page) {
  await page.goto("/next/");
  await page.getByRole("tab", { name: "Planering", exact: true }).click();
  await page.getByLabel("Moment").fill("Andragradsfunktioner — minimipunkt");
  await page.getByRole("button", { name: "Skriv tavlan" }).click();
  const boardFrame = page.frameLocator('iframe[title^="Lektionstavla"]');
  await expect(boardFrame.getByText("Symmetrilinjen:")).toBeVisible({ timeout: 15000 });
}

test("Planering (/next/): Spara som PNG är grindad och sparar via serverfallbacken", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Tvingar fram serverfallbacken deterministiskt — se filhuvudets kommentar.
  await page.addInitScript(() => { delete window.showSaveFilePicker; });

  await page.goto("/next/");
  await page.getByRole("tab", { name: "Planering", exact: true }).click();

  // GRINDAD: ingen tavla ritad än. Knappen finns i DOM:en (figuren är alltid
  // monterad, se BoardPreview.svelte) men figure.idle gömmer hela
  // verktygsraden — samma mönster Skriv ut/Förstora redan lever under.
  const exportBtn = page.getByRole("button", { name: "Spara som PNG" });
  await expect(exportBtn).toBeHidden();

  await page.getByLabel("Moment").fill("Andragradsfunktioner — minimipunkt");
  await page.getByRole("button", { name: "Skriv tavlan" }).click();
  const boardFrame = page.frameLocator('iframe[title^="Lektionstavla"]');
  await expect(boardFrame.getByText("Symmetrilinjen:")).toBeVisible({ timeout: 15000 });

  // Tavlan finns — knappen är nu aktiv, precis som sina syskon.
  await expect(exportBtn).toBeVisible();
  await expect(exportBtn).toBeEnabled();

  const exportSvar = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/planning/export" && r.request().method() === "POST",
  );
  await exportBtn.click();
  const svar = await exportSvar;
  expect(svar.ok(), "POST /api/planning/export svarade " + svar.status()).toBeTruthy();
  const kropp = await svar.json();
  expect(kropp.path, "Servern angav ingen sparad sökväg").toBeTruthy();

  // Kvittot syns i den permanenta live-regionens SYNLIGA kopia (p.exportmsg).
  // Avgränsat dit och inte getByText: den klippta live-regionen (p.exportmsg-sr,
  // role="status") bär SAMMA text och ger annars strict mode violation — precis
  // det mönster InspelningarView.svelte:229/687-702 redan är avgränsat mot.
  await expect(page.locator("p.exportmsg")).toHaveText(/^PNG sparad: /, { timeout: 10000 });

  // MOTORNS EGEN, FÖRUTVARANDE brus: WBHost.exportPng (board.js, inlineUrls)
  // hämtar VARJE url() i KaTeX-typsnittens @font-face-regler för att bädda in
  // dem i export-SVG:n — även .woff/.ttf-fallbackerna, trots att vendor-
  // katalogen bara skeppar .woff2 (app/web/static/vendor/katex/fonts/, 20
  // filer, uppmätt). Webbläsaren hittar ändå .woff2-källan i samma
  // @font-face-regel och exporten blir korrekt — bruset är kosmetiskt och
  // förekommer lika mycket i produktion. Motorn ligger under app/ och är
  // uttryckligen "given" (specen: "Motorn kan det"), så det är test-filtret
  // som ska anpassas, inte motorn. Samma appfel-mönster som
  // inspelningar-kartotek.spec.mjs använder för sin egen 409:a.
  const appfel = errors.filter((e) => !/Failed to load resource/.test(e));
  expect(appfel, appfel.join("\n")).toEqual([]);
});

test("Planering (/next/): ett exportfel syns i vyn", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.addInitScript(() => { delete window.showSaveFilePicker; });
  await skrivTavla(page);

  await page.route("**/api/planning/export", (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "diskfel" }) }),
  );

  await page.getByRole("button", { name: "Spara som PNG" }).click();

  // Felet SYNS — ingen tom .catch. Serverns egen text ("diskfel") ska med,
  // inte bara en generisk reservtext. Avgränsat till den synliga kopian
  // (p.exportmsg) — se motiveringen i föregående test.
  await expect(page.locator("p.exportmsg")).toHaveText("Kunde inte spara PNG: diskfel", { timeout: 10000 });
  await expect(page.locator("p.exportmsg")).toHaveClass(/fel/);

  await page.unroute("**/api/planning/export");

  // Chromes egen "Failed to load resource … 500" är testets EGEN injektion,
  // inte ett appfel — samma filter som inspelningar-kartotek.spec.mjs
  // (appfel) använder för sin 409:a.
  const appfel = errors.filter((e) => !/Failed to load resource/.test(e));
  expect(appfel, appfel.join("\n")).toEqual([]);
});

test("Planering (/next/): skriv tavlan, förhandsvisa, ändra-raden, godkänn & spara", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.goto("/next/");

  // Skalet startar på Transkribera-fliken (som gamla appen) — gå till
  // Planering först. Se docs/superpowers/plans/2026-07-25-transkribera-A1-skal-och-kalla.md.
  await page.getByRole("tab", { name: "Planering", exact: true }).click();

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
