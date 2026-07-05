import { test, expect, failOnConsoleError, transcribeSample } from "../helpers/app";

// OBS: "Summera"-knappen togs bort i förenklingen (ff5f3e2) — kvarvarande
// efterbearbetningar i UI:t är Korrekturläs och Chatta.

test("proofreading (cleanup) post-processing streams a result", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await transcribeSample(page);

  await page.getByRole("button", { name: "Korrekturläs transkriptet", exact: true }).click();
  // The cleaned text renders as word-diffed spans inside the preview box.
  await expect(page.getByText("[FEJK cleanup]")).toBeVisible({ timeout: 15000 });
  expect(errors, errors.join("\n")).toEqual([]);
});

test("chat about the transcript answers", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await transcribeSample(page);

  // Chatten är låst tills transkriptet är korrekturläst (designbeteende);
  // därefter bor den inline i Fråga om lektionen-kortet.
  await page.getByRole("button", { name: "Korrekturläs nu", exact: true }).click();
  const chatInput = page.getByPlaceholder("Skriv en fråga …");
  await expect(chatInput).toBeVisible({ timeout: 15000 });
  await chatInput.fill("Vad handlar lektionen om?");
  await chatInput.press("Enter");
  // Fejken svarar med [1]/[2]-markörer i citat-läget: svaret renderas som
  // klickbara källciteringar + källpanel med segmentets tidsstämpel.
  await expect(page.getByText("Lektionen handlar om bråk")).toBeVisible({ timeout: 15000 });
  const cite = page.getByRole("button", { name: "Visa källa 1 i transkriptet" });
  await expect(cite).toBeVisible();
  await expect(page.getByText("Källor i transkriptet")).toBeVisible();
  await cite.click();
  await expect(cite).toHaveAttribute("data-csup", "on");
  expect(errors, errors.join("\n")).toEqual([]);
});

test("lesson insight extraction runs from the lesson overlay", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await transcribeSample(page);

  // Kartotek-omdesignen: Insikter-panelen är borta; Analysera lektion bor i
  // lektionsoverlayens header och matar Kommande/Terminstrender.
  await page.getByRole("button", { name: "Inspelningar", exact: true }).first().click();
  await page.locator('[data-rec-id]').first().click();
  const [resp] = await Promise.all([
    page.waitForResponse((r) => /\/api\/lessons\/\d+\/extract/.test(r.url())),
    page.getByRole("button", { name: /Analysera lektion/ }).click(),
  ]);
  expect(resp.status()).toBe(200);
  await expect(page.getByText("Lektionen analyserad")).toBeVisible({ timeout: 15000 });
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
