import { getJSON, streamPost } from '../api.js';
import { insp } from './stores.svelte.js';
import { sok } from './sok.svelte.js';
import { peekTermer, valjRader, tidsEtikett } from './kallmodal.js';
import {
  stripKalendertagg,
  tolkaForslag,
  tolkaFragor,
  startTid,
  arKalenderkommando,
  tolkaKommando,
} from './kalender.js';

// EGEN räknare, aldrig delad med kartotekets laddToken: två snabba sökningar i
// följd kan annars landa i fel ordning och skriva ett äldre resultat över ett
// nyare. Samma mönster som laddaLektioner (actions.js:17-38) och korToken
// (transkribera/actions.js:314).
let sokToken = 0;

// EGEN räknare för frågan, skild från sokToken: ordsöket och RAG-frågan är två
// olika hämtningar, och CLAUDE.md kräver en räknare per. streamPost saknar
// AbortController (verifierat: ingen finns någonstans i frontenden), så en
// övergiven ström rullar vidare hos servern — vakten filtrerar bort dess
// events, den stoppar dem inte.
let fragaToken = 0;

// setInterval-handtaget för utrullningen. MÅSTE ägas: timern lever i modulen,
// inte i en komponent, så en avmonterad vy städar den inte. Varje väg ut —
// ny fråga, rensning, fel, färdig utrullning — rensar den. `done` gör det
// MEDVETET INTE: genomsökningen ska alltid gå att följa med ögat, även när
// svaret kom blixtsnabbt, så timern får rulla klart på egen hand.
let utrullning = null;

function stoppaUtrullning() {
  if (utrullning !== null) {
    clearInterval(utrullning);
    utrullning = null;
  }
}

/**
 * Pacar utrullningen av genomsökningskorten.
 *
 * ÄRLIGHETSPRINCIPEN (docs/superpowers/specs/2026-07-18-arkivsok-live-progression-design.md):
 * datan är äkta, bara tempot är regisserat. Servern skickar alla scan_result
 * inom millisekunder (server.py:1582-1584), så träffantalen är kompletta innan
 * första kortet avslöjats — utrullningen finns bara för att förloppet ska gå
 * att följa med ögat.
 *
 * Taket är ~3,5 s oavsett arkivstorlek, golvet 60 ms per kort. Samma formel
 * som gamla appens startScanReveal (app.js:1808-1820).
 */
function startaUtrullning(antal) {
  stoppaUtrullning();
  if (!antal) return;
  // prefers-reduced-motion snappar fram allt direkt. Det kostar ingen
  // information — datan finns redan — bara tempot försvinner.
  if (typeof window !== 'undefined' && window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    sok.skanVisade = antal;
    return;
  }
  const steg = Math.max(60, Math.min(150, Math.round(3500 / antal)));
  utrullning = setInterval(() => {
    if (sok.skanVisade >= antal) {
      stoppaUtrullning();
      return;
    }
    sok.skanVisade += 1;
  }, steg);
}

/** Nollställer allt fråge-tillstånd utom fältets text. */
function nollstallFraga() {
  stoppaUtrullning();
  sok.skanPlan = null;
  sok.skanVisade = 0;
  sok.skanTraffar = {};
  sok.laser = [];
  sok.notis = '';
  sok.svar = '';
  sok.kallor = [];
  sok.fragaFel = '';
  // En ny fråga betyder ett nytt förslag. Gamla appen nollställer askEvent på
  // samma ställe (app.js:1824) — annars står gårdagens kalenderförslag kvar
  // under ett svar som inte handlar om det.
  sok.handelse = null;
  sok.kalFragor = null;
  sok.evValjare = false;
}

/**
 * Översätter ett serverfel till lärartext. Tre fall, ordagrant ur gamla appen
 * (app.js:1865-1869).
 *
 * ANSLUTNINGSFALLET MÅSTE NÄMNA streamPost:s EGEN STRÄNG. När strömmen tar
 * slut utan done eller error syntetiserar api.js:90-92
 * 'Anslutningen till servern bröts.' — den matchar varken "matchar sökningen"
 * eller de engelska nätverksmönstren, så utan den första alternativen nedan
 * hade den fallit till sista grenen och blivit
 * "Kunde inte söka: Anslutningen till servern bröts."
 */
