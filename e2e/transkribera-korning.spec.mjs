// Plan A3: e2e för transkriberingsguidens steg 3 i Svelte-frontenden
// (/next/) — själva körningen. Kör mot den riktiga backenden med fejkad
// inferens (e2e/serve_test_app.py, där _run_transcribe_subprocess ersatts av
// en fejk som emitterar deterministiska logg- och progress-events); /api/sample
// och /api/models är oberörda av fejkarna och svarar på riktigt.
//
// TÄCKER: att starten tar guiden till steg 3 med stegindikatorn på
// Transkribering, att körningen når status Klar med 100 % och klarbeskedet
// (med de filer som faktiskt skrevs), att loggen fälls ut och bär både
// klientens start- och slutrad OCH serverns egna rader däremellan, samt att ett
// avbrott landar i avbrutet-kortet med Återuppta OCH skickar en verklig POST
// till /api/transcribe/cancel — den POSTen är inte bokföring, det är den som
// avslutar subprocessen på servern och släpper GPU:n (app.js:2270-2276).
//
// TÄCKER OCKSÅ läckgrenen i progressanimeringen: att baren fortsätter krypa
// framåt inom fasen mellan serverhändelser. Det är planens enda medvetna
// beteendedivergens mot gamla appen (`real - disp > 0.01` i stället för
// `real > disp`, app.js:2300) och skulle annars sakna assertion helt.
//
// TÄCKER OCKSÅ kökedjan: att klarbeskedet HÅLLS TILLBAKA så länge en post i
// kön fortfarande väntar (nagotKvar), och att done-grenens setTimeout-kedja
// verkligen startar nästa post. Miljön har bara EN riktig mediefil
// (/api/sample), så post 2 är `skadad_inspelning.m4a` — den felar direkt på
// servern ("Filen finns inte", app/web/server.py:524). Det räcker: kedjan
// behöver bara STARTA post 2 för att vara observerbar.
//
// TÄCKER INTE överlämningen till Inspelningar: den vyn är inte migrerad än,
// så guiden stannar medvetet kvar på steg 3 och säger det i klartext i
// stället för att navigera till en platshållare (se plan A3).
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
 * Väntar in startknappen och trycker på den. /api/models gör en riktig
 * hårdvaruskanning även i fejkläge, så vi väntar in katalogen i stället för en
 * fast paus. Svenska är förvalt talat språk, och KB-Whisper large (svenska) är
 * den enda riktigt installerade modellen i den här miljön — bara det språket
 * kan göra knappen klickbar. Etiketten byter form vid flera filer
 * (Installningar.svelte:12-20), därför är den en parameter.
 */
async function startaKon(page, etikett = "Starta transkribering") {
  const start = page.getByRole("button", { name: etikett, exact: true });
  await expect(start).toBeVisible({ timeout: 20_000 });
  await expect(start).toBeEnabled({ timeout: 20_000 });
  await start.click();
}

/** Köar exemplet och startar. */
async function startaExempel(page) {
  await page.getByRole("button", { name: "ett exempel", exact: true }).click();
  await startaKon(page);
}

/**
 * Bromsar /api/transcribe-strömmen så testet styr den händelse för händelse.
 * Fejkkörningen tar ~170 ms — för snabbt både för att hinna klicka Avbryt och
 * för att hinna läsa av baren mitt i körningen.
 *
 * page.route räcker inte hela vägen: route.fulfill kan bara skicka en FÄRDIG
 * kropp, och streamPost (frontend/src/lib/api.js:90) översätter en ström som
 * tar slut utan 'done'/'error' till ett fel — en fulfillad kropp slår alltså
 * över körningen i felläge i stället för att låta den ligga kvar i 'running'.
 * Därför dubbleras window.fetch, med en ReadableStream som testet matar i egen
 * takt via window.__e2eStrom.skicka(ev). Bara /api/transcribe fångas; allt
 * annat — inte minst avbrotts-POSTen, som ska synas i nätverksloggen — går till
 * den riktiga fetchen.
 */
async function bromsaStrommen(page) {
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
}

