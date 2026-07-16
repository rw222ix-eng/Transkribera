import * as fs from "fs";
import { test, expect, failOnConsoleError } from "../helpers/app";

// Fas 0 — Lektionstavlan: whiteboard-motorn renderar den hårdkodade
// exempellektionen i Planering-flikens iframe, helt offline (vendrad
// KaTeX + lokala handstilsfonter), utan [WB]-layoutvarningar.

test("Planering: exempellektionen renderas utan [WB]-varningar", async ({ page }) => {
  const errors: string[] = [];
  const wbWarnings: string[] = [];
  failOnConsoleError(page, errors);
  // Motorns layoutvarningar ("[WB] …"/"[WB check] …") loggas via console.warn
  // — även inifrån iframen bubblar de till sidans console-event.
  page.on("console", (m) => {
    if (m.type() === "warning" && m.text().startsWith("[WB")) wbWarnings.push(m.text());
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Planering", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Dagens tavla" })).toBeVisible();

  const frame = page.frameLocator("[data-wb-frame]");
  await expect(frame.locator(".whiteboard").first()).toBeVisible({ timeout: 15000 });
  // Exempellektionens båda tavlor och innehåll finns på plats.
  await expect(frame.locator(".board-wrapper")).toHaveCount(2);
  await expect(frame.getByText("Exempel 1")).toBeVisible();
  // KaTeX renderade matten — beviset för att den lokala vendringen fungerar.
  await expect(frame.locator(".katex").first()).toBeVisible();

  // Knappen aktiveras först när renderBoard() lösts — dvs. efter motorns
  // asynkrona överlappskoll. Då är varningslistan komplett.
  await expect(page.getByRole("button", { name: "Spara som PNG" })).toBeEnabled({ timeout: 15000 });

  expect(wbWarnings, wbWarnings.join("\n")).toEqual([]);
  expect(errors, errors.join("\n")).toEqual([]);
});

test("Planering: PNG-exporten sparar en fil under testets base_dir", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Planering", exact: true }).click();

  const save = page.getByRole("button", { name: "Spara som PNG" });
  await expect(save).toBeEnabled({ timeout: 15000 });
  await save.click();

  const receipt = page.getByText(/PNG sparad:/);
  await expect(receipt).toBeVisible({ timeout: 20000 });
  const savedPath = (await receipt.innerText()).replace("PNG sparad: ", "").trim();
  expect(savedPath).toContain("planering");
  expect(fs.existsSync(savedPath)).toBe(true);
  // PNG-signaturen — exporten är en riktig rastrerad bild, inte tom data.
  const head = fs.readFileSync(savedPath).subarray(0, 8);
  expect(head.equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))).toBe(true);
});
