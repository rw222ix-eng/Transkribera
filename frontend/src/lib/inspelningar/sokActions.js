import { getJSON, streamPost } from '../api.js';
import { insp } from './stores.svelte.js';
import { sok } from './sok.svelte.js';

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
// ny fråga, rensning, fel, färdig utrullning — rensar den.
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
 * BODYN ÄR {q} OCH INGET MER. Gamla appen skickar alltid {q, calendar: true}
 * (app.js:1831), vilket ger modellen kalenderförmågan — och tvingar klienten
 * att stripCalTag varje token så en påbörjad [KALENDERFÖRSLAG]-rad aldrig
 * blinkar förbi. Serverns default är calendar: false, så utan flaggan uppstår
 * inga taggar och ingen strippning behövs. Kalenderkedjan får slå på den i sin
 * egen plan.
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
  try {
    await streamPost('/api/search/ask', { q }, (ev) => {
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
        sok.svar += ev.text || '';
        sok.notis = '';
      } else if (ev.type === 'done') {
        sok.svar = (ev.result && ev.result.text) || sok.svar;
        sok.kallor = (ev.result && ev.result.sources) || [];
        sok.notis = '';
        // ENDA annonseringen per fråga. Teatern renderas tyst — den uppdateras
        // var 60-150 ms och skulle bli en flod i en skärmläsare, och vyn har
        // redan sin enda annonserande nod.
        //
        // BARA om ingen annan äger statusraden. Ett DELETE-409 som landat under
        // strömmen är viktigare än vårt klarbesked, och B3a:s invariant säger
        // att ett svar aldrig får torka ett besked läraren inte hunnit läsa.
        if (!insp.fel) {
          const n = sok.kallor.length;
          insp.fel = n === 1 ? 'Svaret är klart — 1 källa.' : `Svaret är klart — ${n} källor.`;
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
  nollstallFraga();
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
 * ett RAG-svar. Det svaret finns inte i B3a, så asymmetrin har ingenting att
 * bevara. B3b får återinföra den när den betyder något, och ska då säga varför.
 */
export function valjLage(lage) {
  const nytt = lage === 'ask' ? 'ask' : 'keyword';
  if (sok.lage === nytt) return;
  sok.lage = nytt;
  rensaSokning();
}