export function fragaFelText(message) {
  const m = String(message || '');
  if (/matchar sökningen/i.test(m)) {
    return 'Ingen inspelning i arkivet verkar nämna det du frågar om. '
      + 'Prova att formulera om frågan, eller sök på enstaka ord under Sök ord.';
  }
  if (/anslutningen till servern bröts|network|failed to fetch|load failed/i.test(m)) {
    return 'Anslutningen till appen bröts mitt i sökningen. '
      + 'Ställ frågan igen så görs ett nytt försök.';
  }
  return 'Kunde inte söka: ' + (m || 'okänt fel');
}

/**
 * Ställer frågan och läser svaret ur SSE-strömmen.
 *
 * BODYN BÄR calendar: true, vilket ger modellen förmågan att föreslå en
 * kalenderhändelse (server.py:1417-1433). Priset är att varje token måste
 * strippas: modellens [KALENDERFÖRSLAG]-rad är maskinläsbar och ska aldrig
 * synas, inte ens halvströmmad som "[KALEN".
 *
 * Rå text ackumuleras i `acc`; sok.svar bär alltid den STRIPPADE versionen.
 * Taggarna tolkas ur den råa texten vid done — en halvströmmad JSON går inte
 * att tolka, och att försöka mitt i strömmen ger bara skräpförslag.
 *
 * insp.fel nollställs ÖVERST, aldrig på en framgångsgren — samma invariant som
 * B3a fastställde: nollställ när LÄRAREN AGERADE, aldrig när ett svar landade.
 */
export async function stallFraga() {
  const q = sok.fraga.trim();
  if (!q || sok.fragar) return;
  const token = ++fragaToken;
  nollstallFraga();
  insp.fel = '';
  insp.felArt = '';
  sok.fragar = true;
  let acc = '';
  try {
    await streamPost('/api/search/ask', { q, calendar: true }, (ev) => {
      // Vakten FÖRST: ett event från en övergiven ström får inte röra något.
      if (token !== fragaToken) return;

      if (ev.type === 'scan_plan') {
        // KAN KOMMA TVÅ GÅNGER. Ger ordsökningen noll träffar spelar servern
        // om hela genomsökningen med breddade söktermer (server.py:1478-1568).
        // Utrullningen måste därför börja om från noll, inte fortsätta.
        sok.skanPlan = ev.items || [];
        sok.skanVisade = 0;
        sok.skanTraffar = {};
        startaUtrullning(sok.skanPlan.length);
      } else if (ev.type === 'scan_result') {
        // Ny objektidentitet, inte mutation: $state-proxyn spårar tilldelningen.
        sok.skanTraffar = { ...sok.skanTraffar, [ev.key]: ev.hits };
      } else if (ev.type === 'deep_read') {
        sok.laser = ev.sources || [];
      } else if (ev.type === 'log') {
        sok.notis = ev.msg || '';
      } else if (ev.type === 'token') {
        acc += ev.text || '';
        sok.svar = stripKalendertagg(acc);
        sok.notis = '';
      } else if (ev.type === 'done') {
        const full = (ev.result && ev.result.text) || acc;
        sok.svar = stripKalendertagg(full);
        sok.kallor = (ev.result && ev.result.sources) || [];
        sok.notis = '';

        // KLARGÖRANDE FRÅGOR GÅR FÖRE ett förslag: svarar modellen med båda
        // menar den att förslaget är en gissning den vill ha bekräftad.
        const fragor = tolkaFragor(full);
        if (fragor) {
          sok.kalFragor = { fragor, extra: '' };
        } else {
          const forslag = tolkaForslag(full, sok.handelse);
          if (forslag) {
            sok.handelse = forslag;
            // Google-statusen hämtas FÖRST här — ingen anledning att fråga för
            // en lärare som aldrig ber om en kalenderhändelse.
            if (sok.calAnsluten === null) laddaCalStatus();
          }
        }
        // ENDA annonseringen per fråga. Teatern renderas tyst — den uppdateras
        // var 60-150 ms och skulle bli en flod i en skärmläsare, och vyn har
        // redan sin enda annonserande nod.
        //
        // BARA om ingen annan äger statusraden. Ett DELETE-409 som landat under
        // strömmen är viktigare än vårt klarbesked, och B3a:s invariant säger
        // att ett svar aldrig får torka ett besked läraren inte hunnit läsa.
        if (!insp.fel) {
          const n = sok.kallor.length;
          insp.fel = n === 0
            ? 'Svaret är klart.'
            : n === 1 ? 'Svaret är klart — 1 källa.' : `Svaret är klart — ${n} källor.`;
          insp.felArt = 'info';
        }
      } else if (ev.type === 'error') {
        // Utrullningen snappas fram så progressionen inte fryser mitt i.
        stoppaUtrullning();
        if (sok.skanPlan) sok.skanVisade = sok.skanPlan.length;
        sok.fragaFel = fragaFelText(ev.message);
        sok.notis = '';
      }
    });
  } finally {
    // Vaktad av samma skäl som vakten ovan: har en nyare fråga redan tagit över
    // räknaren ska den här strömmens slut inte släcka dess "Söker …".
    if (token === fragaToken) sok.fragar = false;
  }
}

