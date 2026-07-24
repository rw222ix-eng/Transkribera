// Planeringsarkivet: sparade tavlor och prov, sökbara och frågbara.
export const arkiv = $state({
  items: [],
  loading: false,
  error: '',
  // sök
  query: '',
  mode: 'ask',        // 'ask' = låt modellen svara | 'word' = ordsökning
  hits: null,         // null = ingen sökning gjord; [] = inga träffar
  searching: false,
  // fråga arkivet
  asking: false,
  answer: '',
  askedFor: '',       // frågan svaret gäller
  sources: [],        // vilka poster svaret bygger på
  scan: [],           // [{key, name, hits}] i genomsökningsordning
});

/** Nollställer sök- och svarsläget inför en ny fråga. */
export function resetSearch() {
  arkiv.hits = null;
  arkiv.answer = '';
  arkiv.sources = [];
  arkiv.scan = [];
  arkiv.askedFor = '';
}
