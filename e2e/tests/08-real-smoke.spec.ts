import { test, expect } from "@playwright/test";
import * as path from "path";

// The --real launcher copies the sample into <base>/downloads and runs the REAL
// arbiter + transcription subprocess (genuine KB-Whisper on the GPU).
const sampleReal = path.join(__dirname, "..", ".test-data-real", "downloads", "Mamma waw isolerad.wav");

test("real transcription of the sample produces a transcript and history entry", async ({ page }) => {
  test.setTimeout(300_000); // real model load + transcription on the GPU

  await page.addInitScript((p) => {
    (window as any).pywebview = {
      api: {
        pick_files: async () => [{ path: p, name: p.split(/[\\/]/).pop() }],
        save_file: async () => true,
        reveal: async () => true,
      },
    };
  }, sampleReal);

  await page.goto("/");
  const removeBtns = page.getByRole("button", { name: "Ta bort från kön" });
  for (let i = await removeBtns.count(); i > 0; i--) {
    await removeBtns.first().click();
  }
  await page.getByText("klicka för att välja").click();
  await expect(page.getByText("Mamma waw isolerad").first()).toBeVisible({ timeout: 8000 });
  await expect(page.getByText("KB-Whisper large (sv)")).toBeVisible({ timeout: 20000 });
  await page.getByRole("button", { name: /Starta/ }).click();

  // Wait for the real run to finish: the post-process panel only appears once a
  // transcript exists.
  await expect(page.getByRole("heading", { name: "Korrekturläs transkriptet" }))
    .toBeVisible({ timeout: 280_000 });

  // A new history entry was persisted for the sample.
  await page.getByRole("button", { name: "Inspelningar", exact: true }).first().click();
  await expect(page.getByText("Mamma waw isolerad").first()).toBeVisible({ timeout: 10000 });
});
