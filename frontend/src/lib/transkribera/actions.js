import { getJSON, postJSON, streamPost } from '../api.js';
import { tr, isMedia } from './stores.svelte.js';
import { recommendModel } from './katalog.svelte.js';
import { startProgressAnim, stopProgressAnim } from './korning.js';
// BARA lagringsmodulen — inspelning.svelte.js får ALDRIG importeras härifrån.
// Den importerar den här filen (addFiles), så beroendet åt andra hållet skulle
// sluta cirkeln. inspelningLagring.js importerar ingenting alls, just därför.
import { glomSession } from './inspelningLagring.js';

let idRakning = 0;

/**
 * Glömmer ett mikrofonåtkomstfel när guiden lämnar steg 1. Anropas på de TVÅ
 * ställen där tr.step slås om till 'config'.
 *
 * Varför bara den arten: ett åtkomstfel ("Ingen mikrofon hittades", "Mikrofonen
 * blockerades") är sant om en knapp och en enhet som bara finns på steg 1.
 * tr.recError nollställs annars enbart av en LYCKAD start eller av Avbryt —
 * alltså aldrig på en dator utan mikrofon — och samladStatus() väver in det i
 * steg 2:s synliga felrad. Läraren fick då sitt mikrofonbesked i rött ovanför
 * en fil som inte har med saken att göra, permanent, återannonserat av
 * live-regionen framför varje senare statusändring.
 *
 * Beskeden om FÖRLORAT LJUD (chunk-kedjan, misslyckad slutföring) bär art ''
 * och rörs inte: de gäller ljud som redan spelats in, och att de följer med
 * till steg 2 är hela poängen med den sammanvävningen.
 */
function glomMikrofonfel() {
  if (tr.recErrorArt !== 'mikrofon') return;
  tr.recError = '';
  tr.recErrorArt = '';
}

/**
 * Lägger till källor i kön. Speglar addFilesObjs (app.js:3036-3056) regel för
 * regel: format filtreras, http(s)-länkar släpps alltid igenom, dubbletter på
 * sökväg tas bort, och kön flyttar guiden vidare till steg 2.
 *
 * @param {Array<{name: string, path?: string}>} items
 */
export function addFiles(items) {
  const goda = items.filter((it) => isMedia(it.name) || /^https?:/i.test(it.path || ''));
  const skippade = items.length - goda.length;
  if (!goda.length) {
    tr.fileError = 'Filformatet stöds inte — välj ljud eller video (MP4, MKV, MOV, MP3, WAV, M4A …).';
    tr.fileNoteArt = 'fel';
    tr.dragging = false;
    return;
  }
  const fanns = new Set(tr.queue.map((q) => q.path || q.name));
  const nya = goda
    .filter((g) => !fanns.has(g.path || g.name))
    .map((g) => ({ id: 'q' + ++idRakning, name: g.name, path: g.path || g.name }));
  const dubbletter = goda.length - nya.length;

  tr.queue = [...tr.queue, ...nya];
  tr.dragging = false;
  tr.activeId = tr.activeId || tr.queue[0]?.id || null;
  glomMikrofonfel();
  tr.step = 'config';
  // Gamla appen visar dubblettbeskedet som en flytande toast (app.js:3051-3055).
  // Den här appen har ingen toast-infrastruktur och DESIGN.md:s ton talar emot
  // att bygga en för det här — beskedet hamnar på samma rad som filfelet. Men
  // dubblettbeskedet är inget fel, så det bär en egen "art" (tr.fileNoteArt)
  // som vyn målar neutralt i stället för rött.
  if (skippade) {
    tr.fileError = 'Hoppade över ' + skippade + ' fil(er) — formatet stöds inte.';
    tr.fileNoteArt = 'fel';
  } else if (dubbletter) {
    tr.fileError = dubbletter === 1
      ? '1 fil låg redan i kön.'
      : dubbletter + ' filer låg redan i kön.';
    tr.fileNoteArt = 'info';
  } else {
    tr.fileError = '';
    tr.fileNoteArt = 'fel';
  }
}

/** Tar bort en post ur kön. Speglar removeQ, app.js:1356-1364. */
export function removeFromQueue(id) {
  tr.queue = tr.queue.filter((q) => q.id !== id);
  if (tr.activeId === id) tr.activeId = tr.queue[0]?.id || null;
  // Rensa ett eventuellt kvarstående besked (t.ex. dubblettnotisen) — annars
  // står det kvar utan någon kö att höra till.
  tr.fileError = '';
  // Tom kö tar guiden tillbaka till källsteget — annars står läraren på ett
  // inställningssteg utan något att ställa in.
  if (!tr.queue.length) tr.step = 'source';
}