/** Talet ur kortets "Klart NN %". */
async function lasProcent(procent) {
  return Number(((await procent.textContent()) || "").replace(/\D/g, ""));
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

  // 5) Loggen är ihopfälld från början och fälls ut på klick.
  const loggknapp = page.getByRole("button", { name: "Logg" });
  await expect(loggknapp).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator("ol.loggrader")).toHaveCount(0);
  await loggknapp.click();
  await expect(loggknapp).toHaveAttribute("aria-expanded", "true");
  const rader = page.locator("ol.loggrader li");
  // Ramraderna skriver KLIENTEN själv (actions.js: startRun respektive
  // done-grenen) — de bevisar bara att körningen började och slutade.
  await expect(rader.first()).toContainText("Startar transkribering");
  await expect(rader.last()).toContainText("Färdig på");
  // Mellanraderna är SERVERNS. Det är de som bevisar att strömmens log-events
  // verkligen fyllde på loggen UNDER körningen; utan dem vore testet grönt även
  // om fejken slutade emittera log-events (e2e/serve_test_app.py:63 och 70).
  // Antalet assertas inte: fejken körs en gång per delband i "ärlig
  // progress"-refaktorn, så raderna dyker upp lika många gånger som det finns
  // pass — det är förekomsten, inte antalet, som är beviset.
  await expect(rader.filter({ hasText: "Transkriberar (fejk)" }).first()).toBeVisible();
  await expect(rader.filter({ hasText: /\] Klar\.$/ }).first()).toBeVisible();

  // 6) Inga konsolfel under hela flödet.
  expect(errors, errors.join("\n")).toEqual([]);
});

