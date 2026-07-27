import { getJSON, streamPost } from '../api.js';
import { fmtTid } from '../transkript/tid.js';
import { oppnaTranskriptFor } from '../transkript/actions.js';
import { chatt } from './stores.svelte.js';

// Samtalen, per lektions-id. MODULPRIVAT, aldrig i storen — samma hållning som
// mediaelementet i B2 och resurserna i transkribera/inspelning.svelte.js. En
// vanlig Map i ett $state är dessutom inte djupreaktiv i Svelte 5, så den hade
// bara sett reaktiv ut. Storen bär den AKTUELLA tråden; kartan de vilande.
// Allt försvinner när appen stängs — inget skrivs till disk eller server.
const samtal = new Map();

// Egna räknare per väg. En delad hade låtit sändningen ogiltigförklara
// öppningen — samma regel som inspelningar/actions.js:45-57 beskriver.
let oppnaToken = 0;
let skickToken = 0;

// /api/chat avvisar tomt `model` (server.py:1643-1644) men skickar aldrig
// nyckeln vidare till llama.cpp (llm_client.py:229-233) — värdet kastas.
// Alternativet vore att bära det ur modellkatalogen, men den nya katalog-storen
// behåller bara whisper-listan, OCH /api/models gör en riktig hårdvaruskanning:
// chatten hade då inte gått att öppna förrän skanningen var klar, för ett värde
// servern kastar. Samma sträng som gamla appens ppModel-default (app.js:64).
// KÄND GRÄNS: börjar backenden hedra fältet blir konstanten fel.
const LLM_NAMN = 'Qwen3 14B (Q8_0)';

/** Synlig statusrad OCH annonsering. Enda vägen in — arten sätts med texten. */
export function satBesked(text, art = 'fel') {
  chatt.besked = text;
  chatt.beskedArt = art;
  chatt.annons = text;
}

/** Bara live-regionen. För text som ska höras men inte dubbleras på skärmen. */
export function annonsera(text) {
  chatt.annons = text;
}

/** Allt utom `tank`, som medvetet följer med — det är lärarens preferens. */
function nollstall() {
  chatt.segment = [];
  chatt.laddar = false;
  chatt.besked = '';
  chatt.beskedArt = 'fel';
  chatt.annons = '';
  chatt.trad = [];
  chatt.utkast = '';
  chatt.skickar = false;
  chatt.resonemangOppet = {};
  chatt.valtCitat = null;
}

/**
 * Öppnar chatten för en lektion och återställer ett tidigare samtal.
 *
 * Segmenten hämtas med getJSON, som kastar på !resp.ok. Gamla appens getJSON
 * (app.js:2983) är ett rått fetch().then(r => r.json()) UTAN ok-kontroll — och
 * servern svarar 404 med {"error": "finns inte"} (server.py:848), vilket är
 * giltig JSON. Dess .catch triggas därför aldrig, segmenten blir tomma, och
 * läraren får en tyst chatt som svarar att det inte framgår av transkriptet.
 */
export async function oppnaLektionschatt(lektion) {
  const id = (lektion && (lektion.history_id || lektion.id)) || null;
  const token = ++oppnaToken;
  nollstall();
  chatt.lektionId = id;
  chatt.namn = (lektion && (lektion.name || lektion.namn)) || '';
  // Kopia, inte referens: tråden muteras av skicka(), och kartan får inte
  // ändras under fötterna på ett samtal som ligger vilande.
  const sparat = id ? samtal.get(id) : null;
  chatt.trad = sparat ? sparat.map((m) => ({ ...m })) : [];
  chatt.open = true;

  if (!id) {
    satBesked('Kunde inte öppna chatten — inspelningen saknar en historikpost.');
    return;
  }

  chatt.laddar = true;
  try {
    const h = await getJSON('/api/history/' + encodeURIComponent(id));
    if (token !== oppnaToken) return;
    chatt.segment = Array.isArray(h.transcript) ? h.transcript : [];
  } catch {
    if (token !== oppnaToken) return;
    satBesked('Kunde inte läsa lektionens transkript — starta om appen och försök igen.');
  } finally {
    // finally kör även vid den tidiga return:en ovan, så laddflaggan måste
    // vara token-vaktad den också.
    if (token === oppnaToken) chatt.laddar = false;
  }
}

/** Sparar samtalet och stänger. Räknarna först, som i B2:s stangTranskript. */
export function stangLektionschatt() {
  oppnaToken++;
  skickToken++;
  if (chatt.lektionId && chatt.trad.length) {
    samtal.set(chatt.lektionId, chatt.trad.map((m) => ({ ...m })));
  }
  chatt.open = false;
  nollstall();
  chatt.lektionId = null;
  chatt.namn = '';
}