/**
 * Tillbaka till steg 1. Speglar goSource, app.js:1367, och rensar tr.fileError
 * precis som originalet. Statusraden är numera hoistad ovanför stegväxlingen
 * i TranskriberaView.svelte, så t.ex. dubblettbeskedet från addFiles syns
 * redan på steg 2 — det är inte längre beroende av att stå kvar okänsligt
 * tills läraren går tillbaka hit. Att rensa här förhindrar i stället att ett
 * gammalt besked lever kvar genom godtycklig navigering.
 */
export function goSource() {
  tr.step = 'source';
  tr.fileError = '';
}

/**
 * Köar den riktiga demoinspelningen. /api/sample ger en sökväg som servern
 * redan validerat under base_dir (app/web/server.py:1718) — därför är det här
 * den enda källvägen som går att köra i en vanlig webbläsare.
 */
export async function addSample() {
  tr.fileError = '';
  try {
    const res = await getJSON('/api/sample');
    if (res?.path) {
      addFiles([{ name: res.name, path: res.path }]);
    } else {
      tr.fileError = 'Inget exempel finns på den här datorn — lägg till en egen fil.';
      tr.fileNoteArt = 'fel';
    }
  } catch {
    tr.fileError = 'Inget exempel finns på den här datorn — lägg till en egen fil.';
    tr.fileNoteArt = 'fel';
  }
}

/** Köar ett namn som inte finns, så felvägen går att visa. app.js:3781. */
export function addSampleCorrupt() {
  addFiles([{ name: 'skadad_inspelning.m4a' }]);
}

/** Referens till det dolda <input type="file">, satt av Dropzone. */
let filInput = null;

/** @param {HTMLInputElement | null} el */
export function setFilInput(el) {
  filInput = el;
}

/**
 * Öppnar filväljaren. I pywebview-fönstret används den nativa dialogen, som
 * ger riktiga sökvägar; i en vanlig webbläsare faller vi tillbaka på ett dolt
 * <input type="file">, som BARA ger filnamn. Transkriberingen behöver
 * sökvägar, så webbläsarvägen är en bekvämlighet, inte en fungerande väg.
 * Speglar openPicker, app.js:1348-1353.
 */
export function openPicker() {
  tr.fileError = '';
  const api = /** @type {any} */ (window).pywebview?.api;
  if (api?.pick_files) {
    api.pick_files().then((files) => {
      if (files?.length) addFiles(files);
    });
    return;
  }
  filInput?.click();
}

/** Filer valda i det dolda inputfältet. Speglar onPickFile, app.js:1365. */
export function onPickFile(e) {
  const el = /** @type {HTMLInputElement} */ (e.target);
  const fs = Array.from(el.files || []).map((f) => ({
    name: f.name,
    // File.path finns bara i pywebview-fönstret — i webbläsaren blir det namnet.
    path: /** @type {any} */ (f).path || f.name,
  }));
  if (fs.length) addFiles(fs);
  el.value = '';
}

export function onDragOver(e) {
  e.preventDefault();
  if (!tr.dragging) tr.dragging = true;
}

export function onDragLeave(e) {
  e.preventDefault();
  tr.dragging = false;
}

/** Speglar onDrop, app.js:1368. */
export function onDrop(e) {
  e.preventDefault();
  const fs = Array.from(e.dataTransfer?.files || []).map((f) => ({
    name: f.name,
    path: /** @type {any} */ (f).path || f.name,
  }));
  if (fs.length) addFiles(fs);
  else tr.dragging = false;
}

/** Namn att visa i kön för en länk. Speglar urlName, app.js:1373. */
function lankNamn(u) {
  if (/youtu/i.test(u)) return 'YouTube-länk';
  try {
    return new URL(u).hostname.replace(/^www\./, '') + '-länk';
  } catch {
    return 'Länk';
  }
}

/**
 * Köar en länk. Backendens /api/transcribe hämtar http(s)-källor med yt-dlp,
 * så kön bär bara URL:en som sökväg. Speglar addUrl, app.js:1374-1380.
 */
export function addUrl() {
  const u = tr.urlInput.trim();
  if (!/^https?:\/\//i.test(u)) {
    tr.fileError = 'Klistra in en giltig länk (måste börja med http:// eller https://).';
    tr.fileNoteArt = 'fel';
    return;
  }
  addFiles([{ name: lankNamn(u), path: u }]);
  tr.urlInput = '';
}

