// Inspelning i webbläsaren. Porterad ur gamla appens inspelningsblock
// (app/web/static/app.js:1380-1506), med de defekter som planens spec listar
// LAGADE i stället för troget överförda.
//
// Modulprivata resurser (ström, recorder, AudioContext, timers) hålls här och
// aldrig i storen — samma delning som korning.js gör med sin rAF-loop.
import { tr } from './stores.svelte.js';
import { addFiles } from './actions.js';
import {
  extAvMime,
  sparaSession,
  lasSession,
  glomSession,
  stadaSessioner,
} from './inspelningLagring.js';

const CHUNK_MS = 4000;           // timeslice: en bit var fjärde sekund, app.js:1438
const TYSTNADSNIVA = 0.02;       // under den här nivån räknas det som tystnad
const TYSTNADSSEKUNDER = 4;      // så länge innan "Ingen signal?" visas

let recorder = null;
let strom = null;
let audioCtx = null;
let analysator = null;
let tidTimer = 0;
let nivaTimer = 0;
let tystnadSek = 0;
let session = null;
// Promise<any>, inte det inferrerade Promise<void>: koaChunk kedjar på en
// fetch, och Task 3 lägger till omförsök med svarskropp. Utan annoteringen
// fäller checkJs återtilldelningen (Promise<void | Response>).
/** @type {Promise<any>} */
let uppladdningsKedja = Promise.resolve();
// Sätts SYNKRONT före await getUserMedia. Gamla appen sätter S.recording först
// efter att löftet löst ut (app.js:1441), så ett snabbt dubbelklick kunde starta
// två strömmar och läcka den första öppen.
let startar = false;
// Generationsräknare för inspelningarna, samma mönster som korToken i
// actions.js:284. Bumpas synkront vid varje start och vid varje avbrott.
// slutforInspelning fångar den före sitt första await och jämför före varje
// skrivning: hinner läraren starta en NY inspelning inom fönstret (await på
// uppladdningskedjan plus finish-POSTen) får den gamla, redan avslutade
// körningen inte nollställa den NYA inspelningens tr.recElapsed/tr.recMarkerCount
// och inte flytta guiden från steg 1.
let inspelningsToken = 0;
// Markörerna för den inspelning som pågår just nu. Nollställs på samma ställen
// som annat körtillstånd (startRecording, cancelRecording) och fångas synkront
// av slutforInspelning, se där. Typannoteringen behövs: utan den infererar
// checkJs never[] ur den tomma litteralen och fäller pushen av { t }.
/** @type {Array<{t: number}>} */
let markorer = [];

/** Stöder webbläsaren inspelning alls? app.js:1381. */
export function recSupported() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
}

