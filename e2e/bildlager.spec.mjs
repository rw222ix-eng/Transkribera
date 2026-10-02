import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { existsSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/* BILDLAGRET (lärarens dom 2026-10-02)
 *
 * Där en uppgift beskriver något med mycket text ska bilden ha pilar och mått
 * ovanpå, så att eleven direkt ser vad det handlar om. Plåten är bara målning;
 * lagret är data i dokumentet (`v.bildlager`) som bladet ritar ovanpå bilden
 * (blad-bygg.js bildlager, blad.js bildlagren). tools/bildlager.py skriver
 * datan via appens API.
 *
 * Testet kör verktyget på riktigt mot sviten egen server (18751, tom bas),
 * ritar dokumentet i appen och ritar av det som godkännandet gör. Skärmbilden
 * och avritningen sparas i repots rot (bildlager-skarm.png,
 * bildlager-avritning.png; *.png är gitignorerat) för ögat.
 */

const ROT = join(dirname(fileURLToPath(import.meta.url)), "..");
const PY = existsSync(join(ROT, ".venv/Scripts/python.exe"))
  ? join(ROT, ".venv/Scripts/python.exe")
  : existsSync(join(ROT, ".venv/bin/python")) ? join(ROT, ".venv/bin/python")
    : process.platform === "win32" ? "python" : "python3";

const TUNNEL = {
  begrepp: "negativa tal", filnamn: "a-40-gangtunnel",
  scene: "SCENE. A pedestrian tunnel under a lawn, seen in cross-section.",
};

const LAGER = [
  { typ: "linje", fran: [0, 0.3], till: [1, 0.3], streckad: true, text: "markytan $0$ m" },
  { typ: "pil", fran: [0.17, 0.55], till: [0.3, 0.46], text: "taket $-1$ m" },
  { typ: "pil", fran: [0.17, 0.93], till: [0.3, 0.83], text: "golvet $-4$ m" },
  { typ: "matt", fran: [0.62, 0.45], till: [0.62, 0.84], text: "? m" },
  { typ: "etikett", plats: [0.84, 0.12], text: "Saga: $5$ m?" },
];

function papper() {
  return {
    typ: "Arbetsblad", moment: "Negativa tal", klass: "BA26B",
    kurs: "Matematik, nivå 1a", datum: "2026-10-05", tid: "",
    gy: [], kalla: false, kallor: [], inst: { antal: 2, niva: "E-nivå" },
    bilder: {}, referenser: [], forlaga: null, resultat: null, fokus: "",
    kontext: "start", niva: false, svarighet: 0, andrat: [], provId: 12,
    uppgifter: [
      { nr: 1, p: 1, t: "Beräkna $-3 + 7$.", f: "$4$" },
      { nr: 2, p: 2, t: "Höjderna mäts i meter från markytan. Taket i en "
        + "gångtunnel ligger på $-1$ m och dess golv på $-4$ m. Saga påstår att "
        + "tunneln är $5$ m hög. Har hon rätt?", f: "Nej, $3$ m.", scen: TUNNEL },
    ],
  };
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

/* En målning utan text: himmel, gräs, jord och tunnelns mörka hål. */
const malning = (page, b, h) => page.evaluate(([b, h]) => {
  const c = document.createElement("canvas");
  c.width = b; c.height = h;
  const g = c.getContext("2d");
  g.fillStyle = "#9cc3de"; g.fillRect(0, 0, b, h * 0.3);
  g.fillStyle = "#6d9a4a"; g.fillRect(0, h * 0.27, b, h * 0.05);
  g.fillStyle = "#8a6a4a"; g.fillRect(0, h * 0.32, b, h * 0.68);
  g.fillStyle = "#2b2622"; g.fillRect(b * 0.2, h * 0.45, b * 0.6, h * 0.39);
  g.fillStyle = "#555"; g.fillRect(b * 0.2, h * 0.82, b * 0.6, h * 0.02);
  return c.toDataURL("image/png");
}, [b, h]);

test("verktyget lägger bild och lager, bladet och avritningen bär dem",
  async ({ page, request, baseURL }, info) => {
    await page.goto("/");
    await hydrerad(page);

    const bild = await malning(page, 1280, 720);
    const png = info.outputPath("tunnel.png");
    const lager = info.outputPath("lager.json");
    writeFileSync(png, Buffer.from(bild.split(",")[1], "base64"));
    writeFileSync(lager, JSON.stringify(LAGER));

    const dok = await (await request.post("/api/dokument",
      { data: { dokument: papper(), status: "godkant" } })).json();
    const verktyg = (...arg) => execFileSync(PY,
      ["tools/bildlager.py", "--server", baseURL, ...arg.map(String)],
      { cwd: ROT, encoding: "utf-8", env: { ...process.env, PYTHONIOENCODING: "utf-8" } });
    verktyg("bild", dok.id, 2, png);
    verktyg("satt", dok.id, 2, lager);
    expect(verktyg("visa", dok.id)).toMatch(/uppg2\s+bild\s+lager 5/);

    await page.reload();
    await hydrerad(page);
    await page.getByRole("tab", { name: "Planering" }).click();
    const i = await page.evaluate(id =>
      window.Dokument.sparade().findIndex(d => d.id === id), dok.id);
    expect(i).toBeGreaterThanOrEqual(0);
    await page.evaluate(i => window.Dokument.visa(i), i);
    await expect(page.locator("#forhandsskal")).toBeVisible();

    const kort = page.locator('#fh-ark [data-el="uppg2"]').first();
    const lada = kort.locator(".bildlager");
    await expect(lada.locator("svg.blsvg")).toBeVisible();
    await expect(lada.locator(".bllapp")).toHaveCount(5);
    await expect(lada.locator(".bllapp.blram")).toHaveCount(1);
    // Matematiken är KaTeX, inte råa dollartecken.
    await expect(lada.locator(".bllapp .katex").first()).toBeVisible();
    expect(await lada.locator(".bllapp").allTextContents())
      .not.toContain(expect.stringContaining("$"));
    // Linjerna: markytan, två pilar och måttlinjen, med var sin kontur och
    // tre spetsar (två på måttet) plus måttets två tvärstreck.
    expect(await lada.locator("svg line").count()).toBe(2 * (1 + 2 + 1 + 2));
    expect(await lada.locator("svg polygon").count()).toBe(2 * 4);
    // Bildens proportioner ur PNG-huvudet: 1280 × 720.
    expect(await lada.locator("svg").getAttribute("viewBox")).toBe("0 0 1000 563");

    // Lagret täcker bilden exakt, inte rutan runt den.
    const [rb, rs] = await Promise.all([lada.locator("img").boundingBox(),
                                        lada.locator("svg").boundingBox()]);
    for (const k of ["x", "y", "width", "height"]) expect(Math.abs(rb[k] - rs[k])).toBeLessThan(1.5);
    // Uppgiften utan bild får inget lager.
    await expect(page.locator('#fh-ark [data-el="uppg1"] .bildlager')).toHaveCount(0);

    await kort.screenshot({ path: join(ROT, "bildlager-skarm.png") });

    /* Avritningen, så som godkännandet gör den (blad-bild.js). Samma papper
       med och utan lager: lagret ska synas som mörka pixlar i den tryckta
       bilden, och utan lager ska rutan vara precis som förut. */
    const ut = await page.evaluate(async ([id, bild]) => {
      const v = window.Dokument.sparade().find(d => d.id === id);
      const med = Object.assign(JSON.parse(JSON.stringify(v)), { bilder: { uppg2: bild } });
      const utan = Object.assign(JSON.parse(JSON.stringify(med)), { bildlager: {} });
      const a = (await window.BladBild.dokument(med, { skala: 1 })).uppgift[0];
      const b = (await window.BladBild.dokument(utan, { skala: 1 })).uppgift[0];
      const pixlar = src => new Promise(ja => {
        const im = new Image();
        im.onload = () => {
          const c = document.createElement("canvas");
          c.width = im.width; c.height = im.height;
          const g = c.getContext("2d"); g.drawImage(im, 0, 0);
          ja(g.getImageData(0, 0, c.width, c.height).data);
        };
        im.src = src;
      });
      const [pa, pb] = await Promise.all([pixlar(a), pixlar(b)]);
      let olika = 0;
      for (let k = 0; k < pa.length; k += 4) {
        if (Math.abs(pa[k] - pb[k]) + Math.abs(pa[k + 1] - pb[k + 1]) + Math.abs(pa[k + 2] - pb[k + 2]) > 90) olika++;
      }
      // Utan lager: bilden ligger direkt i rutan, ingen låda runt den.
      const bo = document.createElement("div");
      bo.style.cssText = "position:fixed;left:-30000px;top:0;width:900px";
      document.body.appendChild(bo);
      window.Blad.rita(bo, utan);
      const img = bo.querySelector('[data-el="uppg2"] .prbild img');
      const direkt = !!img && img.parentElement.classList.contains("prbild");
      bo.remove();
      return { a, olika, direkt, lika: pa.length === pb.length };
    }, [dok.id, bild]);
    writeFileSync(join(ROT, "bildlager-avritning.png"), Buffer.from(ut.a.split(",")[1], "base64"));
    expect(ut.lika).toBe(true);
    expect(ut.olika).toBeGreaterThan(1500);
    expect(ut.direkt).toBe(true);
  });

test("plåten får lagret, och proportionerna rättas när bilden landat",
  async ({ page }) => {
    await page.goto("/");
    await hydrerad(page);
    const bild = await malning(page, 800, 600);   // 4:3, inte plåtens 16:9
    await page.route("**/api/platar/**", route => route.fulfill({
      status: 200, contentType: "image/png", body: Buffer.from(bild.split(",")[1], "base64") }));
    const ut = await page.evaluate(async dok => {
      const bo = document.createElement("div");
      bo.style.cssText = "position:fixed;left:0;top:0;width:900px";
      document.body.appendChild(bo);
      window.Blad.rita(bo, dok);
      const lada = bo.querySelector('[data-el="uppg2"] .prplat .bildlager');
      const fore = lada && lada.querySelector("svg").getAttribute("viewBox");
      const img = lada && lada.querySelector("img");
      if (img && !img.complete) await new Promise(ja => img.addEventListener("load", ja, { once: true }));
      await new Promise(ja => requestAnimationFrame(() => requestAnimationFrame(ja)));
      const svg = lada && lada.querySelector("svg");
      const r1 = img.getBoundingClientRect(), r2 = svg.getBoundingClientRect();
      const ut = { fore, efter: svg.getAttribute("viewBox"), lappar: lada.querySelectorAll(".bllapp").length,
                   dw: Math.abs(r1.width - r2.width), dh: Math.abs(r1.height - r2.height),
                   andel: r1.width / lada.closest(".prbild").getBoundingClientRect().width };
      bo.remove();
      return ut;
    }, (() => {
      const v = papper();
      v.uppgifter[1].scen = { ...TUNNEL, plat: "a-40-gangtunnel.png" };
      v.bildlager = { uppg2: LAGER };
      return v;
    })());
    expect(ut.fore).toBe("0 0 1000 563");
    expect(ut.efter).toBe("0 0 1000 750");
    expect(ut.lappar).toBe(5);
    expect(ut.dw).toBeLessThan(1.5);
    expect(ut.dh).toBeLessThan(1.5);
    // Plåten är fortfarande 70 % av rutan, som på pappret.
    expect(ut.andel).toBeGreaterThan(0.66);
    expect(ut.andel).toBeLessThan(0.74);
  });
