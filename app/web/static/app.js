"use strict";
/* ============================================================================
   Transkribera — frontend (vanilla, no build step)
   A near 1:1 port of the Claude Design prototype (Transkribera.dc.html).
   Architecture:
     - S            : single state object
     - helpers      : style + logic helpers (verbatim from prototype)
     - actions      : state transitions (verbatim from prototype)
     - vm()         : the view-model (prototype renderVals) — every computed
                      style string + per-item handler closures
     - view(vm)     : section view functions return HTML strings
     - render()     : state -> vm -> html -> morphdom(#root)  (preserves nodes,
                      so CSS transitions/animations are not reset between ticks)
     - delegation   : handlers/refs registered per-render into H[], referenced
                      from markup via data-click/-input/-change/... = index
     - data-sh      : hover styles applied on pointerenter/leave (style-hover)
   Demo data + simulated timers drive every screen. `// BACKEND:` marks the
   seams where /api/* wiring replaces the simulation later.
   ============================================================================ */
(function () {

  /* ---------------------------------------------------------------- state -- */
  var S = {
    theme: 'light',
    tab: 'transcribe',
    source: 'intervju_lund.mkv',
    dragging: false,
    urlInput: '',
    step: 'config',
    model: 'KB-Whisper large',
    language: 'sv',
    targetLanguage: 'sv',       // resultatspråk; skiljer det sig från language översätts undertexterna
    formats: { srt: true, txt: true, vtt: false },
    subtitleMode: 'separate',   // 'separate' = media + SRT i mappen | 'embed' = bädda in i videon
    embedKind: 'soft',          // 'soft' = muxat sub-spår | 'burn' = inbränt
    audioCorrect: false,        // andra passet: rätta texten mot ljudet (Gemma 3n)
    audioModelInstalled: false, // status från /api/audio-model
    audioModelDownloading: false,
    run: 'idle',
    progress: 0,
    elapsed: 0,
    log: [],
    pp: 'idle',
    ppOp: 'summary',
    ppModel: 'Qwen3 30B-A3B',
    ppOut: '',
    ppPct: 0,
    ppEnabled: false,
    chat: [],
    chatInput: '',
    chatTyping: false,
    chatModalOpen: false,
    chatThink: false,           // Qwen3 "tänk djupare" — bara i chatten, default av
    chatAttach: [],
    openDD: null,
    search: '',
    diskTarget: 'd',
    onlineSort: 'fit',
    useCase: 'all',
    tip: null,
    installed: { 'KB-Whisper large': true, 'Whisper large-v3': true, 'Qwen3 30B-A3B': true, 'Gemma 3 27B': true },
    downloading: {},
    dlProg: {},
    installing: {},
    instProg: {},
    transcriptOpen: false,
    logOpen: false,
    toast: null,
    searchQuery: '',
    currentMatch: 0,
    queue: [{ id: 'f1', name: 'intervju_lund.mkv' }],
    qStatus: {},
    qProgress: {},
    activeId: 'f1',
    fileError: '',
    runError: null,
    dlFailed: {},
    editing: false,
    edits: {},
    edited: false,
    audioPlaying: false,
    audioT: 0,
    audioDur: 0,                // verklig medialängd (s); 0 = okänd → fall tillbaka på AUDIO_DUR
    mediaUrl: null,             // /api/media-URL för den öppna transkriptvyn (null = ingen media)
    runMedia: null,             // mediasökväg från senaste körningens resultat
    transcriptRaw: null,        // ursprungliga segment {start,end,text} bakom transkriptvyn (för att spara)
    history: [
      { id: 'h1', name: 'styrgruppsmöte_q1.mp3', date: 'Idag · 09:14', dur: '18:42', model: 'KB-Whisper large', lang: 'Svenska', formats: ['SRT', 'TXT'], words: 2940 },
      { id: 'h2', name: 'kundintervju_03.wav', date: 'Igår · 16:30', dur: '42:11', model: 'KB-Whisper large', lang: 'Svenska', formats: ['TXT'], words: 6810 },
      { id: 'h3', name: 'webinar_inspelning.mp4', date: '12 jun', dur: '01:03:20', model: 'Whisper large-v3', lang: 'Flerspråkig', formats: ['SRT', 'VTT', 'TXT'], words: 9120 },
    ],
    histViewing: null,
    resultId: null,            // history-id för den öppna transkriberingen (för att spara redigering/sammanfattning)
    transcriptRaw: null,       // segmenten med start/end (display-arrayen tappar dem)
    confirm: null,
    diskWarn: null,
    transcript: null,
    resultFilesReal: null,
    catalogReady: false,
  };

  /* instance (non-state) fields */
  var _t, _pp, _ppIv, _chat, _au, _toastIv, _toastT2, _glideRAF, _lastStart, _runToken = 0;
  var _dl = {}, _inst = {}, _editBuf = {}, _wave = null;
  var _file, _seek, _searchRef, _scrollRef, _procScroll, _chatThread, _imgInput, _media;
  var _prevTab, _prevStep, _prevRun, _prevPP, _prevOp, _prevChatLen, _wasEditing, _wasOpen, _scrollKey;

  /* ----------------------------------------------------------------- data -- */
  // Catalogs are `let` so loadModels() can reassign them to real data from /api/models;
  // the values below are the dev/offline fallback. Item shape mirrors the API.
  // vram = beräknat VRAM-behov (GB) · rtf = hastighet (× realtid) · toks = tokens/s · score = kapacitet/precision
  let WHISPER = [
    { id: 'KB-Whisper large',     size: '3.1 GB', vram: 4.7, rtf: 4,  score: 5.5, lang: 'sv',    recommended: true, useFor: 'Svenska — bäst precision (KB-Labb). Körs även via easytranscriber' },
    { id: 'Canary-Qwen-2.5B',     size: '5.0 GB', vram: 6.5, rtf: 9,  score: 5,   lang: 'en',    useFor: 'Engelska — toppresultat, marginellt tyngre' },
    { id: 'Whisper large-v3',     size: '3.1 GB', vram: 4.7, rtf: 4,  score: 4.5, lang: 'multi', useFor: 'Flerspråkigt allround — robust på de flesta språk' },
    { id: 'Canary 1B v2',         size: '2.0 GB', vram: 3.2, rtf: 13, score: 4,   lang: 'multi', useFor: 'Flerspråkigt och snabbt — bra balans kvalitet/fart' },
    { id: 'Parakeet TDT 0.6B v3', size: '1.2 GB', vram: 2.0, rtf: 25, score: 3.5, lang: 'multi', useFor: 'Snabbast — realtid och stora batchar' },
  ];
  let LLM = [
    { id: 'Qwen3 30B-A3B',      size: '18 GB',  vram: 17, toks: 95,  ctx: '256k', score: 5.5, recommended: true, uses: ['text','sv'],      useFor: 'Textresonemang & svenska — MoE, snabb och stark vid 24 GB', caps: { vision: false, files: ['PDF','TXT','Markdown','DOCX','CSV'] } },
    { id: 'Qwen3 32B',          size: '20 GB',  vram: 20, toks: 22,  ctx: '128k', score: 5.3, uses: ['text','sv'],      useFor: 'Tätt resonemang — högsta kvalitet när tid finns', caps: { vision: false, files: ['PDF','TXT','Markdown','DOCX','CSV'] } },
    { id: 'Gemma 3 27B',        size: '17 GB',  vram: 17, toks: 28,  ctx: '128k', score: 5,   uses: ['text','sv'],      useFor: 'Stark flerspråkig — verifiera svenska mot ScandEval', caps: { vision: false, files: ['PDF','TXT','Markdown','DOCX'] } },
    { id: 'gpt-oss 20B',        size: '12 GB',  vram: 13, toks: 70,  ctx: '128k', score: 4.5, uses: ['text'],           useFor: 'Lättare textmodell — snabb allround', caps: { vision: false, files: ['PDF','TXT','Markdown'] } },
    { id: 'Qwen3-VL-30B-A3B',   size: '18 GB',  vram: 17, toks: 90,  ctx: '256k', score: 5.2, uses: ['vision'],         modality: 'Bildanalys', useFor: 'Videoanalys (bild) — MoE, snabb på bildrutor', caps: { vision: true, files: ['Bilder (PNG/JPG)','Video (MP4)','PDF','TXT'] } },
    { id: 'Qwen3-VL-32B',       size: '21 GB',  vram: 20, toks: 20,  ctx: '256k', score: 5,   uses: ['vision'],         modality: 'Bildanalys', useFor: 'Videoanalys (bild) — högsta visuella precisionen', caps: { vision: true, files: ['Bilder (PNG/JPG)','Video (MP4)','PDF','TXT'] } },
    { id: 'Qwen3-VL-8B',        size: '5.5 GB', vram: 6,  toks: 110, ctx: '256k', score: 4,   uses: ['vision'],         modality: 'Bildanalys', useFor: 'Videoanalys (bild) — lättvikt, lämnar gott om VRAM över', caps: { vision: true, files: ['Bilder (PNG/JPG)','Video (MP4)','TXT'] } },
    { id: 'Qwen3-Omni-30B-A3B', size: '19 GB',  vram: 17, toks: 85,  ctx: '64k',  score: 5,   uses: ['vision','omni'], modality: 'Bild + tal', useFor: 'Videoanalys (bild + tal) — ser bild och hör ljud i ett', caps: { vision: true, files: ['Bilder (PNG/JPG)','Video (MP4)','Ljud (WAV/MP3)','TXT'] } },
  ];
  var LQUANTS = [
    { id: 'Q2_K',   label: 'Q2_K',   mult: 0.58, note: '~2-bit · minst, märkbart lägre kvalitet — bara för svag hårdvara' },
    { id: 'Q3_K_M', label: 'Q3_K_M', mult: 0.78, note: '~3-bit · liten, lätt kvalitetstapp' },
    { id: 'Q4_K_M', label: 'Q4_K_M', mult: 1.00, sweet: true, note: '~4-bit · bästa balansen kvalitet/storlek — standardvalet' },
    { id: 'Q5_K_M', label: 'Q5_K_M', mult: 1.18, note: '~5-bit · bättre kvalitet när du har VRAM över' },
    { id: 'Q6_K',   label: 'Q6_K',   mult: 1.38, note: '~6-bit · mycket nära full kvalitet' },
    { id: 'Q8_0',   label: 'Q8_0',   mult: 1.80, note: '~8-bit · i princip full precision' },
  ];
  var WQUANTS = [
    { id: 'int8', label: 'int8', mult: 0.62, note: '8-bit · mindre och snabbare, minimal kvalitetsskillnad' },
    { id: 'fp16', label: 'fp16', mult: 1.00, sweet: true, note: '16-bit · full precision (standard för Whisper)' },
  ];
  let ONLINE = [
    { id: 'deepseek-r1:8b', size: '4.9 GB', tag: 'Resonemang', uses: ['reason','code'] },
    { id: 'phi4:14b', size: '9.1 GB', tag: 'Kompakt, kraftfull', uses: ['reason','chat','code'] },
    { id: 'command-r:35b', size: '20 GB', tag: 'Lång kontext', uses: ['rag','chat'] },
    { id: 'nemotron-mini', size: '2.7 GB', tag: 'Lättviktig', uses: ['speed','chat'] },
  ];
  let HW = {
    gpu: 'RTX 4090', arch: 'Ada Lovelace', cc: '8.9', cuda: '12.4',
    precisions: 'fp16 · int8 · int4', cpu: 'Ryzen 9 7900X · 12 kärnor',
    vram: { total: 24, free: 22.5 },
    ram:  { total: 64, free: 52 },
    disks: [
      { id: 'c', drive: 'C:', name: 'System · NVMe SSD', total: 512, free: 11 },
      { id: 'd', drive: 'D:', name: 'Lagring · NVMe SSD', total: 2048, free: 1640 },
      { id: 'x', drive: 'X:', name: 'Extern · USB-C SSD', total: 4096, free: 3720 },
    ],
  };
  var STEPS = ['Förbereder', 'Extraherar ljud', 'Transkriberar', 'Färdigställer'];
  var AUDIO_DUR = 150;
  var ALLOWED = ['mp4', 'mkv', 'mov', 'webm', 'avi', 'm4v', 'mp3', 'wav', 'm4a', 'flac', 'aac', 'ogg', 'opus', 'wma'];
  var TRANSCRIPT = [
    { time: '00:00', spk: 0, text: 'Hej och välkomna till veckans avsnitt av vårt uppföljningsmöte.' },
    { time: '00:06', spk: 0, text: 'Idag fortsätter vi på det vi pratade om förra veckan.' },
    { time: '00:13', spk: 1, text: 'Precis, och då blir nästa steg att fördela ansvaret mellan oss.' },
    { time: '00:21', spk: 0, text: 'Jag tänkte att vi börjar med att gå igenom tidsplanen tillsammans.' },
    { time: '00:28', spk: 1, text: 'Bra idé. Vi ligger ungefär två dagar efter den ursprungliga planen.' },
    { time: '00:36', spk: 0, text: 'Det är hanterbart om vi prioriterar rätt saker den här veckan.' },
    { time: '00:44', spk: 1, text: 'Håller med. Vad ser ni som det viktigaste att bli klar med först?' },
    { time: '00:52', spk: 2, text: 'Transkriberingsflödet behöver testas ordentligt innan release.' },
    { time: '01:01', spk: 2, text: 'Och vi måste bekräfta att modellerna fungerar på all hårdvara.' },
    { time: '01:10', spk: 1, text: 'Jag tar ansvar för testningen och återkommer med besked på fredag.' },
    { time: '01:18', spk: 0, text: 'Perfekt. Då tar jag dokumentationen och release-noterna.' },
    { time: '01:27', spk: 2, text: 'Ska vi boka ett kort avstämningsmöte i mitten av veckan?' },
    { time: '01:34', spk: 0, text: 'Ja, låt oss säga onsdag klockan tio — ett kvarts möte räcker.' },
    { time: '01:42', spk: 2, text: 'Låter bra. Då skickar jag en kalenderinbjudan direkt efter mötet.' },
    { time: '01:50', spk: 0, text: 'Finns det något annat vi behöver ta upp innan vi avslutar?' },
    { time: '01:57', spk: 1, text: 'Bara en sak — vi bör informera supportteamet om ändringarna.' },
    { time: '02:05', spk: 2, text: 'Sant, jag lägger till det i mina anteckningar och hör av mig.' },
    { time: '02:13', spk: 0, text: 'Då tror jag vi är klara för idag. Tack för ett bra möte allihop.' },
    { time: '02:20', spk: 1, text: 'Tack själv, och tack för att ni lyssnade — vi hörs nästa vecka.' },
  ];

  /* -------------------------------------------------------------- helpers -- */
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function fmtStorage(g) { return g >= 1000 ? (g / 1024).toFixed(1).replace('.', ',') + ' TB' : g + ' GB'; }
  function fmtTime(s) { var m = Math.floor(s / 60), r = Math.floor(s % 60); return (m < 10 ? '0' : '') + m + ':' + (r < 10 ? '0' : '') + r; }
  function parseTS(t) { var p = (t || '00:00').split(':').map(Number); return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1]; }
  function baseNameOf(name) { var s = (name || 'transkript').trim(); s = s.split(/[\\/]/).pop(); if (s.indexOf('youtu') !== -1) s = 'youtube_klipp'; return s.replace(/\.[^.]+$/, '') || 'transkript'; }
  function baseName() { return baseNameOf(S.source); }
  function extOf(n) { var m = /\.([^.]+)$/.exec(n || ''); return m ? m[1].toLowerCase() : ''; }
  function isMedia(n) { return ALLOWED.indexOf(extOf(n)) !== -1; }
  function qName(queue, id) { var q = (queue || S.queue).find(function (x) { return x.id === id; }); return q ? q.name : ''; }
  function lineText(i) { var e = S.edits; return (e && e[i] != null) ? e[i] : getTranscript()[i].text; }
  function fitColor(f) { return f === 'ok' ? 'var(--ok)' : f === 'warn' ? 'var(--warn)' : f === 'bad' ? 'var(--bad)' : 'var(--ink-3)'; }
  function fitText(f) { return f === 'ok' ? 'Passar din hårdvara' : f === 'warn' ? 'Tungt för din hårdvara' : 'För stort för din hårdvara'; }
  function bestDisk() { return HW.disks.slice().sort(function (a, b) { return b.free - a.free; })[0]; }
  function modelNeedGB(id) { var m = WHISPER.concat(LLM).find(function (x) { return x.id === id; }); if (!m) return 0; var gb = m.download_mb ? m.download_mb / 1024 : (parseFloat(m.size) || 0); return Math.ceil(gb * 1.6); }
  function parseSize(s) { var m = /([\d.]+)\s*(GB|MB)/i.exec(s || ''); return m ? { n: parseFloat(m[1]), u: m[2].toUpperCase() } : null; }
  // Language drives the transcription model: Svenska -> KB-Whisper (lang 'sv'),
  // Engelska -> the multilingual Whisper (lang 'multi'/'en'). No manual model
  // picker any more; we resolve the best INSTALLED model for the language.
  function recommendModel(l, instMap) {
    var inst = instMap || S.installed;
    var pick = function (pred) { var m = WHISPER.find(function (x) { return inst[x.id] && pred(x); }); return m ? m.id : null; };
    if (l === 'en') return pick(function (m) { return m.lang === 'en'; }) || pick(function (m) { return m.lang === 'multi'; }) || S.model;
    return pick(function (m) { return m.lang === 'sv'; }) || pick(function (m) { return m.lang === 'multi'; }) || pick(function () { return true; }) || S.model;
  }
  function countMatches() { var q = S.searchQuery.trim().toLowerCase(); if (!q) return 0; var n = 0; for (var k = 0; k < getTranscript().length; k++) { var pos = 0, i, t = lineText(k).toLowerCase(); while ((i = t.indexOf(q, pos)) !== -1) { n++; pos = i + q.length; } } return n; }
  function pickQuant(model, kind) {
    var free = HW.vram.free, margin = 1.2;
    var ladder = kind === 'whisper' ? WQUANTS : LQUANTS;
    var rungs = ladder.map(function (q) { return Object.assign({}, q, { vram: Math.round(model.vram * q.mult * 10) / 10 }); });
    var chosen = null;
    for (var a = 0; a < rungs.length; a++) { if (free - rungs[a].vram >= margin) chosen = rungs[a]; }
    if (!chosen) { for (var b = 0; b < rungs.length; b++) { if (free - rungs[b].vram >= 0) { chosen = rungs[b]; break; } } }
    if (!chosen) chosen = rungs[0];
    return chosen;
  }
  function estFit(m) {
    var free = HW.vram.free;
    var sizeGB = parseFloat(m.size) || 0;
    var estVram = Math.round(sizeGB * 1.3 * 10) / 10;
    var head = Math.round((free - estVram) * 10) / 10;
    var tier, verdict;
    if (head < 0) { tier = 'bad'; verdict = '~' + Math.abs(head) + ' GB över'; }
    else if (head < 1.5) { tier = 'warn'; verdict = 'tight · ~' + head + ' GB'; }
    else { tier = 'ok'; verdict = '~' + head + ' GB kvar'; }
    return { tier: tier, dot: fitColor(tier), estVram: estVram, head: head, verdict: verdict };
  }
  function fitFor(spec, kind) {
    var free = HW.vram.free;
    var quant = pickQuant(spec, kind);
    var vram = quant.vram;
    var head = Math.round((free - vram) * 10) / 10;
    var tier, verdict;
    if (head < 0) { tier = 'bad'; verdict = 'Saknar ' + Math.abs(head) + ' GB VRAM'; }
    else if (head < 1.5) { tier = 'warn'; verdict = 'Ryms — ' + head + ' GB marginal'; }
    else { tier = 'ok'; verdict = head + ' GB VRAM kvar'; }
    var cs = chipStyle();
    var tipChip = function (label, style, tip) { return { label: label, style: style + ';cursor:help', onEnter: function (e) { showTip(e, tip); }, onLeave: hideTip }; };
    var quantTip = (kind === 'whisper' ? 'Precision ' : 'Kvantisering ') + quant.label + ' — ' + quant.note + '. Vald automatiskt för dina ' + free + ' GB lediga VRAM.';
    var chips = [
      tipChip(quant.label, quantChipStyle(), quantTip),
      tipChip(vram + ' GB VRAM', cs, 'Grafikminne som ' + spec.id + ' kräver vid ' + quant.label + ' och ~4K kontext. Längre kontext ökar behovet via KV-cachen.'),
    ];
    if (kind === 'whisper') {
      var ll = spec.lang === 'sv' ? 'Svenska' : spec.lang === 'en' ? 'Engelska' : 'Flerspråkig';
      chips.unshift({ label: ll, style: cs });
      chips.push({ label: '~' + spec.rtf + '× realtid', style: cs });
    } else {
      chips.push({ label: spec.toks + ' tok/s', style: cs });
      chips.push(tipChip(spec.ctx + ' kontext', cs, 'Maximal kontextlängd. Längre kontext äter mer VRAM via KV-cachen — räkna med mer än siffran ovan vid långa dokument.'));
      if (spec.modality) {
        var mt = spec.modality === 'Bild + tal' ? 'Multimodal — analyserar både bild/video och tal i samma modell.' : 'Multimodal — kan se och analysera bilder och videorutor.';
        chips.push(tipChip(spec.modality, cs, mt));
      }
    }
    return { tier: tier, dot: fitColor(tier), verdict: verdict, chips: chips, quant: quant, vram: vram, head: head };
  }
  function rankModels(arr, kind) {
    var w = { ok: 2, warn: 1, bad: 0 };
    return arr.map(function (m) { return { m: m, f: fitFor(m, kind) }; })
      .sort(function (a, b) { return (w[b.f.tier] * 1000 + b.m.score) - (w[a.f.tier] * 1000 + a.m.score); });
  }
  function hardwareView() {
    var cap = function (label, o, note, tip) {
      var used = Math.max(0, o.total - o.free);
      var frac = Math.min(1, used / o.total);
      var pct = Math.max(3, Math.round(frac * 100));
      var col = 'oklch(0.63 0.15 ' + Math.round(150 - 130 * frac) + ')';
      var t = { label: label, free: fmtStorage(o.free), total: fmtStorage(o.total), note: note,
        barStyle: 'height:100%;width:' + pct + '%;background:' + col + ';border-radius:99px;transition:width .3s ease,background .3s ease' };
      if (tip) { t.onEnter = function (e) { showTip(e, tip); }; t.onLeave = hideTip; t.badgeStyle = infoBadgeStyle(); }
      else { t.badgeStyle = 'display:none'; }
      return t;
    };
    var h = HW;
    var selDisk = h.disks.find(function (d) { return d.id === S.diskTarget; }) || h.disks[0];
    var diskOptions = h.disks.map(function (d) {
      return { drive: d.drive, name: d.name, free: fmtStorage(d.free) + ' ledigt',
        style: ddItem(d.id === selDisk.id),
        checkStyle: 'color:var(--accent);font-size:14.5px;opacity:' + (d.id === selDisk.id ? '1' : '0'),
        onPick: function () { pickDisk(d.id); } };
    });
    return {
      tiles: [
        cap('VRAM ledigt', h.vram, 'avgör största modell', 'Grafikminnet avgör hur stor modell som kan köras helt på GPU:n — den enskilt viktigaste faktorn för hastighet. Får modellen inte plats avlastas lager till system-RAM/CPU, vilket är betydligt långsammare.'),
        cap('System-RAM ledigt', h.ram, 'för laddning och CPU-avlastning', 'Tumregel: minst lika mycket system-RAM som VRAM, helst 1,5–2×. Används vid modelladdning och när lager avlastas från GPU:n till CPU:n.'),
        cap('Ledig disk', selDisk, 'modeller sparas på ' + selDisk.drive, 'Varje modell tar 2–40+ GB på disken. Välj en disk med gott om plats — kvantisering krymper filen rejält jämfört med full precision (fp16).'),
      ],
      specs: [
        { k: 'GPU', v: h.gpu },
        { k: 'Beräkning', v: h.arch + ' · cc ' + h.cc },
        { k: 'CUDA', v: h.cuda },
        { k: 'Precision', v: h.precisions },
        { k: 'CPU', v: h.cpu },
      ],
      ready: 'Kör modeller upp till ~' + h.vram.free + ' GB',
      selDisk: selDisk, diskOptions: diskOptions,
    };
  }
  function toastDetail(size, pct) {
    var m = /([\d.]+)\s*(KB|MB|GB)/i.exec(size || '');
    if (!m) return Math.round(pct) + '%';
    var n = parseFloat(m[1]), u = m[2].toUpperCase();
    var dn = n * pct / 100;
    var speed = u === 'KB' ? (120 + Math.round(Math.sin(pct / 6) * 40)) + ' KB/s' : (8 + Math.round((Math.sin(pct / 6) * 3 + (pct % 5) * 0.5) * 10) / 10) + ' MB/s';
    return dn.toFixed(u === 'KB' ? 0 : 1) + ' / ' + n + ' ' + u + ' · ' + speed;
  }
  function dlDetail(sizeStr, pct) {
    var ps = parseSize(sizeStr);
    var speed = (11 + Math.sin(pct / 6) * 4.5 + (pct % 5) * 0.6).toFixed(1) + ' MB/s';
    if (!ps) return speed;
    var dn = ps.n * pct / 100;
    return dn.toFixed(ps.u === 'GB' ? 1 : 0) + ' / ' + ps.n + ' ' + ps.u + ' · ' + speed;
  }
  function instDetail(pct) { if (pct < 55) return 'Packar upp filer…'; if (pct < 90) return 'Verifierar kontrollsumma…'; return 'Slutför…'; }

  /* ---- style helpers (return inline-style strings) ---- */
  function segBtn(active, h) { return 'flex:1;border:none;background:' + (active ? 'var(--surface)' : 'transparent') + ';color:' + (active ? 'var(--ink)' : 'var(--ink-2)') + ';border-radius:8px;padding:0 10px;' + (h ? 'height:' + h + ';' : 'padding:9px 10px;') + 'font-size:15px;font-weight:500;white-space:nowrap;cursor:pointer;font-family:inherit;box-shadow:' + (active ? 'var(--shadow-sm)' : 'none') + ';transition:background .12s,color .12s,box-shadow .12s'; }
  function chip(active) { return 'border:1px solid ' + (active ? 'var(--ink)' : 'var(--line)') + ';background:' + (active ? 'var(--ink)' : 'transparent') + ';color:' + (active ? 'var(--btn-fg)' : 'var(--ink-2)') + ';border-radius:9px;padding:8px 13px;font-size:14.5px;font-weight:500;cursor:pointer;font-family:inherit;transition:all .12s'; }
  function ddItem(active) { return 'width:100%;display:flex;align-items:center;gap:11px;background:' + (active ? 'var(--sunken)' : 'transparent') + ';border:none;border-radius:9px;padding:10px 11px;cursor:pointer;text-align:left;font-family:inherit;transition:background .12s'; }
  function tabBtn(active) { return 'border:none;background:' + (active ? 'var(--surface)' : 'transparent') + ';color:' + (active ? 'var(--ink)' : 'var(--ink-2)') + ';border-radius:9px;padding:8px 18px;font-size:15.5px;font-weight:500;cursor:pointer;font-family:inherit;box-shadow:' + (active ? 'var(--shadow-sm)' : 'none') + ';transition:background .12s,color .12s,box-shadow .12s'; }
  function rowStyle(last) { return 'display:flex;align-items:center;gap:13px;padding:15px 18px;' + (last ? '' : 'border-bottom:1px solid var(--line);'); }
  function rowStyleRich(last) { return 'display:flex;align-items:flex-start;gap:14px;padding:17px 18px;' + (last ? '' : 'border-bottom:1px solid var(--line);'); }
  function verdictPill(tier) { var c = tier === 'ok' ? 'var(--ok)' : tier === 'warn' ? 'var(--warn)' : 'var(--bad)'; return 'display:inline-flex;align-items:center;font-size:12.5px;font-weight:500;color:' + c + ';background:color-mix(in srgb,' + c + ' 13%,transparent);border-radius:6px;padding:3px 9px;white-space:nowrap;font-variant-numeric:tabular-nums'; }
  function chipStyle() { return "display:inline-flex;align-items:center;gap:5px;font-size:12.5px;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);border-radius:7px;padding:3px 9px;font-variant-numeric:tabular-nums;white-space:nowrap"; }
  function quantChipStyle() { return "display:inline-flex;align-items:center;gap:5px;font-size:12.5px;font-weight:600;color:var(--accent);background:var(--accent-weak);border:1px solid color-mix(in srgb,var(--accent) 24%,transparent);border-radius:7px;padding:3px 9px;font-variant-numeric:tabular-nums;font-family:'Geist',system-ui,sans-serif;cursor:help"; }
  function infoBadgeStyle() { return "display:inline-flex;align-items:center;justify-content:center;width:17px;height:17px;border-radius:50%;font-size:12px;font-weight:700;color:var(--ink);background:var(--sunken);border:1px solid var(--line);cursor:help;font-family:'Geist',system-ui,sans-serif;flex:0 0 auto"; }
  function infoBadge(text) { return { onEnter: function (e) { showTip(e, text); }, onLeave: hideTip }; }
  function tipStyleFor() {
    var t = S.tip;
    if (!t) return 'display:none';
    var vw = (typeof window !== 'undefined' && window.innerWidth) || 1200;
    var x = Math.max(160, Math.min(vw - 160, t.x));
    return "position:fixed;left:" + x + "px;top:" + (t.y - 12) + "px;transform:translate(-50%,-100%);z-index:200;max-width:286px;width:max-content;background:var(--btn-bg);color:var(--btn-fg);font-size:12.5px;line-height:1.5;font-weight:450;letter-spacing:0;padding:10px 13px;border-radius:10px;box-shadow:var(--shadow);pointer-events:none;animation:tipin .12s ease";
  }
  function coralBtn(disabled) { return 'display:inline-flex;align-items:center;justify-content:center;gap:9px;color:#fff;border:none;border-radius:12px;padding:14px 24px;font-size:16px;font-weight:600;cursor:' + (disabled ? 'default' : 'pointer') + ';font-family:inherit;opacity:' + (disabled ? '.7' : '1') + ';letter-spacing:.01em;background-image:linear-gradient(115deg,#d24a37 0%,#ef5f46 38%,#ff8567 68%,#ffb39c 100%);background-size:230% 100%;background-position:0% 0%;box-shadow:0 7px 20px -7px rgba(226,80,58,.6), 0 1px 2px rgba(0,0,0,.1);transition:background-position .65s cubic-bezier(.22,.61,.36,1), box-shadow .25s ease, transform .12s ease'; }
  function primaryBtn(disabled) { return 'display:inline-flex;align-items:center;justify-content:center;gap:9px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:12px;padding:14px 24px;font-size:16px;font-weight:500;cursor:' + (disabled ? 'default' : 'pointer') + ';font-family:inherit;opacity:' + (disabled ? '.55' : '1') + ';box-shadow:var(--shadow-sm);transition:transform .1s,opacity .12s,background .15s'; }

  /* -------------------------------------------------------------- actions -- */
  // BACKEND: theme/tab are pure UI.
  function toggleTheme() { setState(function (s) { return { theme: s.theme === 'light' ? 'dark' : 'light' }; }); }
  function setTab(t) { setState({ tab: t, openDD: null }); }
  function onSource(e) { setState({ source: e.target.value }); }
  function fileRef(el) { _file = el; }
  function openPicker() {
    setState({ fileError: '' });
    var api = window.pywebview && window.pywebview.api;
    if (api && api.pick_files) { api.pick_files().then(function (files) { if (files && files.length) addFilesObjs(files); }); return; }
    if (_file) _file.click();   // browser fallback (names only — transcription needs pywebview paths)
  }
  // BACKEND: addFiles will validate against the server; here it just queues names.
  function addFiles(names) { addFilesObjs(names.map(function (n) { return { name: n, path: n }; })); }
  function removeQ(id) {
    setState(function (s) {
      var queue = s.queue.filter(function (q) { return q.id !== id; });
      var qStatus = Object.assign({}, s.qStatus); delete qStatus[id];
      var activeId = (s.activeId === id) ? ((queue[0] && queue[0].id) || null) : s.activeId;
      return { queue: queue, qStatus: qStatus, activeId: activeId, source: qName(queue, activeId) || '', step: queue.length ? s.step : 'source' };
    });
  }
  function addSample(name) { setState({ fileError: '' }); addFiles([name]); }
  function onPickFile(e) { var fs = e.target.files ? Array.from(e.target.files).map(function (f) { return { name: f.name, path: f.path || f.name }; }) : []; if (fs.length) addFilesObjs(fs); if (e.target) e.target.value = ''; }
  function onDragOver(e) { e.preventDefault(); if (!S.dragging) setState({ dragging: true }); }
  function onDragLeave(e) { e.preventDefault(); setState({ dragging: false }); }
  function onDrop(e) { e.preventDefault(); var fs = (e.dataTransfer && e.dataTransfer.files) ? Array.from(e.dataTransfer.files).map(function (f) { return { name: f.name, path: f.path || f.name }; }) : []; if (fs.length) addFilesObjs(fs); else setState({ dragging: false }); }
  function goSource() { setState({ step: 'source', openDD: null, fileError: '' }); }
  // YouTube/URL source: backend /api/transcribe already downloads http(s) via yt-dlp.
  function onUrlInput(e) { setState({ urlInput: e.target.value }); }
  function onUrlKey(e) { if (e.key === 'Enter') addUrl(); }
  function urlName(u) { if (/youtu/i.test(u)) return 'YouTube-länk'; try { return new URL(u).hostname.replace(/^www\./, '') + '-länk'; } catch (e) { return 'Länk'; } }
  function addUrl() {
    var u = (S.urlInput || '').trim();
    if (!/^https?:\/\//i.test(u)) { setState({ fileError: 'Klistra in en giltig länk (måste börja med http:// eller https://).' }); return; }
    addFilesObjs([{ name: urlName(u), path: u }]);
    setState({ urlInput: '' });
  }
  function restart() {
    clearInterval(_t); clearTimeout(_pp); clearInterval(_ppIv); clearTimeout(_chat); clearInterval(_au);
    Object.values(_dl || {}).forEach(clearInterval);
    setState({ source: '', queue: [], qStatus: {}, qProgress: {}, activeId: null, fileError: '', step: 'source', run: 'idle', progress: 0, elapsed: 0, log: [], pp: 'idle', ppOp: 'summary', ppOut: '', ppEnabled: false, chat: [], chatInput: '', chatTyping: false, chatModalOpen: false, chatThink: false, chatAttach: [], openDD: null, transcriptOpen: false, runError: null, editing: false, edits: {}, edited: false, audioPlaying: false, audioT: 0, audioDur: 0, mediaUrl: null, runMedia: null, histViewing: null, resultId: null, transcriptRaw: null });
  }
  function onSearch(e) { setState({ search: e.target.value }); }
  function toggleFmt(f) { setState(function (s) { var formats = Object.assign({}, s.formats); formats[f] = !formats[f]; return { formats: formats }; }); }
  function pickModel(id) { setState({ model: id, openDD: null }); }
  function pickLang(l) { setState({ language: l, targetLanguage: l, model: recommendModel(l) }); }
  function pickTargetLang(l) { setState({ targetLanguage: l }); }
  function toggleAudioCorrect() { setState(function (s) { return { audioCorrect: !s.audioCorrect }; }); }
  function loadAudioModel() {
    return getJSON('/api/audio-model').then(function (d) { if (d) setState({ audioModelInstalled: !!d.installed }); }).catch(function () {});
  }
  function downloadAudioModel() {
    if (S.audioModelDownloading) return;
    setState({ audioModelDownloading: true });
    streamPost('/api/download/audio-model', {}, function (ev) {
      if (ev.type === 'done') { setState({ audioModelDownloading: false, audioModelInstalled: true }); }
      else if (ev.type === 'error') { setState({ audioModelDownloading: false }); }
    });
  }
  function pickOp(o) { setState({ ppOp: o, pp: 'idle', ppOut: '' }); if (o === 'chat') { seedChat(); openChatModal(); } else closeChatModal(); }
  function openChatModal() { setState({ chatModalOpen: true }); }
  function closeChatModal() { setState({ chatModalOpen: false }); }
  // Qwen3 "thinking": off by default (fast, no English chain-of-thought leak); on only
  // for hard multi-step chat questions. Correction/summary never think.
  function toggleChatThink() { setState(function (s) { return { chatThink: !s.chatThink }; }); }
  function stopProp(e) { e.stopPropagation(); }
  function chatThreadRef(el) { _chatThread = el; }
  function scrollChatBottom() { requestAnimationFrame(function () { var el = _chatThread; if (el) el.scrollTop = el.scrollHeight; }); }
  function pickChatModel(id) { setState({ ppModel: id, openDD: null }); }
  function toggleChatModelDD() { setState(function (s) { return { openDD: s.openDD === 'chatmodel' ? null : 'chatmodel' }; }); }
  // Real image attachment: open a native picker, read each file as a base64 data
  // URL, and stash it on chatAttach. sendChat() forwards data URLs to /api/chat,
  // where the server switches the LLM to the Gemma vision model (llama.cpp --mmproj).
  function imgInputRef(el) { _imgInput = el; }
  function attachImage() { if (_imgInput) _imgInput.click(); }
  function onPickImage(e) {
    var files = e.target.files ? Array.prototype.slice.call(e.target.files) : [];
    files.forEach(function (f) {
      var r = new FileReader();
      r.onload = function () { setState(function (s) { return { chatAttach: s.chatAttach.concat([{ kind: 'image', label: f.name || 'bild.png', data: r.result }]) }; }); };
      r.readAsDataURL(f);
    });
    if (e.target) e.target.value = '';
  }
  function removeAttach(i) { setState(function (s) { return { chatAttach: s.chatAttach.filter(function (_, k) { return k !== i; }) }; }); }
  function pickPPModel(id) { setState({ ppModel: id, openDD: null }); }
  function toggleModelDD() { setState(function (s) { return { openDD: s.openDD === 'model' ? null : 'model' }; }); }
  function togglePPDD() { setState(function (s) { return { openDD: s.openDD === 'ppmodel' ? null : 'ppmodel' }; }); }
  function diskDirFor(d) {
    // Modellerna bor i <enhet>\Transkribera\models på vald disk (Windows).
    var drv = String(d.drive || '').replace(/[\\/]+$/, '');
    return drv + '\\Transkribera\\models';
  }
  function pickDisk(id) {
    setState({ diskTarget: id, openDD: null });
    var d = (HW.disks || []).find(function (x) { return x.id === id; });
    if (!d) return;
    fetch('/api/settings/models-disk', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dir: diskDirFor(d) })
    }).then(function () { loadModels(); }).catch(function () {});
  }
  function loadSettings() {
    // Spegla vald modelldisk efter omstart (matcha enhetsbokstaven i sökvägen).
    return getJSON('/api/settings').then(function (s) {
      if (!s || !s.models_dir) return;
      var drv = String(s.models_dir).slice(0, 2).toUpperCase();
      var d = (HW.disks || []).find(function (x) { return String(x.drive || '').toUpperCase().indexOf(drv) === 0; });
      if (d) setState({ diskTarget: d.id });
    }).catch(function () {});
  }
  function toggleDiskDD() { setState(function (s) { return { openDD: s.openDD === 'disk' ? null : 'disk' }; }); }
  function closeDD() { setState({ openDD: null }); }
  function setUseCase(k) { setState({ useCase: k }); }

  function askUninstall(id) { setState({ confirm: { kind: 'uninstall', id: id, title: 'Ta bort ' + id + '?', body: 'Modellen raderas från disken (' + ((HW.disks.find(function (d) { return d.id === S.diskTarget; }) || {}).drive || '') + '). Du kan ladda ner den igen när som helst.', label: 'Ta bort', danger: true } }); }
  function askRerun(h) { setState({ confirm: { kind: 'rerun', id: h.id, title: 'Transkribera om?', body: '"' + h.name + '" körs igenom på nytt med dina nuvarande inställningar (modell, språk och format). Den läggs i kön på Transkribera-fliken.', label: 'Kör om', danger: false } }); }
  function askDeleteHistory(id, name) { setState({ confirm: { kind: 'history', id: id, title: 'Ta bort transkriberingen?', body: '"' + name + '" tas bort ur historiken. Filer du redan sparat på disken påverkas inte.', label: 'Ta bort', danger: true } }); }
  function confirmYes() {
    var c = S.confirm; if (!c) return;
    if (c.kind === 'uninstall') {
      var isW = WHISPER.some(function (m) { return m.id === c.id; });
      var url = isW ? '/api/uninstall/whisper' : '/api/uninstall/llm';
      var body = isW ? { id: c.id } : { name: c.id };
      setState(function (s) { var installed = Object.assign({}, s.installed); delete installed[c.id]; return { installed: installed, confirm: null }; });
      if (S.model === c.id) { var fb = WHISPER.find(function (m) { return m.id !== c.id && S.installed[m.id]; }); if (fb) setState({ model: fb.id }); }
      // Faktiskt radera modellen från disk; loadModels() stämmer av mot verkligt läge.
      fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
        .then(function () { loadModels(); }).catch(function () {});
    } else if (c.kind === 'history') {
      setState({ confirm: null });
      fetch('/api/history/' + encodeURIComponent(c.id), { method: 'DELETE' }).then(function () { loadHistory(); }).catch(function () {});
    } else if (c.kind === 'rerun') {
      var h = S.history.find(function (x) { return x.id === c.id; });
      setState({ confirm: null });
      if (h) reRunHistory(h);
    } else setState({ confirm: null });
  }
  function confirmNo() { setState({ confirm: null }); }
  function openHistory(h) {
    setState({
      transcriptOpen: true, histViewing: h.id, resultId: h.id,
      transcript: (h.transcript || []).map(function (g) { return { time: fmtTime(g.start), text: g.text }; }),
      transcriptRaw: h.transcript || [],
      mediaUrl: mediaUrlFor(h), audioT: 0, audioDur: 0, audioPlaying: false, edits: {}, edited: false,
    });
  }
  // Spara redigerad transkripttext till disk (skriver om SRT/TXT/VTT i resultatmappen
  // och uppdaterar historiken). No-op om inget redigerats eller ingen post är öppen.
  function saveTranscriptEdits() {
    var id = S.resultId; if (!id) return;
    var raw = S.transcriptRaw || []; if (!raw.length) return;
    if (!Object.keys(S.edits || {}).length) return;
    var segs = raw.map(function (g, i) { return { start: g.start, end: g.end, text: lineText(i) }; });
    fetch('/api/history/' + encodeURIComponent(id), { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ transcript: segs }) })
      .then(function () { loadHistory(); }).catch(function () {});
  }
  function reRunHistory(h) { var id = 'q' + Date.now(); setState({ tab: 'transcribe', step: 'config', queue: [{ id: id, name: h.name, path: h.source || h.name }], qStatus: {}, qProgress: {}, run: 'idle', progress: 0, elapsed: 0, activeId: id, source: h.source || h.name, fileError: '', runError: null, openDD: null }); }

  // The transcript player is backed by a real <audio> element (served from
  // /api/media) when the result media is on disk; it falls back to a simulated
  // clock for demo/seed data with no media. curDur() is the playable length.
  function curDur() { return S.audioDur > 0 ? S.audioDur : AUDIO_DUR; }
  function hasMedia() { return !!(_media && S.mediaUrl); }
  function mediaUrlFor(h) {
    var p = (h && h.video && h.video.path) || (h && h.media) ||
            (h && h.source && !/^https?:/i.test(h.source) ? h.source : null);
    return p ? ('/api/media?path=' + encodeURIComponent(p)) : null;
  }
  // Wire the media element once; its events are the single source of truth for
  // position/duration/play-state (morphdom preserves the node across renders).
  function mediaRef(el) {
    _media = el;
    if (!el || el._wired) return;
    el._wired = true;
    el.addEventListener('timeupdate', function () { setState({ audioT: el.currentTime || 0 }); });
    el.addEventListener('durationchange', function () { if (isFinite(el.duration) && el.duration > 0) setState({ audioDur: el.duration }); });
    el.addEventListener('play', function () { if (!S.audioPlaying) setState({ audioPlaying: true }); });
    el.addEventListener('pause', function () { if (S.audioPlaying) setState({ audioPlaying: false }); });
    el.addEventListener('ended', function () { setState({ audioPlaying: false }); });
  }
  function togglePlay() {
    if (hasMedia()) {
      if (_media.paused) { if (S.audioT >= curDur() - 0.15) _media.currentTime = 0; _media.play().catch(function () {}); }
      else { _media.pause(); }
      return;
    }
    if (S.audioPlaying) { clearInterval(_au); setState({ audioPlaying: false }); return; }
    if (S.audioT >= AUDIO_DUR) setState({ audioT: 0 });
    setState({ audioPlaying: true });
    clearInterval(_au);
    _au = setInterval(function () { setState(function (s) { var t = s.audioT + 0.2; if (t >= AUDIO_DUR) { clearInterval(_au); return { audioT: AUDIO_DUR, audioPlaying: false }; } return { audioT: t }; }); }, 200);
  }
  function seekTrackRef(el) { _seek = el; }
  function onSeekClick(e) {
    var el = _seek; if (!el) return;
    var r = el.getBoundingClientRect();
    var f = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    if (hasMedia()) { _media.currentTime = f * curDur(); setState({ audioT: _media.currentTime }); }
    else { setState({ audioT: f * AUDIO_DUR }); }
  }
  function jumpToLine(i) {
    var t = parseTS(getTranscript()[i].time);
    if (hasMedia()) { _media.currentTime = t; setState({ audioT: t }); _media.play().catch(function () {}); }
    else { setState({ audioT: t }); if (!S.audioPlaying) togglePlay(); }
  }

  function toggleEdit() {
    if (S.editing) { _commitEdits(); saveTranscriptEdits(); setState({ editing: false }); }
    else { _editBuf = {}; clearInterval(_au); if (_media) { try { _media.pause(); } catch (e) {} } setState({ editing: true, audioPlaying: false }); }
  }
  function onEditInput(e) { var i = e.currentTarget.getAttribute('data-eline'); _editBuf = _editBuf || {}; _editBuf[i] = e.currentTarget.textContent; }
  function _commitEdits() {
    var buf = _editBuf || {}; var keys = Object.keys(buf); if (!keys.length) return;
    var orig = getTranscript();   // diff against the real (or demo) transcript, not the seed
    setState(function (s) {
      var edits = Object.assign({}, s.edits); var changed = false;
      keys.forEach(function (k) { var v = buf[k]; var base = orig[k] ? orig[k].text : ''; if (v != null && v.trim() !== base) { edits[k] = v.trim(); changed = true; } else { if (edits[k] != null) changed = true; delete edits[k]; } });
      return { edits: edits, edited: s.edited || changed };
    });
    _editBuf = {};
  }
  // BACKEND: start()/_runActive() simulate transcription; replace with /api/transcribe SSE (streamPost).
  function start() {
    if (S.run === 'running') return;
    if (!S.queue.length) return;
    var now = Date.now();
    if (_lastStart && now - _lastStart < 400) return;
    _lastStart = now;
    var first = S.queue[0];
    var qStatus = {}; S.queue.forEach(function (q) { qStatus[q.id] = 'pending'; });
    setState({ qStatus: qStatus, qProgress: {}, activeId: first.id, source: first.name, runError: null });
    var fired = false;
    var go = function () { if (fired) return; fired = true; _runActive(); };
    var pane = document.querySelector('[data-pane="config"]');
    if (pane && pane.animate) {
      try {
        var a = pane.animate(
          [{ opacity: 1, transform: 'translateY(0) scale(1)', filter: 'blur(0)' }, { opacity: 0, transform: 'translateY(-46px) scale(0.965)', filter: 'blur(3px)' }],
          { duration: 360, easing: 'cubic-bezier(.5,0,.78,.12)', fill: 'forwards' }
        );
        a.onfinish = go; a.oncancel = go;
      } catch (e) { go(); }
      setTimeout(go, 460);
    } else { go(); }
  }
  function _nextPending(excludeId) { for (var k = 0; k < S.queue.length; k++) { var q = S.queue[k]; if (q.id !== excludeId && (S.qStatus[q.id] || 'pending') === 'pending') return q.id; } return null; }
  function _archive(file, secs) {
    var fmts = ['srt', 'txt', 'vtt'].filter(function (f) { return S.formats[f]; }).map(function (f) { return f.toUpperCase(); });
    var langLabel = S.language === 'en' ? 'Engelska' : 'Svenska';
    var entry = { id: 'h' + Date.now() + Math.floor(Math.random() * 99), name: file.name, date: 'Just nu', dur: fmtTime(secs), model: modelLabel(S.model), lang: langLabel, formats: fmts.length ? fmts : ['TXT'], words: 2800 + Math.floor(Math.random() * 500) };
    setState(function (s) { return { history: [entry].concat(s.history.filter(function (h) { return !(h.name === file.name && h.date === 'Just nu'); })) }; });
  }
  // BACKEND: real transcription via /api/transcribe SSE (one request per queue item).
  function _runActive() {
    if (S.run === 'running') return;
    clearInterval(_t);
    var active = S.queue.find(function (q) { return q.id === S.activeId; });
    if (!active) return;
    var token = ++_runToken;
    var src = baseNameOf(active.name);
    setState({
      run: 'running', step: 'process', progress: 0, elapsed: 0, pp: 'idle', ppOut: '',
      chat: [], chatTyping: false, runError: null, transcript: null, resultFilesReal: null,
      source: active.name,
      qStatus: Object.assign({}, S.qStatus, kv(active.id, 'running')),
      log: ['› transkribera "' + src + '" --model ' + modelLabel(S.model), '[00:00] Startar transkribering …'],
    });
    var t0 = Date.now();
    _t = setInterval(function () { if (token === _runToken) setState({ elapsed: (Date.now() - t0) / 1000 }); }, 250);
    var formats = ['srt', 'txt', 'vtt'].filter(function (f) { return S.formats[f]; });
    streamPost('/api/transcribe',
      { source: active.path || active.name, model_id: S.model, language: S.language,
        target_language: S.targetLanguage, formats: formats, audio_correct: S.audioCorrect,
        sub_mode: S.subtitleMode, embed_kind: S.subtitleMode === 'embed' ? S.embedKind : null,
        more_pending: !!_nextPending(active.id) },
      function (ev) {
        if (token !== _runToken) return;
        if (ev.type === 'progress') { setState({ progress: ev.pct || 0 }); }
        else if (ev.type === 'log') { setState(function (s) { return { log: s.log.concat(['[' + fmtTime(s.elapsed) + '] ' + ev.msg]) }; }); }
        else if (ev.type === 'error') {
          clearInterval(_t);
          setState(function (s) { return { run: 'error', runError: { title: 'Transkriberingen misslyckades', detail: ev.message || 'Okänt fel', where: 'run' }, qStatus: Object.assign({}, s.qStatus, kv(active.id, 'error')), qProgress: Object.assign({}, s.qProgress, kv(active.id, Math.round(s.progress))) }; });
        } else if (ev.type === 'done') {
          clearInterval(_t);
          var r = ev.result || {};
          var segs = (r.transcript || []).map(function (g) { return { time: fmtTime(g.start), text: g.text }; });
          setState(function (s) { return { run: 'done', progress: 100, transcript: segs, transcriptRaw: r.transcript || [], resultId: r.id || null, runMedia: r.media || null, edits: {}, edited: false, resultFilesReal: r.files || [], qStatus: Object.assign({}, s.qStatus, kv(active.id, 'done')), qProgress: Object.assign({}, s.qProgress, kv(active.id, 100)), log: s.log.concat(['[klar] Färdig på ' + fmtTime(s.elapsed)]) }; });
          loadHistory();   // server archived this run; refresh from disk
          var next = _nextPending(active.id);
          if (next) { setTimeout(function () { setState({ run: 'idle', activeId: next, source: qName(S.queue, next), audioT: 0 }, function () { _runActive(); }); }, 800); }
          else { setTimeout(function () { afterDone(); }, 450); }
        }
      });
  }
  function cancelRun() {
    _runToken++; clearInterval(_t);
    // Faktiskt avbryta jobbet på servern (avslutar subprocessen och frigör GPU:n),
    // inte bara sluta lyssna på strömmen.
    fetch('/api/transcribe/cancel', { method: 'POST' }).catch(function () {});
    setState(function (s) { return { run: 'cancelled', qStatus: Object.assign({}, s.qStatus, kv(s.activeId, 'pending')) }; });
  }
  function resumeRun() { setState({ run: 'idle' }); _runActive(); }
  function retryRun() { setState({ run: 'idle', runError: null, progress: 0, elapsed: 0 }); _runActive(); }

  // BACKEND: real LLM post-process via /api/postprocess SSE token stream (Ollama).
  function runPP() {
    if (S.pp === 'running') return;
    clearTimeout(_pp); clearInterval(_ppIv);
    setState({ pp: 'running', ppPct: 0, ppOut: '' });
    _ppIv = setInterval(function () { setState(function (s) { return { ppPct: Math.min(95, (s.ppPct || 0) + (3 + Math.random() * 5)) }; }); }, 200);
    var op = { clean: 'cleanup', summary: 'summary' }[S.ppOp] || 'summary';
    var text = getTranscript().map(function (l) { return l.text; }).join(' ');
    var acc = '';
    streamPost('/api/postprocess', { operation: op, transcript: text, model: S.ppModel }, function (ev) {
      if (ev.type === 'token') { acc += ev.text; setState({ ppOut: acc }); }
      else if (ev.type === 'error') { clearInterval(_ppIv); setState({ pp: 'done', ppPct: 100, ppOut: acc || ('Fel: ' + (ev.message || 'okänt')) }); }
      else if (ev.type === 'done') {
        clearInterval(_ppIv); var r = ev.result || {}; var out = r.text || acc;
        setState({ pp: 'done', ppPct: 100, ppOut: out });
        // Spara sammanfattningen till den öppna transkriberingen så den finns kvar.
        if (S.resultId && out && S.ppOp === 'summary') {
          fetch('/api/history/' + encodeURIComponent(S.resultId), { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ summary: out }) })
            .then(function () { loadHistory(); }).catch(function () {});
        }
      }
    });
  }
  function togglePPEnabled() { var next = !S.ppEnabled; setState({ ppEnabled: next }); if (next && S.run === 'done') { if (S.ppOp === 'chat') seedChat(); else runPP(); } }
  function afterDone() { if (!S.ppEnabled) return; if (S.ppOp === 'chat') seedChat(); else runPP(); }
  function seedChat() { if (S.chat.length) return; setState({ chat: [{ role: 'assistant', text: 'Transkriptet är klart. Fråga mig vad som helst — t.ex. "Vad var besluten?" eller "Sammanfatta på en mening."' }] }); }
  function onChatInput(e) { setState({ chatInput: e.target.value }); }
  function onChatKey(e) { if (e.key === 'Enter') sendChat(); }
  // BACKEND: real conversational chat via /api/chat (Ollama /api/chat) over the transcript.
  function sendChat() {
    var q = S.chatInput.trim();
    var att = S.chatAttach;
    if (!q && !att.length) return;
    var attNote = att.length ? att.map(function (a) { return a.label; }).join(', ') : '';
    var images = att.filter(function (a) { return a.kind === 'image' && a.data; }).map(function (a) { return a.data; });
    var userText = q || (att.length ? 'Titta på det bifogade.' : '');
    // push the user turn + an empty assistant placeholder we stream into
    setState(function (s) { return { chat: s.chat.concat([{ role: 'user', text: userText, attach: attNote }, { role: 'assistant', text: '', reason: '' }]), chatInput: '', chatAttach: [], chatTyping: true }; });
    var msgs = S.chat.filter(function (m) { return !(m.role === 'assistant' && !m.text); })
      .map(function (m) { return { role: m.role, content: m.text + (m.attach ? ' [bifogat: ' + m.attach + ']' : '') }; });
    var transcript = getTranscript().map(function (l) { return l.text; }).join(' ');
    var acc = '', accReason = '';
    var setLast = function (text, reason, typing) { setState(function (s) { var c = s.chat.slice(); if (c.length) c[c.length - 1] = { role: 'assistant', text: text, reason: reason }; return { chat: c, chatTyping: !!typing }; }); };
    streamPost('/api/chat', { messages: msgs, transcript: transcript, model: S.ppModel, images: images, think: S.chatThink }, function (ev) {
      if (ev.type === 'reasoning') { accReason += ev.text; setLast(acc, accReason, true); }
      else if (ev.type === 'token') { acc += ev.text; setLast(acc, accReason, false); }
      else if (ev.type === 'error') { setLast(acc || ('Fel: ' + (ev.message || 'okänt')), accReason, false); }
      else if (ev.type === 'done') { var r = ev.result || {}; setLast(r.text || acc, accReason, false); }
    });
  }
  function imageReply() { return 'Jag ser bilden. Den verkar visa en skärmdump kopplad till mötet — vill du att jag beskriver innehållet, läser av text i den (OCR) eller jämför den mot transkriptet?'; }
  function chatReply(q) {
    var t = q.toLowerCase();
    if (/beslut|ansvar|åtgärd/.test(t)) return 'Det viktigaste beslutet var att fördela ansvaret inför nästa steg — det kommer upp kring 00:13 i transkriptet.';
    if (/sammanfatt|en mening|kort/.test(t)) return 'Ett kort uppföljningsmöte där teamet stämde av förra veckans punkter och enades om tidsplan och ansvarsfördelning.';
    if (/ton|känsla|stämning/.test(t)) return 'Tonen är konstruktiv och samstämmig — deltagarna är överens och avslutar positivt.';
    if (/tid|plan|möte|när/.test(t)) return 'De bekräftar tidsplanen och nämner att nästa möte bokas inom kort.';
    return 'Utifrån transkriptet: de återkopplar till förra veckan (00:06), fördelar ansvaret (00:13) och avslutar med tack (00:21). Vill du att jag fördjupar någon del?';
  }
  function ppText() {
    var op = S.ppOp;
    if (op === 'summary') return 'Samtalet inleds med en återkoppling till föregående veckas diskussion och övergår sedan till nästa steg i projektet. Deltagarna är överens om tidsplanen och fördelar ansvaret för de kommande uppgifterna. Avsnittet avslutas med en kort sammanfattning och tack till lyssnarna.';
    return getTranscript().map(function (l) { return l.text; }).join(' ');
  }

  // BACKEND: model download/install simulate; replace with /api/download/* SSE.
  function modelAction(id) {
    if (S.installed[id]) { setState({ model: id, tab: 'transcribe' }); return; }
    if (S.downloading[id] || S.installing[id]) return;
    var disk = HW.disks.find(function (d) { return d.id === S.diskTarget; }) || HW.disks[0];
    var needGB = modelNeedGB(id);
    if (needGB > disk.free - 3) { setState({ diskWarn: { id: id, name: id, needGB: needGB, freeGB: disk.free, drive: disk.drive } }); return; }
    _startDownload(id);
  }
  function diskWarnUseBest() { var w = S.diskWarn; if (!w) return; var d = bestDisk(); setState({ diskTarget: d.id, diskWarn: null }); _startDownload(w.id); }
  function diskWarnCancel() { setState({ diskWarn: null }); }
  function cancelDownload(id) {
    if (_dl && _dl[id]) clearInterval(_dl[id]);
    if (_inst && _inst[id]) clearInterval(_inst[id]);
    setState(function (s) { return { downloading: Object.assign({}, s.downloading, kv(id, false)), installing: Object.assign({}, s.installing, kv(id, false)), dlFailed: Object.assign({}, s.dlFailed, kv(id, true)) }; });
  }
  function retryDownload(id) { setState(function (s) { return { dlFailed: Object.assign({}, s.dlFailed, kv(id, false)) }; }); _startDownload(id); }
  // BACKEND: real model download via /api/download/{whisper,llm} SSE.
  function _startDownload(id) {
    setState(function (s) { return { diskWarn: null, dlFailed: Object.assign({}, s.dlFailed, kv(id, false)), downloading: Object.assign({}, s.downloading, kv(id, true)), dlProg: Object.assign({}, s.dlProg, kv(id, 0)) }; });
    var isW = WHISPER.some(function (m) { return m.id === id; });
    var url = isW ? '/api/download/whisper' : '/api/download/llm';
    var body = isW ? { id: id } : { name: id };
    streamPost(url, body, function (ev) {
      if (ev.type === 'progress') { setState(function (s) { return { dlProg: Object.assign({}, s.dlProg, kv(id, ev.pct || 0)) }; }); }
      else if (ev.type === 'error') { setState(function (s) { return { downloading: Object.assign({}, s.downloading, kv(id, false)), dlFailed: Object.assign({}, s.dlFailed, kv(id, true)) }; }); }
      else if (ev.type === 'done') { setState(function (s) { return { downloading: Object.assign({}, s.downloading, kv(id, false)), installing: Object.assign({}, s.installing, kv(id, false)) }; }); loadModels(); }
    });
  }
  function runInstallTimer(id) {
    _inst = _inst || {};
    clearInterval(_inst[id]);
    _inst[id] = setInterval(function () {
      setState(function (s) {
        var cur = (s.instProg && s.instProg[id]) || 0;
        var nv = Math.min(100, cur + (4 + Math.random() * 5));
        if (nv >= 100) { clearInterval(_inst[id]); return { installed: Object.assign({}, s.installed, kv(id, true)), installing: Object.assign({}, s.installing, kv(id, false)), instProg: Object.assign({}, s.instProg, kv(id, 100)) }; }
        return { instProg: Object.assign({}, s.instProg, kv(id, nv)) };
      });
    }, 185);
  }
  function downloadFile(name, size) {
    clearInterval(_toastIv); clearTimeout(_toastT2);
    setState({ toast: { name: name, size: size || '24 KB', pct: 0, done: false } });
    _toastIv = setInterval(function () {
      setState(function (s) {
        if (!s.toast) { clearInterval(_toastIv); return null; }
        var nv = Math.min(100, (s.toast.pct || 0) + (11 + Math.random() * 17));
        if (nv >= 100) { clearInterval(_toastIv); _toastT2 = setTimeout(function () { setState({ toast: null }); }, 2600); return { toast: Object.assign({}, s.toast, { pct: 100, done: true }) }; }
        return { toast: Object.assign({}, s.toast, { pct: nv }) };
      });
    }, 140);
  }
  function closeToast() { clearInterval(_toastIv); clearTimeout(_toastT2); setState({ toast: null }); }

  function openTranscript() {
    setState({
      transcriptOpen: true, histViewing: null,
      mediaUrl: S.runMedia ? ('/api/media?path=' + encodeURIComponent(S.runMedia)) : null,
      audioT: 0, audioDur: 0, audioPlaying: false,
    });
  }
  function closeTranscript() { if (S.editing) { _commitEdits(); saveTranscriptEdits(); } if (_media) { try { _media.pause(); } catch (e) {} } clearInterval(_au); setState({ transcriptOpen: false, editing: false, audioPlaying: false }); }
  function openLog() { setState({ logOpen: true }); }
  function closeLog() { setState({ logOpen: false }); }
  function onTSearch(e) { setState({ searchQuery: e.target.value, currentMatch: 0 }); }
  function nextMatch() { var n = countMatches(); if (!n) return; setState(function (s) { return { currentMatch: (s.currentMatch + 1) % n }; }); }
  function prevMatch() { var n = countMatches(); if (!n) return; setState(function (s) { return { currentMatch: (s.currentMatch - 1 + n) % n }; }); }
  function onSearchKey(e) { if (e.key === 'Enter') { e.preventDefault(); if (e.shiftKey) prevMatch(); else nextMatch(); } }
  function searchRef(el) { _searchRef = el; }
  function scrollRef(el) { _scrollRef = el; }
  function procScrollRef(el) { _procScroll = el; }
  function showTip(e, text) { var r = e.currentTarget.getBoundingClientRect(); setState({ tip: { text: text, x: Math.round(r.left + r.width / 2), y: Math.round(r.top) } }); }
  function hideTip() { if (S.tip) setState({ tip: null }); }

  function kv(k, v) { var o = {}; o[k] = v; return o; }

  /* ----------------------------------------------------------- backend API -- */
  function modelLabel(id) { var m = WHISPER.concat(LLM).find(function (x) { return x.id === id; }); return (m && (m.label || m.id)) || id; }
  function getTranscript() { return (S.transcript && S.transcript.length) ? S.transcript : TRANSCRIPT; }
  function getJSON(url) { return fetch(url).then(function (r) { return r.json(); }); }

  function streamPost(url, body, onEvent) {
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (resp) {
        if (!resp.ok) {
          return resp.json().then(function (j) { onEvent({ type: 'error', message: (j && j.error) || ('HTTP ' + resp.status) }); })
            .catch(function () { onEvent({ type: 'error', message: 'HTTP ' + resp.status }); });
        }
        var reader = resp.body.getReader(), dec = new TextDecoder(), buf = '';
        function pump() {
          return reader.read().then(function (res) {
            if (res.done) return;
            buf += dec.decode(res.value, { stream: true });
            var parts = buf.split('\n\n'); buf = parts.pop();
            parts.forEach(function (chunk) {
              var line = chunk.split('\n').filter(function (l) { return l.indexOf('data:') === 0; })[0];
              if (line) { try { onEvent(JSON.parse(line.slice(5).trim())); } catch (e) {} }
            });
            return pump();
          });
        }
        return pump();
      })
      .catch(function (e) { onEvent({ type: 'error', message: String((e && e.message) || e) }); });
  }

  function loadModels() {
    return getJSON('/api/models').then(function (d) {
      if (!d || !d.whisper) return;
      WHISPER = d.whisper; LLM = d.llm || []; ONLINE = d.online || []; HW = d.hardware || HW;
      var inst = {};
      WHISPER.concat(LLM).forEach(function (m) { if (m.installed) inst[m.id] = true; });
      var patch = { catalogReady: true, installed: inst };
      var instW = WHISPER.filter(function (m) { return inst[m.id]; });
      if (instW.length) {
        // Keep the model in sync with the chosen language (Svenska/Engelska).
        var byLang = recommendModel(S.language, inst);
        patch.model = (byLang && inst[byLang]) ? byLang
          : (WHISPER.find(function (m) { return m.recommended && inst[m.id]; }) || instW[0]).id;
      }
      var instL = LLM.filter(function (m) { return inst[m.id]; });
      if (instL.length && !inst[S.ppModel]) {
        patch.ppModel = (LLM.find(function (m) { return m.recommended && inst[m.id]; }) || instL[0]).id;
      }
      setState(patch);
    }).catch(function () { /* dev/offline: keep mock catalog */ });
  }

  function loadHistory() {
    return getJSON('/api/history').then(function (h) { if (Array.isArray(h)) setState({ history: h }); }).catch(function () {});
  }

  function addFilesObjs(items) {
    var good = items.filter(function (it) { return isMedia(it.name) || /^https?:/i.test(it.path || ''); });
    var skipped = items.length - good.length;
    if (!good.length) { setState({ fileError: 'Filformatet stöds inte — välj ljud eller video (MP4, MKV, MOV, MP3, WAV, M4A …).', dragging: false }); return; }
    setState(function (s) {
      var existing = new Set(s.queue.map(function (q) { return q.path || q.name; }));
      var adds = good.filter(function (g) { return !existing.has(g.path || g.name); })
        .map(function (g, k) { return { id: 'q' + Date.now() + '_' + k, name: g.name, path: g.path || g.name }; });
      var queue = s.queue.concat(adds);
      var activeId = s.activeId || (queue[0] && queue[0].id) || null;
      return { queue: queue, dragging: false, step: 'config', activeId: activeId, source: qName(queue, activeId) || s.source, fileError: skipped ? ('Hoppade över ' + skipped + ' fil(er) — formatet stöds inte.') : '' };
    });
  }

  function saveResult(f) {
    var api = window.pywebview && window.pywebview.api;
    if (api && api.save_file) { try { api.save_file(f.name, f.path); } catch (e) {} }
    downloadFile(f.name, f.size);   // toast confirmation
  }

  /* --------------------------------------------------------- side-effects -- */
  function syncTheme() { document.documentElement.dataset.theme = S.theme; }
  function playPaneIn() {
    requestAnimationFrame(function () { requestAnimationFrame(function () {
      var pane = document.querySelector('[data-pane="process"]');
      if (!pane || !pane.animate) return;
      try { pane.style.transformOrigin = 'top center'; pane.animate([{ opacity: 0, transform: 'translateY(54px) scale(0.985)', filter: 'blur(3px)' }, { opacity: 1, transform: 'translateY(0) scale(1)', filter: 'blur(0)' }], { duration: 560, easing: 'cubic-bezier(.16,1,.3,1)', fill: 'none' }); } catch (e) {}
    }); });
  }
  function onAnyPress(e) {
    var btn = (e.target && e.target.closest) ? e.target.closest('button') : null;
    if (!btn || !btn.animate) return;
    try { btn.animate([{ transform: 'scale(1)' }, { transform: 'scale(0.92)' }, { transform: 'scale(1)' }], { duration: 300, easing: 'cubic-bezier(.34,1.45,.5,1)' }); } catch (err) {}
  }
  function playTabIn() {
    var sec = document.querySelector('main section');
    if (!sec || !sec.animate) return;
    try { sec.style.transformOrigin = 'top center'; sec.animate([{ opacity: 0, transform: 'scale(0.965)' }, { opacity: 1, transform: 'scale(1)' }], { duration: 440, easing: 'cubic-bezier(.16,1,.3,1)', fill: 'none' }); } catch (e) {}
  }
  function glideTo(targetY, duration) {
    duration = duration || 850;
    var root = document.scrollingElement || document.documentElement;
    var max = Math.max(0, root.scrollHeight - window.innerHeight);
    var end = Math.max(0, Math.min(targetY, max));
    var start = window.scrollY || root.scrollTop || 0;
    var dist = end - start;
    if (Math.abs(dist) < 2) return;
    var ease = function (t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
    cancelAnimationFrame(_glideRAF);
    var t0 = performance.now();
    var step = function (now) { var p = Math.min(1, (now - t0) / duration); window.scrollTo(0, start + dist * ease(p)); if (p < 1) _glideRAF = requestAnimationFrame(step); };
    _glideRAF = requestAnimationFrame(step);
  }
  function smoothScrollProc(sel) { setTimeout(function () { var el = document.querySelector(sel); if (!el) return; var y = el.getBoundingClientRect().top + window.scrollY - 92; glideTo(Math.max(0, y), 720); }, 70); }
  function playResultsIn() {
    requestAnimationFrame(function () { requestAnimationFrame(function () {
      var items = Array.prototype.slice.call(document.querySelectorAll('[data-pane="process"] [data-reveal]'));
      items.forEach(function (el, i) { if (!el.animate) return; try { el.animate([{ opacity: 0, transform: 'translateY(24px) scale(0.985)', filter: 'blur(7px)' }, { opacity: 1, transform: 'translateY(0) scale(1)', filter: 'blur(0)' }], { duration: 640, delay: i * 95, easing: 'cubic-bezier(.16,1,.3,1)', fill: 'backwards' }); } catch (e) {} });
    }); });
  }

  function applySideEffects() {
    syncTheme();
    if (S.editing && !_wasEditing) { _editBuf = {}; requestAnimationFrame(function () { document.querySelectorAll('[data-eline]').forEach(function (el) { var i = el.getAttribute('data-eline'); el.textContent = lineText(+i); }); }); }
    _wasEditing = S.editing;
    if (S.tab !== _prevTab) { _prevTab = S.tab; playTabIn(); }
    if (S.step !== _prevStep) { var to = S.step; _prevStep = to; if (to === 'process') playPaneIn(); }
    var open = S.transcriptOpen;
    if (open && !_wasOpen) { var inp = document.querySelector('[data-tsearch]'); if (inp) inp.focus(); }
    _wasOpen = open;
    if (open) {
      var key = S.currentMatch + '|' + S.searchQuery;
      if (key !== _scrollKey) {
        var cont = _scrollRef;
        var cur = cont && cont.querySelector('[data-current="1"]');
        if (cont && cur) { var cr = cont.getBoundingClientRect(), er = cur.getBoundingClientRect(); cont.scrollTop += (er.top - cr.top) - cr.height / 2; }
        _scrollKey = key;
      }
    }
    if (S.step === 'process') {
      var run = S.run, pp = S.pp, op = S.ppOp, chatLen = S.chat.length;
      if (run === 'done' && _prevRun !== 'done') { playResultsIn(); smoothScrollProc('[data-sec="results"]'); }
      else if (pp !== _prevPP && pp !== 'idle') smoothScrollProc('[data-sec="ppout"]');
      if (chatLen > (_prevChatLen || 0)) scrollChatBottom();
      _prevRun = run; _prevPP = pp; _prevOp = op; _prevChatLen = chatLen;
    } else {
      _prevRun = S.run; _prevPP = S.pp; _prevOp = S.ppOp; _prevChatLen = S.chat.length;
    }
  }

  function onKeyDown(e) {
    if (S.chatModalOpen && e.key === 'Escape') { closeChatModal(); return; }
    if (S.logOpen && e.key === 'Escape') { closeLog(); return; }
    if (!S.transcriptOpen) return;
    if ((e.ctrlKey || e.metaKey) && (e.key === 'f' || e.key === 'F')) { e.preventDefault(); var inp = document.querySelector('[data-tsearch]'); if (inp) inp.focus(); }
    else if (e.key === 'Escape') { closeTranscript(); }
  }

  /* ------------------------------------------------------------ view-model -- */
  function vm() {
    var st = S;
    var isRunning = st.run === 'running';
    var isDone = st.run === 'done';
    var cur = isDone ? STEPS.length : (st.progress < 12 ? 0 : st.progress < 28 ? 1 : st.progress < 92 ? 2 : 3);

    var installedWhisper = WHISPER.filter(function (m) { return st.installed[m.id]; });
    var rankedInstalled = rankModels(installedWhisper, 'whisper');
    var curModel = WHISPER.find(function (m) { return m.id === st.model; }) || WHISPER[0];
    var curFit = fitFor(curModel, 'whisper');
    var fitWord = function (t) { return t === 'ok' ? 'passar bra' : t === 'warn' ? 'tungt' : 'för stort'; };
    var modelOptions = rankedInstalled.map(function (o, i) {
      var m = o.m, f = o.f;
      return { rank: i + 1, name: m.label || m.id, meta: m.size + ' · ' + fitWord(f.tier), dot: f.dot, style: ddItem(m.id === st.model), checkStyle: 'color:var(--accent);font-size:14.5px;opacity:' + (m.id === st.model ? '1' : '0'), onPick: function () { pickModel(m.id); } };
    });

    var langs = [['sv', 'Svenska'], ['en', 'Engelska']];
    var langOptions = langs.map(function (p) { return { label: p[1], style: segBtn(st.language === p[0], '38px'), onPick: function () { pickLang(p[0]); } }; });
    // Result language: pick sv/en; if it differs from the source language the
    // subtitles are translated by the local text model.
    var targetLangs = [['sv', 'Svenska'], ['en', 'Engelska']];
    var targetLangOptions = targetLangs.map(function (p) { return { label: p[1], style: segBtn(st.targetLanguage === p[0], '34px'), onPick: function () { pickTargetLang(p[0]); } }; });
    var translateNote = (st.targetLanguage && st.language && st.targetLanguage !== st.language)
      ? ('Översätts till ' + (st.targetLanguage === 'sv' ? 'svenska' : 'engelska') + ' av språkmodellen.')
      : '';
    var formatChips = ['srt', 'txt', 'vtt'].map(function (f) { return { label: f.toUpperCase(), style: chip(st.formats[f]), onToggle: function () { toggleFmt(f); } }; });
    // Subtitle delivery for video sources: keep media + SRT side by side, or embed
    // the subtitles into the video (soft mux or hard burn). Only shown for video.
    var _activeQ = st.queue.find(function (q) { return q.id === st.activeId; }) || st.queue[0];
    var _activeIsVideo = !!(_activeQ && /\.(mp4|mkv|mov|webm|avi|m4v)$/i.test(_activeQ.name || ''));
    var subtitleOptions = [['separate', 'Spara separat'], ['embed', 'Bädda in']].map(function (p) { return { label: p[1], style: segBtn(st.subtitleMode === p[0], '34px'), onPick: function () { setState({ subtitleMode: p[0] }); } }; });
    var embedOptions = [['soft', 'Mjukt sub-spår'], ['burn', 'Hård inbränning']].map(function (p) { return { label: p[1], style: segBtn(st.embedKind === p[0], '34px'), onPick: function () { setState({ embedKind: p[0] }); } }; });

    var steps = STEPS.map(function (label, idx) {
      var done = idx < cur, active = idx === cur && !isDone;
      return {
        label: label, icon: done || isDone ? '✓' : (idx + 1),
        barStyle: 'height:4px;border-radius:99px;background:' + (done || isDone ? 'var(--ok)' : active ? 'var(--accent)' : 'var(--line)') + ';' + (active ? 'background-image:linear-gradient(90deg,var(--accent) 0,var(--accent) 50%,color-mix(in srgb,var(--accent) 30%,transparent) 50%,color-mix(in srgb,var(--accent) 30%,transparent));background-size:28px 100%;animation:flow .8s linear infinite;' : ''),
        dotStyle: 'width:18px;height:18px;border-radius:50%;flex:0 0 auto;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:600;' + (done || isDone ? 'background:var(--ok);color:#fff' : active ? 'background:var(--accent);color:#fff;animation:pulse 1.4s ease infinite' : 'background:transparent;border:1.5px solid var(--line-2);color:var(--ink-3)'),
        labelStyle: 'font-size:13.5px;font-weight:500;color:' + (done || isDone ? 'var(--ink)' : active ? 'var(--ink)' : 'var(--ink-3)'),
      };
    });

    var base = baseName();
    var fmtMeta = { srt: ['SRT', '38 KB'], txt: ['TXT', '21 KB'], vtt: ['VTT', '40 KB'] };
    var resultFiles = (st.resultFilesReal && st.resultFilesReal.length)
      ? st.resultFilesReal.map(function (f) { return { type: (f.ext || '').toUpperCase(), name: f.name, size: f.size, onDownload: function () { saveResult(f); } }; })
      : ['srt', 'txt', 'vtt'].filter(function (f) { return st.formats[f]; }).map(function (f) { return { type: fmtMeta[f][0], name: base + '.' + f, size: fmtMeta[f][1], onDownload: function () { downloadFile(base + '.' + f, fmtMeta[f][1]); } }; });

    var hw = hardwareView();
    var stepOrder = ['source', 'config', 'process'];
    var stepDefs = [['source', 'Källa'], ['config', 'Inställningar'], ['process', 'Resultat']];
    var curStepIdx = stepOrder.indexOf(st.step);
    var stepItems = stepDefs.map(function (p, i) {
      var state = i < curStepIdx ? 'done' : i === curStepIdx ? 'active' : 'todo';
      return {
        label: p[1], icon: state === 'done' ? '✓' : (i + 1),
        dotStyle: 'width:24px;height:24px;border-radius:50%;flex:0 0 auto;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600;' + (state === 'done' ? 'background:var(--ok);color:#fff' : state === 'active' ? 'background:var(--ink);color:var(--btn-fg)' : 'background:transparent;border:1.5px solid var(--line-2);color:var(--ink-3)'),
        labelStyle: 'font-size:14px;font-weight:' + (state === 'active' ? '600' : '500') + ';color:' + (state === 'todo' ? 'var(--ink-3)' : state === 'active' ? 'var(--ink)' : 'var(--ink-2)') + ';white-space:nowrap',
        lineStyle: i === stepDefs.length - 1 ? 'display:none' : 'flex:1;height:1.5px;background:var(--line);min-width:16px;margin:0 4px',
      };
    });
    var rankedWhisper = rankModels(WHISPER, 'whisper');
    var whisperRows = rankedWhisper.map(function (o, i) {
      var m = o.m, f = o.f;
      var inst = st.installed[m.id], dl = st.downloading[m.id], ing = st.installing[m.id], failed = st.dlFailed[m.id];
      var pct = ing ? (st.instProg[m.id] || 0) : (st.dlProg[m.id] || 0);
      var phase = dl ? 'downloading' : ing ? 'installing' : failed ? 'failed' : inst ? 'installed' : 'idle';
      return {
        rank: i + 1, name: m.label || m.id, size: m.size, dot: f.dot, recommended: !!m.recommended, verdict: f.verdict, verdictStyle: verdictPill(f.tier), useFor: m.useFor, chips: f.chips,
        rowStyle: rowStyleRich(i === rankedWhisper.length - 1),
        phase: phase, pct: pct, detail: ing ? instDetail(pct) : dlDetail(m.size, pct),
        onAction: function () { if (failed) retryDownload(m.id); else if (!inst && !dl && !ing) modelAction(m.id); },
        onCancel: function () { cancelDownload(m.id); }, removable: !!inst, notRemovable: !inst, onRemove: function () { askUninstall(m.id); },
      };
    });
    var uc = st.useCase || 'all';
    var llmPool = uc === 'all' ? LLM : LLM.filter(function (m) { return (m.uses || []).indexOf(uc) !== -1; });
    var rankedLLM = rankModels(llmPool, 'llm');
    var llmEmpty = rankedLLM.length === 0;
    var llmRows = rankedLLM.map(function (o, i) {
      var m = o.m, f = o.f;
      var inst = st.installed[m.id], dl = st.downloading[m.id], ing = st.installing[m.id], failed = st.dlFailed[m.id];
      var disabled = f.tier === 'bad';
      var pct = ing ? (st.instProg[m.id] || 0) : (st.dlProg[m.id] || 0);
      var phase = dl ? 'downloading' : ing ? 'installing' : disabled ? 'incompatible' : failed ? 'failed' : inst ? 'installed' : 'idle';
      return {
        rank: i + 1, name: m.label || m.id, size: m.size, dot: f.dot, recommended: !!m.recommended, verdict: f.verdict, verdictStyle: verdictPill(f.tier), useFor: m.useFor, chips: f.chips,
        rowStyle: rowStyleRich(i === rankedLLM.length - 1),
        phase: phase, pct: pct, detail: ing ? instDetail(pct) : dlDetail(m.size, pct),
        onAction: function () { if (failed) retryDownload(m.id); else if (!disabled && !inst && !dl && !ing) modelAction(m.id); },
        onCancel: function () { cancelDownload(m.id); }, removable: !!inst, notRemovable: !inst, onRemove: function () { askUninstall(m.id); },
      };
    });
    var q = st.search.trim().toLowerCase();
    var sortMode = st.onlineSort || 'fit';
    var tierW = { ok: 2, warn: 1, bad: 0 };
    var onlinePool = ONLINE.map(function (m) { return { m: m, f: estFit(m) }; });
    onlinePool = onlinePool.filter(function (o) {
      var m = o.m, f = o.f;
      if (uc !== 'all' && (m.uses || []).indexOf(uc) === -1) return false;
      if (!q) return true;
      var fw = f.tier === 'ok' ? 'passar bra lätt grön' : f.tier === 'warn' ? 'tight gul marginal' : 'över för stor röd';
      return [m.id, m.tag, m.size, fw].join(' ').toLowerCase().indexOf(q) !== -1;
    });
    onlinePool.sort(function (a, b) {
      if (sortMode === 'size') return parseFloat(a.m.size) - parseFloat(b.m.size);
      if (sortMode === 'name') return a.m.id.localeCompare(b.m.id);
      return (tierW[b.f.tier] * 1000 + b.f.head) - (tierW[a.f.tier] * 1000 + a.f.head);
    });
    var onlineRows = onlinePool.map(function (o, i) {
      var m = o.m, f = o.f;
      var inst = st.installed[m.id], dl = st.downloading[m.id], ing = st.installing[m.id];
      var pct = ing ? (st.instProg[m.id] || 0) : (st.dlProg[m.id] || 0);
      var phase = dl ? 'downloading' : ing ? 'installing' : inst ? 'installed' : 'idle';
      return { rank: i + 1, name: m.label || m.id, size: m.size, tag: m.tag, dot: f.dot, verdict: f.verdict, verdictStyle: verdictPill(f.tier), rowStyle: rowStyleRich(i === onlinePool.length - 1), phase: phase, pct: pct, detail: ing ? instDetail(pct) : dlDetail(m.size, pct), onAction: function () { if (!inst && !dl && !ing) modelAction(m.id); } };
    });
    var onlineSortOptions = [['fit', 'Passar din dator'], ['size', 'Storlek']].map(function (p) { return { label: p[1], style: segBtn(sortMode === p[0], '34px'), onPick: function () { setState({ onlineSort: p[0] }); } }; });
    var USECASES = [['all', 'Alla'], ['text', 'Textresonemang'], ['sv', 'Svensk text'], ['vision', 'Videoanalys · bild'], ['omni', 'Videoanalys · bild + tal']];
    var useCaseOptions = USECASES.map(function (p) { return { label: p[1], style: segBtn(uc === p[0], '30px') + ';flex:0 0 auto;font-size:13.5px;font-weight:500', onPick: function () { setUseCase(p[0]); } }; });

    var OPS = [['clean', 'Korrekturläs', 'Rättar stavfel & småfel — skriver inte om'], ['summary', 'Summera', 'Korta ner till det viktiga'], ['chat', 'Chatta', 'Ställ frågor om innehållet']];
    var ppOps = OPS.map(function (p) { return { key: p[0], label: p[1], sub: p[2], onPick: function () { pickOp(p[0]); }, selected: st.ppOp === p[0], unselected: st.ppOp !== p[0] }; });
    var ppModelOptions = LLM.filter(function (m) { return m.fit !== 'bad'; }).map(function (m) { return { name: m.label || m.id, size: m.size, style: ddItem(m.id === st.ppModel), onPick: function () { pickPPModel(m.id); } }; });
    var ppOutTitles = { summary: 'Sammanfattning', clean: 'Korrekturläst text' };
    var ppOpLabel = (ppOps.find(function (o) { return o.key === st.ppOp; }) || {}).label;
    var chat = st.chat.map(function (m) {
      return {
        text: m.text, hasAttach: !!m.attach, attach: m.attach || '',
        reason: m.reason || '', hasReason: !!(m.reason && m.reason.length),
        rowStyle: 'display:flex;flex-direction:column;gap:5px;align-items:' + (m.role === 'user' ? 'flex-end' : 'flex-start'),
        bubbleStyle: m.role === 'user' ? 'max-width:82%;background:var(--btn-bg);color:var(--btn-fg);border-radius:15px 15px 4px 15px;padding:11px 15px;font-size:15.5px;line-height:1.5' : 'max-width:82%;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:15px 15px 15px 4px;padding:11px 15px;font-size:15.5px;line-height:1.5',
        attachStyle: 'display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);border-radius:8px;padding:4px 9px;font-variant-numeric:tabular-nums',
        reasonStyle: 'max-width:82%;background:var(--sunken);border:1px dashed var(--line-2);color:var(--ink-2);border-radius:13px;padding:9px 13px;font-size:13px;line-height:1.5;white-space:pre-wrap',
      };
    });

    var cm = LLM.find(function (m) { return m.id === st.ppModel; }) || LLM[0];
    var caps = (cm && cm.caps) || { vision: false, files: ['TXT'] };
    var chipBase = 'display:inline-flex;align-items:center;gap:6px;font-size:12.5px;font-weight:500;padding:5px 11px;border-radius:8px;';
    var neutralChip = chipBase + 'color:var(--ink);background:var(--surface);border:1px solid var(--line)';
    var chatCaps = [
      { label: caps.vision ? 'Bildanalys' : 'Endast text', style: chipBase + (caps.vision ? 'color:var(--accent);background:var(--accent-weak);border:1px solid color-mix(in srgb,var(--accent) 22%,transparent)' : 'color:var(--ink-2);background:var(--surface);border:1px solid var(--line)') },
      { label: 'Kontext ' + cm.ctx, style: neutralChip },
      { label: cm.toks + ' tok/s', style: neutralChip },
      { label: caps.files.length + ' filformat', style: neutralChip },
    ];
    var chatModelOptions = LLM.map(function (m) {
      return { name: m.label || m.id, size: m.size, visionStyle: 'font-size:10px;font-weight:700;letter-spacing:.03em;text-transform:uppercase;color:var(--accent);background:var(--accent-weak);border-radius:5px;padding:1px 6px;flex:0 0 auto;' + ((m.caps && m.caps.vision) ? '' : 'display:none'), style: ddItem(m.id === st.ppModel), checkStyle: 'color:var(--accent);font-size:14.5px;opacity:' + (m.id === st.ppModel ? '1' : '0'), onPick: function () { pickChatModel(m.id); } };
    });
    var chatAttachments = st.chatAttach.map(function (a, i) { return { label: a.label, thumb: a.data || '', dotStyle: 'width:7px;height:7px;border-radius:2px;flex:0 0 auto;background:' + (a.kind === 'image' ? 'var(--accent)' : 'var(--ink-3)'), onRemove: function () { removeAttach(i); } }; });

    var lastIdx = st.log.length - 1;
    var logRows = st.log.map(function (line, i) {
      var time = '', msg = line, isKlar = false;
      if (line.indexOf('› ') === 0) { msg = line.slice(2); }
      else { var mm = line.match(/^\[([^\]]+)\]\s*(.*)$/); if (mm) { time = mm[1]; msg = mm[2]; if (time === 'klar') { isKlar = true; time = ''; } } }
      var last = i === lastIdx;
      var green = st.run === 'done' || !last;
      var dotStyle = green ? 'width:13px;height:13px;border-radius:50%;flex:0 0 auto;display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:700;color:#fff;background:var(--ok)' : 'width:13px;height:13px;border-radius:50%;flex:0 0 auto;background:var(--surface);border:2px solid var(--line-2);box-sizing:border-box';
      return { time: time, msg: msg, icon: (green && isKlar) ? '✓' : '', dotStyle: dotStyle, lineStyle: 'width:2px;flex:1;min-height:12px;margin-top:2px;background:var(--line);' + (last ? 'display:none' : '') };
    });

    var viewingHist = st.histViewing ? st.history.find(function (h) { return h.id === st.histViewing; }) : null;
    var transcriptFileName = viewingHist ? viewingHist.name : (baseName() + '.txt');
    var aT = st.audioT;
    var dur = st.audioDur > 0 ? st.audioDur : AUDIO_DUR;
    var curLine = -1;
    for (var k2 = 0; k2 < getTranscript().length; k2++) { if (parseTS(getTranscript()[k2].time) <= aT) curLine = k2; else break; }
    var q0 = st.searchQuery.trim();
    var mIdx = 0;
    var tLines = getTranscript().map(function (ln, idx) {
      var text = lineText(idx);
      var isCurrent = idx === curLine && (st.audioPlaying || aT > 0);
      var segments;
      if (!q0 || st.editing) { segments = [{ text: text, plain: true, match: false, current: false }]; }
      else {
        segments = [];
        var t = text, tl = text.toLowerCase(), ql = q0.toLowerCase(), pos = 0, i;
        while ((i = tl.indexOf(ql, pos)) !== -1) { if (i > pos) segments.push({ text: t.slice(pos, i), plain: true, match: false, current: false }); var isCur = mIdx === st.currentMatch; segments.push({ text: t.slice(i, i + ql.length), plain: false, match: !isCur, current: isCur }); mIdx++; pos = i + ql.length; }
        if (pos < t.length) segments.push({ text: t.slice(pos), plain: true, match: false, current: false });
        if (!segments.length) segments.push({ text: t, plain: true, match: false, current: false });
      }
      return {
        idx: idx, time: ln.time, text: text, segments: segments,
        current: isCurrent,
        rowStyle: 'display:flex;gap:18px;padding:7px 12px;border-radius:11px;scroll-margin-top:90px;transition:background .2s;' + (isCurrent ? 'background:var(--accent-weak)' : ''),
        timeStyle: 'font-size:13px;width:50px;flex:0 0 auto;padding-top:6px;font-variant-numeric:tabular-nums;cursor:pointer;color:' + (isCurrent ? 'var(--accent)' : 'var(--ink-3)') + ';font-weight:' + (isCurrent ? '600' : '400'),
        editStyle: 'flex:1;font-size:18px;line-height:1.7;color:var(--ink);outline:none;border-radius:7px;padding:1px 8px;margin:-1px -8px;background:var(--sunken);box-shadow:inset 0 0 0 1px var(--line)',
        onJump: function () { jumpToLine(idx); },
      };
    });
    var totalM = mIdx;
    var matchLabel = !q0 ? '' : totalM ? (st.currentMatch + 1) + '/' + totalM : '0/0';
    if (!_wave) _wave = Array.from({ length: 72 }, function (_, k) { return 16 + Math.round((Math.abs(Math.sin(k * 1.7) + Math.sin(k * 0.55) * 0.7) / 1.7) * 78); });
    var aPct = Math.max(0, Math.min(100, (st.audioT / dur) * 100));
    var waveBars = _wave.map(function (h, k) { return { style: 'flex:1;height:' + h + '%;border-radius:2px;min-width:2px;align-self:center;background:' + (((k / _wave.length) * 100) <= aPct ? 'var(--accent)' : 'var(--line-2)') + ';transition:background .15s' }; });

    var statusWord = { pending: 'Väntar', running: 'Kör', done: 'Klar', error: 'Fel' };
    var statusCol = { pending: 'var(--ink-3)', running: 'var(--accent)', done: 'var(--ok)', error: 'var(--bad)' };
    var queueItems = st.queue.map(function (qq) {
      var status = st.qStatus[qq.id] || 'pending';
      var pct = st.qProgress[qq.id] || 0;
      var isActive = qq.id === st.activeId && st.step === 'process';
      return {
        id: qq.id, name: qq.name, ext: (/^https?:/i.test(qq.path || '') ? 'URL' : (extOf(qq.name) || 'fil').toUpperCase()), status: status, statusLabel: statusWord[status], pct: pct,
        dotStyle: 'width:9px;height:9px;border-radius:50%;flex:0 0 auto;background:' + statusCol[status] + (status === 'running' ? ';animation:pulse 1.4s ease infinite' : ''),
        statusStyle: 'font-size:12.5px;font-weight:600;color:' + statusCol[status] + ';font-variant-numeric:tabular-nums;flex:0 0 auto',
        barStyle: 'height:100%;width:' + (status === 'done' ? 100 : status === 'running' ? pct : 0) + '%;background:' + statusCol[status] + ';border-radius:99px;transition:width .3s ease',
        showBar: status === 'running' || status === 'done',
        rowStyle: 'display:flex;align-items:center;gap:12px;padding:11px 14px;border-radius:13px;border:1px solid ' + (isActive ? 'var(--line-2)' : 'var(--line)') + ';background:' + (isActive ? 'var(--sunken)' : 'var(--surface)') + ';box-shadow:var(--shadow-sm)',
        canRemove: st.step !== 'process', onRemove: function () { removeQ(qq.id); },
      };
    });
    var doneCount = st.queue.filter(function (qq) { return st.qStatus[qq.id] === 'done'; }).length;
    var noWhisper = !WHISPER.some(function (m) { return st.installed[m.id]; });
    var historyItems = st.history.map(function (h) {
      return {
        id: h.id, name: h.name, date: h.date,
        meta: h.dur + ' · ' + h.model + ' · ' + h.lang,
        formats: (h.formats || []).map(function (f) { return { label: f }; }),
        onOpen: function () { openHistory(h); }, onRerun: function () { askRerun(h); }, onDelete: function () { askDeleteHistory(h.id, h.name); },
        onDownload: function () { downloadFile(baseNameOf(h.name) + '.' + ((h.formats && h.formats[0]) || 'TXT').toLowerCase(), Math.max(9, Math.round((h.words || 3000) / 140)) + ' KB'); },
        thumbUrl: (h.video && h.video.path) ? ('/api/thumb?path=' + encodeURIComponent(h.video.path)) : null,
      };
    });

    return {
      theme: st.theme,
      tabTranscribe: st.tab === 'transcribe', tabModels: st.tab === 'models', tabHistory: st.tab === 'history',
      onTabT: function () { setTab('transcribe'); }, onTabM: function () { setTab('models'); }, onTabH: function () { setTab('history'); },
      tabTStyle: tabBtn(st.tab === 'transcribe'), tabMStyle: tabBtn(st.tab === 'models'), tabHStyle: tabBtn(st.tab === 'history'),
      toggleTheme: toggleTheme,

      queueItems: queueItems, queueCount: st.queue.length, multiQueue: st.queue.length > 1, hasQueue: st.queue.length > 0,
      queueDoneCount: doneCount, queueSummary: doneCount + ' av ' + st.queue.length + ' klara',
      fileError: st.fileError, hasFileError: !!st.fileError,
      addSampleNormal: function () { addSample('mötesinspelning.mp3'); }, addSampleCorrupt: function () { addSample('skadad_inspelning.m4a'); },

      noWhisper: noWhisper, hasWhisper: !noWhisper,
      gotoModels: function () { setTab('models'); }, getRecommended: function () { setTab('models'); modelAction('KB-Whisper large'); },

      isError: st.run === 'error', isCancelled: st.run === 'cancelled', notErrorState: st.run !== 'error' && st.run !== 'cancelled',
      runErrorTitle: st.runError ? st.runError.title : '', runErrorDetail: st.runError ? st.runError.detail : '',
      onCancelRun: cancelRun, onResumeRun: resumeRun, onRetryRun: retryRun,

      historyItems: historyItems, historyEmpty: st.history.length === 0, historyCount: st.history.length,

      waveBars: waveBars, audioPlaying: st.audioPlaying, audioPaused: !st.audioPlaying,
      audioCur: fmtTime(st.audioT), audioDur: fmtTime(dur),
      mediaUrl: st.mediaUrl, hasMediaEl: !!st.mediaUrl, mediaRef: mediaRef,
      onTogglePlay: togglePlay, onSeekClick: onSeekClick, seekTrackRef: seekTrackRef,
      editing: st.editing, notEditing: !st.editing, onToggleEdit: toggleEdit, onEditInput: onEditInput,
      editBtnLabel: st.editing ? '✓ Klar' : 'Redigera', transcriptEdited: st.edited,
      editBtnStyle: st.editing ? 'flex:0 0 auto;display:inline-flex;align-items:center;gap:6px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:10px;padding:8px 15px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit' : 'flex:0 0 auto;display:inline-flex;align-items:center;gap:7px;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:8px 15px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit',
      transcriptFileName: transcriptFileName,

      diskWarnOpen: !!st.diskWarn, diskWarnName: st.diskWarn ? st.diskWarn.name : '',
      diskWarnText: st.diskWarn ? ('Modellen behöver ungefär ' + st.diskWarn.needGB + ' GB ledigt, men ' + st.diskWarn.drive + ' har bara ' + fmtStorage(st.diskWarn.freeGB) + ' kvar.') : '',
      diskWarnBestLabel: st.diskWarn ? ('Ladda ner till ' + bestDisk().drive + ' · ' + fmtStorage(bestDisk().free) + ' ledigt') : '',
      onDiskWarnUseBest: diskWarnUseBest, onDiskWarnCancel: diskWarnCancel,

      confirmOpen: !!st.confirm, confirmTitle: st.confirm ? st.confirm.title : '', confirmBody: st.confirm ? st.confirm.body : '', confirmLabel: st.confirm ? st.confirm.label : 'OK',
      confirmBtnStyle: (st.confirm && st.confirm.danger) ? 'display:inline-flex;align-items:center;justify-content:center;background:var(--bad);color:#fff;border:none;border-radius:11px;padding:11px 20px;font-size:15px;font-weight:600;cursor:pointer;font-family:inherit' : primaryBtn(false),
      onConfirmYes: confirmYes, onConfirmNo: confirmNo,

      source: st.source, onSource: onSource,
      hasSource: !!(st.source && st.source.trim()), noSource: !(st.source && st.source.trim()),
      stepSource: st.step === 'source', stepConfig: st.step === 'config', stepProcess: st.step === 'process',
      stepItems: stepItems, restart: restart, goSource: goSource, sourceLabel: st.source || 'okänd källa',
      openPicker: openPicker, fileRef: fileRef, onPickFile: onPickFile, onDragOver: onDragOver, onDragLeave: onDragLeave, onDrop: onDrop,
      urlInput: st.urlInput, onUrlInput: onUrlInput, onAddUrl: addUrl, onUrlKey: onUrlKey,
      dropzoneStyle: 'position:relative;border:1.5px dashed ' + (st.dragging ? 'var(--accent)' : 'var(--line-2)') + ';border-radius:20px;background:' + (st.dragging ? 'var(--accent-weak)' : 'var(--surface)') + ';flex:1 1 auto;min-height:200px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:32px 24px;text-align:center;box-shadow:var(--shadow-sm);cursor:pointer;user-select:none;-webkit-user-select:none;transition:border-color .12s,background .12s',
      curModelName: curModel.label || curModel.id,
      curModelMeta: 'Väljs automatiskt · ' + (st.language === 'en' ? 'Engelska' : 'Svenska'),
      curModelDot: curFit.dot,
      langOptions: langOptions, formatChips: formatChips,
      targetLangOptions: targetLangOptions, translateNote: translateNote,
      subtitleOptions: subtitleOptions, embedOptions: embedOptions,
      showSubtitleMode: _activeIsVideo, showEmbed: st.subtitleMode === 'embed' && _activeIsVideo,
      audioCorrect: st.audioCorrect, onToggleAudioCorrect: toggleAudioCorrect,
      audioModelInstalled: st.audioModelInstalled, audioModelDownloading: st.audioModelDownloading,
      onDownloadAudioModel: downloadAudioModel,
      acSwitchTrack: 'position:relative;width:42px;height:25px;border-radius:999px;flex:0 0 auto;background:' + (st.audioCorrect ? 'var(--ink)' : 'var(--line-2)') + ';transition:background .15s;cursor:pointer',
      acSwitchKnob: 'position:absolute;top:3px;left:3px;width:19px;height:19px;border-radius:50%;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.2);transition:transform .15s;transform:translateX(' + (st.audioCorrect ? '17px' : '0') + ')',

      onStart: start, isRunning: isRunning, notRunning: !isRunning,
      startBtnLabel: isRunning ? 'Transkriberar…' : isDone ? 'Kör igen' : (st.queue.length > 1 ? 'Starta · ' + st.queue.length + ' filer' : 'Starta'),
      startBtnStyle: coralBtn(isRunning) + ';width:100%;padding:16px 24px;font-size:16.5px',
      startBtnStyleBar: primaryBtn(isRunning) + ';padding:12px 22px;font-size:15px;border-radius:11px;flex:0 0 auto',

      showStatus: st.step === 'process',
      statusBadge: st.run === 'error' ? 'FEL' : st.run === 'cancelled' ? 'AVBRUTEN' : isDone ? 'KLAR' : 'KÖR',
      statusBadgeStyle: (function (col) { return "font-family:'Geist',system-ui,sans-serif;font-size:12px;font-weight:500;color:" + col + ";background:color-mix(in srgb," + col + " 14%,transparent);padding:3px 9px;border-radius:6px;letter-spacing:0.05em"; })(st.run === 'error' ? 'var(--bad)' : st.run === 'cancelled' ? 'var(--ink-3)' : isDone ? 'var(--ok)' : 'var(--accent)'),
      statusFile: baseName(), elapsedLabel: fmtTime(st.elapsed), progressLabel: Math.round(st.progress) + '%', steps: steps,
      logText: st.log.join('\n'), logRows: logRows, logClipped: logRows.length > 3,
      logOpen: st.logOpen, openLog: openLog, closeLog: closeLog,
      hasToast: !!st.toast, toastName: st.toast && st.toast.name, toastLoading: !!st.toast && !st.toast.done, toastDone: !!st.toast && st.toast.done,
      toastTitle: st.toast ? (st.toast.title || (st.toast.done ? 'Nedladdning klar' : 'Laddar ner …')) : '', closeToast: closeToast,
      toastPct: st.toast ? Math.round(st.toast.pct || 0) : 0, toastDetail: st.toast ? (st.toast.detail != null ? st.toast.detail : toastDetail(st.toast.size, st.toast.pct || 0)) : '',
      toastBarStyle: 'height:100%;width:' + (st.toast ? Math.round(st.toast.pct || 0) : 0) + '%;background:var(--accent);border-radius:99px;transition:width .14s linear',
      transcriptOpen: st.transcriptOpen, openTranscript: openTranscript, closeTranscript: closeTranscript, transcriptFile: baseName() + '.txt',
      searchQuery: st.searchQuery, onTSearch: onTSearch, onSearchKey: onSearchKey, searchRef: searchRef, scrollRef: scrollRef,
      nextMatch: nextMatch, prevMatch: prevMatch, matchLabel: matchLabel, tLines: tLines,

      showResults: isDone, resultCount: resultFiles.length, resultDuration: fmtTime(st.elapsed), resultFiles: resultFiles,
      transcript: getTranscript().slice(0, 3).map(function (ln, idx) { return { time: ln.time, text: lineText(idx) }; }),

      ppEnabled: st.ppEnabled, ppOff: !st.ppEnabled, togglePPEnabled: togglePPEnabled,
      ppSwitchTrack: 'position:relative;width:42px;height:25px;border-radius:999px;flex:0 0 auto;background:' + (st.ppEnabled ? 'var(--ink)' : 'var(--line-2)') + ';transition:background .15s',
      ppSwitchKnob: 'position:absolute;top:3px;left:3px;width:19px;height:19px;border-radius:50%;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.2);transition:transform .15s;transform:translateX(' + (st.ppEnabled ? '17px' : '0') + ')',
      ppOps: ppOps, ppModel: st.ppModel, togglePPDD: togglePPDD, ppDDOpen: st.openDD === 'ppmodel', ppModelOptions: ppModelOptions,
      showPP: isDone, ppOpLabel: ppOpLabel, ppShowRun: st.ppOp !== 'chat', onRunPP: runPP, ppRunLabel: 'Kör',
      ppRunBtnStyle: primaryBtn(st.pp === 'running') + ';min-width:152px', ppRunIdle: st.pp !== 'running', ppPct: Math.round(st.ppPct || 0),
      ppRingStyle: 'position:relative;width:22px;height:22px;border-radius:50%;flex:0 0 auto;background:conic-gradient(var(--accent) ' + (Math.round(st.ppPct || 0) * 3.6) + 'deg, rgba(255,255,255,.2) 0);animation:ppglow 1.6s ease-in-out infinite;transition:background .13s linear',
      ppShowText: st.ppOp !== 'chat' && st.pp !== 'idle', ppShowChat: st.ppOp === 'chat', ppRunning: st.pp === 'running', ppShowOut: st.pp === 'done',
      ppTextDone: st.pp === 'done' && st.ppOp !== 'chat', ppCleanDone: false,
      ppCleanLines: getTranscript().map(function (ln, idx) { return { time: ln.time, text: lineText(idx) }; }),
      ppCleanFiles: resultFiles, ppOut: st.ppOut, ppOutTitle: ppOutTitles[st.ppOp],
      chat: chat, chatTyping: st.chatTyping, chatInput: st.chatInput, onChatInput: onChatInput, onChatKey: onChatKey, onChatSend: sendChat, chatSendStyle: primaryBtn(false),
      chatModalOpen: st.chatModalOpen, openChatModal: openChatModal, closeChatModal: closeChatModal, stop: stopProp, chatThreadRef: chatThreadRef, chatOpenBtnStyle: primaryBtn(false),
      chatThink: st.chatThink, onToggleChatThink: toggleChatThink,
      chatThinkBtnStyle: 'display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:500;font-family:inherit;cursor:pointer;border-radius:99px;padding:6px 12px;border:1px solid ' + (st.chatThink ? 'color-mix(in srgb,var(--accent) 40%,transparent);background:var(--accent-weak);color:var(--accent)' : 'var(--line);background:var(--surface);color:var(--ink-2)'),
      chatThinkHint: st.chatThink ? 'Tänker djupare före svar — bättre på svåra flerstegsfrågor, men något långsammare.' : 'Snabbt svar utan synligt resonemang. Slå på för svåra flerstegsfrågor.',
      chatModelName: cm.label || cm.id, chatModelDesc: cm.useFor,
      chatKind: 'text + bild',
      chatCtx: cm.ctx, chatPlusAttach: attachImage, imgInputRef: imgInputRef, onPickImage: onPickImage,
      chatCaps: chatCaps, chatModelOptions: chatModelOptions, chatModelDDOpen: st.openDD === 'chatmodel', toggleChatModelDD: toggleChatModelDD,
      chatAttachments: chatAttachments, hasAttach: st.chatAttach.length > 0, attachImage: attachImage,

      hwTiles: hw.tiles, hwSpecs: hw.specs, hwReady: hw.ready,
      diskOptions: hw.diskOptions, diskDDOpen: st.openDD === 'disk', toggleDiskDD: toggleDiskDD,
      curDiskDrive: hw.selDisk.drive, curDiskName: hw.selDisk.name, curDiskFree: fmtStorage(hw.selDisk.free) + ' ledigt',
      whisperRows: whisperRows, llmRows: llmRows, onlineRows: onlineRows, onlineSortOptions: onlineSortOptions,
      onlineEmpty: onlineRows.length === 0, llmEmpty: llmEmpty,
      search: st.search, onSearch: onSearch, useCaseOptions: useCaseOptions, infoBadgeStyle: infoBadgeStyle(),
      useCaseTip: infoBadge('Filtrerar och rangordnar språk- och videomodellerna efter uppgift — textresonemang, svensk text, videoanalys på bild eller bild + tal. Transkriberingsmodellerna ovan påverkas inte.'),

      tipOpen: !!st.tip, tipText: st.tip ? st.tip.text : '', tipStyle: tipStyleFor(),
      tipFullscreen: infoBadge('Klicka för helskärm'),

      anyDDOpen: st.openDD !== null, closeDD: closeDD,
    };
  }

  /* --------------------------------------------------------------- runtime -- */
  var H = [];                // per-render handler/ref registry
  var pendingCbs = [];
  var _raf = false;

  function on(fn) { if (typeof fn !== 'function') return '-1'; return String(H.push(fn) - 1); }
  window.__tr_on = on;       // exposed so view modules can register handlers

  function setState(patch, cb) {
    if (typeof patch === 'function') patch = patch(S);
    if (patch == null) { if (cb) pendingCbs.push(cb); if (cb) scheduleRender(); return; }
    Object.assign(S, patch);
    if (cb) pendingCbs.push(cb);
    scheduleRender();
  }
  function scheduleRender() { if (_raf) return; _raf = true; requestAnimationFrame(function () { _raf = false; render(); }); }

  function render() {
    var root = document.getElementById('root');
    if (!root) return;
    H = [];
    var v = vm();
    var htmlStr = view(v);
    morphdom(root, '<div id="root">' + htmlStr + '</div>', {
      childrenOnly: true,
      // Key the wizard panes by data-pane so morphdom REPLACES (not reuses) the node when the
      // step changes — otherwise the config pane's fill:forwards fly-out animation (from start())
      // sticks to the reused node and leaves the process pane stuck at opacity:0.
      getNodeKey: function (node) { return node.nodeType === 1 ? (node.getAttribute('data-key') || node.getAttribute('data-pane') || node.id || null) : null; },
      onBeforeElUpdated: function (from, to) {
        if (from.nodeType === 1 && from.hasAttribute('data-eline') && S.editing) return false;
        return true;
      },
    });
    root.querySelectorAll('[data-ref]').forEach(function (el) { var f = H[+el.dataset.ref]; if (typeof f === 'function') f(el); });
    applySideEffects();
    var cbs = pendingCbs; pendingCbs = []; cbs.forEach(function (cb) { try { cb(); } catch (e) {} });
  }

  /* event delegation: data-click / -input / -change / -keydown / -enter / -leave / -dragover / -dragleave / -drop */
  function dispatch(el, key, e) { if (!el) return; var idx = el.getAttribute('data-' + key); if (idx == null) return; var fn = H[+idx]; if (typeof fn === 'function') fn(e); }
  function bindEvents(root) {
    root.addEventListener('click', function (e) { var el = e.target.closest('[data-click]'); dispatch(el, 'click', e); });
    root.addEventListener('input', function (e) { var el = e.target.closest('[data-input]'); dispatch(el, 'input', e); });
    root.addEventListener('change', function (e) { var el = e.target.closest('[data-change]'); dispatch(el, 'change', e); });
    root.addEventListener('keydown', function (e) { var el = e.target.closest('[data-keydown]'); dispatch(el, 'keydown', e); });
    root.addEventListener('dragover', function (e) { var el = e.target.closest('[data-dragover]'); if (el) dispatch(el, 'dragover', e); });
    root.addEventListener('dragleave', function (e) { var el = e.target.closest('[data-dragleave]'); if (el) dispatch(el, 'dragleave', e); });
    root.addEventListener('drop', function (e) { var el = e.target.closest('[data-drop]'); if (el) dispatch(el, 'drop', e); });
    // hover: data-sh visual styles + data-enter/data-leave handlers (tooltips)
    root.addEventListener('pointerover', function (e) {
      var sh = e.target.closest('[data-sh]');
      if (sh && sh._shBase === undefined) { sh._shBase = sh.getAttribute('style') || ''; applyDecls(sh, sh.getAttribute('data-sh')); }
      var en = e.target.closest('[data-enter]'); dispatch(en, 'enter', e);
    });
    root.addEventListener('pointerout', function (e) {
      var sh = e.target.closest('[data-sh]');
      if (sh && sh._shBase !== undefined && !sh.contains(e.relatedTarget)) { sh.setAttribute('style', sh._shBase); sh._shBase = undefined; }
      var lv = e.target.closest('[data-leave]'); if (lv && !lv.contains(e.relatedTarget)) dispatch(lv, 'leave', e);
    });
  }
  function applyDecls(el, css) {
    if (!css) return;
    css.split(';').forEach(function (d) {
      d = d.trim(); if (!d) return;
      var i = d.indexOf(':'); if (i < 0) return;
      var prop = d.slice(0, i).trim();
      var val = d.slice(i + 1).trim(); var pri = '';
      if (/!important$/.test(val)) { pri = 'important'; val = val.replace(/!important$/, '').trim(); }
      el.style.setProperty(prop, val, pri);
    });
  }

  /* ----------------------------------------------------------------- views -- */
  function viewHeader(v) {
    return '' +
    '<header style="position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:24px;padding:16px 32px;border-bottom:1px solid var(--line);background:color-mix(in srgb, var(--canvas) 82%, transparent);backdrop-filter:saturate(1.4) blur(14px)">' +
      '<div style="display:flex;align-items:center;gap:11px;min-width:200px">' +
        '<div style="display:flex;align-items:flex-end;gap:2.5px;height:20px">' +
          '<div style="width:3px;height:7px;border-radius:2px;background:var(--ink)"></div>' +
          '<div style="width:3px;height:14px;border-radius:2px;background:var(--ink)"></div>' +
          '<div style="width:3px;height:20px;border-radius:2px;background:var(--accent)"></div>' +
          '<div style="width:3px;height:11px;border-radius:2px;background:var(--ink)"></div>' +
          '<div style="width:3px;height:16px;border-radius:2px;background:var(--ink)"></div>' +
        '</div>' +
        '<span style="font-size:17.5px;font-weight:600;letter-spacing:-0.02em">Transkribera</span>' +
      '</div>' +
      '<nav style="flex:1;display:flex;justify-content:center">' +
        '<div style="display:inline-flex;gap:3px;padding:4px;background:var(--track);border-radius:12px;border:1px solid var(--line)">' +
          '<button data-click="' + on(v.onTabT) + '" style="' + v.tabTStyle + '" data-sh="background:var(--surface) !important;color:var(--ink) !important;box-shadow:var(--shadow-sm) !important">Transkribera</button>' +
          '<button data-click="' + on(v.onTabH) + '" style="' + v.tabHStyle + '" data-sh="background:var(--surface) !important;color:var(--ink) !important;box-shadow:var(--shadow-sm) !important">Historik</button>' +
          '<button data-click="' + on(v.onTabM) + '" style="' + v.tabMStyle + '" data-sh="background:var(--surface) !important;color:var(--ink) !important;box-shadow:var(--shadow-sm) !important">Modeller</button>' +
        '</div>' +
      '</nav>' +
      '<div style="min-width:200px;display:flex;justify-content:flex-end;align-items:center;gap:12px">' +
        '<span style="display:inline-flex;align-items:center;gap:8px;background:color-mix(in srgb,var(--ok) 13%,transparent);color:var(--ok);border-radius:999px;padding:5px 12px 5px 10px;font-size:13.5px;font-weight:500">' +
          '<span style="width:7px;height:7px;border-radius:50%;background:var(--ok)"></span>Ansluten' +
        '</span>' +
        '<button data-click="' + on(v.toggleTheme) + '" aria-label="Växla tema" style="position:relative;width:38px;height:38px;border-radius:10px;border:1px solid var(--line);background:var(--surface);cursor:pointer;display:flex;align-items:center;justify-content:center" data-sh="border-color:var(--line-2) !important">' +
          '<span style="position:relative;width:16px;height:16px;border-radius:50%;background:var(--ink);overflow:hidden;display:block">' +
            '<span style="position:absolute;top:-3px;right:-4px;width:13px;height:13px;border-radius:50%;background:var(--surface)"></span>' +
          '</span>' +
        '</button>' +
      '</div>' +
    '</header>';
  }

  function stub(title) { return '<section style="min-height:calc(100vh - 80px);display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--ink-3);font-size:15px;gap:8px"><div style="font-size:22px;font-weight:600;color:var(--ink);letter-spacing:-0.02em">' + esc(title) + '</div><div>Vyn byggs i fas 2.</div></section>'; }
  // <<<VIEWS_START>>> (Phase-2 views — ported verbatim from prototype, verified)
