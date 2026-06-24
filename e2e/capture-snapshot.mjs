// Fångar appens FAKTISKA renderade DOM per vy och buntar till en fristående
// HTML-fil (design-system/app-snapshot.html) som kan laddas upp till Claude Design
// som "så här ser appen ut idag". Kör mot en fejk-server (ingen GPU/riktig data).
//   PORT=8766 node capture-snapshot.mjs
import { chromium } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";

const PORT = process.env.PORT || "8766";
const BASE = `http://127.0.0.1:${PORT}`;
const ROOT = "E:/Transkribera";
const OUT = `${ROOT}/design-system/app-snapshot.html`;
const SAMPLE = `${ROOT}/e2e/.test-data-preview/downloads/Mamma waw isolerad.wav`;

// Appens riktiga CSS, men: släpp lokala woff2 (offline) -> Google Fonts, och
// skala om shell-reglerna (#root) till en wrapper-klass så vyer kan staplas.
const style = readFileSync(`${ROOT}/app/web/static/style.css`, "utf8")
  .replace(/@font-face\{[^}]*\}/g, "")
  .replace(/#root\{/g, ".approot{");
const FONT = '<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&display=swap" rel="stylesheet">';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1040, height: 820 } });
await page.addInitScript((p) => {
  window.pywebview = { api: {
    pick_files: async () => [{ path: p, name: "Mamma waw isolerad.wav" }],
    save_file: async () => true, reveal: async () => true,
  }};
}, SAMPLE);

await page.goto(BASE, { waitUntil: "load" });
await page.waitForTimeout(1400);
const header = await page.evaluate(() => document.querySelector("header")?.outerHTML || "");
const grab = async (ms = 700) => { await page.waitForTimeout(ms); return page.evaluate(() => document.querySelector("main")?.outerHTML || ""); };

const shots = [];
shots.push(["Transkribera · Källa", await grab()]);

// Välj exempelfilen via fejkad pywebview-väljare -> Inställningar
try { await page.getByText("klicka för att välja").first().click(); } catch {}
shots.push(["Transkribera · Inställningar", await grab(900)]);

// Starta -> riktigt (fejkat) resultat med transkript
try {
  await page.getByRole("button", { name: /Starta/ }).first().click();
  await page.getByText("bråk och procent").first().waitFor({ timeout: 20000 });
} catch {}
shots.push(["Transkribera · Resultat", await grab(900)]);

const nav = async (name) => { try { await page.getByRole("button", { name, exact: true }).first().click(); } catch {} await page.waitForTimeout(800); };
await nav("Historik");  shots.push(["Historik", await grab()]);
await nav("Lektioner"); shots.push(["Lektioner", await grab()]);
await nav("Modeller");  shots.push(["Modeller", await grab()]);

const sections = shots.map(([label, main]) => `
  <div style="margin:0 auto 44px;max-width:1120px">
    <div style="font:600 12px Geist,system-ui,sans-serif;letter-spacing:.05em;text-transform:uppercase;color:#9a9a93;padding:6px 6px">${label}</div>
    <div class="approot" data-theme="light" style="border:1px solid #e2e2db;border-radius:16px;overflow:hidden;box-shadow:0 2px 14px rgba(0,0,0,.06)">${header}${main}</div>
  </div>`).join("\n");

const doc = `<!DOCTYPE html>
<html lang="sv" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transkribera — aktuell app-design (snapshot)</title>
${FONT}
<style>
${style}
body{margin:0;padding:30px;background:#f0f0eb;font-family:'Geist',system-ui,-apple-system,sans-serif;letter-spacing:-.01em}
.approot{display:block;min-height:0}
.approot main{min-height:0 !important}
h1.cap{max-width:1120px;margin:0 auto 20px;font:600 22px 'Geist',sans-serif;color:#0b0b0d;letter-spacing:-.02em}
</style>
</head>
<body>
<h1 class="cap">Transkribera — exakt så här ser appen ut idag (fångad från appens egen DOM)</h1>
${sections}
</body>
</html>`;

writeFileSync(OUT, doc, "utf8");
console.log("WROTE", OUT, doc.length, "tecken,", shots.length, "vyer");

await page.goto("file:///" + OUT.replace(/ /g, "%20"), { waitUntil: "load" });
await page.waitForTimeout(1800);
await page.screenshot({ path: `${ROOT}/design-system/_snapshot-verify.png` });
await browser.close();
