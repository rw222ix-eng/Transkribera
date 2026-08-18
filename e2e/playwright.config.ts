import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
import { join } from "node:path";

/* Webbläsaren sviten kör i — se kommentaren vid `channel` nedan. */
const CHROME = process.env.CHROME_PATH || "/opt/pw-browsers/chromium";

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
/* Pythonen sviten startar servern med. Macen har ingen `python` alls — bara
 * `python3` — och beroendena ligger i .venv, inte systemvitt: hela sviten föll
 * på «python: command not found» innan den hunnit starta. Samma ordning som
 * tools/miljo.sh: venv först, sedan plattformens namn. Behållaren har `python`
 * i PATH som förr. */
const ROT = join(__dirname, "..");
const PY = existsSync(join(ROT, ".venv/bin/python"))
  ? ".venv/bin/python"
  : existsSync(join(ROT, ".venv/Scripts/python.exe"))
    ? ".venv\\Scripts\\python.exe"
    : process.platform === "darwin" ? "python3" : "python";

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
  /* Playwrights standardgräns är 30 s och är satt för rena UI-test. Sviten kör
   * appens riktiga server: generering, validering, reparationsrundor och
   * Tectonic. Dag 3 behövde redan sätta 240 s för hand.
   *
   * På GitHubs windows-runner föll tre test på just 30 s (2026-08-09) medan
   * samma test tar sekunder här — och dag 4 föll likadant på den här maskinen
   * när soaken körde tracemalloc bredvid. Det är maskinens hastighet som
   * avgör, inte koden.
   *
   * OBS att detta är en gräns, inte en väntan: en grön körning blir inte en
   * sekund långsammare av att taket höjs. Blir ett test konsekvent 60 s är det
   * något annat, och då syns det i körningstiderna. */
  timeout: 90_000,
  /* Omförsök BARA i CI, och bara där av en mätt anledning.
   *
   * GitHubs windows-runner har två kärnor och kör Chrome, Python-servern och
   * Playwright samtidigt. Under trängseln tog en 404 på en statisk fil 38
   * sekunder (spår, 2026-08-09) — ren kö. Följden blev att ETT test föll per
   * körning, men aldrig samma: flerklass, sedan iterera och rattning, sedan
   * offline, sedan dag 3. Alla på tid, aldrig på påstående.
   *
   * Hypotesen att appen svälter trådpoolen mättes och FÖLL: hela sviten kördes
   * lokalt med serverns trådantal provat var tredje sekund, och trådarna toppar
   * på 24 av anyios 40 och sjunker mot slutet. Det finns alltså inget i koden
   * att laga.
   *
   * Noll här: ett test som är flakigt på den här maskinen är ett fynd, och det
   * ska synas direkt. I CI rapporterar Playwright omförsökta test som «flaky» —
   * de göms inte, de får en etikett. Faller ett test alla tre gångerna är det
   * trasigt på riktigt. */
  retries: process.env.CI ? 2 : 0,
  forbidOnly: !!process.env.CI,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    // Rörelse av: himlens Ken Burns-panorering pågår i 56 sekunder och gör varje
    // skärmbild olik den förra. Utan detta mäter man animeringen, inte designen.
    reducedMotion: "reduce",
    viewport: { width: 1440, height: 950 },
    // Playwrights egen chromium är inte nedladdad på lärarens maskiner; appen
    // körs ändå bara i den Chromium som pywebview bäddar in på Windows.
    //
    // I en Linuxbehållare finns ingen Chrome att välja kanal på, och sviten gick
    // därför inte att köra där alls — vilket är illa, för det är i behållare
    // utvecklingen numera delvis sker. Finns en Chromium på plats (CHROME_PATH,
    // annars den förinstallerade) körs den; annars står kanalen kvar som förut.
    ...(existsSync(CHROME) ? { launchOptions: { executablePath: CHROME } }
                           : { channel: "chrome" as const }),
    /* Spåret och `test-results/<test>/error-context.md` skrivs för det test som
     * FÖLL — och Playwright tömmer test-results i början av NÄSTA körning.
     * LÄS DEM INNAN DU KÖR OM. En röd apa (2026-08-14) gick inte att förklara
     * efteråt: sviten kördes om direkt för att se om felet satt kvar, och då
     * var både spåret och felmeddelandet borta. Sju gröna körningar senare fanns
     * ingenting kvar att titta på. */
    trace: "retain-on-failure",
  },
  webServer: {
    // Servern körs mot en TOM temporär bas, aldrig repot. create_app utan
    // base_dir pekar på reporoten — alltså lärarens riktiga transkribera.db,
    // history.json och Transkriberingar/ — och varje skrivande test hade
    // skrivit där. Se e2e/testserver.py.
    command: `${PY} e2e/testserver.py ${PORT}`,
    cwd: "..",
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: SOAK,
    timeout: 120_000,
  },
});