function viewTranscribe(v){ return `
    ${ v.noWhisper ? `
    <section style="min-height:calc(100vh - 80px);display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:40px 0 90px">
      <div style="width:74px;height:74px;border-radius:20px;background:var(--surface);border:1px solid var(--line);box-shadow:var(--shadow-sm);display:flex;align-items:center;justify-content:center;margin-bottom:24px">
        <div style="display:flex;align-items:flex-end;gap:3px;height:28px">
          <div style="width:4px;height:10px;border-radius:2px;background:var(--line-2)"></div>
          <div style="width:4px;height:19px;border-radius:2px;background:var(--line-2)"></div>
          <div style="width:4px;height:28px;border-radius:2px;background:var(--accent)"></div>
          <div style="width:4px;height:15px;border-radius:2px;background:var(--line-2)"></div>
          <div style="width:4px;height:22px;border-radius:2px;background:var(--line-2)"></div>
        </div>
      </div>
      <h1 style="font-size:28px;font-weight:600;letter-spacing:-0.03em;margin:0 0 9px">Ladda ner en modell för att börja</h1>
      <p style="margin:0 0 28px;color:var(--ink-2);font-size:16.5px;max-width:440px;line-height:1.55">Transkriberingen körs helt lokalt med en Whisper-modell — och du har ingen installerad ännu. Hämta den rekommenderade så är du igång på någon minut.</p>
      <div style="display:flex;gap:11px;flex-wrap:wrap;justify-content:center">
        <button data-click="${on(v.getRecommended)}" style="display:inline-flex;align-items:center;gap:9px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:12px;padding:13px 22px;font-size:15.5px;font-weight:500;cursor:pointer;font-family:inherit;box-shadow:var(--shadow-sm)" data-sh="background:color-mix(in srgb, var(--btn-bg) 78%, var(--accent)) !important">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2.5v7.5"></path><path d="M4.5 6.5 8 10l3.5-3.5"></path><path d="M3 13.5h10"></path></svg>Ladda ner KB-Whisper large
        </button>
        <button data-click="${on(v.gotoModels)}" style="background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:12px;padding:13px 22px;font-size:15.5px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important">Bläddra bland modeller</button>
      </div>
    </section>
    ` : '' }

    ${ v.hasWhisper ? `
    <section style="min-height:calc(100vh - 80px);display:flex;flex-direction:column;padding:16px 0 28px">

      <div style="display:flex;align-items:center;gap:9px;flex:0 0 auto;margin-bottom:22px">
        ${ v.stepItems.map(function(s){ return `
          <div style="display:flex;align-items:center;gap:9px;flex:0 0 auto">
            <span style="${s.dotStyle}">${esc(s.icon)}</span>
            <span style="${s.labelStyle}">${esc(s.label)}</span>
          </div>
          <div style="${s.lineStyle}"></div>
        `; }).join('') }
      </div>

      ${ v.stepSource ? `
      <div style="flex:1;display:flex;flex-direction:column;min-height:0">
        <div style="text-align:center;margin-bottom:18px">
          <h1 style="font-size:30px;font-weight:600;letter-spacing:-0.03em;margin:0 0 6px">Vad vill du transkribera?</h1>
          <p style="margin:0;color:var(--ink-2);font-size:16.5px">Dra in en eller flera filer, eller välj från datorn — allt körs på din egen dator.</p>
        </div>
        <div data-click="${on(v.openPicker)}" data-dragover="${on(v.onDragOver)}" data-dragleave="${on(v.onDragLeave)}" data-drop="${on(v.onDrop)}" style="${v.dropzoneStyle}">
          <input data-ref="${on(v.fileRef)}" type="file" accept="audio/*,video/*" multiple="true" data-change="${on(v.onPickFile)}" style="display:none">
          <div style="position:relative">
            <div style="font-size:19px;font-weight:500;margin-bottom:6px;color:var(--ink)">Dra in filer — eller klicka för att välja</div>
            <div style="font-size:14.5px;color:var(--ink-2)">MP4 · MKV · MOV · MP3 · WAV · M4A — flera filer går bra</div>
          </div>
        </div>

        <div style="display:flex;align-items:center;gap:10px;margin-top:12px">
          <span style="font-size:11.5px;text-transform:uppercase;letter-spacing:0.05em;color:var(--ink-2);font-weight:600;flex:0 0 auto">Eller länk</span>
          <div style="flex:1;display:flex;align-items:center;gap:8px;min-width:0;background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:7px 7px 7px 13px;box-shadow:var(--shadow-sm)">
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="var(--ink-3)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" style="flex:0 0 auto"><path d="M6.8 9.2a3 3 0 0 0 4.3 0l1.7-1.7a3 3 0 0 0-4.3-4.3l-1 1"></path><path d="M9.2 6.8a3 3 0 0 0-4.3 0L3.2 8.5a3 3 0 0 0 4.3 4.3l1-1"></path></svg>
            <input value="${esc(v.urlInput)}" data-input="${on(v.onUrlInput)}" data-keydown="${on(v.onUrlKey)}" placeholder="Klistra in en YouTube-länk …" style="flex:1;min-width:0;border:none;outline:none;background:transparent;font-size:15px;color:var(--ink);font-family:inherit">
            <button data-click="${on(v.onAddUrl)}" style="flex:0 0 auto;display:inline-flex;align-items:center;gap:6px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:8px;padding:8px 15px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="background:color-mix(in srgb, var(--btn-bg) 78%, var(--accent)) !important">Lägg till</button>
          </div>
        </div>

        ${ v.hasFileError ? `
          <div style="display:flex;align-items:center;gap:10px;margin-top:14px;background:color-mix(in srgb,var(--bad) 7%,var(--surface));border:1px solid color-mix(in srgb,var(--bad) 30%,transparent);border-radius:12px;padding:12px 15px">
            <span style="width:20px;height:20px;border-radius:50%;flex:0 0 auto;background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700">!</span>
            <span style="font-size:14.5px;color:var(--ink)">${esc(v.fileError)}</span>
          </div>
        ` : '' }

        <div style="display:flex;align-items:center;gap:9px;margin-top:18px;flex-wrap:wrap">
          <span style="font-size:11.5px;text-transform:uppercase;letter-spacing:0.05em;color:var(--ink-2);font-weight:600">Eller prova med</span>
          <button data-click="${on(v.addSampleNormal)}" style="display:inline-flex;align-items:center;gap:7px;font-size:13.5px;font-weight:500;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:9px;padding:7px 12px;cursor:pointer;font-family:inherit;font-variant-numeric:tabular-nums" data-sh="border-color:var(--ink-3) !important">
            <span style="width:7px;height:7px;border-radius:2px;background:var(--ok);flex:0 0 auto"></span>mötesinspelning.mp3
          </button>
          <button data-click="${on(v.addSampleCorrupt)}" style="display:inline-flex;align-items:center;gap:7px;font-size:13.5px;font-weight:500;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:9px;padding:7px 12px;cursor:pointer;font-family:inherit;font-variant-numeric:tabular-nums" data-sh="border-color:var(--ink-3) !important">
            <span style="width:7px;height:7px;border-radius:2px;background:var(--bad);flex:0 0 auto"></span>skadad_inspelning.m4a
          </button>
        </div>
      </div>
      ` : '' }

      ${ v.stepConfig ? `
      <div data-pane="config" style="flex:1;display:flex;flex-direction:column;min-height:0">
        <div style="margin-bottom:22px">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px">
            <div style="display:flex;align-items:baseline;gap:9px">
              <span style="font-size:12px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink-2)">Filer i kö</span>
              <span style="font-size:13px;color:var(--ink-3);font-variant-numeric:tabular-nums">${esc(v.queueCount)}</span>
            </div>
            <button data-click="${on(v.goSource)}" style="display:inline-flex;align-items:center;gap:6px;background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:7px 13px;font-size:13.5px;font-weight:500;cursor:pointer;font-family:inherit;flex:0 0 auto" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important">
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M8 3v10M3 8h10"></path></svg>Lägg till fler
            </button>
          </div>
          <div style="display:flex;flex-direction:column;gap:8px">
            ${ v.queueItems.map(function(q){ return `
              <div data-key="${esc(q.id)}" style="${q.rowStyle}">
                <span style="font-size:11px;font-weight:600;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);border-radius:6px;padding:3px 7px;flex:0 0 auto;font-variant-numeric:tabular-nums">${esc(q.ext)}</span>
                <span style="flex:1;min-width:0;font-size:15.5px;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-variant-numeric:tabular-nums">${esc(q.name)}</span>
                <button data-click="${on(q.onRemove)}" aria-label="Ta bort från kön" style="width:30px;height:30px;flex:0 0 auto;border:1px solid var(--line);background:var(--surface);border-radius:8px;cursor:pointer;color:var(--ink-3);display:flex;align-items:center;justify-content:center" data-sh="border-color:var(--bad) !important;color:var(--bad) !important">
                  <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 3l8 8M11 3l-8 8"></path></svg>
                </button>
              </div>
            `; }).join('') }
          </div>
        </div>

        <h2 style="font-size:22px;font-weight:600;letter-spacing:-0.02em;margin:0 0 14px">Inställningar</h2>

        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px;box-shadow:var(--shadow-sm)">
          <div style="display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:11px;flex:0 0 auto">
            ${ v.langOptions.map(function(l){ return `
              <button data-click="${on(l.onPick)}" style="${l.style}" data-sh="background:var(--surface) !important;color:var(--ink) !important;box-shadow:var(--shadow-sm) !important">${esc(l.label)}</button>
            `; }).join('') }
          </div>

          <div style="display:flex;align-items:center;gap:10px;flex:1 1 210px;min-width:200px;background:var(--sunken);border:1px solid var(--line);border-radius:11px;padding:9px 13px">
            <span style="width:8px;height:8px;border-radius:50%;flex:0 0 auto;background:${v.curModelDot}"></span>
            <span style="flex:1;min-width:0">
              <span style="display:block;font-size:14.5px;font-weight:500;color:var(--ink)">${esc(v.curModelName)}</span>
              <span style="display:block;font-size:12px;color:var(--ink-2);font-variant-numeric:tabular-nums">${esc(v.curModelMeta)}</span>
            </span>
          </div>

        <div style="flex:1 1 auto"></div>

        <div style="display:flex;gap:6px;flex:0 0 auto">
          ${ v.formatChips.map(function(f){ return `
            <button data-click="${on(f.onToggle)}" style="${f.style}" data-sh="border-color:var(--line-2) !important;box-shadow:var(--shadow-sm) !important">${esc(f.label)}</button>
          `; }).join('') }
        </div>
        </div>

        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:12px;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px;box-shadow:var(--shadow-sm)">
          <span style="font-size:14px;color:var(--ink-2);font-weight:500">Resultatspråk</span>
          <div style="display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:11px">
            ${ v.targetLangOptions.map(function(o){ return `<button data-click="${on(o.onPick)}" style="${o.style}" data-sh="background:var(--surface) !important;color:var(--ink) !important;box-shadow:var(--shadow-sm) !important">${esc(o.label)}</button>`; }).join('') }
          </div>
          ${ v.translateNote ? `<span style="font-size:13px;color:var(--accent)">${esc(v.translateNote)}</span>` : '' }
        </div>

        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:12px;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px 14px;box-shadow:var(--shadow-sm)">
          <div data-click="${on(v.onToggleAudioCorrect)}" style="${v.acSwitchTrack}"><span style="${v.acSwitchKnob}"></span></div>
          <div style="flex:1;min-width:0">
            <div style="font-size:14.5px;font-weight:500;color:var(--ink)">Rätta mot ljudet <span style="font-size:12px;color:var(--ink-3)">· Gemma 3n (experimentell)</span></div>
            <div style="font-size:12.5px;color:var(--ink-2)">Ett andra pass som rättar transkriptet mot vad som faktiskt sägs.</div>
          </div>
          ${ v.audioModelInstalled ? '' : `
            <button data-click="${on(v.onDownloadAudioModel)}" style="flex:0 0 auto;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:7px 13px;font-size:13.5px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--ink) !important">${ v.audioModelDownloading ? 'Laddar ner …' : 'Ladda ner modell' }</button>
          ` }
        </div>

        ${ v.showSubtitleMode ? `
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:12px;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px;box-shadow:var(--shadow-sm)">
          <span style="font-size:14px;color:var(--ink-2);font-weight:500">Undertext i video</span>
          <div style="display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:11px">
            ${ v.subtitleOptions.map(function(o){ return `<button data-click="${on(o.onPick)}" style="${o.style}" data-sh="background:var(--surface) !important;color:var(--ink) !important;box-shadow:var(--shadow-sm) !important">${esc(o.label)}</button>`; }).join('') }
          </div>
          ${ v.showEmbed ? `
          <div style="display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:11px">
            ${ v.embedOptions.map(function(o){ return `<button data-click="${on(o.onPick)}" style="${o.style}" data-sh="background:var(--surface) !important;color:var(--ink) !important;box-shadow:var(--shadow-sm) !important">${esc(o.label)}</button>`; }).join('') }
          </div>
          ` : '' }
        </div>
        ` : '' }

        <div style="flex:0 0 auto;height:46px"></div>

        <button data-click="${on(v.onStart)}" class="korbtn" style="position:relative;overflow:visible;display:flex;align-items:center;justify-content:center;gap:13px;width:100%;height:60px;border:1.5px solid var(--ink);border-radius:14px;background:var(--surface);cursor:pointer;font-family:inherit;padding:0" data-sh="box-shadow:var(--shadow) !important;transform:translateY(-1px) !important">
          ${ v.isRunning ? `
            <span style="width:16px;height:16px;border-radius:50%;border:2px solid color-mix(in srgb,var(--ink) 28%,transparent);border-top-color:var(--ink);animation:spin .7s linear infinite;display:inline-block"></span>
            <span style="font-size:16.5px;font-weight:600;letter-spacing:-0.01em;color:var(--ink)">${esc(v.startBtnLabel)}</span>
          ` : '' }
          ${ v.notRunning ? `
            <div style="position:relative;width:30px;height:44px;flex:0 0 auto">
              <div data-bubble data-anim style="position:absolute;left:50%;bottom:calc(100% + 12px);background:var(--surface);border:1.5px solid var(--line-2);border-radius:11px;padding:7px 12px;white-space:nowrap;font-size:14px;font-weight:600;color:var(--accent);box-shadow:var(--shadow);z-index:5;animation:bubbleLife 4s cubic-bezier(.45,.05,.3,1) infinite">Nu kör vi!<span style="position:absolute;left:50%;bottom:-6px;width:10px;height:10px;margin-left:-5px;background:var(--surface);border-right:1.5px solid var(--line-2);border-bottom:1.5px solid var(--line-2);transform:rotate(45deg)"></span></div>
              <div data-anim style="position:absolute;inset:0;animation:choreoBody 4s cubic-bezier(.45,.05,.3,1) infinite">
                <div style="position:absolute;left:9px;top:0;width:12px;height:12px;border-radius:50%;background:var(--ink)"></div>
                <div style="position:absolute;left:13.5px;top:12px;width:3px;height:17px;border-radius:2px;background:var(--ink)"></div>
                <div data-anim style="position:absolute;left:13.5px;top:14px;width:3px;height:13px;border-radius:2px;background:var(--ink);transform-origin:50% 0;animation:choreoArmR 4s cubic-bezier(.45,.05,.3,1) infinite"></div>
                <div data-anim style="position:absolute;left:13.5px;top:14px;width:3px;height:13px;border-radius:2px;background:var(--ink);transform-origin:50% 0;animation:choreoArmL 4s cubic-bezier(.45,.05,.3,1) infinite"></div>
                <div data-anim style="position:absolute;left:13.5px;top:28px;width:3px;height:15px;border-radius:2px;background:var(--ink);transform-origin:50% 0;animation:choreoLegR 4s cubic-bezier(.45,.05,.3,1) infinite"></div>
                <div data-anim style="position:absolute;left:13.5px;top:28px;width:3px;height:15px;border-radius:2px;background:var(--ink);transform-origin:50% 0;animation:choreoLegL 4s cubic-bezier(.45,.05,.3,1) infinite"></div>
              </div>
            </div>
            <span data-anim style="font-size:16.5px;font-weight:600;letter-spacing:-0.01em;color:var(--ink);display:inline-block;animation:startaShake 4s linear infinite">${esc(v.startBtnLabel)}</span>
          ` : '' }
        </button>
      </div>
      ` : '' }

      ${ v.stepProcess ? `
      <div data-pane="process" style="flex:1;display:flex;flex-direction:column;min-height:0">
        <div data-ref="${on(v.procScrollRef)}" data-procscroll="1" style="display:flex;flex-direction:column">
          <div style="height:2px"></div>

      ${ v.multiQueue ? `
      <div style="margin-top:24px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:9px">
          <span style="font-size:12px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink-2)">Kö</span>
          <span style="font-size:13px;color:var(--ink-2);font-variant-numeric:tabular-nums">${esc(v.queueSummary)}</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px">
          ${ v.queueItems.map(function(q){ return `
            <div data-key="${esc(q.id)}" style="${q.rowStyle}">
              <span style="${q.dotStyle}"></span>
              <span style="font-size:11px;font-weight:600;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);border-radius:6px;padding:3px 7px;flex:0 0 auto;font-variant-numeric:tabular-nums">${esc(q.ext)}</span>
              <span style="flex:1;min-width:0;font-size:14.5px;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-variant-numeric:tabular-nums">${esc(q.name)}</span>
              <span style="${q.statusStyle}">${esc(q.statusLabel)}</span>
            </div>
          `; }).join('') }
        </div>
      </div>
      ` : '' }

      ${ v.showStatus ? `
      <div style="margin-top:24px;background:var(--surface);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);overflow:hidden">
        <div style="padding:22px 24px 20px">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px">
            <div style="display:flex;align-items:center;gap:10px;min-width:0">
              <span style="${v.statusBadgeStyle}">${esc(v.statusBadge)}</span>
              <span style="font-size:15.5px;color:var(--ink-2);font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.statusFile)}</span>
            </div>
            <div style="display:flex;align-items:center;gap:14px;font-size:14.5px;color:var(--ink-2);font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums;flex:0 0 auto">
              <span>${esc(v.elapsedLabel)}</span>
              <span style="font-weight:500;color:var(--ink);font-size:15.5px">${esc(v.progressLabel)}</span>
              ${ v.isRunning ? `
                <button data-click="${on(v.onCancelRun)}" style="background:transparent;border:1px solid var(--line);color:var(--ink-2);border-radius:9px;padding:6px 13px;font-size:13.5px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--bad) !important;color:var(--bad) !important">Avbryt</button>
              ` : '' }
            </div>
          </div>

          ${ v.isError ? `
          <div style="display:flex;gap:13px;align-items:flex-start;background:color-mix(in srgb,var(--bad) 7%,var(--surface));border:1px solid color-mix(in srgb,var(--bad) 30%,transparent);border-radius:14px;padding:16px 18px">
            <span style="width:30px;height:30px;border-radius:50%;flex:0 0 auto;background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad);display:flex;align-items:center;justify-content:center;font-size:17px;font-weight:700;margin-top:1px">!</span>
            <div style="flex:1;min-width:0">
              <div style="font-size:16.5px;font-weight:600;color:var(--ink)">${esc(v.runErrorTitle)}</div>
              <div style="font-size:14.5px;color:var(--ink-2);margin-top:5px;line-height:1.55">${esc(v.runErrorDetail)}</div>
              <div style="display:flex;gap:9px;margin-top:15px;flex-wrap:wrap">
                <button data-click="${on(v.onRetryRun)}" style="display:inline-flex;align-items:center;gap:7px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:10px;padding:9px 16px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="background:color-mix(in srgb, var(--btn-bg) 78%, var(--accent)) !important"><span style="font-size:15px;line-height:1">↻</span>Försök igen</button>
                <button data-click="${on(v.goSource)}" style="background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:9px 16px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important">Byt fil</button>
                <button data-click="${on(v.openLog)}" style="background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:9px 16px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important">Visa logg</button>
              </div>
            </div>
          </div>
          ` : '' }

          ${ v.isCancelled ? `
          <div style="display:flex;gap:13px;align-items:flex-start;background:var(--sunken);border:1px solid var(--line);border-radius:14px;padding:16px 18px">
            <span style="width:30px;height:30px;border-radius:50%;flex:0 0 auto;background:var(--surface);border:1px solid var(--line-2);color:var(--ink-3);display:flex;align-items:center;justify-content:center;margin-top:1px"><span style="width:11px;height:11px;border-radius:2px;background:var(--ink-3)"></span></span>
            <div style="flex:1;min-width:0">
              <div style="font-size:16.5px;font-weight:600;color:var(--ink)">Transkriberingen avbröts</div>
              <div style="font-size:14.5px;color:var(--ink-2);margin-top:5px;line-height:1.55">Du stoppade körningen — inget sparades. Återuppta där du var, eller byt fil.</div>
              <div style="display:flex;gap:9px;margin-top:15px;flex-wrap:wrap">
                <button data-click="${on(v.onResumeRun)}" style="display:inline-flex;align-items:center;gap:7px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:10px;padding:9px 16px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="background:color-mix(in srgb, var(--btn-bg) 78%, var(--accent)) !important">Återuppta</button>
                <button data-click="${on(v.goSource)}" style="background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:9px 16px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important">Byt fil</button>
              </div>
            </div>
          </div>
          ` : '' }

          ${ v.notErrorState ? `
          <div style="display:flex;gap:8px;margin-bottom:16px">
            ${ v.steps.map(function(s){ return `
              <div style="flex:1;display:flex;flex-direction:column;gap:8px">
                <div style="${s.barStyle}"></div>
                <div style="display:flex;align-items:center;gap:6px">
                  <span style="${s.dotStyle}">${esc(s.icon)}</span>
                  <span style="${s.labelStyle}">${esc(s.label)}</span>
                </div>
              </div>
            `; }).join('') }
          </div>
          ` : '' }
        </div>

        <div data-click="${on(v.openLog)}" style="border-top:1px solid var(--line);background:var(--surface);cursor:pointer;border-radius:0 0 18px 18px;transition:background .12s" data-sh="background:var(--sunken) !important">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:11px 24px;font-size:13.5px;color:var(--ink-2)">
            <span style="display:flex;align-items:center;gap:8px">
              <span style="width:6px;height:6px;border-radius:50%;background:var(--ink-3)"></span>
              <span style="font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums;letter-spacing:0.02em;text-transform:uppercase;font-size:12.5px">Logg</span>
            </span>
            <span style="display:inline-flex;align-items:center;gap:7px;color:var(--ink);font-size:13px;font-weight:500;font-family:inherit">
              <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M2 5V2h3"></path><path d="M9 2h3v3"></path><path d="M12 9v3h-3"></path><path d="M5 12H2V9"></path></svg>Helskärm
            </span>
          </div>
          <div style="position:relative;padding:6px 24px 14px;max-height:96px;overflow:hidden">
            ${ v.logRows.map(function(r){ return `
              <div style="display:flex;gap:14px">
                <span style="font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums;font-size:12.5px;color:var(--ink-3);width:42px;flex:0 0 auto;text-align:right;padding-top:1px">${esc(r.time)}</span>
                <div style="position:relative;display:flex;flex-direction:column;align-items:center;flex:0 0 auto">
                  <span style="${r.dotStyle}">${esc(r.icon)}</span>
                  <span style="${r.lineStyle}"></span>
                </div>
                <span style="font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums;font-size:13px;color:var(--ink);padding-bottom:13px;line-height:1.45;min-width:0">${esc(r.msg)}</span>
              </div>
            `; }).join('') }
            ${ v.logClipped ? `
              <div style="position:absolute;left:0;right:0;bottom:0;height:40px;background:linear-gradient(180deg,transparent,var(--surface));pointer-events:none;border-radius:0 0 18px 18px"></div>
            ` : '' }
          </div>
        </div>
      </div>
      ` : '' }

      ${ v.showResults ? `
      <div data-sec="results" style="margin-top:24px;scroll-margin-top:8px">
        <div data-reveal style="display:flex;align-items:center;gap:9px;margin-bottom:14px">
          <span style="width:18px;height:18px;border-radius:50%;background:var(--ok);color:#fff;display:flex;align-items:center;justify-content:center;font-size:12.5px;flex:0 0 auto">✓</span>
          <h2 style="font-size:20px;font-weight:600;letter-spacing:-0.02em;margin:0">Klar</h2>
          <span style="color:var(--ink-2);font-size:15.5px">· ${esc(v.resultCount)} filer · ${esc(v.resultDuration)}</span>
        </div>

        <div style="display:grid;gap:10px;margin-bottom:18px">
          ${ v.resultFiles.map(function(r){ return `
            <div data-key="${esc(r.name)}" data-reveal style="display:flex;align-items:center;gap:14px;background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:14px 16px;box-shadow:var(--shadow-sm)">
              <span style="font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums;font-size:12.5px;font-weight:500;color:var(--accent);background:var(--accent-weak);padding:5px 9px;border-radius:7px;letter-spacing:0.03em">${esc(r.type)}</span>
              <span style="flex:1;min-width:0;font-size:16px;font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.name)}</span>
              <span style="font-size:14px;color:var(--ink-2);font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums">${esc(r.size)}</span>
              <button data-click="${on(r.onDownload)}" style="display:inline-flex;align-items:center;gap:8px;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:8px 14px 8px 12px;font-size:14.5px;font-weight:500;cursor:pointer;font-family:inherit;transition:background .14s,border-color .14s,color .14s" data-sh="border-color:var(--ink) !important;background:var(--ink) !important;color:var(--btn-fg) !important">
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2.5v7.5"></path><path d="M4.5 6.5 8 10l3.5-3.5"></path><path d="M3 13.5h10"></path></svg>Ladda ner
              </button>
            </div>
          `; }).join('') }
        </div>

        <div data-reveal data-click="${on(v.openTranscript)}" style="background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px 20px;box-shadow:var(--shadow-sm);cursor:pointer;transition:border-color .12s,box-shadow .12s" data-sh="border-color:var(--line-2) !important;box-shadow:var(--shadow) !important">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
            <div style="font-size:12.5px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink-2);font-family:'Geist',system-ui,sans-serif">Förhandsvisning</div>
            <span style="display:inline-flex;align-items:center;gap:7px;color:var(--ink);font-size:13px;font-weight:500;font-family:inherit">
              <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M2 5V2h3"></path><path d="M9 2h3v3"></path><path d="M12 9v3h-3"></path><path d="M5 12H2V9"></path></svg>Helskärm
            </span>
          </div>
          ${ v.transcript.map(function(t, idx){ return `
            <div data-key="${esc(idx)}" style="display:flex;gap:14px;padding:5px 0">
              <span style="font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums;font-size:13.5px;color:var(--ink-3);flex:0 0 auto;width:46px;padding-top:2px">${esc(t.time)}</span>
              <span style="font-size:16px;color:var(--ink);line-height:1.5">${esc(t.text)}</span>
            </div>
          `; }).join('') }
        </div>
      </div>
      ` : '' }

      ${ v.showPP ? `
      <div data-sec="pp" data-reveal style="margin-top:28px;background:var(--surface);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow)">
        <div style="padding:22px 24px 20px">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
            <span style="font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums;font-size:12px;font-weight:500;color:var(--accent);background:var(--accent-weak);padding:3px 9px;border-radius:6px">LLM</span>
            <h2 style="font-size:19px;font-weight:600;letter-spacing:-0.02em;margin:0">Efterbearbeta transkriptet</h2>
          </div>
          <p style="margin:0 0 18px;color:var(--ink-2);font-size:15px">Valfritt — förfina resultatet lokalt med en språkmodell.</p>
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px">
            ${ v.ppOps.map(function(o){ return `
              ${ o.selected ? `
                <button data-key="${esc(o.key)}" data-click="${on(o.onPick)}" style="display:flex;flex-direction:column;gap:3px;align-items:flex-start;text-align:left;padding:13px 14px;border-radius:12px;cursor:pointer;font-family:inherit;color:var(--ink);width:100%;border:1.5px solid var(--ink);background:var(--sunken);transition:border-color .12s,background .12s,box-shadow .12s" data-sh="box-shadow:var(--shadow-sm) !important">
                  <span style="font-size:14.5px;font-weight:500">${esc(o.label)}</span>
                  <span style="font-size:12.5px;color:var(--ink-2);line-height:1.3">${esc(o.sub)}</span>
                </button>
              ` : '' }
              ${ o.unselected ? `
                <button data-key="${esc(o.key)}" data-click="${on(o.onPick)}" style="display:flex;flex-direction:column;gap:3px;align-items:flex-start;text-align:left;padding:13px 14px;border-radius:12px;cursor:pointer;font-family:inherit;color:var(--ink);width:100%;border:1.5px solid var(--line);background:var(--surface);transition:border-color .12s,background .12s,box-shadow .12s" data-sh="border-color:var(--ink-3) !important;background:var(--sunken) !important;box-shadow:var(--shadow-sm) !important">
                  <span style="font-size:14.5px;font-weight:500">${esc(o.label)}</span>
                  <span style="font-size:12.5px;color:var(--ink-2);line-height:1.3">${esc(o.sub)}</span>
                </button>
              ` : '' }
            `; }).join('') }
          </div>
          <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap">
            <div style="position:relative;flex:1;min-width:200px">
              <div style="font-size:14px;font-weight:500;color:var(--ink-2);margin-bottom:8px">LLM-modell</div>
              <button data-click="${on(v.togglePPDD)}" style="width:100%;max-width:320px;display:flex;align-items:center;gap:10px;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 14px;cursor:pointer;text-align:left" data-sh="border-color:var(--line-2) !important">
                <span style="width:7px;height:7px;border-radius:50%;flex:0 0 auto;background:var(--ok)"></span>
                <span style="flex:1;font-size:15.5px;font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums;color:var(--ink)">${esc(v.ppModel)}</span>
                <span style="width:6px;height:6px;border-right:1.6px solid var(--ink-3);border-bottom:1.6px solid var(--ink-3);transform:rotate(45deg);margin:-3px 2px 0 0"></span>
              </button>
              ${ v.ppDDOpen ? `
              <div style="position:absolute;bottom:calc(100% + 6px);left:0;width:100%;max-width:320px;z-index:30;background:var(--surface);border:1px solid var(--line);border-radius:13px;box-shadow:var(--shadow);padding:6px;animation:fadeup .14s ease">
                ${ v.ppModelOptions.map(function(m){ return `
                  <button data-key="${esc(m.name)}" data-click="${on(m.onPick)}" style="${m.style}" data-sh="background:var(--sunken) !important">
                    <span style="flex:1;font-size:15px;font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums;color:var(--ink)">${esc(m.name)}</span>
                    <span style="font-size:13px;color:var(--ink-2)">${esc(m.size)}</span>
                  </button>
                `; }).join('') }
              </div>
              ` : '' }
            </div>
            ${ v.ppShowRun ? `
              <button data-click="${on(v.onRunPP)}" style="${v.ppRunBtnStyle}" data-sh="background:color-mix(in srgb, var(--btn-bg) 72%, var(--accent)) !important">
                ${ v.ppRunning ? `
                  <span style="display:flex;align-items:center;gap:11px">
                    <span style="${v.ppRingStyle}"><span style="position:absolute;inset:3px;border-radius:50%;background:var(--btn-bg)"></span></span>
                    <span style="font-variant-numeric:tabular-nums">Bearbetar ${esc(v.ppPct)}%</span>
                  </span>
                ` : '' }
                ${ v.ppRunIdle ? `
                  <span>${esc(v.ppRunLabel)}</span>
                ` : '' }
              </button>
            ` : '' }
          </div>
        </div>

        ${ v.ppShowText ? `
        <div data-sec="ppout" style="border-top:1px solid var(--line);background:var(--sunken);padding:20px 24px;border-radius:0 0 18px 18px">
          ${ v.ppRunning ? `
            <div style="display:flex;align-items:center;gap:10px;color:var(--ink-2);font-size:15px">
              <span style="width:15px;height:15px;border-radius:50%;border:2px solid var(--line-2);border-top-color:var(--accent);animation:spin .7s linear infinite;display:inline-block"></span>Kör ${esc(v.ppOpLabel)} …
            </div>
          ` : '' }
          ${ v.ppTextDone ? `
            <div style="font-size:12.5px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink-2);margin-bottom:10px;font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums">${esc(v.ppOutTitle)}</div>
            <div style="font-size:16px;line-height:1.65;color:var(--ink);white-space:pre-wrap">${esc(v.ppOut)}</div>
          ` : '' }
          ${ v.ppCleanDone ? `
            <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px;flex-wrap:wrap">
              <div style="display:flex;align-items:center;gap:9px">
                <span style="width:18px;height:18px;border-radius:50%;background:var(--ok);color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;flex:0 0 auto">✓</span>
                <span style="font-size:12.5px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink-2);font-family:'Geist',system-ui,sans-serif">Korrekturläst transkript</span>
              </div>
              <span style="font-size:13px;color:var(--ink-2)">Samma transkript — stavfel och småfel rättade</span>
            </div>
            <div style="background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:16px 18px;margin-bottom:14px;max-height:320px;overflow-y:auto" data-hidescroll="1">
              ${ v.ppCleanLines.map(function(c, idx){ return `
                <div data-key="${esc(idx)}" style="display:flex;gap:14px;padding:5px 0">
                  <span style="font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums;font-size:13px;color:var(--ink-3);flex:0 0 auto;width:44px;padding-top:2px">${esc(c.time)}</span>
                  <span style="font-size:15.5px;line-height:1.5;color:var(--ink)">${esc(c.text)}</span>
                </div>
              `; }).join('') }
            </div>
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              <span style="font-size:13px;color:var(--ink-2);margin-right:4px">Ladda ner korrigerad:</span>
              ${ v.ppCleanFiles.map(function(f){ return `
                <button data-key="${esc(f.type)}" data-click="${on(f.onDownload)}" style="display:inline-flex;align-items:center;gap:7px;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:8px 14px 8px 12px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit;transition:background .14s,border-color .14s,color .14s" data-sh="border-color:var(--ink) !important;background:var(--ink) !important;color:var(--btn-fg) !important">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2.5v7.5"></path><path d="M4.5 6.5 8 10l3.5-3.5"></path><path d="M3 13.5h10"></path></svg>${esc(f.type)}
                </button>
              `; }).join('') }
            </div>
          ` : '' }
        </div>
        ` : '' }

        ${ v.ppShowChat ? `
        <div data-sec="chat" style="border-top:1px solid var(--line);background:var(--sunken);border-radius:0 0 18px 18px;padding:18px 24px;display:flex;align-items:center;gap:16px;flex-wrap:wrap">
          <div style="flex:1;min-width:200px">
            <div style="font-size:15px;font-weight:600;color:var(--ink)">Chatta med transkriptet</div>
            <div style="font-size:13.5px;color:var(--ink-2);margin-top:2px">Öppnas i ett fönster — gränssnittet anpassas efter modellens förmågor.</div>
          </div>
          <button data-click="${on(v.openChatModal)}" style="${v.chatOpenBtnStyle}" data-sh="background:color-mix(in srgb, var(--btn-bg) 72%, var(--accent)) !important">
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 3.5h11v8h-7l-3 2.5z"></path></svg>Öppna chatt
          </button>
        </div>
        ` : '' }
      </div>
      ` : '' }
        </div>
        <button data-click="${on(v.restart)}" style="margin-top:16px;flex:0 0 auto;align-self:center;display:inline-flex;align-items:center;justify-content:center;gap:8px;background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:11px;padding:11px 22px;font-size:15px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important">
          <span style="font-size:16px;line-height:1">↺</span>Ny transkribering — börja om
        </button>
      </div>
      ` : '' }
    </section>
    ` : '' }
`; }

