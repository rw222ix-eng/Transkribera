import { test, expect, failOnConsoleError } from "../helpers/app";

// One stable landmark per top-level view (discovered against the live app).
const VIEWS: { tab: string; landmark: (page: import("@playwright/test").Page) => import("@playwright/test").Locator }[] = [
  { tab: "Transkribera", landmark: (p) => p.getByRole("heading", { name: "Vad vill du transkribera?" }) },
  { tab: "Historik", landmark: (p) => p.getByRole("heading", { name: "Historik" }) },
  { tab: "Lektioner", landmark: (p) => p.getByRole("heading", { name: "Lektioner" }) },
  { tab: "Modeller", landmark: (p) => p.getByRole("heading", { name: "Transkriberingsmodeller" }) },
];

test("app boots without console errors", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await page.goto("/");
  await expect(page.locator("#root")).not.toBeEmpty();
  // Transcribe is the default view; a clean start opens on the source step.
  await expect(page.getByRole("heading", { name: "Vad vill du transkribera?" })).toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
});

for (const v of VIEWS) {
  test(`view renders: ${v.tab}`, async ({ page }) => {
    const errors: string[] = [];
    failOnConsoleError(page, errors);
    await page.goto("/");
    await page.getByRole("button", { name: v.tab, exact: true }).first().click();
    await expect(v.landmark(page)).toBeVisible();
    expect(errors, errors.join("\n")).toEqual([]);
  });
}
