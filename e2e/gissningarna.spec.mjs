import { expect, test } from "@playwright/test";

/* GISSNINGARNA OCH VECKOMATTEN SOM EGENSKAPER (Etapp 4.5)
 *
 * Två rena funktioner bär hela appens tideräkning, och båda går sönder tyst:
 *
 *   · `gissaDatum`/`gissaTid` (app.js) läser filnamnet en lärare råkar ha:
 *     «NA25 2026-08-20 kl 0905.m4a», «ma3c 20 aug 09.05.mp3», «Inspelning
 *     (3).m4a». Läses datumet som en tid — 2026-08-20 som 20:26 — hamnar
 *     lektionen på fel plats i schemat, och `Kalender.traff` gör den
 *     gissningen till FAKTA: klass och kurs sätts utan att läraren tillfrågas.
 *   · ISO-veckorna styr veckovyn, terminsvyn, «nästa skolvecka» och varje
 *     dokuments plats. Kända datum är prövade (kalendern.spec.mjs); här körs
 *     hela år mot en oberoende referens.
 *
 * Fallen genereras med en FAST seed: en röd körning går att köra om exakt.
 * Hypothesis finns bara i Python, och funktionerna bor i webbläsaren — så
 * generatorn är skriven här, med samma tanke: många fall, få påståenden, och
 * krympning görs för hand ur utskriften när något faller.
 */

const SCHEMA = { schema: [], lov: [], poster: [] };

const json = (route, kropp) => route.fulfill({
  status: 200, contentType: "application/json", body: JSON.stringify(kropp) });

async function fejka(page) {
  await page.route("**/api/schema", route => json(route, SCHEMA));
  await page.route("**/api/lessons", route => json(route, []));
  await page.route("**/api/history", route => json(route, []));
  await page.route("**/api/klassprofil", route => json(route, {}));
  await page.route("**/api/dokument", route => json(route, { sparade: [], utkast: null }));
}

const hydrerad = page => page.waitForFunction(() =>
  window.Kalender && window.Kalender.franServern());

// ── Filnamnen ────────────────────────────────────────────────────────────

test("ett datum i filnamnet läses aldrig som ett klockslag", async ({ page }) => {
  await fejka(page);
  await page.clock.install({ time: new Date("2026-09-08T08:00:00") });
  await page.goto("/");
  await hydrerad(page);

  const fall = await page.evaluate(() => {
    /* Mulberry32 — liten, seedad och deterministisk. Samma seed ger samma
       tusen filnamn varje körning, på varje maskin. */
    let s = 20260808;
    const slump = () => {
      s |= 0; s = (s + 0x6D2B79F5) | 0;
      let t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    const heltal = (a, b) => a + Math.floor(slump() * (b - a + 1));
    const nolla = n => String(n).padStart(2, "0");
    const KLASS = ["NA25", "TE25prk", "IN24prk", "NA24", "", "ma3c", "Ma 4"];
    const SEP = ["-", "_", ".", " ", ""];
    const ÄNDELSE = [".m4a", ".mp3", ".wav", ".MP3", ".m4a"];

    const ut = [];
    for (let i = 0; i < 1200; i++) {
      const år = heltal(2020, 2029);
      const mån = heltal(1, 12);
      const dag = heltal(1, 28);
      const tim = heltal(0, 23);
      const min = heltal(0, 59);
      const sep = SEP[heltal(0, SEP.length - 1)];
      const datumtext = `${år}${sep}${nolla(mån)}${sep}${nolla(dag)}`;
      const tidstext = [
        `kl ${nolla(tim)}.${nolla(min)}`,
        `${nolla(tim)}.${nolla(min)}`,
        `${nolla(tim)}:${nolla(min)}`,
        `${nolla(tim)}${nolla(min)}`,
        "",
      ][heltal(0, 4)];
      const namn = [KLASS[heltal(0, KLASS.length - 1)], datumtext, tidstext]
        .filter(Boolean).join(" ") + ÄNDELSE[heltal(0, ÄNDELSE.length - 1)];
      ut.push({ namn, år, mån, dag, tim, min, tidstext,
                datum: gissaDatum(namn), tid: gissaTid(namn) });
    }
    return ut;
  });

  const trasiga = [];
  for (const f of fall) {
    const vantat = `${f.år}-${String(f.mån).padStart(2, "0")}-${String(f.dag).padStart(2, "0")}`;
    // Datumet läses ur namnet — inte dagens datum, och inte ur klockslaget.
    if (f.år >= 2020 && f.år <= 2029 && f.datum !== vantat) {
      trasiga.push(`datum: ${f.namn} → ${f.datum} (väntat ${vantat})`);
    }
    // Tiden är antingen den som står i namnet eller ingen alls. Den får ALDRIG
    // komma ur datumsiffrorna.
    const vantadTid = f.tidstext
      ? `${String(f.tim).padStart(2, "0")}:${String(f.min).padStart(2, "0")}` : "";
    if (f.tid !== vantadTid) {
      trasiga.push(`tid: ${f.namn} → ${f.tid} (väntat ${vantadTid || "ingen"})`);
    }
  }
  expect(trasiga.slice(0, 10), `${trasiga.length} av ${fall.length} fall`).toEqual([]);
});

test("filnamn utan datum eller tid gissar inte fram något", async ({ page }) => {
  await fejka(page);
  await page.clock.install({ time: new Date("2026-09-08T08:00:00") });
  await page.goto("/");
  await hydrerad(page);

  const svar = await page.evaluate(() => ["Inspelning (3).m4a", "lektion.wav",
    "röstmemo 7.m4a", "NA25 halvklass.m4a", "ljud 2.mp3", "kapitel 1.1.m4a"]
    .map(n => ({ n, datum: gissaDatum(n), tid: gissaTid(n) })));

  for (const s of svar) {
    // Utan datum i namnet står dagens datum kvar — det är ett förval läraren
    // ser och kan ändra, inte en gissning som utger sig för att vara läst.
    expect(s.datum, s.n).toBe("2026-09-08");
    expect(s.tid, s.n).toBe("");
  }
});

test("2026-08-20 är ett datum, inte klockan 20:26", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);
  const svar = await page.evaluate(() => ({
    bara: { d: gissaDatum("2026-08-20.m4a"), t: gissaTid("2026-08-20.m4a") },
    ihop: { d: gissaDatum("20260820.m4a"), t: gissaTid("20260820.m4a") },
    med: { d: gissaDatum("NA25 2026-08-20 0905.m4a"),
           t: gissaTid("NA25 2026-08-20 0905.m4a") },
  }));
  expect(svar.bara).toEqual({ d: "2026-08-20", t: "" });
  expect(svar.ihop).toEqual({ d: "2026-08-20", t: "" });
  expect(svar.med).toEqual({ d: "2026-08-20", t: "09:05" });
});

