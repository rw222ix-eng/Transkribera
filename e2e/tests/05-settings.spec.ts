import { test, expect, failOnConsoleError } from "../helpers/app";

test("models view shows installed + downloadable models and the disk picker", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await page.goto("/");
  await page.getByRole("button", { name: "Modeller", exact: true }).first().click();

  await expect(page.getByRole("heading", { name: "Transkriberingsmodeller" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Språk- och videomodeller" })).toBeVisible();

  // KB-Whisper large + others are installed; uninstalled ones offer a download.
  await expect(page.getByText("✓ Installerad").first()).toBeVisible();
  expect(await page.getByText("✓ Installerad").count()).toBeGreaterThanOrEqual(2);
  expect(await page.getByText("Ladda ner").count()).toBeGreaterThanOrEqual(1);

  // Models-disk picker (shows free space).
  await expect(page.getByText(/ledigt/).first()).toBeVisible();

  expect(errors, errors.join("\n")).toEqual([]);
});

test("model use-case filter chips switch the list without errors", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await page.goto("/");
  await page.getByRole("button", { name: "Modeller", exact: true }).first().click();

  await page.getByRole("button", { name: "Svensk text", exact: true }).click();
  await page.getByRole("button", { name: "Videoanalys · bild", exact: true }).click();
  await page.getByRole("button", { name: "Alla", exact: true }).first().click();

  // Still rendering the catalog after filtering.
  await expect(page.getByRole("heading", { name: "Språk- och videomodeller" })).toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
});
