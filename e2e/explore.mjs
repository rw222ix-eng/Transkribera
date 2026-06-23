import { chromium } from "@playwright/test";

const TABS = ["Transkribera", "Historik", "Lektioner", "Modeller"];

const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1040, height: 780 } });
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push("PAGEERROR: " + e));
await page.goto("http://127.0.0.1:8731/");
await page.waitForTimeout(800);

async function dump(label) {
  const buttons = await page.$$eval("button", (els) =>
    els.map((e) => (e.textContent || "").trim()).filter(Boolean).slice(0, 40));
  const headings = await page.$$eval("h1,h2,h3", (els) =>
    els.map((e) => (e.textContent || "").trim()).filter(Boolean).slice(0, 15));
  const inputs = await page.$$eval("input,select,textarea", (els) =>
    els.map((e) => `${e.tagName.toLowerCase()}[${e.type || ""}] ph="${e.placeholder || ""}"`).slice(0, 20));
  console.log(`\n===== ${label} =====`);
  console.log("H:", JSON.stringify(headings));
  console.log("BTN:", JSON.stringify(buttons));
  console.log("IN:", JSON.stringify(inputs));
}

await dump("initial (Transkribera)");
for (const t of TABS.slice(1)) {
  await page.getByRole("button", { name: t, exact: true }).first().click();
  await page.waitForTimeout(600);
  await dump(t);
}
console.log("\nCONSOLE_ERRORS:", JSON.stringify(errors, null, 2));
await b.close();
