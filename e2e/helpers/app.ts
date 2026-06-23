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

// Collect console errors / page errors into `errors` for an assertion at the
// end of a test. Call right after creating the page, before navigation.
export function failOnConsoleError(page: Page, errors: string[]) {
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(String(e)));
}

export { test, expect };
