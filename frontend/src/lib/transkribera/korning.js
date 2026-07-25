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

// ---- Mjuk, kontinuerlig framåtrörelse för progressbaren ---------------------
// Servern rapporterar i glesa hopp, och inte alls under t.ex. en nedladdning.
// Utan det här fryser baren och läraren drar slutsatsen att appen hängt sig.
// Visningsvärdet glider mot serverns värde och läcker långsamt framåt INOM
// aktuell fas mellan händelser. Monotont — det backar aldrig — och når 100
// först vid 'done'. Porterad ur _progFrame, app.js:2280-2308.

let rafId = 0;
let disp = 0;

function frame() {
  rafId = 0;
  if (tr.run !== 'running' && tr.run !== 'done') return;   // avbruten/fel/idle → stopp
  const real = Math.max(0, Math.min(100, tr.progress || 0));
  if (tr.run === 'done') {
    disp += (100 - disp) * 0.16;
    if (disp > 99.8) disp = 100;
  } else {
    const b = stageBounds();
    let ph = 0;
    while (ph < b.length - 2 && real >= b[ph + 1]) ph++;
    const tak = b[ph + 1] - 0.5;          // stanna inom aktuell fas
    if (real > disp) {
      disp += (Math.min(real, 99) - disp) * 0.12;   // hinn ikapp servern
    } else if (disp < tak) {
      disp += (tak - disp) * 0.004;                 // läck framåt så inget fryser
    }
    if (disp > 99) disp = 99;
  }
  tr.dispProgress = disp;
  if (tr.run === 'running' || disp < 100) rafId = requestAnimationFrame(frame);
}

/** Startar animeringen från nuvarande visningsvärde. app.js:2308. */
export function startProgressAnim() {
  disp = tr.dispProgress || 0;
  if (!rafId) rafId = requestAnimationFrame(frame);
}

/** Stoppar animeringen. Anropas vid avbrott och när vyn lämnas. */
export function stopProgressAnim() {
  if (rafId) cancelAnimationFrame(rafId);
  rafId = 0;
}
