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

  // Chatten är låst tills transkriptet är korrekturläst (designbeteende).
  await page.getByRole("button", { name: "Korrekturläs nu", exact: true }).click();
  await page.getByRole("button", { name: "Öppna chatt", exact: true }).click({ timeout: 15000 });
  const chatInput = page.getByPlaceholder("Fråga om transkriptet …");
  await chatInput.fill("Vad handlar lektionen om?");
  await chatInput.press("Enter");
  await expect(page.getByText("[FEJK chatt]")).toBeVisible({ timeout: 15000 });
  expect(errors, errors.join("\n")).toEqual([]);
});

test("lesson insight extraction shows the extracted action", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await transcribeSample(page);

  await page.getByRole("button", { name: "Lektioner", exact: true }).first().click();
  await page.getByRole("button", { name: "Insikter" }).first().click();
  await page.getByRole("button", { name: /Analysera lektion/ }).click();
  await expect(page.getByText("Räkna uppgift 5 till nästa gång.")).toBeVisible({ timeout: 15000 });
  expect(errors, errors.join("\n")).toEqual([]);
});

test("cross-lesson AI question answers over the transcripts", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await transcribeSample(page);

  await page.getByRole("button", { name: "Lektioner", exact: true }).first().click();
  await page.getByRole("button", { name: "Fråga (AI)" }).first().click();
  // In AI mode the input placeholder and submit button both change; wait for the
  // re-render to settle and the typed value to commit before submitting.
  const askInput = page.getByPlaceholder("Ställ en fråga, t.ex. När hade vi prov om derivata?");
  await expect(askInput).toBeVisible();
  await askInput.fill("bråk");
  await expect(askInput).toHaveValue("bråk");
  await page.getByRole("button", { name: "Fråga", exact: true }).click();
  await expect(page.getByText("[FEJK svar]")).toBeVisible({ timeout: 15000 });
  expect(errors, errors.join("\n")).toEqual([]);
});