/** Öppnar B2:s transkriptvy OVANPÅ chatten. Samtalet ligger kvar. */
export function oppnaTranskriptet() {
  if (!chatt.lektionId) return;
  // Gamla appen stänger chatten först (app.js:4162) och kastar därmed hela
  // samtalet. Motiveringen var en z-index-stapel — transkriptmodalen låg på
  // 100, overlayen på 120. showModal() har ingen stapel: top-layer ordnar
  // rutorna i öppningsordning, så den här lägger sig ovanpå av sig själv.
  oppnaTranskriptFor(chatt.lektionId, chatt.namn);
}

export function vaxlaResonemang(mi) {
  chatt.resonemangOppet = { ...chatt.resonemangOppet, [mi]: !chatt.resonemangOppet[mi] };
}

/** Växling: samma citat igen fäller ihop källpanelen. */
export function valjCitat(mi, segIndex) {
  const samma = chatt.valtCitat && chatt.valtCitat.mi === mi && chatt.valtCitat.segIndex === segIndex;
  chatt.valtCitat = samma ? null : { mi, segIndex };
}

export function vaxlaTank() {
  chatt.tank = !chatt.tank;
}

/**
 * Ställer frågan och strömmar svaret.
 *
 * Två av gamla appens defekter bor här. `skickar` förblir sant till done ELLER
 * error; gamla appen släcker sin motsvarighet vid FÖRSTA token (app.js:2536-
 * 2537), vilket återaktiverar Skicka mitt i svaret och låter två strömmar
 * skriva till samma meddelande. Och varje event är token-vaktat; utan det kan
 * lektion A:s svar skriva över lektion B:s sista meddelande, eftersom
 * skrivningen bara kollar att tråden inte är tom (app.js:2527).
 */
export async function skicka() {
  const fraga = chatt.utkast.trim();
  if (!fraga || chatt.skickar || !chatt.lektionId) return;
  const token = ++skickToken;

  chatt.trad = [
    ...chatt.trad,
    { roll: 'anvandare', text: fraga, resonemang: '' },
    { roll: 'modell', text: '', resonemang: '' },
  ];
  chatt.utkast = '';
  chatt.skickar = true;
  chatt.besked = '';
  chatt.beskedArt = 'fel';
  annonsera('Svarar …');

  // Storen håller svenska fältnamn; API:t vill ha {role, content}. Skiftet
  // sker här, på ett ställe. Den tomma platshållaren filtreras bort — den är
  // en renderingsdetalj, inte ett meddelande.
  const messages = chatt.trad
    .filter((m) => !(m.roll === 'modell' && !m.text))
    .map((m) => ({ role: m.roll === 'anvandare' ? 'user' : 'assistant', content: m.text }));

  const transcript = chatt.segment
    .map((s, i) => '[' + (i + 1) + '] (' + fmtTid(s.start) + ') ' + (s.text || ''))
    .join('\n');

  let svar = '';
  let resonemang = '';

  const skrivSista = () => {
    const t = [...chatt.trad];
    if (t.length) t[t.length - 1] = { roll: 'modell', text: svar, resonemang };
    chatt.trad = t;
  };

  await streamPost(
    '/api/chat',
    {
      messages,
      transcript,
      model: LLM_NAMN,
      think: chatt.tank,
      cite: true,
      calendar: false, // kalendermaskineriet portas inte i B4
    },
    (ev) => {
      if (token !== skickToken) return;
      if (ev.type === 'token') {
        svar += ev.text || '';
        skrivSista();
      } else if (ev.type === 'reasoning') {
        resonemang += ev.text || '';
        skrivSista();
      } else if (ev.type === 'done') {
        // done bär HELA svaret (sse.py:27) — vi behöver inte lita på vår
        // egen ackumulering.
        svar = (ev.result && ev.result.text) || svar;
        skrivSista();
        chatt.skickar = false;
        // Först nu annonseras texten. Ett svar som växer sub-word för
        // sub-word vore oanvändbart att lyssna på.
        annonsera(svar || 'Svaret kom tomt.');
      } else if (ev.type === 'error') {
        chatt.skickar = false;
        // streamPost normaliserar även 400 och 409 hit. 409 betyder att GPU:n
        // är upptagen med en transkribering, och den texten kommer från
        // servern (server.py:1645-1648) — den är mer precis än vår.
        satBesked(ev.message || 'Kunde inte fråga lektionen — kontrollera att appen körs.');
      }
    },
  );

  // streamPost kastar aldrig, men en ström som slutar utan terminalt event
  // ger ett error-event ovan. Den här raden är bältet till hängslet.
  if (token === skickToken) chatt.skickar = false;
}
