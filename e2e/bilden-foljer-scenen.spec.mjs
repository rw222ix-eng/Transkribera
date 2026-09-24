import { expect, test } from "@playwright/test";

/* BILDEN HÖR TILL SCENEN, INTE TILL NUMRET (2026-09-24 kväll)
 *
 * Lärarens egna bilder bor i dokumentets `bilder` under uppgiftens nummer.
 * Blad 135 skrevs om i ett varv: uppgift 3 blev en vattenslang, och bilden på
 * en planka stod kvar ovanför den nya texten. Nu sparas scenen bilden målades
 * för i `bildscen`, och en bild vars scen uppgiften inte längre har ritas inte.
 * Bilder utan märke (äldre papper) ritas som förut.
 */

const SCHEMA = { schema: [], lov: [], poster: [] };
// En pixel, PNG.
const PIXEL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAf"
  + "FcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";

const SLANG = { begrepp: "vattenslang", filnamn: "a-03-vattenslang",
  scene: "SCENE. A green garden hose on a lawn.\nIntended use: längd." };

function papper(bildscen) {
  return {
    typ: "Arbetsblad", moment: "Inför provet", klass: "BA26B",
    kurs: "Matematik, nivå 1a", datum: "2026-09-30", tid: "",
    gy: [], kalla: false, kallor: [], inst: { antal: 1, niva: "E-nivå" },
    bilder: { uppg1: PIXEL }, ...(bildscen === undefined ? {} : { bildscen }),
    referenser: [], forlaga: null, resultat: null, fokus: "",
    kontext: "start", niva: false, svarighet: 0, andrat: [],
    provId: 12, uppgifter: [
      { nr: 1, p: 2, t: "En vattenslang är 25 m lång. Hur lång är halva?",
        f: "12,5 m", scen: SLANG },
    ],
  };
}

const rad = (id, dok) => ({
  id, status: "godkant", markor: 0, sort: id, foljd: null,
  versioner: [dok], dokument: { ...dok, id },
});

async function fejka(page, sparade) {
  const json = (route, kropp) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(kropp) });
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade, utkast: null }));
  await page.route("**/api/dokument/**", route => json(route, { ok: true, id: 1 }));
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern() && window.Dokument);

async function bildenSyns(page, dok) {
  await fejka(page, [rad(1, dok)]);
  await page.goto("/");
  await hydrerad(page);
  await page.getByRole("tab", { name: "Planering" }).click();
  await page.evaluate(() => window.Dokument.visa(0));
  await expect(page.locator("#forhandsskal")).toBeVisible();
  await expect(page.locator('#fh-ark [data-el="uppg1"]').first()).toBeVisible();
  return page.locator('#fh-ark [data-el="uppg1"] .prbild img').count();
}

test("en bild målad för en annan scen ritas inte", async ({ page }) => {
  expect(await bildenSyns(page, papper({ uppg1: "a-03-planka" }))).toBe(0);
});

test("bilden till uppgiftens egen scen ritas", async ({ page }) => {
  expect(await bildenSyns(page, papper({ uppg1: "a-03-vattenslang" })))
    .toBeGreaterThan(0);
});

test("en bild utan märke ritas som förut", async ({ page }) => {
  expect(await bildenSyns(page, papper(undefined))).toBeGreaterThan(0);
});

test("märket är scenens filnamn, och en uppgift utan scen märks med texten",
  async ({ page }) => {
    await fejka(page, []);
    await page.goto("/");
    await hydrerad(page);
    const ut = await page.evaluate(scen => [
      window.Blad.scenNyckel({ nr: 1, t: "x", scen }),
      window.Blad.scenNyckel({ nr: 2, t: "Lös  ekvationen" }),
      window.Blad.bildInaktuell({ bildscen: { uppg1: "a-03-planka" },
        uppgifter: [{ nr: 1, scen }] }, "uppg1"),
      window.Blad.bildInaktuell({ bildscen: {}, uppgifter: [] }, "forsatt"),
    ], SLANG);
    expect(ut).toEqual(["a-03-vattenslang", "Lös ekvationen", true, false]);
  });

test("den inaktuella bilden säger varför i canvas, men inte i trycket",
  async ({ page }) => {
    await fejka(page, []);
    await page.goto("/");
    await hydrerad(page);
    const ut = await page.evaluate(dok => {
      const bo = document.createElement("div");
      bo.style.cssText = "position:fixed;left:-30000px;top:0;width:900px";
      document.body.appendChild(bo);
      window.Blad.rita(bo, dok);
      const rad = bo.querySelector('[data-el="uppg1"] .prinaktuell');
      const ut = { rad: rad ? rad.textContent : "", img: bo.querySelectorAll('[data-el="uppg1"] img').length };
      bo.remove();
      return ut;
    }, papper({ uppg1: "a-03-planka" }));
    expect(ut.rad).toContain("äldre version");
    expect(ut.img).toBe(0);
  });

test("intervallets minus efter «]» är ett förtecken", async ({ page }) => {
  await fejka(page, []);
  await page.goto("/");
  await hydrerad(page);
  const tex = await page.evaluate(() => {
    const fangat = [];
    const org = window.katex.render;
    window.katex.render = function (t, el, o) { fangat.push(t); return org.call(this, t, el, o); };
    const d = document.createElement("div");
    d.innerHTML = '<span class="mat" data-tex="]-3,\ 4]"></span>';
    document.body.appendChild(d);
    try { window.Matte && window.Matte.satt && window.Matte.satt(d); } finally {
      window.katex.render = org; d.remove();
    }
    return fangat;
  });
  expect(tex.some(t => t.includes("]{-}3"))).toBe(true);
});
