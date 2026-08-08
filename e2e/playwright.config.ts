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
/* Soak-körningen (tools/soak.py) startar EN server med en bas som lever kvar
 * mellan varven — det är hela poängen: läckor syns bara i ett hus som inte rivs
 * varje gång. Då ska sviten återanvända den servern i stället för att starta en
 * egen och tömma basen. */
const SOAK = !!process.env.SOAK;
const PORT = SOAK ? Number(process.env.SOAK_PORT || 8752) : 8751;

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.mjs$/,
  fullyParallel: false,
  /* EN worker. `fullyParallel: false` serialiserar bara testerna INOM en fil —
   * filerna fördelades på en worker per kärna och körde alltså samtidigt, mot
   * EN server och EN databas. Det märktes inte så länge sviten mest läste och
   * fejkade rutter med page.route, men Etapp 4:s lärardagar skriver på riktigt:
   * en fil som raderade ett papper kunde då dra undan mattan för en annan fils
   * mätning. Appen är dessutom en enanvändarapp — hundratals lärare betyder
   * hundratals SESSIONER, aldrig samtidiga. Serialiserat är alltså också
   * sannare. */
  workers: 1,
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
    // Servern körs mot en TOM temporär bas, aldrig repot. create_app utan
    // base_dir pekar på reporoten — alltså lärarens riktiga transkribera.db,
    // history.json och Transkriberingar/ — och varje skrivande test hade
    // skrivit där. Se e2e/testserver.py.
    command: `python e2e/testserver.py ${PORT}`,
    cwd: "..",
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: SOAK,
    timeout: 120_000,
  },
});
