import { test, expect, failOnConsoleError } from "../helpers/app";
import * as path from "path";

const VIEWS = [
  { tab: "Transkribera", landmark: "Lägg till fler" },
  { tab: "Historik", landmark: "Historik" },
  { tab: "Lektioner", landmark: "Lektioner" },
  { tab: "Modeller", landmark: "Transkriberingsmodeller" },
];
const SIZES = [
  { w: 1040, h: 780 }, // native window size
  { w: 820, h: 600 },  // min window size
];
const THEMES = ["light", "dark"] as const;
const OUT = path.join(__dirname, "..", "visual-screens");

for (const view of VIEWS) {
  for (const size of SIZES) {
    for (const theme of THEMES) {
      test(`visual: ${view.tab} ${size.w}x${size.h} ${theme}`, async ({ page }) => {
        const errors: string[] = [];
        failOnConsoleError(page, errors);
        await page.setViewportSize({ width: size.w, height: size.h });
        await page.goto("/");

        if (theme === "dark") {
          await page.getByRole("button", { name: "Växla tema" }).click();
          await expect
            .poll(() => page.evaluate(() => document.documentElement.dataset.theme))
            .toBe("dark");
        }

        // Navigate to the view (Transkribera is default).
        if (view.tab !== "Transkribera") {
          await page.getByRole("button", { name: view.tab, exact: true }).first().click();
        }
        await expect(
          view.tab === "Transkribera"
            ? page.getByRole("button", { name: view.landmark })
            : page.getByRole("heading", { name: view.landmark })
        ).toBeVisible();

        await page.screenshot({
          path: path.join(OUT, `${view.tab}-${size.w}x${size.h}-${theme}.png`),
          fullPage: true,
        });

        // No element should overflow the viewport horizontally.
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth
        );
        expect(overflow, `horizontal overflow on ${view.tab} ${size.w}x${size.h} ${theme}`).toBeLessThanOrEqual(1);
        expect(errors, errors.join("\n")).toEqual([]);
      });
    }
  }
}
