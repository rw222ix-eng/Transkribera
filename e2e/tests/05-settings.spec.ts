import { test, expect, failOnConsoleError } from "../helpers/app";

// Modeller-fliken togs bort ur headern i omdesignen ("fast modelluppsättning",
// ff5f3e2) — modellvyn går inte längre att nå via UI:t. Katalog- och
// inställningsendpointsen som appen bygger på verifieras därför på API-nivå.

test("modellkatalogen svarar med installerade modeller", async ({ request }) => {
  const resp = await request.get("/api/models");
  expect(resp.status()).toBe(200);
  const body = await resp.json();
  expect(Array.isArray(body.whisper)).toBe(true);
  expect(body.whisper.length).toBeGreaterThan(0);
  expect(body.hardware).toBeTruthy();
});

test("inställningar svarar och appen startar utan konsolfel", async ({ page, request }) => {
  const errors: string[] = [];
  failOnConsoleError(page, errors);

  const resp = await request.get("/api/settings");
  expect(resp.status()).toBe(200);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Vad vill du transkribera?" })).toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
});
