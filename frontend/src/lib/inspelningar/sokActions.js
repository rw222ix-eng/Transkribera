import { getJSON } from '../api.js';
import { insp } from './stores.svelte.js';
import { sok } from './sok.svelte.js';

// EGEN räknare, aldrig delad med kartotekets laddToken: två snabba sökningar i
// följd kan annars landa i fel ordning och skriva ett äldre resultat över ett
// nyare. Samma mönster som laddaLektioner (actions.js:17-38) och korToken
// (transkribera/actions.js:314).
let sokToken = 0;

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
 * Rensar fältet och träffarna, men lämnar läget.
 *
 * Bumpar räknaren så att ett svar som redan är i luften inte får återuppliva
 * träfflistan efteråt — utan den kan läraren rensa fältet och ändå se träffar
 * dyka upp en sekund senare. soker nollställs av SAMMA skäl och hör ihop med
 * bumpen: ett svar i luften vars finally är vaktad (token !== sokToken) rör
 * aldrig soker, så utan raden nedan kan körknappen fastna i "Söker …".
 *
 * insp.fel/insp.felArt nollställs ÄVEN HÄR (RÄTTAT I SLUTGRANSKNINGEN, se
 * .superpowers/sdd/b3a-slutfix-report.md), av samma "läraren agerade"-skäl
 * som korSoknings tom-fråga-gren: utan raderna nedan kan ett gammalt
 * "Kunde inte söka — kontrollera att appen körs." stå kvar sedan kartoteket
 * redan kommit tillbaka.
 */
export function rensaSokning() {
  sokToken++;
  sok.fraga = '';
  sok.traffar = null;
  sok.soker = false;
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
