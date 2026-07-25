import { tr } from './stores.svelte.js';

// Fasmodellen för en körning. Porterad ur gamla appens stageNames/stageBounds
// (app.js:290-296). Korrekturpasset finns bara när läraren bett om det OCH
// modellen är installerad — annars byter fasindelningen form.

/** Kommer den här körningen att korrekturläsa mot ljudet? app.js:290. */
export function willCorrect() {
  return !!(tr.audioCorrect && tr.audioModelInstalled);
}

/** Fasernas namn. app.js:291-295. */
export function stageNames() {
  return willCorrect()
    ? ['Förbereder', 'Extraherar ljud', 'Transkriberar', 'Korrekturläser', 'Färdigställer']
    : ['Förbereder', 'Extraherar ljud', 'Transkriberar', 'Färdigställer'];
}

/**
 * Procentgränserna mellan faserna. Alltid ETT element längre än stageNames —
 * både start och slut ingår. app.js:296.
 */
export function stageBounds() {
  return willCorrect() ? [0, 12, 28, 60, 92, 100] : [0, 12, 28, 92, 100];
}

/**
 * Vilken fas procenten hamnar i. En klar körning ger ett index bortom sista
 * fasen, så alla faser läses som avklarade. Speglar app.js:3172-3174.
 * @param {number} pct
 * @param {boolean} done
 */
export function phaseIndex(pct, done) {
  const namn = stageNames();
  const b = stageBounds();
  if (done) return namn.length;
  let i = 0;
  while (i < namn.length - 1 && pct >= b[i + 1]) i++;
  return i;
}
