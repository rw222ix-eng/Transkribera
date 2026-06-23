import { test, expect, failOnConsoleError } from "../helpers/app";

// Chromium runs with --use-fake-device-for-media-stream (see playwright.config),
// so getUserMedia + MediaRecorder work headless without a real microphone.
test("record a lesson and add it to the transcription queue", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await page.goto("/");

  // Clear the queue to reveal the source step (which holds the record control).
  const removeBtns = page.getByRole("button", { name: "Ta bort från kön" });
  for (let i = await removeBtns.count(); i > 0; i--) {
    await removeBtns.first().click();
  }

  await page.getByRole("button", { name: "Starta inspelning" }).click();
  // Let MediaRecorder collect and flush a chunk or two.
  await page.waitForTimeout(1800);
  await page.getByRole("button", { name: /Stoppa/ }).click();

  // The finished recording is added to the queue as lektion_<timestamp>.<ext>.
  await expect(page.getByText(/lektion_/)).toBeVisible({ timeout: 12000 });
  expect(errors, errors.join("\n")).toEqual([]);
});