// ── ISO-veckorna ─────────────────────────────────────────────────────────

test("veckonumren håller ISO över fyra hela år", async ({ page }) => {
  await fejka(page);
  await page.goto("/");
  await hydrerad(page);

  const fel = await page.evaluate(() => {
    /* Oberoende referens: ISO 8601 räknat på torsdagen i samma vecka. Den
       skrivs här, inte i appen, så ett fel i appens implementation inte kan
       göra sig självt rätt. */
    const isoRef = iso => {
      const d = new Date(iso + "T12:00:00Z");
      const dag = (d.getUTCDay() + 6) % 7;                 // mån=0
      d.setUTCDate(d.getUTCDate() - dag + 3);              // torsdagen
      const forsta = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
      const fdag = (forsta.getUTCDay() + 6) % 7;
      forsta.setUTCDate(forsta.getUTCDate() - fdag + 3);
      return 1 + Math.round((d - forsta) / (7 * 86400000));
    };
    const brister = [];
    const start = new Date(Date.UTC(2024, 0, 1));
    for (let i = 0; i < 4 * 366; i++) {
      const d = new Date(start.getTime() + i * 86400000);
      const iso = d.toISOString().slice(0, 10);
      const nr = window.Kalender.veckonr(iso);
      if (nr !== isoRef(iso)) { brister.push(`${iso}: ${nr} ≠ ${isoRef(iso)}`); continue; }
      // Måndagen i veckan är en måndag, ligger bakåt och i samma vecka.
      const man = window.Kalender.mandagen(iso);
      const md = new Date(man + "T12:00:00Z");
      if (md.getUTCDay() !== 1) brister.push(`${iso}: ${man} är ingen måndag`);
      if (man > iso) brister.push(`${iso}: måndagen ${man} ligger framåt`);
      if ((new Date(iso + "T12:00:00Z") - md) / 86400000 > 6) {
        brister.push(`${iso}: måndagen ${man} ligger mer än sex dagar bort`);
      }
      if (window.Kalender.veckonr(man) !== nr) {
        brister.push(`${iso}: måndagen hamnar i en annan vecka`);
      }
      if (brister.length > 20) break;
    }
    return brister;
  });
  expect(fel).toEqual([]);
});

test("varje vecka har sju dagar med samma nummer — också vecka 53",
  async ({ page }) => {
    await fejka(page);
    await page.goto("/");
    await hydrerad(page);

    const fel = await page.evaluate(() => {
      const brister = [];
      // Fyra årsskiften i rad, inklusive 2026→2027 (v53) och 2020→2021 (v53).
      for (const start of ["2020-12-21", "2021-12-27", "2026-12-21", "2027-12-27"]) {
        const nr = window.Kalender.veckonr(start);
        for (let i = 0; i < 7; i++) {
          const d = new Date(start + "T12:00:00Z");
          d.setUTCDate(d.getUTCDate() + i);
          const iso = d.toISOString().slice(0, 10);
          if (window.Kalender.veckonr(iso) !== nr) {
            brister.push(`${iso} bytte vecka mitt i veckan (${start} = v${nr})`);
          }
          if (window.Kalender.mandagen(iso) !== start) {
            brister.push(`${iso} pekar på fel måndag (${window.Kalender.mandagen(iso)} ≠ ${start})`);
          }
        }
      }
      return brister;
    });
    expect(fel).toEqual([]);
  });
