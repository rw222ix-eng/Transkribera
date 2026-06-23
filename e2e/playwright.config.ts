import { defineConfig, devices } from "@playwright/test";
import * as path from "path";

const REPO = path.resolve(__dirname, "..");
const PORT = 8731;
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
      name: "real",
      testMatch: /real-smoke\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1040, height: 780 } },
      webServer: {
        command: `python e2e/serve_test_app.py --real`,
        cwd: REPO,
        url: BASE_URL,
        timeout: 60_000,
        reuseExistingServer: false,
        env: {
          TRANSKRIBERA_PORT: String(PORT),
          TRANSKRIBERA_BASE_DIR: TEST_DATA_REAL,
        },
      },
    },
  ],
  // Default server (fake) for the fake + visual projects.
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
