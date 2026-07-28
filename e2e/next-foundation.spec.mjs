// Playwright-smoke för den parallella Svelte+Vite-frontenden under /next.
// Bevisar bara att grunden renderar via FastAPI-mountet i app/web/server.py —
// att designsystemets pappersduk laddar och att sidan är felfri. Själva
// tavelflödet testas av planering-tavla.spec.mjs.
import { test, expect, failOnConsoleError } from "./helpers/app";

test("Svelte-grunden under /next/ renderar", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.goto("/next/");

  // Skalet: tre flikar, Transkribera aktiv från start. Flikarna är RIKTIGA
  // flikar (role="tab" i en tablist), inte längre växlingsknappar med
  // aria-pressed — se AppShell.svelte för varför.
  const tabs = ["Transkribera", "Inspelningar", "Planering"];
  for (const t of tabs) {
    await expect(page.getByRole("tab", { name: t, exact: true })).toBeVisible();
  }
  // Panelen är knuten till sin flik. Utan den här raden kan aria-controls
  // peka på ett id som inte finns och testet märker ingenting.
  await expect(page.getByRole("tabpanel", { name: "Transkribera" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Transkribera", exact: true }))
    .toHaveAttribute("aria-selected", "true");

  // Planeringsvyn finns kvar bakom sin flik.
  await page.getByRole("tab", { name: "Planering", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Dagens tavla" })).toBeVisible();

  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bg).toBe("rgb(241, 242, 237)"); // pappersduken (#F1F2ED)

  expect(errors, errors.join("\n")).toEqual([]);
});
