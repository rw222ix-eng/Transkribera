import { test, expect, failOnConsoleError, transcribeSample } from "../helpers/app";

// /api/open launches a native file-explorer window on the host; stub it so the
// QA run never spawns Explorer windows.
async function stubOpen(page: import("@playwright/test").Page) {
  await page.route("**/api/open", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
}

test("assign a lesson to a class and course", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await transcribeSample(page);

  await page.getByRole("button", { name: "Lektioner", exact: true }).first().click();
  await page.getByRole("button", { name: "Tilldela" }).first().click();
  await page.getByPlaceholder("t.ex. NA21").fill("NA21");
  await page.getByPlaceholder("t.ex. Matematik 2b").fill("Matematik 2b");
  await expect(page.getByPlaceholder("t.ex. Matematik 2b")).toHaveValue("Matematik 2b");
  await page.getByRole("button", { name: "Spara", exact: true }).click();

  // The assigned lesson row shows class + course together (filter dropdowns also
  // gain hidden <option>s, so match the row's combined text, not bare "NA21").
  await expect(page.getByText(/NA21[\s\S]*Matematik 2b/).first()).toBeVisible({ timeout: 10000 });
  expect(errors, errors.join("\n")).toEqual([]);
});

test("export the knowledge-base backup", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await stubOpen(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Lektioner", exact: true }).first().click();

  const [resp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/backup")),
    page.getByRole("button", { name: /Säkerhetskopiera/ }).click(),
  ]);
  expect(resp.status()).toBe(200);
  await expect(page.getByText("Säkerhetskopia skapad")).toBeVisible({ timeout: 8000 });
  expect(errors, errors.join("\n")).toEqual([]);
});

test("export a lesson report", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await stubOpen(page);
  await transcribeSample(page);

  await page.getByRole("button", { name: "Lektioner", exact: true }).first().click();
  await page.getByRole("button", { name: "Insikter" }).first().click();
  const [resp] = await Promise.all([
    page.waitForResponse((r) => /\/api\/lessons\/\d+\/report/.test(r.url())),
    page.getByRole("button", { name: /Rapport/ }).click(),
  ]);
  expect(resp.status()).toBe(200);
  expect(errors, errors.join("\n")).toEqual([]);
});

test("agenda exports an .ics calendar (API)", async ({ request }) => {
  // The agenda panel only renders when dated insights exist; verify the export
  // endpoint that powers it directly.
  const resp = await request.post("http://127.0.0.1:8731/api/agenda/ics", { data: {} });
  expect(resp.status()).toBe(200);
  const body = await resp.json();
  expect(String(body.path)).toContain(".ics");
});
