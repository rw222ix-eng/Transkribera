import { defineConfig } from "@playwright/test";

/* E2E för Transkriberas frontend.
 *
 * Sviten startar den RIKTIGA FastAPI-servern och kör mot den. Ingen fejkserver
 * behövs längre: frontenden anropar inget API — den är designprototypen från
 * Claude Design, med hårdkodad data och setTimeout i stället för nätverk. Det
 * som går att testa i dag är alltså sättningen och offline-integriteten, och det
 * är också precis det som är lätt att förstöra av misstag. När backen kopplas in
 * växer sviten med den.
 *
 * Egen port (8751), skild från utvecklingsserverns 8750, så en igångvarande
 * dev-server inte tystar en trasig svit genom att svara i dess ställe.
 */
const PORT = 8751;

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.mjs$/,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    // Rörelse av: himlens Ken Burns-panorering pågår i 56 sekunder och gör varje
    // skärmbild olik den förra. Utan detta mäter man animeringen, inte designen.
    reducedMotion: "reduce",
    viewport: { width: 1440, height: 950 },
    // Playwrights egen chromium är inte nedladdad i den här miljön; appen körs
    // ändå bara i den Chromium som pywebview bäddar in på Windows.
    channel: "chrome",
    trace: "retain-on-failure",
  },
  webServer: {
    command: `python -c "import uvicorn; uvicorn.run('app.web.server:create_app', factory=True, host='127.0.0.1', port=${PORT}, log_level='warning')"`,
    cwd: "..",
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