/** lektion_2026-07-25_1432 — tidsstämpeln i filnamnet. app.js:1382-1385. */
function stampel() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}`;
}

/** Läsbart besked per felorsak. Gamla appen ger samma text för alla fel
 *  (app.js:1445), vilket är direkt missvisande när ingen mikrofon finns. */
function mikrofonFel(err) {
  const namn = err && err.name;
  if (namn === 'NotAllowedError' || namn === 'SecurityError')
    return 'Mikrofonen blockerades. Tillåt mikrofon för appen och försök igen.';
  if (namn === 'NotFoundError' || namn === 'OverconstrainedError')
    return 'Ingen mikrofon hittades. Koppla in en och försök igen.';
  if (namn === 'NotReadableError')
    return 'Mikrofonen används av ett annat program. Stäng det och försök igen.';
  return `Kunde inte komma åt mikrofonen${namn ? ` (${namn})` : ''}.`;
}

function valjMimeType() {
  const helst = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
  if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return null;
  return helst.find((t) => MediaRecorder.isTypeSupported(t)) || null;
}

function stoppaStrom() {
  if (!strom) return;
  try { strom.getTracks().forEach((t) => t.stop()); } catch { /* redan död */ }
  strom = null;
}

function stoppaNivamatare() {
  clearInterval(nivaTimer);
  nivaTimer = 0;
  tystnadSek = 0;
  if (audioCtx) {
    try { audioCtx.close(); } catch { /* redan stängd */ }
    audioCtx = null;
  }
  analysator = null;
}

/** RMS på tidsdomändata, förstärkt 4x så vanligt tal syns i mätaren.
 *  Porterad rakt av ur app.js:1392-1413 — samma fftSize, samma 200 ms. */
function startaNivamatare(s) {
  try {
    // webkitAudioContext finns inte i lib.dom:s Window — casten hindrar
    // svelte-check från att fälla prefixet, som Safari fortfarande behöver.
    const AC = window.AudioContext || /** @type {any} */ (window).webkitAudioContext;
    if (!AC) return;
    audioCtx = new AC();
    const kalla = audioCtx.createMediaStreamSource(s);
    analysator = audioCtx.createAnalyser();
    analysator.fftSize = 1024;
    // Kopplas ALDRIG till destination — det skulle ge en återkopplingsslinga.
    kalla.connect(analysator);
    const buf = new Uint8Array(analysator.fftSize);
    nivaTimer = setInterval(() => {
      if (!analysator) return;
      analysator.getByteTimeDomainData(buf);
      let summa = 0;
      for (let i = 0; i < buf.length; i++) {
        const d = (buf[i] - 128) / 128;
        summa += d * d;
      }
      const niva = Math.min(1, Math.sqrt(summa / buf.length) * 4);
      tystnadSek = niva < TYSTNADSNIVA ? tystnadSek + 0.2 : 0;
      tr.recLevel = niva;
      tr.recSilent = tystnadSek > TYSTNADSSEKUNDER;
    }, 200);
  } catch { /* nivåmätaren är bonus — inspelningen fortsätter utan den */ }
}

export async function startRecording() {
  if (startar || tr.recording) return;
  if (!recSupported()) {
    tr.recError = 'Inspelning stöds inte i den här vyn.';
    return;
  }
  startar = true;
  // Bumpas här, synkront vid klicket — INTE efter att getUserMedia löst ut.
  // Ligger en behörighetsdialog och väntar hinner en pågående slutforInspelning
  // annars slå om tr.step till 'config' innan strömmen delats ut, och den nya
  // inspelningen skulle starta med widgeten avmonterad.
  inspelningsToken++;
  tr.recError = '';
  tr.recLostSecs = 0;
  try {
    const s = await navigator.mediaDevices.getUserMedia({ audio: true });
    strom = s;
    session = `rec_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    uppladdningsKedja = Promise.resolve();

    const mt = valjMimeType();
    recorder = mt ? new MediaRecorder(s, { mimeType: mt }) : new MediaRecorder(s);
    sparaSession(session, { mime: recorder.mimeType || mt || '', markers: [] });

    recorder.ondataavailable = (e) => { if (e.data && e.data.size) koaChunk(e.data); };
    recorder.onstop = () => { slutforInspelning(recorder ? recorder.mimeType : ''); };
    recorder.start(CHUNK_MS);

    // Gamla appen lyssnar inte på detta alls: dras mikrofonen ur upptäcks det
    // aldrig, och läraren tror att lektionen spelas in.
    s.getAudioTracks().forEach((spar) => {
      spar.onended = () => {
        tr.recError = 'Mikrofonen försvann — inspelningen stoppades. Det som hann spelas in finns kvar.';
        stopRecording();
      };
    });

    tr.recording = true;
    tr.recElapsed = 0;
    tr.recMarkerCount = 0;
    markorer = [];
    tr.recLevel = 0;
    tr.recSilent = false;
    startaNivamatare(s);
    clearInterval(tidTimer);
    tidTimer = setInterval(() => { tr.recElapsed += 1; }, 1000);
    window.addEventListener('beforeunload', vaktaOmladdning);
  } catch (err) {
    tr.recError = mikrofonFel(err);
    stoppaStrom();
  } finally {
    startar = false;
  }
}

