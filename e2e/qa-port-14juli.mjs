// Visuell QA av 14 juli-porten mot fejkservern.
// Kör:  node qa-port-14juli.mjs   (startar egen server på TRANSKRIBERA_PORT || 8841)
// Skärmbilder hamnar i visual-screens/port-14juli/.
import { chromium } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.TRANSKRIBERA_PORT || 8841);
const BASE = `http://127.0.0.1:${PORT}`;
const OUT = path.join(here, "visual-screens", "port-14juli");
mkdirSync(OUT, { recursive: true });

const TEST_DATA = path.join(here, ".test-data-qa");
const server = spawn("python", [path.join(here, "serve_test_app.py")], {
  env: { ...process.env, TRANSKRIBERA_PORT: String(PORT), TRANSKRIBERA_BASE_DIR: TEST_DATA },
  stdio: "ignore",
});
const kill = () => { try { server.kill(); } catch {} };
process.on("exit", kill);

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
for (let i = 0; i < 60; i++) {
  try { const r = await fetch(BASE + "/api/hardware"); if (r.ok) break; } catch {}
  await wait(500);
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1240, height: 860 } });
const shot = (name) => page.screenshot({ path: path.join(OUT, name + ".png"), fullPage: false });

// Fejka pywebview-pickern med exempel-filen.
const sample = path.join(TEST_DATA, "downloads", "Mamma waw isolerad.wav");
await page.addInitScript((p) => {
  window.pywebview = { api: { pick_files: () => Promise.resolve([{ name: "Mamma waw isolerad.wav", path: p }]) } };
}, sample);

await page.goto(BASE + "/?e2e=1");
await page.getByText("klicka för att välja").click();
await page.getByText("KB-Whisper large (sv)").waitFor({ timeout: 15000 });
await page.getByRole("button", { name: /Starta/ }).click();

// Steg 3 under körning (fejken är snabb — bilderna är best effort).
await page.getByText(/Inspelningar öppnas när det är klart/).waitFor({ timeout: 6000 }).catch(() => {});
await shot("01-steg3-bearbetar-lokalt");

// Klart-raden + auto-navigeringen.
await page.getByText(/Öppnar Inspelningar/).waitFor({ timeout: 20000 }).catch(() => {});
await shot("02-steg3-klart");
await page.locator("[data-rec-id]").first().waitFor({ timeout: 15000 });
await shot("03-inspelningar-efter-auto-nav");

// Arkivsvaret: Fråga AI → svar med källpanel + följdfrågefält.
await page.getByRole("button", { name: "Fråga AI", exact: true }).first().click();
const ask = page.getByPlaceholder("Ställ en fråga, t.ex. när hade vi prov om derivata?");
await ask.fill("bråk");
await page.getByRole("button", { name: "Fråga", exact: true }).click();
await page.getByText("[FEJK svar]").waitFor({ timeout: 15000 });
await page.getByText("Källor i arkivet").waitFor({ timeout: 10000 });
await shot("04-arkivsvar-kallpanel");

// Zooma svaret till modal.
await page.getByTitle("Klicka för att förstora svaret").click();
await wait(600);
await shot("05-arkivsvar-zoom");
await page.keyboard.press("Escape");
await wait(500);

// Lektionsoverlayn: sidopanel-chatt + källa som scrollar transkriptet.
await page.keyboard.press("Escape"); // rensa ask-läget
await page.locator("[data-rec-id]").first().click();
const chatInput = page.getByPlaceholder("Skriv en fråga …");
await chatInput.waitFor({ timeout: 15000 });
await shot("06-overlay-sidopanel");
await chatInput.fill("Vad handlar lektionen om?");
await chatInput.press("Enter");
await page.getByRole("button", { name: "Visa källa 1 i transkriptet" }).waitFor({ timeout: 15000 });
await page.getByRole("button", { name: "Visa källa 1 i transkriptet" }).click();
await page.locator("[data-ovhit]").waitFor({ timeout: 5000 });
await wait(400);
await shot("07-overlay-kalla-scrollad");

// Kalenderförslag i sidopanelen.
await page.getByRole("button", { name: "Kalenderhändelse" }).click().catch(() => {});
await wait(400);
await shot("08-overlay-kalenderforslag");

await browser.close();
kill();
console.log("Skärmbilder i", OUT);
