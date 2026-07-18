// QA: svarskortets nya enkolumnslayout (layout-passet 2026-07-18):
// hårlinje-fot med åtgärder, centrerad chattvy, källchips i arkivfoten.
import { chromium } from "@playwright/test";
import * as path from "node:path";

const OUT = "E:/Transkribera/e2e/visual-screens";
const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1280, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push("PAGEERROR: " + e));

await page.goto("http://127.0.0.1:8765", { waitUntil: "load" });

// 1) Inspelningssidans svarskort — fot med åtgärder, ingen sidospalt.
await page.getByRole("button", { name: "Inspelningar", exact: true }).first().click();
await page.getByPlaceholder(/Ställ en fråga/).fill("Var förklarar jag täljare och nämnare?");
await page.getByRole("button", { name: "Fråga", exact: true }).click();
await page.getByText(/Genomsökte \d+ inspelningar/).waitFor({ timeout: 15000 });
await page.getByText("Öppna i chattvyn ↗").waitFor({ timeout: 15000 });
await page.waitForTimeout(400);
await page.screenshot({ path: path.join(OUT, "qa-svarskort-fot.png") });

// 2) Chattvyn — centrerad läsström, höjd efter innehåll.
await page.getByText("Öppna i chattvyn ↗").click();
await page.getByRole("dialog", { name: "Arkivsvar — chatt" }).waitFor({ timeout: 5000 });
await page.waitForTimeout(600);
await page.screenshot({ path: path.join(OUT, "qa-svarskort-zoom.png") });
await page.keyboard.press("Escape");
await page.waitForTimeout(500);

// 3) Planeringsarkivets svarskort — källchips i foten.
await page.getByRole("button", { name: "Planering", exact: true }).first().click();
const arkInput = page.getByPlaceholder(/Ställ en fråga/);
await arkInput.waitFor({ timeout: 8000 });
await arkInput.fill("vad gick vi igenom om täljare?");
await page.getByRole("button", { name: "Fråga", exact: true }).click();
await page.getByText(/Genomsökte \d+ tavlor och prov/).waitFor({ timeout: 15000 });
await page.getByText("Källor", { exact: true }).waitFor({ timeout: 15000 });
await page.waitForTimeout(400);
await page.screenshot({ path: path.join(OUT, "qa-svarskort-arkiv.png") });

console.log("Sidfel:", JSON.stringify(errors));
await b.close();
process.exit(errors.length ? 1 : 0);