test("Transkribera (/next/): avbrott stoppar körningen och erbjuder Återuppta", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await bromsaStrommen(page);

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

test("Transkribera (/next/): baren kryper vidare mellan serverhändelser", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Läckgrenen i korning.js är planens enda medvetna beteendedivergens mot
  // gamla appen: ikappvillkoret är `real - disp > 0.01`, inte `real > disp`
  // (app.js:2300). Skillnaden är inte kosmetisk. `disp` konvergerar
  // asymptotiskt mot `real` UNDERIFRÅN och når det aldrig, så med
  // originalvillkoret blir läckgrenen onåbar och baren fryser bitvis exakt
  // mellan serverhändelser — precis det animeringen finns för att hindra.
  // Avbrottsspecen kan inte skilja villkoren åt: den skickar pct 100, som
  // klampas till 99, och båda landar på "Klart 99 %". Det här testet finns för
  // att en återgång till `real > disp` ska FALLA.
  await bromsaStrommen(page);

  await page.goto("/next/");
  await kravExempel(page);
  await startaExempel(page);

  const procent = page.locator(".kort .topp .matt").filter({ hasText: "Klart" });
  await expect(page.locator(".kort .status")).toHaveText("Kör");

  // EN enda serverhändelse, och sedan tystnad — exakt det läge som fryser
  // baren i gamla appen.
  await page.evaluate(() => window.__e2eStrom.skicka({ type: "progress", pct: 30 }));

  // Först hinner ikapp-grenen upp baren till serverns 30 %. Väntan är på ">= 29"
  // och inte på exakt "Klart 30 %": med den RÄTTA koden passerar baren 30 och
  // fortsätter, så 30 står bara kvar en halvsekund. Att kräva den rutan vore
  // ett kapplöpningstest — och just den rutan är dessutom det enda de båda
  // villkoren är överens om.
  await expect
    .poll(() => lasProcent(procent), { timeout: 20_000 })
    .toBeGreaterThanOrEqual(29);
  const fore = await lasProcent(procent);

  // Utan en enda ny serverhändelse ska baren fortsätta framåt inom fasen.
  await page.waitForTimeout(3000);
  const efter = await lasProcent(procent);

  expect(
    efter,
    "Baren frös på serverns senaste värde (" + fore + " % → " + efter + " %) i " +
      "stället för att krypa vidare. Läckgrenen i korning.js är onåbar — är " +
      "ikappvillkoret återställt till gamla appens `real > disp`?",
  ).toBeGreaterThanOrEqual(35);

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Transkribera (/next/): kökedjan startar nästa post och håller tillbaka klarbeskedet", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Fönstret där post 1 är klar och post 2 fortfarande väntar är bara 800 ms
  // långt (kedjans setTimeout i actions.js). En stickprovsassertion mitt i det
  // fönstret vore ett kapplöpningstest, så i stället installeras — före
  // navigeringen — en MutationObserver som läser av VARJE DOM-mutation. Samma
  // slags vakt som avbrottstestet ovan använder.
  //
  //   brott:      klarbeskedet fanns medan en köpost stod på "Väntar" —
  //               alltså nagotKvar-grinden inverterad eller borta.
  //   vantelage:  antalet mutationer där körningen sa "Klar" OCH en post
  //               stod kvar på "Väntar" — beviset att testet verkligen
  //               passerade genom det tillstånd grinden gäller, i stället för
  //               att godkännas tomt.
  await page.addInitScript(() => {
    window.__e2eKedja = { brott: [], vantelage: 0 };
    const las = (el) => (el?.textContent || "").replace(/\s+/g, " ").trim();
    const kolla = () => {
      const laget = las(document.querySelector(".kort .status"));
      const ko = [...document.querySelectorAll(".ko .qstatus")].map(las);
      const vantar = ko.includes("Väntar");
      if (!vantar) return;
      if (document.querySelector(".klar-besked")) {
        window.__e2eKedja.brott.push(laget + " / kö: " + ko.join(","));
      }
      if (laget === "Klar") window.__e2eKedja.vantelage++;
    };
    const start = () => new MutationObserver(kolla).observe(document.body, {
      subtree: true, childList: true, characterData: true,
    });
    if (document.body) start();
    else document.addEventListener("DOMContentLoaded", start);
  });

  await page.goto("/next/");
  await kravExempel(page);

  // Två poster, i den ordningen: exemplet blir klart och kedjan tar vid;
  // skadad_inspelning.m4a finns inte på disk och felar direkt på servern.
  // Ordningen är bärande — kedjan sitter i done-grenen, så en felande post 1
  // skulle aldrig starta post 2. Att köa flyttar guiden till steg 2, därför
  // tar "Lägg till fler" oss tillbaka till steg 1 för den andra posten.
  await page.getByRole("button", { name: "ett exempel", exact: true }).click();
  await page.getByRole("button", { name: "Lägg till fler", exact: true }).click();
  await page.getByRole("button", { name: "skadad_inspelning.m4a", exact: true }).click();
  await expect(page.locator("ul.ko li")).toHaveCount(2);

  await startaKon(page, "Starta · 2 filer");

  const kortFil = page.locator(".kort .fil");
  const status = page.locator(".kort .status");
  await expect(kortFil).toHaveText("Mamma waw isolerad.wav");

  // Kedjan tar vid: kortet byter till post 2, som felar på servern. Utan
  // setTimeout-kedjan i done-grenen står kortet kvar på post 1 för alltid.
  await expect(kortFil).toHaveText("skadad_inspelning.m4a", { timeout: 30_000 });
  await expect(status).toHaveText("Fel", { timeout: 15_000 });

  // Post 1 blev alltså verkligen klar innan kedjan gick vidare.
  await expect(page.getByText("Kö — 1 av 2 klara")).toBeVisible();

  // Klarbeskedet hör till en TÖMD kö och får inte finnas här — varken nu
  // (post 2 felade) eller under väntefönstret (vakten nedan).
  await expect(page.getByText("Klart — lektionen är sparad.")).toHaveCount(0);

  const kedja = await page.evaluate(() => window.__e2eKedja);
  expect(
    kedja.brott,
    "Klarbeskedet visades medan en köpost fortfarande väntade: " + kedja.brott.join(" | "),
  ).toEqual([]);
  expect(
    kedja.vantelage,
    "Testet passerade aldrig tillståndet \"post 1 klar, post 2 väntar\" — " +
      "vakten ovan hade inget att fånga och assertionen vore tom.",
  ).toBeGreaterThan(0);

  expect(errors, errors.join("\n")).toEqual([]);
});
