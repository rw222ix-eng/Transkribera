import { Page, test, expect } from "@playwright/test";

// Städat i samband med att den gamla vanilla-appen (app.js/style.css/
// index.html) pensionerades — se
// docs/superpowers/plans/2026-07-25-cutover-till-svelte.md, Task 4, och
// .superpowers/sdd/pensionering-report.md. Borttaget: samplePath,
// installFakePywebview, gotoApp och transcribeSample — de drev den gamla
// filväljar-/pywebview-baserade transkriberingsguiden och användes bara av
// de nu raderade specarna under e2e/tests/ (utom 08-real-smoke.spec.ts, som
// portats till Svelte-flödet och inte behöver dem: /api/sample ger en
// riktig sökväg utan pywebview-mock). Ingen kvarvarande spec importerar
// dem — kontrollerat före borttagningen.

// Collect console errors / page errors into `errors` for an assertion at the
// end of a test. Call right after creating the page, before navigation.
export function failOnConsoleError(page: Page, errors: string[]) {
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(String(e)));
}

export { test, expect };
