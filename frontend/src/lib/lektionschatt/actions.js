import { getJSON, streamPost } from '../api.js';
import { fmtTid } from '../transkript/tid.js';
import { oppnaTranskriptFor } from '../transkript/actions.js';
import { chatt } from './stores.svelte.js';
import { kal } from '../kalender/stores.svelte.js';
import { strippaTagg, tolkaForslag, tolkaFragor } from '../kalender/tagg.js';
import { tolkaKommando } from '../kalender/kommando.js';
import { nollstallForslag, hamtaStatus } from '../kalender/actions.js';

// Samtalen, per lektions-id. MODULPRIVAT, aldrig i storen — samma hållning som
// mediaelementet i B2 och resurserna i transkribera/inspelning.js. En
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
  // Kalenderförslaget hör till SAMTALET, precis som tråden — det får inte
  // överleva ett lektionsbyte eller en stängning. Se kalender/actions.js.
  // 'lektion' är lektionschattens värdnyckel i kal.forslag — arkivsvarets
  // motsvarande nollställning (inspelningar/sokActions.js:nollstallFraga)
  // använder 'arkiv'.
  nollstallForslag('lektion');
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
 * Skrivradens Skicka-knapp: tar frågan ur chatt.utkast och skickar den.
 * Själva sändningen (kalenderkommando-snabbvägen, POST:en, strömningen) är
 * utbruten till skickaFraga() nedan, som ÄVEN anropas från
 * kalender/FragekortModal.svelte med en konstruerad text (frågekortets
 * "Skapa direkt"/"Skapa förslaget") — samma sändningsväg, oavsett om texten
 * kom från skrivrutan eller frågekortet.
 */
