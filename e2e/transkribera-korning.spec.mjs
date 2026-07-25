// Plan A3: e2e för transkriberingsguidens steg 3 i Svelte-frontenden
// (/next/) — själva körningen. Kör mot den riktiga backenden med fejkad
// inferens (e2e/serve_test_app.py, där _run_transcribe_subprocess ersatts av
// en fejk som emitterar deterministiska logg- och progress-events); /api/sample
// och /api/models är oberörda av fejkarna och svarar på riktigt.
//
// TÄCKER: att starten tar guiden till steg 3 med stegindikatorn på
// Transkribering, att körningen når status Klar med 100 % och klarbeskedet
// (med de filer som faktiskt skrevs), att loggen fälls ut och bär både
// startraden och slutraden, samt att ett avbrott landar i avbrutet-kortet med
// Återuppta OCH skickar en verklig POST till /api/transcribe/cancel — den
// POSTen är inte bokföring, det är den som avslutar subprocessen på servern
// och släpper GPU:n (app.js:2270-2276).
//
// TÄCKER INTE överlämningen till Inspelningar: den vyn är inte migrerad än,
// så guiden stannar medvetet kvar på steg 3 och säger det i klartext i
// stället för att navigera till en platshållare (se plan A3). TÄCKER INTE
// heller kökedjan med flera filer (startRun startar nästa post efter 800 ms) —
// miljön har bara EN riktig mediefil att köa (/api/sample), och ett påhittat
// filnamn skulle ta felvägen i stället för att bli klart.
import { test, expect, failOnConsoleError } from "./helpers/app";

/** Förkontroll: utan demofilen blir felet annars en obegriplig timeout. */
async function kravExempel(page) {
  const sample = await page.request.get("/api/sample");
  expect(
    sample.status(),
    'Saknad testfixtur: "Mamma waw isolerad.wav" i repo-roten (se e2e/serve_test_app.py). ' +
      "/api/sample svarade " + sample.status() + ".",
  ).toBe(200);
  return sample.json();
}

/**
 * Köar exemplet och väntar in startknappen. /api/models gör en riktig
 * hårdvaruskanning även i fejkläge, så vi väntar in katalogen i stället för en
 * fast paus. Svenska är förvalt talat språk, och KB-Whisper large (svenska) är
 * den enda riktigt installerade modellen i den här miljön — bara det språket
 * kan göra knappen klickbar.
 */
async function startaExempel(page) {
  await page.getByRole("button", { name: "ett exempel", exact: true }).click();
  const start = page.getByRole("button", { name: "Starta transkribering", exact: true });
  await expect(start).toBeVisible({ timeout: 20_000 });
  await expect(start).toBeEnabled({ timeout: 20_000 });
  await start.click();
}

test("Transkribera (/next/): körningen blir klar, med filer och logg", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.goto("/next/");
  const exempel = await kravExempel(page);
  // Filstammen härleds ur serverns eget svar i stället för att hårdkodas, så
  // filassertionen nedan följer med om fixturen någonsin byter namn.
  const stam = exempel.name.replace(/\.[^.]+$/, "");

  await startaExempel(page);

  // 1) Starten tar guiden till steg 3, och stegindikatorn säger det.
  const aktivtSteg = page.locator("ol.steg li.aktiv");
  await expect(aktivtSteg).toHaveAttribute("aria-current", "step");
  await expect(aktivtSteg).toContainText("Transkribering");
  await expect(page.getByRole("heading", { name: /Bearbetar/ })).toBeVisible();

  // 2) Körningen går i mål: statusen säger Klar och baren når 100 %.
  //    dispProgress animeras mjukt mot 100 efter 'done' (korning.js), så
  //    procenten väntas in i stället för att läsas av direkt.
  const status = page.locator(".kort .status");
  const procent = page.locator(".kort .topp .matt").filter({ hasText: "Klart" });
  await expect(status).toHaveText("Klar", { timeout: 30_000 });
  await expect(procent).toHaveText("Klart 100 %", { timeout: 15_000 });

  // 3) Klarbeskedet: lektionen är sparad, och det står rakt ut att
  //    Inspelningar kommer senare — guiden navigerar alltså inte någonstans.
  await expect(page.getByText("Klart — lektionen är sparad.")).toBeVisible();
  await expect(page.getByText(/Inspelningar — där lektionen går att öppna/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Transkribera något mer" })).toBeVisible();

  // 4) Filerna som faktiskt skrevs listas med sina NAMN. Servern skickar dem
  //    som objekt (app/output_store.py:_file_entry) — en rad som säger
  //    "[object Object]" är exakt det felet den här assertionen finns för.
  const filer = page.locator("ul.filer li");
  await expect(filer.filter({ hasText: stam + ".srt" })).toHaveCount(1);
  await expect(filer.filter({ hasText: "[object Object]" })).toHaveCount(0);

  // 5) Loggen är ihopfälld från början och fälls ut på klick. Den ska bära
  //    både startraden och slutraden — alltså ha fyllts på UNDER körningen.
  const loggknapp = page.getByRole("button", { name: "Logg" });
  await expect(loggknapp).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator("ol.loggrader")).toHaveCount(0);
  await loggknapp.click();
  await expect(loggknapp).toHaveAttribute("aria-expanded", "true");
  const rader = page.locator("ol.loggrader li");
  await expect(rader.first()).toContainText("Startar transkribering");
  await expect(rader.last()).toContainText("Färdig på");

  // 6) Inga konsolfel under hela flödet.
  expect(errors, errors.join("\n")).toEqual([]);
});

