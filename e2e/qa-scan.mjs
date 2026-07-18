// QA: arkivsökets live-progression (fas 1 kartotek + fas 2 läsbord)
// Kör mot den redan startade fakeservern på 8765 (seedad med 6 lektioner).
import { chromium } from "@playwright/test";
import * as path from "node:path";

const BASE = "http://127.0.0.1:8765";
const OUT = "E:/Transkribera/e2e/visual-screens";

const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1240, height: 900 } });
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push("PAGEERROR: " + e));

await page.goto(BASE, { waitUntil: "load" });
await page.getByRole("button", { name: "Inspelningar", exact: true }).first().click();
await page.getByPlaceholder(/Ställ en fråga/).fill("Var förklarar jag täljare och nämnare?");
await page.getByRole("button", { name: "Fråga", exact: true }).click();

// Fas 1: fånga mitt i utrullningen (kort i Läser/Läst/I kö-lägen).
await page.getByText(/Söker igenom \d+ inspelningar/).waitFor({ timeout: 5000 });
await page.waitForTimeout(450);
await page.screenshot({ path: path.join(OUT, "qa-scan-fas1.png") });

// Fas 2: läsbordet medan svaret streamas (skimmer aktiv).
await page.getByText(/AI:n läser nu dessa \d+/).waitFor({ timeout: 10000 });
await page.screenshot({ path: path.join(OUT, "qa-scan-fas2-laser.png") });

// Klart läge: Genomsökte + Svaret bygger på dessa N.
await page.getByText(/Genomsökte \d+ inspelningar/).waitFor({ timeout: 10000 });
await page.getByText(/Svaret bygger på dessa \d+/).waitFor({ timeout: 5000 });
await page.waitForTimeout(300);
await page.screenshot({ path: path.join(OUT, "qa-scan-klar.png") });

console.log("Konsolfel:", JSON.stringify(errors));
await b.close();
process.exit(0);
