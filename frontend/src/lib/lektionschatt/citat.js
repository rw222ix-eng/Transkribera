// Källciteringar i ett modellsvar. Ren modul — importerar ingenting.
//
// ETT pass ger både renderingsbitarna och källorna. Gamla appen kör
// parseChatCites för alla meddelanden vid varje rAF-render (app.js:4197 →
// 1541), alltså tiotals gånger i sekunden medan ett svar strömmar.

// Speglar regexen i app.js:1566: [3], [3, 7], [1–3], [1-3].
const CITAT = /\[(\d{1,3}(?:\s*[,–—-]\s*\d{1,3})*)\]/g;

// Ett längre intervall är nästan säkert inte en källhänvisning utan något
// modellen råkat skriva. Samma tak som gamla appen.
const MAX_INTERVALL = 30;

/**
 * Segmentindex (0-baserade) för en hakparentes innehåll, eller null om något
 * nummer ligger utanför transkriptet. null betyder "lämna som ren text" —
 * hellre en synlig hakparentes än en knapp som pekar på ingenting.
 */
function tolkaNummer(ra, antal) {
  const ut = [];
  for (const del of ra.split(',')) {
    const bit = del.trim();
    const intervall = /^(\d{1,3})\s*[–—-]\s*(\d{1,3})$/.exec(bit);
    if (intervall) {
      const fran = Number(intervall[1]);
      const till = Number(intervall[2]);
      if (till < fran || till - fran + 1 > MAX_INTERVALL) return null;
      for (let n = fran; n <= till; n++) {
        if (n < 1 || n > antal) return null;
        ut.push(n - 1);
      }
    } else {
      const n = Number(bit);
      if (!Number.isInteger(n) || n < 1 || n > antal) return null;
      ut.push(n - 1);
    }
  }
  return ut.length ? ut : null;
}

/**
 * Styckar ett svar i renderbara bitar och plockar ut källorna.
 *
 * Returnerar `{bitar, kallor}` där en bit är antingen `{text}` eller
 * `{citat: {segIndex, nummer}}`, och `kallor` är de citerade segmenten i
 * visningsordning, en gång var.
 *
 * Visningsnumren räknas om per meddelande i citeringsordning, som i gamla
 * appen (app.js:1590): segment [47] i transkriptet visas som 1 om det är
 * svarets första källa.
 */
export function parseCitat(text, segment) {
  const s = text || '';
  const antal = Array.isArray(segment) ? segment.length : 0;
  const bitar = [];
  const kallor = [];
  const sedda = new Map(); // segIndex → visningsnummer

  let pos = 0;
  CITAT.lastIndex = 0;
  let m;
  while ((m = CITAT.exec(s)) !== null) {
    const index = tolkaNummer(m[1], antal);
    // Ogiltig hänvisning: pos flyttas inte, så hakparentesen följer med i
    // nästa textbit och syns som den skrevs.
    if (!index) continue;

    if (m.index > pos) bitar.push({ text: s.slice(pos, m.index) });
    for (const segIndex of index) {
      let nummer = sedda.get(segIndex);
      if (nummer === undefined) {
        nummer = kallor.length + 1;
        sedda.set(segIndex, nummer);
        kallor.push({ segIndex, nummer });
      }
      bitar.push({ citat: { segIndex, nummer } });
    }
    pos = m.index + m[0].length;
  }
  if (pos < s.length) bitar.push({ text: s.slice(pos) });

  return { bitar, kallor };
}