/** Vidare till inställningarna. Kön måste ha något i sig. */
export function goConfig() {
  if (!tr.queue.length) return;
  // Egen väg ut ur steg 1, vid sidan av addFiles: kön kan ha fyllts innan
  // läraren försökte spela in. Se glomMikrofonfel.
  glomMikrofonfel();
  tr.step = 'config';
}

/**
 * Byter talat språk. Nollställer resultatspråket till samma språk och väljer
 * om modellen — ett nytt talat språk ska inte lämna kvar en gammal
 * översättning eller en modell för fel språk. Speglar pickLang, app.js:1516.
 * @param {'sv'|'en'} l
 */
export function pickLang(l) {
  tr.language = l;
  tr.targetLanguage = l;
  tr.model = recommendModel(l);
}

/**
 * Byter resultatspråk. Skiljer det sig från det talade översätts texten.
 * @param {'sv'|'en'} l
 */
export function pickTargetLang(l) {
  tr.targetLanguage = l;
}

/**
 * Väljer modell för det språk som redan står i formuläret, utan att röra
 * något annat. Används när modellkatalogen landar efter första renderingen —
 * gamla appen sätter bara patch.model där (app.js:3020-3024), och att köra
 * hela pickLang skulle nollställa ett resultatspråk läraren redan valt.
 */
export function syncModel() {
  tr.model = recommendModel(tr.language);
}

/** Slår på/av ett utdataformat. Ny objekt, inte mutation. */
export function toggleFormat(f) {
  tr.formats = { ...tr.formats, [f]: !tr.formats[f] };
}

/** Slår på/av andra passet som rättar mot ljudet. */
export function toggleAudioCorrect() {
  tr.audioCorrect = !tr.audioCorrect;
}

/** Är ljudmodellen installerad? Speglar loadAudioModel, app.js:1519-1521. */
export async function loadAudioModel() {
  try {
    const d = await getJSON('/api/audio-model');
    if (d) tr.audioModelInstalled = !!d.installed;
  } catch {
    // Tyst: knappen visas då som "Ladda ner modell", vilket är sant.
  }
}

/**
 * Laddar ner ljudmodellen. Ett fel MÅSTE synas — Gemma 3n är gated, och utan
 * besked ser knappen bara död ut. Speglar downloadAudioModel, app.js:1522-1534,
 * men beskedet hamnar på statusraden i stället för i en toast.
 */
export async function downloadAudioModel() {
  if (tr.audioModelDownloading) return;
  tr.audioModelDownloading = true;
  tr.fileError = '';
  await streamPost('/api/download/audio-model', {}, (ev) => {
    if (ev.type === 'done') {
      tr.audioModelDownloading = false;
      tr.audioModelInstalled = true;
    } else if (ev.type === 'error') {
      tr.audioModelDownloading = false;
      tr.fileNoteArt = 'fel';
      tr.fileError = 'Kunde inte ladda ner ljudmodellen: ' + (ev.message || 'okänt fel');
    }
  });
}

/** mm:ss för loggraderna. Speglar fmtTime, app.js. */
function fmtTid(s) {
  const n = Math.max(0, Math.floor(s || 0));
  const m = Math.floor(n / 60);
  return String(m).padStart(2, '0') + ':' + String(n % 60).padStart(2, '0');
}

/** Nästa köpost som inte körts än. Speglar _nextPending, app.js:2207. */
export function nextPending(excludeId) {
  for (const q of tr.queue) {
    if (q.id !== excludeId && (tr.qStatus[q.id] || 'pending') === 'pending') return q.id;
  }
  return null;
}

// Ökar vid avbrott så en ström som fortfarande droppar in inte får skriva
// tillstånd för en körning läraren redan avbrutit. Speglar _runToken,
// app.js:2220.
let korToken = 0;
let tickare = null;

/** Stoppar sekundräknaren. */
function stoppaTickare() {
  if (tickare) {
    clearInterval(tickare);
    tickare = null;
  }
}

/**
 * Kör den aktiva köposten mot /api/transcribe. Speglar _runActive,
 * app.js:2215-2268 — payloaden matchas fält för fält.
 */
