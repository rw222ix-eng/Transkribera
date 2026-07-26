// Plan A1: e2e för transkriberingsguidens steg 1 i Svelte-frontenden
// (/next/). Kör mot den riktiga backenden med fejkad inferens
// (e2e/serve_test_app.py) — /api/sample är INTE stubbad och ger en riktig,
// validerad sökväg under base_dir (app/web/server.py:1718).
//
// TÄCKER INTE filväljaren eller drag-och-släpp: båda kräver pywebview
// (window.pywebview.api.pick_files respektive File.path), som inte finns i
// en vanlig webbläsare. Det är en medveten lucka, inte en glömska.
import { test, expect, failOnConsoleError } from "./helpers/app";

test("Transkribera (/next/): exempel i kön, dubblett, länk och borttagning", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.goto("/next/");

  // /api/sample kräver att "Mamma waw isolerad.wav" finns i repo-roten —
  // e2e/serve_test_app.py kopierar den bara om den finns, och den ligger inte
  // i git. Utan den blir felet annars en obegriplig timeout på kön.
  const sample = await page.request.get("/api/sample");
  expect(
    sample.status(),
    'Saknad testfixtur: "Mamma waw isolerad.wav" i repo-roten (se e2e/serve_test_app.py). ' +
      "/api/sample svarade " + sample.status() + ".",
  ).toBe(200);

  // 1) Skalet startar på Transkribera-fliken.
  await expect(page.getByRole("button", { name: "Transkribera", exact: true }))
    .toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: /Vad vill du transkribera/ })).toBeVisible();

  // 2) Exempelfilen: /api/sample ger en riktig sökväg som hamnar i kön.
  const ko = page.locator("ul.ko li");
  await expect(ko).toHaveCount(0);
  await page.getByRole("button", { name: "ett exempel", exact: true }).click();
  // Kön tar guiden vidare till steg 2 (som gamla appen) — tillbaka till
  // källsteget för att fortsätta pröva källfälten.
  await page.getByRole("button", { name: "Lägg till fler" }).click();
  await expect(ko).toHaveCount(1);
  await expect(page.getByText("1 fil i kön.")).toBeVisible();

  // 3) Samma fil igen är en dubblett — kön växer inte, och läraren får veta.
  await page.getByRole("button", { name: "ett exempel", exact: true }).click();
  // Dubbletten går genom addFiles precis som en ny fil, så guiden hoppar
  // återigen till steg 2. Statusraden är hoistad ovanför stegväxlingen
  // (plan A2-fixrunda) och är den enda live-regionen i båda stegen, så
  // beskedet ska synas HÄR, direkt på steg 2 — utan att navigera tillbaka
  // till källsteget först.
  await expect(ko).toHaveCount(1);
  await expect(page.getByTestId("statusrad")).toHaveText("1 fil låg redan i kön.");
  // Tillbaka till källsteget igen, för att fortsätta pröva källfälten
  // (länkfältet nedan finns bara där).
  await page.getByRole("button", { name: "Lägg till fler" }).click();

  // 4) Ogiltig länk avvisas med besked, och köas inte.
  // exact: true krävs — aria-label på fältet ("YouTube-länk") är en delsträng
  // av borttagningsknappens aria-label ("Ta bort YouTube-länk ur kön"), och
  // getByLabel matchar tillgängliga namn som delsträng. Utan exact matchar
  // lokatorn två element så fort en YouTube-rad ligger i kön, vilket bryter
  // Playwrights strict mode i steg 6.
  const lank = page.getByLabel("YouTube-länk", { exact: true });
  await lank.fill("inte-en-länk");
  await lank.press("Enter");
  await expect(page.getByTestId("statusrad")).toHaveText(
    "Klistra in en giltig länk (måste börja med http:// eller https://).",
  );
  await expect(ko).toHaveCount(1);

  // 5) Giltig länk köas med härlett namn, och fältet töms.
  await lank.fill("https://www.youtube.com/watch?v=abc123");
  await lank.press("Enter");
  // Ännu en lyckad köning tar guiden vidare till steg 2 igen.
  await page.getByRole("button", { name: "Lägg till fler" }).click();
  await expect(ko).toHaveCount(2);
  await expect(page.getByText("YouTube-länk", { exact: true })).toBeVisible();
  await expect(lank).toHaveValue("");

  // 6) Borttagning plockar bort rätt post — länken försvinner, exemplet är kvar.
  await page.getByRole("button", { name: /Ta bort YouTube-länk/ }).click();
  await expect(ko).toHaveCount(1);
  await expect(page.getByText("YouTube-länk", { exact: true })).toHaveCount(0);

  // 7) Inga konsolfel under hela flödet.
  expect(errors, errors.join("\n")).toEqual([]);
});

