import { expect, test } from "@playwright/test";
import * as L from "./larardag.mjs";

/* APAN — slumpmässig men SEEDAD misshandel av varje vy (Etapp 4.3)
 *
 * Filen heter zz- för att den ska köras SIST. Apan klickar också på det
 * destruktiva — «Radera», «Börja om», markera-allt — och sviten delar bas.
 * Kördes den mitt i skulle nästa spec mäta apans städning i stället för sitt
 * eget arbete.
 *
 * Lärardagarna kör appen som den är tänkt att köras. Apan gör tvärtom: den
 * klickar där ingen skulle klicka, i en ordning ingen skulle välja, mitt i
 * animationer och halvöppna paneler. Det är den enda sortens test som hittar
 * «klick på Godkänn innan pappret ritats färdigt» och «Escape mitt i
 * bokremsan» — fel som aldrig står i något flöde.
 *
 * Kravet är lågt men absolut: appen får inte skriva ett enda fel i konsolen,
 * och den måste svara efteråt. Ett obehandlat undantag i en klickhanterare
 * lämnar gränssnittet i ett halvläge — knappen som inte längre går att trycka
 * på, panelen som inte går att stänga — och läraren märker det först när hon
 * behöver det som inte fungerar.
 *
 * gremlins.js valdes bort: biblioteket hade behövt vendreras in i repot (CDN
 * är uteslutet — offline-testet är svitens viktigaste), och det appen behöver
 * är trettio rader seedad slump, inte ett bibliotek. Seeden är fast: en röd
 * körning går att köra om exakt, och siffran i felutskriften säger vilket varv
 * som fällde den.
 */

