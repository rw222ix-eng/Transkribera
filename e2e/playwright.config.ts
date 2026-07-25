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
      name: "next-foundation",
      testDir: __dirname,
      testMatch: [
        /next-foundation\.spec\.mjs$/,
        /planering-tavla\.spec\.mjs$/,
        /planering-arkiv\.spec\.mjs$/,
        /planering-prov\.spec\.mjs$/,
        /transkribera-kalla\.spec\.mjs$/,
        /transkribera-installningar\.spec\.mjs$/,
        /transkribera-korning\.spec\.mjs$/,
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
