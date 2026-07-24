// Playwright-smoke för den parallella Svelte+Vite-frontenden under /next.
// Bevisar bara att grunden renderar via FastAPI-mountet i app/web/server.py —
// att designsystemets pappersduk laddar och att sidan är felfri. Själva
// tavelflödet testas av planering-tavla.spec.mjs.
import { test, expect, failOnConsoleError } from "./helpers/app";

test("Svelte-grunden under /next/ renderar", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.goto("/next/");

  // Vyns rubrik — sätts av PlaneringView, inte av det gamla scaffold-skalet.
  await expect(page.locator("#app h1")).toHaveText("Dagens tavla");

  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bg).toBe("rgb(241, 242, 237)"); // pappersduken (#F1F2ED)

  expect(errors, errors.join("\n")).toEqual([]);
});
