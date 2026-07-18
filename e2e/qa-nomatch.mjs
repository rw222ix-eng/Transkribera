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
await page.getByText(/Ingen inspelning i arkivet verkar nämna/).waitFor({ timeout: 8000 });
await page.screenshot({ path: path.join(OUT, "qa-scan-tomlage.png") });
console.log("tomläge OK");
await b.close();
