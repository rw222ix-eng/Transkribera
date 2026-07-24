// Planeringsarkivet: sparade tavlor och prov, sökbara och frågbara.
import { getJSON } from '../api.js';

export const arkiv = $state({
  items: [],
  loading: true,
  error: '',
  // sök
  query: '',
  mode: 'ask',        // 'ask' = låt modellen svara | 'word' = ordsökning
  hits: null,         // null = ingen sökning gjord; [] = inga träffar
  searching: false,
  // fråga arkivet
  asking: false,
  answer: '',
  askError: '',       // felmeddelande — hålls isär från answer, se runAsk
  askedFor: '',       // frågan svaret gäller
  sources: [],        // vilka poster svaret bygger på
  scan: [],           // [{key, name, hits}] i genomsökningsordning
  // följdfrågor — fortsätter samtalet utan att söka om
  followups: [],      // [{q, a, typing, error}]
  followInput: '',
  run: 0,             // körtoken: en äldre ström får aldrig skriva i en nyare
});

/** Hämtar arkivlistan. Anropas vid montering och efter en ny sparad tavla —
 * se ArkivView.svelte och planering/actions.js: approveBoard(). */
export async function loadArkiv() {
  arkiv.loading = true;
  try {
    const d = await getJSON('/api/planning/archive');
    arkiv.items = d?.items ?? [];
    arkiv.error = '';
  } catch (e) {
    arkiv.error = 'Kunde inte hämta arkivet: ' + (e?.message || e);
  } finally {
    arkiv.loading = false;
  }
}

/** Nollställer sök- och svarsläget inför en ny fråga.
 * OBS: rör inte `run` här — det är en körtoken som bara ökar (se actions.js:
 * runAsk/sendFollow/clearSearch), aldrig återställs. */
export function resetSearch() {
  arkiv.hits = null;
  arkiv.answer = '';
  arkiv.askError = '';
  arkiv.sources = [];
  arkiv.scan = [];
  arkiv.askedFor = '';
  arkiv.followups = [];
  arkiv.followInput = '';
}