/**
 * Kör ordsökningen. Anropas från Enter i fältet och från Sök-knappen — ALDRIG
 * per tangenttryck. Gamla appens per-tecken-beteende (onSearchInput,
 * app.js:1783-1788) drev bara titelfiltret av kartoteket, som utgår i den här
 * planen, så ingen debounce behövs.
 *
 * Söket är OFILTRERAT. api_search (app/web/server.py:1395-1410) tar inga
 * filterparametrar, så klass, kurs och månad påverkar inte träffarna. Det är
 * avsiktligt: läraren söker i arkivet, inte i sin nuvarande vy. Träffkortet
 * visar klass och kurs, så var träffen hör hemma går att se.
 *
 * Endpointen svarar ALLTID 200 — tom fråga ger tom lista, aldrig ett fel. Den
 * tidiga returen nedan finns ändå, så en tom fråga tar tillbaka kartoteket i
 * stället för att rendera "Inga lektioner matchade din sökning".
 */
export async function korSokning() {
  const q = sok.fraga.trim();
  if (!q) {
    // Samma generationsvakt som i rensaSokning, och av samma skäl: den här
    // grenen nollställer träffarna utan att starta en ny hämtning, så utan
    // bumpen får ett svar som redan är i luften skriva tillbaka dem.
    sokToken++;
    sok.traffar = null;
    // soker HÖR IHOP med bumpen ovan och måste nollställas av SAMMA skäl:
    // skriv ett ord, Enter (hämtning i luften, soker=true), töm fältet,
    // Enter igen — den här grenen körs, men det gamla svaret landar
    // FORTFARANDE. Dess try-grens finally är vaktad (token !== sokToken
    // efter bumpen ovan) och rör då aldrig soker, så utan raden nedan
    // fastnar körknappen i "Söker …"/disabled för alltid — enda vägen ut
    // vore att skriva om och trycka Enter. rensaSokning gör samma
    // nollställning, av exakt samma skäl.
    sok.soker = false;
    // insp.fel/insp.felArt nollställs HÄR OCKSÅ (RÄTTAT I SLUTGRANSKNINGEN,
    // se .superpowers/sdd/b3a-slutfix-report.md) — samma "läraren
    // agerade"-mönster som nollställningen längre ned i den vanliga vägen
    // bygger på. Läraren har just TÖMT fältet, vilket tar tillbaka
    // kartoteket; utan raderna nedan kan "Kunde inte söka — kontrollera att
    // appen körs." från ett tidigare misslyckat sök stå kvar sedan
    // kartoteket redan syns igen — ett besked om något som inte längre
    // visas. rensaSokning gör samma nollställning, av exakt samma skäl.
    insp.fel = '';
    insp.felArt = '';
    return;
  }
  // Nollställs HÄR, ÖVERST — samma mönster som markeraKlar och exporteraIcs
  // (actions.js): rensa statusraden innan hämtningen startar, inte på
  // framgångsgrenen efteråt. Låg nollställningen kvar där en sökningen just
  // lyckades stod kartoteket öppet för Radera/Redigera under HELA tiden
  // sökningen pågick (kartoteket lämnas orört tills svaret landar, se
  // InspelningarView.svelte), så ett fel som landade UNDER tiden — t.ex.
  // DELETE:ets 409 ("kunde inte radera mappen …", bekraftaRadera ovan) —
  // torkades bort så fort söksvaret kom tillbaka, och läraren hann aldrig
  // läsa det. bekraftaRadera avstår redan medvetet från att hämta om
  // lektionerna efter ett misslyckat DELETE av exakt det skälet; en
  // nollställning på korSoknings framgångsgren öppnade samma dörr från ett
  // nytt håll.
  insp.fel = '';
  insp.felArt = '';
  const token = ++sokToken;
  sok.soker = true;
  try {
    const res = await getJSON('/api/search?q=' + encodeURIComponent(q));
    if (token !== sokToken) return;
    sok.traffar = res && Array.isArray(res.hits) ? res.hits : [];
  } catch {
    if (token !== sokToken) return;
    // traffar tillbaka till NULL, alltså kartoteket — inte en tom träfflista.
    sok.traffar = null;
    insp.fel = 'Kunde inte söka — kontrollera att appen körs.';
    insp.felArt = '';
  } finally {
    // Vaktad av samma skäl som vakterna ovan: har en nyare sökning redan tagit
    // över räknaren ska det här svaret inte släcka dess "Söker …".
    if (token === sokToken) sok.soker = false;
  }
}