function viewModels(v){
  function dlbtn(r){
    var p = r.phase || 'idle';
    var pct = Math.round(r.pct || 0);
    var detail = r.detail || '';
    var progressing = p === 'downloading' || p === 'installing';
    var base = 'position:relative;overflow:hidden;box-sizing:border-box;display:inline-flex;align-items:center;justify-content:center;gap:6px;width:154px;height:40px;border-radius:9px;padding:7px 14px;font-size:14.5px;font-weight:500;font-family:inherit;white-space:nowrap;transition:border-color .15s,background .15s;';
    var btnStyle, btnHover = '';
    if (progressing) {
      btnStyle = base + 'background:var(--surface);border:1px solid var(--accent);color:var(--ink);cursor:default;padding-right:26px';
    } else if (p === 'installed') {
      btnStyle = base + 'background:transparent;border:1px solid transparent;color:var(--ok);cursor:default';
    } else if (p === 'incompatible') {
      btnStyle = base + 'background:transparent;border:1px solid transparent;color:var(--ink-3);cursor:default';
    } else if (p === 'failed') {
      btnStyle = base + 'background:transparent;border:1px solid var(--bad);color:var(--bad);cursor:pointer';
      btnHover = 'background:color-mix(in srgb,var(--bad) 8%,transparent) !important';
    } else {
      btnStyle = base + 'background:transparent;border:1px solid var(--line-2);color:var(--ink);cursor:pointer';
      btnHover = 'background:var(--sunken) !important;border-color:var(--ink-3) !important;box-shadow:var(--shadow-sm) !important';
    }
    var fillStyle = p === 'installing'
      ? 'position:absolute;left:0;top:0;bottom:0;z-index:0;width:' + pct + '%;background-color:var(--accent);background-image:repeating-linear-gradient(135deg, rgba(255,255,255,0.3) 0, rgba(255,255,255,0.3) 4px, transparent 4px, transparent 8px);background-size:16px 16px;animation:dlstripe .6s linear infinite;transition:width .22s ease'
      : 'position:absolute;left:0;top:0;bottom:0;z-index:0;width:' + pct + '%;background:var(--accent);transition:width .22s ease';
    var progLabel = p === 'installing' ? 'Installerar' : 'Laddar ner';
    if (progressing) {
      return `<div style="${btnStyle}">
    <div style="${fillStyle}"></div>
    <span style="position:relative;z-index:1;display:flex;flex-direction:column;align-items:center;line-height:1.1;padding-right:16px;max-width:100%;overflow:hidden">
      <span style="font-size:13.5px;font-weight:600;white-space:nowrap">${esc(progLabel)} ${esc(pct)}%</span>
      <span style="font-size:10.5px;font-weight:500;color:var(--ink-2);font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px">${esc(detail)}</span>
    </span>
    <button data-click="${on(r.onCancel)}" aria-label="Avbryt nedladdning" style="position:absolute;right:5px;top:50%;transform:translateY(-50%);z-index:2;width:22px;height:22px;border:none;background:var(--surface);border-radius:6px;cursor:pointer;color:var(--ink-2);display:flex;align-items:center;justify-content:center" data-sh="color:var(--bad) !important;background:var(--sunken) !important">
      <svg width="10" height="10" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 3l8 8M11 3l-8 8"></path></svg>
    </button>
  </div>`;
    }
    return `<button data-click="${on(r.onAction)}" style="${btnStyle}" data-sh="${btnHover}">
    ${ p === 'idle' ? `<span style="position:relative;z-index:1;display:inline-flex;align-items:center;gap:6px">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2.5v7.5"></path><path d="M4.5 6.5 8 10l3.5-3.5"></path><path d="M3 13.5h10"></path></svg>Ladda ner
      </span>` : '' }
    ${ p === 'failed' ? `<span style="position:relative;z-index:1;display:inline-flex;align-items:center;gap:6px"><span style="font-size:14px;line-height:1">↻</span>Försök igen</span>` : '' }
    ${ p === 'installed' ? `<span style="position:relative;z-index:1;display:inline-flex;align-items:center;gap:5px;color:var(--ok)">✓ Installerad</span>` : '' }
    ${ p === 'incompatible' ? `<span style="position:relative;z-index:1;color:var(--ink-3)">Ej kompatibel</span>` : '' }
  </button>`;
  }
  function modelRow(x, last){
    return `<div data-key="${esc(x.name)}" style="${x.rowStyle}">
              <span style="width:24px;height:24px;border-radius:50%;flex:0 0 auto;margin-top:1px;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);font-variant-numeric:tabular-nums">${esc(x.rank)}</span>
              <span style="width:9px;height:9px;border-radius:50%;flex:0 0 auto;margin-top:7px;background:${x.dot}"></span>
              <div style="flex:1;min-width:0">
                <div style="display:flex;align-items:center;gap:9px;flex-wrap:wrap">
                  <span style="font-size:16px;font-weight:500;color:var(--ink);font-variant-numeric:tabular-nums">${esc(x.name)}</span>
                  ${ x.recommended ? `<span style="font-size:12px;font-weight:500;color:var(--accent);background:var(--accent-weak);padding:2px 7px;border-radius:5px">Rekommenderad</span>` : '' }
                  <span style="${x.verdictStyle}">${esc(x.verdict)}</span>
                </div>
                <div style="font-size:14px;color:var(--ink-2);margin-top:4px">${esc(x.useFor)}</div>
                <div style="display:flex;gap:7px;margin-top:9px;flex-wrap:wrap">
                  ${ x.chips.map(function(c){ return `<span style="${c.style}" data-enter="${on(c.onEnter)}" data-leave="${on(c.onLeave)}">${esc(c.label)}</span>`; }).join('') }
                </div>
              </div>
              <div style="display:flex;flex-direction:column;align-items:flex-end;gap:9px;flex:0 0 auto">
                <span style="font-size:13px;color:var(--ink-2);font-variant-numeric:tabular-nums">${esc(x.size)}</span>
                <div style="display:flex;align-items:center;gap:7px">
                  ${ x.removable ? `<button data-click="${on(x.onRemove)}" aria-label="Ta bort modell" style="width:38px;height:38px;flex:0 0 auto;border:1px solid var(--line);background:var(--surface);border-radius:9px;cursor:pointer;color:var(--ink-3);display:flex;align-items:center;justify-content:center" data-sh="border-color:var(--bad) !important;color:var(--bad) !important">
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.5 8.5h6l.5-8.5"></path></svg>
                    </button>` : '' }
                  ${ x.notRemovable ? `<span style="width:38px;flex:0 0 auto"></span>` : '' }
                  ${ dlbtn(x) }
                </div>
              </div>
            </div>`;
  }
  return `<section style="padding:44px 0 96px">
      <div style="text-align:center;max-width:640px;margin:0 auto 24px">
        <h1 style="font-size:34px;font-weight:600;letter-spacing:-0.03em;margin:0 0 6px">Modeller</h1>
        <p style="margin:0;color:var(--ink-2);font-size:17px">Hantera lokala modeller. Märkningen visar hur väl varje modell passar din hårdvara.</p>
      </div>

      <!-- Hårdvara -->
      <div style="background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:20px 22px;margin-bottom:32px;box-shadow:var(--shadow-sm)">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px">
          <span style="display:inline-flex;align-items:center;gap:8px;background:color-mix(in srgb,var(--ok) 13%,transparent);color:var(--ink);border-radius:999px;padding:5px 13px 5px 10px;font-size:13.5px;font-weight:500">
            <span style="width:7px;height:7px;border-radius:50%;background:var(--ok)"></span>Hårdvara identifierad
          </span>
          <span style="font-size:13px;color:var(--ink);font-variant-numeric:tabular-nums">${esc(v.hwReady)}</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:16px;margin-bottom:18px">
          ${ v.hwTiles.map(function(t){ return `<div>
              <div style="display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:7px">
                <span style="display:inline-flex;align-items:center;gap:6px">
                  <span style="font-size:14px;font-weight:500;color:var(--ink)">${esc(t.label)}</span>
                  <span style="font-size:12px;color:var(--ink)">· ${esc(t.note)}</span>
                  <span data-enter="${on(t.onEnter)}" data-leave="${on(t.onLeave)}" style="${t.badgeStyle}">?</span>
                </span>
                <span style="font-size:13.5px;color:var(--ink-2);font-variant-numeric:tabular-nums;flex:0 0 auto">
                  <strong style="color:var(--ink);font-size:15.5px;font-weight:600">${esc(t.free)}</strong> / ${esc(t.total)}
                </span>
              </div>
              <div style="height:8px;border-radius:99px;background:var(--track);overflow:hidden">
                <div style="${t.barStyle}"></div>
              </div>
            </div>`; }).join('') }
        </div>
        <div style="border-top:1px solid var(--line);padding-top:14px;margin-bottom:14px;display:flex;align-items:center;gap:14px;flex-wrap:wrap">
          <div style="display:flex;align-items:center;gap:9px;flex:0 0 auto">
            <span style="width:30px;height:30px;border-radius:8px;background:var(--sunken);border:1px solid var(--line);display:flex;align-items:center;justify-content:center;flex:0 0 auto">
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="var(--ink-3)" stroke-width="1.5"><rect x="2" y="3.5" width="12" height="9" rx="2"></rect><circle cx="11" cy="8" r="1.3" fill="var(--ink-3)" stroke="none"></circle></svg>
            </span>
            <span style="font-size:12px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink)">Nedladdningsdisk</span>
          </div>
          <div style="position:relative;flex:1 1 240px;min-width:230px;max-width:380px">
            <button data-click="${on(v.toggleDiskDD)}" style="width:100%;display:flex;align-items:center;gap:11px;background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:9px 13px;cursor:pointer;text-align:left;box-shadow:var(--shadow-sm)" data-sh="border-color:var(--line-2) !important">
              <span style="font-family:'Geist',system-ui,sans-serif;font-size:13px;font-weight:600;color:var(--ink);background:var(--sunken);border:1px solid var(--line);border-radius:6px;padding:2px 7px;flex:0 0 auto;font-variant-numeric:tabular-nums">${esc(v.curDiskDrive)}</span>
              <span style="flex:1;min-width:0;font-size:14.5px;font-weight:500;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.curDiskName)}</span>
              <span style="font-size:13px;color:var(--ink);font-variant-numeric:tabular-nums;flex:0 0 auto">${esc(v.curDiskFree)}</span>
              <span style="width:7px;height:7px;border-right:1.6px solid var(--ink-3);border-bottom:1.6px solid var(--ink-3);transform:rotate(45deg);margin:-3px 2px 0 0;flex:0 0 auto"></span>
            </button>
            ${ v.diskDDOpen ? `<div style="position:absolute;top:calc(100% + 6px);left:0;right:0;z-index:30;background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);padding:6px;animation:fadeup .14s ease">
              ${ v.diskOptions.map(function(d){ return `<button data-click="${on(d.onPick)}" style="${d.style}" data-sh="background:var(--sunken) !important">
                  <span style="font-family:'Geist',system-ui,sans-serif;font-size:13px;font-weight:600;color:var(--ink);background:var(--sunken);border:1px solid var(--line);border-radius:6px;padding:2px 7px;flex:0 0 auto;font-variant-numeric:tabular-nums">${esc(d.drive)}</span>
                  <span style="flex:1;min-width:0">
                    <span style="display:block;font-size:15px;font-weight:500;color:var(--ink)">${esc(d.name)}</span>
                    <span style="display:block;font-size:12.5px;color:var(--ink-2);font-variant-numeric:tabular-nums">${esc(d.free)}</span>
                  </span>
                  <span style="${d.checkStyle}">✓</span>
                </button>`; }).join('') }
            </div>` : '' }
          </div>
        </div>
        <div style="border-top:1px solid var(--line);padding-top:14px;display:flex;flex-wrap:wrap;gap:14px 28px">
          ${ v.hwSpecs.map(function(s){ return `<span style="display:inline-flex;flex-direction:column;gap:3px">
              <span style="font-size:11.5px;text-transform:uppercase;letter-spacing:0.06em;font-weight:700;color:var(--ink)">${esc(s.k)}</span>
              <span style="font-size:14px;font-weight:500;color:var(--ink);font-variant-numeric:tabular-nums">${esc(s.v)}</span>
            </span>`; }).join('') }
        </div>
      </div>

      <!-- Whisper -->
      <div style="margin-bottom:30px">
        <div style="display:flex;align-items:baseline;gap:9px;margin-bottom:12px">
          <h2 style="font-size:17.5px;font-weight:600;letter-spacing:-0.01em;margin:0">Transkriberingsmodeller</h2>
          <span style="color:var(--ink);font-size:15px;font-weight:500">tal till text · svenska & flerspråkigt</span>
        </div>
        <div style="background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:var(--shadow-sm)">
          ${ v.whisperRows.map(function(w){ return modelRow(w); }).join('') }
        </div>
      </div>

      <!-- LLM -->
      <div style="margin-bottom:30px">
        <div style="display:flex;align-items:baseline;gap:9px;margin-bottom:12px">
          <h2 style="font-size:17.5px;font-weight:600;letter-spacing:-0.01em;margin:0">Språk- och videomodeller</h2>
          <span style="color:var(--ink);font-size:15px;font-weight:500">efterbearbetning & analys · lokalt via Ollama</span>
        </div>
        <p style="margin:-4px 0 12px;font-size:13.5px;color:var(--ink-2);max-width:620px">Kvantiseringsnivån väljs automatiskt efter din lediga VRAM — håll muspekaren över den <span style="color:var(--accent);font-weight:600">blå Q-taggen</span> för att se vilken nivå och vad den innebär.</p>

        <!-- Användningsfall -->
        <div style="display:flex;align-items:center;gap:11px;flex-wrap:wrap;margin-bottom:14px">
          <span style="font-size:11.5px;text-transform:uppercase;letter-spacing:0.05em;color:var(--ink-2);font-weight:600">Användningsfall</span>
          <div style="display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:12px;flex-wrap:wrap">
            ${ v.useCaseOptions.map(function(u){ return `<button data-click="${on(u.onPick)}" style="${u.style}" data-sh="background:var(--surface) !important;color:var(--ink) !important;box-shadow:var(--shadow-sm) !important">${esc(u.label)}</button>`; }).join('') }
          </div>
          <span data-enter="${on(v.useCaseTip.onEnter)}" data-leave="${on(v.useCaseTip.onLeave)}" style="${v.infoBadgeStyle}">?</span>
        </div>
        <div style="background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:var(--shadow-sm)">
          ${ v.llmRows.map(function(l){ return modelRow(l); }).join('') }
          ${ v.llmEmpty ? `<div style="padding:26px;text-align:center;color:var(--ink-2);font-size:15px">Ingen LLM-modell matchar det valda användningsfallet.</div>` : '' }
        </div>
      </div>

    </section>`;
}

