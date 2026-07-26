import { defineConfig, devices } from "@playwright/test";
import * as path from "path";

const REPO = path.resolve(__dirname, "..");
// 8731 kan hamna i Windows exkluderade portintervall (Hyper-V) — tillåt override.
const PORT = Number(process.env.TRANSKRIBERA_PORT || 8731);
const BASE_URL = `http://127.0.0.1:${PORT}`;
const TEST_DATA = path.join(__dirname, ".test-data");
const TEST_DATA_REAL = path.join(__dirname, ".test-data-real");

// Expose the isolated base dir to specs (for injecting the sample file path).
process.env.E2E_TEST_DATA = TEST_DATA;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false, // one shared server + one shared GPU
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: {
      args: [
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
      ],
    },
  },
  projects: [
    {
      name: "fake",
      testIgnore: /(visual|real-smoke)\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1040, height: 780 } },
    },
    {
      name: "visual",
      testMatch: /visual\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      // The real smoke runs against the REAL backend. Playwright's webServer is
      // top-level only, so start the real server yourself before this project:
      //   TRANSKRIBERA_BASE_DIR=e2e/.test-data-real python e2e/serve_test_app.py --real
      // (npm run test:real reuses whatever is already listening on the port).
      name: "real",
      testMatch: /real-smoke\.spec\.ts/,
      // The CTranslate2 transcription subprocess can abort natively on
      // Windows/CUDA (see CLAUDE.md); retry the genuine run so a transient
      // teardown abort doesn't fail the smoke.
      retries: 3,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1040, height: 780 } },
    },
    {
      // Task 6: standalone smoke for the Vite/Svelte build served at /next.
      // Lives at e2e/next-foundation.spec.mjs (repo-root-adjacent, per the
      // task-6 brief) rather than under testDir (./tests), so it needs its
      // own testDir/testMatch here. Reuses the same fake webServer as
      // "fake"/"visual" — it only asserts the /next mount renders.
      //
      // Task 8 adds e2e/planering-tavla.spec.mjs alongside it (same
      // repo-root-adjacent placement, same fake webServer) covering the full
      // board flow (skriv/förhandsvisa/ändra/godkänn) against the /next
      // mount — matched here too rather than as a separate project, per the
      // task-8 brief.
      //
      // Plan 3 Task 4 adds e2e/planering-arkiv.spec.mjs (same placement,
      // same fake webServer) covering the archive (list/word-search/Rensa/
      // Fråga AI) below the board view — see .superpowers/sdd/task-4-brief.md.
      //
      // Plan 4 Task 6 adds e2e/planering-prov.spec.mjs (same placement, same
      // fake webServer) covering the prov/arbetsblad flow (typväljare,
      // innehållsval, generering, den delade ändringschatten, godkännande
      // och PDF) — see docs/superpowers/plans/2026-07-25-prov-arbetsblad-
      // svelte.md, Task 6. It never touches the planning archive, so it
      // doesn't disturb planering-arkiv.spec.mjs's "exactly one entry"
      // assumption regardless of execution order.
      //
      // OBS (stale-bundle-gaten): app/web/next/ är byggartefakter (npm run
      // build i repo-roten), inte något Playwright bygger själv — webServer
      // nedan är top-level och delas av alla projekt, så den kan inte bygga
      // åt just detta ett. Kör därför alltid via `npm run test:next-foundation`
      // (e2e/package.json), som bygger frontend FÖRST och sedan kör detta
      // projekt — annars riskerar testerna att tyst godkänna en gammal bundle.
      //
      // Plan A1 Task 5 lägger till e2e/transkribera-kalla.spec.mjs (samma
      // placering, samma fejkserver) som täcker guidens steg 1: kön via
      // /api/sample, dubblettbeskedet, länkvalideringen och borttagning.
      // Filväljaren och drag-och-släpp kräver pywebview och täcks INTE här —
      // se docs/superpowers/plans/2026-07-25-transkribera-A1-skal-och-kalla.md.
      //
      // Plan A2 Task 6 lägger till e2e/transkribera-installningar.spec.mjs
      // (samma placering, samma fejkserver) som täcker guidens steg 2:
      // kölistan, talat språk/resultatspråk, formatchipsen och
      // undertextvillkoret. Steg 3 (själva körningen) täcks INTE här — det
      // steget finns inte än, se plan A3. Startknappen renderas avstängd,
      // och specen kontrollerar just att den ÄR avstängd.
      //
      // Plan A3 Task 6 lägger till e2e/transkribera-korning.spec.mjs (samma
      // placering, samma fejkserver) som täcker guidens steg 3: att starten
      // tar guiden hit med stegindikatorn på Transkribering, att körningen
      // når Klar med 100 % och klarbeskedet, att loggen fälls ut, och att ett
      // avbrott landar i avbrutet-kortet med Återuppta och en verklig POST
      // till /api/transcribe/cancel. Fixrundan lägger till kökedjan: att
      // klarbeskedet hålls tillbaka så länge en post väntar och att nästa post
      // verkligen startas. Överlämningen till Inspelningar täcks
      // INTE — den vyn är inte migrerad än, så guiden stannar medvetet kvar
      // på steg 3 och säger det i klartext i stället för att navigera till en
      // platshållare (se plan A3).
      //
      // Plan A4 Task 6 lägger till e2e/transkribera-inspelning.spec.mjs (samma
      // placering, samma fejkserver) som täcker inspelningen i guidens steg 1:
      // start och timer, att bitarna verkligen POSTas till
      // /api/recording/append, Markera (räknare + localStorage), Stoppa och
      // lägg till, topbar-brickan över flikbyte, bannern för oavslutade
      // .part-filer (inklusive att den PÅGÅENDE inspelningen filtreras bort),
      // hela felkedjan för uppladdningen (nätverksfel med växande
      // sekundräknare, omförsöket, och serverns 507 utan omförsök), hela
      // markörkedjan fram till POST /api/recordings/{id}/markers, nekad
      // mikrofon, samt att en körning inte går att starta mitt i en inspelning
      // och att brickan inte lämnar en pågående körning om den grinden ändå
      // kringgås. Fejkmikrofonen kommer från de GLOBALA launchOptions ovan
      // (--use-fake-device-for-media-stream + --use-fake-ui-for-media-stream),
      // som alla projekt ärver — projektet behöver alltså inga egna flaggor.
      // TÄCKS INTE: tystnadsvarningen (fejkenheten skickar en kontinuerlig ton
      // och blir aldrig tyst), localStorage över en pywebview-omstart (bara
      // över en omladdning), och riktig mikrofonhårdvara inklusive att enheten
      // dras ur mitt i en inspelning. Specens egen kommentar upprepar listan.
      //
      // Plan B1 Task 5 lägger till e2e/inspelningar-kartotek.spec.mjs (samma
      // placering, samma fejkserver) som täcker Inspelningar-flikens kartotek:
      // veckogrupperingen med antal per grupp, att KLASS-filtret verkligen
      // skickar ett nytt GET /api/lessons (avläst ur nätverksloggen) medan
      // MÅNADS-filtret inte skickar något alls, generationsvakten som hindrar
      // ett långsammare filtersvar från att skriva över ett nyare, PATCH:en
      // från redigeringsdialogen, DELETE:et från raderingsbekräftelsen,
      // DELETE:ets 409 (fejkat med page.route och serverns egen kropp — det som
      // prövas är klientens visningsväg, inte serverns förmåga att svara 409),
      // de två åtskilda tomtillstånden och ärlighetsvakten för historikposter
      // utan lektionsrad. TÄCKER INTE: att öppna en lektion (transkript, ljud,
      // chatt — det finns inte i B1 och kommer i B2/B4), sök, arkivfrågan och
      // panelerna, kortets miniatyr (miljön har bara en .wav) eller en ÄKTA
      // fillåsning bakom 409:an. Specen skapar sina lektioner via
      // riktiga POST /api/transcribe — det finns ingen POST /api/lessons — och
      // raderar dem i afterEach, så basmappen lämnas i samma tomma läge som
      // servern startade i. Den sorteras FÖRST av filerna i det här projektet,
      // vilket är just därför städningen är obligatorisk.
      // Se .superpowers/sdd/task-5-brief.md.
      //
      // FÄLLA FÖR B2-B5, skarpladdad men ännu otriggad: en CSS-räkning av
      // [role="status"] inuti den SYNLIGA Inspelningar-panelen ger nu 2 —
      // RedigeraLektion.svelte:165 plus InspelningarView.svelte:94 — medan
      // TILLGÄNGLIGHETSTRÄDET säger 1. Motsägelsen är skenbar och båda noderna
      // är rätt: stängd är dialogen display:none och alltså ur trädet, öppen gör
      // showModal() resten av panelen inert och tar bort vyns region ur trädet i
      // stället. Antalet annonserande noder i den kontext som faktiskt syns är
      // alltid ett. En framtida spec som vill hålla den regeln MÅSTE därför
      // räkna med getByRole("status") — eller utesluta dialog:not([open]) — och
      // inte med page.locator('[role="status"]'). Ingen befintlig spärr träffas
      // (A4:s antalsspärr i transkribera-kalla.spec.mjs räknar i
      // Transkribera-panelen, som inte har någon dialog), men mönstret ärvs av
      // varje vy B2-B5 lägger till.
      name: "next-foundation",
      testDir: __dirname,
      testMatch: [
        /inspelningar-kartotek\.spec\.mjs$/,
        /next-foundation\.spec\.mjs$/,
        /planering-tavla\.spec\.mjs$/,
        /planering-arkiv\.spec\.mjs$/,
        /planering-prov\.spec\.mjs$/,
        /transkribera-kalla\.spec\.mjs$/,
        /transkribera-installningar\.spec\.mjs$/,
        /transkribera-korning\.spec\.mjs$/,
        /transkribera-inspelning\.spec\.mjs$/,
      ],
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Default server (fake) for the fake + visual projects. reuseExistingServer
  // lets the real smoke reuse a manually-started --real server on the same port.
  webServer: {
    command: `python e2e/serve_test_app.py`,
    cwd: REPO,
    url: BASE_URL,
    timeout: 60_000,
    reuseExistingServer: true,
    env: {
      TRANSKRIBERA_PORT: String(PORT),
      TRANSKRIBERA_BASE_DIR: TEST_DATA,
    },
  },
});
