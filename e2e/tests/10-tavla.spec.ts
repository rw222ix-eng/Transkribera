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

test("expr.js: uttryck kompileras och ritas — ogiltiga blir [WB]-varning", async ({ page }) => {
  await page.goto("/static/whiteboard/board.html");

  const boardWith = (plots: object[]) => ({
    boards: [{
      width: 900, height: 780, chrome: "minimal", name: "expr-test",
      sections: [{ kind: "graph", width: 500, height: 320,
                   xRange: [-1, 5], yRange: [-2, 4], grid: true, axes: true,
                   plots }],
    }],
  });

  // Giltigt uttryck → kurvan ritas utan varningar.
  const ok = await page.evaluate(
    (spec) => (window as any).WBHost.render(spec).then((r: any) => r.warnings),
    boardWith([{ expr: "x^2 - 4*x + 3", color: "red" }]));
  expect(ok).toEqual([]);
  expect(await page.locator(".wb-svg path").count()).toBeGreaterThan(0);

  // Ogiltigt uttryck → [WB check]-varning i stället för krasch.
  const bad = await page.evaluate(
    (spec) => (window as any).WBHost.render(spec).then((r: any) => r.warnings),
    boardWith([{ expr: "foo(x)", color: "red" }]));
  expect(bad.some((w: string) => w.includes("ogiltigt uttryck"))).toBe(true);
});

test("Planering: generera → iterera via chatt → godkänn & spara (fejk)", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await page.goto("/");
  await page.getByRole("button", { name: "Planering", exact: true }).click();

  // Exempellektionen visas tills något genererats.
  await expect(page.getByText("Exempellektion")).toBeVisible();

  // Generera: momentet blir tavlans titel i fejken.
  await page.getByLabel("Moment").fill("Andragradsfunktioner — minimipunkt");
  await page.getByRole("button", { name: "Skriv tavlan" }).click();

  // Tavlan byts ut (fejk-boarden har graf + expr → kurvan ritas på riktigt).
  await expect(page.getByText("Andragradsfunktioner — minimipunkt").first())
    .toBeVisible({ timeout: 15000 });
  await expect(page.getByText("Exempellektion")).toHaveCount(0);
  const frame = page.frameLocator("[data-wb-frame]");
  await expect(frame.getByText("Symmetrilinjen:")).toBeVisible({ timeout: 15000 });

  // Iterera via chatten (fejken suffixar titeln).
  const chat = page.getByLabel("Ändra tavlan");
  await expect(chat).toBeVisible();
  await chat.fill("byt exempel 2 mot ett med decimaltal");
  await page.getByRole("button", { name: "Ändra", exact: true }).click();
  await expect(page.getByText(/\(ändrad\)/).first()).toBeVisible({ timeout: 15000 });

  // Godkänn & spara → WB-JSON skrivs under testets base_dir.
  const approve = page.getByRole("button", { name: "Godkänn & spara" });
  await expect(approve).toBeEnabled({ timeout: 15000 });
  await approve.click();
  const receipt = page.getByText(/Sparad:/);
  await expect(receipt).toBeVisible({ timeout: 15000 });
  const savedPath = (await receipt.innerText()).replace("Sparad: ", "").trim();
  expect(savedPath.endsWith(".json")).toBe(true);
  expect(fs.existsSync(savedPath)).toBe(true);
  const payload = JSON.parse(fs.readFileSync(savedPath, "utf-8"));
  expect(payload.version).toBe("wb-json-v1");
  expect(payload.board.title).toContain("Andragradsfunktioner");

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Planering: godkänd tavla hamnar i arkivet och kan öppnas", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Planering", exact: true }).click();

  const now = new Date();
  const datum = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-15`;
  await page.getByLabel("Moment").fill("Arkivtest — trigonometri");
  await page.getByLabel("Datum", { exact: true }).fill(datum);
  await page.getByLabel("Starttid").fill("09:10");
  await page.getByRole("button", { name: "Skriv tavlan" }).click();

  const approve = page.getByRole("button", { name: "Godkänn & spara" });
  await expect(approve).toBeEnabled({ timeout: 15000 });
  await approve.click();
  await expect(page.getByText(/Sparad:/)).toBeVisible({ timeout: 15000 });

  // Planeringen dyker upp som veckogrupperad rad i arkivet ...
  const rad = page.getByRole("button", { name: /Arkivtest — trigonometri/ });
  await expect(rad.first()).toBeVisible({ timeout: 10000 });

  // ... och klick på raden laddar den sparade tavlan i läsläge.
  await rad.first().click();
  const frame = page.frameLocator("[data-wb-frame]");
  await expect(frame.getByText("Symmetrilinjen:")).toBeVisible({ timeout: 15000 });
});

test("Planering: PNG-exporten sparar en fil under testets base_dir", async ({ page }) => {
  // Filväljardialogen (File System Access) kan inte besvaras headless —
  // ta bort API:t så exporten tar server-fallbacken (som testet verifierar).
  await page.addInitScript(() => { delete (window as any).showSaveFilePicker; });
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
