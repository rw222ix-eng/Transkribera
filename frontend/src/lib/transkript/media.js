// Vilket medieelement en inspelning ska spelas i, och vilken URL det får.
// Ren modul — importerar ingenting.

// Behållarformat som renderas som <video>. Listan är app/media.py:39:s
// VIDEO_EXTS MINUS webm, och avvikelsen är avsiktlig: .webm är appens EGET
// ljudinspelningsformat (audio/webm;codecs=opus, plan A4). En lektion läraren
// spelat in i appen har ingen videoström, så ett <video> hade gett en svart
// ruta där ljudet ändå hörs. inspelningar/Lektionskort.svelte:20-23 gör samma
// undantag för miniatyrerna, av samma skäl.
//
// Priset: en NEDLADDAD .webm-video spelas som ljud. Det är precis vad gamla
// appen gör med allt (app.js:5556 renderar alltid <audio>), alltså ingen
// regression — och den vanliga filen är den egeninspelade.
const VIDEO_EXT = ['mp4', 'm4v', 'mkv', 'mov', 'avi'];

// Ändelser ensure_web_video (app/media.py:98-100) returnerar OFÖRÄNDRADE.
// Allt annat transkodas vid första begäran: stream-copy → NVENC → libx264.
// Det kan ta minuter och kan kasta, alltså svara 500 (server.py:1703-1707).
const WEBBVIDEO = ['mp4', 'm4v', 'mov', 'webm'];

function andelse(sokvag) {
  const m = /\.([^.\\/]+)$/.exec(sokvag || '');
  return m ? m[1].toLowerCase() : '';
}

export function arVideoFil(sokvag) {
  return VIDEO_EXT.includes(andelse(sokvag));
}

/** Sant när servern måste transkoda innan den kan svara. Bara meningsfullt för video. */
export function masteTranskodas(sokvag) {
  return !WEBBVIDEO.includes(andelse(sokvag));
}

export function byggMediaUrl(sokvag, somVideo) {
  if (!sokvag) return null;
  return '/api/media?path=' + encodeURIComponent(sokvag) + (somVideo ? '&want=video' : '');
}
