// Sifferkällornas parser. Porterad ur gamla appens parseChatCites
// (app/web/static/app.js:1566-1601), bantad till det arkivsvaret behöver:
// den gamla varianten bar med sig segmentens tid och text för lektionschatten,
// medan arkivet bara behöver veta VILKEN källa ett nummer pekar på.
//
// REN MODUL: inga runes, inga importer, inget tillstånd. Därför .js och inte
// .svelte.js.

// Matchar [1], [1-3], [1–3], [1, 2] och [1–2, 5]. Tre siffror är taket, samma
// som gamla appen — fyra siffror i hakparentes är nästan alltid ett årtal.
const CITAT = /\[(\d{1,3}(?:\s*[,–—-]\s*\d{1,3})*)\]/g;

/**
 * Delar upp ett svar i text och källhänvisningar.
 *
 * Numren RÄKNAS OM i citeringsordning: citerar svaret bara källa 3 visas den
 * som [1]. Det är gamla appens beteende och det rätta — läsaren ska se en
 * obruten svit, inte modellens interna numrering.
 *
 * En hänvisning utanför källistan lämnas som TEXT i stället för att kastas
 * bort. Modellen hittar ibland på ett nummer, och att tyst radera det ur
 * svaret vore värre än att visa det som det står.
 *
 * Returnerar null när ingen giltig hänvisning hittades, så anroparen kan
 * rendera texten rå utan att gå igenom token-listan.
 */
export function parseCitat(text, antalKallor) {
  const s = String(text || '');
  const antal = Number(antalKallor) || 0;
  const tokens = [];
  const refs = [];
  const sedda = new Map(); // kallIndex → visningsnummer
  let sist = 0;
  let m;

  CITAT.lastIndex = 0;
  while ((m = CITAT.exec(s))) {
    const nummer = [];
    let giltig = true;
    for (const del of m[1].split(/\s*,\s*/)) {
      const intervall = del.match(/^(\d{1,3})\s*[–—-]\s*(\d{1,3})$/);
      if (intervall) {
        const a = parseInt(intervall[1], 10);
        const b = parseInt(intervall[2], 10);
        // b - a <= 30: ett "intervall" på hundra källor är inte en hänvisning
        // utan ett missförstånd. Samma tak som gamla appen.
        if (!(a >= 1 && b >= a && b <= antal && b - a <= 30)) { giltig = false; break; }
        for (let x = a; x <= b; x++) if (!nummer.includes(x)) nummer.push(x);
      } else if (/^\d{1,3}$/.test(del)) {
        const n = parseInt(del, 10);
        if (!(n >= 1 && n <= antal)) { giltig = false; break; }
        if (!nummer.includes(n)) nummer.push(n);
      } else {
        giltig = false;
        break;
      }
    }
    if (!giltig || !nummer.length) continue;

    const fore = s.slice(sist, m.index);
    if (fore) tokens.push({ text: fore });
    for (const n of nummer) {
      const kallIndex = n - 1;
      if (!sedda.has(kallIndex)) {
        sedda.set(kallIndex, refs.length + 1);
        refs.push({ num: refs.length + 1, kallIndex });
      }
      tokens.push({ cite: sedda.get(kallIndex), kallIndex });
    }
    sist = m.index + m[0].length;
  }

  if (!refs.length) return null;
  const rest = s.slice(sist);
  if (rest) tokens.push({ text: rest });
  return { tokens, refs };
}
