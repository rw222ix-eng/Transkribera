// Plan A2: e2e för transkriberingsguidens steg 2 i Svelte-frontenden
// (/next/). Kör mot den riktiga backenden med fejkad inferens
// (e2e/serve_test_app.py); /api/sample och /api/models är oberörda av
// fejkarna och svarar på riktigt.
//
// Plan A3 (task 4) lägger till täckning av steg 3:s startknapp: att den blir
// klickbar när en fil är köad och en modell är vald. /api/models gör en
// riktig hårdvaruskanning även i fejkläge, så testet väntar in katalogen i
// stället för en fast paus, och växlar talat språk till svenska — KB-Whisper
// large är den enda riktiga modellen som faktiskt är installerad i den här
// miljön, så bara det språket kan göra knappen klickbar.
// TÄCKER INTE själva körningen (fasbaren, den animerade procenten och den
// riktiga transkriberingen) — det verifierades manuellt mot fejkservern,
// se .superpowers/sdd/task-4-brief.md.
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

  // 7) Ett laddat exempel plus en vald modell aktiverar startknappen — steg 3
  // finns nu (plan A3). Växla tillbaka till svenska: det är den enda riktigt
  // installerade Whisper-modellen i den här miljön (KB-Whisper large), så
  // bara det språket kan göra knappen klickbar. Vänta in katalogen (riktig
  // hårdvaruskanning i /api/models) i stället för en fast paus.
  await talat.getByRole("button", { name: "Svenska" }).click();
  const start = page.getByRole("button", { name: "Starta transkribering", exact: true });
  await expect(start).toBeVisible({ timeout: 20_000 });
  await expect(start).toBeEnabled();

  // 8) Inga konsolfel under hela flödet.
  expect(errors, errors.join("\n")).toEqual([]);
});
