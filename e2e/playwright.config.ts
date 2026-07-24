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
      name: "next-foundation",
      testDir: __dirname,
      testMatch: /next-foundation\.spec\.mjs$/,
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
