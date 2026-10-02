import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { forbiNivavarningen } from "./larardag.mjs";

/* PROVETS FIGURRECEPT PÅ ARBETSBLADET
 *
 * Generatorn skriver figurer som recept ur exam_spec ({"typ":"linjar","k":2,
 * "m":1}, andragrad, exponential …). Provet sätts i LaTeX och fick sin graf
 * av exam_figures.py, men arbetsbladets och gruppuppgiftens PDF är skärmens
 * avritning, och figurer.js kände inte typerna. NA26F:s blad (exam 160,
 * 2026-10-02) stod med «Figuren visar grafen till …» och ingen graf.
 *
 * Här skrivs ett arbetsblad med en linjär graf och en andragradsgraf (den
 * senare på en uppgift med deluppgifter), och båda måste bli SVG med en blå kurva
 * (exam_figures: \draw[blue,very thick]; Typsts blue är #0074d9). Allt API
 * fejkas, sviten skriver aldrig mot lärarens server.
 */

const SCHEMA = {
  schema: [{ dag: 1, tid: "09:05–10:20", kurs: "Matematik, nivå 1c",
             klass: "NA26F", sal: "P807" }],
  lov: [], poster: [],
};

const EXAM = {
  titel: "Funktioner och grafer",
  kurs: "Matematik, nivå 1c", klass: "NA26F", datum: "2026-11-16", tid_min: 60,
  hjalpmedel: "Räknare får användas.",
  uppgifter: [
    { formaga: "B", typ: "rutin", poang: [2, 0, 0],
      text: "Figuren visar grafen till funktionen $f(x) = 2x + 1$.",
      figur: { typ: "linjar", k: 2, m: 1 },
      losning: "$f(2) = 5$", bedomning: "+1 E avläsning." },
    { formaga: "B", typ: "rutin", poang: [1, 1, 0],
      text: "Grafen till en andragradsfunktion visas i figuren.",
      figur: { typ: "andragrad", a: 1, b: -4, c: 3 },
      losning: "", bedomning: "",
      deluppgifter: [
        { poang: [1, 0, 0], text: "Ange nollställena.",
          losning: "$x = 1$ och $x = 3$", bedomning: "+1 E" },
        { poang: [0, 1, 0], text: "Ange symmetrilinjen.",
          losning: "$x = 2$", bedomning: "+1 C" },
      ] },
  ],
};

const strom = h => h.map(x => `data: ${JSON.stringify(x)}\n\n`).join("");

async function fejka(page) {
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
  await page.route("**/api/planning/**", route => json(route, { ok: true }));
  await page.route("**/api/exams/**", route => route.fulfill({
    status: 200, contentType: "text/event-stream",
    body: strom([{ type: "done", result: {
      id: 9, exam: EXAM, typ: "arbetsblad", status: "utkast", errors: [],
      rounds: 1, granser: { E: 3, C: 1, A: 0 }, summor: { totalt: 4 } } }]) }));
}