export async function skicka() {
  const fraga = chatt.utkast.trim();
  if (!fraga || chatt.skickar || !chatt.lektionId) return;
  chatt.utkast = '';
  await skickaFraga(fraga);
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
 *
 * Guarden nedan (`!fraga || chatt.skickar || !chatt.lektionId`) är också
 * halva fixen för D2 (rekon §11): FragekortModal.svelte stänger ALDRIG
 * kal.fragor förrän den vet att den här funktionen faktiskt kommer köra —
 * se den modalens paSvara() och dess kommentar om den andra halvan.
 */
export async function skickaFraga(fraga) {
  if (!fraga || chatt.skickar || !chatt.lektionId) return;

  // Kalenderkommandon ("flytta till onsdag 14:30", "kortare titel" …)
  // tolkas lokalt utan LLM-anrop när ett förslag redan finns och inte är
  // tillagt — speglar gamla appens snabbväg (app.js:2501-2521). Grinden
  // (isCal/calComplex) ligger inuti tolkaKommando själv (se kommando.js),
  // så den enda regeln här är "körs alltid, lita på ett tomt resultat".
  // (Ett frågekortssvar når aldrig hit ändå: kal.forslag.lektion är null
  // under STEG 1 — se tagg.js — så villkoret nedan är automatiskt falskt då.)
  if (kal.forslag.lektion && !kal.forslag.lektion.tillagd) {
    const { patch, gjort } = tolkaKommando(fraga, kal.forslag.lektion);
    if (gjort.length) {
      Object.assign(kal.forslag.lektion, patch);
      const svarText = 'Klart — jag ändrade ' + gjort.join(' och ') + '.';
      chatt.trad = [
        ...chatt.trad,
        { roll: 'anvandare', text: fraga, resonemang: '' },
        { roll: 'modell', text: svarText, resonemang: '' },
      ];
      chatt.besked = '';
      chatt.beskedArt = 'fel';
      annonsera(svarText);
      return;
    }
  }

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

  // Modellen kan skapa/ändra kalenderförslaget direkt ur samtalet: den får
  // det aktuella förslaget och svarar med en [KALENDERFÖRSLAG]-rad som
  // tolkas i done-grenen nedan. Speglar app.js:2530-2534.
  const calEv = kal.forslag.lektion && !kal.forslag.lektion.tillagd
    ? {
        title: kal.forslag.lektion.titel,
        date: kal.forslag.lektion.startIso || null,
        time: (kal.forslag.lektion.nar || '').slice(-5),
        end_date: kal.forslag.lektion.slutIso || null,
        desc: kal.forslag.lektion.anteckning || '',
      }
    : null;

  // `raw` är modellens otolkade text (kan innehålla en kalendertagg); `svar`
  // är vad som faktiskt visas — alltid taggstrippad, även halvströmmad, så
  // en rå [KALENDERFÖRSLAG]-rad aldrig flimrar fram innan svaret är klart.
  let raw = '';
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
      calendar: true,
      cal_event: calEv,
    },
    (ev) => {
      if (token !== skickToken) return;
      if (ev.type === 'token') {
        raw += ev.text || '';
        svar = strippaTagg(raw);
        skrivSista();
      } else if (ev.type === 'reasoning') {
        resonemang += ev.text || '';
        skrivSista();
      } else if (ev.type === 'done') {
        // done bär HELA svaret (sse.py:27) — vi behöver inte lita på vår
        // egen ackumulering.
        const full = (ev.result && ev.result.text) || raw;

        // Klargörande frågor (STEG 1) före ett nytt förslag, eller själva
        // förslaget (STEG 2) — aldrig båda i samma svar. tolkaFragor provas
        // först, precis som applyCalQ gjorde före applyCalTag (app.js:2542-
        // 2543).
        let taggBesked = null;
        let fel = null;
        const fr = tolkaFragor(full);
        if (fr.hittad && fr.fragor) {
          // Frågekortet: öppnar FragekortModal.svelte med alternativ-korten.
          // `val` (vald-state) hör inte hemma i tolkaFragor (se tagg.js) —
          // läggs på här, vid öppning. tolkaFragor speglade tidigare bara
          // applyCalQ:s parsning (rekon §11); denna omgång kopplar in kortet.
          kal.fragor = { vard: 'lektion', fragor: fr.fragor.map((f) => ({ ...f, val: null })), fritext: '' };
          taggBesked = 'Några frågor innan jag skapar förslaget — svara i kortet som öppnats.';
        } else if (fr.hittad) {
          // D3: taggen fanns men gick inte att tolka. Strippas ändå (nedan)
          // — aldrig rå JSON kvar i bubblan.
          fel = 'Kalenderfrågorna gick inte att tolka — skriv gärna om vad du vill boka.';
        } else {
          const fs = tolkaForslag(full, kal.forslag.lektion);
          if (fs.hittad && fs.forslag) {
            kal.forslag.lektion = fs.forslag;
            if (kal.ansluten === null) hamtaStatus();
            taggBesked = 'Här är kalenderförslaget: "' + (fs.forslag.titel || '') + '" · ' + fs.forslag.nar
              + (fs.forslag.slutDag ? ' → ' + fs.forslag.slutDag : '')
              + '. Inget läggs in förrän du godkänner med Lägg till.';
          } else if (fs.hittad) {
            // D3, samma fix för [KALENDERFÖRSLAG].
            fel = 'Kalenderförslaget gick inte att tolka — skriv gärna om vad du vill boka.';
          }
        }

        // Svarar modellen med enbart kalenderraden blir bubblan annars tom.
        svar = strippaTagg(full);
        if (!svar && taggBesked) svar = taggBesked;
        if (!svar && fel) svar = 'Kalenderdelen av svaret gick inte att tolka.';
        skrivSista();
        chatt.skickar = false;
        if (fel) {
          // satBesked sätter både den synliga statusraden och annonseringen
          // i ett svep — anropas i stället för annonsera() här, annars
          // skriver den över felet en rad längre ner.
          satBesked(fel);
        } else {
          // Först nu annonseras texten. Ett svar som växer sub-word för
          // sub-word vore oanvändbart att lyssna på.
          annonsera(svar || 'Svaret kom tomt.');
        }
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
