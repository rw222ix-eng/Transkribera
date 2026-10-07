import { expect, test } from "@playwright/test";

/* MOLNVÄGEN
 *
 * Språkmodellsarbetet görs av Claude Code hos Anthropic. Frontenden måste hitta
 * servern och läsa vad den säger om Claude Code, annars kör den prototypens
 * egna data medan ingenting skrivs på riktigt.
 *
 * Transkriberingen hos ElevenLabs prövades också här. Den togs bort med
 * Transkribera-fliken 2026-10-07.
 */

test("appen ser servern och läser vem som skriver", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-server", "");
  const varKors = await page.evaluate(() => window.API.varKors);
  expect(varKors.moln.sprakmodell.leverantor).toBe("Anthropic");
  expect(varKors.moln.sprakmodell.verktyg).toBe("Claude Code");
});