export async function startRun() {
  if (tr.run === 'running') return;
  const aktiv = tr.queue.find((q) => q.id === tr.activeId) || tr.queue[0];
  if (!aktiv) return;
  const token = ++korToken;

  tr.step = 'process';
  tr.run = 'running';
  tr.progress = 0;
  tr.dispProgress = 0;
  tr.elapsed = 0;
  tr.runError = null;
  tr.resultFiles = [];
  tr.resultId = null;
  tr.resultSegment = [];
  tr.resultMedia = null;
  tr.qStatus = { ...tr.qStatus, [aktiv.id]: 'running' };
  tr.log = ['[00:00] Startar transkribering …'];
  startProgressAnim();

  const t0 = Date.now();
  stoppaTickare();
  tickare = setInterval(() => {
    if (token === korToken) tr.elapsed = (Date.now() - t0) / 1000;
  }, 250);

  const formats = ['srt', 'txt', 'vtt'].filter((f) => tr.formats[f]);

  await streamPost(
    '/api/transcribe',
    {
      source: aktiv.path || aktiv.name,
      model_id: tr.model,
      language: tr.language,
      target_language: tr.targetLanguage,
      formats,
      audio_correct: tr.audioCorrect,
      sub_mode: tr.subtitleMode,
      // Ternären är bärande: tr.embedKind behåller sitt värde när läraren
      // växlar tillbaka till "Spara separat", så ett gammalt 'burn' skulle
      // annars läcka in i en separate-förfrågan. Speglar app.js:2236.
      embed_kind: tr.subtitleMode === 'embed' ? tr.embedKind : null,
      more_pending: !!nextPending(aktiv.id),
    },
    (ev) => {
      if (token !== korToken) return;
      if (ev.type === 'progress') {
        // Aldrig 100 % före 'done' — 100 ska betyda färdig, inte "Whisper
        // klar, sätter fortfarande ihop". Speglar app.js:2241-2243.
        tr.progress = Math.min(ev.pct || 0, 99);
      } else if (ev.type === 'log') {
        tr.log = [...tr.log, '[' + fmtTid(tr.elapsed) + '] ' + ev.msg];
      } else if (ev.type === 'error') {
        stoppaTickare();
        stopProgressAnim();
        tr.run = 'error';
        tr.runError = {
          title: 'Transkriberingen misslyckades',
          detail: ev.message || 'Okänt fel',
        };
        tr.qStatus = { ...tr.qStatus, [aktiv.id]: 'error' };
        tr.qProgress = { ...tr.qProgress, [aktiv.id]: Math.round(tr.progress) };
      } else if (ev.type === 'done') {
        stoppaTickare();
        const r = ev.result || {};
        tr.run = 'done';
        tr.progress = 100;
        tr.resultFiles = r.files || [];
        tr.resultId = r.id || null;
        tr.resultSegment = Array.isArray(r.transcript) ? r.transcript : [];
        tr.resultMedia = r.media || null;
        tr.qStatus = { ...tr.qStatus, [aktiv.id]: 'done' };
        tr.qProgress = { ...tr.qProgress, [aktiv.id]: 100 };
        tr.log = [...tr.log, '[klar] Färdig på ' + fmtTid(tr.elapsed)];
        // Markörer satta under inspelningen kan inte postas förrän lektionen
        // har ett id. Speglar app.js:2255-2263, matchat på filens path.
        const mark = tr.recMarkersByPath[aktiv.path];
        if (mark && mark.markers.length && r.id) {
          postJSON(`/api/recordings/${r.id}/markers`, { markers: mark.markers })
            .then(() => glomSession(mark.session))
            // Faller POSTen är markörerna BORTA för den här lektionen. Inget
            // omförsök, till skillnad från chunk-kedjan — och ingen
            // återställningsväg heller: aterstallOavslutad nås bara ur bannern,
            // som listar sessioner med en .part på disk, och en SLUTFÖRD
            // inspelning har ingen (finish har döpt om filen). Sessionen finns
            // då varken i tr.incompleteRecs eller — tre rader ned — i
            // tr.recMarkersByPath, så stadaSessioner sveper localStorage-posten
            // vid nästa besök på steg 1.
            //
            // Alternativet vore att behålla posten i tr.recMarkersByPath vid
            // fel. Det avvisas: done-grenen är enda läsaren, och den körs bara
            // om SAMMA sökväg transkriberas igen — en köpost som är 'done' körs
            // inte om. Omförsöket hade alltså aldrig fyrat, medan posten i
            // gengäld hållits vid liv i localStorage för alltid av just den
            // stadaSessioner-vakt som skyddar väntande markörer. En läcka i
            // utbyte mot ett omförsök som inte finns.
            //
            // Priset är en tyst förlust av markörerna. Accepterat: servern är
            // lokal, POSTen är den sista av tre mot samma process, och ljudet
            // och transkriptionen är redan sparade — det som går förlorat är
            // tidsstämplarna, inte lektionen.
            .catch(() => {});
          const { [aktiv.path]: _borttagen, ...kvar } = tr.recMarkersByPath;
          tr.recMarkersByPath = kvar;
        }
        const nasta = nextPending(aktiv.id);
        if (nasta) {
          // Nästa fil startar efter en kort paus, så läraren hinner se att den
          // förra blev klar. Speglar app.js:2256-2259.
          setTimeout(() => {
            if (token !== korToken) return;
            tr.activeId = nasta;
            tr.run = 'idle';
            startRun();
          }, 800);
        }
      }
    },
  );
}

