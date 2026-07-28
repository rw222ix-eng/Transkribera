// Task 6 (Plan 4): e2e för prov- och arbetsbladsflödet i den nya Svelte-
// frontenden (/next/). Bevisar hela vägen typväljare -> innehållsval ->
// generering -> ändra via den delade chatten -> godkänn & PDF, mot den
// riktiga backenden (fejkad LLM/GPU/Tectonic, se e2e/serve_test_app.py) —
// inte bara att grunden monteras. Se docs/superpowers/plans/
// 2026-07-25-prov-arbetsblad-svelte.md, Task 6.
//
// Mönster/fixtures återanvända rakt av från e2e/planering-tavla.spec.mjs
// och e2e/planering-arkiv.spec.mjs: failOnConsoleError, "/next/"-
// navigeringen och frameLocator-vanan (den här specen rör aldrig
// tavel-iframen). serve_test_app.py patchar exam_gen.generate_exam och
// exam_gen.refine_exam deterministiskt (_fake_exam/fake_refine_exam,
// ~rad 201-251) och exam_pdf.compile_pdf/engine_available (~rad 253-263)
// med en riktig, giltig PDF-stubbe — så generering, refine OCH
// godkännande+PDF går att köra end-to-end mot fejkservern utan Tectonic.
//
// Körordning (alfabetisk filordning inom next-foundation-projektet, se
// kommentaren i planering-arkiv.spec.mjs): next-foundation -> planering-
// arkiv -> planering-prov -> planering-tavla. Den här specen skapar inga
// planeringsarkivposter (prov/arbetsblad ligger i en egen tabell, rörs
// aldrig av routes_planning.py) och stör därför inte arkiv-specens
// "exakt en post"-antagande, oavsett körordning.
import { test, expect, failOnConsoleError } from "./helpers/app";

// Kursen har riktigt seedat Gy25-innehåll (seed_course_content körs vid
// serverstart, se .superpowers/sdd/progress.md T2) — "Aritmetik, algebra
// och funktioner" är den första gruppen med 7 punkter.
const KURS = "Matematik, nivå 1a";

