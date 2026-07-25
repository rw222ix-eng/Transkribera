import { getJSON } from '../api.js';

// Modellkatalogen och hårdvaran, hämtade i ETT anrop: /api/models svarar med
// {whisper, llm, online, hardware}. Speglar loadModels (app.js:3010-3030), men
// bara den del inställningssteget faktiskt renderar. Modellhanteraren med
// nedladdningar och kvantiseringschips hör till plan C.
export const katalog = $state({
  whisper: [],       // [{id, label, lang, score, size, vram, …}]
  installed: {},     // {id: true}
  vramFree: 0,       // GB ledigt grafikminne
  klar: false,       // katalogen är hämtad (motsvarar catalogReady)
});

/**
 * Hämtar katalogen. Returnerar `false` vid fel (nätverksfel eller ett svar
 * utan whisper-lista) så att anroparen kan berätta det för läraren —
 * katalog.klar förblir annars false utan förklaring, och startEtikett i
 * Installningar.svelte fastnar på "Laddar modeller …" i evighet. Modulen
 * känner inte till tr — den ska inte känna till storen; TranskriberaView:s
 * mount-effekt tolkar returvärdet och skriver på statusraden.
 */
export async function loadKatalog() {
  try {
    const d = await getJSON('/api/models');
    if (!d?.whisper) return false;
    katalog.whisper = d.whisper;
    const inst = {};
    for (const m of d.whisper) if (m.installed) inst[m.id] = true;
    katalog.installed = inst;
    katalog.vramFree = d.hardware?.vram?.free ?? 0;
    katalog.klar = true;
  } catch {
    return false;
  }
}

/**
 * Bästa INSTALLERADE modellen för språket, annars ''. Speglar recommendModel
 * (app.js:450-466) — inklusive dess viktigaste egenskap: det finns MEDVETET
 * ingen fallback över språkgränsen. En engelsk körning får aldrig tyst välja
 * en svensk modell; tomt svar gör att panelen ber om en nedladdning i stället.
 * @param {'sv'|'en'} sprak
 */
export function recommendModel(sprak) {
  const basta = (pred) => {
    let b = null;
    for (const m of katalog.whisper) {
      if (!katalog.installed[m.id] || !pred(m)) continue;
      if (!b || (m.score || 0) > (b.score || 0)) b = m;
    }
    return b ? b.id : null;
  };
  if (sprak === 'en') {
    return basta((m) => m.lang === 'en') || basta((m) => m.lang === 'multi') || '';
  }
  return basta((m) => m.lang === 'sv') || basta((m) => m.lang === 'multi') || '';
}

/** Modellens visningsnamn. */
export function modellNamn(id) {
  const m = katalog.whisper.find((x) => x.id === id);
  return m ? (m.label || m.id) : '';
}

/**
 * Statusprickens färg ur VRAM-marginalen. Samma trösklar som fitFor
 * (app.js:493-497): under noll är röd, under 1,5 GB marginal är gul.
 * Bara pricken — chipsen och verdikt-texten hör till plan C.
 */
export function fitDot(id) {
  const m = katalog.whisper.find((x) => x.id === id);
  if (!m) return 'var(--ink-3)';
  const head = katalog.vramFree - (m.vram || 0);
  if (head < 0) return 'var(--bad)';
  if (head < 1.5) return 'var(--warn)';
  return 'var(--ok)';
}
