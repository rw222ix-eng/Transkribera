// Tidkoder och tidsuppslag för transkriptvyn. Ren modul — importerar ingenting.
//
// Egen modul och inte fmtTid ur transkribera/actions.js:297: den är modulprivat
// och saknar timkomponent, vilket är rätt där (loggraderna mäter körtid, som
// aldrig når en timme) och fel här. Gamla appens fmtTime (app.js:424) har samma
// brist och visar "78:03" för en lektion på en timme och 18 minuter.

/** Sekunder → "mm:ss" under en timme, "h:mm:ss" över. */
export function fmtTid(sekunder) {
  const n = Math.max(0, Math.floor(sekunder || 0));
  const timmar = Math.floor(n / 3600);
  const minuter = Math.floor((n % 3600) / 60);
  const s = String(n % 60).padStart(2, '0');
  const m = String(minuter).padStart(2, '0');
  return timmar ? `${timmar}:${m}:${s}` : `${m}:${s}`;
}

/**
 * Index för det segment som spelas vid `tid`, eller -1 före det första.
 *
 * Binärsökning, inte gamla appens linjära svep (app.js:3317). Svepet kördes
 * dessutom vid varje render av HELA appen, eftersom det låg ogrindat i vm().
 * Segmenten är sorterade på `start` — det är serverns kontrakt
 * (app/transcriber.py:211).
 */
export function aktuellRad(segment, tid) {
  let lo = 0;
  let hi = segment.length - 1;
  let svar = -1;
  while (lo <= hi) {
    const mitt = (lo + hi) >> 1;
    if ((segment[mitt].start ?? 0) <= tid) {
      svar = mitt;
      lo = mitt + 1;
    } else {
      hi = mitt - 1;
    }
  }
  return svar;
}