/**
 * Rensar fältet, träffarna OCH frågan, men lämnar läget.
 *
 * Bumpar BÅDA räknarna så att varken ett ordsökssvar eller en RAG-ström som
 * redan är i luften kan skriva tillbaka något efteråt. soker och fragar
 * nollställs av samma skäl: ett övergivet svars finally är vaktad och rör dem
 * aldrig, så utan raderna nedan kan körknappen fastna i "Söker …".
 *
 * Det här är också "✕ Ny fråga". Notera att den INTE är en avbrytning i
 * nätverksmening: streamPost saknar AbortController, så strömmen rullar vidare
 * hos servern tills LLM:en är klar och GPU-låset släpps först då. En ny fråga
 * direkt efteråt kan därför mötas av 409. Gamla appen beter sig likadant.
 *
 * insp.fel/insp.felArt nollställs av samma "läraren agerade"-skäl som i
 * korSokning: utan det kan ett gammalt besked stå kvar sedan ytan det gällde
 * redan försvunnit.
 */
export function rensaSokning() {
  sokToken++;
  fragaToken++;
  // Källmodalens och följdfrågornas räknare bumpas av samma skäl: en hämtning
  // eller ström som redan är i luften får inte skriva tillbaka något efteråt.
  kallaToken++;
  foljdToken++;
  nollstallFraga();
  sok.kalla = null;
  sok.foljdfragor = [];
  sok.foljdInput = '';
  sok.foljdSkriver = false;
  sok.fraga = '';
  sok.traffar = null;
  sok.soker = false;
  sok.fragar = false;
  insp.fel = '';
  insp.felArt = '';
}

/**
 * Byter läge. SYMMETRISKT: båda riktningarna nollställer fråga och träffar.
 *
 * Gamla appen är asymmetrisk här — setSearchMode (app.js:1779-1782) kör hela
 * clearSearch() mot keyword men tömmer bara träffarna mot ask, för att bevara
 * ett RAG-svar när läraren växlade bort och tillbaka. B3b HAR nu ett riktigt
 * RAG-svar (sok.svar, sok.kallor) och behöll ändå symmetrin, MED AVSIKT: att
 * bevara ett svar bakom ett lägesbyte gör tillståndet svårare att resonera
 * om (vilket svar hör till vilken fråga, i vilket läge?) för en marginell
 * vinst — läraren kan ställa om frågan. Ingen öppen TODO; symmetrin är den
 * avsedda formen, inte en plats att fylla senare.
 */
export function valjLage(lage) {
  const nytt = lage === 'ask' ? 'ask' : 'keyword';
  if (sok.lage === nytt) return;
  sok.lage = nytt;
  rensaSokning();
}

// EGNA räknare för källmodalen och följdfrågorna. Tre hämtningar i samma fil
// betyder tre räknare — en delad låter den ena ogiltigförklara den andra.
let kallaToken = 0;
let foljdToken = 0;

