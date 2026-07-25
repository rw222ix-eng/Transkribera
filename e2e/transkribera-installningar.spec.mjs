// Plan A2: e2e för transkriberingsguidens steg 2 i Svelte-frontenden
// (/next/). Kör mot den riktiga backenden med fejkad inferens
// (e2e/serve_test_app.py); /api/sample och /api/models är oberörda av
// fejkarna och svarar på riktigt.
//
// TÄCKER INTE steg 3 (körningen) — den byggs i plan A3. Startknappen är
// avstängd, och den här specen kontrollerar att den ÄR avstängd, så att
// ingen råkar tro att guiden går hela vägen.
import { test, expect, failOnConsoleError } from "./helpers/app";

test("Transkribera (/next/): inställningssteget", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.goto("/next/");

  // /api/sample kräver "Mamma waw isolerad.wav" i repo-roten — utan den blir
  // felet annars en obegriplig timeout. Samma förkontroll som källstegets spec.
  const sample = await page.request.get("/api/sample");
  expect(
    sample.status(),
    'Saknad testfixtur: "Mamma waw isolerad.wav" i repo-roten (se e2e/serve_test_app.py).',
  ).toBe(200);

  // 1) Att köa en fil tar guiden till steg 2 — och stegindikatorn säger det.
  await page.getByRole("button", { name: "ett exempel", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Så ska det låta/ })).toBeVisible();
  await expect(page.locator("li.aktiv")).toHaveAttribute("aria-current", "step");
  await expect(page.locator("li.aktiv")).toContainText("Inställningar");

  // 2) Kön följer med hit, och "Lägg till fler" går tillbaka till steg 1.
  await expect(page.locator("ul.ko li")).toHaveCount(1);
  await page.getByRole("button", { name: "Lägg till fler" }).click();
  await expect(page.getByRole("heading", { name: /Vad vill du transkribera/ })).toBeVisible();
  await page.getByRole("button", { name: "Nästa: inställningar" }).click();
  await expect(page.getByRole("heading", { name: /Så ska det låta/ })).toBeVisible();

  // 3) Talat språk styr resultatspråket: byter man till Engelska följer
  // resultatet med, i stället för att lämna kvar en oavsiktlig översättning
  // (pickLang, app.js:1516).
  const talat = page.getByRole("group", { name: "Talat språk" });
  const resultat = page.getByRole("group", { name: "Resultatspråk" });
  await talat.getByRole("button", { name: "Engelska" }).click();
  await expect(resultat.getByRole("button", { name: "Engelska" }))
    .toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText(/samma som det talade språket/)).toBeVisible();

  // 4) Skiljer sig språken säger panelen att texten översätts.
  await resultat.getByRole("button", { name: "Svenska" }).click();
  await expect(page.getByText("Översätts från engelska till svenska.")).toBeVisible();

  // 5) Formatchipsen växlar.
  const srt = page.getByRole("button", { name: "SRT", exact: true });
  await expect(srt).toHaveAttribute("aria-pressed", "true");
  await srt.click();
  await expect(srt).toHaveAttribute("aria-pressed", "false");

  // 6) Undertextsektionen hör till video — exempelfilen är ljud, så den ska
  // INTE finnas här.
  await expect(page.getByRole("group", { name: "Undertext i video" })).toHaveCount(0);

  // 7) Startknappen är avstängd: steg 3 finns inte än (plan A3).
  const start = page.getByRole("button", {
    name: /Starta transkribering|Ladda ner en modell först|Laddar modeller/,
  });
  await expect(start).toBeVisible();
  await expect(start).toBeDisabled();

  // 8) Inga konsolfel under hela flödet.
  expect(errors, errors.join("\n")).toEqual([]);
});