function viewHistory(v){ return `
    <section style="padding:44px 0 96px">
      <div style="text-align:center;max-width:640px;margin:0 auto 28px">
        <h1 style="font-size:34px;font-weight:600;letter-spacing:-0.03em;margin:0 0 6px">Historik</h1>
        <p style="margin:0;color:var(--ink-2);font-size:17px">Dina tidigare transkriberingar. Öppna, kör om eller ladda ner igen — allt ligger kvar lokalt.</p>
      </div>

      ${ v.historyEmpty ? `
        <div style="text-align:center;padding:60px 24px;background:var(--surface);border:1px solid var(--line);border-radius:16px;color:var(--ink-2);font-size:16px">Inga transkriberingar än. När du kört klart en fil dyker den upp här.</div>
      ` : '' }

      <div style="display:flex;flex-direction:column;gap:10px">
        ${ v.historyItems.map(function(h){ return `
          <div data-key="${esc(h.id)}" style="display:flex;align-items:center;gap:15px;background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:15px 18px;box-shadow:var(--shadow-sm)">
            <span style="width:64px;height:40px;border-radius:9px;background:var(--sunken);border:1px solid var(--line);display:flex;align-items:center;justify-content:center;flex:0 0 auto;overflow:hidden">
              ${ h.thumbUrl ? `
                <img src="${h.thumbUrl}" loading="lazy" alt="" style="width:100%;height:100%;object-fit:cover" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
                <span style="display:none;align-items:flex-end;gap:2px;height:16px">
                  <span style="width:2.5px;height:6px;border-radius:2px;background:var(--ink-3)"></span>
                  <span style="width:2.5px;height:13px;border-radius:2px;background:var(--ink-3)"></span>
                  <span style="width:2.5px;height:16px;border-radius:2px;background:var(--accent)"></span>
                  <span style="width:2.5px;height:9px;border-radius:2px;background:var(--ink-3)"></span>
                </span>
              ` : `
                <span style="display:flex;align-items:flex-end;gap:2px;height:16px">
                  <span style="width:2.5px;height:6px;border-radius:2px;background:var(--ink-3)"></span>
                  <span style="width:2.5px;height:13px;border-radius:2px;background:var(--ink-3)"></span>
                  <span style="width:2.5px;height:16px;border-radius:2px;background:var(--accent)"></span>
                  <span style="width:2.5px;height:9px;border-radius:2px;background:var(--ink-3)"></span>
                </span>
              ` }
            </span>
            <div style="flex:1;min-width:0">
              <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">
                <span style="font-size:16px;font-weight:500;color:var(--ink);font-variant-numeric:tabular-nums;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(h.name)}</span>
                <span style="font-size:13px;color:var(--ink-3);font-variant-numeric:tabular-nums">${esc(h.date)}</span>
              </div>
              <div style="font-size:13.5px;color:var(--ink-2);margin-top:3px;font-variant-numeric:tabular-nums">${esc(h.meta)}</div>
              <div style="display:flex;gap:6px;margin-top:9px;flex-wrap:wrap">
                ${ h.formats.map(function(f){ return `
                  <span style="font-size:11.5px;font-weight:500;color:var(--accent);background:var(--accent-weak);border-radius:5px;padding:2px 8px;letter-spacing:0.03em">${esc(f.label)}</span>
                `; }).join('') }
              </div>
            </div>
            <div style="display:flex;align-items:center;gap:7px;flex:0 0 auto">
              <button data-click="${on(h.onOpen)}" style="background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:8px 14px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--ink) !important;background:var(--ink) !important;color:var(--btn-fg) !important">Öppna</button>
              <button data-click="${on(h.onDownload)}" aria-label="Ladda ner" style="width:38px;height:38px;border:1px solid var(--line);background:var(--surface);border-radius:9px;cursor:pointer;color:var(--ink-2);display:flex;align-items:center;justify-content:center;transition:border-color .12s,color .12s,background .12s" data-sh="border-color:var(--accent) !important;color:var(--accent) !important;background:var(--accent-weak) !important">
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2.5v7.5"></path><path d="M4.5 6.5 8 10l3.5-3.5"></path><path d="M3 13.5h10"></path></svg>
              </button>
              <button data-click="${on(h.onRerun)}" aria-label="Kör om" style="width:38px;height:38px;border:1px solid var(--line);background:var(--surface);border-radius:9px;cursor:pointer;color:var(--ink-2);display:flex;align-items:center;justify-content:center;transition:border-color .12s,color .12s,background .12s" data-sh="border-color:var(--accent) !important;color:var(--accent) !important;background:var(--accent-weak) !important">
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M13 8a5 5 0 1 1-1.5-3.5"></path><path d="M13 2.5V5h-2.5"></path></svg>
              </button>
              <button data-click="${on(h.onDelete)}" aria-label="Ta bort" style="width:38px;height:38px;border:1px solid var(--line);background:var(--surface);border-radius:9px;cursor:pointer;color:var(--ink-3);display:flex;align-items:center;justify-content:center" data-sh="border-color:var(--bad) !important;color:var(--bad) !important">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.5 8.5h6l.5-8.5"></path></svg>
              </button>
            </div>
          </div>
        `; }).join('') }
      </div>
    </section>
`; }

