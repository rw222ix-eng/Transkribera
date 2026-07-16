import { test, expect, failOnConsoleError, transcribeSample } from "../helpers/app";

// OBS (design 14 juli): wizardens KORREKTUR-kort och Qwen-språkstäd är borta —
// korrekturen (Gemma 3n mot ljudet) körs i serverns transkriberingspipeline.

test("wizard fire-and-forget: öppnar Inspelningar och nollställs", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await transcribeSample(page);   // slutar på Inspelningar

  // Wizarden har nollställts — tillbaka på steg 1 (Källa) med tom kö.
  await page.getByRole("button", { name: "Transkribera", exact: true }).first().click();
  await expect(page.getByText("klicka för att välja")).toBeVisible({ timeout: 8000 });
  expect(await page.getByRole("button", { name: "Ta bort från kön" }).count()).toBe(0);
  expect(errors, errors.join("\n")).toEqual([]);
});

test("chat about the transcript happens under Inspelningar", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await transcribeSample(page);

  // Chatten bor i lektionsoverlayns sidopanel — öppna kortet under Inspelningar.
  await page.locator('[data-rec-id]').first().click();
  const chatInput = page.getByPlaceholder("Skriv en fråga …");
  await expect(chatInput).toBeVisible({ timeout: 15000 });
  await chatInput.fill("Vad handlar lektionen om?");
  await chatInput.press("Enter");
  // Fejken svarar med [1]/[2]-markörer i citat-läget: svaret renderas som
  // klickbara källciteringar i lektionschatten.
  await expect(page.getByText("Lektionen handlar om bråk")).toBeVisible({ timeout: 15000 });
  const cite = page.getByRole("button", { name: "Visa källa 1 i transkriptet" });
  await expect(cite).toBeVisible();
  // Källrads-chipsen under svaret togs bort 2026-07-15 — de numrerade
  // citatknapparna i texten är den enda (och tillräckliga) källingången.
  await cite.click();
  await expect(cite).toHaveAttribute("data-csup", "on");
  // Design 14 juli: källan scrollar transkriptet till träffraden (data-ovhit).
  await expect(page.locator("[data-ovhit]")).toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
});

test("lesson insights are extracted automatically after transcription", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);

  // Analysera lektion-knappen är borttagen: extraktionen körs som tyst
  // bakgrundsprocess när hela kön är klar (finishTranscribe → autoExtractLessons)
  // och matar Kommande/Inför nästa lektion/Terminstrender utan användaråtgärd.
  const [resp] = await Promise.all([
    page.waitForResponse((r) => /\/api\/lessons\/\d+\/extract/.test(r.url()), { timeout: 60000 }),
    transcribeSample(page),
  ]);
  expect(resp.status()).toBe(200);
  expect(errors, errors.join("\n")).toEqual([]);
});

test("cross-lesson AI question answers over the transcripts", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await transcribeSample(page);

  await page.getByRole("button", { name: "Inspelningar", exact: true }).first().click();
  await page.getByRole("button", { name: "Fråga AI", exact: true }).first().click();
  // In AI mode the input placeholder and submit button both change; wait for the
  // re-render to settle and the typed value to commit before submitting.
  const askInput = page.getByPlaceholder("Ställ en fråga, t.ex. när hade vi prov om derivata?");
  await expect(askInput).toBeVisible();
  await askInput.fill("bråk");
  await expect(askInput).toHaveValue("bråk");
  // När fältet fått text blir ✕ Rensa synlig (data-vis) — invänta den så att
  // klicket inte landar på gamla koordinater.
  await expect(page.getByRole("button", { name: "Rensa" })).toBeVisible();
  await page.getByRole("button", { name: "Fråga", exact: true }).click();
  // Svaret streamas inline i svarskortet under skannings-rutnätet.
  await expect(page.getByText("[FEJK svar]")).toBeVisible({ timeout: 15000 });
  // Skanningen landar i klart-läget och kartotek-koreografin lyfter de
  // lektionskort som svaret faktiskt bygger på (källorna från RAG-svaret).
  await expect(page.getByText(/Genomsökte \d+ inspelningar/)).toBeVisible({ timeout: 10000 });
  await expect(page.locator('[data-stage="lift"]').first()).toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
});