/**
 * Öppnar källmodalen för en sifferkälla i svaret.
 *
 * Matchningen använder termer ur BÅDE frågan och svaret. Modellen omformulerar
 * ofta — frågan säger "stereotyper" om ett klipp som säger "fördomar" — så
 * svarets egna ord är den säkraste bryggan tillbaka till källraden. Gamla
 * appens kommentar (app.js:2389-2391) säger samma sak.
 *
 * Modalen öppnas OMEDELBART med laddar: true, inte efter hämtningen. Ett klick
 * som inte gör något på en halv sekund läses som att knappen är trasig.
 */
export async function oppnaKalla(kalla) {
  if (!kalla) return;
  const token = ++kallaToken;
  sok.kalla = {
    namn: kalla.name || '(namnlös)',
    meta: [kalla.group, kalla.course, kalla.datum].filter(Boolean).join(' · '),
    laddar: true,
    rader: [],
    fler: 0,
    fel: false,
  };
  const hid = kalla.history_id || kalla.lesson_id;
  try {
    const h = await getJSON('/api/history/' + encodeURIComponent(hid));
    if (token !== kallaToken || !sok.kalla) return;
    const segment = ((h && h.transcript) || []).map((g) => ({
      tid: tidsEtikett(g.start),
      text: g.text,
    }));
    const { rader, fler } = valjRader(segment, peekTermer(sok.fraga + ' ' + sok.svar));
    sok.kalla = { ...sok.kalla, laddar: false, rader, fler };
  } catch {
    if (token !== kallaToken || !sok.kalla) return;
    sok.kalla = { ...sok.kalla, laddar: false, fel: true };
  }
}

/** Stänger källmodalen. Bumpar räknaren så en hämtning i luften inte kan
 *  återuppliva den efteråt. */
export function stangKalla() {
  kallaToken++;
  sok.kalla = null;
}

/**
 * Ställer en följdfråga.
 *
 * SKICKAR BARA {q} — inget samtalsminne, ingen kalenderflagga. Servern får
 * alltså ingen historik, vilket gör varje följdfråga till en fristående
 * arkivsökning. Det är gamla appens beteende (app.js:1937) och behålls; se
 * kommentaren i sok.svelte.js för vad det innebär för läraren.
 *
 * Egen generationsvakt, och bubblan patchas via index i stället för "sista
 * posten": hinner en rensning tömma listan medan strömmen lever skulle en
 * sista-posten-patch annars skriva i fel bubbla.
 */
export async function stallFoljdfraga() {
  const q = sok.foljdInput.trim();
  if (!q || sok.fragar || sok.foljdSkriver) return;

  // KORT ÄNDRINGSKOMMANDO mot ett befintligt förslag tolkas LOKALT, utan
  // LLM-anrop: "flytta till onsdag 14:30" behöver ingen språkmodell, och en
  // rundtur dit tar sekunder för något som ska kännas omedelbart.
  //
  // En TOM patch betyder att regexen inte förstod. Då faller frågan igenom som
  // en vanlig arkivsökning — att svara med hjälptexten på en riktig fråga vore
  // värre än att bara söka. Gamla appen gör samma val (app.js:1905-1916).
  if (arKalenderkommando(sok.handelse, q)) {
    const { patch, svar } = tolkaKommando(sok.handelse, q);
    if (Object.keys(patch).length) {
      sok.handelse = { ...sok.handelse, ...patch };
      sok.foljdfragor = [...sok.foljdfragor, { q, a: svar, skriver: false }];
      sok.foljdInput = '';
      return;
    }
  }

  const token = ++foljdToken;
  const index = sok.foljdfragor.length;
  sok.foljdfragor = [...sok.foljdfragor, { q, a: '', skriver: true }];
  sok.foljdInput = '';
  sok.foljdSkriver = true;
  let acc = '';
  const patcha = (fn) => {
    if (token !== foljdToken) return;
    const lista = sok.foljdfragor.slice();
    if (!lista[index]) return;
    lista[index] = fn({ ...lista[index] });
    sok.foljdfragor = lista;
  };
  try {
    // calendar: true även här — en följdfråga är oftast just den som ber om en
    // kalenderhändelse ("boka provet på fredag"). Taggarna strippas likadant.
    await streamPost('/api/search/ask', { q, calendar: true }, (ev) => {
      if (token !== foljdToken) return;
      if (ev.type === 'token') {
        acc += ev.text || '';
        patcha((f) => ({ ...f, a: stripKalendertagg(acc) }));
      } else if (ev.type === 'done') {
        const full = (ev.result && ev.result.text) || acc;
        patcha((f) => ({ ...f, skriver: false, a: stripKalendertagg(full) }));
        const fragor = tolkaFragor(full);
        if (fragor) {
          sok.kalFragor = { fragor, extra: '' };
        } else {
          const forslag = tolkaForslag(full, sok.handelse);
          if (forslag) {
            sok.handelse = forslag;
            if (sok.calAnsluten === null) laddaCalStatus();
          }
        }
      } else if (ev.type === 'error') {
        patcha((f) => ({ ...f, skriver: false, a: f.a || fragaFelText(ev.message) }));
      }
    });
  } finally {
    if (token === foljdToken) sok.foljdSkriver = false;
  }
}

