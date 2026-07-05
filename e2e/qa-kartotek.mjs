// Engångs-QA för kartotek-porten: transkribera samplet, gå till Inspelningar,
// kör Fråga AI-flödet och öppna lektionsoverlayen — skärmbilder till visual-screens/.
//   TRANSKRIBERA_PORT=8733 TRANSKRIBERA_BASE_DIR=e2e/.test-data node e2e/qa-kartotek.mjs
import { chromium } from "@playwright/test";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const DIR = path.dirname(fileURLToPath(import.meta.url));
const PORT = process.env.QA_PORT || "8733";
const BASE = `http://127.0.0.1:${PORT}`;
const SAMPLE = path.join(DIR, ".test-data-qa", "downloads", "Mamma waw isolerad.wav");
const OUT = path.join(DIR, "visual-screens");

const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1200, height: 860 } });
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push("PAGEERROR: " + e));

await page.addInitScript((p) => {
  window.pywebview = { api: {
    pick_files: async () => [{ path: p, name: "Mamma waw isolerad.wav" }],
    save_file: async () => true, reveal: async () => true,
  }};
}, SAMPLE);

await page.goto(BASE, { waitUntil: "load" });

// Transkribera samplet så arkivet har en lektion.
const removeBtns = page.getByRole("button", { name: "Ta bort från kön" });
for (let i = await removeBtns.count(); i > 0; i--) await removeBtns.first().click();
await page.getByText("klicka för att välja").click();
await page.getByText("KB-Whisper large (sv)").waitFor({ timeout: 15000 });
await page.getByRole("button", { name: /Starta/ }).click();
await page.getByText("bråk och procent").first().waitFor({ timeout: 20000 });

// 1) Kartoteket (ljust)
await page.getByRole("button", { name: "Inspelningar", exact: true }).first().click();
await page.locator("[data-rec-id]").first().waitFor({ timeout: 10000 });
await page.waitForTimeout(600);
await page.screenshot({ path: path.join(OUT, "qa-kartotek-light.png"), fullPage: true });

// 2) Fråga AI-flödet: skanning + inline-svar
await page.getByPlaceholder(/Ställ en fråga/).fill("bråk");
await page.getByRole("button", { name: "Fråga", exact: true }).click();
await page.getByText("[FEJK svar]").waitFor({ timeout: 15000 });
await page.getByText(/Genomsökte \d+ inspelningar/).waitFor({ timeout: 10000 });
await page.waitForTimeout(400);
await page.screenshot({ path: path.join(OUT, "qa-ask-flow.png"), fullPage: true });

// 3) Lektionsoverlayen: transkript + chatt + kalenderförslag
await page.getByRole("button", { name: "✕ Ny fråga" }).click();
await page.locator("[data-rec-id]").first().click();
await page.getByText("Transkription").waitFor({ timeout: 10000 });
await page.getByRole("button", { name: "Kalenderhändelse" }).click();
await page.getByText("Förslag → Google Kalender").waitFor({ timeout: 5000 });
await page.waitForTimeout(400);
await page.screenshot({ path: path.join(OUT, "qa-overlay-event.png"), fullPage: true });

// 4) Mörkt tema på kartoteket
await page.keyboard.press("Escape");
await page.getByRole("button", { name: "Växla tema" }).click();
await page.waitForTimeout(400);
await page.screenshot({ path: path.join(OUT, "qa-kartotek-dark.png"), fullPage: true });

console.log("Konsolfel:", JSON.stringify(errors, null, 2));
await b.close();
process.exit(errors.length ? 1 : 0);
