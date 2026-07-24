// Arkivets sök-/frågeaktioner: ordsökning, "fråga AI:n" med genomsöknings-SSE,
// och följdfrågor som fortsätter samtalet utan att söka om.
// Speglar app.js: runArkiv/runArkivAsk/sendArkivFollow/clearArkiv, se
// _arkRun-körtoken-kommentarerna där för varför `arkiv.run` bara ökar.
import { getJSON, streamPost } from '../api.js';
import { arkiv, resetSearch } from './stores.svelte.js';

/** Kalibrerar serverns felmeddelande till en lugn svensk text.
 * Delas av runAsk och sendFollow — samma tre fall som gamla appen. */
export function askFelText(message) {
  return /matchar sökningen/i.test(message || '')
    ? 'Ingen tavla och inget prov i arkivet verkar nämna det du frågar om. Prova att formulera om frågan.'
    : /network|failed to fetch|load failed/i.test(message || '')
    ? 'Anslutningen till appen bröts mitt i sökningen. Ställ frågan igen så görs ett nytt försök.'
    : 'Kunde inte svara: ' + (message || 'okänt fel');
}

/** Ordsökning i arkivet. */
export async function runSearch() {
  const q = arkiv.query.trim();
  if (!q || arkiv.searching) return;
  resetSearch();
  arkiv.searching = true;
  try {
    const d = await getJSON('/api/planning/archive/search?q=' + encodeURIComponent(q));
    arkiv.hits = d?.hits ?? [];
    arkiv.error = '';
  } catch (e) {
    arkiv.hits = [];
    arkiv.error = 'Sökningen misslyckades: ' + (e?.message || e);
  } finally {
    arkiv.searching = false;
  }
}

/** Frågar AI:n över arkivet, med live genomsöknings-progression. */
export async function runAsk() {
  const q = arkiv.query.trim();
  if (!q || arkiv.asking) return;
  const run = ++arkiv.run;
  resetSearch();
  arkiv.asking = true;
  arkiv.askedFor = q;
  try {
    await streamPost('/api/planning/ask', { q }, (ev) => {
      if (run !== arkiv.run) return; // en nyare fråga (eller Rensa) har tagit över
      if (ev.type === 'scan_plan') {
        arkiv.scan = (ev.items ?? []).map((i) => ({ ...i, hits: null }));
      } else if (ev.type === 'scan_result') {
        arkiv.scan = arkiv.scan.map((s) => (s.key === ev.key ? { ...s, ...ev } : s));
      } else if (ev.type === 'deep_read') {
        // deep_read anländer INNAN genereringen startar (se routes_planning.py)
        // — källorna sätts därför inte här, utan vid done. Annars visar
        // "Bygger på: …" som om svaret lyckats även när ett fel inträffar
        // mitt i strömmen.
      } else if (ev.type === 'token') {
        arkiv.answer += ev.text ?? '';
      } else if (ev.type === 'done') {
        arkiv.sources = ev.result?.sources ?? [];
      } else if (ev.type === 'error') {
        // Samma tre fall som den gamla appen (app.js: runArkivAsk) — ett
        // tomt arkiv ska kännas som ett ärligt svar, inte ett fel.
        arkiv.askError = askFelText(ev.message);
      }
    });
  } finally {
    if (run === arkiv.run) arkiv.asking = false;
  }
}

/** Rensar sök-/svarsläget och avbryter en eventuell pågående ström. */
export function clearSearch() {
  arkiv.run++; // överger en pågående ask/sendFollow-ström — se runAsk/sendFollow
  arkiv.query = '';
  resetSearch();
  arkiv.error = '';
}

/** Ställer en följdfråga: fortsätter samtalet utan att söka om.
 * Varje följdfråga har eget error-fält — till skillnad från gamla appen
 * (app.js: sendArkivFollow) maskeras aldrig ett fel som ett (trunkerat) svar. */
export async function sendFollow() {
  const q = arkiv.followInput.trim();
  if (!q || arkiv.asking) return;
  const run = ++arkiv.run;
  arkiv.followInput = '';
  arkiv.followups = [...arkiv.followups, { q, a: '', typing: true, error: '' }];

  /** Uppdaterar sista följdfrågan utan att röra de tidigare. */
  const patchLast = (fn) => {
    if (!arkiv.followups.length) return;
    const fs = arkiv.followups.slice();
    fs[fs.length - 1] = fn({ ...fs[fs.length - 1] });
    arkiv.followups = fs;
  };

  await streamPost('/api/planning/ask', { q }, (ev) => {
    if (run !== arkiv.run) return; // en nyare fråga har tagit över
    if (ev.type === 'token') {
      patchLast((f) => ({ ...f, a: f.a + (ev.text ?? '') }));
    } else if (ev.type === 'done') {
      patchLast((f) => ({ ...f, typing: false }));
    } else if (ev.type === 'error') {
      // Avvikelse från gamla appen (medveten): felet maskeras inte som svar.
      patchLast((f) => ({ ...f, typing: false, error: askFelText(ev.message) }));
    }
  });
}
