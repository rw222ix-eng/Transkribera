// Sessionslagring för inspelningar. Den här modulen importerar MEDVETET
// ingenting: både actions.js och inspelning.svelte.js behöver den, och
// inspelning.svelte.js importerar actions.js. Vore den beroende av någon av
// dem skulle importgrafen bli cirkulär.
//
// Varför localStorage: markörerna och den valda codec:en måste överleva en
// krasch mitt i lektionen. Att lägga dem på servern hade krävt en ny endpoint,
// och migrationen får inte ändra något under app/.

const NYCKEL = 'transkribera.inspelning.';

/** Filändelsen för en inspelad mimeType. Speglar finishRecording, app.js:1471-1475. */
export function extAvMime(mime) {
  const t = mime && mime.indexOf('audio') === 0 ? mime : 'audio/webm';
  if (t.includes('ogg')) return 'ogg';
  if (t.includes('mp4')) return 'm4a';
  if (t.includes('mpeg')) return 'mp3';
  if (t.includes('wav')) return 'wav';
  return 'webm';
}

/** Skriver sessionens post. Tyst vid full eller avstängd lagring — en trasig
 *  localStorage får aldrig fälla en pågående inspelning. */
export function sparaSession(session, data) {
  try {
    localStorage.setItem(NYCKEL + session, JSON.stringify(data));
  } catch { /* lagringen är en bonus, inte ett krav */ }
}

/** Sessionens post, eller null. */
export function lasSession(session) {
  try {
    return JSON.parse(localStorage.getItem(NYCKEL + session) || 'null');
  } catch {
    return null;
  }
}

/** Glömmer sessionen. Anropas när markörerna postats eller sessionen slängts. */
export function glomSession(session) {
  try {
    localStorage.removeItem(NYCKEL + session);
  } catch { /* se sparaSession */ }
}

/** Städar poster vars session inte längre finns bland de oavslutade, så
 *  lagringen inte växer obegränsat. `levande` är en lista med sessions-id. */
export function stadaSessioner(levande) {
  try {
    const behall = new Set(levande);
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k && k.startsWith(NYCKEL) && !behall.has(k.slice(NYCKEL.length))) {
        localStorage.removeItem(k);
      }
    }
  } catch { /* se sparaSession */ }
}
