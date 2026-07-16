// Spec-runner för lektionstavlor (Fas 2): ladda godtycklig WB-JSON headless,
// returnera motorns [WB]-varningar och (valfritt) en skärmdump.
//
//   node e2e/render-board.mjs <spec.json> [--screenshot <ut.png>]
//
// spec.json är antingen ett helt WB-dokument ({title, boards}) eller motorns
// råa format ({boards} / enskild board). Skriptet startar en egen liten
// statisk server över app/web/static (ingen FastAPI behövs) och skriver
// resultatet som JSON på stdout:
//
//   { "warnings": ["[WB] …", …], "screenshot": "ut.png" | null }
//
// Används av tests/bench_whiteboard.py och för manuell felsökning — samma
// metodik som designprojektets screenshots-iterationer.
import * as fs from "fs";
import * as http from "http";
import * as path from "path";
import { fileURLToPath } from "url";
import { chromium } from "playwright";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATIC_DIR = path.resolve(HERE, "..", "app", "web", "static");

const args = process.argv.slice(2);
const specPath = args.find((a) => !a.startsWith("--"));
if (!specPath) {
  console.error("användning: node render-board.mjs <spec.json> [--screenshot <ut.png>]");
  process.exit(2);
}
const shotIdx = args.indexOf("--screenshot");
const shotPath = shotIdx >= 0 ? args[shotIdx + 1] : null;

const raw = JSON.parse(fs.readFileSync(specPath, "utf-8"));
const spec = raw.boards ? { boards: raw.boards } : raw;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".woff2": "font/woff2",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, "http://x").pathname)
    .replace(/^\/static\//, "/");
  const file = path.join(STATIC_DIR, path.normalize(rel).replace(/^([\\/]|\.\.)+/, ""));
  if (!file.startsWith(STATIC_DIR) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404); res.end("not found"); return;
  }
  res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});

await new Promise((r) => server.listen(0, "127.0.0.1", r));
const port = server.address().port;

setTimeout(() => { console.error("HARD TIMEOUT"); process.exit(3); }, 90000);

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  await page.goto(`http://127.0.0.1:${port}/whiteboard/board.html`, { timeout: 20000 });
  const result = await page.evaluate(
    (s) => window.WBHost.render(s).then((r) => ({ warnings: r.warnings })),
    spec);
  if (pageErrors.length) result.warnings.push(...pageErrors.map((e) => "[JS-fel] " + e));
  if (shotPath) {
    await page.waitForTimeout(150);   // låt fit-skalningen sätta sig
    await page.screenshot({ path: shotPath, fullPage: true });
  }
  result.screenshot = shotPath || null;
  console.log(JSON.stringify(result));
  await browser.close();
  server.close();
  process.exit(0);              // keep-alive-anslutningar håller annars servern vid liv
} catch (e) {
  console.error(String(e));
  await browser.close().catch(() => {});
  process.exit(1);
}
