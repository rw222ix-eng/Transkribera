// Playwright-smoke för den parallella Svelte+Vite-frontenden under /next.
// Bevisar bara att grunden (Task 1-5) faktiskt renderar via FastAPI-mountet i
// app/web/server.py — inte hela appen. Se .superpowers/sdd/task-6-brief.md.
import { test, expect, failOnConsoleError } from "./helpers/app";

test("Svelte-grunden under /next/ renderar", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.goto("/next/");

  await expect(page.locator("#app h1")).toHaveText("Grunden är på plats.");

  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bg).toBe("rgb(241, 242, 237)"); // pappersduken (#F1F2ED)

  expect(errors, errors.join("\n")).toEqual([]);
});
