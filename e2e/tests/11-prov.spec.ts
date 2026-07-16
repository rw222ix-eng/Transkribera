import { test, expect, failOnConsoleError } from "../helpers/app";

// Fas 4 — Provgeneratorn: guide (kurs → innehållspunkter) → generera →
// per-uppgift-iteration → godkänn → PDF, allt mot fejkade LLM/PDF-motorer
// men riktiga rutter, DB (v5) och artefaktskrivning.

test("Prov: guide → generera → iterera → godkänn → PDF (fejk)", async ({ page }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Planering", exact: true }).click();

  // Guide: kurs → innehållspunkter (seedade ur bundlad JSON) med ✓/○-status.
  await page.getByLabel("Provkurs").selectOption({ label: "Ma2b" });
  const chip = page.getByRole("button", { name: /Algebra/ }).first();
  await expect(chip).toBeVisible({ timeout: 10000 });
  await chip.click();
  await expect(chip).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("button", { name: "Skriv provet" }).click();

  // Resultat: balansmätare + kravgränser + numrerade uppgifter.
  await expect(page.getByText("Prov — Ma2b")).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/Totalt 20 p/)).toBeVisible();
  await expect(page.getByText(/Kravgränser: E 5/)).toBeVisible();
  await expect(page.getByText("Uppgift 1", { exact: true })).toBeVisible();
  await expect(page.getByText("Uppgift 6", { exact: true })).toBeVisible();

  // Per-uppgift-chatt: riktad omgenerering ger ny version.
  await page.getByLabel("Ändra uppgift 1").fill("gör den svårare");
  await page.locator('[data-key="ex-u-1"]').getByRole("button", { name: "Ändra" }).click();
  await expect(page.getByText(/\(ändrad\)/)).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("Version 2 av 2")).toBeVisible();

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