test("arbetsbladet ritar provets linjar- och andragradsgraf", async ({ page }) => {
  const varningar = [];
  page.on("console", m => { if (/Okänd figurtyp/.test(m.text())) varningar.push(m.text()); });
  await fejka(page);
  await page.goto("/");
  await page.waitForFunction(() =>
    window.Kalender && window.Kalender.franServern() && window.Dokument);
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => {
    window.SattLage("Arbetsblad");
    const satt = (id, v) => {
      const e = document.querySelector(id);
      e.value = v;
      e.dispatchEvent(new Event("change", { bubbles: true }));
    };
    satt("#p-kurs", "Matematik, nivå 1c");
    satt("#p-klass", "NA26F");
    const f = document.querySelector("#moment");
    f.value = "funktioner";
    f.dispatchEvent(new Event("input", { bubbles: true }));
    window.PlanSteg.las(4, false);
    window.PlanSteg.gaTill(4);
  });
  await page.locator("#skriv").click();
  await forbiNivavarningen(page);
  await expect(page.locator("#dokument")).toBeVisible({ timeout: 15_000 });

  /* Båda recepten ska bli källa (data-cetz) och sedan SVG. Kompilatorn är
     kall första gången och tar några sekunder. */
  const figurer = page.locator('#dokument [data-figur^="{"]');
  await expect(figurer).toHaveCount(2);
  await expect(page.locator('#dokument [data-figur^="{"] svg')).toHaveCount(2,
    { timeout: 45_000 });

  const kurvor = await page.evaluate(() =>
    [...document.querySelectorAll('#dokument [data-figur^="{"]')].map(el => ({
      typ: JSON.parse(el.dataset.figur).typ,
      blaa: [...el.querySelectorAll("svg path")].filter(p =>
        /#0074d9/i.test((p.getAttribute("stroke") || "") + (p.getAttribute("style") || ""))).length,
      text: el.querySelector("svg") ? el.querySelectorAll("svg use").length : 0,
    })));
  expect(kurvor.map(k => k.typ).sort()).toEqual(["andragrad", "linjar"]);
  for (const k of kurvor) {
    expect(k.blaa, `${k.typ}: ingen blå kurva i SVG:n`).toBeGreaterThan(0);
    expect(k.text, `${k.typ}: inga etiketter på axlarna`).toBeGreaterThan(3);
  }
  expect(varningar).toEqual([]);

  /* Bilderna hamnar i worktreens test-results/ (gitignorerad) för ögat. */
  const ut = join(dirname(fileURLToPath(import.meta.url)), "..", "test-results", "provfigurer");
  mkdirSync(ut, { recursive: true });
  for (let i = 0; i < 2; i++) {
    await figurer.nth(i).scrollIntoViewIfNeeded();
    await figurer.nth(i).screenshot({ path: join(ut, `figur-${i + 1}.png`) });
  }
  await page.locator("#dokument").screenshot({ path: join(ut, "bladet.png") });
});

test("varje provrecept kompileras till SVG i Typst", async ({ page }) => {
  /* Node-testet (tests/test_figurer_exam_spec.py) ser bara att källan finns.
     Om CeTZ godtar den syns först här: ett syntaxfel i ett recept ger ingen
     SVG, och bladet står med en röd ruta. */
  const FIGURER = [
    { typ: "linjar", k: -3, m: 4 },
    { typ: "andragrad", a: -0.5, b: 2, c: -6 },
    { typ: "exponential", C: 2, bas: 1.5 },
    { typ: "normalfordelning", mu: 170, sigma: 7.5 },
    { typ: "triangel", a: 3, b: 4, c: 5 },
    { typ: "enhetscirkel", vinkel: 130 },
    { typ: "stapeldiagram", kategorier: ["Buss", "Cykel*", "_Bil_"], varden: [12, 7, 3] },
    { typ: "ladagram", min: 2, q1: 5, median: 7.5, q3: 9, max: 14 },
    // Tavlans triangel, den gamla formen, ska ritas som förut.
    { typ: "triangel", rattVid: "B", sidaAB: "a", sidaBC: "b", sidaCA: "c" },
  ];
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.Figur && window.Figurer);
  const ut = await page.evaluate(async figurer => {
    const rot = document.createElement("div");
    rot.id = "provrecept";
    rot.style.cssText = "position:fixed;inset:0;z-index:99999;background:#fff;display:grid;"
      + "grid-template-columns:repeat(3,1fr);gap:12px;padding:12px;overflow:auto";
    document.body.appendChild(rot);
    const svar = [];
    for (const f of figurer) {
      const ruta = document.createElement("div");
      ruta.style.cssText = "border:1px solid #ddd;padding:4px;height:240px";
      rot.appendChild(ruta);
      try {
        ruta.innerHTML = await window.Figur.svg(window.Figurer.kalla(f));
        const s = ruta.querySelector("svg");
        s.style.width = "100%";
        s.style.height = "100%";
        svar.push({ typ: f.typ, ok: true, banor: ruta.querySelectorAll("path").length });
      } catch (e) {
        svar.push({ typ: f.typ, ok: false, fel: String((e && e.message) || e) });
      }
    }
    return svar;
  }, FIGURER);
  for (const s of ut) {
    expect(s.ok, `${s.typ}: ${s.fel}`).toBe(true);
    expect(s.banor, `${s.typ}: tom SVG`).toBeGreaterThan(2);
  }
  const mapp = join(dirname(fileURLToPath(import.meta.url)), "..", "test-results", "provfigurer");
  mkdirSync(mapp, { recursive: true });
  await page.setViewportSize({ width: 1200, height: 800 });
  await page.locator("#provrecept").screenshot({ path: join(mapp, "alla-recept.png") });
});
