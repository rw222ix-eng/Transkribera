import { test, expect, failOnConsoleError, transcribeSample } from "../helpers/app";

test("summary post-processing streams a result", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await transcribeSample(page);

  await page.getByRole("button", { name: "Summera", exact: true }).click();
  await expect(page.getByText("[FEJK summary]")).toBeVisible({ timeout: 15000 });
  expect(errors, errors.join("\n")).toEqual([]);
});

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

test("lesson insight extraction shows the extracted action", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await transcribeSample(page);

  await page.getByRole("button", { name: "Inspelningar", exact: true }).first().click();
  await page.getByRole("button", { name: "Insikter" }).first().click();
  await page.getByRole("button", { name: /Analysera lektion/ }).click();
  await expect(page.getByText("Räkna uppgift 5 till nästa gång.")).toBeVisible({ timeout: 15000 });
  expect(errors, errors.join("\n")).toEqual([]);
});

test("cross-lesson AI question answers over the transcripts", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await transcribeSample(page);

  await page.getByRole("button", { name: "Inspelningar", exact: true }).first().click();
  await page.getByRole("button", { name: "Fråga (AI)" }).first().click();
  // In AI mode the input placeholder and submit button both change; wait for the
  // re-render to settle and the typed value to commit before submitting.
  const askInput = page.getByPlaceholder("Ställ en fråga, t.ex. När hade vi prov om derivata?");
  await expect(askInput).toBeVisible();
  await askInput.fill("bråk");
  await expect(askInput).toHaveValue("bråk");
  await page.getByRole("button", { name: "Fråga", exact: true }).click();
  await expect(page.getByText("[FEJK svar]")).toBeVisible({ timeout: 15000 });
  // Tänker-bannern landar i klart-läget och scen-koreografin lyfter de
  // lektionskort som svaret faktiskt bygger på (källorna från RAG-svaret).
  await expect(page.getByText("Svar klart")).toBeVisible({ timeout: 10000 });
  await expect(page.locator('[data-stage="lift"]').first()).toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
});
