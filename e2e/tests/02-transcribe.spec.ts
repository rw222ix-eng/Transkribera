import { test, expect, failOnConsoleError, installFakePywebview, samplePath } from "../helpers/app";

test("transcribe a picked file produces a result and a history entry", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await installFakePywebview(page, samplePath());
  await page.goto("/");

  // Clear any pre-existing queue items (the app currently ships with a demo
  // queue entry; this loop also works once that seed data is removed).
  const removeBtns = page.getByRole("button", { name: "Ta bort från kön" });
  for (let i = await removeBtns.count(); i > 0; i--) {
    await removeBtns.first().click();
  }

  // Pick the sample via the fake pywebview picker (dropzone is data-click=openPicker).
  await page.getByText("klicka för att välja").click();
  await expect(page.getByText("Mamma waw isolerad").first()).toBeVisible({ timeout: 8000 });

  // Wait until the real model catalog has loaded (the "(sv)" label only appears
  // once /api/models resolves) — starting before that sends the stale prototype id.
  await expect(page.getByText("KB-Whisper large (sv)")).toBeVisible({ timeout: 15000 });

  // Start transcription (label varies: "Starta" / "Starta · N filer" / "Kör igen").
  const startBtn = page.getByRole("button", { name: /Starta/ });
  await expect(startBtn).toBeVisible();
  await startBtn.click();

  // Faked SSE finishes fast; the result transcript shows a faked segment.
  await expect(page.getByText("bråk och procent")).toBeVisible({ timeout: 20000 });

  // The merged Inspelningar view shows a new entry for the sample.
  await page.getByRole("button", { name: "Inspelningar", exact: true }).first().click();
  await expect(page.getByText("Mamma waw isolerad").first()).toBeVisible({ timeout: 10000 });

  expect(errors, errors.join("\n")).toEqual([]);
});
