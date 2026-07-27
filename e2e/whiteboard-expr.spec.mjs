// Räddad ur den pensionerade vanilla-sviten (e2e/tests/10-tavla.spec.ts) i
// samband med att app.js, style.css och index.html raderades — se
// docs/superpowers/plans/2026-07-25-cutover-till-svelte.md, Task 4, och
// .superpowers/sdd/pensionering-report.md. Testet nedan är den enda spärren
// mot att ogiltiga uttryck kraschar whiteboard-motorn (expr.js); motorn
// lever vidare (Planering-flikens tavla, prov/arbetsblad) helt oberoende av
// gamla appen, så testet flyttas hit ORDAGRANT i stället för att pensioneras
// med resten av 10-tavla.spec.ts. Assertionerna är oförändrade.
import { test, expect } from "./helpers/app";

test("expr.js: uttryck kompileras och ritas — ogiltiga blir [WB]-varning", async ({ page }) => {
  await page.goto("/static/whiteboard/board.html");

  const boardWith = (plots) => ({
    boards: [{
      width: 900, height: 780, chrome: "minimal", name: "expr-test",
      sections: [{ kind: "graph", width: 500, height: 320,
                   xRange: [-1, 5], yRange: [-2, 4], grid: true, axes: true,
                   plots }],
    }],
  });

  // Giltigt uttryck → kurvan ritas utan varningar.
  const ok = await page.evaluate(
    (spec) => window.WBHost.render(spec).then((r) => r.warnings),
    boardWith([{ expr: "x^2 - 4*x + 3", color: "red" }]));
  expect(ok).toEqual([]);
  expect(await page.locator(".wb-svg path").count()).toBeGreaterThan(0);

  // Ogiltigt uttryck → [WB check]-varning i stället för krasch.
  const bad = await page.evaluate(
    (spec) => window.WBHost.render(spec).then((r) => r.warnings),
    boardWith([{ expr: "foo(x)", color: "red" }]));
  expect(bad.some((w) => w.includes("ogiltigt uttryck"))).toBe(true);
});
