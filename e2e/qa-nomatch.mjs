// QA: ärligt tomläge — AI-fråga utan innehållsordsträff ska ge ett naturligt
// svar, inte "Kunde inte söka: …". Kör mot fakeservern på 8765.
import { chromium } from "@playwright/test";
import * as path from "node:path";

const OUT = "E:/Transkribera/e2e/visual-screens";
const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1240, height: 900 } });
await page.goto("http://127.0.0.1:8765", { waitUntil: "load" });
await page.getByRole("button", { name: "Inspelningar", exact: true }).first().click();
await page.getByPlaceholder(/Ställ en fråga/).fill("Var förklarar jag fotosyntesen?");
await page.getByRole("button", { name: "Fråga", exact: true }).click();
// Genomsökningen ska spelas upp ÄVEN vid 0 träffar (svaret kommer direkt,
// utan LLM) — fånga fas 1 mitt i utrullningen, sedan det ärliga svaret.
await page.getByText(/Söker igenom \d+ inspelningar/).waitFor({ timeout: 5000 });
await page.waitForTimeout(400);
await page.screenshot({ path: path.join(OUT, "qa-scan-tomlage-fas1.png") });
await page.getByText(/läst igenom alla \d+ inspelningar/).waitFor({ timeout: 8000 });
await page.getByText(/Genomsökte \d+ inspelningar/).waitFor({ timeout: 8000 });
await page.waitForTimeout(300);
await page.screenshot({ path: path.join(OUT, "qa-scan-tomlage.png") });
console.log("tomläge OK");
await b.close();