function viewModals(v){ return `
  ${ v.anyDDOpen ? `
    <div data-click="${on(v.closeDD)}" style="position:fixed;inset:0;z-index:25"></div>
  ` : '' }

  ${ v.chatModalOpen ? `
  <div data-click="${on(v.closeChatModal)}" style="position:fixed;inset:0;z-index:120;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(11,11,13,.42);backdrop-filter:blur(3px);animation:modalback .34s ease">
    <div data-click="${on(v.stop)}" style="width:100%;max-width:520px;max-height:88vh;display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--line);border-radius:26px;box-shadow:var(--shadow);overflow:visible;animation:modalpop .52s cubic-bezier(.16,1,.3,1);transform-origin:center bottom">

      <div style="padding:14px 0 0;display:flex;justify-content:center;flex:0 0 auto"><span style="width:38px;height:4px;border-radius:99px;background:var(--line-2)"></span></div>

      <div style="padding:16px 26px 14px;flex:0 0 auto">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
          <div style="min-width:0">
            <div style="font-size:23px;font-weight:600;letter-spacing:-.025em;color:var(--ink)">Chatta med transkriptet</div>
            <div style="position:relative;margin-top:7px">
              <button data-click="${on(v.toggleChatModelDD)}" style="display:inline-flex;align-items:center;gap:8px;background:transparent;border:none;padding:0;cursor:pointer;font-family:inherit;max-width:100%;flex-wrap:wrap" data-sh="opacity:.65 !important">
                <span style="width:7px;height:7px;border-radius:50%;flex:0 0 auto;background:var(--ok)"></span>
                <span style="font-size:14.5px;font-weight:500;color:var(--ink);font-family:'Geist',system-ui,sans-serif">${esc(v.chatModelName)}</span>
                <span style="font-size:14px;color:var(--ink-3)">·</span>
                <span style="font-size:14px;color:var(--ink-2)">${esc(v.chatKind)}</span>
                <span style="font-size:14px;color:var(--ink-3)">·</span>
                <span style="font-size:14px;color:var(--ink-2);font-variant-numeric:tabular-nums">${esc(v.chatCtx)}</span>
                <span style="width:6px;height:6px;border-right:1.6px solid var(--ink-3);border-bottom:1.6px solid var(--ink-3);transform:rotate(45deg);margin:-3px 0 0 2px;flex:0 0 auto"></span>
              </button>
              ${ v.chatModelDDOpen ? `
              <div style="position:absolute;top:calc(100% + 8px);left:0;width:280px;z-index:40;background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);padding:6px;animation:fadeup .14s ease">
                ${ v.chatModelOptions.map(function(m){ return `
                  <button data-key="${esc(m.name)}" data-click="${on(m.onPick)}" style="${m.style}" data-sh="background:var(--sunken) !important">
                    <span style="flex:1;min-width:0;font-size:15px;font-family:'Geist',system-ui,sans-serif;color:var(--ink)">${esc(m.name)}</span>
                    <span style="${m.visionStyle}">Vision</span>
                    <span style="font-size:12.5px;color:var(--ink-2);flex:0 0 auto">${esc(m.size)}</span>
                    <span style="${m.checkStyle}">✓</span>
                  </button>
                `; }).join('') }
              </div>
              ` : '' }
            </div>
          </div>
          <button data-click="${on(v.closeChatModal)}" aria-label="Stäng" style="width:34px;height:34px;flex:0 0 auto;border:1px solid var(--line);background:var(--surface);border-radius:50%;cursor:pointer;color:var(--ink);display:flex;align-items:center;justify-content:center" data-sh="background:var(--sunken) !important;border-color:var(--line-2) !important">
            <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 3l8 8M11 3l-8 8"></path></svg>
          </button>
        </div>
      </div>

      <div data-ref="${on(v.chatThreadRef)}" data-hidescroll="1" style="flex:1;overflow-y:auto;padding:4px 26px 16px;display:flex;flex-direction:column;gap:14px;min-height:150px">
        ${ v.chat.map(function(m){ return `
          <div style="${m.rowStyle}">
            ${ m.hasAttach ? `
              <span style="${m.attachStyle}"><span style="width:8px;height:8px;border-radius:2px;background:var(--accent);flex:0 0 auto"></span>${esc(m.attach)}</span>
            ` : '' }
            ${ m.hasReason ? `
              <div style="${m.reasonStyle}"><span style="display:block;font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-3);margin-bottom:4px">Resonemang</span>${esc(m.reason)}</div>
            ` : '' }
            <div style="${m.bubbleStyle}">${esc(m.text)}</div>
          </div>
        `; }).join('') }
        ${ v.chatTyping ? `
          <div style="display:flex"><div style="background:var(--surface);border:1px solid var(--line);border-radius:15px 15px 15px 4px;padding:12px 16px;color:var(--ink-2);font-size:15px">skriver …</div></div>
        ` : '' }
      </div>

      <div style="padding:8px 20px 20px;flex:0 0 auto">
        <input data-ref="${on(v.imgInputRef)}" type="file" accept="image/*" multiple="true" data-change="${on(v.onPickImage)}" style="display:none">
        ${ v.hasAttach ? `
          <div style="display:flex;gap:7px;flex-wrap:wrap;padding:0 4px 10px">
            ${ v.chatAttachments.map(function(a){ return `
              <span style="display:inline-flex;align-items:center;gap:7px;font-size:13px;color:var(--ink);background:var(--accent-weak);border:1px solid color-mix(in srgb,var(--accent) 22%,transparent);border-radius:8px;padding:4px 8px 4px ${a.thumb ? '4px' : '10px'}">
                ${ a.thumb ? `<img src="${esc(a.thumb)}" alt="" style="width:26px;height:26px;border-radius:5px;object-fit:cover;flex:0 0 auto;display:block">` : `<span style="${a.dotStyle}"></span>` }${esc(a.label)}
                <button data-click="${on(a.onRemove)}" aria-label="Ta bort" style="width:17px;height:17px;border:none;background:transparent;color:var(--ink-2);cursor:pointer;display:flex;align-items:center;justify-content:center;font-family:inherit" data-sh="color:var(--ink) !important">
                  <svg width="11" height="11" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 3l8 8M11 3l-8 8"></path></svg>
                </button>
              </span>
            `; }).join('') }
          </div>
        ` : '' }
        <div style="display:flex;align-items:center;gap:8px;background:var(--sunken);border:1px solid var(--line);border-radius:99px;padding:6px">
          <button data-click="${on(v.chatPlusAttach)}" aria-label="Bifoga bild" style="width:34px;height:34px;flex:0 0 auto;border:1px solid var(--line);border-radius:50%;background:var(--surface);cursor:pointer;color:var(--ink-2);display:flex;align-items:center;justify-content:center" data-sh="color:var(--ink) !important;border-color:var(--line-2) !important">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M8 3v10M3 8h10"></path></svg>
          </button>
          <input value="${esc(v.chatInput)}" data-input="${on(v.onChatInput)}" data-keydown="${on(v.onChatKey)}" placeholder="Fråga om transkriptet …" style="flex:1;min-width:0;background:transparent;border:none;outline:none;font-size:15.5px;color:var(--ink);font-family:inherit;padding:0 4px">
          <button data-click="${on(v.onChatSend)}" aria-label="Skicka" style="width:40px;height:40px;flex:0 0 auto;border:none;border-radius:50%;background:var(--btn-bg);color:var(--btn-fg);cursor:pointer;display:flex;align-items:center;justify-content:center" data-sh="background:color-mix(in srgb, var(--btn-bg) 72%, var(--accent)) !important">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"></path></svg>
          </button>
        </div>
        <div style="display:flex;align-items:center;gap:10px;margin-top:11px;flex-wrap:wrap;padding:0 2px">
          <button data-click="${on(v.onToggleChatThink)}" style="${v.chatThinkBtnStyle}" aria-pressed="${v.chatThink ? 'true' : 'false'}" data-sh="border-color:var(--ink-3) !important">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8 1.5a4.5 4.5 0 0 0-2.6 8.2c.4.3.6.6.6 1v.8h4v-.8c0-.4.2-.7.6-1A4.5 4.5 0 0 0 8 1.5z"></path><path d="M6 14.5h4"></path></svg>
            Tänk djupare
          </button>
          <span style="font-size:12px;color:var(--ink-3);flex:1;min-width:120px">${esc(v.chatThinkHint)}</span>
        </div>
        <div style="font-size:12px;color:var(--ink-2);line-height:1.45;padding:9px 6px 0">Bifoga en bild (📎) så svarar <strong style="color:var(--ink);font-weight:600">Gemma 3 (vision)</strong> på frågor om den — modellen växlas in automatiskt.</div>
      </div>

    </div>
  </div>
  ` : '' }

  ${ v.tipOpen ? `
    <div style="${v.tipStyle}">${esc(v.tipText)}</div>
  ` : '' }

  ${ v.transcriptOpen ? `
  <div style="position:fixed;inset:0;z-index:100;background:var(--canvas);display:flex;flex-direction:column">
    <div style="display:flex;align-items:center;gap:14px;padding:15px 28px;border-bottom:1px solid var(--line)">
      <div style="min-width:0">
        <div style="display:flex;align-items:center;gap:9px"><span style="font-size:17px;font-weight:600;letter-spacing:-0.02em">Transkript</span>${ v.transcriptEdited ? `<span style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ok);font-weight:500"><span style="width:6px;height:6px;border-radius:50%;background:var(--ok)"></span>Sparat</span>` : '' }</div>
        <div style="font-size:13px;color:var(--ink-2);font-variant-numeric:tabular-nums">${esc(v.transcriptFileName)}</div>
      </div>
      <div style="flex:1"></div>
      ${ v.notEditing ? `
      <div style="display:flex;align-items:center;gap:8px;background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:7px 8px 7px 13px;box-shadow:var(--shadow-sm)">
        <span style="width:13px;height:13px;border:1.6px solid var(--ink-3);border-radius:50%;flex:0 0 auto"></span>
        <input data-tsearch="1" value="${esc(v.searchQuery)}" data-input="${on(v.onTSearch)}" data-keydown="${on(v.onSearchKey)}" placeholder="Sök i transkriptet …" style="border:none;outline:none;background:transparent;font-size:14.5px;color:var(--ink);font-family:inherit;width:200px">
        <span style="font-size:12.5px;color:var(--ink-2);font-variant-numeric:tabular-nums;white-space:nowrap;min-width:42px;text-align:right">${esc(v.matchLabel)}</span>
        <div style="display:flex;gap:2px;border-left:1px solid var(--line);padding-left:6px">
          <button data-click="${on(v.prevMatch)}" aria-label="Föregående träff" style="width:26px;height:26px;border:none;background:transparent;border-radius:7px;cursor:pointer;color:var(--ink-2);font-size:14px;display:flex;align-items:center;justify-content:center" data-sh="background:var(--sunken) !important;color:var(--ink) !important">↑</button>
          <button data-click="${on(v.nextMatch)}" aria-label="Nästa träff" style="width:26px;height:26px;border:none;background:transparent;border-radius:7px;cursor:pointer;color:var(--ink-2);font-size:14px;display:flex;align-items:center;justify-content:center" data-sh="background:var(--sunken) !important;color:var(--ink) !important">↓</button>
        </div>
      </div>
      ` : '' }
      <button data-click="${on(v.onToggleEdit)}" style="${v.editBtnStyle}" data-sh="border-color:var(--line-2) !important">
        ${ v.notEditing ? `<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 3.5l3 3L6 13l-3.5.5L3 10z"></path></svg>` : '' }${esc(v.editBtnLabel)}
      </button>
      <button data-click="${on(v.closeTranscript)}" aria-label="Stäng" style="width:38px;height:38px;flex:0 0 auto;border:1px solid var(--line);background:var(--surface);border-radius:10px;cursor:pointer;color:var(--ink);font-size:16px;display:flex;align-items:center;justify-content:center" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important">✕</button>
    </div>

    ${ v.editing ? `
      <div style="background:var(--accent-weak);border-bottom:1px solid color-mix(in srgb,var(--accent) 18%,transparent);padding:9px 28px;font-size:13.5px;color:var(--accent);font-weight:500;text-align:center">Redigeringsläge — klicka i en rad och rätta texten. Ändringarna sparas när du klickar Klar.</div>
    ` : '' }

    <div data-ref="${on(v.scrollRef)}" data-hidescroll="1" style="flex:1;overflow-y:auto;padding:26px 32px 90px">
      <div style="max-width:760px;margin:0 auto">
        ${ v.tLines.map(function(ln){ return `
          <div data-key="${esc(ln.idx)}" style="${ln.rowStyle}">
            <span data-click="${on(ln.onJump)}" style="${ln.timeStyle}" data-sh="color:var(--accent) !important">${esc(ln.time)}</span>
            ${ v.editing ? `
              <div data-eline="${esc(ln.idx)}" contentEditable="true" data-input="${on(v.onEditInput)}" style="${ln.editStyle}"></div>
            ` : '' }
            ${ v.notEditing ? `
              <span style="font-size:18px;line-height:1.7;color:var(--ink);flex:1;min-width:0">
                ${ ln.segments.map(function(seg){ return `
                  ${ seg.plain ? `<span>${esc(seg.text)}</span>` : '' }
                  ${ seg.match ? `<span style="background:var(--accent-weak);border-radius:3px;box-shadow:0 0 0 1px var(--accent-weak)">${esc(seg.text)}</span>` : '' }
                  ${ seg.current ? `<span data-current="1" style="background:var(--accent);color:#fff;border-radius:3px;box-shadow:0 0 0 2px var(--accent)">${esc(seg.text)}</span>` : '' }
                `; }).join('') }
              </span>
            ` : '' }
          </div>
        `; }).join('') }
      </div>
    </div>

    ${ v.hasMediaEl ? `<audio data-ref="${on(v.mediaRef)}" src="${esc(v.mediaUrl)}" preload="metadata" style="display:none"></audio>` : '' }
    <div style="flex:0 0 auto;border-top:1px solid var(--line);background:color-mix(in srgb,var(--surface) 72%,transparent);backdrop-filter:saturate(1.3) blur(14px);padding:13px 28px;display:flex;align-items:center;gap:18px">
      <button data-click="${on(v.onTogglePlay)}" aria-label="Spela eller pausa" style="width:46px;height:46px;flex:0 0 auto;border-radius:50%;border:none;background:var(--btn-bg);color:var(--btn-fg);cursor:pointer;display:flex;align-items:center;justify-content:center" data-sh="background:color-mix(in srgb, var(--btn-bg) 78%, var(--accent)) !important">
        ${ v.audioPaused ? `<svg width="17" height="17" viewBox="0 0 16 16" fill="currentColor"><path d="M4.5 3.2v9.6c0 .5.5.8 1 .5l7.3-4.8c.4-.3.4-.8 0-1.1L5.5 2.7c-.5-.3-1 0-1 .5z"></path></svg>` : '' }
        ${ v.audioPlaying ? `<svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor"><rect x="3.5" y="3" width="3.2" height="10" rx="1"></rect><rect x="9.3" y="3" width="3.2" height="10" rx="1"></rect></svg>` : '' }
      </button>
      <span style="font-size:13.5px;color:var(--ink-2);font-variant-numeric:tabular-nums;flex:0 0 auto;width:42px">${esc(v.audioCur)}</span>
      <div data-ref="${on(v.seekTrackRef)}" data-click="${on(v.onSeekClick)}" style="flex:1;height:42px;display:flex;align-items:stretch;gap:2px;cursor:pointer">
        ${ v.waveBars.map(function(b){ return `<span style="${b.style}"></span>`; }).join('') }
      </div>
      <span style="font-size:13.5px;color:var(--ink-2);font-variant-numeric:tabular-nums;flex:0 0 auto;width:42px;text-align:right">${esc(v.audioDur)}</span>
    </div>
  </div>
  ` : '' }

  ${ v.logOpen ? `
  <div style="position:fixed;inset:0;z-index:100;background:var(--canvas);display:flex;flex-direction:column">
    <div style="display:flex;align-items:center;gap:16px;padding:16px 28px;border-bottom:1px solid var(--line)">
      <div style="display:flex;align-items:center;gap:10px;min-width:0">
        <span style="width:8px;height:8px;border-radius:50%;background:var(--ok);flex:0 0 auto"></span>
        <div style="min-width:0">
          <div style="font-size:17px;font-weight:600;letter-spacing:-0.02em">Logg</div>
          <div style="font-size:13px;color:var(--ink-2);font-variant-numeric:tabular-nums">${esc(v.statusFile)}</div>
        </div>
      </div>
      <div style="flex:1"></div>
      <button data-click="${on(v.closeLog)}" aria-label="Stäng" style="width:38px;height:38px;flex:0 0 auto;border:1px solid var(--line);background:var(--surface);border-radius:10px;cursor:pointer;color:var(--ink);font-size:16px;display:flex;align-items:center;justify-content:center" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important">✕</button>
    </div>
    <div data-hidescroll="1" style="flex:1;overflow-y:auto;padding:30px 32px 80px">
      <div style="max-width:760px;margin:0 auto">
        ${ v.logRows.map(function(r){ return `
          <div style="display:flex;gap:18px">
            <span style="font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums;font-size:13.5px;color:var(--ink-3);width:52px;flex:0 0 auto;text-align:right;padding-top:2px">${esc(r.time)}</span>
            <div style="position:relative;display:flex;flex-direction:column;align-items:center;flex:0 0 auto">
              <span style="${r.dotStyle}">${esc(r.icon)}</span>
              <span style="${r.lineStyle}"></span>
            </div>
            <span style="font-family:'Geist',system-ui,sans-serif;font-variant-numeric:tabular-nums;font-size:15px;color:var(--ink);padding-bottom:18px;line-height:1.5;min-width:0">${esc(r.msg)}</span>
          </div>
        `; }).join('') }
      </div>
    </div>
  </div>
  ` : '' }

  ${ v.diskWarnOpen ? `
  <div data-click="${on(v.onDiskWarnCancel)}" style="position:fixed;inset:0;z-index:130;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(11,11,13,.42);backdrop-filter:blur(3px);animation:modalback .26s ease">
    <div data-click="${on(v.stop)}" style="width:100%;max-width:440px;background:var(--surface);border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow);padding:26px 26px 22px;animation:modalpop .42s cubic-bezier(.16,1,.3,1)">
      <div style="display:flex;align-items:center;gap:13px;margin-bottom:15px">
        <span style="width:42px;height:42px;border-radius:12px;flex:0 0 auto;background:color-mix(in srgb,var(--warn) 15%,transparent);color:var(--warn);display:flex;align-items:center;justify-content:center"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 1.5 21h21z"></path><path d="M12 9.5v5"></path><path d="M12 17.5h.01"></path></svg></span>
        <div style="font-size:19px;font-weight:600;letter-spacing:-0.02em;color:var(--ink)">Inte tillräckligt med diskutrymme</div>
      </div>
      <p style="margin:0 0 8px;color:var(--ink-2);font-size:15px;line-height:1.55">${esc(v.diskWarnText)}</p>
      <p style="margin:0 0 20px;color:var(--ink-2);font-size:15px;line-height:1.55">Välj en annan disk, eller frigör utrymme och försök igen.</p>
      <div style="display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap">
        <button data-click="${on(v.onDiskWarnCancel)}" style="background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:11px;padding:11px 18px;font-size:15px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important">Avbryt</button>
        <button data-click="${on(v.onDiskWarnUseBest)}" style="display:inline-flex;align-items:center;gap:8px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:11px;padding:11px 18px;font-size:15px;font-weight:500;cursor:pointer;font-family:inherit;box-shadow:var(--shadow-sm)" data-sh="background:color-mix(in srgb, var(--btn-bg) 78%, var(--accent)) !important">${esc(v.diskWarnBestLabel)}</button>
      </div>
    </div>
  </div>
  ` : '' }

  ${ v.confirmOpen ? `
  <div data-click="${on(v.onConfirmNo)}" style="position:fixed;inset:0;z-index:140;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(11,11,13,.42);backdrop-filter:blur(3px);animation:modalback .26s ease">
    <div data-click="${on(v.stop)}" style="width:100%;max-width:420px;background:var(--surface);border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow);padding:26px;animation:modalpop .42s cubic-bezier(.16,1,.3,1)">
      <div style="font-size:19px;font-weight:600;letter-spacing:-0.02em;color:var(--ink);margin-bottom:9px">${esc(v.confirmTitle)}</div>
      <p style="margin:0 0 22px;color:var(--ink-2);font-size:15px;line-height:1.55">${esc(v.confirmBody)}</p>
      <div style="display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap">
        <button data-click="${on(v.onConfirmNo)}" style="background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:11px;padding:11px 18px;font-size:15px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important">Avbryt</button>
        <button data-click="${on(v.onConfirmYes)}" style="${v.confirmBtnStyle}">${esc(v.confirmLabel)}</button>
      </div>
    </div>
  </div>
  ` : '' }

  ${ v.hasToast ? `
  <div style="position:fixed;left:50%;bottom:30px;transform:translate(-50%,0);z-index:200;display:flex;align-items:center;gap:13px;background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:13px 20px 13px 13px;box-shadow:var(--shadow);width:336px;animation:toastin .32s cubic-bezier(.16,1,.3,1)">
    ${ v.toastLoading ? `
      <span style="width:40px;height:40px;border-radius:12px;flex:0 0 auto;display:flex;align-items:center;justify-content:center;background:var(--accent-weak);color:var(--accent)">
        <span style="display:flex;animation:dlbounce .85s ease-in-out infinite"><svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v8"></path><path d="M4.5 6.5 8 10l3.5-3.5"></path><path d="M3 13.5h10"></path></svg></span>
      </span>
    ` : '' }
    ${ v.toastDone ? `
      <span style="width:40px;height:40px;border-radius:12px;flex:0 0 auto;display:flex;align-items:center;justify-content:center;background:color-mix(in srgb,var(--ok) 16%,transparent);color:var(--ok);font-size:18px">✓</span>
    ` : '' }
    <div style="min-width:0;flex:1">
      <div style="display:flex;align-items:baseline;justify-content:space-between;gap:10px">
        <span style="font-size:14.5px;font-weight:600;color:var(--ink);letter-spacing:-0.01em">${esc(v.toastTitle)}</span>
        <span style="font-size:12.5px;color:var(--ink-2);font-variant-numeric:tabular-nums;flex:0 0 auto">${esc(v.toastName)}</span>
      </div>
      <div style="height:6px;border-radius:99px;background:var(--track);overflow:hidden;margin:7px 0 5px"><div style="${v.toastBarStyle}"></div></div>
      <div style="font-size:12px;color:var(--ink-2);font-variant-numeric:tabular-nums">${esc(v.toastDetail)}</div>
    </div>
    <button data-click="${on(v.closeToast)}" aria-label="Stäng" style="width:26px;height:26px;flex:0 0 auto;align-self:flex-start;border:none;background:transparent;border-radius:7px;cursor:pointer;color:var(--ink-3);font-size:13px;display:flex;align-items:center;justify-content:center" data-sh="background:var(--sunken) !important;color:var(--ink) !important">✕</button>
  </div>
  ` : '' }
`; }

  // <<<VIEWS_END>>>

  function view(v) {
    return viewHeader(v) +
      '<main style="max-width:780px;margin:0 auto;padding:0 32px">' +
      (v.tabTranscribe ? viewTranscribe(v) : '') +
      (v.tabModels ? viewModels(v) : '') +
      (v.tabHistory ? viewHistory(v) : '') +
      '</main>' +
      viewModals(v);
  }

  /* ------------------------------------------------------------------ init -- */
  function init() {
    var root = document.getElementById('root');
    bindEvents(root);
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('pointerdown', onAnyPress, true);
    syncTheme();
    _prevTab = S.tab; _prevStep = S.step; _prevOp = S.ppOp;
    render();
    loadModels().then(loadSettings);   // real catalog, then reflect chosen models disk
    loadHistory();  // load persisted transcription history
    loadAudioModel();  // audio-correction model install status
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();

})();