test("Transkribera (/next/): avbrott stoppar körningen och erbjuder Återuppta", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Fejkkörningen tar ~170 ms — för snabbt både för att hinna klicka Avbryt
  // och för att hinna läsa av baren mitt i körningen. Strömmen måste bromsas.
  //
  // page.route räcker inte hela vägen: route.fulfill kan bara skicka en
  // FÄRDIG kropp, och streamPost (frontend/src/lib/api.js:90) översätter en
  // ström som tar slut utan 'done'/'error' till ett fel — en fulfillad kropp
  // slår alltså över körningen i felläge i stället för att låta den ligga kvar
  // i 'running'. Därför dubbleras window.fetch, med en ReadableStream som
  // testet matar i egen takt. Bara /api/transcribe fångas; allt annat — inte
  // minst avbrotts-POSTen, som ska synas i nätverksloggen — går till den
  // riktiga fetchen.
  await page.addInitScript(() => {
    const riktig = window.fetch.bind(window);
    const kodare = new TextEncoder();
    let styrning = null;
    window.__e2eStrom = {
      skicka(ev) {
        styrning.enqueue(kodare.encode("data: " + JSON.stringify(ev) + "\n\n"));
      },
    };
    window.fetch = (input, init) => {
      const url = String(typeof input === "string" ? input : input.url).split("?")[0];
      if (/\/api\/transcribe$/.test(url)) {
        return Promise.resolve(new Response(
          new ReadableStream({ start(c) { styrning = c; } }),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ));
      }
      return riktig(input, init);
    };
  });

  await page.goto("/next/");
  await kravExempel(page);
  await startaExempel(page);

  const status = page.locator(".kort .status");
  const procent = page.locator(".kort .topp .matt").filter({ hasText: "Klart" });
  await expect(status).toHaveText("Kör");

  // Vakt för "100 % betyder färdig". Den installeras INNAN progressen skickas
  // och läser av varje DOM-mutation i kortets topprad, så den ser varje ruta
  // baren ritar — inte bara de stunder testet råkar läsa av. En stickprovs-
  // assertion skulle missa en bar som passerar 100 på väg någonstans.
  await page.evaluate(() => {
    window.__e2eBrott = [];
    const topp = document.querySelector(".kort .topp");
    const las = (el) => (el?.textContent || "").replace(/\s+/g, " ").trim();
    new MutationObserver(() => {
      const laget = las(document.querySelector(".kort .status"));
      const matt = [...document.querySelectorAll(".kort .topp .matt")].map(las);
      if (matt.includes("Klart 100 %") && laget !== "Klar") {
        window.__e2eBrott.push(laget + " / Klart 100 %");
      }
    }).observe(topp, { subtree: true, childList: true, characterData: true });
  });

  // Servern påstår 100 % INNAN den är klar. Loggraden bevisar samtidigt att
  // klienten verkligen läser strömmen.
  await page.evaluate(() => {
    window.__e2eStrom.skicka({ type: "log", msg: "Transkriberar (fejk) ..." });
    window.__e2eStrom.skicka({ type: "progress", pct: 100 });
  });

  // Baren rör sig — men stannar under 100, för körningen är inte klar.
  await expect(procent).toHaveText("Klart 99 %", { timeout: 10_000 });
  await expect(status).toHaveText("Kör");

  // Avbryt. POSTen fångas ur NÄTVERKSLOGGEN (inte ur koden), och väntan
  // registreras före klicket så den inte kan mättas av något äldre anrop.
  const avbrottsPost = page.waitForRequest(
    (r) => r.url().includes("/api/transcribe/cancel") && r.method() === "POST",
  );
  await page.getByRole("button", { name: "Avbryt", exact: true }).click();
  await avbrottsPost;

  // Avbrutet-kortet, med vägen tillbaka in i körningen.
  await expect(status).toHaveText("Avbruten");
  await expect(page.getByText("Transkriberingen avbröts")).toBeVisible();
  await expect(
    page.getByText("Du stoppade körningen — inget sparades. Återuppta där du var, eller byt fil."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Återuppta", exact: true })).toBeEnabled();

  // Avbrottet fryser baren (stopProgressAnim) — den ska stå kvar under 100,
  // och klarbeskedet hör bara till en färdig körning.
  await expect(procent).toHaveText("Klart 99 %");
  await expect(page.getByText("Klart — lektionen är sparad.")).toHaveCount(0);

  // Vakten får inte ha sett en enda ruta där baren sa 100 % utan att
  // körningen var klar.
  const brott = await page.evaluate(() => window.__e2eBrott);
  expect(brott, "Baren visade 100 % innan körningen var klar: " + brott.join(", ")).toEqual([]);

  expect(errors, errors.join("\n")).toEqual([]);
});
