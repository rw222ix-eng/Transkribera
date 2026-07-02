import { Page, test, expect } from "@playwright/test";
import * as path from "path";

// The sample file the launcher copied into the isolated base/downloads.
export function samplePath(): string {
  const base = process.env.E2E_TEST_DATA as string;
  return path.join(base, "downloads", "Mamma waw isolerad.wav");
}

// Make the page believe it runs inside pywebview so the genuine file-pick ->
// transcribe flow executes. MUST be called before navigation (addInitScript).
export async function installFakePywebview(page: Page, filePath: string) {
  await page.addInitScript((p) => {
    (window as any).pywebview = {
      api: {
        pick_files: async () => [{ path: p, name: p.split(/[\\/]/).pop() }],
        save_file: async () => true,
        reveal: async () => true,
      },
    };
  }, filePath);
}

// Navigate to the app with the e2e flag so app.js exposes window.S (read-only
// state access for assertions via page.evaluate).
export async function gotoApp(page: Page) {
  await page.goto("/?e2e=1");
}

// Collect console errors / page errors into `errors` for an assertion at the
// end of a test. Call right after creating the page, before navigation.
export function failOnConsoleError(page: Page, errors: string[]) {
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(String(e)));
}

// Drive the full file-pick -> transcribe flow with the faked ASR, leaving the
// page in the "done" result view. Shared setup for post-processing tests.
export async function transcribeSample(page: Page) {
  await installFakePywebview(page, samplePath());
  await page.goto("/");
  const removeBtns = page.getByRole("button", { name: "Ta bort från kön" });
  for (let i = await removeBtns.count(); i > 0; i--) await removeBtns.first().click();
  await page.getByText("klicka för att välja").click();
  await expect(page.getByText("Mamma waw isolerad").first()).toBeVisible({ timeout: 8000 });
  await expect(page.getByText("KB-Whisper large (sv)")).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: /Starta/ }).click();
  await expect(page.getByText("bråk och procent")).toBeVisible({ timeout: 20000 });
}

export { test, expect };