export function stopRecording() {
  clearInterval(tidTimer);
  tidTimer = 0;
  stoppaNivamatare();
  window.removeEventListener('beforeunload', vaktaOmladdning);
  try {
    // else-grenen är en härdning: stoppaStrom() körs annars BARA ur
    // slutforInspelning, som bara körs ur recorder.onstop. Är recorder null
    // eller redan 'inactive' kommer inget onstop, inga spår stoppas och
    // mikrofonlampan lyser vidare fast läraren tror att hon stoppat.
    // stoppaStrom() är idempotent, så dubbelanrop är ofarligt.
    //
    // MEN — utgå INTE från att stopRecording alltid stänger sessionen: i
    // else-grenen skickas varken finish eller discard. En .part blir kvar på
    // servern, och backend erbjuder den som "ofullständig", vilket är rimligt —
    // men den som bygger vidare måste veta att sessionen bara SLUTFÖRS via
    // onstop-vägen.
    //
    // `session` nollställs däremot här, i grenen. Vägen var onåbar från UI:t när
    // den skrevs, men spar.onended leder numera in i funktionen: dras mikrofonen
    // ur precis innan recordern hunnit lämna 'inactive' står modulvariabeln kvar
    // med ett sessions-id vars .part ingen längre skriver till. laddaOavslutade
    // filtrerar bort just det id:t ur bannern som "den pågående inspelningen",
    // och räknar det som levande vid städningen — så den övergivna .part-filen
    // blev osynlig för läraren i stället för återställbar.
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    else {
      stoppaStrom();
      session = null;
    }
  } catch { /* redan stoppad */ }
  tr.recording = false;
  tr.recLevel = 0;
  tr.recSilent = false;
  // slutforInspelning körs ur recorder.onstop.
}

export function cancelRecording() {
  // Ett avbrott är också ett generationsskifte: skulle en slutföring ändå vara
  // i flykt får den inte skriva tillbaka tillstånd för det läraren just slängt.
  inspelningsToken++;
  clearInterval(tidTimer);
  tidTimer = 0;
  stoppaNivamatare();
  window.removeEventListener('beforeunload', vaktaOmladdning);
  try {
    if (recorder && recorder.state !== 'inactive') {
      recorder.onstop = null;      // ingen slutföring — det här är ett avbrott
      // ondataavailable MÅSTE nollas också. stop() flushar det som ligger kvar
      // i bufferten via ett dataavailable som kommer ASYNKRONT, efter att
      // raderna nedan redan satt session = null. koaChunk läser session då och
      // POSTar mot ?session=null — backendens sessionsregex (server.py:741)
      // släpper igenom "null", så avbrottet skrev en föräldralös
      // downloads/null.part som ingen städar, och som växte för varje avbrott.
      // Flushen hann dessutom EFTER discard-anropet, så den återuppstod efter
      // städningen. Verifierat live: nätverksloggen visade append(session=null)
      // efter discard. Avvikelse från briefens kodblock, se rapporten.
      recorder.ondataavailable = null;
      recorder.stop();
    }
  } catch { /* redan stoppad */ }
  stoppaStrom();
  const slangd = session;
  session = null;
  if (slangd) {
    glomSession(slangd);
    // discard MÅSTE vänta in uppladdningskedjan. En vanlig 4-sekundersflush kan
    // ligga i flykt när läraren trycker Avbryt, och api_recording_append
    // (app/web/server.py:762-764) öppnar filen med "ab" — den ÅTERSKAPAR alltså
    // .part-filen om discard hunnit unlink:a först. Resultatet blir samma symtom
    // som den lagade null.part-defekten, fast med ett riktigt sessions-id: en
    // föräldralös .part med verkligt lektionsljud som /api/recordings/incomplete
    // sedan erbjuder läraren att återställa — efter att hon uttryckligen bett
    // appen slänga den. Fönstret är litet men ingen städar upp efteråt, och en
    // belastad server breddar det.
    // .catch(() => {}) före .then: kedjan får inte kortslutas av att en append
    // föll, då är det ännu viktigare att discard körs.
    uppladdningsKedja
      .catch(() => {})
      .then(() => fetch(`/api/recording/discard?session=${encodeURIComponent(slangd)}`, { method: 'POST' }))
      .catch(() => { /* .part städas av backend vid nästa start */ });
  }
  tr.recording = false;
  tr.recElapsed = 0;
  tr.recError = '';
  tr.recMarkerCount = 0;
  markorer = [];
  tr.recLevel = 0;
  tr.recSilent = false;
  tr.recLostSecs = 0;
}

