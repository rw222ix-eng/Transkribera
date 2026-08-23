import { expect, test } from "@playwright/test";
import * as L from "./larardag.mjs";

/* FÖRLOPPSRADEN NÄR PROVET SKRIVS
 *
 * Läraren såg «Claude skriver provet» och en klocka i sju till tio minuter, och
 * så var det klart på en gång. Serverns loggrader nådde klienten hela tiden —
 * men skrevs bara i faslistans `.fdetalj`, och faslistan är HOPFÄLLD medan
 * jobbet går. Under själva modellanropet skickade servern dessutom ingenting:
 * `token_cb=None` stod i exam_gen._llm_round, och med --json-schema kommer
 * svaret aldrig ens som text_delta (claude_code, input_json_delta).
 *
 * Kedjan som prövas här är alltså hela: CLI:ts ström → claude_code →
 * exam_gen._Uppgiftsraknare → log_cb → SSE → api.js → fraga.js smal-läge.
 * Bara molnet är fejkat (kassett, e2e/testserver.py) — allt efter svaret är
 * appens riktiga kod.
 *
 * ── MÄTMETODEN ────────────────────────────────────────────────────────────
 * Inte en ögonblicksbild: kassetten spelas upp så fort disken orkar, så «vänta
 * tills rutan säger X» är ett lopp mot en rad som redan hunnit bytas ut.
 *
 * Och inte heller en MutationObserver, fast det var första försöket. Den kördes
 * grön här och FÖLL i full svit: kommer flera SSE-händelser i samma TCP-bit
 * skriver klienten alla raderna i ETT synkront svep, och observatören — som
 * körs en gång per mikrouppgiftsomgång — ser bara den sista. Raderna
 * försvann alltså när maskinen hade bråttom, vilket är precis tvärtemot vad
 * ett flakigt test får göra.
 *
 * Kroken sitter därför på `textContent`-sättaren, som är det enda stället VARJE
 * skrivning passerar. Bredderna får observatören behålla: de sätts som
 * style-attribut, och en missad mellanbredd kan aldrig hitta på ett hopp bakåt
 * som inte fanns.
 */

/** Skrivs in före sidan laddas: den samlar radens historik åt testet. */
const OBSERVATOR = () => {
  window.__forlopp = { rader: [], bredder: [], brukar: "" };
  const f = window.__forlopp;

  const txt = Object.getOwnPropertyDescriptor(Node.prototype, "textContent");
  Object.defineProperty(Node.prototype, "textContent", {
    configurable: true,
    get() { return txt.get.call(this); },
    set(v) {
      txt.set.call(this, v);
      if (this.classList && this.classList.contains("fsmaltext")) {
        f.rader.push(String(v));
      }
    },
  });

  const titta = () => {
    const b = document.querySelector(".fsmalspar i");
    if (b) {
      const w = parseFloat(b.style.width) || 0;
      if (f.bredder[f.bredder.length - 1] !== w) f.bredder.push(w);
    }
    const br = document.querySelector(".fsmalbrukar");
    if (br && br.textContent) f.brukar = br.textContent;
  };
  /* `document`, inte `document.documentElement`: init-skriptet körs innan
     sidans egen första rad, och roten finns inte alltid att haka på än. */
  new MutationObserver(titta).observe(document, {
    subtree: true, childList: true, characterData: true,
    attributes: true, attributeFilter: ["style"],
  });
};

/* Sviten delar bas. Ett utkast som blir kvar här återställs i NÄSTA spec och
   drar undan mattan för den — och det gjorde det, första gången den här filen
   föll. Städningen ligger därför i afterEach och inte sist i testet: den ska
   köras också (särskilt) när något gått fel. */
test.afterEach(async ({ page }) => {
  const hogen = await (await page.request.get("/api/dokument")).json()
    .catch(() => ({}));
  if (hogen && hogen.utkast && hogen.utkast.id) {
    await page.request.delete(`/api/dokument/${hogen.utkast.id}`).catch(() => {});
  }
});

test("den smala raden bär serverns egna rader medan provet skrivs", async ({ page }) => {
  await page.addInitScript(OBSERVATOR);
  await L.fejkatMoln(page);
  await L.oppna(page);
  await L.valjKlass(page, "NA25");
  await L.skriv(page, { typ: "Prov", moment: "derivator" });
  await L.vantaPapper(page, 60_000);

  const f = await page.evaluate(() => window.__forlopp);

  /* 1. RADEN SÄGER VAD SERVERN GÖR. Kravet är uppgiftsräknaren och inget
        annat: «Skriver provet …» fanns redan och stod stilla hela tiden. */
  const uppgifter = f.rader.filter(r => /uppgift \d+ av \d+/.test(r));
  expect(uppgifter.length,
    `ingen uppgiftsrad nådde .fsmaltext — raderna var: ${JSON.stringify(f.rader)}`)
    .toBeGreaterThan(0);
  /* …och SKRIVNINGENS rader räknar upp en uppgift i taget, från ett. En
     reparationsrunda börjar om på 1 — den skriver om hela dokumentet — men den
     säger vilken runda den är på, så numret betyder fortfarande något. */
  const nr = f.rader.filter(r => /^Skriver uppgift /.test(r))
    .map(r => Number(/uppgift (\d+) av/.exec(r)[1]));
  expect(nr).toEqual(nr.map((_, i) => i + 1));

  /* 2. INGEN RAD ÄR KAPAD TILL «… …». Serverns rader slutar på ett eget
        tankstreck, och en trubbig kapning hade lagt ett till. */
  for (const r of f.rader) {
    expect(r.length).toBeLessThanOrEqual(60);
    expect(r).not.toMatch(/…\s*…$/);
  }

  /* 3. MÄTAREN GÅR ALDRIG BAKÅT — och den rör sig. En mätare som står still
        är inte att skilja från en hängd app; en som hoppar tillbaka läses som
        ett fel. */
  expect(f.bredder.length).toBeGreaterThan(3);
  for (let i = 1; i < f.bredder.length; i++) {
    expect(f.bredder[i],
      `mätaren gick bakåt: ${JSON.stringify(f.bredder)}`)
      .toBeGreaterThanOrEqual(f.bredder[i - 1] - 0.01);
  }
  expect(Math.max(...f.bredder)).toBeGreaterThan(Math.min(...f.bredder));

  /* 4. SPANNET STÅR BREDVID KLOCKAN. Sju till tio minuter är lärarens egen
        mätning av provet — det är därför bara provet har ett spann. */
  expect(f.brukar).toContain("min");
});