/**
 * Avbryter körningen. POSTar till /api/transcribe/cancel — det räcker INTE att
 * sluta lyssna på strömmen: servern måste avsluta subprocessen och släppa
 * GPU:n. Speglar cancelRun, app.js:2269-2276.
 */
export async function cancelRun() {
  korToken++;
  stoppaTickare();
  stopProgressAnim();
  const id = tr.activeId;
  tr.run = 'cancelled';
  // Tillbaka till 'pending' så posten går att återuppta.
  if (id) tr.qStatus = { ...tr.qStatus, [id]: 'pending' };
  try {
    await fetch('/api/transcribe/cancel', { method: 'POST' });
  } catch {
    // Servern kan redan ha avslutat jobbet — UI:t är ändå avbrutet.
  }
}

/**
 * "Transkribera något mer" — nollställer HELA körtillståndet och tar guiden
 * tillbaka till steg 1. Speglar gamla appens restart (app.js:1508-1512) fält
 * för fält.
 *
 * restart() navigerar inte själv någonstans. Gamla appen gör `restart();
 * setTab('recordings');` i finishTranscribe (app.js:2323-2324) — den raden har
 * medvetet ingen motsvarighet här. Guiden stannar på steg 3 och ERBJUDER
 * transkriptet i stället för att rycka undan vyn (plan B2). Notera också att
 * fliken heter 'inspelningar' i den här frontenden, inte 'recordings'.
 *
 * goSource räcker inte: den byter bara steg. Kön, qStatus, activeId, run='done'
 * och resultatfilerna skulle leva kvar, med två följder — steg 1 säger "1 fil i
 * kön" om precis den fil som nyss rapporterades sparad, och eftersom addFiles
 * behåller ett redan satt activeId (`tr.activeId = tr.activeId || …`) skulle
 * nästa start köra om den GAMLA filen först: en andra lessons-rad och en andra
 * utdatamapp för samma lektion.
 */
export function nyTranskribering() {
  // Körtoken först, likt cancelRun: en ström som fortfarande droppar in blir
  // ogiltig omedelbart och kan inte skriva in i tillståndet vi tömmer nedan.
  // Ingen nåbar väg dit är funnen — knappen är grindad på run === 'done' &&
  // !nagotKvar — men raden är billig försäkring.
  korToken++;
  // Sedan timers, precis som restart():s clearInterval/clearTimeout — inget får
  // skriva in i det tillstånd vi tömmer på nästa rad.
  stoppaTickare();
  stopProgressAnim();
  tr.queue = [];
  tr.qStatus = {};
  tr.qProgress = {};
  tr.activeId = null;
  tr.run = 'idle';
  tr.progress = 0;
  tr.dispProgress = 0;
  tr.elapsed = 0;
  tr.log = [];
  tr.runError = null;
  tr.resultFiles = [];
  tr.resultId = null;
  tr.resultSegment = [];
  tr.resultMedia = null;
  tr.logExpand = false;
  goSource();
}

/** Återupptar den avbrutna posten. Speglar resumeRun, app.js:2277. */
export function resumeRun() {
  tr.run = 'idle';
  startRun();
}

/** Kör om efter ett fel, med nollställda räknare. Speglar retryRun, app.js:2278. */
export function retryRun() {
  tr.run = 'idle';
  tr.runError = null;
  tr.progress = 0;
  tr.dispProgress = 0;
  tr.elapsed = 0;
  startRun();
}

/** Fäller ut/ihop loggen. Speglar toggleLogExpand, app.js:2310. */
export function toggleLog() {
  tr.logExpand = !tr.logExpand;
}
