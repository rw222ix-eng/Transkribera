// Källmodalens textmatchning. Porterad ur gamla appens _peekTerms/_segScores
// och fönsterberäkningen i openCitePeek (app/web/static/app.js:2392-2443).
//
// REN MODUL: inga runes, inga importer, inget tillstånd. Därför .js.

// Stoppord för matchningen. MEDVETET en egen lista, skild från backendens
// _STOPWORDS_SV (app/db.py:918-936): den här ska rensa bort ord som är vanliga
// i ett LLM-SVAR ("visar", "samband", "utdraget"), inte i ett transkript.
const STOPP = new Set(
  ('inte alla vara finns detta denna dessa vilket vilka också eller bara mycket sina hans hennes '
    + 'efter innan sedan under över genom fram från sägs nämns säger något någon handlar exempel '
    + 'inspelningen lektionen klippet sketchen tavlan provet skulle kommer kanske ganska väldigt '
    + 'samma andra olika visar samband källa källor utdrag utdragen').split(' '),
);

/**
 * Plockar ut sökbara ord ur frågan och svaret.
 *
 * MATCHNINGEN ANVÄNDER BÅDE FRÅGAN OCH SVARET, och det är hela poängen
 * (kommenterat i gamla appen, app.js:2389-2391): modellen omformulerar ofta —
 * frågan säger "stereotyper" om ett klipp som säger "fördomar" — så svarets
 * egna ord är den säkraste bryggan tillbaka till källraden.
 *
 * Ord kortare än fyra tecken faller bort. De matchar för mycket.
 */
export function peekTermer(text) {
  const sedda = new Set();
  const ut = [];
  for (const ord of String(text || '').toLowerCase().split(/[^a-zåäö0-9]+/i)) {
    if (ord.length >= 4 && !STOPP.has(ord) && !sedda.has(ord)) {
      sedda.add(ord);
      ut.push(ord);
    }
  }
  return ut;
}

/** Antal termer som förekommer i varje segment. */
export function segmentPoang(segment, termer) {
  return segment.map((s) => {
    const low = (s.text || '').toLowerCase();
    let n = 0;
    for (const t of termer) if (low.includes(t)) n++;
    return n;
  });
}

/**
 * Väljer ut fönstret som ska visas: två rader före träffen och fem efter.
 *
 * En rad räknas som träff vid **två** termer eller fler — ett ensamt ord är för
 * svagt. Undantaget är den bäst matchande raden, som alltid räknas så länge den
 * har minst en term; annars kan modalen öppnas helt utan markering.
 *
 * `fler` är antalet träffar som hamnade utanför fönstret, så modalen kan säga
 * att det finns mer att läsa i stället för att låtsas att detta var allt.
 */
export function valjRader(segment, termer) {
  const poang = segmentPoang(segment, termer);
  let bast = 0;
  poang.forEach((n, i) => {
    if (n > poang[bast]) bast = i;
  });
  const traffar = [];
  segment.forEach((_, i) => {
    if (poang[i] >= 2 || (i === bast && poang[bast] > 0)) traffar.push(i);
  });
  const mitt = traffar.length ? (traffar.includes(bast) ? bast : traffar[0]) : 0;
  const fran = Math.max(0, mitt - 2);
  const till = Math.min(segment.length, mitt + 5);
  return {
    rader: segment.slice(fran, till).map((s, i) => ({
      tid: s.tid,
      text: s.text,
      traff: traffar.includes(fran + i),
    })),
    fler: traffar.filter((i) => i < fran || i >= till).length,
  };
}

/**
 * Sekunder → "M:SS", eller "H:MM:SS" för inspelningar över en timme.
 * Speglar gamla appens fmtTime.
 */
export function tidsEtikett(sekunder) {
  const s = Math.max(0, Math.floor(Number(sekunder) || 0));
  const t = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  const tva = (n) => String(n).padStart(2, '0');
  return t > 0 ? `${t}:${tva(m)}:${tva(r)}` : `${m}:${tva(r)}`;
}
