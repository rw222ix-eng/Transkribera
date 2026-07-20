import { test, expect, failOnConsoleError } from "../helpers/app";

// Fas 4/5 + enad byggpanel (2026-07-19): typväljaren Tavla|Prov|Arbetsblad,
// kurschips, generera → markera uppgift → gemensam chatt → godkänn → PDF,
// allt mot fejkade LLM/PDF-motorer men riktiga rutter, DB och artefakter.

test("Prov: byggpanel → generera → markerad uppgift via chatten → godkänn → PDF (fejk)", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Planering", exact: true }).click();

  // Typväljaren: Prov — typspecifika fält (provtid, Del B/C) visas.
  await page.getByRole("group", { name: "Dokumenttyp" })
    .getByRole("button", { name: "Prov", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Nytt prov" })).toBeVisible();
  await expect(page.getByLabel("Provtid (minuter)")).toBeVisible();

  // Delade fält: kurschip → innehållspunkter (seedade ur bundlad JSON),
  // grupperade per Gy25-rubrik som fälls ut vid klick.
  await page.getByRole("button", { name: "Nivå 2b", exact: true }).click();
  const grupp = page.getByRole("button", { name: /Aritmetik, algebra/ }).first();
  await expect(grupp).toBeVisible({ timeout: 10000 });
  await grupp.click();
  const chip = page.getByRole("button", { name: /andragradsekvationer/ }).first();
  await expect(chip).toBeVisible();
  await chip.click();
  await expect(chip).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("button", { name: "Skriv provet" }).click();

  // Resultat: balansmätare + kravgränser + numrerade uppgifter.
  // .first(): titeln syns både i provkortet och i arkivraden (utkast listas).
  await expect(page.getByText("Prov — Matematik, nivå 2b").first()).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/Totalt 20 p/)).toBeVisible();
  await expect(page.getByText(/Kravgränser: E 5/)).toBeVisible();
  await expect(page.getByText("Uppgift 1", { exact: true })).toBeVisible();
  await expect(page.getByText("Uppgift 6", { exact: true })).toBeVisible();

  // Elementmarkering: klick på uppgift 1 → chip vid chatten → riktad
  // omgenerering via den gemensamma chatten ger ny version.
  await page.locator('[data-key="ex-u-1"]').click();
  await expect(page.locator('[data-key="ex-u-1"]')).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("Ändringen gäller")).toBeVisible();
  await expect(page.getByText("Uppgift 1").nth(1)).toBeVisible();   // chippen
  await page.getByLabel("Ändra provet").fill("gör den svårare");
  await page.getByRole("button", { name: "Ändra", exact: true }).click();
  await expect(page.getByText(/\(ändrad\)/)).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("Version 2 av 2")).toBeVisible();
  // Markeringen rensas efter skick.
  await expect(page.getByText("Ändringen gäller")).toHaveCount(0);

  // Godkänn → PDF kompileras (fejkad motor) och kan öppnas.
  await page.getByRole("button", { name: "Godkänn & skapa PDF" }).click();
  await expect(page.getByText(/PDF skapad:/)).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole("button", { name: "Öppna PDF" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Öppna i Overleaf" })).toBeVisible();

  const examId = await page.evaluate(() => (window as any).S.exam.id);
  const pdf = await page.request.get(`/api/exams/${examId}/pdf`);
  expect(pdf.status()).toBe(200);
  expect((await pdf.body()).subarray(0, 4).toString()).toBe("%PDF");
  const tex = await page.request.get(`/api/exams/${examId}/tex`);
  expect(tex.status()).toBe(200);
  expect(await tex.text()).toContain("\\documentclass");

  expect(errors, errors.join("\n")).toEqual([]);
});

test("Arbetsblad: typväljaren döljer provfälten, facit-mall, arkivet listar posten (fejk)", async ({ page }) => {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Planering", exact: true }).click();

  await page.getByRole("group", { name: "Dokumenttyp" })
    .getByRole("button", { name: "Arbetsblad", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Nytt arbetsblad" })).toBeVisible();
  // Provspecifika fält visas inte för arbetsblad.
  await expect(page.getByLabel("Provtid (minuter)")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Del B/C" })).toHaveCount(0);

  const kurschip = page.getByRole("button", { name: "Nivå 2b", exact: true });
  await kurschip.click();
  // Invänta omrenderingen efter kursvalet innan CTA:n klickas — annars kan
  // klicket träffa en handler-id som just bytts ut av morphdom.
  await expect(kurschip).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Skriv arbetsbladet" }).click();
  await expect(page.getByText("Arbetsblad — Matematik, nivå 2b").first()).toBeVisible({ timeout: 15000 });

  await page.getByRole("button", { name: "Godkänn & skapa PDF" }).click();
  await expect(page.getByText(/PDF skapad:/)).toBeVisible({ timeout: 15000 });

  // typflaggan hela vägen: .tex är arbetsbladsmallen med facit, utan kravgränser
  const examId = await page.evaluate(() => (window as any).S.exam.id);
  const tex = await (await page.request.get(`/api/exams/${examId}/tex`)).text();
  expect(tex).toContain("Facit");
  expect(tex).not.toContain("Kravgränser");

  // Arkivet listar den godkända posten som Arbetsblad.
  await expect(page.getByText("Arkiv", { exact: true })).toBeVisible();
  await expect(page.getByText("Arbetsblad", { exact: true }).last()).toBeVisible({ timeout: 10000 });
});

test("Delade fält: kursvalet följer med mellan Tavla, Prov och Arbetsblad", async ({ page }) => {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Planering", exact: true }).click();

  const seg = page.getByRole("group", { name: "Dokumenttyp" });
  await seg.getByRole("button", { name: "Prov", exact: true }).click();
  await page.getByRole("button", { name: "Nivå 2b", exact: true }).click();
  await expect(page.getByRole("button", { name: "Nivå 2b", exact: true }))
    .toHaveAttribute("aria-pressed", "true");

  await seg.getByRole("button", { name: "Tavla", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Dagens tavla" })).toBeVisible();
  await expect(page.getByLabel("Moment")).toBeVisible();
  await expect(page.getByRole("button", { name: "Nivå 2b", exact: true }))
    .toHaveAttribute("aria-pressed", "true");

  await seg.getByRole("button", { name: "Arbetsblad", exact: true }).click();
  await expect(page.getByRole("button", { name: "Nivå 2b", exact: true }))
    .toHaveAttribute("aria-pressed", "true");
});