test("Planering (/next/): skriv provet, ändra via chatten, godkänn & PDF", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.goto("/next/");

  // Skalet startar på Transkribera-fliken (som gamla appen) — gå till
  // Planering först. Se docs/superpowers/plans/2026-07-25-transkribera-A1-skal-och-kalla.md.
  await page.getByRole("tab", { name: "Planering", exact: true }).click();

  // 1) Typväljaren: Prov byter rubriken (heading, "Nytt prov" — serif-
  // kursiverade "prov" ingår i den tillgängliga rubriktexten).
  await expect(page.getByRole("heading", { name: /tavla/i })).toBeVisible();
  await page.getByRole("button", { name: "Prov", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Nytt prov" })).toBeVisible();

  // 2) CTA:n är avstängd tills en kurs är vald — innehållsval är valfritt
  // (exCanStart: !!st.byggCourseId, app.js:3605; parity-fix: gaten kräver
  // bara kurs, precis som gamla appen, se BuildPanel.svelte).
  const cta = page.getByRole("button", { name: "Skriv provet" });
  await expect(cta).toBeDisabled();

  // 3) Kursval laddar kursens innehållspunkter (ContentPicker.svelte via
  // loadContent(), triggat av $effect på plan.courseId i PlaneringView) OCH
  // slår på CTA:n direkt — utan att någon innehållspunkt är vald.
  // Kursen väljs i en <select>, inte bland chips: tio kurser gav tio synliga
  // val vid ett beslut, och Klass-raden ovanför var redan en select
  // (BuildPanel.svelte). selectOption matchar på etikett.
  //
  // getByRole("combobox"), inte getByLabel: Planering-panelen har ett ANNAT
  // fält som också bär den tillgängliga etiketten "Kurs", och getByLabel
  // träffar båda. Rollen skiljer dem — en <select> är combobox, det andra
  // fältet är en textbox.
  await page
    .getByRole("combobox", { name: "Kurs", exact: true })
    .selectOption({ label: KURS });
  await expect(page.getByText("Aritmetik, algebra och funktioner")).toBeVisible({ timeout: 10000 });
  await expect(page.getByText("0 valda av 7", { exact: true })).toBeVisible();
  await expect(cta).toBeEnabled();

  // 4) Att markera en hel grupp innehållspunkter fungerar fortfarande — och
  // CTA:n förblir på (den var redan på från steg 3).
  await page.getByRole("button", { name: "Markera alla" }).first().click();
  await expect(page.getByText("7 valda av 7", { exact: true })).toBeVisible();
  await expect(cta).toBeEnabled();

  // 5) Generering: en loggrad från fejk-provgeneratorn, sedan provkortet med
  // sex uppgifter (_fake_exam, e2e/serve_test_app.py).
  await cta.click();
  await expect(page.getByText(/Skriver provet/)).toBeVisible({ timeout: 15000 });
  const card = page.locator('[data-key="exam-card"]');
  await expect(card).toBeVisible({ timeout: 15000 });
  await expect(card.getByText("Prov — " + KURS)).toBeVisible();
  const tasks = card.locator(".tasks li");
  await expect(tasks).toHaveCount(6);
  await expect(card.getByText("Uppgift 1", { exact: true })).toBeVisible();

  // 6) Ändra-raden (den delade chatten) visas nu när provet (prov.doc.id)
  // finns, med en provspecifik platshållartext (ChangeChat.svelte).
  const changeField = page.getByLabel("Ändra provet");
  await expect(changeField).toBeVisible();
  await expect(changeField).toHaveAttribute(
    "placeholder",
    "Ändra provet — t.ex. gör uppgift 3 svårare, lägg till en A-uppgift",
  );

  // 6b) refineExam(): skicka en ändring UTAN markerade uppgifter och vänta på
  // att uppgift 1 får ändrings-suffixet. fake_refine_exam (e2e/serve_test_app.py)
  // lägger deterministiskt till " (ändrad)" på uppgift `nummer` — utan
  // markering skickas inget nummer, och fejken faller tillbaka på uppgift 1.
  const chat = changeField.locator("xpath=ancestor::div[contains(@class,'chat')]");
  await changeField.fill("Gör uppgift 1 svårare");
  await chat.getByRole("button", { name: "Skicka" }).click();
  await expect(
    card.locator(".tasks li").first().getByText(/\(ändrad\)$/),
  ).toBeVisible({ timeout: 15000 });
  // Fältet töms igen efter en lyckad ändring.
  await expect(changeField).toHaveValue("");

  // 6c) Elementriktad ändring (Plan 5 Task 2): markera uppgift 3 och skicka.
  // body.nummer = 3 gör att fejken ändrar just uppgift 3, inte uppgift 1 —
  // det är beviset för att markeringen når backenden. Raden ovanför fältet
  // ska namnge uppgiften, och markeringen ska vara tömd efteråt.
  const rader = card.locator(".tasks li");
  await rader.nth(2).getByRole("button", { name: "Markera uppgift 3" }).click();
  await expect(page.getByText("Ändringen gäller uppgift 3.")).toBeVisible();
  await changeField.fill("Byt kontext i uppgiften");
  await chat.getByRole("button", { name: "Skicka" }).click();
  await expect(rader.nth(2).getByText(/\(ändrad\)$/)).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/^Ändringen gäller uppgift/)).toHaveCount(0);
  await expect(card.locator(".tasks li.vald")).toHaveCount(0);

  // 6d) Två markerade uppgifter scopear inte via nummer — de vävs in i
  // meddelandet i stället (app.js:951-956). Fejken ändrar då uppgift 1, och
  // uppräkningen följer svensk grammatik ("1 och 2").
  await rader.nth(0).getByRole("button", { name: "Markera uppgift 1" }).click();
  await rader.nth(1).getByRole("button", { name: "Markera uppgift 2" }).click();
  await expect(page.getByText("Ändringen gäller uppgift 1 och 2.")).toBeVisible();
  await expect(card.locator(".tasks li.vald")).toHaveCount(2);
  // Rensa-knappen tömmer markeringen utan att skicka något.
  await page.getByRole("button", { name: "Rensa markeringen" }).click();
  await expect(card.locator(".tasks li.vald")).toHaveCount(0);

  // 7) Godkänn och skapa PDF: fejkservern har en riktig Tectonic-binär och
  // en patchad compile_pdf som alltid ger en giltig PDF-stubbe tillbaka
  // (fake_compile_pdf, e2e/serve_test_app.py) — deterministiskt, ingen
  // flaky LaTeX-kompilering. Statustaggen byter till "godkänt" och Öppna
  // PDF/TeX dyker upp.
  await card.getByRole("button", { name: "Godkänn och skapa PDF" }).click();
  await expect(card.getByText("godkänt", { exact: true })).toBeVisible({ timeout: 15000 });
  await expect(card.getByRole("button", { name: "Öppna PDF" })).toBeVisible();
  await expect(card.getByRole("button", { name: "Öppna TeX" })).toBeVisible();
  await expect(card.getByText(/PDF skapad:/)).toBeVisible();

  // 8) Inga konsolfel under hela flödet.
  expect(errors, errors.join("\n")).toEqual([]);
});