// Regressionstest för A2-fixrundan: ett misslyckat nedladdningsförsök av
// ljudmodellen (Gemma är gated — 401 utan accepterad licens) satte tidigare
// tr.fileError, men statusraden som visar den satt fast i källstegets
// {#if}-gren, så felet var osynligt på steg 2 där nedladdningsknappen bor.
// Modellen råkar vara installerad på utvecklingsmaskinen (se
// .superpowers/sdd/a2-task-4-report.md), så felvägen mockas fram med
// page.route i stället för att bero på maskinens faktiska modellstatus.
test("Transkribera (/next/): misslyckad nedladdning av ljudmodellen visar fel på steg 2", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  // Tvinga fram "ej installerad" så nedladdningsknappen renderas, oavsett
  // om modellen faktiskt ligger på disk här.
  await page.route("**/api/audio-model", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: "google/gemma-4-E4B-it", installed: false, download_mb: 16500 }),
    }),
  );
  // Samma SSE-kontrakt som backenden (app/web/sse.py:sse_response): ett
  // undantag blir data: {"type":"error","message":...}\n\n, konsumerat av
  // streamPost i frontend/src/lib/api.js.
  await page.route("**/api/download/audio-model", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: 'data: {"type": "error", "message": "401 Unauthorized — modellen är gated"}\n\n',
    }),
  );

  await page.goto("/next/");

  const sample = await page.request.get("/api/sample");
  expect(
    sample.status(),
    'Saknad testfixtur: "Mamma waw isolerad.wav" i repo-roten (se e2e/serve_test_app.py). ' +
      "/api/sample svarade " + sample.status() + ".",
  ).toBe(200);

  // Exempelfilen tar guiden till steg 2, där Formatval — och dess
  // nedladdningsknapp — renderas.
  await page.getByRole("button", { name: "ett exempel", exact: true }).click();

  const nedladdning = page.getByRole("button", { name: "Ladda ner modell" });
  await expect(nedladdning).toBeVisible();
  await nedladdning.click();

  // Felet ska synas HÄR, direkt på steg 2 — statusraden är hoistad ovanför
  // stegväxlingen (plan A2-fixrunda) just för att göra det här felet synligt.
  const statusrad = page.getByTestId("statusrad");
  await expect(statusrad).toBeVisible();
  await expect(statusrad).toHaveText(
    "Kunde inte ladda ner ljudmodellen: 401 Unauthorized — modellen är gated",
  );
  // Samma text bärs av den enda live-regionen, för skärmläsare.
  await expect(page.getByRole("status")).toHaveText(
    "Kunde inte ladda ner ljudmodellen: 401 Unauthorized — modellen är gated",
  );
  // Knappen ska ha återgått till sin ursprungstext, inte fastnat på "Laddar ner …".
  await expect(page.getByRole("button", { name: "Ladda ner modell" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Laddar ner …" })).toHaveCount(0);

  expect(errors, errors.join("\n")).toEqual([]);
});

// Regressionsspärr för själva live-regionen (p.fel-sr).
//
// Mönstret "{#if} runt en role=\"status\"" har fällts TRE gånger i den här
// migrationen — A2:s fixrunda, A3:s slutgranskning och A4 Task 2 — och hade
// ändå ingen automatisk spärr: testerna ovan assertar alla på den SYNLIGA
// kopian (data-testid="statusrad"), som är aria-hidden och alltså inte är det
// skärmläsaren läser. En live-region som monteras in i DOM:en samtidigt som
// sin text annonseras inte pålitligt; det som annonseras är en MUTATION i en
// nod som redan låg där.
//
// Testet vaktar därför tre egenskaper:
//   1. p.fel-sr finns INNAN något fel uppstått (en {#if}-grindad region finns
//      inte alls då, och en region som ligger inuti stegväxlingens
//      source-gren försvinner vid stegbyte),
//   2. det är SAMMA DOM-nod efteråt — noden märks med en expando som måste
//      överleva. Monteras regionen om i stället för att mutera försvinner
//      märket, och skärmläsaren annonserar ingenting,
//   3. antalet [role="status"] inuti den SYNLIGA panelens section.view är
//      oförändrat — två samtidigt muterande live-regioner läses i
//      oförutsägbar ordning, vilket är varför inspelningswidgeten medvetet
//      saknar en egen.
//
// Om avgränsningen ".pane:not([hidden])": App.svelte göms per flik med hidden,
// inte genom att avmontera, så varje migrerad vy ligger kvar i DOM:en samtidigt
// — och varje vy har rätteligen sin egen permanenta live-region. En
// sidoövergripande räkning fällde därför plan B1:s nya Inspelningar-vy för att
// den gjorde rätt. Att en dold panels region inte kan annonsera är garanterat:
// .pane[hidden] är display:none, alltså borta ur tillgänglighetsträdet.
//
// Ingen fejkmikrofon behövs: felet som framkallas är tr.fileError ur addUrl
// (ogiltig länk), samma väg som testet överst i filen redan använder. Regionen
// bär båda felkanalerna, så spärren gäller lika mycket för tr.recError.
test("Transkribera (/next/): live-regionen är permanent och muterar i stället för att monteras om", async ({ page }) => {
  const errors = [];
  failOnConsoleError(page, errors);

  await page.goto("/next/");

  // Avgränsat till den SYNLIGA panelen. App.svelte göms per flik med hidden,
  // inte {#if}, så alla vyers paneler ligger kvar i DOM:en samtidigt — och
  // varje vy har (rätteligen) sin egen permanenta live-region. En sidoövergripande
  // räkning skulle därför fälla varje ny vy som gör rätt. Att en dold panels
  // region inte kan annonsera är dessutom garanterat: .pane[hidden] är
  // display:none, vilket tar bort den ur tillgänglighetsträdet.
  const region = page.locator(".pane:not([hidden]) section.view p.fel-sr");
  const liveRegioner = page.locator('.pane:not([hidden]) section.view [role="status"]');

  // 1) Regionen finns FÖRE felet — tom, men på plats och med role="status".
  await expect(region).toHaveCount(1);
  await expect(region).toHaveText("");
  await expect(region).toHaveAttribute("role", "status");
  const antalFore = await liveRegioner.count();
  expect(antalFore).toBe(1);

  // Märk noden. Expandon lever bara så länge exakt DET HÄR DOM-elementet gör —
  // en ommontering ger ett nytt element utan märke.
  await region.evaluate((el) => {
    el.dataset.spar = "fel-sr-1";
  });

  // 2) Framkalla ett tr.fileError. Ogiltig länk, samma väg som ovan.
  const lank = page.getByLabel("YouTube-länk", { exact: true });
  await lank.fill("inte-en-länk");
  await lank.press("Enter");
  await expect(region).toHaveText(
    "Klistra in en giltig länk (måste börja med http:// eller https://).",
  );

  // 3) Samma nod, samma antal live-regioner.
  await expect(region).toHaveCount(1);
  await expect(region).toHaveAttribute("data-spar", "fel-sr-1");
  expect(await liveRegioner.count()).toBe(antalFore);

  expect(errors, errors.join("\n")).toEqual([]);
});