/** Trettio rader apa, körda inne i sidan. Returnerar loggen över vad den gjorde. */
const APAN = ({ varv, seed }) => new Promise(klar => {
  let s = seed;
  const slump = () => {
    s |= 0; s = (s + 0x6D2B79F5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const heltal = n => Math.floor(slump() * n);
  const logg = [];

  /* Vad apan får röra. Filväljare öppnar ett systemfönster som ingen kan
     stänga, och en länk ut ur appen avslutar körningen — resten är fritt
     vilt, inklusive det destruktiva: basen är temporär. */
  const VAL = 'button, [role="tab"], [role="button"], .lekt, .kalla, .lagekort,'
    + ' .bkbokrad, .bksida, .tbv, input[type="checkbox"], input[type="radio"],'
    + ' select, .rattfalt, .komini, [data-el]';
  const synlig = el => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const st = getComputedStyle(el);
    return st.visibility !== "hidden" && st.display !== "none" && !el.disabled;
  };
  const kandidater = () =>
    [...document.querySelectorAll(VAL)].filter(el =>
      synlig(el) && !el.closest("[hidden]") && el.type !== "file");

  const TANGENTER = ["Escape", "Tab", "Enter", " ", "ArrowDown", "ArrowUp",
                     "ArrowLeft", "ArrowRight"];
  const TEXT = ["derivata", "4.2", "x^2", "", "  ", "åäö", "12", "-1",
                "9999999999", "<b>hej</b>"];

  let i = 0;
  const steg = () => {
    if (i++ >= varv) return klar(logg);
    const tarning = slump();
    try {
      if (tarning < 0.62) {
        const lista = kandidater();
        if (lista.length) {
          const el = lista[heltal(lista.length)];
          logg.push(`${i} klick ${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}`);
          el.click();
        }
      } else if (tarning < 0.78) {
        const t = TANGENTER[heltal(TANGENTER.length)];
        logg.push(`${i} tangent ${t}`);
        (document.activeElement || document.body).dispatchEvent(
          new KeyboardEvent("keydown", { key: t, bubbles: true }));
      } else if (tarning < 0.9) {
        const falt = [...document.querySelectorAll("input[type='text'], input:not([type]), input[type='number'], textarea")]
          .filter(synlig);
        if (falt.length) {
          const f = falt[heltal(falt.length)];
          const v = TEXT[heltal(TEXT.length)];
          logg.push(`${i} skriv ${f.id || f.className}="${v}"`);
          f.value = v;
          f.dispatchEvent(new Event("input", { bubbles: true }));
          f.dispatchEvent(new Event("change", { bubbles: true }));
        }
      } else {
        logg.push(`${i} rulla`);
        window.scrollTo(0, heltal(document.body.scrollHeight));
      }
    } catch (e) {
      /* Ett undantag HÄR är apans eget (elementet försvann mellan urval och
         klick) — appens undantag fångas av pageerror-vakten utanför. */
      logg.push(`${i} apan halkade: ${e.message}`);
    }
    setTimeout(steg, 12);
  };
  steg();
});

/** Svarar appen fortfarande? Ett halvläge syns här och ingen annanstans.
 *
 *  Apan har ofta klickat sig vidare i stegen, så testet frågar inte efter en
 *  bestämd knapp — det frågar om vyerna fortfarande GÅR ATT BYTA och om det
 *  som ritas är något. En app som fastnat i en modal eller kastat i en
 *  klickhanterare klarar inte det. */
async function levande(page) {
  /* Apan lämnar ofta en modal öppen, och den stängs i LAGER: videon först,
     sedan helskärmsläget, sedan rutan (lektion.js tangent) — och står
     markören i ett fält går första Escape till att lämna fältet. Fyra tryck
     räcker för varje kedja appen har. Att rutan GÅR att stänga är en del av
     det testet frågar om; en modal som inte lyssnar hade fastnat här. */
  for (let i = 0; i < 4; i++) {
    if (!await page.locator(".modalskal[data-pa], .modalskal:not([hidden])")
      .first().isVisible().catch(() => false)) break;
    await page.keyboard.press("Escape");
    await page.waitForTimeout(250);
  }
  await page.keyboard.press("Escape");
  await page.getByRole("tab", { name: "Planering" }).click({ timeout: 15_000 });
  await expect(page.locator("#schemavecka")).toContainText("Vecka");
  /* Veckan kan glida in (klass.js byt, 175 + 20 + 300 ms). Det som prövas är
     att veckan RITAS — inte att den innehåller lektioner: apan bläddrar gärna
     till ett lov eller ut ur läsåret, och en tom vecka är ett riktigt svar. */
  await page.waitForTimeout(700);
  expect(await page.locator("#schemagrid .skdag").count()).toBeGreaterThan(0);
  await page.getByRole("tab", { name: "Transkribera" }).click({ timeout: 15_000 });
  await expect(page.locator("#vy-transkribera")).toBeVisible();
  await expect(page.locator("#vy-transkribera [data-steg]:not([hidden])").first())
    .toBeVisible();
}

/* Apans första fynd, pinnat som ett vanligt flöde: en seedad körning bevisar
   inte samma sak två gånger, och den här buggen ska aldrig komma tillbaka. */
test("döpa om en inspelning och klicka vidare kraschar inte listan",
  async ({ page }) => {
    const fel = L.vakt(page);
    await L.fejkatMoln(page);
    await L.oppna(page);
    // Inspelningarna är ett SÖKLÄGE i arkivfältet — och arkivfältet bor i
    // planeringsvyn.
    await page.getByRole("tab", { name: "Planering" }).click();
    /* Listan ritas ur inspelningskorten (#inspelningar .kort), som hydreras ur
       /api/history. Svitens bas är tom, så korten läggs in här — det som ska
       prövas är listans egen händelsekedja, inte varifrån raderna kom. */
    await page.evaluate(() => {
      const vard = document.querySelector("#inspelningar");
      vard.innerHTML = "";
      [["NA25 måndag", "2026-09-07", "NA25"], ["TE25prk tisdag", "2026-09-08", "TE25prk"]]
        .forEach(([namn, datum, klass]) => {
          const k = document.createElement("article");
          k.className = "kort";
          k.dataset.datum = datum;
          k.dataset.klass = klass;
          k.dataset.kurs = "Matematik, nivå 2c";
          k.innerHTML = '<span class="namn"></span><span class="tumlangd">45 min</span>';
          k.querySelector(".namn").textContent = namn;
          vard.appendChild(k);
        });
      window.Inspelningar.lage(true);
    });
    const rader = page.locator("#insplada .ilrad");
    await expect(rader.first()).toBeVisible();
    expect(await rader.count()).toBe(2);

    // Döp om den första — fältet tar fokus — och klicka sedan på ANNAT i
    // lådan. Blur ritade då om hela lådan (innerHTML) mitt i klicket, och
    // webbläsaren kastade: «The node to be removed is no longer a child of
    // this node. Perhaps it was moved in a 'blur' event handler?»
    await rader.first().locator("[data-dop]").click();
    const falt = page.locator("#insplada .ildop");
    await expect(falt).toBeVisible();
    await falt.fill("Omdöpt av testet");
    /* Klicket dispatchas i sidan, inte med musen: då ligger fokus KVAR i
       fältet när kryssrutans hanterare ritar om lådan, och det är blur —
       utlöst mitt i innerHTML-bytet, av att fältet rycks ur trädet — som
       kastade. Med muspekaren blurrar fältet först och kedjan blir en annan. */
    await page.evaluate(() => document.querySelectorAll("#insplada .ilrad")[1]
      .querySelector(".ilkryss").click());

    await page.waitForTimeout(400);
    await expect(page.locator("#insplada .ilrad").first()).toContainText("Omdöpt av testet");
    L.rent(fel);
  });

const VYER = [
  { namn: "transkribering", flik: "Transkribera", seed: 4711 },
  { namn: "planering", flik: "Planering", seed: 90210 },
  { namn: "planering, steg för steg", flik: "Planering", seed: 13,
    innan: async page => page.evaluate(() => {
      window.PlanSteg.las(2, false); window.PlanSteg.gaTill(2);
    }) },
  { namn: "veckan i terminsläge", flik: "Planering", seed: 555,
    innan: async page => page.locator("#schemalage button", { hasText: "Termin" }).click() },
];

for (const vy of VYER) {
  test(`apan i ${vy.namn} lämnar inget fel i konsolen`, async ({ page }) => {
    test.setTimeout(180_000);
    const fel = L.vakt(page);
    await L.fejkatMoln(page);
    await L.oppna(page);
    await page.getByRole("tab", { name: vy.flik }).click();
    if (vy.innan) await vy.innan(page);

    const logg = await page.evaluate(APAN, { varv: 400, seed: vy.seed });
    expect(logg.length).toBeGreaterThan(300);

    // Ge påbörjade anrop en chans att svara — ett fel som kommer efter att
    // apan slutat är lika mycket ett fel.
    await page.waitForTimeout(1500);
    /* Två svar som INTE är 2xx är väntade och tas om hand i appen; webbläsaren
       loggar dem ändå:
         · /api/sample 404 — det finns ingen exempelfil på den här maskinen.
           Knappen faller tillbaka på prototypens namn (app.js, try/catch).
         · /api/schema/synk 409 — Google Kalender är inte kopplad i svitens bas.
           Synkraden visar serverns besked som en toast (klass.js).
         · /api/exams/generate 400 — apan trycker Skriv utan att ha valt kurs.
           Servern svarar «välj en kurs» och skrivrutan visar det; att appen
           frågar utan kurs är apans verk, inte appens.
         · /api/planning/generate 400 och 409 — samma sak för tavlan. 409:an
           kommer när apan hinner trycka Skriv två gånger: GPU-låset är taget av
           det första jobbet och servern svarar «upptagen», precis som den ska.
           Att det bara syns ibland är tajming — på CI:s långsammare maskin
           landar andra klicket oftare innan första jobbet släppt (2026-08-09). */
    L.rent(fel, { tillat: [/api\/sample/, /api\/schema\/synk/,
                           /api\/exams\/generate/, /api\/planning\/generate/] });
    await levande(page);
  });
}