/* ---- Kalenderkedjan -------------------------------------------------------
   Modellen kan svara med [KALENDERFÖRSLAG] eller [KALENDERFRÅGOR]. Båda
   raderna klipps ur svarstexten av stripKalendertagg innan den visas; det som
   blir kvar här är förslaget läraren granskar och godkänner.

   GOOGLE KALENDER ÄR APPENS ENDA VÄG UT UR MASKINEN — se kommentaren i
   sok.svelte.js. */

/** Hämtar Google-kopplingens status. Tyst: ett misslyckat statusanrop är
 *  inget läraren kan åtgärda, och förslaget ska ändå gå att granska. */
export async function laddaCalStatus() {
  try {
    const r = await getJSON('/api/calendar/status');
    sok.calAnsluten = !!(r && r.connected);
    sok.calKlientKlar = !!(r && r.client_ready);
  } catch {
    sok.calAnsluten = false;
    sok.calKlientKlar = false;
  }
}

/**
 * Startar Googles samtyckesflöde.
 *
 * `/api/calendar/connect` BLOCKERAR tills flödet är klart i webbläsaren
 * (server.py:1344-1348), så anropet kan stå öppet i minuter. Knappen låses
 * under tiden och släpps i finally — överger läraren inloggningen svarar
 * fetchen aldrig, och utan den raden hade knappen varit låst till omstart.
 */
export async function anslutCal() {
  if (sok.calAnsluten || sok.calUpptagen) return;
  sok.calUpptagen = true;
  insp.fel = '';
  insp.felArt = '';
  try {
    const r = await fetch('/api/calendar/connect', { method: 'POST' });
    const j = await r.json().catch(() => null);
    sok.calAnsluten = !!(j && j.connected);
    if (sok.calAnsluten) sok.calSetupOppen = false;
    else if (j && j.error) insp.fel = j.error;
  } catch {
    sok.calAnsluten = false;
  } finally {
    sok.calUpptagen = false;
  }
}

/** Öppnar det guidade uppsättningsfönstret och hämtar färsk status. */
export function oppnaCalSetup() {
  sok.calSetupOppen = true;
  laddaCalStatus();
}

export function stangCalSetup() {
  sok.calSetupOppen = false;
  sok.calUpptagen = false;
}

/** Öppnar Google Cloud Console i lärarens webbläsare. */
export function oppnaGoogleConsole() {
  fetch('/api/calendar/open-console', { method: 'POST' }).catch(() => {});
}

/**
 * Installerar OAuth-klientfilen läraren valt.
 *
 * Filen POSTas RÅ, inte som JSON-kropp: endpointen läser `await req.body()`
 * och validerar innehållet själv (server.py:1363-1379). Den avvisar kroppar
 * över 64 kB innan de buffras.
 */
export async function installeraKlientfil(fil) {
  if (!fil || sok.calUpptagen) return;
  sok.calUpptagen = true;
  insp.fel = '';
  insp.felArt = '';
  try {
    const text = await fil.text();
    const r = await fetch('/api/calendar/client-secret', { method: 'POST', body: text });
    const j = await r.json().catch(() => null);
    if (!r.ok) {
      insp.fel = (j && j.error) || 'Kunde inte installera klientfilen.';
      return;
    }
    insp.fel = 'Klientfilen är installerad.';
    insp.felArt = 'info';
    await laddaCalStatus();
  } catch {
    insp.fel = 'Kunde inte läsa klientfilen.';
  } finally {
    sok.calUpptagen = false;
  }
}