/** Markerar ett viktigt ögonblick. app.js:1462-1466 — bara en tidsstämpel;
 *  etiketter finns i schemat men gamla appen skriver aldrig någon. */
export function addRecMarker() {
  if (!tr.recording || !session) return;
  markorer = [...markorer, { t: tr.recElapsed }];
  tr.recMarkerCount = markorer.length;
  // Skrivs till localStorage direkt. Gamla appen håller dem BARA i minnet, så
  // en krasch mitt i lektionen förlorar dem permanent — återställningen
  // återskapar bara ljudet.
  const post = lasSession(session) || { mime: '', markers: [] };
  sparaSession(session, { ...post, markers: markorer });
}

function vaktaOmladdning(e) {
  e.preventDefault();
  e.returnValue = '';
}

/**
 * Laddar upp en bit. Returnerar {ok} eller {ok:false, fel}.
 * Ett nätverksfel får ETT omförsök; ett svar från servern (4xx/5xx) får inget —
 * har servern sagt nej hjälper inte en likadan förfrågan till.
 */
async function laddaUppChunk(blob, s) {
  for (let forsok = 0; forsok < 2; forsok++) {
    try {
      const r = await fetch(`/api/recording/append?session=${encodeURIComponent(s)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: blob,
      });
      if (r.ok) return { ok: true };
      const j = await r.json().catch(() => null);
      return { ok: false, fel: (j && j.error) || 'Kunde inte spara inspelningen.' };
    } catch {
      // Nätverksfel. Faller igenom till ett omförsök, sedan ger vi upp.
    }
  }
  return { ok: false, fel: 'Nätverket svarade inte.' };
}

/**
 * Köar en bit i ordning. Misslyckas den räknas de förlorade sekunderna upp och
 * läraren FÅR VETA. Gamla appen sväljer felet helt (app.js:1420), vilket är det
 * värsta en inspelningsapp kan göra: ljud försvinner utan att någon märker det.
 */
function koaChunk(blob) {
  const s = session;
  // Fångas SYNKRONT tillsammans med sessionen — se inspelningsToken.
  const token = inspelningsToken;
  uppladdningsKedja = uppladdningsKedja.then(async () => {
    const { ok, fel } = await laddaUppChunk(blob, s);
    if (ok) return;
    // Generationsvakt — MEDVETET tvärtemot slutforInspelnings felgren, som är
    // ovaktad. Skillnaden: den grenen bär ett engångsbesked om att en HEL
    // lektion inte gick att slutföra, utan siffra. Här hör både räknaren och
    // texten till den inspelning som just nu visas i widgeten — startRecording
    // och cancelRecording nollställer tr.recLostSecs — och meddelandet citerar
    // räknaren. En bit från en avslutad eller avbruten session som fallerar
    // efter att läraren startat en NY inspelning skulle alltså både skriva
    // förlorade sekunder på fel körning och göra själva siffran osann: "4
    // sekunder av inspelningen gick förlorade" om en inspelning där ingenting
    // gått förlorat.
    //
    // Priset: faller en gammal bit precis i det fönstret sägs det inte, och
    // filen köas ändå med en lucka. Accepterat, av två skäl. Efter Avbryt har
    // läraren uttryckligen slängt ljudet — där är beskedet bara brus. Och är
    // nätet verkligen nere fallerar den NYA inspelningens egna bitar inom fyra
    // sekunder, så hon får veta då; tyst blir bara ett fel som hinner läka
    // exakt inuti fönstret.
    if (token !== inspelningsToken) return;
    tr.recLostSecs += CHUNK_MS / 1000;
    // AVSTEG från briefens ordalydelse, som slutar "Resten spelas in som
    // vanligt." Den meningen är ett LÖFTE om att felet var engångsartat, och
    // löftet är osant i precis det serverfel som realistiskt inträffar: 413
    // är i praktiken onåbart (MAX_UPLOAD_BYTES är 2 GiB, server.py:40), medan
    // 507 — full disk, server.py:765-768 — är BESTÄNDIGT. Varje följande bit
    // fallerar också, räknaren tickar 4 → 8 → 12, och texten påstår samtidigt
    // att resten spelas in normalt. Osant precis när läraren behöver veta att
    // det inte är det.
    //
    // "Inspelningen fortsätter." håller i BÅDA fallen, och säger bara det som
    // faktiskt är sant: kedjan bryts inte, recordern rullar vidare, följande
    // bitar försöker fortfarande, och det som gick fram läggs ändå i kön vid
    // Stoppa. Den lovar däremot ingenting om att följande bitar LYCKAS — det
    // får siffran som växer bära, tillsammans med serverns egen text ("Kunde
    // inte skriva till disk — kontrollera ledigt utrymme.").
    tr.recError =
      `${fel} ${tr.recLostSecs} sekunder av inspelningen gick förlorade. ` +
      'Inspelningen fortsätter.';
  });
  return uppladdningsKedja;
}

/** Stänger sessionen, lägger filen i kön och lämnar över markörerna. */
async function slutforInspelning(mime) {
  // Fångas SYNKRONT, före det första await:et — se inspelningsToken.
  const token = inspelningsToken;
  stoppaStrom();
  stoppaNivamatare();
  const s = session;
  session = null;
  // Markörerna fångas SYNKRONT tillsammans med sessionen och token, av exakt
  // samma skäl. Läses `markorer` först efter await:en nedan kan läraren redan
  // ha startat en NY inspelning (som nollställt listan) och satt markörer i
  // den — då hade den gamla filen fått den nya lektionens markörer, och den
  // nya lektionen blivit av med dem. Nollställningen här är dessutom vad som
  // gör listan tom för nästa inspelning även utan startRecording, t.ex. om
  // läraren stoppar och aldrig spelar in igen.
  const mina = markorer;
  markorer = [];
  if (!s) {
    if (token === inspelningsToken) tr.recElapsed = 0;
    return;
  }
  const namn = `lektion_${stampel()}.${extAvMime(mime)}`;
  try {
    await uppladdningsKedja;
    const r = await fetch(
      `/api/recording/finish?session=${encodeURIComponent(s)}&name=${encodeURIComponent(namn)}`,
      { method: 'POST' },
    );
    const res = await r.json();
    const aktuell = token === inspelningsToken;
    if (res && res.path) {
      // Markörhandoffen är MEDVETET ovaktad, precis som addFiles nedan — och
      // till skillnad från räknarna sist i grenen. Skälet är detsamma som för
      // addFiles: det här hör till FILEN, inte till den inspelning widgeten
      // visar just nu. Nyckeln är res.path, mellanlagret läses av actions.js
      // när just den filen transkriberats klart, och filen köas ovillkorligt.
      // Hoppade vi över handoffen när körningen är inaktuell skulle den gamla
      // lektionen transkriberas utan sina markörer, samtidigt som posten i
      // localStorage blev kvar för alltid — ingen skulle någonsin posta eller
      // glömma den. Ingen krock med en pågående inspelning är möjlig: den har
      // en egen session och en egen (nyss nollställd) markörlista, och
      // nycklarna i tr.recMarkersByPath är filsökvägar som finish gjort unika.
      //
      // Posten i localStorage behålls så länge markörerna väntar — det ÄR
      // kraschnätet — och glöms först i actions.js, när servern tagit emot dem.
      if (mina.length) {
        tr.recMarkersByPath = {
          ...tr.recMarkersByPath,
          [res.path]: { session: s, markers: mina },
        };
      } else {
        // Inga markörer att vänta på, alltså inget att skydda mot en krasch.
        // Posten bär bara mime i det läget.
        glomSession(s);
      }

      // Filen läggs ALLTID i kön, även om en ny inspelning hunnit starta: en
      // lektion går inte att spela in igen, filen ligger redan färdig på disk
      // (finish har döpt om .part-filen) och skulle annars försvinna ur UI:t
      // utan ett ord. Men addFiles slår om tr.step till 'config', och steg 2
      // avmonterar <Inspelning /> — är den här körningen INAKTUELL måste
      // guiden därför hållas kvar på det steg den stod på.
      //
      // Vakten är !aktuell, INTE tr.recording: startRecording bumpar
      // inspelningsToken synkront på klicket men sätter tr.recording först
      // efter await getUserMedia. I fönstret däremellan — behörighetsdialogen
      // eller enhetsförvärvet — är körningen redan inaktuell medan
      // tr.recording fortfarande är false. Landade den gamla slutföringen där
      // slog tr.recording-vakten inte till: guiden hamnade på steg 2,
      // <Inspelning /> avmonterades, och strax därefter startade inspelningen
      // med mikrofonen på, timern tickande, bitar POSTade var fjärde sekund,
      // beforeunload blockerande och Stoppa/Avbryt utom räckhåll. !aktuell
      // täcker båda fallen och konsumerar den synkrona token-bumpen som
      // kommentaren vid inspelningsToken lovar.
      //
      // De vägar där !aktuell är sant utan att någon inspelning pågår (nekad
      // mikrofon, eller ett avbrott av den efterföljande sessionen) ger att
      // filen köas men att guiden står kvar på steg 1 — ofarligt, "Nästa:
      // inställningar" är klickbar där.
      const steg = tr.step;
      addFiles([{ name: res.name || namn, path: res.path }]);
      if (!aktuell) tr.step = steg;
      // Räknarna tillhör den inspelning som just nu visas i widgeten. Är
      // körningen inaktuell skulle de nollställa den nya inspelningens tid och
      // markörantal mitt i lektionen.
      if (aktuell) {
        tr.recElapsed = 0;
        tr.recMarkerCount = 0;
      }
    } else {
      // Ingen generationsvakt på felet, medvetet: det gäller den GAMLA
      // inspelningen och måste nå läraren även om en ny hunnit starta —
      // annars försvinner beskedet att en hel lektion inte gick att slutföra.
      //
      // Markörerna är borta ur minnet här (de fångades och nollställdes
      // synkront ovan), men posten i localStorage rörs INTE: filen blev aldrig
      // klar, så det finns ingen sökväg att nyckla dem på. Ljudet ligger kvar
      // som en .part och erbjuds av /api/recordings/incomplete — markörerna
      // ligger kvar bredvid, under samma sessions-id, åt återställningen.
      tr.recError = (res && res.error) || 'Kunde inte slutföra inspelningen.';
    }
  } catch {
    // Samma sak här: posten i localStorage lämnas kvar åt återställningen.
    tr.recError = 'Kunde inte slutföra inspelningen.';
  }
}

/* ---------------------------------------- oavslutade inspelningar (krasch) -- */

/** Hämtar oavslutade .part-filer och städar lagringen mot dem. app.js:1490-1494. */
export async function laddaOavslutade() {
  // Städningen får BARA köras när vi faktiskt fått listan. Faller fetch eller
  // r.json(), eller svarar servern 500 (FastAPI ger då {"detail": …}, alltså
  // ingen array), vet vi ingenting om vilka .part-filer som finns — och att
  // städa mot en tom lista raderar då varenda sparad post för filer som
  // ligger kvar på disk. Nästa lyckade laddning visar dem igen, men
  // lasSession ger null → extAvMime(null) → .webm: exakt den defekt det här
  // steget finns för, återinförd av en övergående nätverksstörning, plus att
  // de kraschsparade markörerna är permanent borta. Posten ÄR kraschnätet
  // (se slutforInspelning), och den får inte offras för städning.
  let ok = false;
  try {
    const r = await fetch('/api/recordings/incomplete');
    const lista = await r.json();
    if (Array.isArray(lista)) {
      // Den PÅGÅENDE inspelningens egen .part filtreras bort. Widgeten KAN
      // monteras om mitt i en inspelning: tr.recording grindar bara "Nästa:
      // inställningar" (TranskriberaView.svelte), medan addFiles sätter
      // tr.step = 'config' ovillkorligt (actions.js:37) — och Dropzone,
      // LankFalt, "ett exempel" och exempelfilen är alla klickbara medan det
      // spelas in. Vägen: spela in → dra in en fil → steg 2 → "Lägg till fler"
      // → steg 1 → den här effekten körs om. Den levande .part-filen är då
      // större än noll byte och listas av server.py:796-806.
      //
      // Utan filtret erbjuder bannern den pågående lektionen med Släng och
      // Återställ bredvid "Spelar in 12:34":
      //  · Släng unlink:ar .part medan recordern rullar, och nästa append
      //    öppnar filen igen med "ab" (server.py:763) — lektionen trunkeras
      //    tyst till det som spelades in EFTER klicket. Precis den
      //    återuppståndelse cancelRecording går långa vägar för att undvika.
      //  · Återställ döper om den levande .part-filen; resten hamnar i en ny
      //    fil och markörerna följer bara den andra.
      tr.incompleteRecs = lista.filter((p) => p && p.session !== session);
      ok = true;
    } else {
      tr.incompleteRecs = [];
    }
  } catch {
    tr.incompleteRecs = [];
  }
  if (!ok) return;
  // De VÄNTANDE markörsessionerna måste räknas som levande. En SLUTFÖRD
  // inspelning har fått sin .part omdöpt av finish och dyker därför aldrig upp
  // i /api/recordings/incomplete — men dess localStorage-post ska leva tills
  // markörerna postats (actions.js gör det först när transkriberingen är klar).
  // Städade vi bara mot incompleteRecs skulle ett besök på steg 1 under
  // pågående transkribering svepa bort posten mitt i det fönster den finns för.
  //
  // Den PÅGÅENDE sessionen måste med av samma skäl, och dessutom för att den
  // nyss filtrerats bort ur listan ovan: sker omkörningen inom de första ~4
  // sekunderna, innan första chunk-POSTen skapat .part-filen, finns den i
  // ingen av källorna alls. Posten skulle raderas, addRecMarker återskapa den
  // med mime: '' — och en senare krasch återställas som .webm.
  stadaSessioner([
    ...tr.incompleteRecs.map((p) => p.session),
    ...Object.values(tr.recMarkersByPath).map((m) => m.session),
    ...(session ? [session] : []),
  ]);
}

/**
 * Gör en oavslutad inspelning till en fil i kön. Filändelsen hämtas ur den
 * sparade sessionen — gamla appen hårdkodar .webm (app.js:1496) och ger alltså
 * fel ändelse för allt som inte spelades in med webm.
 */
export async function aterstallOavslutad(s) {
  const post = lasSession(s);
  const namn = `återställd_${s}.${extAvMime(post && post.mime)}`;
  try {
    const r = await fetch(
      `/api/recording/finish?session=${encodeURIComponent(s)}&name=${encodeURIComponent(namn)}`,
      { method: 'POST' },
    );
    const res = await r.json();
    if (res && res.path) {
      if (post && post.markers && post.markers.length) {
        tr.recMarkersByPath = {
          ...tr.recMarkersByPath,
          [res.path]: { session: s, markers: post.markers },
        };
      } else {
        glomSession(s);
      }
      addFiles([{ name: res.name || namn, path: res.path }]);
    } else {
      tr.recError = (res && res.error) || 'Kunde inte återställa inspelningen.';
    }
  } catch {
    tr.recError = 'Kunde inte återställa inspelningen.';
  }
  await laddaOavslutade();
}

/** Raderar en oavslutad inspelning permanent. app.js:1503-1506. */
export async function slangOavslutad(s) {
  try {
    await fetch(`/api/recording/discard?session=${encodeURIComponent(s)}`, { method: 'POST' });
    // glomSession körs FÖRST efter att POSTen gått igenom. Låg den före
    // await:et — som gamla appen och som briefen — försvann mime och markörer
    // så snart nätet hackade, medan .part-filen låg kvar på disk: nästa
    // laddning erbjuder den igen, och en Återställ då ger extAvMime(null)
    // → .webm plus tappade markörer. Alltså exakt den defekt hela det här
    // steget finns för att laga.
    //
    // "Lyckades" är ändå en svag signal: backendens discard sväljer OSError
    // och svarar {ok: true} även när unlink föll (server.py:810-819). Filen
    // kan alltså ligga kvar trots att posten glöms — men då dyker den upp i
    // bannern igen, och det är den riktningen felet ska luta åt.
    glomSession(s);
  } catch { /* filen ligger kvar och dyker upp igen nästa gång */ }
  await laddaOavslutade();
}
