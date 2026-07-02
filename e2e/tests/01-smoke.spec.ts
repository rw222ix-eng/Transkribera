import { test, expect, failOnConsoleError } from "../helpers/app";

// One stable landmark per top-level view (discovered against the live app).
// Modeller-fliken togs bort ur headern i omdesignen (fast modelluppsättning);
// kvar finns bara Transkribera och Inspelningar.
const VIEWS: { tab: string; landmark: (page: import("@playwright/test").Page) => import("@playwright/test").Locator }[] = [
  { tab: "Transkribera", landmark: (p) => p.getByRole("heading", { name: "Vad vill du transkribera?" }) },
  { tab: "Inspelningar", landmark: (p) => p.getByRole("heading", { name: "Inspelningar" }) },
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