/** Sätter ett fält på förslaget. */
export function satHandelseFalt(nyckel, varde) {
  if (!sok.handelse) return;
  sok.handelse = { ...sok.handelse, [nyckel]: varde };
}

/** Dag- och tidväljaren. Dagen bär sitt ISO-datum, så ett val utanför
 *  etikettuppslaget ändå landar rätt i API-anropet. */
export function valjDag(etikett, iso) {
  if (!sok.handelse) return;
  const bitar = (sok.handelse.when || ' · ').split(' · ');
  sok.handelse = {
    ...sok.handelse,
    when: `${etikett} · ${bitar[1] || '08:00'}`,
    startIso: iso,
  };
}

export function valjTid(tid) {
  if (!sok.handelse) return;
  const bitar = (sok.handelse.when || ' · ').split(' · ');
  sok.handelse = { ...sok.handelse, when: `${bitar[0] || ''} · ${tid}` };
  sok.evValjare = false;
}

export function avfardaHandelse() {
  sok.handelse = null;
  sok.evValjare = false;
}

/**
 * Skickar händelsen till Google Kalender.
 *
 * Felet visas i vyns statusrad, inte som en toast: den nya frontenden har
 * ingen toast-mekanism, och ett misslyckat kalenderanrop är ett direkt svar på
 * ett klick — precis det insp.fel finns för.
 */
export async function laggTillHandelse() {
  const ev = sok.handelse;
  if (!ev || ev.busy || ev.added) return;
  sok.handelse = { ...ev, busy: true };
  insp.fel = '';
  insp.felArt = '';
  try {
    const r = await fetch('/api/calendar/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: ev.title,
        start: startTid(ev),
        description: ev.desc || '',
        end_date: ev.endIso || null,
      }),
    });
    const j = await r.json().catch(() => null);
    if (!r.ok) {
      sok.handelse = { ...sok.handelse, busy: false };
      insp.fel = (j && j.error) || 'Kunde inte skapa händelsen i Google Kalender.';
      insp.felArt = '';
      return;
    }
    sok.handelse = { ...sok.handelse, busy: false, added: true };
    insp.fel = 'Händelsen är tillagd i Google Kalender.';
    insp.felArt = 'info';
  } catch {
    sok.handelse = { ...sok.handelse, busy: false };
    insp.fel = 'Kunde inte nå Google Kalender — kontrollera att appen körs.';
    insp.felArt = '';
  }
}

/* ---- Modellens klargörande frågor ---- */

export function valjFragesvar(index, alternativ) {
  if (!sok.kalFragor) return;
  const fragor = sok.kalFragor.fragor.map((f, i) =>
    // Klick på ett redan valt alternativ nollställer det: läraren ska kunna
    // ångra utan att behöva stänga dialogen.
    i === index ? { ...f, val: f.val === alternativ ? null : alternativ } : f,
  );
  sok.kalFragor = { ...sok.kalFragor, fragor };
}

export function satFrageExtra(varde) {
  if (!sok.kalFragor) return;
  sok.kalFragor = { ...sok.kalFragor, extra: varde };
}

export function stangFragor() {
  sok.kalFragor = null;
}

/**
 * Skickar svaren tillbaka till modellen som en ny fråga.
 *
 * `hoppa` betyder "strunta i frågorna och gissa rimligt" — läraren ska aldrig
 * tvingas svara på tre frågor för att få en kalenderhändelse.
 */
export function skickaFragesvar(hoppa) {
  const cq = sok.kalFragor;
  if (!cq) return;
  let text;
  if (hoppa) {
    text = 'Skapa kalenderhändelsen direkt med rimliga antaganden.';
  } else {
    const delar = cq.fragor.map((f) => `${f.q} Svar: ${f.val || 'inget särskilt'}`);
    if ((cq.extra || '').trim()) delar.push(`Övrigt önskemål: ${cq.extra.trim()}`);
    text = delar.join(' · ') + ' — skapa nu kalenderhändelsen med en detaljerad anteckning utifrån detta.';
  }
  sok.kalFragor = null;
  sok.foljdInput = text;
  stallFoljdfraga();
}
