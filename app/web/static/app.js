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
    source: '',
    dragging: false,
    urlInput: '',
    step: 'source',
    model: 'KB-Whisper large',
    language: 'sv',
    targetLanguage: 'sv',       // resultatspråk; skiljer det sig från language översätts undertexterna
    formats: { srt: true, txt: true, vtt: false },
    subtitleMode: 'separate',   // 'separate' = media + SRT i mappen | 'embed' = bädda in i videon
    embedKind: 'soft',          // 'soft' = muxat sub-spår | 'burn' = inbränt
    audioCorrect: true,         // andra passet: rätta texten mot ljudet (Gemma 3n) — på som standard
    audioModelInstalled: false, // status från /api/audio-model
    audioModelDownloading: false,
    run: 'idle',
    progress: 0,        // server-rapporterad "sanning" (kliver i hopp mellan SSE-event)
    dispProgress: 0,    // mjukt animerat visningsvärde — rör sig alltid framåt, aldrig bakåt
    elapsed: 0,
    log: [],
    ppModel: 'Qwen3 14B (Q8_0)',   // fast intern LLM för chatt/analys
    // Per-lektion chattmodal (Chatta-knapp på inspelnings-kortet) — egen isolerad chatt
    lessonChatId: null,         // öppen lektions history-id (även "overlay öppen"-flagga)
    lessonChatName: '',
    lessonChatSegs: [],         // lektionens transkript-segment ({time,text})
    lessonChat: [],
    lessonChatInput: '',
    lessonChatTyping: false,
    lessonChatCiteSel: null,
    reasonOpen: {},             // resonemangsrutor: mi → öppen/stängd (default: öppen medan den strömmar)
    lessonChatThink: false,
    lessonChatMeta: null,       // overlay-huvudets metadata: {lessonId,date,dur,model,lang,group,course,cc}
    lessonChatHitT: null,       // tidsstämpel (mm:ss) att markera i overlay-transkriptet
    lessonChatEvent: null,      // kalenderförslag: {title,when,desc,added,busy,endDay}
    ovEvOpen: false,            // förslags-raden i overlayen utfälld till redigeringsboxen
    citePeek: null,             // källmodal från arkivsvarets sifferkällor {src,q,name,meta,rows,…}
    citePeekClosing: false,     // modalen spelar sin stängningsanimation
    ovDescView: false,          // anteckningen i snabbtitten öppnad i läsmodal
    evPick: null,               // öppen dag/tid-väljare i kalenderförslaget
    descModal: false,           // anteckningens inzoomade redigeringsmodal
    descModalClosing: false,
    calConnected: null,         // Google Kalender-status: null = okänd, annars bool
    calClientReady: null,       // finns en OAuth-klient (inbyggd/installerad)?
    calHint: '',                // senaste hjälptext från /api/calendar/status
    calSetupOpen: false,        // guidat "Koppla Google Kalender"-fönster
    calBusy: false,             // installation/inloggning pågår
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
    logExpand: false,           // vikbar logg i statuskortet (design: Visa/Dölj)
    toast: null,
    searchQuery: '',
    currentMatch: 0,
    queue: [],
    qStatus: {},
    qProgress: {},
    activeId: null,
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
    history: [],
    histViewing: null,
    lessons: [],
    groups: [],
    courses: [],
    lessonFilterGroup: '',
    lessonFilterCourse: '',
    lessonFilterMonth: '',     // klientfilter på YYYY-MM (datum)
    filterOpen: null,          // öppen filterpopover: 'klass' | 'kurs' | 'datum'
    filterClosing: false,      // popovern spelar sin stängningsanimation
    askScanPlan: null,         // scan_plan-eventet: [{key, name}] i äkta genomsökningsordning
    askScanRes: {},            // scan_result-eventen: key → verkligt träffantal
    askScanShown: 0,           // utrullningstakt: hur många kort som avslöjats hittills
    askDeep: null,             // deep_read-eventet: källorna AI:n läser djupt
    editingLesson: null,
    lessonEdits: {},
    nextPrep: null,
    lessonSearch: '',          // fritextsök över alla lektioner
    searchMode: 'ask',         // 'ask' = LLM-svar (RAG, mallens default) | 'keyword' = träfflista + livefilter
    searchHits: null,          // null = ingen sökning gjord; [] = inga träffar
    searching: false,
    askAnswer: '',             // strömmat LLM-svar i "Fråga"-läget
    askSources: null,          // lektioner svaret bygger på
    asking: false,
    askQ: '',                  // frågan som visas i tänker-bannern
    askZoom: false,            // SVAR-kortet förstorat till modal (design 14 juli)
    askZoomClosing: false,
    srcBox: true,              // hopfällbar "Källor i arkivet"-panel i svaret
    askFollowups: [],          // följdfrågor i svaret: {q, a, typing}
    askFollowInput: '',
    askEvent: null,            // kalenderförslag i arkivsvaret (samma form som lessonChatEvent)
    descModalFor: 'lesson',    // vilket förslag anteckningsmodalen redigerar: 'lesson' | 'ask'
    agenda: null,              // daterade poster tvärs alla klasser
    agendaOpen: false,         // utfälld agenda-panel
    agendaExporting: false,
    trends: null,              // terminstrender för vald klass
    backingUp: false,          // säkerhetskopiering pågår
    resultId: null,            // history-id för den öppna transkriberingen (för att spara redigering/sammanfattning)
    transcriptRaw: null,       // segmenten med start/end (display-arrayen tappar dem)
    confirm: null,
    diskWarn: null,
    transcript: null,
    resultFilesReal: null,
    catalogReady: false,
    recording: false,
    recElapsed: 0,
    recError: '',
    recMarkerCount: 0,         // antal markörer satta under pågående inspelning
    markers: [],               // markörer för den öppna transkriptvyn
    recLevel: 0,               // mikrofon-nivå 0..1 (nivåmätare)
    recSilent: false,          // varning: tyst/ingen signal en längre stund
    incompleteRecs: [],        // oavslutade inspelningar att återställa (krasch)
    // Planering (Fas 0): whiteboard-motorn renderar en hårdkodad exempellektion
    // i en egen iframe; LLM-generering kommer i Fas 1.
    wbRendered: false,         // aktuella tavlan är färdigrenderad i iframen
    wbWarnings: [],            // [WB]-varningar från motorns senaste rendering
    wbExporting: false,        // PNG-export pågår
    wbExportMsg: '',           // kvitto/fel från senaste exporten
    wbZoom: false,             // tavelkortet förstorat till modal (chatt + knappar i kortet)
    wbZoomClosing: false,
    // Planering (Fas 1): generera egna tavlor via LLM:en
    planGroupId: '',           // vald klass (''  = ingen)
    planCourseId: '',          // vald kurs
    planMoment: '',            // moment/ämne (fritext)
    planUnderlag: null,        // uppladdat underlag: {id, filer:[{namn,beskrivning}]}
    planUnderlagBusy: false,   // uppladdning/bildtolkning pågår
    planPhase: 'idle',         // idle|running|done|error
    planLog: [],               // loggrader från SSE-jobbet
    planId: null,              // serverns planerings-id (för refine/approve)
    planBoard: null,           // genererad WB-JSON ({title, boards})
    planErrors: [],            // kvarstående valideringsfel (redovisas ärligt)
    planChatInput: '',         // chattfältet för iteration
    planSavedPath: '',         // kvitto från Godkänn & spara
    planDatum: '',             // formulärets datum (för kalendern/minnet)
    planStarttid: '',          // formulärets starttid
    // Inbyggd kalender (Fas 3): lokal SQLite-läsning — ingen synk/CalDAV
    // Planeringsarkivet (ersätter kalendern): tavlor + prov i veckogrupper,
    // sök- och frågbara med samma RAG-mönster som Inspelningar-arkivet.
    arkItems: [],              // poster från /api/planning/archive
    arkQ: '',                  // sök-/frågefältet
    arkMode: 'ask',            // 'ask' = LLM-svar | 'keyword' = träfflista
    arkHits: null,             // null = ingen sökning; [] = inga träffar
    arkSearching: false,
    arkAsking: false,
    arkAnswer: '',             // strömmat LLM-svar
    arkSources: null,          // vilka tavlor/prov svaret bygger på
    arkQAsked: '',             // frågan som svaret gäller
    arkScanPlan: null,         // scan_plan: [{key, name}] i äkta genomsökningsordning
    arkScanRes: {},            // scan_result: key → verkligt träffantal
    arkScanShown: 0,           // utrullningstakt (avslöjade kort)
    arkDeep: null,             // deep_read: källorna AI:n läser djupt
    arkFollowups: [],          // följdfrågor [{q, a, typing}]
    arkFollowInput: '',
    // Provgeneratorn (Fas 4)
    exCourseId: '',            // vald kurs för provet
    exGroupId: '',             // vald klass (minneskontext + auto-koppling)
    exContent: [],             // kursens innehållspunkter (med behandlad-flagga)
    exPunkter: {},             // valda innehållspunkter {content_id: true}
    exAntal: '8',              // ungefärligt antal uppgifter
    exTid: '120',              // provtid i minuter
    exDelar: true,             // dela i Del B/C
    exDatum: '',               // provdatum (kalendern/minnet)
    exPhase: 'idle',           // idle|running|done|error
    exLog: [],                 // SSE-loggrader
    exUnderlag: null,          // bildunderlag för provet: {id, filer:[{namn,beskrivning}]}
    exUnderlagBusy: false,     // uppladdning/bildtolkning pågår
    exErrors: [],              // kvarstående schema-/balans-/kompileringsfel
    exam: null,                // serverns provresultat (id, exam, granser, …)
    exChat: {},                // per-uppgift-chattfält {nummer: text}
    exMsg: '',                 // kvitto (PDF skapad m.m.)
    exTyp: 'prov',             // prov | arbetsblad (Fas 5)
    exCcOpen: {},              // ihopfällbara innehållsgrupper {rubrik: true/false}; osatt = auto
    exDeleteArm: false,        // raderingsknappen är i bekräftelseläge
    exReferensId: '',          // referensläge: utgå från tidigare prov
    exRefOpen: false,          // referens-popovern (custom dropdown) är öppen
    exRefClosing: false,       // popovern spelar sin stängningsanimation
    exHistorik: [],            // kursens prov/arbetsblad (historik + referensval)
  };

  /* instance (non-state) fields */
  var _t, _finishT, _chat, _au, _toastIv, _toastT2, _glideRAF, _progRAF, _disp, _lastStart, _runToken = 0;
  var _fltTimer = null, _scanTimer = null, _askRun = 0, _askZoomT = null, _descT = null;
  var _wbZoomT = null;
  var _dl = {}, _inst = {}, _editBuf = {}, _wave = null;
  var _file, _seek, _searchRef, _scrollRef, _procScroll, _media, _clientFile;
  var _rec = null, _recChunks = [], _recStream = null, _recTimer = null;
  var _recMarkers = [], _recMarkersByPath = {};   // live-markörer under inspelning
  var _doneHids = [];                             // history-id:n från körningens klara filer (auto-extraktion)
  var _recSession = null, _recUploadChain = null; // inkrementell flush till disk
  var _recAudioCtx = null, _recAnalyser = null, _recLevelTimer = null, _recSilenceSecs = 0;
  var _prevTab, _prevStep, _wasEditing, _wasOpen, _scrollKey, _wasModal;

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
  // Korrekturpasset (Gemma 3n mot ljudet) körs i serverns pipeline och tar
  // 60–90 %-bandet av progressen när ljudmodellen finns — då visas det som ett
  // eget steg. Utan korrektur äger transkriberingen 0–90 % som förut.
  function willCorrect() { return !!(S.audioCorrect && S.audioModelInstalled); }
  function stageNames() {
    return willCorrect()
      ? ['Förbereder', 'Extraherar ljud', 'Transkriberar', 'Korrekturläser', 'Färdigställer']
      : ['Förbereder', 'Extraherar ljud', 'Transkriberar', 'Färdigställer'];
  }
  function stageBounds() { return willCorrect() ? [0, 12, 28, 60, 92, 100] : [0, 12, 28, 92, 100]; }
  var AUDIO_DUR = 150;
  var ALLOWED = ['mp4', 'mkv', 'mov', 'webm', 'avi', 'm4v', 'mp3', 'wav', 'm4a', 'flac', 'aac', 'ogg', 'opus', 'wma'];
  /* -------------------------------------------------------------- helpers -- */
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  // Render a search snippet: escape first (XSS-safe), then turn the backend's
  // \x02..\x03 match markers into highlighted <mark> spans.
  function hl(s) { return esc(s).replace(/\x02/g, '<mark style="background:var(--accent-weak);color:var(--accent);border-radius:3px;padding:0 2px">').replace(/\x03/g, '</mark>'); }

  // ---- Rikt chatt-svar: Markdown + LaTeX-liknande matematik -----------------
  // Offline utan build → egen lätt renderare (KaTeX-fonterna går inte att bunta).
  // Täcker det en lektionschatt ger: fetstil/kursiv/kod/listor/stycken + matte i
  // $…$ / $$…$$ (exponent, index, bråk, rot, grekiska, operatorer). All text
  // escapas först — modellens svar renderas aldrig som rå HTML.
  var _GREEK = { alpha:'α',beta:'β',gamma:'γ',delta:'δ',epsilon:'ε',varepsilon:'ε',zeta:'ζ',eta:'η',theta:'θ',vartheta:'ϑ',iota:'ι',kappa:'κ',lambda:'λ',mu:'μ',nu:'ν',xi:'ξ',pi:'π',rho:'ρ',sigma:'σ',tau:'τ',upsilon:'υ',phi:'φ',varphi:'φ',chi:'χ',psi:'ψ',omega:'ω',Gamma:'Γ',Delta:'Δ',Theta:'Θ',Lambda:'Λ',Xi:'Ξ',Pi:'Π',Sigma:'Σ',Phi:'Φ',Psi:'Ψ',Omega:'Ω' };
  var _MSYM = { cdot:'·',times:'×',div:'÷',pm:'±',mp:'∓',leq:'≤',le:'≤',geq:'≥',ge:'≥',neq:'≠',ne:'≠',approx:'≈',equiv:'≡',sim:'∼',cong:'≅',propto:'∝',to:'→',rightarrow:'→',Rightarrow:'⇒',leftarrow:'←',Leftarrow:'⇐',leftrightarrow:'↔',infty:'∞',partial:'∂',nabla:'∇',sum:'∑',prod:'∏',int:'∫',oint:'∮',angle:'∠',perp:'⊥',parallel:'∥',in:'∈',notin:'∉',forall:'∀',exists:'∃',emptyset:'∅',cup:'∪',cap:'∩',subset:'⊂',subseteq:'⊆',supset:'⊃',supseteq:'⊇',ldots:'…',cdots:'⋯',dots:'…',circ:'∘',degree:'°',deg:'°',prime:'′',ast:'∗',star:'⋆',land:'∧',lor:'∨',neg:'¬' };
  var _MFUN = { sin:1,cos:1,tan:1,cot:1,sec:1,csc:1,arcsin:1,arccos:1,arctan:1,sinh:1,cosh:1,tanh:1,log:1,ln:1,lg:1,exp:1,lim:1,max:1,min:1,det:1,gcd:1,mod:1,dim:1 };

  function _mGroup(s, i) {
    if (s.charAt(i) === '{') {
      var d = 1, j = i + 1;
      while (j < s.length && d > 0) { var ch = s.charAt(j); if (ch === '{') d++; else if (ch === '}') d--; j++; }
      return { body: s.slice(i + 1, j - 1), next: j };
    }
    var m = /^\\[a-zA-Z]+|^\\.|^[\s\S]/.exec(s.slice(i));
    var tok = m ? m[0] : (s.charAt(i) || '');
    return { body: tok, next: i + tok.length };
  }
  function _math(s) {
    var out = '', i = 0, n = s.length;
    while (i < n) {
      var c = s.charAt(i);
      if (c === '\\') {
        var mm = /^\\([a-zA-Z]+)|^\\([\s\S])/.exec(s.slice(i));
        var name = mm ? (mm[1] || mm[2]) : '';
        var adv = mm ? mm[0].length : 1;
        var after = i + adv;
        if (name === 'frac' || name === 'dfrac' || name === 'tfrac') {
          var g1 = _mGroup(s, after), g2 = _mGroup(s, g1.next);
          out += '<span class="mfrac"><span class="mfr-n">' + _math(g1.body) + '</span><span class="mfr-d">' + _math(g2.body) + '</span></span>';
          i = g2.next; continue;
        }
        if (name === 'sqrt') {
          var k = after, root = '';
          if (s.charAt(k) === '[') { var e = s.indexOf(']', k); if (e > -1) { root = s.slice(k + 1, e); k = e + 1; } }
          var gs = _mGroup(s, k);
          out += (root ? '<sup class="mroot">' + _math(root) + '</sup>' : '') + '<span class="msqrt">√<span class="msqrt-b">' + _math(gs.body) + '</span></span>';
          i = gs.next; continue;
        }
        if (name === 'text' || name === 'mathrm' || name === 'operatorname' || name === 'mathbf') {
          var gt = _mGroup(s, after); out += '<span class="mtext">' + esc(gt.body) + '</span>'; i = gt.next; continue;
        }
        if (_MFUN[name]) { out += '<span class="mfun">' + name + '</span>'; i = after; continue; }
        if (_GREEK[name] != null) { out += _GREEK[name]; i = after; continue; }
        if (_MSYM[name] != null) { out += _MSYM[name]; i = after; continue; }
        if (name === 'sqrt') { i = after; continue; }
        if (/^(left|right|big|Big|bigg|Bigg|displaystyle|textstyle|limits|,|;|:|!|>| )$/.test(name)) { i = after; continue; }
        if (name === 'quad' || name === 'qquad') { out += '  '; i = after; continue; }
        out += esc(name); i = after; continue;
      }
      if (c === '^' || c === '_') {
        var g = _mGroup(s, i + 1);
        out += (c === '^' ? '<sup>' : '<sub>') + _math(g.body) + (c === '^' ? '</sup>' : '</sub>');
        i = g.next; continue;
      }
      if (c === '{') { var gb = _mGroup(s, i); out += _math(gb.body); i = gb.next; continue; }
      if (c === '}') { i++; continue; }
      if (/[a-zA-Z]/.test(c)) { out += '<i class="mvar">' + c + '</i>'; i++; continue; }
      out += esc(c); i++;
    }
    return out;
  }
  function renderMath(tex, display) {
    var inner; try { inner = _math(String(tex).trim()); } catch (e) { inner = esc(tex); }
    return '<span class="math' + (display ? ' math-d' : '') + '">' + inner + '</span>';
  }
  function _mdInline(s) {
    // Inline-kod hanteras i _stash (före matte), inte här — så $ inuti `kod` inte mattas.
    return s
      .replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^\w*])\*([^*\n]+?)\*(?![\w*])/g, '$1<em>$2</em>');
  }
  // Lyft ut kod och matte till platshållare (\x00N\x00) FÖRE markdown-formatering.
  // KOD stashas före matte, så dollartecken i `kod` aldrig tolkas som matte. Varje
  // post har färdig, säker HTML (.h) och sin råtext (.r). All text escapas.
  function _stash(src, store) {
    function push(h, r) { store.push({ h: h, r: r }); return '\x00' + (store.length - 1) + '\x00'; }
    return String(src == null ? '' : src)
      .replace(/`([^`\n]+)`/g, function (_m, t) { return push('<code class="md-code">' + esc(t) + '</code>', '`' + t + '`'); })
      .replace(/\$\$([\s\S]+?)\$\$/g, function (m, t) { return push(renderMath(t, true), m); })
      .replace(/\\\[([\s\S]+?)\\\]/g, function (m, t) { return push(renderMath(t, true), m); })
      .replace(/\\\(([\s\S]+?)\\\)/g, function (m, t) { return push(renderMath(t, false), m); })
      // Kräv icke-blanktecken direkt före avslutande $ så "$5 och $10" inte
      // falskt tolkas som matte ("5 och "). Äkta matte ($x^2$) slutar på ett tecken.
      .replace(/\$(?=\S)([^\n$]*?[^\s$])\$/g, function (m, t) { return push(renderMath(t, false), m); });
  }
  function _popStash(html, store) { return html.replace(/\x00(\d+)\x00/g, function (_m, k) { return (store[+k] && store[+k].h) || ''; }); }
  // Inuti kodblock: återställ matte-/kod-platshållare till sin escapade RÅTEXT
  // i stället för renderad HTML — annars hamnade matte-HTML inne i <code>.
  function _popRaw(html, store) { return html.replace(/\x00(\d+)\x00/g, function (_m, k) { return store[+k] ? esc(store[+k].r) : ''; }); }

  // Inline-läge: flödar med citat-knapparna i källförankrade svar.
  function renderRichInline(src) {
    var store = [], s = _stash(src, store);
    var html = _mdInline(esc(s)).replace(/^\s*[-*•]\s+/gm, '• ').replace(/\n{2,}/g, '<br><br>').replace(/\n/g, '<br>');
    return _popStash(html, store);
  }
  // Block-läge: fristående svarsbubbla — stycken, listor, rubriker, kod.
  function renderRich(src) {
    var store = [], s = _stash(String(src == null ? '' : src).replace(/\r/g, ''), store);
    var lines = s.split('\n'), html = '', para = [], listType = null, items = [];
    function flushPara() { if (para.length) { html += '<p class="md-p">' + _mdInline(esc(para.join(' ').trim())) + '</p>'; para = []; } }
    function flushList() { if (listType) { html += '<' + listType + ' class="md-list">' + items.map(function (it) { return '<li>' + _mdInline(esc(it)) + '</li>'; }).join('') + '</' + listType + '>'; listType = null; items = []; } }
    for (var i = 0; i < lines.length; i++) {
      var t = lines[i].trim();
      if (/^```/.test(t)) { flushPara(); flushList(); var code = []; i++; while (i < lines.length && !/^```/.test(lines[i].trim())) { code.push(lines[i]); i++; } html += '<pre class="md-pre"><code>' + _popRaw(esc(code.join('\n')), store) + '</code></pre>'; continue; }
      var h = /^(#{1,4})\s+(.*)$/.exec(t);
      if (h) { flushPara(); flushList(); html += '<div class="md-h">' + _mdInline(esc(h[2])) + '</div>'; continue; }
      var ul = /^[-*•]\s+(.*)$/.exec(t), ol = /^\d+[.)]\s+(.*)$/.exec(t);
      if (ul) { flushPara(); if (listType && listType !== 'ul') flushList(); listType = 'ul'; items.push(ul[1]); continue; }
      if (ol) { flushPara(); if (listType && listType !== 'ol') flushList(); listType = 'ol'; items.push(ol[1]); continue; }
      if (t === '') { flushPara(); flushList(); continue; }
      flushList(); para.push(t);
    }
    flushPara(); flushList();
    return _popStash(html, store);
  }
  function fmtStorage(g) { return g >= 1000 ? (g / 1024).toFixed(1).replace('.', ',') + ' TB' : g + ' GB'; }
  function fmtTime(s) { var m = Math.floor(s / 60), r = Math.floor(s % 60); return (m < 10 ? '0' : '') + m + ':' + (r < 10 ? '0' : '') + r; }
  function parseTS(t) { var p = (t || '00:00').split(':').map(Number); return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1]; }
  function baseNameOf(name) { var s = (name || 'transkript').trim(); s = s.split(/[\\/]/).pop(); if (s.indexOf('youtu') !== -1) s = 'youtube_klipp'; return s.replace(/\.[^.]+$/, '') || 'transkript'; }
  function baseName() { return baseNameOf(S.source); }
  function extOf(n) { var m = /\.([^.]+)$/.exec(n || ''); return m ? m[1].toLowerCase() : ''; }
  function isMedia(n) { return ALLOWED.indexOf(extOf(n)) !== -1; }
  // Videoförhandsvisning på korten: bara riktiga videofiler får en thumbnail.
  // (history-postens `video` sätts även för ljud — den är den spelbara median —
  // och webm är appens ljudinspelningsformat, så det räknas som ljud här.)
  var VIDEO_EXT = { mp4: 1, m4v: 1, mkv: 1, mov: 1, avi: 1, mpg: 1, mpeg: 1, wmv: 1, flv: 1, ts: 1, mts: 1 };
  function _videoThumb(h) {
    var v = h && h.video;
    if (!v || !v.path) return null;
    var ext = (v.ext || extOf(v.name || '')).toLowerCase();
    return VIDEO_EXT[ext] ? '/api/thumb?path=' + encodeURIComponent(v.path) : null;
  }
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
    // Pick the BEST installed match (highest score), not the first in catalog
    // order — otherwise sv would resolve to kb-whisper-tiny over kb-whisper-large.
    var pick = function (pred) {
      var best = null;
      WHISPER.forEach(function (x) {
        if (inst[x.id] && pred(x) && (!best || (x.score || 0) > (best.score || 0))) best = x;
      });
      return best ? best.id : null;
    };
    // No cross-language fallback: never auto-select a Swedish-only model for English
    // (or vice versa). Return '' when no language-appropriate model is installed so the
    // UI prompts for a download instead of silently transcribing with the wrong model.
    if (l === 'en') return pick(function (m) { return m.lang === 'en'; }) || pick(function (m) { return m.lang === 'multi'; }) || '';
    return pick(function (m) { return m.lang === 'sv'; }) || pick(function (m) { return m.lang === 'multi'; }) || '';
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
        barStyle: 'height:100%;width:100%;transform-origin:left;transform:scaleX(' + (pct / 100) + ');background:' + col + ';border-radius:99px;transition:transform .3s ease,background .3s ease' };
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
  function rowStyle(last) { return 'display:flex;align-items:center;gap:13px;padding:15px 18px;' + (last ? '' : 'border-bottom:1px solid var(--line);'); }
  function rowStyleRich(last) { return 'display:flex;align-items:flex-start;gap:14px;padding:17px 18px;' + (last ? '' : 'border-bottom:1px solid var(--line);'); }
  function verdictPill(tier) { var c = tier === 'ok' ? 'var(--ok)' : tier === 'warn' ? 'var(--warn)' : 'var(--bad)'; return 'display:inline-flex;align-items:center;font-size:12.5px;font-weight:500;color:' + c + ';background:color-mix(in srgb,' + c + ' 13%,transparent);border-radius:6px;padding:3px 9px;white-space:nowrap;font-variant-numeric:tabular-nums'; }
  function chipStyle() { return "display:inline-flex;align-items:center;gap:5px;font-size:12.5px;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);border-radius:7px;padding:3px 9px;font-variant-numeric:tabular-nums;white-space:nowrap"; }
  function quantChipStyle() { return "display:inline-flex;align-items:center;gap:5px;font-size:12.5px;font-weight:600;color:var(--accent);background:var(--accent-weak);border:1px solid color-mix(in srgb,var(--accent) 24%,transparent);border-radius:7px;padding:3px 9px;font-variant-numeric:tabular-nums;cursor:help"; }
  function infoBadgeStyle() { return "display:inline-flex;align-items:center;justify-content:center;width:17px;height:17px;border-radius:50%;font-size:12px;font-weight:700;color:var(--ink);background:var(--sunken);border:1px solid var(--line);cursor:help;flex:0 0 auto"; }
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
  function setTab(t) {
    // Historik + Lektioner är sammanslagna till Inspelningar (design).
    if (t === 'history' || t === 'lessons') t = 'recordings';
    setState({ tab: t, openDD: null });
    if (t === 'recordings') { loadHistory(); loadLessons(); loadOrg(); loadPrep(); loadAgenda(); loadTrends(); }
    if (t === 'planning') { loadOrg(); loadArkiv(); }   // formulär + arkiv
  }
  /* ------------------------------------------------- Planering (Fas 0) -- */
  // Tavlan renderas av whiteboard-motorn (vendrad från designprojektet
  // Whiteboardtavla) i en EGEN iframe: motorns styles.css äger body-nivån i
  // sitt dokument och får inte läcka in i appens UI, och iframen är samtidigt
  // containern som morphdom aldrig diffar (jfr audio-elementet — motorn äger
  // sin egen DOM). Innehållet i Fas 0 är en hårdkodad exempellektion.
  var WB_EXAMPLE_TITLE = 'Pythagoras sats';
  var WB_EXAMPLE = { boards: [
    { // vänster tavla (smal, 900×780) — teori
      width: 900, height: 780,
      padding: { top: 30, right: 30, bottom: 30, left: 40 },
      chrome: 'aluminium', tray: true,
      name: 'exempel-vanster',
      sections: [
        { kind: 'heading', text: 'Pythagoras sats', size: 34,
          underline: { color: 'red', amplitude: 2, thickness: 3, reserve: 14 },
          gapAfter: 18 },
        { kind: 'text', text: 'I en rätvinklig triangel:', size: 22, gapAfter: 8 },
        { kind: 'math', latex: 'a^2 + b^2 = c^2', size: 30, color: 'blue', gapAfter: 18 },
        { kind: 'text', text: 'där', size: 20, gapAfter: 4 },
        { kind: 'list', bullet: '–', size: 19, gap: 4, indent: 22, items: [
          'a, b = kateter (sidorna vid räta vinkeln)',
          'c = hypotenusa (motsatt räta vinkeln)',
        ], gapAfter: 18 },
        { kind: 'shape', type: 'right-triangle', width: 260, height: 180,
          labels: { left: 'a', bottom: 'b', right: 'c', inside: 'v' }, gapAfter: 14 },
        { kind: 'callout', color: 'red', fillOpacity: 0.06, padding: 12, children: [
          { kind: 'text', text: 'Kom ihåg:', size: 18, color: 'red', gapAfter: 4 },
          { kind: 'text', text: 'Gäller BARA för rätvinkliga trianglar.', size: 18, color: 'red' },
        ]},
      ],
    },
    { // höger tavla (bred, 1800×780) — två exempel i kolumner
      width: 1800, height: 780,
      padding: { top: 30, right: 30, bottom: 30, left: 30 },
      chrome: 'aluminium', tray: true,
      name: 'exempel-hoger',
      columns: [
        { weight: 1, sections: [
          { kind: 'heading', text: 'Exempel 1', size: 28, underline: { color: 'blue' }, gapAfter: 14 },
          { kind: 'text', text: 'Beräkna hypotenusan c om a = 3 och b = 4.', size: 20, gapAfter: 12 },
          { kind: 'math', latex: 'c^2 = 3^2 + 4^2', size: 22, gapAfter: 6 },
          { kind: 'math', latex: 'c^2 = 9 + 16 = 25', size: 22, gapAfter: 6 },
          { kind: 'math', latex: 'c = \\sqrt{25} = 5', size: 24, color: 'green', gapAfter: 18 },
          { kind: 'shape', type: 'right-triangle', width: 220, height: 170,
            labels: { left: 'a = 3', bottom: 'b = 4', right: 'c = 5' } },
        ]},
        { weight: 1, sections: [
          { kind: 'heading', text: 'Exempel 2', size: 28, underline: { color: 'blue' }, gapAfter: 14 },
          { kind: 'text', text: 'En stege på 5 m lutar mot en vägg. Foten är 2 m från väggen. Hur högt når stegen?', size: 19, gapAfter: 12 },
          { kind: 'math', latex: 'h^2 + 2^2 = 5^2', size: 22, gapAfter: 6 },
          { kind: 'math', latex: 'h^2 = 25 - 4 = 21', size: 22, gapAfter: 6 },
          { kind: 'math', latex: 'h = \\sqrt{21} \\approx 4{,}58 \\text{ m}', size: 22, color: 'green', gapAfter: 14 },
          { kind: 'callout', color: 'blue', fillOpacity: 0.06, padding: 10, children: [
            { kind: 'text', text: 'Svar: stegen når ca 4,58 m upp.', size: 18, color: 'blue' },
          ]},
        ]},
      ],
    },
  ]};

  var _wbFrame = null;
  var _wbReportRounds = 0;    // klientsidans tak på render-report-loopen
  function wbTitle() {
    return (S.planBoard && S.planBoard.title) || WB_EXAMPLE_TITLE;
  }
  function wbFrameRef(el) {
    _wbFrame = el;
    if (!el || el._wired) return;
    el._wired = true;
    el.addEventListener('load', renderCurrentBoard);
    // morphdom kan ge oss en redan laddad nod tillbaka (fliken lämnas/öppnas)
    if (el.contentWindow && el.contentWindow.WBHost) renderCurrentBoard();
  }
  // Renderar den genererade tavlan om en finns, annars exempellektionen.
  // Efter rendering rapporteras motorns [WB]-varningar till servern
  // (render-report) som kan köra en reparationsrunda — andra försvarslinjen
  // i specen. Klienten tar max 2 rapportrundor; servern håller den delade
  // rundbudgeten (max 3 LLM-rundor totalt).
  function renderCurrentBoard() {
    var win = _wbFrame && _wbFrame.contentWindow;
    if (!win || !win.WBHost) return;
    var spec = S.planBoard ? { boards: S.planBoard.boards } : WB_EXAMPLE;
    win.WBHost.render(spec).then(function (res) {
      var warnings = (res && res.warnings) || [];
      setState({ wbRendered: true, wbWarnings: warnings });
      if (S.planId && warnings.length && _wbReportRounds < 2 && S.planPhase !== 'running') {
        _wbReportRounds += 1;
        reportRenderWarnings(warnings);
      }
    }).catch(function (e) {
      setState({ wbRendered: false,
                 wbWarnings: ['Tavlan kunde inte renderas: ' + ((e && e.message) || e)] });
    });
  }
  function reportRenderWarnings(warnings) {
    setState({ planPhase: 'running',
               planLog: S.planLog.concat(['Tavlan har layoutvarningar — försöker reparera …']) });
    streamPost('/api/planning/' + S.planId + '/render-report',
               { warnings: warnings }, onPlanEvent);
  }
  function wbPrint() {
    var win = _wbFrame && _wbFrame.contentWindow;
    if (win && win.WBHost) win.WBHost.print();
  }
  // Tavelkortet förstoras till modal PÅ PLATS: iframen får aldrig flyttas i
  // DOM (reparenting laddar om dokumentet och tömmer tavlan), så wrappern
  // blir backdrop och samma kort växer via data-attribut + CSS.
  function openWbZoom() { clearTimeout(_wbZoomT); setState({ wbZoom: true, wbZoomClosing: false }); }
  function closeWbZoom() {
    if (!S.wbZoom || S.wbZoomClosing) return;
    clearTimeout(_wbZoomT);
    setState({ wbZoomClosing: true });
    _wbZoomT = setTimeout(function () { setState({ wbZoom: false, wbZoomClosing: false }); }, 340);
  }
  function wbExportPng() {
    var win = _wbFrame && _wbFrame.contentWindow;
    if (!win || !win.WBHost || S.wbExporting) return;
    // Filväljardialog (File System Access) där den finns — användaren väljer
    // själv plats på datorn. Dialogen måste öppnas direkt i klickgesten
    // (före den långsamma canvas-exporten), annars nekar webbläsaren den.
    if (window.showSaveFilePicker) {
      var namn = (wbTitle() || 'tavla').replace(/[\\/:*?"<>|]/g, '-') + '.png';
      window.showSaveFilePicker({
        suggestedName: namn,
        types: [{ description: 'PNG-bild', accept: { 'image/png': ['.png'] } }],
      }).then(function (handle) {
        setState({ wbExporting: true, wbExportMsg: '' });
        return win.WBHost.exportPng(2)
          .then(function (dataUrl) { return fetch(dataUrl); })
          .then(function (r) { return r.blob(); })
          .then(function (blob) {
            return handle.createWritable().then(function (w) {
              return w.write(blob).then(function () { return w.close(); });
            });
          })
          .then(function () {
            setState({ wbExporting: false, wbExportMsg: 'PNG sparad: ' + handle.name });
          });
      }).catch(function (e) {
        if (e && e.name === 'AbortError') { setState({ wbExporting: false, wbExportMsg: '' }); return; }
        setState({ wbExporting: false,
                   wbExportMsg: 'Kunde inte spara PNG: ' + ((e && e.message) || e) });
      });
      return;
    }
    // Fallback (äldre motor utan File System Access): spara via servern
    // under Transkriberingar/ som tidigare.
    setState({ wbExporting: true, wbExportMsg: '' });
    win.WBHost.exportPng(2).then(function (dataUrl) {
      return fetch('/api/planning/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: wbTitle(), png: dataUrl }),
      }).then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, body: j }; });
      });
    }).then(function (res) {
      if (!res.ok || res.body.error) throw new Error(res.body.error || 'Exporten misslyckades.');
      setState({ wbExporting: false, wbExportMsg: 'PNG sparad: ' + res.body.path });
    }).catch(function (e) {
      setState({ wbExporting: false,
                 wbExportMsg: 'Kunde inte spara PNG: ' + ((e && e.message) || e) });
    });
  }

  /* Generera/iterera tavlan (Fas 1) — SSE-jobb under GPU-arbitern. */
  function onPlanEvent(ev) {
    if (ev.type === 'log') {
      setState(function (s) { return { planLog: s.planLog.concat([ev.msg]) }; });
    } else if (ev.type === 'error') {
      setState(function (s) {
        return { planPhase: 'error',
                 planLog: s.planLog.concat(['Fel: ' + ev.message]) };
      });
    } else if (ev.type === 'done') {
      var r = ev.result || {};
      var patch = { planPhase: 'done', planErrors: r.errors || [] };
      if (r.id) patch.planId = r.id;
      if (r.board) patch.planBoard = r.board;
      setState(patch, function () { if (r.board) renderCurrentBoard(); });
    }
  }
  function startPlanGenerate() {
    var moment = (S.planMoment || '').trim();
    if (!moment || S.planPhase === 'running') return;
    _wbReportRounds = 0;
    setState({ planPhase: 'running', planLog: [], planErrors: [],
               planSavedPath: '', wbExportMsg: '', wbRendered: false });
    streamPost('/api/planning/generate', {
      moment: moment,
      group_id: S.planGroupId ? +S.planGroupId : null,
      course_id: S.planCourseId ? +S.planCourseId : null,
      datum: S.planDatum || null,
      starttid: S.planStarttid || null,
      underlag: S.planUnderlag ? S.planUnderlag.id : null,
    }, onPlanEvent);
  }
  function sendPlanRefine() {
    var msg = (S.planChatInput || '').trim();
    if (!msg || !S.planId || S.planPhase === 'running') return;
    _wbReportRounds = 0;
    setState({ planPhase: 'running', planChatInput: '', planLog: [],
               planErrors: [], planSavedPath: '' });
    streamPost('/api/planning/' + S.planId + '/refine', { message: msg }, onPlanEvent);
  }
  function approvePlan() {
    if (!S.planId || S.planPhase === 'running') return;
    fetch('/api/planning/' + S.planId + '/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok || res.body.error) throw new Error(res.body.error || 'Kunde inte spara.');
        setState({ planSavedPath: res.body.path });
        loadArkiv();           // planeringen syns direkt i arkivet
      })
      .catch(function (e) {
        setState({ planSavedPath: '', wbExportMsg: 'Kunde inte spara: ' + ((e && e.message) || e) });
      });
  }
  function onPlanGroup(e) { setState({ planGroupId: e.target.value }); }
  function onPlanCourse(e) { setState({ planCourseId: e.target.value }); }
  function onPlanMoment(e) { setState({ planMoment: e.target.value }); }
  // Underlag: bokssidor/uppgifter (PNG/JPG/WebP/PDF). Filerna läses som
  // data-URL:er och bildtolkas lokalt av visionsmodellen. Samma flöde
  // används av tavlan (plan*) och provet (ex*) — cb-objektet skiljer dem.
  function _pickUnderlagFiles(cb) {
    var inp = document.createElement('input');
    inp.type = 'file'; inp.multiple = true;
    inp.accept = '.png,.jpg,.jpeg,.webp,.pdf,image/png,image/jpeg,image/webp,application/pdf';
    inp.onchange = function () {
      var files = Array.prototype.slice.call(inp.files || []);
      if (!files.length) return;
      Promise.all(files.map(function (f) {
        return new Promise(function (res, rej) {
          var r = new FileReader();
          r.onload = function () { res({ namn: f.name, data: String(r.result || '') }); };
          r.onerror = rej;
          r.readAsDataURL(f);
        });
      })).then(function (filer) {
        cb.busy(true);
        streamPost('/api/planning/underlag', { filer: filer }, function (ev) {
          if (ev.type === 'log') cb.log(ev.msg);
          else if (ev.type === 'error') {
            cb.busy(false);
            setState({ toast: { title: 'Underlag', detail: ev.message || 'uppladdningen misslyckades', kind: 'error', done: false } });
            setTimeout(function () { setState({ toast: null }); }, 7000);
          } else if (ev.type === 'done') cb.done(ev.result || null);
        });
      }).catch(function () {
        cb.busy(false);
        setState({ toast: { title: 'Underlag', detail: 'kunde inte läsa filerna', kind: 'error', done: false } });
        setTimeout(function () { setState({ toast: null }); }, 7000);
      });
    };
    inp.click();
  }
  function onPickUnderlag() {
    if (S.planUnderlagBusy) return;
    _pickUnderlagFiles({
      busy: function (b) { setState({ planUnderlagBusy: b, planLog: [] }); },
      log: function (m) { setState(function (s) { return { planLog: s.planLog.concat([m]) }; }); },
      done: function (r) { setState({ planUnderlagBusy: false, planLog: [], planUnderlag: r }); },
    });
  }
  function onClearUnderlag() { setState({ planUnderlag: null }); }
  function onPickExUnderlag() {
    if (S.exUnderlagBusy) return;
    _pickUnderlagFiles({
      busy: function (b) { setState({ exUnderlagBusy: b, exLog: [] }); },
      log: function (m) { setState(function (s) { return { exLog: s.exLog.concat([m]) }; }); },
      done: function (r) { setState({ exUnderlagBusy: false, exLog: [], exUnderlag: r }); },
    });
  }
  function onClearExUnderlag() { setState({ exUnderlag: null }); }
  function onPlanMomentKey(e) { if (e.key === 'Enter') startPlanGenerate(); }
  function onPlanChatInput(e) { setState({ planChatInput: e.target.value }); }
  function onPlanChatKey(e) { if (e.key === 'Enter') sendPlanRefine(); }
  function onPlanDatum(e) { setState({ planDatum: e.target.value }); }
  function onPlanStarttid(e) { setState({ planStarttid: e.target.value }); }

  /* --------------------------------- planeringsarkivet (ersätter kalendern) --
     Tavlor + prov/arbetsblad i veckogrupper, med fritextsök och LLM-frågor
     över arkivet — samma RAG-mönster som Inspelningar-arkivet, men inga
     kalenderhändelser skapas härifrån. */
  var _arkRun = 0, _arkScanTimer = null;

  function loadArkiv() {
    getJSON('/api/planning/archive')
      .then(function (r) { setState({ arkItems: (r && r.items) || [] }); })
      .catch(function () {});
  }
  function onArkInput(e) { setState({ arkQ: e.target.value }); }
  function setArkMode(mode) { setState({ arkMode: mode }); }
  function clearArkiv() {
    _arkRun++;
    if (_arkScanTimer) { clearInterval(_arkScanTimer); _arkScanTimer = null; }
    setState({ arkQ: '', arkHits: null, arkSearching: false, arkAsking: false,
               arkAnswer: '', arkSources: null, arkQAsked: '', arkScanPlan: null,
               arkScanRes: {}, arkScanShown: 0, arkDeep: null,
               arkFollowups: [], arkFollowInput: '' });
  }
  function runArkiv() {
    var q = (S.arkQ || '').trim();
    if (!q) { setState({ arkHits: null }); return; }
    if (S.arkMode === 'ask') { runArkivAsk(q); return; }
    setState({ arkSearching: true, arkAnswer: '', arkSources: null });
    getJSON('/api/planning/archive/search?q=' + encodeURIComponent(q))
      .then(function (r) { setState({ arkHits: (r && r.hits) || [], arkSearching: false }); })
      .catch(function () { setState({ arkHits: [], arkSearching: false }); });
  }
  function runArkivAsk(q) {
    var run = ++_arkRun;
    // Samma äkta live-progression som kartoteket: backend berättar vad som
    // genomsöks och vad som träffar; utrullningen pacas i startScanReveal.
    if (_arkScanTimer) { clearInterval(_arkScanTimer); _arkScanTimer = null; }
    setState({ arkAsking: true, arkAnswer: '', arkSources: null, arkHits: null,
               arkQAsked: q, arkScanPlan: null, arkScanRes: {}, arkScanShown: 0,
               arkDeep: null, arkFollowups: [], arkFollowInput: '' });
    streamPost('/api/planning/ask', { q: q }, function (ev) {
      if (run !== _arkRun) return;             // en nyare fråga har tagit över
      if (ev.type === 'scan_plan') {
        if (_arkScanTimer) clearInterval(_arkScanTimer);
        _arkScanTimer = startScanReveal((ev.items || []).length, 'arkScanShown', 'arkAsking');
        setState({ arkScanPlan: ev.items || [] });
      } else if (ev.type === 'scan_result') {
        setState(function (s) {
          var m = Object.assign({}, s.arkScanRes); m[ev.key] = ev.hits;
          return { arkScanRes: m };
        });
      } else if (ev.type === 'deep_read') {
        setState({ arkDeep: ev.sources || [] });
      } else if (ev.type === 'token') {
        setState(function (s) { return { arkAnswer: s.arkAnswer + ev.text }; });
      } else if (ev.type === 'done') {
        if (_arkScanTimer) { clearInterval(_arkScanTimer); _arkScanTimer = null; }
        setState({ arkAsking: false, arkScanShown: 9999,
                   arkSources: (ev.result && ev.result.sources) || [] });
      } else if (ev.type === 'error') {
        if (_arkScanTimer) { clearInterval(_arkScanTimer); _arkScanTimer = null; }
        setState({ arkAsking: false,
                   arkAnswer: 'Kunde inte söka: ' + (ev.message || 'okänt fel') });
      }
    });
  }
  function sendArkivFollow() {
    var q = (S.arkFollowInput || '').trim();
    if (!q || S.arkAsking) return;
    var run = ++_arkRun;
    setState(function (s) {
      return { arkFollowInput: '',
               arkFollowups: (s.arkFollowups || []).concat([{ q: q, a: '', typing: true }]) };
    });
    streamPost('/api/planning/ask', { q: q }, function (ev) {
      if (run !== _arkRun) return;
      var patchLast = function (fn) {
        setState(function (s) {
          var fs = (s.arkFollowups || []).slice(); if (!fs.length) return null;
          fs[fs.length - 1] = fn(Object.assign({}, fs[fs.length - 1]));
          return { arkFollowups: fs };
        });
      };
      if (ev.type === 'token') patchLast(function (f) { f.a += ev.text; return f; });
      else if (ev.type === 'done') patchLast(function (f) { f.typing = false; return f; });
      else if (ev.type === 'error') patchLast(function (f) { f.typing = false; f.a = f.a || ('Kunde inte söka: ' + (ev.message || 'okänt fel')); return f; });
    });
  }
  // Öppna en arkivpost: tavlan laddas i läsläge i tavelkortet ovanför;
  // prov/arbetsblad öppnas i provkortet — man ser exakt vad den innehåller.
  function openArkivItem(it) {
    if (it.typ === 'tavla') {
      fetch('/api/planning/' + it.id)
        .then(function (r) { return r.json(); })
        .then(function (p) {
          if (p && p.board) {
            setState({ planBoard: p.board, planId: null, planErrors: [],
                       planSavedPath: '', wbExportMsg: '', wbRendered: false },
                     renderCurrentBoard);
            try { window.scrollTo({ top: 0, behavior: 'smooth' }); } catch (e) {}
          }
        })
        .catch(function () {});
    } else {
      // Toggle: klick på posten som redan är öppen stänger kortet i stället
      // för att tyst ladda om samma innehåll (kändes som ett dött klick).
      if (S.exam && String(S.exam.id) === String(it.id)) { closeExam(); return; }
      getJSON('/api/exams/' + it.id).then(function (r) {
        if (r && r.id) setState({ exam: r, exErrors: r.errors || [], exChat: {}, exMsg: '', exDeleteArm: false }, scrollToExamCard);
      }).catch(function () {});
    }
  }
  function closeExam() {
    setState({ exam: null, exErrors: [], exChat: {}, exMsg: '', exDeleteArm: false });
  }
  // Radering i två steg: första klicket armar en inline-bekräftelse i kortet
  // (ingen modal), andra klicket raderar permanent — post, versioner och filer.
  function armDeleteExam() { setState({ exDeleteArm: true }); }
  function cancelDeleteExam() { setState({ exDeleteArm: false }); }
  function deleteExam() {
    var id = S.exam && S.exam.id;
    if (!id) return;
    fetch('/api/exams/' + id, { method: 'DELETE' })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (res.ok && res.j && res.j.ok) {
          setState({ exam: null, exErrors: [], exChat: {}, exMsg: '', exDeleteArm: false });
          loadArkiv();
          loadExamHistorik();
        } else {
          setState({ exMsg: 'Kunde inte radera: ' + ((res.j && res.j.error) || 'okänt fel'), exDeleteArm: false });
        }
      })
      .catch(function () { setState({ exMsg: 'Kunde inte radera — försök igen.', exDeleteArm: false }); });
  }
  function scrollToExamCard() {
    try {
      var el = document.querySelector('[data-key="exam-card"]');
      if (!el) return;
      var still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      el.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'start' });
    } catch (e) {}
  }
  /* ------------------------------------------------ provgeneratorn (Fas 4) -- */
  function loadExamContent() {
    if (!S.exCourseId) { setState({ exContent: [], exPunkter: {} }); return; }
    var q = '/api/exams/content-status?course_id=' + S.exCourseId +
            (S.exGroupId ? '&group_id=' + S.exGroupId : '');
    getJSON(q).then(function (r) {
      setState({ exContent: (r && r.punkter) || [], exPunkter: {} });
    }).catch(function () {});
  }
  function loadExamHistorik() {
    if (!S.exCourseId) { setState({ exHistorik: [], exReferensId: '' }); return; }
    getJSON('/api/exams?course_id=' + S.exCourseId).then(function (r) {
      setState({ exHistorik: (r && r.exams) || [], exReferensId: '' });
    }).catch(function () {});
  }
  // Chips och segment i stället för native selects (samma vokabulär som tavlan):
  // klick väljer, klick på vald kurs/klass avmarkerar.
  function exPickCourse(id) {
    setState(function (s) {
      return { exCourseId: String(s.exCourseId) === String(id) ? '' : String(id) };
    }, function () { loadExamContent(); loadExamHistorik(); });
  }
  function exPickGroup(id) {
    setState(function (s) {
      return { exGroupId: String(s.exGroupId) === String(id) ? '' : String(id) };
    }, loadExamContent);
  }
  function exPickTyp(t) { setState({ exTyp: t }); }
  // Delade kurschips för provet (samma formspråk som tavlans planCourseGroups):
  // kompakta nivåetiketter grupperade per ämne, klick på vald avmarkerar.
  function courseChipGroups(selId, pick) {
    var groups = [], byAmne = {};
    S.courses.forEach(function (c) {
      var chip = { namn: c.namn, kort: c.niva_kort || c.namn,
                   sel: String(c.id) === String(selId),
                   onPick: function () { pick(c.id); } };
      var amne = c.amne_namn || 'Övrigt';
      if (!(amne in byAmne)) { byAmne[amne] = { amne: amne, chips: [] }; groups.push(byAmne[amne]); }
      byAmne[amne].chips.push(chip);
    });
    return groups;
  }
  // Referensprovet är en riktig meny — custom popover med mjuk hover-stängning,
  // samma mönster som kartotekets filterpopovers.
  var _exRefTimer = null;
  function exToggleRef() {
    if (_exRefTimer) clearTimeout(_exRefTimer);
    setState(function (s) { return { exRefOpen: !s.exRefOpen, exRefClosing: false }; });
  }
  function exSoftCloseRef() {
    if (!S.exRefOpen) return;
    if (_exRefTimer) clearTimeout(_exRefTimer);
    _exRefTimer = setTimeout(function () {
      setState({ exRefClosing: true });
      _exRefTimer = setTimeout(function () { setState({ exRefOpen: false, exRefClosing: false }); }, 190);
    }, 300);
  }
  function exCancelCloseRef() {
    if (_exRefTimer) clearTimeout(_exRefTimer);
    if (S.exRefClosing) setState({ exRefClosing: false });
  }
  function exPickRef(id) {
    if (_exRefTimer) clearTimeout(_exRefTimer);
    setState({ exReferensId: String(id), exRefOpen: false, exRefClosing: false });
  }
  function exToggleGrupp(rubrik) {
    setState(function (s) {
      var o = Object.assign({}, s.exCcOpen);
      // Osatt = auto (öppen om gruppen har val); toggla utifrån visat läge.
      var shownOpen = (rubrik in o) ? !!o[rubrik]
        : s.exContent.some(function (p) { return (p.rubrik || 'Övrigt') === rubrik && s.exPunkter[p.id]; });
      o[rubrik] = !shownOpen;
      return { exCcOpen: o };
    });
  }
  function exTogglePunkt(id) {
    setState(function (s) {
      var p = Object.assign({}, s.exPunkter);
      if (p[id]) delete p[id]; else p[id] = true;
      return { exPunkter: p };
    });
  }
  function onExAntal(e) { setState({ exAntal: e.target.value }); }
  function onExTid(e) { setState({ exTid: e.target.value }); }
  function onExDatum(e) { setState({ exDatum: e.target.value }); }
  function onExDelar() { setState(function (s) { return { exDelar: !s.exDelar }; }); }
  function onExamEvent(ev) {
    if (ev.type === 'log') {
      setState(function (s) { return { exLog: s.exLog.concat([ev.msg]) }; });
    } else if (ev.type === 'error') {
      setState(function (s) {
        return { exPhase: 'error', exLog: s.exLog.concat(['Fel: ' + ev.message]) };
      });
    } else if (ev.type === 'done') {
      var r = ev.result || {};
      var patch = { exPhase: 'done', exErrors: r.errors || [] };
      if (r.id) { patch.exam = r; patch.exChat = {}; }
      if (r.pdf) patch.exMsg = 'PDF skapad: ' + r.pdf;
      else if (r.tex && r.status === 'godkänt') patch.exMsg = 'Sparad utan PDF: ' + r.tex;
      setState(patch);
      loadArkiv();
      loadExamHistorik();      // historiken + prövad-markörerna uppdateras
      loadExamContent();
    }
  }
  function startExamGenerate() {
    if (!S.exCourseId || S.exPhase === 'running') return;
    setState({ exPhase: 'running', exLog: [], exErrors: [], exMsg: '' });
    streamPost('/api/exams/generate', {
      course_id: +S.exCourseId,
      group_id: S.exGroupId ? +S.exGroupId : null,
      punkter: Object.keys(S.exPunkter).map(Number),
      antal: +S.exAntal || 8,
      tid_min: +S.exTid || 120,
      delar: S.exDelar,
      datum: S.exDatum || null,
      typ: S.exTyp,
      referens_exam_id: S.exReferensId ? +S.exReferensId : null,
      underlag: S.exUnderlag ? S.exUnderlag.id : null,
    }, onExamEvent);
  }
  function onExChat(nummer) {
    return function (e) {
      setState(function (s) {
        var c = Object.assign({}, s.exChat); c[nummer] = e.target.value;
        return { exChat: c };
      });
    };
  }
  function sendExamRefine(nummer) {
    return function () {
      var msg = (S.exChat[nummer] || '').trim();
      if (!msg || !S.exam || S.exPhase === 'running') return;
      setState({ exPhase: 'running', exLog: [], exErrors: [], exMsg: '' });
      streamPost('/api/exams/' + S.exam.id + '/refine',
                 { message: msg, nummer: nummer }, onExamEvent);
    };
  }
  function approveExam() {
    if (!S.exam || S.exPhase === 'running') return;
    setState({ exPhase: 'running', exLog: [], exErrors: [], exMsg: '' });
    streamPost('/api/exams/' + S.exam.id + '/approve', {}, onExamEvent);
  }
  function openExamPdf() { if (S.exam) window.open('/api/exams/' + S.exam.id + '/pdf', '_blank'); }
  function openExamTex() { if (S.exam) window.open('/api/exams/' + S.exam.id + '/tex', '_blank'); }
  // "Öppna i Overleaf" — uttryckligt tillval (Overleafs docs-gateway tar emot
  // en POST med källan; prov innehåller ingen elevdata). Aldrig huvudvägen.
  function openInOverleaf() {
    if (!S.exam) return;
    fetch('/api/exams/' + S.exam.id + '/tex')
      .then(function (r) { if (!r.ok) throw new Error('ingen .tex ännu — godkänn provet först'); return r.text(); })
      .then(function (tex) {
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = 'https://www.overleaf.com/docs';
        form.target = '_blank';
        var field = document.createElement('textarea');
        field.name = 'snip';
        field.value = tex;
        form.appendChild(field);
        document.body.appendChild(form);
        form.submit();
        form.remove();
      })
      .catch(function (e) { setState({ exMsg: 'Overleaf: ' + ((e && e.message) || e) }); });
  }
  // Spegling av mallens numrering (Del B, C, D, del-lösa) så "uppgift N"
  // i chatt/refine pekar på samma uppgift som på pappersprovet.
  function examNumbered(exam) {
    var order = ['B', 'C', 'D', null];
    var out = [];
    var nummer = 0;
    order.forEach(function (del) {
      (exam.uppgifter || []).forEach(function (u, idx) {
        if ((u.del || null) !== del) return;
        nummer += 1;
        out.push({ nummer: nummer, idx: idx, u: u });
      });
    });
    return out;
  }

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
  /* ----------------------------------------------- inbyggd inspelning (Fas 4) -- */
  function recSupported() { return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder); }
  function recStamp() {
    var d = new Date(); function p(n) { return (n < 10 ? '0' : '') + n; }
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + '_' + p(d.getHours()) + p(d.getMinutes());
  }
  function _stopStream() { if (_recStream) { try { _recStream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {} _recStream = null; } }
  function _stopLevelMeter() {
    clearInterval(_recLevelTimer); _recLevelTimer = null; _recSilenceSecs = 0;
    if (_recAudioCtx) { try { _recAudioCtx.close(); } catch (e) {} _recAudioCtx = null; }
    _recAnalyser = null;
  }
  function _startLevelMeter(stream) {
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      _recAudioCtx = new AC();
      var src = _recAudioCtx.createMediaStreamSource(stream);
      _recAnalyser = _recAudioCtx.createAnalyser();
      _recAnalyser.fftSize = 1024;
      src.connect(_recAnalyser);
      var buf = new Uint8Array(_recAnalyser.fftSize);
      _recLevelTimer = setInterval(function () {
        if (!_recAnalyser) return;
        _recAnalyser.getByteTimeDomainData(buf);
        var sum = 0;
        for (var i = 0; i < buf.length; i++) { var d = (buf[i] - 128) / 128; sum += d * d; }
        var rms = Math.sqrt(sum / buf.length);            // 0..~1
        var level = Math.min(1, rms * 4);
        if (level < 0.02) { _recSilenceSecs += 0.2; } else { _recSilenceSecs = 0; }
        setState({ recLevel: level, recSilent: _recSilenceSecs > 4 });
      }, 200);
    } catch (e) { /* nivåmätaren är bonus — fortsätt utan den */ }
  }
  // Ladda upp en inspelad bit direkt till disk (krasch-säkert), i ordning.
  function _appendChunk(blob) {
    _recUploadChain = (_recUploadChain || Promise.resolve()).then(function () {
      return fetch('/api/recording/append?session=' + encodeURIComponent(_recSession), {
        method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: blob
      }).then(function (r) { if (!r.ok) { return r.json().then(function (j) { setState({ recError: (j && j.error) || 'Kunde inte spara inspelningen.' }); }); } })
        .catch(function () { /* nästa bit försöker igen; .part behåller det som hann skrivas */ });
    });
    return _recUploadChain;
  }
  function startRecording() {
    if (!recSupported()) { setState({ recError: 'Inspelning stöds inte i den här vyn.' }); return; }
    setState({ recError: '', fileError: '' });
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      _recStream = stream; _recChunks = [];
      _recSession = 'rec_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
      _recUploadChain = Promise.resolve();
      var prefer = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
      var mt = (window.MediaRecorder && MediaRecorder.isTypeSupported)
        ? prefer.filter(function (t) { return MediaRecorder.isTypeSupported(t); })[0] : null;
      _rec = mt ? new MediaRecorder(stream, { mimeType: mt }) : new MediaRecorder(stream);
      // Flush each chunk straight to disk so a crash mid-lesson is recoverable.
      _rec.ondataavailable = function (e) { if (e.data && e.data.size) _appendChunk(e.data); };
      _rec.onstop = function () { finishRecording(_rec ? _rec.mimeType : ''); };
      _rec.start(4000);                                   // timeslice → periodisk flush
      _recMarkers = [];
      _startLevelMeter(stream);
      setState({ recording: true, recElapsed: 0, recMarkerCount: 0, recLevel: 0, recSilent: false });
      clearInterval(_recTimer);
      _recTimer = setInterval(function () { setState(function (s) { return { recElapsed: s.recElapsed + 1 }; }); }, 1000);
    }).catch(function () {
      setState({ recError: 'Kunde inte komma åt mikrofonen. Tillåt mikrofon och försök igen.' });
    });
  }
  function stopRecording() {
    clearInterval(_recTimer); _stopLevelMeter();
    try { if (_rec && _rec.state !== 'inactive') _rec.stop(); } catch (e) {}
    setState({ recording: false, recLevel: 0, recSilent: false });   // finishRecording runs on 'stop'
  }
  function cancelRecording() {
    clearInterval(_recTimer); _stopLevelMeter(); _recChunks = []; _recMarkers = [];
    try { if (_rec && _rec.state !== 'inactive') { _rec.onstop = null; _rec.stop(); } } catch (e) {}
    _stopStream();
    var session = _recSession; _recSession = null;
    if (session) { fetch('/api/recording/discard?session=' + encodeURIComponent(session), { method: 'POST' }).catch(function () {}); }
    setState({ recording: false, recElapsed: 0, recError: '', recMarkerCount: 0, recLevel: 0, recSilent: false });
  }
  // Markera ett viktigt ögonblick live — hittas igen utan talarseparation.
  function addRecMarker() {
    if (!S.recording) return;
    _recMarkers.push({ t: S.recElapsed });
    setState({ recMarkerCount: _recMarkers.length });
  }
  function finishRecording(mime) {
    _stopStream(); _stopLevelMeter();
    var session = _recSession; _recSession = null;
    if (!session) { setState({ recElapsed: 0 }); return; }
    var type = (mime && mime.indexOf('audio') === 0) ? mime : 'audio/webm';
    var ext = type.indexOf('ogg') !== -1 ? 'ogg'
      : type.indexOf('mp4') !== -1 ? 'm4a'
      : type.indexOf('mpeg') !== -1 ? 'mp3'
      : type.indexOf('wav') !== -1 ? 'wav' : 'webm';
    var name = 'lektion_' + recStamp() + '.' + ext;
    var markers = _recMarkers; _recMarkers = [];
    // Wait for every flushed chunk to land, THEN finalise the .part on disk.
    (_recUploadChain || Promise.resolve()).then(function () {
      return fetch('/api/recording/finish?session=' + encodeURIComponent(session) + '&name=' + encodeURIComponent(name), { method: 'POST' });
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res && res.path) {
        if (markers.length) { _recMarkersByPath[res.path] = markers; }
        addFilesObjs([{ name: res.name || name, path: res.path }]);
        setState({ recElapsed: 0, recMarkerCount: 0 });
      } else { setState({ recError: (res && res.error) || 'Kunde inte slutföra inspelningen.' }); }
    }).catch(function () { setState({ recError: 'Kunde inte slutföra inspelningen.' }); });
  }
  /* ------------------------------- återställ oavslutad inspelning (krasch) -- */
  function loadIncompleteRecs() {
    return getJSON('/api/recordings/incomplete')
      .then(function (l) { setState({ incompleteRecs: Array.isArray(l) ? l : [] }); })
      .catch(function () { setState({ incompleteRecs: [] }); });
  }
  function recoverIncomplete(session) {
    var name = 'återställd_' + session + '.webm';
    fetch('/api/recording/finish?session=' + encodeURIComponent(session) + '&name=' + encodeURIComponent(name), { method: 'POST' })
      .then(function (r) { return r.json(); }).then(function (res) {
        if (res && res.path) { addFilesObjs([{ name: res.name || name, path: res.path }]); }
        loadIncompleteRecs();
      }).catch(function () {});
  }
  function discardIncomplete(session) {
    fetch('/api/recording/discard?session=' + encodeURIComponent(session), { method: 'POST' })
      .then(function () { loadIncompleteRecs(); }).catch(function () {});
  }

  function restart() {
    clearInterval(_t); clearTimeout(_finishT); clearTimeout(_chat); clearInterval(_au);
    Object.values(_dl || {}).forEach(clearInterval);
    setState({ source: '', queue: [], qStatus: {}, qProgress: {}, activeId: null, fileError: '', step: 'source', run: 'idle', progress: 0, elapsed: 0, log: [], openDD: null, transcriptOpen: false, runError: null, editing: false, edits: {}, edited: false, audioPlaying: false, audioT: 0, audioDur: 0, mediaUrl: null, runMedia: null, histViewing: null, resultId: null, transcriptRaw: null, logExpand: false });
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
      else if (ev.type === 'error') {
        // Surface the failure — annars ser det ut som att knappen inte gör något.
        // Gemma 3n är gated: 401 utan accepterad licens + HF_TOKEN.
        setState({ audioModelDownloading: false,
                   toast: { title: 'Kunde inte ladda ner ljudmodellen', name: '', detail: ev.message || '', kind: 'error' } });
      }
    });
  }
  // Qwen3 "thinking": off by default (fast, no English chain-of-thought leak); on only
  // for hard multi-step chat questions. Correction/summary never think.
  // Bygger renderbara chatt-meddelanden (bubblor + källförankrade citat/källpanel).
  // Delas av resultatvyns "Fråga om lektionen" och per-lektion-chattmodalen.
  function buildChatMessages(messages, segs, citeSel, onCite, typing, reasonOpen, onToggleReason) {
    return messages.map(function (m, mi) {
      var cited = (m.role !== 'user' && m.text) ? parseChatCites(m.text, segs) : null;
      return {
        text: m.text, isUser: m.role === 'user', hasAttach: !!m.attach, attach: m.attach || '',
        reason: m.reason || '', hasReason: !!(m.reason && m.reason.length),
        // Öppen medan svaret strömmar (tänker-känslan); hopfälld när det är klart.
        // Ett klick vinner alltid över default.
        reasonIsOpen: (reasonOpen && (mi in reasonOpen)) ? !!reasonOpen[mi] : (!!typing && mi === messages.length - 1),
        onToggleReason: function (e) { if (e) e.stopPropagation(); if (onToggleReason) onToggleReason(mi); },
        rowStyle: 'display:flex;flex-direction:column;gap:5px;align-items:' + (m.role === 'user' ? 'flex-end' : 'flex-start'),
        bubbleStyle: m.role === 'user' ? 'max-width:82%;background:var(--accent-weak);color:var(--ink);border:1px solid color-mix(in srgb,var(--accent) 25%,transparent);border-radius:15px 15px 4px 15px;padding:11px 15px;font-size:15.5px;line-height:1.5' : 'max-width:82%;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:15px 15px 15px 4px;padding:11px 15px;font-size:15.5px;line-height:1.5',
        attachStyle: 'display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);border-radius:8px;padding:4px 9px;font-variant-numeric:tabular-nums',
        reasonStyle: 'max-width:82%;background:var(--sunken);border:1px dashed var(--line-2);color:var(--ink-2);border-radius:13px;padding:9px 13px;font-size:13px;line-height:1.5;white-space:pre-wrap',
        hasCites: !!cited,
        tokens: cited ? cited.tokens.map(function (tk) {
          if (tk.cite === undefined) return { isText: true, text: tk.text };
          return { isCite: true, num: tk.cite, supFlag: citeSel === (mi + ':' + tk.segIdx) ? 'on' : 'off', onCite: function () { onCite(mi, tk.segIdx); } };
        }) : [],
      };
    });
  }
  // Parsar citatmarkörer i ett assistentsvar till klickbara citat. Numren pekar på
  // segmenten som skickades till modellen (1-baserat); visningsnumren räknas om
  // per meddelande i citeringsordning. Utöver [n] hanteras intervall och listor —
  // [1–3], [1-3], [1, 2] och [1–2, 5] — eftersom modellen ofta skriver så trots
  // instruktionen. Ogiltiga markörer lämnas kvar som text.
  function parseChatCites(text, segs) {
    var tokens = [], refs = [], seen = {};
    var re = /\[(\d{1,3}(?:\s*[,–—-]\s*\d{1,3})*)\]/g, last = 0, m;
    while ((m = re.exec(text))) {
      var nums = [], ok = true;
      var parts = m[1].split(/\s*,\s*/);
      for (var pi = 0; pi < parts.length; pi++) {
        var rm = parts[pi].match(/^(\d{1,3})\s*[–—-]\s*(\d{1,3})$/);
        if (rm) {
          var a = parseInt(rm[1], 10), b = parseInt(rm[2], 10);
          if (!(a >= 1 && b >= a && b <= segs.length && b - a <= 30)) { ok = false; break; }
          for (var x = a; x <= b; x++) { if (nums.indexOf(x) < 0) nums.push(x); }
        } else if (/^\d{1,3}$/.test(parts[pi])) {
          var n = parseInt(parts[pi], 10);
          if (!(n >= 1 && n <= segs.length)) { ok = false; break; }
          if (nums.indexOf(n) < 0) nums.push(n);
        } else { ok = false; break; }
      }
      if (!ok || !nums.length) continue;
      var before = text.slice(last, m.index);
      if (before) tokens.push({ text: before });
      for (var ni = 0; ni < nums.length; ni++) {
        var segIdx = nums[ni] - 1;
        if (!(segIdx in seen)) {
          seen[segIdx] = refs.length + 1;
          refs.push({ num: refs.length + 1, segIdx: segIdx, time: segs[segIdx].time || '', text: segs[segIdx].text || '' });
        }
        tokens.push({ cite: seen[segIdx], segIdx: segIdx });
      }
      last = m.index + m[0].length;
    }
    if (!refs.length) return null;
    var rest = text.slice(last);
    if (rest) tokens.push({ text: rest });
    return { tokens: tokens, refs: refs };
  }
  function stopProp(e) { e.stopPropagation(); }
  function toggleModelDD() { setState(function (s) { return { openDD: s.openDD === 'model' ? null : 'model' }; }); }
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
    } else if (c.kind === 'lesson') {
      setState({ confirm: null });
      deleteLesson(c.id);
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
      markers: [],
    });
    loadMarkers(h.id);
  }
  /* ----------------------------------------- markörer i transkriptvyn -- */
  function loadMarkers(historyId) {
    if (!historyId) { setState({ markers: [] }); return; }
    getJSON('/api/recordings/' + encodeURIComponent(historyId) + '/markers')
      .then(function (m) { setState({ markers: Array.isArray(m) ? m : [] }); })
      .catch(function () { setState({ markers: [] }); });
  }
  function seekToTime(t) {
    if (hasMedia()) { _media.currentTime = t; setState({ audioT: t }); _media.play().catch(function () {}); }
    else { setState({ audioT: t }); }
  }
  function addPlaybackMarker() {
    var id = S.resultId; if (!id) return;
    fetch('/api/recordings/' + encodeURIComponent(id) + '/markers', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ markers: [{ t: S.audioT || 0 }] })
    }).then(function () { loadMarkers(id); }).catch(function () {});
  }
  function deleteMarker(markerId) {
    fetch('/api/markers/' + encodeURIComponent(markerId), { method: 'DELETE' })
      .then(function () { loadMarkers(S.resultId); }).catch(function () {});
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

  /* ----------------------------------------------------------- lessons (Fas 1) -- */
  function lessonQuery() {
    var p = [];
    if (S.lessonFilterGroup) p.push('group_id=' + encodeURIComponent(S.lessonFilterGroup));
    if (S.lessonFilterCourse) p.push('course_id=' + encodeURIComponent(S.lessonFilterCourse));
    return p.length ? '?' + p.join('&') : '';
  }
  function loadLessons() {
    return getJSON('/api/lessons' + lessonQuery())
      .then(function (l) { if (Array.isArray(l)) setState({ lessons: l }); }).catch(function () {});
  }
  function loadOrg() {
    return Promise.all([getJSON('/api/groups'), getJSON('/api/courses')])
      .then(function (r) {
        setState({ groups: Array.isArray(r[0]) ? r[0] : [], courses: Array.isArray(r[1]) ? r[1] : [] });
      }).catch(function () {});
  }
  function setLessonFilter(which, val) {
    var patch = {}; patch[which] = val;
    setState(patch, function () { loadLessons(); loadPrep(); loadTrends(); });
  }
  function setMonthFilter(val) { setState({ lessonFilterMonth: val }); }   // klientsidan, ingen omladdning
  function clearLessonFilters() {
    setState({ lessonFilterGroup: '', lessonFilterCourse: '', lessonFilterMonth: '' },
      function () { loadLessons(); loadPrep(); loadTrends(); });
  }
  function loadPrep() {
    if (!S.lessonFilterGroup) { setState({ nextPrep: null }); return Promise.resolve(); }
    return getJSON('/api/next-prep?group_id=' + encodeURIComponent(S.lessonFilterGroup))
      .then(function (p) { setState({ nextPrep: p && p.group_id ? p : null }); })
      .catch(function () { setState({ nextPrep: null }); });
  }
  function loadTrends() {
    if (!S.lessonFilterGroup) { setState({ trends: null }); return Promise.resolve(); }
    return getJSON('/api/trends?group_id=' + encodeURIComponent(S.lessonFilterGroup))
      .then(function (t) { setState({ trends: t && t.group_id ? t : null }); })
      .catch(function () { setState({ trends: null }); });
  }
  function markPrepDone(insightId) {
    fetch('/api/insights/' + encodeURIComponent(insightId), {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'klar' })
    }).then(function () { loadPrep(); }).catch(function () {});
  }
  function startEditLesson(l) {
    setState({ editingLesson: l.id, lessonEdits: { name: l.name || '(namnlös)', group: l.group || '', course: l.course || '', sal: l.sal || '', datum: l.datum || '' } });
  }
  function cancelEditLesson() { setState({ editingLesson: null, lessonEdits: {} }); }
  function onLessonField(field, val) {
    setState(function (s) { var e = Object.assign({}, s.lessonEdits); e[field] = val; return { lessonEdits: e }; });
  }
  function saveLesson(id) {
    var e = S.lessonEdits || {};
    fetch('/api/lessons/' + encodeURIComponent(id), {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group_name: e.group || '', course_name: e.course || '', sal: e.sal || '', datum: e.datum || '' })
    }).then(function () {
      setState({ editingLesson: null, lessonEdits: {} }, function () { loadLessons(); loadOrg(); });
    }).catch(function () { setState({ editingLesson: null, lessonEdits: {} }); });
  }
  function openLesson(l) {
    var h = S.history.find(function (x) { return x.id === l.history_id; });
    if (h) { openHistory(h); return; }
    if (l.history_id) {
      getJSON('/api/history/' + encodeURIComponent(l.history_id)).then(function (hit) {
        if (hit && hit.id) { setState(function (s) { return { history: s.history.concat([hit]) }; }); openHistory(hit); }
      }).catch(function () {});
    }
  }
  function askDeleteLesson(id, name) {
    setState({ confirm: { kind: 'lesson', id: id, title: 'Ta bort lektionen?', body: '"' + name + '" tas bort ur lektionsdatabasen och historiken. Filer du redan sparat på disken påverkas inte.', label: 'Ta bort', danger: true } });
  }
  function deleteLesson(id) {
    fetch('/api/lessons/' + encodeURIComponent(id), { method: 'DELETE' })
      .then(function () { loadLessons(); loadHistory(); loadPrep(); }).catch(function () {});
  }

  /* ------------------------------------------ fritextsök över alla lektioner -- */
  function setSearchMode(mode) {
    if (mode === 'keyword') { clearSearch(); setState({ searchMode: 'keyword' }); }
    else setState({ searchMode: 'ask', searchHits: null, lessonSearch: '' });
  }
  function onSearchInput(e) {
    var val = e.target.value;
    // Sök ord-läget filtrerar kartoteket live (FLIP); Fråga-läget skriver bara fältet.
    if (S.searchMode === 'keyword') flipRecGrid(function () { setState({ lessonSearch: val }); });
    else setState({ lessonSearch: val });
  }
  function clearSearch() {
    _askRun++;                                   // ogiltigförklara ev. pågående ask-ström
    if (_scanTimer) { clearInterval(_scanTimer); _scanTimer = null; }
    clearTimeout(_askZoomT);
    setState({ lessonSearch: '', searchHits: null, askAnswer: '', askSources: null, askQ: '', asking: false, askScanPlan: null, askScanRes: {}, askScanShown: 0, askDeep: null, askZoom: false, askZoomClosing: false, srcBox: true, askFollowups: [], askFollowInput: '', askEvent: null });
  }
  function runSearch() {
    var q = (S.lessonSearch || '').trim();
    if (!q) { setState({ searchHits: null }); return; }
    if (S.searchMode === 'ask') { runAsk(q); return; }
    setState({ searching: true, askAnswer: '', askSources: null });
    getJSON('/api/search?q=' + encodeURIComponent(q))
      .then(function (r) { setState({ searchHits: (r && r.hits) || [], searching: false }); })
      .catch(function () { setState({ searchHits: [], searching: false }); });
  }
  // Utrullningstakt för skanningskorten: backend skickar hela den äkta
  // träffbilden på millisekunder, men avslöjandet pacas (~60–150 ms/kort,
  // tak ~3,5 s) så progressionen går att följa med ögat. Datat är äkta —
  // bara takten är styrd. Delas av kartoteket och planeringsarkivet.
  function startScanReveal(planLen, shownKey, isLiveKey) {
    var step = Math.max(60, Math.min(150, Math.round(3500 / Math.max(1, planLen))));
    var t = setInterval(function () {
      setState(function (s) {
        if (!s[isLiveKey] || s[shownKey] >= planLen) { clearInterval(t); return null; }
        var patch = {}; patch[shownKey] = s[shownKey] + 1; return patch;
      });
    }, step);
    return t;
  }
  function runAsk(q) {
    var run = ++_askRun;
    if (_scanTimer) { clearInterval(_scanTimer); _scanTimer = null; }
    setState({ asking: true, askAnswer: '', askSources: null, searchHits: null, askQ: q, askScanPlan: null, askScanRes: {}, askScanShown: 0, askDeep: null, askZoom: false, askZoomClosing: false, srcBox: true, askFollowups: [], askFollowInput: '', askEvent: null });
    // Inget förhandsbyggt kalenderförslag på nyckelord — förslag skapas bara
    // uttryckligen via kalenderknappen och godkänns alltid innan de läggs in.
    streamPost('/api/search/ask', { q: q }, function (ev) {
      if (run !== _askRun) return;               // en nyare fråga (eller Esc) har tagit över
      if (ev.type === 'scan_plan') {             // äkta genomsökningsordning från backend
        if (_scanTimer) clearInterval(_scanTimer);
        _scanTimer = startScanReveal((ev.items || []).length, 'askScanShown', 'asking');
        setState({ askScanPlan: ev.items || [] });
      } else if (ev.type === 'scan_result') {    // verkligt träffantal per inspelning
        setState(function (s) {
          var m = Object.assign({}, s.askScanRes); m[ev.key] = ev.hits;
          return { askScanRes: m };
        });
      } else if (ev.type === 'deep_read') {      // källorna AI:n faktiskt läser
        setState({ askDeep: ev.sources || [] });
      } else if (ev.type === 'token') {
        setState(function (s) { return { askAnswer: s.askAnswer + ev.text }; });
      } else if (ev.type === 'done') {
        if (_scanTimer) { clearInterval(_scanTimer); _scanTimer = null; }
        setState({ asking: false, askScanShown: 9999, askSources: (ev.result && ev.result.sources) || [] });
      } else if (ev.type === 'error') {
        // Frys utrullningen där den står — felraden tar över berättelsen.
        if (_scanTimer) { clearInterval(_scanTimer); _scanTimer = null; }
        setState({ asking: false, askAnswer: 'Kunde inte söka: ' + (ev.message || 'okänt fel') });
      }
    });
  }
  function openSearchHit(hit) { openLesson({ id: hit.lesson_id, history_id: hit.history_id }); }

  // ---- Arkivsvaret (design 14 juli): zoom till modal, hopfällbar källpanel,
  // följdfrågor som verkliga RAG-omfrågor mot /api/search/ask. ----------------
  function openAskZoom() { clearTimeout(_askZoomT); setState({ askZoom: true, askZoomClosing: false }); }
  function closeAskZoom() {
    if (!S.askZoom || S.askZoomClosing) return;
    clearTimeout(_askZoomT);
    setState({ askZoomClosing: true });
    _askZoomT = setTimeout(function () { setState({ askZoom: false, askZoomClosing: false }); }, 380);
  }
  function toggleSrcBox() { setState(function (s) { return { srcBox: !s.srcBox }; }); }
  function scrollAskChat(smooth) {
    try {
      var sc = document.querySelector('[data-askscroll]');
      if (sc) { if (smooth) sc.scrollTo({ top: sc.scrollHeight, behavior: 'smooth' }); else sc.scrollTop = sc.scrollHeight; }
    } catch (e) {}
  }
  function sendAskFollow() {
    var q = (S.askFollowInput || '').trim();
    if (!q || S.asking) return;
    // Kommandon ("flytta till onsdag 14:30" …) justerar ett BEFINTLIGT förslag
    // med regex-tolken; nya förslag skapas bara via kalenderknappen.
    var evNow = S.askEvent;
    var isCal = evNow && !evNow.added && (/flytta|ändra|byt|boka|döp|kalla|titel|anteckning/i.test(q) || /\d{1,2}[:.]\d{2}/.test(q) || /måndag|tisdag|onsdag|torsdag|fredag|lördag|söndag|imorgon|nästa vecka|klockan/i.test(q));
    if (isCal) {
      var r0 = applyEventCommand(evNow, q);
      setState(function (s) {
        if (!s.askEvent) return null;
        return { askFollowInput: '',
                 askEvent: Object.assign({}, s.askEvent, r0.patch),
                 askFollowups: (s.askFollowups || []).concat([{ q: q, a: r0.reply, typing: false }]) };
      }, function () { scrollAskChat(true); });
      return;
    }
    var run = ++_askRun;
    setState(function (s) { return { askFollowInput: '', askFollowups: (s.askFollowups || []).concat([{ q: q, a: '', typing: true }]) }; },
      function () { scrollAskChat(true); });
    streamPost('/api/search/ask', { q: q }, function (ev) {
      if (run !== _askRun) return;               // en nyare fråga (eller Esc) har tagit över
      var patchLast = function (fn) {
        setState(function (s) {
          var fs = (s.askFollowups || []).slice(); if (!fs.length) return null;
          fs[fs.length - 1] = fn(Object.assign({}, fs[fs.length - 1]));
          return { askFollowups: fs };
        }, function () { scrollAskChat(false); });
      };
      if (ev.type === 'token') patchLast(function (f) { f.a += ev.text; return f; });
      else if (ev.type === 'done') patchLast(function (f) { f.typing = false; return f; });
      else if (ev.type === 'error') patchLast(function (f) { f.typing = false; f.a = f.a || ('Kunde inte söka: ' + (ev.message || 'okänt fel')); return f; });
    });
  }

  /* ---- Kartoteket: kurs-färgchips, veckogrupper, filterpopovers, FLIP ---- */
  var CC_KEYS = ['sky', 'sage', 'plum', 'mustard'];
  // Stabil färg per kurs (mallen mappar fasta kursnamn; appens kurser är fria,
  // så färgen härleds deterministiskt ur namnet i stället).
  function ccOf(l) {
    if (!l || (!l.group && !l.course)) return 'none';
    var s2 = String(l.course || l.group), h = 0;
    for (var i = 0; i < s2.length; i++) h = (h * 31 + s2.charCodeAt(i)) >>> 0;
    return CC_KEYS[h % CC_KEYS.length];
  }
  var _MON_SV = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];
  function weekInfo(datum) {
    var d = new Date((datum || '') + 'T12:00:00');
    if (isNaN(d.getTime())) return { key: 'x', label: 'Tidigare', num: '·', range: '', start: 0 };
    var day = (d.getDay() + 6) % 7;
    var mon = new Date(d); mon.setDate(d.getDate() - day);
    var fri = new Date(mon); fri.setDate(mon.getDate() + 4);
    // ISO-veckonummer (torsdagsregeln)
    var t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    var dn = (t.getUTCDay() + 6) % 7;
    t.setUTCDate(t.getUTCDate() - dn + 3);
    var ft = new Date(Date.UTC(t.getUTCFullYear(), 0, 4));
    var wk = 1 + Math.round(((t - ft) / 86400000 - 3 + ((ft.getUTCDay() + 6) % 7)) / 7);
    var fmt = function (x) { return x.getDate() + ' ' + _MON_SV[x.getMonth()]; };
    return { key: 'v' + wk + '-' + mon.getFullYear(), label: 'Vecka ' + wk, num: String(wk),
             range: fmt(mon) + ' – ' + fmt(fri), start: mon.getTime() };
  }
  function toggleFilter(w) {
    if (_fltTimer) clearTimeout(_fltTimer);
    setState(function (s) { return { filterOpen: s.filterOpen === w ? null : w, filterClosing: false }; });
  }
  // Mjuk stängning vid mouseleave — kort grace-period så menyn inte hinner
  // försvinna på vägen ner till den (mallens softCloseFilter).
  function softCloseFilter() {
    if (!S.filterOpen) return;
    if (_fltTimer) clearTimeout(_fltTimer);
    _fltTimer = setTimeout(function () {
      setState({ filterClosing: true });
      _fltTimer = setTimeout(function () { setState({ filterOpen: null, filterClosing: false }); }, 190);
    }, 300);
  }
  function cancelCloseFilter() {
    if (_fltTimer) clearTimeout(_fltTimer);
    if (S.filterClosing) setState({ filterClosing: false });
  }
  function pickFilter(which, val) {
    if (_fltTimer) clearTimeout(_fltTimer);
    setState({ filterOpen: null, filterClosing: false });
    if (which === 'datum') flipRecGrid(function () { setMonthFilter(val); });
    else setLessonFilter(which === 'klass' ? 'lessonFilterGroup' : 'lessonFilterCourse', val);
  }
  // FLIP-animation: kort glider mjukt till nya positioner, nya tonas in,
  // bortsorterade tonas ut (klientsidiga filter: datum + Sök ord-läget).
  function flipRecGrid(apply) {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) { apply(); return; }
    var els = Array.prototype.slice.call(document.querySelectorAll('[data-rec-id]'));
    if (!els.length || !els[0].animate) { apply(); return; }
    var old = new Map();
    els.forEach(function (el) { old.set(el.getAttribute('data-rec-id'), { r: el.getBoundingClientRect(), clone: el.cloneNode(true) }); });
    apply();
    // pendingCbs körs direkt efter morphdom — mät de nya positionerna där.
    setState(null, function () {
      var seen = {};
      document.querySelectorAll('[data-rec-id]').forEach(function (el) {
        var id = el.getAttribute('data-rec-id'); seen[id] = true;
        var o = old.get(id); var nr = el.getBoundingClientRect();
        if (o) {
          var dx = o.r.left - nr.left, dy = o.r.top - nr.top;
          if (Math.abs(dx) > 1 || Math.abs(dy) > 1) el.animate([{ transform: 'translate(' + dx + 'px,' + dy + 'px)' }, { transform: 'translate(0,0)' }], { duration: 460, easing: 'cubic-bezier(.22,1,.36,1)' });
        } else {
          el.animate([{ opacity: 0, transform: 'translateY(16px) scale(.96)' }, { opacity: 1, transform: 'none' }], { duration: 400, easing: 'cubic-bezier(.22,1,.36,1)' });
        }
      });
      old.forEach(function (o, id) {
        if (seen[id]) return;
        var c = o.clone;
        c.removeAttribute('data-rec-id');
        c.style.position = 'fixed'; c.style.left = o.r.left + 'px'; c.style.top = o.r.top + 'px';
        c.style.width = o.r.width + 'px'; c.style.height = o.r.height + 'px';
        c.style.margin = '0'; c.style.boxSizing = 'border-box'; c.style.pointerEvents = 'none'; c.style.zIndex = '5';
        document.body.appendChild(c);
        var a = c.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(12px) scale(.95)' }], { duration: 240, easing: 'ease-out' });
        a.onfinish = function () { c.remove(); };
        setTimeout(function () { if (c.parentNode) c.remove(); }, 450);
      });
    });
  }

  /* --------------------------------- säkerhetskopiering + lektionsrapport -- */
  function _openContainingFolder(path) {
    var dir = String(path || '').replace(/[\/\\][^\/\\]*$/, '');
    if (dir) fetch('/api/open', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: dir }) }).catch(function () {});
  }
  function backupNow() {
    setState({ backingUp: true });
    fetch('/api/backup', { method: 'POST' }).then(function (r) { return r.json(); }).then(function (res) {
      setState({ backingUp: false });
      if (res && res.path) {
        _openContainingFolder(res.path);
        setState({ toast: { title: 'Säkerhetskopia skapad', name: (res.files || []).length + ' filer', done: true } });
        clearTimeout(_toastT2); _toastT2 = setTimeout(function () { setState({ toast: null }); }, 3200);
      }
    }).catch(function () { setState({ backingUp: false }); });
  }

  /* ----------------------------------- agenda: daterade poster tvärs klasser -- */
  function loadAgenda() {
    return getJSON('/api/agenda')
      .then(function (a) { setState({ agenda: Array.isArray(a) ? a : [] }); })
      .catch(function () { setState({ agenda: [] }); });
  }
  function toggleAgenda() { setState(function (s) { return { agendaOpen: !s.agendaOpen }; }); }
  function markAgendaDone(insightId) {
    fetch('/api/insights/' + encodeURIComponent(insightId), {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'klar' })
    }).then(function () { loadAgenda(); loadPrep(); }).catch(function () {});
  }
  function exportAgendaIcs() {
    setState({ agendaExporting: true });
    fetch('/api/agenda/ics', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        setState({ agendaExporting: false });
        if (res && res.path) {
          fetch('/api/open', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: res.path }) }).catch(function () {});
          setState({ toast: { title: 'Kalenderfil sparad', name: (res.count || 0) + ' poster', done: true } });
          clearTimeout(_toastT2); _toastT2 = setTimeout(function () { setState({ toast: null }); }, 3200);
        }
      })
      .catch(function () { setState({ agendaExporting: false }); });
  }

  var TYP_LABEL = { kalender: 'Kalender', 'svårighet': 'Svårighet', 'åtgärd': 'Åtgärd', grupprum: 'Grupprum', material: 'Material', 'övrigt': 'Övrigt' };

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
  function seekAbs(t) {
    var d = curDur();
    var clamped = Math.max(0, Math.min(d, t));
    if (hasMedia()) { _media.currentTime = clamped; }
    setState({ audioT: clamped });
  }
  function onSeekKey(e) {
    var k = e.key, d = curDur(), cur = S.audioT || 0;
    if (k === 'ArrowRight' || k === 'ArrowUp') { e.preventDefault(); seekAbs(cur + 5); }
    else if (k === 'ArrowLeft' || k === 'ArrowDown') { e.preventDefault(); seekAbs(cur - 5); }
    else if (k === 'PageUp') { e.preventDefault(); seekAbs(cur + 30); }
    else if (k === 'PageDown') { e.preventDefault(); seekAbs(cur - 30); }
    else if (k === 'Home') { e.preventDefault(); seekAbs(0); }
    else if (k === 'End') { e.preventDefault(); seekAbs(d); }
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
      keys.forEach(function (k) { var v = buf[k]; var base = (getTranscript()[k] || {}).text; if (v != null && v.trim() !== base) { edits[k] = v.trim(); changed = true; } else { if (edits[k] != null) changed = true; delete edits[k]; } });
      return { edits: edits, edited: s.edited || changed };
    });
    _editBuf = {};
  }
  // BACKEND: start()/_runActive() simulate transcription; replace with /api/transcribe SSE (streamPost).
  function start() {
    if (S.run === 'running') return;
    if (!S.queue.length) return;
    // Modellkatalogen (/api/models) inte klar än — vänta hellre än att skicka
    // det stale prototyp-id:t som servern avvisar med 400.
    if (!S.catalogReady) return;
    // Modellerna är förinstallerade; om ingen är vald (ovanligt) blockera bara start.
    if (!S.model) { return; }
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
    clearInterval(_t); clearTimeout(_finishT);
    var active = S.queue.find(function (q) { return q.id === S.activeId; });
    if (!active) return;
    var token = ++_runToken;
    var src = baseNameOf(active.name);
    setState({
      run: 'running', step: 'process', progress: 0, dispProgress: 0, elapsed: 0,
      runError: null, transcript: null, resultFilesReal: null,
      source: active.name,
      qStatus: Object.assign({}, S.qStatus, kv(active.id, 'running')),
      log: ['› transkribera "' + src + '" --model ' + modelLabel(S.model), '[00:00] Startar transkribering …'],
    });
    _startProgress();   // mjuk, kontinuerligt framåtrörelse tills 'done'
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
        // Never show 100% until the 'done' event — 100% must mean actually finished,
        // not "Whisper done, still assembling". Server already scales transcription to
        // 0-90 and nudges 93/98 through the finishing phase; clamp as a safety net.
        if (ev.type === 'progress') { setState({ progress: Math.min(ev.pct || 0, 99) }); }
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
          if (r.id) _doneHids.push(r.id);   // kom ihåg körningen till auto-extraktionen
          // Attach any live markers captured while recording this file.
          var marks = _recMarkersByPath[active.path];
          if (marks && marks.length && r.id) {
            fetch('/api/recordings/' + encodeURIComponent(r.id) + '/markers', {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ markers: marks })
            }).catch(function () {});
            delete _recMarkersByPath[active.path];
          }
          var next = _nextPending(active.id);
          if (next) { setTimeout(function () { setState({ run: 'idle', activeId: next, source: qName(S.queue, next), audioT: 0 }, function () { _runActive(); }); }, 800); }
          else { setTimeout(function () { afterDone(); }, 450); }
        }
      });
  }
  function cancelRun() {
    _runToken++; clearInterval(_t); clearTimeout(_finishT);
    // Faktiskt avbryta jobbet på servern (avslutar subprocessen och frigör GPU:n),
    // inte bara sluta lyssna på strömmen.
    fetch('/api/transcribe/cancel', { method: 'POST' }).catch(function () {});
    setState(function (s) { return { run: 'cancelled', qStatus: Object.assign({}, s.qStatus, kv(s.activeId, 'pending')) }; });
  }
  function resumeRun() { setState({ run: 'idle' }); _runActive(); }
  function retryRun() { setState({ run: 'idle', runError: null, progress: 0, dispProgress: 0, elapsed: 0 }); _runActive(); }

  // ---- Live, kontinuerligt framåtrörelse för progressbaren ------------------
  // Servern rapporterar framsteg i glesa hopp (och inte alls under t.ex. en
  // URL-nedladdning). Här animeras ett visningsvärde (_disp) med requestAnimation-
  // Frame: det glider mjukt fram mot serverns värde och "läcker" långsamt framåt
  // inom det aktiva steget mellan händelser så baren/procenten aldrig fryser.
  // Monotont — det backar aldrig och når 100 % först vid 'done'.
  // Fasgränserna för stegen (Förbereder…Färdigställer) kommer från stageBounds()
  // — samma indelning driver progress-rAF:en och stegvyn.
  function _progFrame() {
    _progRAF = 0;
    var run = S.run;
    if (run !== 'running' && run !== 'done') return;           // avbruten/fel/idle → stoppa
    var real = Math.max(0, Math.min(100, S.progress || 0));
    if (run === 'done') {
      _disp += (100 - _disp) * 0.16;                            // glid sista biten upp till 100
      if (_disp > 99.8) _disp = 100;
    } else {
      var B = stageBounds();
      var ph = 0; while (ph < B.length - 2 && real >= B[ph + 1]) ph++;
      var ceil = B[ph + 1] - 0.5;                               // stanna inom aktuellt steg
      if (real > _disp) _disp += (Math.min(real, 99) - _disp) * 0.12;   // hinn ikapp servern
      else if (_disp < ceil) _disp += (ceil - _disp) * 0.012;           // långsam framåtläckage
      if (_disp > 99) _disp = 99;
    }
    if (Math.round(_disp) !== Math.round(S.dispProgress || 0)) setState({ dispProgress: _disp });
    if (run === 'running' || (run === 'done' && _disp < 100)) _progRAF = requestAnimationFrame(_progFrame);
    else if (run === 'done' && S.dispProgress !== 100) setState({ dispProgress: 100 });
  }
  function _startProgress() { _disp = S.dispProgress || 0; if (!_progRAF) _progRAF = requestAnimationFrame(_progFrame); }

  function toggleLogExpand() { setState(function (s) { return { logExpand: !s.logExpand }; }); }

  // Fire-and-forget (design 14 juli): korrekturen körs i serverns pipeline, så
  // när sista filen är klar visas en kort "Klart"-rad och sedan öppnas
  // Inspelningar där lektionen redan ligger sparad. Wizarden nollställs.
  function afterDone() {
    clearTimeout(_finishT);
    _finishT = setTimeout(finishTranscribe, 1600);
  }
  function finishTranscribe() {
    _finishT = null;
    var n = S.queue.filter(function (q) { return S.qStatus[q.id] === 'done'; }).length;
    var corrected = willCorrect();
    restart();
    setTab('recordings');
    clearInterval(_toastIv); clearTimeout(_toastT2);
    setState({ toast: { title: n > 1 ? (n + ' filer transkriberade') : (corrected ? 'Transkriberad och korrekturläst' : 'Transkriberad'), name: n > 1 ? 'Sparade i Inspelningar' : 'Sparad i Inspelningar', done: true } });
    _toastT2 = setTimeout(function () { setState({ toast: null }); }, 4200);
    var hids = _doneHids.slice(); _doneHids = [];
    autoExtractLessons(hids);
  }

  // Auto-extraktion (bakgrundsprocess): när hela kön är klar analyseras varje ny
  // lektion med den lokala modellen — kalenderposter, åtgärder och svårigheter
  // matas in i Kommande/Inför nästa lektion/Terminstrender utan någon knapp.
  // Körs EFTER kön (aldrig parallellt med Whisper — GPU-arbitern serialiserar),
  // en lektion i taget, och tyst: paneler fylls på när de är klara.
  function autoExtractLessons(hids) {
    if (!hids.length) return;
    getJSON('/api/lessons').then(function (lessons) {
      if (!Array.isArray(lessons)) return;
      var lids = lessons.filter(function (l) { return l.history_id && hids.indexOf(l.history_id) !== -1; })
                        .map(function (l) { return l.id; });
      var next = function () {
        var lid = lids.shift();
        if (lid == null) { loadAgenda(); loadPrep(); loadTrends(); return; }
        streamPost('/api/lessons/' + encodeURIComponent(lid) + '/extract', {}, function (ev) {
          if (ev.type === 'done' || ev.type === 'error') next();
        });
      };
      next();
    }).catch(function () {});
  }

  // ---- Lektionsoverlay (fullskärm): transkript + samma källförankrade chatt
  // men mot EN lektions transkript, isolerat från resultatvyns chatt. ---------
  function openLessonChat(l, hitT, hitQuery) {
    var hid = l.history_id || l.id;
    var lessonId = l.lesson_id != null ? l.lesson_id
      : (l.history_id && l.id !== l.history_id ? l.id : null);
    setState({ lessonChatId: hid, lessonChatName: l.name || l.namn || '(namnlös)',
               lessonChatMeta: { lessonId: lessonId,
                                 date: l.date || l.datum || '', dur: l.dur || '',
                                 model: l.model || '', lang: l.lang || '',
                                 group: l.group || '', course: l.course || '', cc: ccOf(l) },
               lessonChatHitT: hitT || null,
               lessonChatSegs: [], lessonChat: [], lessonChatInput: '',
               lessonChatTyping: false, lessonChatCiteSel: null, reasonOpen: {},
               lessonChatEvent: null, evPick: null, ovEvOpen: false });
    getJSON('/api/history/' + encodeURIComponent(hid)).then(function (h) {
      var segs = ((h && h.transcript) || []).map(function (g) { return { time: fmtTime(g.start), text: g.text }; });
      setState({ lessonChatSegs: segs });
      // Citatklick från arkivsvaret: hoppa direkt till första transkriptraden
      // som innehåller någon av frågans termer — så man ser var i
      // transkriptionen informationen kommer ifrån.
      if (!hitT && hitQuery) {
        var terms = _peekTerms(hitQuery);
        var scores = _segScores(segs, terms);
        var best = 0;
        scores.forEach(function (n, i) { if (n > scores[best]) best = i; });
        if (scores[best] > 0 && segs[best].time) jumpToSource(segs[best].time);
      }
    }).catch(function () {});
  }
  function closeLessonChat() { clearTimeout(_descT); setState({ lessonChatId: null, lessonChat: [], lessonChatInput: '', lessonChatCiteSel: null, reasonOpen: {}, lessonChatMeta: null, lessonChatHitT: null, lessonChatEvent: null, evPick: null, ovEvOpen: false, ovDescView: false, descModal: false, descModalClosing: false }); }

  /* ---- Källmodal för arkivsvarets sifferkällor -----------------------------
     Klick på [n] öppnar en liten modal som visar själva stället i
     transkriptionen (träffraderna markerade) — chattvyn nås via knappen.
     Matchningen använder termer ur BÅDE frågan och svaret: modellen
     omformulerar ofta ("stereotyper" om ett klipp som säger "fördomar"),
     så svarets egna ord är den säkraste bryggan tillbaka till källraden. */
  var _PEEK_STOP = {};
  ('inte alla vara finns detta denna dessa vilket vilka också eller bara mycket sina hans hennes ' +
   'efter innan sedan under över genom fram från sägs nämns säger något någon handlar exempel ' +
   'inspelningen lektionen klippet sketchen tavlan provet skulle kommer kanske ganska väldigt ' +
   'samma andra olika visar samband källa källor utdrag utdragen').split(' ')
    .forEach(function (w) { _PEEK_STOP[w] = 1; });
  function _peekTerms(text) {
    var seen = {}, out = [];
    String(text || '').toLowerCase().split(/[^a-zåäö0-9]+/i).forEach(function (w) {
      if (w.length >= 4 && !_PEEK_STOP[w] && !seen[w]) { seen[w] = 1; out.push(w); }
    });
    return out;
  }
  function _segScores(segs, terms) {
    return segs.map(function (sg) {
      var low = (sg.text || '').toLowerCase(), n = 0;
      terms.forEach(function (t) { if (low.indexOf(t) >= 0) n++; });
      return n;
    });
  }
  var _peekT = null;
  function openCitePeek(src, q, ans) {
    clearTimeout(_peekT);
    var hitText = (q || '') + ' ' + (ans || '');
    setState({ citePeek: { src: src, q: q || '', hitText: hitText,
                           name: src.name || '(namnlös)',
                           meta: [src.group, src.course, src.datum].filter(Boolean).join(' · '),
                           loading: true, rows: [], more: 0 },
               citePeekClosing: false });
    var hid = src.history_id || src.id;
    getJSON('/api/history/' + encodeURIComponent(hid)).then(function (h) {
      var segs = ((h && h.transcript) || []).map(function (g) { return { time: fmtTime(g.start), text: g.text }; });
      var terms = _peekTerms(hitText);
      var scores = _segScores(segs, terms);
      var best = 0;
      scores.forEach(function (n, i) { if (n > scores[best]) best = i; });
      var hits = [];
      segs.forEach(function (sg, i) {
        if (scores[i] >= 2 || (i === best && scores[best] > 0)) hits.push(i);
      });
      var center = hits.length ? (hits.indexOf(best) >= 0 ? best : hits[0]) : 0;
      var from = Math.max(0, center - 2), to = Math.min(segs.length, center + 5);
      var rows = segs.slice(from, to).map(function (sg, i) {
        return { time: sg.time, text: sg.text, hit: hits.indexOf(from + i) >= 0 };
      });
      setState(function (s) {
        if (!s.citePeek) return null;
        return { citePeek: Object.assign({}, s.citePeek, {
          loading: false, rows: rows,
          more: hits.filter(function (i) { return i < from || i >= to; }).length,
        }) };
      });
    }).catch(function () {
      setState(function (s) {
        return s.citePeek ? { citePeek: Object.assign({}, s.citePeek, { loading: false }) } : null;
      });
    });
  }
  function closeCitePeek() {
    if (!S.citePeek || S.citePeekClosing) return;
    clearTimeout(_peekT);
    setState({ citePeekClosing: true });
    _peekT = setTimeout(function () { setState({ citePeek: null, citePeekClosing: false }); }, 340);
  }
  function citePeekOpenChat() {
    var p = S.citePeek; if (!p) return;
    clearTimeout(_peekT);
    setState({ citePeek: null, citePeekClosing: false });
    openLessonChat(p.src, null, p.hitText || p.q);
  }
  function onLessonChatInput(e) { setState({ lessonChatInput: e.target.value }); }
  function onLessonChatKey(e) { if (e.key === 'Enter') sendLessonChat(); }
  function toggleLessonChatThink() { setState(function (s) { return { lessonChatThink: !s.lessonChatThink }; }); }
  function toggleReason(mi) {
    setState(function (s) {
      var ro = Object.assign({}, s.reasonOpen);
      var cur = (mi in ro) ? !!ro[mi] : (!!s.lessonChatTyping && mi === s.lessonChat.length - 1);
      ro[mi] = !cur;
      return { reasonOpen: ro };
    });
  }
  function selectLessonChatCite(mi, segIdx) {
    var key = mi + ':' + segIdx;
    var seg = S.lessonChatSegs[segIdx] || {};
    var same = S.lessonChatCiteSel === key;
    setState({ lessonChatCiteSel: same ? null : key, lessonChatHitT: same ? null : (seg.time || null) });
    if (!same && seg.time) jumpToSource(seg.time);
  }
  // Design 14 juli: en källa i chatten scrollar transkriptet till träffraden
  // (data-ovhit i data-ovscroll) i stället för att visa ett inline-utdrag.
  function jumpToSource(t) {
    setState({ lessonChatHitT: t });
    setTimeout(function () {
      try {
        var sc = document.querySelector('[data-ovscroll]');
        var row = sc && sc.querySelector('[data-ovhit]');
        if (sc && row) sc.scrollTo({ top: Math.max(0, row.getBoundingClientRect().top - sc.getBoundingClientRect().top + sc.scrollTop - sc.clientHeight * 0.3), behavior: 'smooth' });
      } catch (e) {}
    }, 80);
  }
  function sendLessonChat(qArg) {
    if (S.lessonChatTyping) return;
    var q = (typeof qArg === 'string' && qArg ? qArg : S.lessonChatInput).trim();
    if (!q) return;
    // Kalenderönskemål får INGET förhandsbyggt förslag: modellen resonerar först
    // och skapar förslaget via sin [KALENDERFÖRSLAG]-rad (applyCalTag på 'done').
    // Läraren godkänner sedan uttryckligen med "Lägg till" — inget läggs in automatiskt.
    // Kalenderkommandon ("flytta till onsdag 14:30", "kortare titel" …) tolkas av
    // regex-tolken och uppdaterar förslaget direkt — utan LLM-anrop (design 14 juli).
    var evNow = S.lessonChatEvent;
    var isCal = evNow && !evNow.added && (/flytta|ändra|byt|boka|döp|kalla|titel|anteckning/i.test(q) || /\d{1,2}[:.]\d{2}/.test(q) || /måndag|tisdag|onsdag|torsdag|fredag|lördag|söndag|imorgon|nästa vecka|klockan/i.test(q));
    // Snabbvägen tar bara korta enradskommandon den förstår fullt ut ("flytta till
    // onsdag 14:30"). Längre eller sammansatta önskemål ("mer detaljerad", "hela
    // nästa vecka, varje dag 7–16") går till modellen, som kan skriva om hela
    // förslaget — annars svarar regexen "Klart" på delar den aldrig tillämpade.
    var calComplex = q.length > 80
      || (q.match(/[.!?]/g) || []).length > 1
      || /detaljerad|detaljer|mål|beskriv|utveckla|förklara|varje dag|hela (nästa )?veckan?|från kl/i.test(q);
    if (isCal && !calComplex) {
      var r0 = applyEventCommand(evNow, q);
      if (Object.keys(r0.patch).length) {
        setState(function (s) {
          if (!s.lessonChatEvent) return null;
          return { lessonChatInput: '',
                   lessonChatEvent: Object.assign({}, s.lessonChatEvent, r0.patch),
                   lessonChat: s.lessonChat.concat([{ role: 'user', text: q }, { role: 'assistant', text: r0.reply, reason: '' }]) };
        });
        return;
      }
    }
    setState(function (s) { return { lessonChat: s.lessonChat.concat([{ role: 'user', text: q }, { role: 'assistant', text: '', reason: '' }]), lessonChatInput: '', lessonChatTyping: true, lessonChatCiteSel: null }; });
    var msgs = S.lessonChat.filter(function (m) { return !(m.role === 'assistant' && !m.text); })
      .map(function (m) { return { role: m.role, content: m.text }; });
    var transcript = S.lessonChatSegs.map(function (l, i) { return '[' + (i + 1) + '] (' + (l.time || '') + ') ' + l.text; }).join('\n');
    var acc = '', accReason = '';
    var setLast = function (text, reason, typing) { setState(function (s) { var c = s.lessonChat.slice(); if (c.length) c[c.length - 1] = { role: 'assistant', text: stripCalTag(text), reason: reason }; return { lessonChat: c, lessonChatTyping: !!typing }; }); };
    // Modellen kan skapa/ändra kalenderförslaget direkt ur samtalet: den får dagens
    // datum + aktuellt förslag och svarar med en [KALENDERFÖRSLAG]-rad som appliceras här.
    var calEv = S.lessonChatEvent && !S.lessonChatEvent.added ? {
      title: S.lessonChatEvent.title, date: S.lessonChatEvent.startIso || null,
      time: (S.lessonChatEvent.when || '').slice(-5), end_date: S.lessonChatEvent.endIso || null,
      desc: S.lessonChatEvent.desc || '',
    } : null;
    streamPost('/api/chat', { messages: msgs, transcript: transcript, model: S.ppModel, think: S.lessonChatThink, cite: true, calendar: true, cal_event: calEv }, function (ev) {
      if (ev.type === 'reasoning') { accReason += ev.text; setLast(acc, accReason, true); }
      else if (ev.type === 'token') { acc += ev.text; setLast(acc, accReason, false); }
      else if (ev.type === 'error') { setLast(acc || ('Fel: ' + (ev.message || 'okänt')), accReason, false); }
      else if (ev.type === 'done') {
        var r = ev.result || {}; var full = r.text || acc;
        var applied = applyCalTag('lesson', full);
        var shown = stripCalTag(full);
        // Svarar modellen med enbart kalenderraden blir bubblan tom — sätt då en
        // egen bekräftelse byggd ur det uppdaterade förslaget.
        if (!shown && applied) {
          var e2 = S.lessonChatEvent || {};
          shown = 'Här är kalenderförslaget: ”' + (e2.title || '') + '” · ' + (e2.when || '') + (e2.endDay ? ' → ' + e2.endDay : '') + '. Inget läggs in förrän du godkänner med Lägg till — justera annars i förslags-rutan eller fortsätt chatta.';
        }
        setLast(shown || full, accReason, false);
      }
    });
  }

  /* ---- Kalenderförslag i lektionsoverlayen (Google Kalender) ---------------
     Förslaget byggs lokalt ur lektionens metadata; kommandoraden ("flytta till
     onsdag 14:30", "kortare titel", "lägg till …") tolkas med mallens regex-
     tolk — inga LLM-anrop behövs för att justera tid/titel/anteckning. -------- */
  var EV_TIMES = ['08:00', '08:30', '09:10', '10:00', '10:45', '11:30', '12:15', '13:00', '13:45', '14:30', '15:15', '16:00'];
  var _DAYS_SV = ['sön', 'mån', 'tis', 'ons', 'tors', 'fre', 'lör'];
  function evDays() {
    var now = new Date(), out = [];
    for (var i = 0; i < 8; i++) {
      var d = new Date(now); d.setDate(now.getDate() + i);
      out.push({ label: _DAYS_SV[d.getDay()] + ' ' + d.getDate() + ' ' + _MON_SV[d.getMonth()],
                 iso: d.toISOString().slice(0, 10),
                 pre: i === 0 ? 'Idag' : (i === 1 ? 'Imorgon' : '') });
    }
    return out;
  }
  // 'YYYY-MM-DD' → 'fre 17 jul' (samma etikettform som evDays).
  function _isoLabel(iso) {
    var d = new Date(iso + 'T12:00:00');
    if (isNaN(d)) return null;
    return _DAYS_SV[d.getDay()] + ' ' + d.getDate() + ' ' + _MON_SV[d.getMonth()];
  }
  function _calErrToast(msg) {
    setState({ toast: { title: 'Google Kalender', detail: msg, kind: 'error', done: false } });
    clearTimeout(_toastT2); _toastT2 = setTimeout(function () { setState({ toast: null }); }, 9000);
  }
  function loadCalStatus() {
    return getJSON('/api/calendar/status')
      .then(function (r) { setState({ calConnected: !!(r && r.connected), calClientReady: !!(r && r.client_ready), calHint: (r && r.hint) || '' }); })
      .catch(function () { setState({ calConnected: false, calClientReady: false }); });
  }
  // En OAuth-klient krävs alltid. Finns den redan (inbyggd/installerad) räcker
  // ett klick "Logga in med Google"; annars öppnas det guidade fönstret.
  function startCalConnect() { if (S.calClientReady) connectCalendar(); else openCalSetup(); }
  function openCalSetup() { setState({ calSetupOpen: true }); loadCalStatus(); }
  // Nollställ calBusy här: /api/calendar/connect blockerar tills Google-flödet är
  // klart, och överger användaren inloggningen svarar fetchen aldrig — utan detta
  // förblir "Logga in med Google" låst tills appen startas om.
  function closeCalSetup() { setState({ calSetupOpen: false, calBusy: false }); }
  function openGoogleConsole() { fetch('/api/calendar/open-console', { method: 'POST' }).catch(function () {}); }
  function clientFileRef(el) { _clientFile = el; }
  function pickClientSecret() { if (_clientFile) _clientFile.click(); }
  function onPickClientSecret(e) {
    var f = e.target && e.target.files && e.target.files[0];
    if (e.target) e.target.value = '';            // tillåt att välja samma fil igen
    if (!f) return;
    setState({ calBusy: true });
    var reader = new FileReader();
    reader.onload = function () {
      fetch('/api/calendar/client-secret', { method: 'POST', body: String(reader.result || '') })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          setState({ calBusy: false });
          if (res.ok) {
            loadCalStatus();
            setState({ toast: { title: 'Google Kalender', name: 'Klientfil installerad', done: true } });
            clearTimeout(_toastT2); _toastT2 = setTimeout(function () { setState({ toast: null }); }, 3200);
          } else { _calErrToast((res.j && res.j.error) || 'kunde inte installera klientfilen'); }
        }).catch(function () { setState({ calBusy: false }); });
    };
    reader.onerror = function () { setState({ calBusy: false }); };
    reader.readAsText(f);
  }
  function connectCalendar() {
    setState({ calBusy: true });
    fetch('/api/calendar/connect', { method: 'POST' }).then(function (r) { return r.json(); }).then(function (res) {
      var ok = !!(res && res.connected);
      setState({ calConnected: ok, calBusy: false });
      if (ok) setState({ calSetupOpen: false });
      else if (res && res.error) _calErrToast(res.error);
    }).catch(function () { setState({ calConnected: false, calBusy: false }); });
  }
  function proposeLessonEvent() {
    var m = S.lessonChatMeta || {};
    var days = evDays();
    var terms = S.lessonChatSegs.length ? '' : '';
    setState({ lessonChatEvent: {
      title: (m.group ? m.group + ' — ' : '') + 'Uppföljning: ' + (S.lessonChatName || 'lektionen'),
      when: days[2].label + ' · 08:00', startIso: days[2].iso,
      desc: 'Uppföljning av "' + (S.lessonChatName || 'lektionen') + '"' + (m.course ? ' i ' + m.course : '') + '. Läxförhör på begreppen från lektionen.',
      added: false, busy: false,
    }, evPick: null });
    if (S.calConnected === null) loadCalStatus();
  }
  // Kalenderförslag i arkivsvaret ("Fråga ditt arkiv") — samma box som i
  // lektionsoverlayen men byggt ur arkivfrågan i stället för lektionens metadata.
  function proposeAskEvent(q) {
    q = (q || S.askQ || '').trim();
    var days = evDays();
    setState({ askEvent: {
      title: 'Uppföljning: ' + (q.length > 52 ? q.slice(0, 52).trim() + '…' : (q || 'arkivfråga')),
      when: days[2].label + ' · 08:00', startIso: days[2].iso,
      desc: q ? 'Utifrån arkivfrågan ”' + q + '”.' : '',
      added: false, busy: false,
    }, evPick: null });
    if (S.calConnected === null) loadCalStatus();
  }
  // Förslaget finns på två ställen: lektionsoverlayen ('lesson' → lessonChatEvent)
  // och arkivsvaret ('ask' → askEvent). Samma box, samma hjälpare.
  var _EVKEY = { lesson: 'lessonChatEvent', ask: 'askEvent' };
  function setEvField(which, k, v) {
    var key = _EVKEY[which];
    setState(function (s) { return s[key] ? kv(key, Object.assign({}, s[key], kv(k, v))) : null; });
  }
  function toggleEvPick(which) { setState(function (s) { return { evPick: s.evPick === which ? null : which }; }); }
  function pickEvPart(which, part, val, iso) {
    var ev = S[_EVKEY[which]]; if (!ev) return;
    var bits = (ev.when || ' · ').split(' · ');
    var when = (part === 'day' ? val : (bits[0] || '')) + ' · ' + (part === 'time' ? val : (bits[1] || '09:00'));
    var key = _EVKEY[which];
    setState(function (s) {
      if (!s[key]) return null;
      var patch = { when: when };
      if (part === 'day' && iso) patch.startIso = iso;
      return kv(key, Object.assign({}, s[key], patch));
    });
    if (part === 'time') setState({ evPick: null });
  }
  // "dag mån · HH:MM" -> ISO-start för API:t (dagens etikett slås upp mot evDays()).
  function _evWhenToStart(when) {
    var bits = (when || '').split(' · ');
    var day = evDays().filter(function (d) { return d.label === bits[0]; })[0];
    var time = /^\d{2}:\d{2}$/.test(bits[1] || '') ? bits[1] : '08:00';
    return (day ? day.iso : new Date().toISOString().slice(0, 10)) + 'T' + time + ':00';
  }
  function addEvent(which) {
    var key = _EVKEY[which];
    var ev = S[key]; if (!ev || ev.busy || ev.added) return;
    setEvField(which, 'busy', true);
    // startIso vinner över etikett-uppslaget: chatten kan sätta datum utanför
    // dag-väljarens 8-dagarsfönster, där _evWhenToStart inte hittar etiketten.
    var evTime = /^\d{2}:\d{2}$/.test((ev.when || '').slice(-5)) ? (ev.when || '').slice(-5) : '08:00';
    fetch('/api/calendar/event', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: ev.title, start: ev.startIso ? ev.startIso + 'T' + evTime + ':00' : _evWhenToStart(ev.when), description: ev.desc || '',
                             end_date: ev.endIso || null })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); }).then(function (res) {
      if (res.ok) { setState(function (s) { return s[key] ? kv(key, Object.assign({}, s[key], { busy: false, added: true })) : null; }); }
      else {
        setEvField(which, 'busy', false);
        var msg = (res.j && res.j.error) || 'kunde inte skapa händelsen';
        setState({ toast: { title: 'Google Kalender', detail: msg, kind: 'error', done: false } });
        clearTimeout(_toastT2); _toastT2 = setTimeout(function () { setState({ toast: null }); }, 9000);
      }
    }).catch(function () { setEvField(which, 'busy', false); });
  }
  function dismissEvent(which) { setState(Object.assign({ evPick: null }, kv(_EVKEY[which], null))); }
  // [KALENDERFÖRSLAG] {json} — modellens maskinläsbara kalenderrad (llm_client._cal_instr).
  // Döljs ur visningen (även halvströmmad) och appliceras på förslaget när svaret är klart.
  var _CAL_TAG = '[KALENDERFÖRSLAG]';
  function stripCalTag(text) {
    var i = text.indexOf(_CAL_TAG);
    if (i < 0) { i = text.search(/\[K[A-ZÅÄÖ]{0,15}$/); }   // halvströmmad markör i svansen
    return i >= 0 ? text.slice(0, i).replace(/\s+$/, '') : text;
  }
  function applyCalTag(which, text) {
    var i = text.indexOf(_CAL_TAG);
    if (i < 0) return false;
    var cal = null;
    try { cal = JSON.parse((text.slice(i + _CAL_TAG.length).match(/\{[\s\S]*\}/) || [null])[0]); } catch (e) {}
    if (!cal || typeof cal !== 'object') return false;
    var key = _EVKEY[which];
    setState(function (s) {
      var ev = s[key];
      if (ev && ev.added) ev = null;                        // redan tillagd → nytt förslag
      var base = ev || { title: '', when: '', desc: '', added: false, busy: false };
      var patch = {};
      if (typeof cal.title === 'string' && cal.title) patch.title = cal.title;
      if (typeof cal.desc === 'string' && cal.desc) patch.desc = cal.desc;
      var time = (typeof cal.time === 'string' && /^\d{1,2}:\d{2}$/.test(cal.time))
        ? (cal.time.length < 5 ? '0' + cal.time : cal.time)
        : (/^\d{2}:\d{2}$/.test((base.when || '').slice(-5)) ? (base.when || '').slice(-5) : '08:00');
      var dayLabel = null, startIso = base.startIso || null;
      if (typeof cal.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(cal.date)) {
        var lbl = _isoLabel(cal.date);
        if (lbl) { dayLabel = lbl; startIso = cal.date; }
      }
      if (!dayLabel) dayLabel = (base.when || ' · ').split(' · ')[0] || evDays()[2].label;
      if (!startIso) startIso = evDays()[2].iso;
      patch.when = dayLabel + ' · ' + time;
      patch.startIso = startIso;
      if (typeof cal.end_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(cal.end_date) && cal.end_date > startIso) {
        patch.endIso = cal.end_date; patch.endDay = _isoLabel(cal.end_date);
      } else if (cal.end_date === null) {
        patch.endIso = null; patch.endDay = null;
      }
      return kv(key, Object.assign({}, base, patch));
    });
    // Modellens förslag ska granskas direkt: fäll ut redigeringsboxen i
    // overlayen så läraren ser exakt vad som föreslås innan hen godkänner.
    if (which === 'lesson') setState({ ovEvOpen: true });
    if (S.calConnected === null) loadCalStatus();
    return true;
  }
  function openDescModal(which) { clearTimeout(_descT); setState({ descModal: true, descModalClosing: false, descModalFor: which || 'lesson' }); }
  // Vymodell för förslags-boxen (lessonEventBox) — delas av overlayen och arkivsvaret.
  function evBoxVM(which, st) {
    var ev = st[_EVKEY[which]];
    return {
      notAdded: !ev.added, added: ev.added, busy: ev.busy,
      title: ev.title, when: ev.when + (ev.endDay ? ' → ' + ev.endDay : ''), desc: ev.desc || '',
      calKnown: st.calConnected !== null, calConnected: st.calConnected === true,
      onConnect: startCalConnect,
      setTitle: function (e) { setEvField(which, 'title', e.target.value); },
      setDesc: function (e) { setEvField(which, 'desc', e.target.value); },
      onAdd: function (e) { if (e) e.stopPropagation(); addEvent(which); },
      onDismiss: function (e) { if (e) e.stopPropagation(); dismissEvent(which); },
      onTitleKey: function (e) { if (e.key === 'Enter') { e.preventDefault(); addEvent(which); } },
      descFocusRef: function (el) { if (el && !el._descBound) { el._descBound = true; el.addEventListener('focus', function () { el.blur(); openDescModal(which); }); } },
      pickOpen: st.evPick === which,
      onTogglePick: function (e) { if (e) e.stopPropagation(); toggleEvPick(which); },
      dayOpts: evDays().map(function (d) {
        return { key: d.label, label: d.label, pre: d.pre, hasPre: !!d.pre,
                 curQ: (ev.when || '').indexOf(d.label) === 0 ? '1' : '',
                 onPick: function (e) { if (e) e.stopPropagation(); pickEvPart(which, 'day', d.label, d.iso); } };
      }),
      timeOpts: EV_TIMES.map(function (t2) {
        return { key: t2, label: t2, curQ: (ev.when || '').slice(-5) === t2 ? '1' : '',
                 onPick: function (e) { if (e) e.stopPropagation(); pickEvPart(which, 'time', t2); } };
      }),
    };
  }
  function closeDescModal() {
    if (!S.descModal || S.descModalClosing) return;
    clearTimeout(_descT);
    setState({ descModalClosing: true });
    _descT = setTimeout(function () { setState({ descModal: false, descModalClosing: false }); }, 440);
  }
  function applyEventCommand(ev, q) {
    var low = q.toLowerCase();
    var patch = {}, done = [];
    var bits = (ev.when || ' · ').split(' · ');
    var day = bits[0] || '', time = bits[1] || '08:00', whenChanged = false;
    // tid — "14:30", "14.30", "kl 9", "klockan 10"
    var tm = low.match(/(\d{1,2})[:.](\d{2})/);
    var th = tm ? null : low.match(/(?:kl\.?|klockan)\s*(\d{1,2})(?!\d)/);
    if (tm) { time = (tm[1].length < 2 ? '0' + tm[1] : tm[1]) + ':' + tm[2]; whenChanged = true; }
    else if (th) { time = (th[1].length < 2 ? '0' + th[1] : th[1]) + ':00'; whenChanged = true; }
    if (whenChanged) done.push('tiden till ' + time);
    // flera dagar — "pågå till fredag", "till och med torsdag", "t.o.m. ons",
    // "fram till fredag"; "en dag"/"bara en dag" nollställer slutdagen.
    var days = evDays();
    var W = [['måndag', 'mån'], ['tisdag', 'tis'], ['onsdag', 'ons'], ['torsdag', 'tors'], ['fredag', 'fre'], ['lördag', 'lör'], ['söndag', 'sön']];
    var edm = low.match(/(?:pågå(?:r)?(?:\s+till)?|till och med|t\.?o\.?m\.?|fram till)\s+(måndag|tisdag|onsdag|torsdag|fredag|lördag|söndag|mån|tis|ons|tors|fre|lör|sön)/);
    if (edm) {
      var ewi = -1;
      for (var ei = 0; ei < W.length; ei++) { if (W[ei][0] === edm[1] || W[ei][1] === edm[1]) { ewi = ei; break; } }
      if (ewi >= 0) {
        // Första matchande veckodag STRIKT EFTER startdagen ("till fredag" när
        // starten är en fredag = nästa fredag). Kan hamna utanför dag-väljarens
        // fönster, därför bär förslaget även slutdatumet som ISO (endIso).
        var sd0 = days.filter(function (d) { return d.label === day; })[0];
        var base = new Date((sd0 ? sd0.iso : days[0].iso) + 'T12:00:00');
        var gidx = (ewi + 1) % 7;   // W är mån..sön; Date.getDay() har sön=0
        for (var k = 1; k <= 7; k++) {
          var dt = new Date(base); dt.setDate(base.getDate() + k);
          if (dt.getDay() === gidx) {
            patch.endDay = _DAYS_SV[dt.getDay()] + ' ' + dt.getDate() + ' ' + _MON_SV[dt.getMonth()];
            patch.endIso = dt.toISOString().slice(0, 10);
            done.push('händelsen till att pågå till ' + patch.endDay);
            low = low.replace(edm[0], '');   // så slutdagen inte också tolkas som ny startdag
            break;
          }
        }
      }
    } else if (/(?:^|\s)(?:bara |endast )?en dag(?:\s|$|\.)/.test(low) && ev.endDay) {
      patch.endDay = null; patch.endIso = null; done.push('händelsen till en enda dag');
    }
    var nd = null;
    if (low.indexOf('imorgon') >= 0 || low.indexOf('i morgon') >= 0) nd = days[1];
    else if (low.indexOf('nästa vecka') >= 0) nd = days[7];
    else if (low.indexOf('idag') >= 0 || low.indexOf('i dag') >= 0) nd = days[0];
    else { for (var wi = 0; wi < W.length; wi++) { var w = W[wi]; if (low.indexOf(w[0]) >= 0 || new RegExp('(^|\\s)' + w[1] + '(\\s|$)').test(low)) { nd = days.slice(1).filter(function (d) { return d.label.indexOf(w[1] + ' ') === 0; })[0] || null; break; } } }
    if (nd) { day = nd.label; whenChanged = true; patch.startIso = nd.iso; done.push('dagen till ' + nd.label); }
    if (whenChanged) patch.when = day + ' · ' + time;
    // titel
    var tt = q.match(/(?:titeln?(?:\s+till|\s+ska vara)?|kalla (?:den|det)|döp (?:den|det) till)\s+["”«']?(.+?)["”»']?$/i);
    if (low.indexOf('kortare titel') >= 0 || low.indexOf('korta titeln') >= 0) {
      var m = S.lessonChatMeta || {};
      patch.title = (m.group ? m.group + ': ' : '') + 'Uppföljning'; done.push('titeln till "' + patch.title + '"');
    } else if (tt && tt[1] && !/^(till|ska)/i.test(tt[1])) {
      patch.title = tt[1].charAt(0).toUpperCase() + tt[1].slice(1); done.push('titeln till "' + patch.title + '"');
    }
    // anteckning
    var ad = q.match(/(?:lägg till|skriv|anteckna)(?:\s+att)?\s+(.+)$/i);
    if (ad && /^läxan?( i anteckningen)?\.?$/i.test(ad[1].trim())) {
      patch.desc = (ev.desc || '') + ' Läxa: repetera begreppen från lektionen.';
      done.push('läxan i anteckningen');
    } else if (ad && !tt) {
      var txt = ad[1].trim().replace(/^i anteckningen\s+/i, '');
      patch.desc = (ev.desc || '') + ' ' + txt.charAt(0).toUpperCase() + txt.slice(1) + (/[.!?]$/.test(txt) ? '' : '.');
      done.push('det i anteckningen');
    }
    var reply = done.length
      ? 'Klart — jag ändrade ' + done.join(' och ') + '.'
      : 'Jag kan ändra tid, datum, titel och anteckningen — t.ex. ”flytta till onsdag 14:30”, ”kalla den Läxförhör bråk” eller ”lägg till att de ska repetera bråken”.';
    return { patch: patch, reply: reply };
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
  function getTranscript() { return (S.transcript && S.transcript.length) ? S.transcript : []; }
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
        // Keep the model in sync with the chosen language. '' when no language-
        // appropriate model is installed — never cross-select (e.g. a Swedish model
        // for English); the UI then prompts for a download instead.
        patch.model = recommendModel(S.language, inst);
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
    var dupes = 0;
    setState(function (s) {
      var existing = new Set(s.queue.map(function (q) { return q.path || q.name; }));
      var adds = good.filter(function (g) { return !existing.has(g.path || g.name); })
        .map(function (g, k) { return { id: 'q' + Date.now() + '_' + k, name: g.name, path: g.path || g.name }; });
      dupes = good.length - adds.length;
      var queue = s.queue.concat(adds);
      var activeId = s.activeId || (queue[0] && queue[0].id) || null;
      return { queue: queue, dragging: false, step: 'config', activeId: activeId, source: qName(queue, activeId) || s.source, fileError: skipped ? ('Hoppade över ' + skipped + ' fil(er) — formatet stöds inte.') : '' };
    });
    // Design (14 juli): filer som redan låg i kön filtreras tyst bort — berätta det.
    if (dupes) {
      clearInterval(_toastIv); clearTimeout(_toastT2);
      setState({ toast: { title: dupes === 1 ? '1 fil låg redan i kön' : dupes + ' filer låg redan i kön', name: '', done: true } });
      _toastT2 = setTimeout(function () { setState({ toast: null }); }, 3200);
    }
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

  function applySideEffects() {
    syncTheme();
    // Tavel-iframen är morphdom-skyddad (data-wb-frame), så en data-ref-attribut
    // på den fryser vid första rendern medan H-registret byggs om varje render —
    // ett fruset id kan då träffa FEL handler när id-layouten skiftar. Koppla den
    // därför direkt här i stället för via data-ref. (wbFrameRef är idempotent.)
    var _wbEl = document.querySelector('[data-wb-frame]');
    if (_wbEl) wbFrameRef(_wbEl); else _wbFrame = null;
    if (S.editing && !_wasEditing) { _editBuf = {}; requestAnimationFrame(function () { document.querySelectorAll('[data-eline]').forEach(function (el) { var i = el.getAttribute('data-eline'); el.textContent = lineText(+i); }); }); }
    _wasEditing = S.editing;
    if (S.tab !== _prevTab) { _prevTab = S.tab; playTabIn(); }
    if (S.step !== _prevStep) { var to = S.step; _prevStep = to; if (to === 'process') playPaneIn(); }
    var open = S.transcriptOpen;
    if (open && !_wasOpen) { var inp = document.querySelector('[data-tsearch]'); if (inp) inp.focus(); }
    _wasOpen = open;
    // Dialoger: flytta fokus in i dialogen när den öppnas (fokusfällan i onKeyDown
    // håller det sedan kvar). En ren skärmläsar- och tangentbordsförbättring.
    var modalNow = !!document.querySelector('[data-dialog]');
    if (modalNow && !_wasModal) {
      requestAnimationFrame(function () {
        var card = document.querySelector('[data-dialog]');
        if (!card || card.contains(document.activeElement)) return;
        var f = card.querySelector('input:not([type=file]):not([disabled]),textarea:not([disabled]),select:not([disabled]),button:not([disabled]),[tabindex]:not([tabindex="-1"])');
        try { (f || card).focus(); } catch (e) {}
      });
    }
    _wasModal = modalNow;
    if (open) {
      var key = S.currentMatch + '|' + S.searchQuery;
      if (key !== _scrollKey) {
        var cont = _scrollRef;
        var cur = cont && cont.querySelector('[data-current="1"]');
        if (cont && cur) { var cr = cont.getBoundingClientRect(), er = cur.getBoundingClientRect(); cont.scrollTop += (er.top - cr.top) - cr.height / 2; }
        _scrollKey = key;
      }
    }
  }

  function onKeyDown(e) {
    // Fokusfälla: håll Tab-fokus kvar inuti den översta öppna dialogen.
    if (e.key === 'Tab') {
      var dlgs = document.querySelectorAll('[data-dialog]');
      var mc = dlgs.length ? dlgs[dlgs.length - 1] : null;
      if (mc) {
        var sel = 'a[href],button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';
        var f = Array.prototype.filter.call(mc.querySelectorAll(sel), function (el) { return el.offsetWidth > 0 || el.offsetHeight > 0 || el === document.activeElement; });
        if (f.length) {
          var first = f[0], last = f[f.length - 1], a = document.activeElement;
          if (e.shiftKey && (a === first || !mc.contains(a))) { e.preventDefault(); last.focus(); }
          else if (!e.shiftKey && (a === last || !mc.contains(a))) { e.preventDefault(); first.focus(); }
        }
        return;
      }
    }
    if (S.editingLesson && e.key === 'Escape') { cancelEditLesson(); return; }
    if (S.lessonChatId && e.key === 'Escape') {
      if (S.descModal && !S.descModalClosing) { closeDescModal(); return; }
      if (S.evPick) { setState({ evPick: null }); return; }
      closeLessonChat(); return;
    }
    if (S.logOpen && e.key === 'Escape') { closeLog(); return; }
    if (S.filterOpen && e.key === 'Escape') { setState({ filterOpen: null, filterClosing: false }); return; }
    if (S.askZoom && e.key === 'Escape') { closeAskZoom(); return; }
    if (S.wbZoom && e.key === 'Escape') { closeWbZoom(); return; }
    if (e.key === 'Escape' && S.tab === 'recordings' && S.searchMode === 'ask' && (S.asking || S.askAnswer)) { clearSearch(); return; }
    if (!S.transcriptOpen) return;
    if ((e.ctrlKey || e.metaKey) && (e.key === 'f' || e.key === 'F')) { e.preventDefault(); var inp = document.querySelector('[data-tsearch]'); if (inp) inp.focus(); }
    else if (e.key === 'Escape') { closeTranscript(); }
  }

  /* ------------------------------------------------------------ view-model -- */
  function vm() {
    var st = S;
    var isRunning = st.run === 'running';
    var isDone = st.run === 'done';
    // Baren/stegen drivs av det mjuka visningsvärdet (dispProgress), inte de glesa
    // serverhoppen — så de växer kontinuerligt. dispProgress ligger aldrig före
    // servern över en stegräns, så det aktiva steget förblir ärligt.
    var prog = isDone ? 100 : Math.max(0, Math.min(100, st.dispProgress || 0));
    var STAGES = stageNames(), BOUNDS = stageBounds();
    var cur = STAGES.length;
    if (!isDone) { cur = 0; while (cur < STAGES.length - 1 && prog >= BOUNDS[cur + 1]) cur++; }

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
    var langOptions = langs.map(function (p) { return { label: p[1], active: st.language === p[0], style: segBtn(st.language === p[0], '38px'), onPick: function () { pickLang(p[0]); } }; });
    // Result language: pick sv/en; if it differs from the source language the
    // subtitles are translated by the local text model.
    var targetLangs = [['sv', 'Svenska'], ['en', 'Engelska']];
    var targetLangOptions = targetLangs.map(function (p) { return { label: p[1], active: st.targetLanguage === p[0], style: segBtn(st.targetLanguage === p[0], '34px'), onPick: function () { pickTargetLang(p[0]); } }; });
    var translateNote = (st.targetLanguage && st.language && st.targetLanguage !== st.language)
      ? ('Översätts till ' + (st.targetLanguage === 'sv' ? 'svenska' : 'engelska') + ' av språkmodellen.')
      : '';
    // Språk-flödet (design): talat -> resultat med live-status för översättning.
    var _langName = function (c) { return c === 'en' ? 'engelska' : 'svenska'; };
    var isTranslating = !!(st.targetLanguage && st.language && st.targetLanguage !== st.language);
    var transHint = isTranslating
      ? ('Översätts från ' + _langName(st.language) + ' till ' + _langName(st.targetLanguage) + '.')
      : ('Resultatet blir på ' + _langName(st.targetLanguage || st.language) + ' — samma som det talade språket.');
    var formatChips = ['srt', 'txt', 'vtt'].map(function (f) { return { label: f.toUpperCase(), active: st.formats[f], style: chip(st.formats[f]), onToggle: function () { toggleFmt(f); } }; });
    // Subtitle delivery for video sources: keep media + SRT side by side, or embed
    // the subtitles into the video (soft mux or hard burn). Only shown for video.
    var _activeQ = st.queue.find(function (q) { return q.id === st.activeId; }) || st.queue[0];
    var _activeIsVideo = !!(_activeQ && /\.(mp4|mkv|mov|webm|avi|m4v)$/i.test(_activeQ.name || ''));
    var subtitleOptions = [['separate', 'Spara separat'], ['embed', 'Bädda in']].map(function (p) { return { label: p[1], active: st.subtitleMode === p[0], style: segBtn(st.subtitleMode === p[0], '34px'), onPick: function () { setState({ subtitleMode: p[0] }); } }; });
    var embedOptions = [['soft', 'Mjukt sub-spår'], ['burn', 'Hård inbränning']].map(function (p) { return { label: p[1], active: st.embedKind === p[0], style: segBtn(st.embedKind === p[0], '34px'), onPick: function () { setState({ embedKind: p[0] }); } }; });

    var PHASE_LO2 = BOUNDS.slice(0, BOUNDS.length - 1), PHASE_HI2 = BOUNDS.slice(1);
    var steps = STAGES.map(function (label, idx) {
      var done = idx < cur, active = idx === cur && !isDone;
      // Aktivt steg fylls proportionellt mot hur långt prog kommit i just det
      // steget → baren växer mjukt och kontinuerligt istället för att blinka helt.
      var frac = (done || isDone) ? 1 : active ? Math.max(0, Math.min(1, (prog - PHASE_LO2[idx]) / (PHASE_HI2[idx] - PHASE_LO2[idx]))) : 0;
      var pctW = (done || isDone) ? 100 : active ? Math.max(3, frac * 100) : 0;
      return {
        label: label, icon: done || isDone ? '✓' : (idx + 1),
        barTrackStyle: 'height:4px;border-radius:99px;background:var(--line);overflow:hidden',
        barFillStyle: 'height:100%;border-radius:99px;background:' + (done || isDone ? 'var(--ok)' : 'var(--accent)') + ';width:' + pctW.toFixed(1) + '%;transition:width .22s linear' + (active ? ';background-image:linear-gradient(90deg,var(--accent) 0,var(--accent) 55%,color-mix(in srgb,var(--accent) 35%,#fff) 78%,var(--accent));background-size:26px 100%;animation:flow .8s linear infinite' : ''),
        dotStyle: 'width:18px;height:18px;border-radius:50%;flex:0 0 auto;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:600;' + (done || isDone ? 'background:var(--ok);color:var(--on-ok)' : active ? 'background:var(--accent);color:var(--on-accent);animation:pulse 1.4s ease infinite' : 'background:transparent;border:1.5px solid var(--line-2);color:var(--ink-3)'),
        labelStyle: 'font-size:13.5px;font-weight:500;color:' + (done || isDone ? 'var(--ink)' : active ? 'var(--ink)' : 'var(--ink-3)'),
      };
    });

    var base = baseName();

    var hw = hardwareView();
    var stepOrder = ['source', 'config', 'process'];
    var stepDefs = [['source', 'Källa'], ['config', 'Inställningar'], ['process', 'Transkribering']];
    var curStepIdx = stepOrder.indexOf(st.step);
    var stepItems = stepDefs.map(function (p, i) {
      var state = i < curStepIdx ? 'done' : i === curStepIdx ? 'active' : 'todo';
      return {
        label: p[1], icon: state === 'done' ? '✓' : (i + 1),
        dotStyle: 'width:24px;height:24px;border-radius:50%;flex:0 0 auto;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600;' + (state === 'done' ? 'background:var(--ok);color:var(--on-ok)' : state === 'active' ? 'background:var(--ink);color:var(--btn-fg)' : 'background:transparent;border:1.5px solid var(--line-2);color:var(--ink-3)'),
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



    var lastIdx = st.log.length - 1;
    var logRows = st.log.map(function (line, i) {
      var time = '', msg = line, isKlar = false;
      if (line.indexOf('› ') === 0) { msg = line.slice(2); }
      else { var mm = line.match(/^\[([^\]]+)\]\s*(.*)$/); if (mm) { time = mm[1]; msg = mm[2]; if (time === 'klar') { isKlar = true; time = ''; } } }
      var last = i === lastIdx;
      var green = st.run === 'done' || !last;
      var dotStyle = green ? 'width:13px;height:13px;border-radius:50%;flex:0 0 auto;display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:700;color:var(--on-ok);background:var(--ok)' : 'width:13px;height:13px;border-radius:50%;flex:0 0 auto;background:var(--surface);border:2px solid var(--line-2);box-sizing:border-box';
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
        barStyle: 'height:100%;width:100%;transform-origin:left;transform:scaleX(' + ((status === 'done' ? 100 : status === 'running' ? pct : 0) / 100) + ');background:' + statusCol[status] + ';border-radius:99px;transition:transform .3s ease',
        showBar: status === 'running' || status === 'done',
        rowStyle: 'display:flex;align-items:center;gap:12px;padding:11px 14px;border-radius:13px;border:1px solid ' + (isActive ? 'var(--line-2)' : 'var(--line)') + ';background:' + (isActive ? 'var(--sunken)' : 'var(--surface)') + ';box-shadow:var(--shadow-sm)',
        canRemove: st.step !== 'process', onRemove: function () { removeQ(qq.id); },
      };
    });
    var doneCount = st.queue.filter(function (qq) { return st.qStatus[qq.id] === 'done'; }).length;
    var historyItems = st.history.map(function (h) {
      return {
        id: h.id, name: h.name, date: h.date,
        meta: h.dur + ' · ' + h.model + ' · ' + h.lang,
        formats: (h.formats || []).map(function (f) { return { label: f }; }),
        onOpen: function () { openHistory(h); }, onRerun: function () { askRerun(h); }, onDelete: function () { askDeleteHistory(h.id, h.name); },
        onDownload: function () { downloadFile(baseNameOf(h.name) + '.' + ((h.formats && h.formats[0]) || 'TXT').toLowerCase(), Math.max(9, Math.round((h.words || 3000) / 140)) + ' KB'); },
        thumbUrl: _videoThumb(h),
      };
    });

    // Scen-koreografi i Inspelningar: under en AI-fråga lyfts relevanta kort och
    // övriga dimmas. Medan modellen tänker är relevansen en preliminär
    // nyckelordsmatch; när svaret kommit styr de riktiga källorna.
    var askActive = st.searchMode === 'ask' && (st.asking || !!st.askAnswer);
    var askSourceIds = null;
    if (askActive && st.askSources && st.askSources.length) {
      askSourceIds = {};
      st.askSources.forEach(function (s2) { if (s2.lesson_id != null) askSourceIds[s2.lesson_id] = true; });
    }
    // Träff = äkta backend-data: efter svaret de riktiga källorna, under
    // skanningen de verkliga innehållsordsträffarna (scan_result). Ingen
    // klientmatchning på frågans ord längre — den markerade småordsträffar.
    var askDeepIds = null;
    if (askActive && st.askDeep && st.askDeep.length) {
      askDeepIds = {};
      st.askDeep.forEach(function (s2) { if (s2.lesson_id != null) askDeepIds[s2.lesson_id] = true; });
    }
    function lessonHit(l) {
      if (askSourceIds) return !!askSourceIds[l.id];
      if (askDeepIds) return !!askDeepIds[l.id];
      if (st.askScanPlan) return (st.askScanRes[l.id] || 0) > 0;
      return false;
    }

    // Live-skanningen: backend har berättat den äkta genomsökningsordningen
    // (askScanPlan); utrullningen (askScanShown) pacas av startScanReveal.
    var scanPlan = st.askScanPlan || [];
    var scanning = st.asking;
    var scanShown = Math.min(st.askScanShown, scanPlan.length);
    var scannedIds = {};
    scanPlan.slice(0, scanning ? scanShown : scanPlan.length).forEach(function (p) { scannedIds[p.key] = true; });
    function lessonStage(l) {
      if (!askActive) return '';
      var hit = lessonHit(l);
      if (hit && (!scanning || scannedIds[l.id])) return 'lift';
      return (!scanning || scannedIds[l.id]) ? 'dim' : '';
    }

    // Uppslag history-id → post EN gång (i stället för en find() per lektion per
    // render → O(lektioner × historik)).
    var histById = {};
    (st.history || []).forEach(function (x) { histById[x.id] = x; });
    var lessonItems = st.lessons.map(function (l) {
      var isHit = askActive && lessonHit(l) && (!scanning || scannedIds[l.id]);
      // Videoförhandsvisning: bara VIDEO-källor får en thumbnail på kortet (h.video
      // sätts även för ljud — det är den spelbara median — så gå på filändelsen).
      // Rena ljudinspelningar (wav/mp3/m4a/webm …) visas som text, som idag.
      var thumbUrl = _videoThumb(histById[l.history_id]);
      return {
        id: l.id, name: l.name || '(namnlös)', date: l.date || l.datum || '', thumbUrl: thumbUrl,
        datum: l.datum || l.date || '',
        meta: [l.dur, l.model, l.lang].filter(Boolean).join(' · '),
        dur: l.dur || '', sal: l.sal || '',
        unassigned: !l.group && !l.course,
        cc: ccOf(l),
        tagLabel: l.group ? (l.group + (l.course ? ' · ' + String(l.course).slice(0, 2) : '')) : (l.course || 'Ej tilldelad'),
        tagFull: l.group ? (l.group + (l.course ? ' · ' + l.course : '')) : (l.course || 'Ej tilldelad'),
        stage: lessonStage(l),
        isHit: isHit,
        onOpenChat: function () { openLessonChat(l); },
        onOpen: function () { openLesson(l); },
        onRename: function (e) { if (e) e.stopPropagation(); startEditLesson(l); },
        onDelete: function (e) { if (e) e.stopPropagation(); askDeleteLesson(l.id, l.name || '(namnlös)'); },
      };
    });
    // Datum-filter (klientsidan): distinkta månader + filtrering av korten.
    var lessonMonths = Array.from(new Set(st.lessons.map(function (l) { return (l.datum || l.date || '').slice(0, 7); }).filter(Boolean))).sort().reverse();
    if (st.lessonFilterMonth) lessonItems = lessonItems.filter(function (it) { return (it.datum || '').slice(0, 7) === st.lessonFilterMonth; });
    // Sök ord-läget filtrerar kartoteket live på titel/klass/kurs (FLIP i onSearchInput).
    var kwTerms = (st.searchMode === 'keyword' ? (st.lessonSearch || '') : '').toLowerCase().split(/\s+/).filter(Boolean);
    if (kwTerms.length) lessonItems = lessonItems.filter(function (it) {
      var hay = (it.name + ' ' + it.tagLabel).toLowerCase();
      return kwTerms.every(function (w) { return hay.indexOf(w) >= 0; });
    });
    // Kartoteket: veckogrupper (nyaste veckan först).
    var weekMap = {};
    lessonItems.forEach(function (it) {
      var wi = weekInfo(it.datum);
      if (!weekMap[wi.key]) weekMap[wi.key] = { key: wi.key, num: wi.num, label: wi.label, range: wi.range, start: wi.start, cards: [] };
      weekMap[wi.key].cards.push(it);
    });
    var weekGroups = Object.keys(weekMap).map(function (k) { return weekMap[k]; })
      .sort(function (a, b) { return b.start - a.start; })
      .map(function (g) {
        var nh = g.cards.filter(function (c) { return c.isHit; }).length;
        return { key: g.key, num: g.num, isWeek: g.num !== '·', label: g.label, range: g.range,
                 count: g.cards.length + (g.cards.length === 1 ? ' inspelning' : ' inspelningar'),
                 cards: g.cards, hasHits: nh > 0, hitLabel: nh + (nh === 1 ? ' träff' : ' träffar') };
      });

    return {
      theme: st.theme,
      tabTranscribe: st.tab === 'transcribe', tabRecordings: st.tab === 'recordings',
      tabPlanning: st.tab === 'planning',
      onTabT: function () { setTab('transcribe'); }, onTabIn: function () { setTab('recordings'); },
      onTabP: function () { setTab('planning'); },
      tabTOn: st.tab === 'transcribe', tabInOn: st.tab === 'recordings',
      tabPlOn: st.tab === 'planning',

      // Planering (Fas 0/1)
      wbTitle: wbTitle(),
      wbFrameRef: wbFrameRef, wbRendered: st.wbRendered,
      wbWarnings: st.wbWarnings, wbWarnCount: st.wbWarnings.length,
      onWbPrint: wbPrint, onWbExport: wbExportPng,
      wbExporting: st.wbExporting, wbExportMsg: st.wbExportMsg,
      wbExportFailed: /^Kunde inte/.test(st.wbExportMsg),
      // Tavelzoomen: kortet förstoras på plats (data-wbwrap/data-wbzoom)
      wbZoomFlag: st.wbZoom ? (st.wbZoomClosing ? 'closing' : 'on') : '',
      wbZoomOn: !!st.wbZoom && !st.wbZoomClosing,
      onWbZoomOpen: openWbZoom,
      onWbZoomClose: function () { closeWbZoom(); },
      onWbCardClick: function (e) { if (e) e.stopPropagation(); },
      planGroups: st.groups, planCourses: st.courses,
      planGroupId: st.planGroupId, planCourseId: st.planCourseId,
      // Chips i stället för dropdowns: klick väljer, klick på vald avmarkerar.
      // Ämnesmodellen (Gy25): servern levererar amne_namn/niva_kort/sort —
      // chipsen grupperas per ämne i progressionsordning. Fritextkurser utan
      // ämne hamnar i en egen grupp sist.
      planCourseGroups: (function () {
        var groups = [], byAmne = {};
        st.courses.forEach(function (c) {
          var sel = String(c.id) === String(st.planCourseId);
          var chip = {
            namn: c.namn,
            kort: c.niva_kort || c.namn,
            sel: sel,
            onPick: function () { setState({ planCourseId: sel ? '' : String(c.id) }); },
          };
          var amne = c.amne_namn || 'Övrigt';
          if (!(amne in byAmne)) { byAmne[amne] = { amne: amne, chips: [] }; groups.push(byAmne[amne]); }
          byAmne[amne].chips.push(chip);
        });
        return groups;
      })(),
      planGroupOpts: st.groups.map(function (g) {
        var sel = String(g.id) === String(st.planGroupId);
        return { namn: g.namn, sel: sel, onPick: function () { setState({ planGroupId: sel ? '' : String(g.id) }); } };
      }),
      planHasGroups: st.groups.length > 0,
      planMoment: st.planMoment,
      planUnderlag: st.planUnderlag,
      planUnderlagBusy: !!st.planUnderlagBusy,
      onPickUnderlag: onPickUnderlag, onClearUnderlag: onClearUnderlag,
      onPlanGroup: onPlanGroup, onPlanCourse: onPlanCourse,
      onPlanMoment: onPlanMoment, onPlanMomentKey: onPlanMomentKey,
      onPlanStart: startPlanGenerate,
      planRunning: st.planPhase === 'running',
      planCanStart: !!st.planMoment.trim() && st.planPhase !== 'running',
      planLog: st.planLog, planHasLog: st.planLog.length > 0,
      planErrors: st.planErrors, planErrCount: st.planErrors.length,
      planHasBoard: !!st.planBoard, planId: st.planId,
      planIsExample: !st.planBoard,
      planChatInput: st.planChatInput,
      onPlanChatInput: onPlanChatInput, onPlanChatKey: onPlanChatKey,
      onPlanRefine: sendPlanRefine, onPlanApprove: approvePlan,
      planSavedPath: st.planSavedPath,
      planDatum: st.planDatum, planStarttid: st.planStarttid,
      onPlanDatum: onPlanDatum, onPlanStarttid: onPlanStarttid,
      // Provgeneratorn (Fas 4)
      exCourseId: st.exCourseId, exGroupId: st.exGroupId,
      // Samma chip-vokabulär som tavlan: kurs- och klassval är chips,
      // dokumenttypen ett segment — inga native selects.
      exCourseGroups: courseChipGroups(st.exCourseId, exPickCourse),
      exGroupOpts: st.groups.map(function (g) {
        return { namn: g.namn, sel: String(g.id) === String(st.exGroupId),
                 onPick: function () { exPickGroup(g.id); } };
      }),
      // Punkterna grupperas per Gy25-område som ihopfällbara valgrupper:
      // rubriken bär en räknare, varje rad är punktens egen text (kortad).
      // Osatt öppet-läge = auto: grupper med val står öppna.
      exContentGroups: (function () {
        var groups = [];
        var byRubrik = {};
        st.exContent.forEach(function (p) {
          var r = p.rubrik || 'Övrigt';
          if (!byRubrik[r]) {
            byRubrik[r] = { rubrik: r, punkter: [], valda: 0 };
            groups.push(byRubrik[r]);
          }
          var kort = (p.text || '').replace(/\s+/g, ' ').trim();
          var mening = kort.indexOf('. ');
          if (mening > 0) kort = kort.slice(0, mening);
          kort = kort.replace(/\.$/, '');
          if (kort.length > 88) kort = kort.slice(0, 87).replace(/\s+\S*$/, '') + ' …';
          var vald = !!st.exPunkter[p.id];
          if (vald) byRubrik[r].valda += 1;
          var status = p.provad ? 'redan prövat på prov' :
                       p.behandlad ? 'behandlat i undervisningen' : 'ännu inte behandlat';
          byRubrik[r].punkter.push({
            id: p.id, kort: kort, text: p.text,
            behandlad: !!p.behandlad, provad: !!p.provad,
            vald: vald, statusText: status,
            onToggle: function () { exTogglePunkt(p.id); } });
        });
        groups.forEach(function (g) {
          g.open = (g.rubrik in st.exCcOpen) ? !!st.exCcOpen[g.rubrik] : g.valda > 0;
          g.onToggleOpen = function () { exToggleGrupp(g.rubrik); };
        });
        return groups;
      })(),
      exValdaTotal: Object.keys(st.exPunkter).length,
      exTyp: st.exTyp,
      onExTypProv: function () { exPickTyp('prov'); },
      onExTypArbetsblad: function () { exPickTyp('arbetsblad'); },
      exUnderlag: st.exUnderlag, exUnderlagBusy: !!st.exUnderlagBusy,
      onPickExUnderlag: onPickExUnderlag, onClearExUnderlag: onClearExUnderlag,
      exReferensId: st.exReferensId,
      // Referensprovet är en custom popover-meny (samma mönster som
      // kartotekets filterpopovers: data-pop + mjuk hover-stängning).
      exReferensVal: st.exHistorik.filter(function (h) {
        return h.status === 'godkänt' && (h.typ || 'prov') === 'prov';
      }),
      exRefOpen: !!st.exRefOpen,
      exRefAnim: st.exRefClosing ? 'closing' : '',
      exRefOn: st.exReferensId ? 'on' : '',
      exRefToggle: exToggleRef, exRefEnter: exCancelCloseRef, exRefLeave: exSoftCloseRef,
      exRefLabel: (function () {
        var h = st.exHistorik.filter(function (x) { return String(x.id) === String(st.exReferensId); })[0];
        return h ? 'Utgår från: ' + (h.titel || 'prov') : 'Utan referensprov';
      })(),
      exRefOpts: [{ id: '', titel: 'Utan referensprov', datum: '' }].concat(
        st.exHistorik.filter(function (h) {
          return h.status === 'godkänt' && (h.typ || 'prov') === 'prov';
        })
      ).map(function (h) {
        var label = h.id === '' ? h.titel : (h.titel || 'prov') + (h.datum ? ' · ' + h.datum : '');
        return { key: 'ref' + h.id, label: label,
                 isCur: String(st.exReferensId) === String(h.id) || (!st.exReferensId && h.id === ''),
                 onSelect: function () { exPickRef(h.id); } };
      }),
      exDubbletter: (st.exam && st.exam.dubbletter) || [],
      exAntal: st.exAntal, exTid: st.exTid, exDatum: st.exDatum,
      exDelar: st.exDelar,
      onExAntal: onExAntal, onExTid: onExTid, onExDatum: onExDatum,
      onExDelar: onExDelar,
      onExStart: startExamGenerate,
      exRunning: st.exPhase === 'running',
      exCanStart: !!st.exCourseId && st.exPhase !== 'running',
      exLog: st.exLog, exHasLog: st.exLog.length > 0,
      exErrors: st.exErrors, exErrCount: st.exErrors.length,
      exMsg: st.exMsg,
      exam: (function () {
        var ex = st.exam;
        if (!ex || !ex.exam) return null;
        var cur = null;
        (ex.versions || []).forEach(function (v) { if (!cur || v.version > cur.version) cur = v; });
        return {
          id: ex.id,
          titel: ex.exam.titel || 'Prov',
          typ: ex.typ || 'prov',
          status: ex.status,
          godkant: ex.status === 'godkänt',
          versionRad: 'Version ' + ((cur && cur.version) || 1) + ' av ' + (ex.versions || []).length,
          hasPdf: !!(cur && cur.pdf_path),
          hasTex: !!(cur && cur.tex_path),
          balansRad: ex.summor ? ('Totalt ' + ex.summor.total + ' p  ·  E ' + ex.summor.e + '  ·  C ' + ex.summor.c + '  ·  A ' + ex.summor.a) : '',
          granserRad: ex.granser ? ('Kravgränser: E ' + ex.granser.E.minst + '  ·  C ' + ex.granser.C.minst + ' (varav ' + ex.granser.C.varav_ca + ' C/A)  ·  A ' + ex.granser.A.minst + ' (varav ' + ex.granser.A.varav_a + ' A)') : '',
          formagor: ex.summor ? Object.keys(ex.summor.formagor).map(function (f) {
            return { f: f, p: ex.summor.formagor[f] };
          }) : [],
          uppgifter: examNumbered(ex.exam).map(function (n) {
            return {
              nummer: n.nummer,
              del: n.u.del || '',
              formaga: n.u.formaga,
              typ: n.u.typ,
              poangStr: (n.u.poang || [0, 0, 0]).join('/'),
              text: n.u.text || '',
              chatValue: st.exChat[n.nummer] || '',
              onChat: onExChat(n.nummer),
              onSend: sendExamRefine(n.nummer),
              canSend: !!(st.exChat[n.nummer] || '').trim() && st.exPhase !== 'running',
            };
          }),
        };
      })(),
      onExApprove: approveExam, onExPdf: openExamPdf, onExTex: openExamTex,
      onExOverleaf: openInOverleaf, onExClose: closeExam,
      exDeleteArm: !!st.exDeleteArm,
      onExDeleteArm: armDeleteExam, onExDeleteCancel: cancelDeleteExam,
      onExDelete: deleteExam,
      // Planeringsarkivet (ersätter kalendern): sök/fråga + veckogrupper
      arkiv: st.tab === 'planning' ? (function () {
        var typLabel = { tavla: 'Tavla', prov: 'Prov', arbetsblad: 'Arbetsblad' };
        var items = (st.arkItems || []).map(function (it) {
          return {
            key: it.typ + '-' + it.id,
            typ: it.typ, typLabel: typLabel[it.typ] || it.typ,
            titel: it.titel || '(utan titel)',
            datum: it.datum || '', starttid: it.starttid || '',
            cc: ccOf(it),
            tag: [it.group, it.course].filter(Boolean).join(' · ') || 'Ej tilldelad',
            held: it.status === 'hållen', godkand: it.status === 'godkänt',
            cancelled: it.status === 'inställd',
            statusLabel: it.status || '',
            onOpen: function () { openArkivItem(it); },
          };
        });
        // Veckogrupper, nyaste veckan först — samma grammatik som kartoteket.
        var wMap = {};
        items.forEach(function (it) {
          var wi = weekInfo(it.datum);
          if (!wMap[wi.key]) wMap[wi.key] = { key: wi.key, num: wi.num, label: wi.label, range: wi.range, start: wi.start, rows: [] };
          wMap[wi.key].rows.push(it);
        });
        var weeks = Object.keys(wMap).map(function (k) { return wMap[k]; })
          .sort(function (a, b) { return b.start - a.start; })
          .map(function (g) {
            g.rows.sort(function (a, b) { return (b.datum + b.starttid).localeCompare(a.datum + a.starttid); });
            var n = g.rows.length;
            return { key: g.key, num: g.num, isWeek: g.num !== '·', label: g.label,
                     range: g.range, rows: g.rows,
                     count: n + (n === 1 ? ' post' : ' poster') };
          });
        var asking = !!st.arkAsking;
        var askActive = asking || !!st.arkAnswer;
        var hitCount = (st.arkSources || []).length;
        return {
          count: (st.arkItems || []).length,
          empty: (st.arkItems || []).length === 0,
          weeks: weeks,
          search: {
            query: st.arkQ,
            modeAsk: st.arkMode === 'ask', modeKeyword: st.arkMode === 'keyword',
            busy: st.arkSearching || asking,
            onInput: onArkInput, onClear: clearArkiv, onRun: runArkiv,
            onKey: function (e) { if (e.key === 'Enter') { e.preventDefault(); runArkiv(); } },
            onAsk: function () { setArkMode('ask'); },
            onKeyword: function () { setArkMode('keyword'); },
            hasQuery: !!(st.arkQ || '').trim(),
            showSuggest: st.arkMode === 'ask' && !asking && !st.arkAnswer,
            suggestions: [
              'När gick vi igenom derivatans definition?',
              'Sammanfatta vad vi har gått igenom i höst',
              'Hitta provet om sannolikhet',
            ].map(function (q) {
              return { label: q, onClick: function () { setState({ arkMode: 'ask', arkQ: q }); runArkivAsk(q); } };
            }),
            searched: Array.isArray(st.arkHits),
            showNoHits: st.arkMode === 'keyword' && Array.isArray(st.arkHits) && st.arkHits.length === 0 && !st.arkSearching,
            hits: (st.arkHits || []).map(function (h) {
              return { snippet: hl(h.snippet || ''),
                       meta: [typLabel[h.typ] || h.typ, h.group, h.course, h.datum].filter(Boolean).join(' · '),
                       name: h.titel || '(utan titel)',
                       onOpen: function () { openArkivItem(h); } };
            }),
          },
          scan: askActive ? {
            theater: buildScanModel({
              plan: st.arkScanPlan, res: st.arkScanRes || {}, shown: st.arkScanShown,
              scanning: asking, deep: st.arkDeep, noun: 'tavlor och prov',
              onNew: clearArkiv,
              deskCards: (st.arkDeep || []).map(function (s2) {
                var clickable = !asking && !!st.arkAnswer;
                return { key: s2.typ + '-' + s2.id, title: s2.titel || '(utan titel)',
                         typLabel: typLabel[s2.typ] || s2.typ,
                         sub: [s2.group, s2.course, s2.datum].filter(Boolean).join(' · '),
                         onOpen: clickable ? function (e) { if (e) e.stopPropagation(); openArkivItem(s2); } : null };
              }),
            }),
          } : null,
          q: st.arkQAsked,
          ansStarted: !!st.arkAnswer,
          ansTyping: asking && !!st.arkAnswer,
          ansDone: !asking && !!st.arkAnswer,
          ansHeadLabel: (!asking && st.arkAnswer)
            ? ('Svar — ' + hitCount + (hitCount === 1 ? ' källa' : ' källor'))
            : 'Svar',
          answer: st.arkAnswer,
          sources: (st.arkSources || []).map(function (s2) {
            return { key: 'as-' + s2.typ + '-' + s2.id,
                     typLabel: typLabel[s2.typ] || s2.typ,
                     titel: s2.titel || '(utan titel)',
                     sub: [s2.group, s2.course, s2.datum].filter(Boolean).join(' · '),
                     onOpen: function (e) { if (e) e.stopPropagation(); openArkivItem(s2); } };
          }),
          followups: (st.arkFollowups || []).map(function (f, i) {
            return { key: 'af' + i, q: f.q, a: f.a, typing: !!f.typing };
          }),
          followInput: st.arkFollowInput || '',
          setFollow: function (e) { setState({ arkFollowInput: e.target.value }); },
          onFollowKey: function (e) { if (e.key === 'Enter') { e.preventDefault(); sendArkivFollow(); } },
          sendFollow: sendArkivFollow,
        };
      })() : null,
      themeIsLight: st.theme !== 'dark',
      toggleTheme: toggleTheme,

      queueItems: queueItems, queueCount: st.queue.length, multiQueue: st.queue.length > 1, hasQueue: st.queue.length > 0,
      queueDoneCount: doneCount, queueSummary: doneCount + ' av ' + st.queue.length + ' klara',
      fileError: st.fileError, hasFileError: !!st.fileError,
      addSampleNormal: function () {
        setState({ fileError: '' });
        getJSON('/api/sample').then(function (res) {
          if (res && res.path) addFilesObjs([{ name: res.name, path: res.path }]);
          else setState({ fileError: 'Inget exempel finns på den här datorn — lägg till en egen fil.' });
        }).catch(function () { setState({ fileError: 'Inget exempel finns på den här datorn — lägg till en egen fil.' }); });
      },
      addSampleCorrupt: function () { addSample('skadad_inspelning.m4a'); },

      isError: st.run === 'error', isCancelled: st.run === 'cancelled', notErrorState: st.run !== 'error' && st.run !== 'cancelled',
      runErrorTitle: st.runError ? st.runError.title : '', runErrorDetail: st.runError ? st.runError.detail : '',
      onCancelRun: cancelRun, onResumeRun: resumeRun, onRetryRun: retryRun,

      historyItems: historyItems, historyEmpty: st.history.length === 0, historyCount: st.history.length,

      lessonItems: lessonItems, lessonsEmpty: st.lessons.length === 0,
      weekGroups: weekGroups, recEmpty: st.lessons.length > 0 && lessonItems.length === 0,
      archiveCountLabel: 'Arkiv — ' + st.lessons.length + (st.lessons.length === 1 ? ' inspelning' : ' inspelningar') + ' i minnet',
      askActive: askActive,
      // Kartotekets live-skanning + inline-svar (ersätter tänker-bannern + svarsmodalen)
      askScan: askActive ? {
        theater: buildScanModel({
          plan: scanPlan, res: st.askScanRes || {}, shown: st.askScanShown,
          scanning: scanning, deep: st.askDeep, noun: 'inspelningar',
          onNew: clearSearch,
          deskCards: (st.askDeep || []).map(function (s2) {
            var clickable = !st.asking && !!st.askAnswer;
            return { key: s2.lesson_id, title: s2.name || '(namnlös)',
                     sub: [s2.group, s2.course, s2.datum].filter(Boolean).join(' · '),
                     onOpen: clickable ? function (e) { if (e) e.stopPropagation(); openCitePeek(s2, st.askQ, st.askAnswer); } : null };
          }),
        }),
        q: st.askQ,
        onNew: clearSearch,
        ansStarted: !!st.askAnswer,
        ansTyping: st.asking && !!st.askAnswer,
        ansDone: !st.asking && !!st.askAnswer,
        ansHeadLabel: (!st.asking && st.askAnswer)
          ? ('Svar — ' + (st.askSources || []).length + ((st.askSources || []).length === 1 ? ' källa' : ' källor'))
          : 'Svar',
        answer: st.askAnswer,
        // Klickbara sifferkällor i svaret (samma källförankring som lektions-
        // chatten): [n] parsas när svaret är klart; klick öppnar inspelningen
        // och hoppar till stället i transkriptet där frågans termer förekommer.
        ansTokens: (function () {
          if (st.asking || !st.askAnswer) return null;
          var srcs = st.askSources || [];
          if (!srcs.length) return null;
          var cited = parseChatCites(st.askAnswer,
            srcs.map(function (s2) { return { time: '', text: s2.name || '' }; }));
          if (!cited) return null;
          return cited.tokens.map(function (tk) {
            if (tk.cite === undefined) return { isText: true, text: tk.text };
            var s2 = srcs[tk.segIdx];
            return { isCite: true, num: tk.cite,
                     label: [s2 && s2.name, s2 && s2.datum].filter(Boolean).join(' · '),
                     onCite: function (e) { if (e) e.stopPropagation(); openCitePeek(s2, st.askQ, st.askAnswer); } };
          });
        })(),
        // Zoom till modal (data-askwrap/data-askzoom) — klick förstorar, Esc/klick utanför stänger
        askZoomFlag: st.askZoom ? (st.askZoomClosing ? 'closing' : 'on') : '',
        askZoomOn: !!st.askZoom && !st.askZoomClosing,
        onAskCardClick: function (e) { if (e) e.stopPropagation(); if (!st.askZoom) openAskZoom(); },
        closeAskZoom: function () { closeAskZoom(); },
        // Hopfällbar källpanel till höger; källraderna öppnar lektionen
        // (RAG-svaret saknar radnivå-källor — medveten avvikelse från mallens inline-utdrag)
        ansHasRefs: !st.asking && !!st.askAnswer && (st.askSources || []).length > 0,
        askRefCount: String((st.askSources || []).length),
        srcBoxOpen: !!st.srcBox,
        srcChevFlag: st.srcBox ? 'open' : '',
        toggleSrcBox: function (e) { if (e) e.stopPropagation(); toggleSrcBox(); },
        askRefs: (st.askSources || []).map(function (s2, ri) {
          return { key: 'rf' + ri, rec: s2.name || '(namnlös)',
                   meta: s2.datum || '',
                   text: [s2.group, s2.course].filter(Boolean).join(' · '),
                   onPick: function (e) { if (e) e.stopPropagation(); openLessonChat(s2); } };
        }),
        // Följdfrågor — riktiga omfrågor mot arkivet
        askFollowups: (st.askFollowups || []).map(function (f, i) {
          return { key: 'f' + i, q: f.q, a: f.a, typing: !!f.typing };
        }),
        askFollowInput: st.askFollowInput || '',
        setAskFollow: function (e) { setState({ askFollowInput: e.target.value }); },
        onAskFollowKey: function (e) { if (e.key === 'Enter') { e.preventDefault(); sendAskFollow(); } },
        sendAskFollow: sendAskFollow,
        // Kalenderförslag i arkivsvaret — knapp + samma box som i overlayen
        proposeAskCal: function (e) { if (e) e.stopPropagation(); if (!st.askEvent) proposeAskEvent(st.askQ); },
        askEvent: st.askEvent ? evBoxVM('ask', st) : null,
        sources: (st.askSources || []).map(function (s2) {
          return { rec: s2.name || '(namnlös)',
                   sub: [s2.group, s2.course, s2.datum].filter(Boolean).join(' · '),
                   onCite: function (e) { if (e) e.stopPropagation(); openLessonChat(s2); } };
        }),
      } : null,
      lessonGroups: st.groups, lessonCourses: st.courses,
      lessonMonths: lessonMonths, lessonFilterMonth: st.lessonFilterMonth,
      onClearFilters: clearLessonFilters,
      onClearGroup: function () { setLessonFilter('lessonFilterGroup', ''); },
      onClearCourse: function () { setLessonFilter('lessonFilterCourse', ''); },
      onClearMonth: function () { setMonthFilter(''); },
      hasGroups: st.groups.length > 0, hasCourses: st.courses.length > 0, hasMonths: lessonMonths.length > 0,
      filterGroupLabel: (st.groups.find(function (g) { return String(g.id) === String(st.lessonFilterGroup); }) || {}).namn || '',
      filterCourseLabel: (st.courses.find(function (c) { return String(c.id) === String(st.lessonFilterCourse); }) || {}).namn || '',
      hasActiveFilter: !!(st.lessonFilterGroup || st.lessonFilterCourse || st.lessonFilterMonth),
      // Filterpopovers (mallens custom dropdowns med mjuk stängning)
      fPopAnim: st.filterClosing ? 'closing' : '',
      fEnter: cancelCloseFilter, fLeave: softCloseFilter,
      fKlassOpen: st.filterOpen === 'klass', fKursOpen: st.filterOpen === 'kurs', fDatumOpen: st.filterOpen === 'datum',
      fKlassToggle: function () { toggleFilter('klass'); },
      fKursToggle: function () { toggleFilter('kurs'); },
      fDatumToggle: function () { toggleFilter('datum'); },
      klassSelOn: st.lessonFilterGroup ? 'on' : '',
      kursSelOn: st.lessonFilterCourse ? 'on' : '',
      datumSelOn: st.lessonFilterMonth ? 'on' : '',
      klassMenuOpts: [{ id: '', namn: 'Alla klasser' }].concat(st.groups).map(function (g) {
        return { key: 'g' + g.id, label: g.namn, isCur: String(st.lessonFilterGroup) === String(g.id) || (!st.lessonFilterGroup && g.id === ''),
                 onSelect: function () { pickFilter('klass', g.id); } };
      }),
      kursMenuOpts: [{ id: '', namn: 'Alla kurser' }].concat(st.courses).map(function (c) {
        return { key: 'c' + c.id, label: c.namn, isCur: String(st.lessonFilterCourse) === String(c.id) || (!st.lessonFilterCourse && c.id === ''),
                 onSelect: function () { pickFilter('kurs', c.id); } };
      }),
      datumMenuOpts: [{ ym: '', label: 'Alla datum' }].concat(lessonMonths.map(function (m) {
        var p = String(m).split('-');
        return { ym: m, label: (_MON_SV[parseInt(p[1], 10) - 1] || p[1]) + ' ' + p[0] };
      })).map(function (o) {
        return { key: 'd' + o.ym, label: o.label, isCur: (st.lessonFilterMonth || '') === o.ym,
                 onSelect: function () { pickFilter('datum', o.ym); } };
      }),
      fKlassLabel: (function () { var n = (st.groups.find(function (g) { return String(g.id) === String(st.lessonFilterGroup); }) || {}).namn; return n ? 'Klass · ' + n : 'Alla klasser'; })(),
      fKursLabel: (function () { var n = (st.courses.find(function (c) { return String(c.id) === String(st.lessonFilterCourse); }) || {}).namn; return n ? 'Kurs · ' + n : 'Alla kurser'; })(),
      fDatumLabel: st.lessonFilterMonth
        ? (function () { var p = st.lessonFilterMonth.split('-'); return 'Datum · ' + (_MON_SV[parseInt(p[1], 10) - 1] || p[1]) + ' ' + p[0]; })()
        : 'Alla datum',
      prep: st.nextPrep ? {
        group: st.nextPrep.group,
        lastDate: st.nextPrep.last_lesson ? (st.nextPrep.last_lesson.datum || '') : '',
        actions: (st.nextPrep.open_actions || []).map(function (a) {
          return { id: a.id, text: a.text, typLabel: TYP_LABEL[a.typ] || a.typ,
                   ref: a.ref || '', date: a.lesson_datum || '', onDone: function () { markPrepDone(a.id); } };
        }),
        difficulties: (st.nextPrep.difficulties || []).map(function (d) { return { text: d.text, ref: d.ref || '' }; }),
        empty: (st.nextPrep.open_actions || []).length === 0 && (st.nextPrep.difficulties || []).length === 0,
      } : null,

      trends: st.trends ? (function () {
        var t = st.trends;
        var act = t.actions || { open: 0, done: 0 };
        var actTotal = act.open + act.done;
        return {
          group: t.group, lessons: t.lessons, analysed: t.analysed,
          counts: [
            { label: 'Svårigheter', n: t.counts['svårighet'] || 0 },
            { label: 'Åtgärder', n: t.counts['åtgärd'] || 0 },
            { label: 'Kalender', n: t.counts['kalender'] || 0 },
            { label: 'Grupprum', n: t.counts['grupprum'] || 0 },
            { label: 'Material', n: t.counts['material'] || 0 },
          ],
          actOpen: act.open, actDone: act.done, actTotal: actTotal,
          actPct: actTotal ? Math.round(act.done / actTotal * 100) : 0,
          difficulties: (t.top_difficulties || []).map(function (d) {
            return { text: d.text, count: d.count, recurring: d.count > 1,
                     refs: (d.refs || []).join(', ') };
          }),
          empty: t.lessons === 0,
        };
      })() : null,

      backup: { busy: st.backingUp, onRun: backupNow },

      agenda: (function () {
        var items = st.agenda || [];
        var open = items.filter(function (a) { return a.status !== 'klar'; });
        return {
          loaded: Array.isArray(st.agenda), count: open.length, total: items.length,
          overdueCount: open.filter(function (a) { return a.overdue; }).length,
          isOpen: st.agendaOpen, onToggle: toggleAgenda,
          exporting: st.agendaExporting, onExport: exportAgendaIcs,
          items: items.map(function (a) {
            return {
              text: a.text || '',
              meta: [a.group, a.course, a.lesson_name].filter(Boolean).join(' · '),
              due: a.due_date || '', overdue: !!a.overdue, today: !!a.today,
              done: a.status === 'klar', typLabel: TYP_LABEL[a.typ] || a.typ,
              onDone: function () { markAgendaDone(a.id); },
            };
          }),
        };
      })(),

      lessonsSearch: {
        query: st.lessonSearch, mode: st.searchMode,
        modeKeyword: st.searchMode === 'keyword', modeAsk: st.searchMode === 'ask',
        busy: st.searching || st.asking,
        onInput: onSearchInput, onClear: clearSearch, onRun: runSearch,
        onKey: function (e) { if (e.key === 'Enter') { e.preventDefault(); runSearch(); } },
        onKeyword: function () { setSearchMode('keyword'); },
        onAsk: function () { setSearchMode('ask'); },
        hasQuery: !!(st.lessonSearch || '').trim(),
        // förslagschips (mallens askSuggestions) — visas i AI-läget före första frågan
        showSuggest: st.searchMode === 'ask' && !st.asking && !st.askAnswer,
        suggestions: [
          'Var förklarar jag täljare och nämnare?',
          'Vilka lektioner tar upp procent?',
        ].map(function (q) {
          return { label: q, onClick: function () { setState({ searchMode: 'ask', lessonSearch: q }); runAsk(q); } };
        }),
        // keyword-läge
        hits: (st.searchHits || []).map(function (h) {
          return { snippet: hl(h.snippet || ''),
                   meta: [h.group, h.course, h.date || h.datum].filter(Boolean).join(' · ') || 'Ej tilldelad',
                   name: h.name || '(namnlös)', onOpen: function () { openSearchHit(h); } };
        }),
        showNoHits: st.searchMode === 'keyword' && Array.isArray(st.searchHits) && st.searchHits.length === 0 && !st.searching,
        searched: Array.isArray(st.searchHits),
        // fråga-läge (RAG)
        answer: st.askAnswer, asking: st.asking, hasAnswer: !!st.askAnswer,
        sources: (st.askSources || []).map(function (s2) {
          return { label: [s2.group, s2.course, s2.datum, s2.name].filter(Boolean).join(' · '),
                   onOpen: function () { openSearchHit(s2); } };
        }),
      },

      waveBars: waveBars, audioPlaying: st.audioPlaying, audioPaused: !st.audioPlaying,
      audioCur: fmtTime(st.audioT), audioDur: fmtTime(dur),
      mediaUrl: st.mediaUrl, hasMediaEl: !!st.mediaUrl, mediaRef: mediaRef,
      onTogglePlay: togglePlay, onSeekClick: onSeekClick, onSeekKey: onSeekKey, seekTrackRef: seekTrackRef,
      seekMax: Math.round(dur), seekNow: Math.round(st.audioT || 0),
      markers: (st.markers || []).map(function (m) {
        return { id: m.id, t: m.t || 0, label: fmtTime(m.t || 0),
                 onSeek: function () { seekToTime(m.t || 0); },
                 onDelete: function () { deleteMarker(m.id); } };
      }),
      hasMarkers: (st.markers || []).length > 0, onAddMarker: addPlaybackMarker,
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
      recording: st.recording, recElapsedFmt: fmtTime(st.recElapsed), recSupported: recSupported(),
      recError: st.recError, hasRecError: !!st.recError, recMarkerCount: st.recMarkerCount,
      recLevelPct: Math.round((st.recLevel || 0) * 100), recSilent: st.recSilent,
      onStartRec: startRecording, onStopRec: stopRecording, onCancelRec: cancelRecording, onMarkRec: addRecMarker,
      incompleteRecs: (st.incompleteRecs || []).map(function (r) {
        return { session: r.session, label: (r.size || '') + (r.modified ? ' · ' + r.modified : ''),
                 onRecover: function () { recoverIncomplete(r.session); },
                 onDiscard: function () { discardIncomplete(r.session); } };
      }),
      hasIncompleteRecs: (st.incompleteRecs || []).length > 0,
      dropzoneStyle: 'position:relative;border:1.5px dashed ' + (st.dragging ? 'var(--accent)' : 'var(--line-2)') + ';border-radius:20px;background:' + (st.dragging ? 'var(--accent-weak)' : 'var(--surface)') + ';flex:1 1 auto;min-height:200px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:32px 24px;text-align:center;box-shadow:var(--shadow-sm);cursor:pointer;user-select:none;-webkit-user-select:none;transition:border-color .12s,background .12s',
      curModelName: st.model ? (curModel.label || curModel.id) : ('Ingen modell för ' + (st.language === 'en' ? 'engelska' : 'svenska')),
      curModelMeta: st.model ? ('Väljs automatiskt · ' + (st.language === 'en' ? 'Engelska' : 'Svenska')) : 'Ingen modell installerad för språket — kontrollera installationen',
      curModelDot: st.model ? curFit.dot : 'var(--bad)',
      langOptions: langOptions, formatChips: formatChips,
      targetLangOptions: targetLangOptions, translateNote: translateNote,
      isTranslating: isTranslating, transTag: isTranslating ? 'Översätter' : 'Samma språk',
      transHint: transHint,
      modelFootMeta: st.model ? 'väljs automatiskt' : 'ingen modell installerad för språket',
      subtitleOptions: subtitleOptions, embedOptions: embedOptions,
      showSubtitleMode: _activeIsVideo, showEmbed: st.subtitleMode === 'embed' && _activeIsVideo,
      audioCorrect: st.audioCorrect, onToggleAudioCorrect: toggleAudioCorrect,
      audioModelInstalled: st.audioModelInstalled, audioModelDownloading: st.audioModelDownloading,
      onDownloadAudioModel: downloadAudioModel,
      acSwitchTrack: 'position:relative;width:42px;height:25px;border-radius:999px;flex:0 0 auto;background:' + (st.audioCorrect ? 'var(--ink)' : 'var(--line-2)') + ';transition:background .15s;cursor:pointer',
      acSwitchKnob: 'position:absolute;top:3px;left:3px;width:19px;height:19px;border-radius:50%;background:var(--knob);border:1px solid var(--line);box-shadow:var(--shadow-sm);transition:transform .15s;transform:translateX(' + (st.audioCorrect ? '17px' : '0') + ')',

      onStart: start, isRunning: isRunning, notRunning: !isRunning, startReady: st.catalogReady,
      startBtnLabel: !st.catalogReady ? 'Laddar modeller…' : (st.catalogReady && !st.model) ? 'Ladda ner en modell först' : isRunning ? 'Transkriberar…' : isDone ? 'Kör igen' : (st.queue.length > 1 ? 'Starta · ' + st.queue.length + ' filer' : 'Starta transkribering'),
      startBtnStyle: coralBtn(isRunning) + ';width:100%;padding:16px 24px;font-size:16.5px',
      startBtnStyleBar: primaryBtn(isRunning) + ';padding:12px 22px;font-size:15px;border-radius:11px;flex:0 0 auto',

      showStatus: st.step === 'process',
      statusBadge: st.run === 'error' ? 'FEL' : st.run === 'cancelled' ? 'AVBRUTEN' : isDone ? 'KLAR' : 'KÖR',
      statusBadgeStyle: (function (col) { return "font-size:12px;font-weight:500;color:" + col + ";background:color-mix(in srgb," + col + " 14%,transparent);padding:3px 9px;border-radius:6px;letter-spacing:0.05em"; })(st.run === 'error' ? 'var(--bad)' : st.run === 'cancelled' ? 'var(--ink-3)' : isDone ? 'var(--ok)' : 'var(--accent)'),
      statusFile: baseName(), elapsedLabel: fmtTime(st.elapsed), progressLabel: Math.round(isDone ? 100 : (st.dispProgress || 0)) + '%', steps: steps,
      logText: st.log.join('\n'), logRows: logRows, logClipped: logRows.length > 3,
      logOpen: st.logOpen, openLog: openLog, closeLog: closeLog,
      calSetupOpen: !!st.calSetupOpen,
      calSetup: {
        connected: st.calConnected === true,
        clientReady: st.calClientReady === true,
        busy: !!st.calBusy,
        onClose: closeCalSetup, onOpenConsole: openGoogleConsole,
        onPickFile: pickClientSecret, onLogin: connectCalendar,
        clientFileRef: clientFileRef, onClientFile: onPickClientSecret,
      },
      hasToast: !!st.toast, toastName: st.toast && st.toast.name,
      toastError: !!(st.toast && st.toast.kind === 'error'),
      toastLoading: !!st.toast && !st.toast.done && !(st.toast && st.toast.kind === 'error'), toastDone: !!st.toast && st.toast.done,
      toastMessage: st.toast ? (st.toast.detail || st.toast.name || '') : '',
      toastTitle: st.toast ? (st.toast.title || (st.toast.kind === 'error' ? 'Något gick fel' : st.toast.done ? 'Nedladdning klar' : 'Laddar ner …')) : '', closeToast: closeToast,
      toastPct: st.toast ? Math.round(st.toast.pct || 0) : 0, toastDetail: st.toast ? (st.toast.detail != null ? st.toast.detail : toastDetail(st.toast.size, st.toast.pct || 0)) : '',
      toastBarStyle: 'height:100%;width:100%;transform-origin:left;transform:scaleX(' + ((st.toast ? Math.round(st.toast.pct || 0) : 0) / 100) + ');background:var(--accent);border-radius:99px;transition:transform .14s linear',
      transcriptOpen: st.transcriptOpen, closeTranscript: closeTranscript, transcriptFile: baseName() + '.txt',
      searchQuery: st.searchQuery, onTSearch: onTSearch, onSearchKey: onSearchKey, searchRef: searchRef, scrollRef: scrollRef,
      nextMatch: nextMatch, prevMatch: prevMatch, matchLabel: matchLabel, tLines: tLines,

      // Fire-and-forget-avslutningen (design 14 juli): kort "Klart"-rad, sedan
      // öppnas Inspelningar automatiskt (finishTranscribe).
      showDone: isDone,
      procLede: willCorrect()
        ? 'Transkriberas och korrekturläses automatiskt mot ljudet med Gemma 3n. När allt är klart landar lektionen i Inspelningar.'
        : 'Transkriberas lokalt på din dator. När allt är klart landar lektionen i Inspelningar.',
      runningNote: (willCorrect() ? 'Transkriberar och korrekturläser' : 'Transkriberar') + ' … Inspelningar öppnas när det är klart',
      doneNote: willCorrect() ? 'Klart — korrekturläst och sparad. Öppnar Inspelningar …' : 'Klart — sparad. Öppnar Inspelningar …',
      ppModel: st.ppModel,
      logExpand: st.logExpand, toggleLogExpand: toggleLogExpand,
      logToggleLabel: st.logExpand ? 'Dölj' : 'Visa',
      stop: stopProp,
      citePeek: st.citePeek ? {
        anim: st.citePeekClosing ? 'closing' : '',
        name: st.citePeek.name, meta: st.citePeek.meta,
        loading: !!st.citePeek.loading,
        rows: st.citePeek.rows || [],
        empty: !st.citePeek.loading && !(st.citePeek.rows || []).length,
        more: st.citePeek.more || 0,
        onClose: closeCitePeek, onOpenChat: citePeekOpenChat,
      } : null,

      // Lektionsoverlay (fullskärm): transkript + chatt + kalenderförslag
      lessonChatOpen: !!st.lessonChatId,
      lessonChatName: st.lessonChatName,
      lessonChatLoading: !!st.lessonChatId && st.lessonChatSegs.length === 0,
      closeLessonChat: closeLessonChat,
      // Redigeringsmodal för lektionsuppgifter (pennan på kortet ersätter
      // mallens borttagna inline-fält; utökad med Sal + Datum som appen har)
      renameOpen: !!st.editingLesson,
      renameName: (st.lessonEdits || {}).name || '',
      renameGroup: (st.lessonEdits || {}).group || '',
      renameCourse: (st.lessonEdits || {}).course || '',
      renameSal: (st.lessonEdits || {}).sal || '',
      renameDatum: (st.lessonEdits || {}).datum || '',
      onRenameGroup: function (e) { onLessonField('group', e.target.value); },
      onRenameCourse: function (e) { onLessonField('course', e.target.value); },
      onRenameSal: function (e) { onLessonField('sal', e.target.value); },
      onRenameDatum: function (e) { onLessonField('datum', e.target.value); },
      onRenameSave: function () { saveLesson(st.editingLesson); },
      onRenameCancel: cancelEditLesson,

      ovCc: (st.lessonChatMeta || {}).cc || 'none',
      ovTag: (function () { var m = st.lessonChatMeta || {}; return m.group ? (m.group + (m.course ? ' · ' + m.course : '')) : (m.course || 'Ej tilldelad'); })(),
      ovMeta: (function () { var m = st.lessonChatMeta || {}; return [m.date, m.dur, m.model, m.lang].filter(Boolean).join(' · '); })(),
      ovRows: st.lessonChatSegs.map(function (seg) {
        var hit = !!st.lessonChatHitT && st.lessonChatHitT === seg.time;
        return { t: seg.time, txt: seg.text, hit: hit, norm: !hit };
      }),
      ovHasHit: !!st.lessonChatHitT, ovHitT: st.lessonChatHitT || '',
      ovHitClear: function () { setState({ lessonChatHitT: null, lessonChatCiteSel: null }); },
      ovDescView: !!st.ovDescView,
      ovDescOpen: function () { setState({ ovDescView: true }); },
      ovDescClose: function () { setState({ ovDescView: false }); },
      // Stäng overlayn först — transkriptmodalen (z 100) ligger annars under overlayn (z 120).
      ovOpenFull: function () { var hid = st.lessonChatId; closeLessonChat(); openLesson({ history_id: hid }); },
      ovHasLesson: !!(st.lessonChatMeta && st.lessonChatMeta.lessonId),
      ovAskSum: function () { sendLessonChat('Sammanfatta lektionen i tre punkter'); },
      ovAskStud: function () { sendLessonChat('Vilka elever nämns och varför?'); },
      ovAskRemind: function () { sendLessonChat('Skapa en läxpåminnelse utifrån lektionen'); },
      // Guardad: klick när ett förslag redan finns fäller ut det i stället för att skriva över.
      proposeOvEvent: function () { if (S.lessonChatEvent) setState({ ovEvOpen: true }); else proposeLessonEvent(); },
      ovEvent: st.lessonChatEvent ? evBoxVM('lesson', st) : null,
      ovEvOpen: !!st.ovEvOpen,
      toggleOvEv: function () { setState(function (s) { return { ovEvOpen: !s.ovEvOpen }; }); },
      // Anteckningens inzoomade redigeringsmodal (design 14 juli)
      descModalOpen: !!st.descModal,
      descModalAnim: st.descModalClosing ? 'closing' : '',
      closeDescModal: closeDescModal,
      descModalVal: ((st.descModalFor === 'ask' ? st.askEvent : st.lessonChatEvent) || {}).desc || '',
      setDescModalVal: function (e) { setEvField(st.descModalFor === 'ask' ? 'ask' : 'lesson', 'desc', e.target.value); },
      lessonChatThread: {
        chatEmpty: st.lessonChat.length === 0,
        chatHasMsgs: st.lessonChat.length > 0,
        chat: buildChatMessages(st.lessonChat, st.lessonChatSegs, st.lessonChatCiteSel, selectLessonChatCite, st.lessonChatTyping, st.reasonOpen, toggleReason),
        chatTyping: st.lessonChatTyping,
        chatInput: st.lessonChatInput,
        onChatInput: onLessonChatInput, onChatKey: onLessonChatKey, onChatSend: sendLessonChat,
        chatThink: st.lessonChatThink, onToggleChatThink: toggleLessonChatThink,
        chatThinkBtnStyle: 'display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:500;font-family:inherit;cursor:pointer;border-radius:99px;padding:6px 12px;border:1px solid ' + (st.lessonChatThink ? 'color-mix(in srgb,var(--accent) 40%,transparent);background:var(--accent-weak);color:var(--accent)' : 'var(--line);background:var(--surface);color:var(--ink-2)'),
        chatThinkHint: st.lessonChatThink ? 'Tänker djupare före svar — bättre på svåra flerstegsfrågor, men något långsammare.' : 'Snabbt svar utan synligt resonemang. Slå på för svåra flerstegsfrågor.',
        ppModel: st.ppModel, ovModelTitle: 'Språkmodell: ' + st.ppModel, openTranscript: null,
      },

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
        // Tavel-iframen ägs av whiteboard-motorn — morphdom får aldrig
        // röra den (en diff skulle ladda om dokumentet och tömma tavlan).
        if (from.nodeType === 1 && from.hasAttribute('data-wb-frame')) return false;
        return true;
      },
    });
    root.querySelectorAll('[data-ref]').forEach(function (el) { var f = H[+el.dataset.ref]; if (typeof f === 'function') f(el); });
    applySideEffects();
    renderMathIn(root);
    var cbs = pendingCbs; pendingCbs = []; cbs.forEach(function (cb) { try { cb(); } catch (e) {} });
  }

  /* KaTeX-rendering av $…$-segment i element märkta data-math (provkortets
     uppgiftstexter). Körs efter varje render — morphdom återställer texten
     från templaten, så passet är idempotent. Obalanserade $ lämnas som text. */
  function renderMathIn(root) {
    if (!window.katex) return;
    root.querySelectorAll('[data-math]').forEach(function (el) {
      var txt = el.textContent;
      if (txt.indexOf('$') === -1) return;
      var parts = txt.split('$');
      if (parts.length < 3) return;
      var html = '';
      for (var i = 0; i < parts.length; i++) {
        if (i % 2 === 0 || i === parts.length - 1) { html += esc(parts[i]); continue; }
        try {
          html += katex.renderToString(parts[i], { throwOnError: false, output: 'html' });
        } catch (e) { html += esc('$' + parts[i] + '$'); }
      }
      el.innerHTML = html;
    });
  }

  /* event delegation: data-click / -input / -change / -keydown / -enter / -leave / -dragover / -dragleave / -drop */
  function dispatch(el, key, e) { if (!el) return; var idx = el.getAttribute('data-' + key); if (idx == null) return; var fn = H[+idx]; if (typeof fn === 'function') fn(e); }
  function bindEvents(root) {
    root.addEventListener('click', function (e) { var el = e.target.closest('[data-click]'); dispatch(el, 'click', e); });
    root.addEventListener('input', function (e) { var el = e.target.closest('[data-input]'); dispatch(el, 'input', e); });
    root.addEventListener('change', function (e) { var el = e.target.closest('[data-change]'); dispatch(el, 'change', e); });
    root.addEventListener('keydown', function (e) {
      var el = e.target.closest('[data-keydown]'); dispatch(el, 'keydown', e);
      // Tangentbordsaktivering för egna kontroller: fokuserbara div/span med
      // data-click aktiveras med Enter/Mellanslag, precis som en riktig <button>.
      if (e.defaultPrevented) return;
      if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
      var t = e.target, tn = t.tagName;
      if (tn === 'INPUT' || tn === 'TEXTAREA' || tn === 'SELECT' || t.isContentEditable) return;
      var ck = t.closest('[data-click]');
      if (!ck) return;
      var ctag = ck.tagName;
      if (ctag === 'BUTTON' || ctag === 'A') return;                 // native aktivering finns redan
      if (ck.getAttribute('tabindex') == null || ck.getAttribute('role') === 'slider') return;
      e.preventDefault();
      dispatch(ck, 'click', e);
    });
    root.addEventListener('dragover', function (e) { var el = e.target.closest('[data-dragover]'); if (el) dispatch(el, 'dragover', e); });
    root.addEventListener('dragleave', function (e) { var el = e.target.closest('[data-dragleave]'); if (el) dispatch(el, 'dragleave', e); });
    root.addEventListener('drop', function (e) { var el = e.target.closest('[data-drop]'); if (el) dispatch(el, 'drop', e); });
    // hover: data-sh visual styles + data-enter/data-leave handlers (tooltips)
    // <button> hoppas över: knapparnas hover ägs av det enhetliga knappspråket
    // i style.css (editorial); inline !important skulle annars vinna över det.
    root.addEventListener('pointerover', function (e) {
      var sh = e.target.closest('[data-sh]');
      if (sh && sh.tagName === 'BUTTON') sh = null;
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
    '<header style="position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:16px;padding:16px 20px;border-bottom:1px solid var(--line);background:color-mix(in srgb, var(--canvas) 82%, transparent);backdrop-filter:saturate(1.4) blur(14px)">' +
      '<div style="display:flex;align-items:center;gap:11px;flex:1 1 0;min-width:0;overflow:hidden">' +
        '<div style="display:flex;align-items:flex-end;gap:2.5px;height:20px">' +
          '<div style="width:3px;height:7px;border-radius:2px;background:var(--ink)"></div>' +
          '<div style="width:3px;height:14px;border-radius:2px;background:var(--ink)"></div>' +
          '<div style="width:3px;height:20px;border-radius:2px;background:var(--accent)"></div>' +
          '<div style="width:3px;height:11px;border-radius:2px;background:var(--ink)"></div>' +
          '<div style="width:3px;height:16px;border-radius:2px;background:var(--ink)"></div>' +
        '</div>' +
        '<span style="font-size:18.5px;font-weight:500;letter-spacing:-0.01em;text-transform:lowercase">transkrib<span class="ser" style="font-size:20px;color:var(--ink)">era</span></span>' +
      '</div>' +
      '<nav style="flex:0 1 auto;min-width:0;display:flex;justify-content:center">' +
        '<div style="display:inline-flex;gap:3px;padding:4px;background:var(--track);border-radius:12px;border:1px solid var(--line)">' +
          '<button data-click="' + on(v.onTabT) + '" aria-pressed="' + v.tabTOn + '" data-seg="' + (v.tabTOn ? 'on' : 'off') + '" style="border:none;border-radius:9px;padding:8px 15px;font-size:15.5px;font-weight:500;cursor:pointer;font-family:inherit;white-space:nowrap;background:transparent;color:var(--ink-2);transition:background .12s,color .12s,box-shadow .12s">Transkribera</button>' +
          '<button data-click="' + on(v.onTabIn) + '" aria-pressed="' + v.tabInOn + '" data-seg="' + (v.tabInOn ? 'on' : 'off') + '" style="border:none;border-radius:9px;padding:8px 15px;font-size:15.5px;font-weight:500;cursor:pointer;font-family:inherit;white-space:nowrap;background:transparent;color:var(--ink-2);transition:background .12s,color .12s,box-shadow .12s">Inspelningar</button>' +
          '<button data-click="' + on(v.onTabP) + '" aria-pressed="' + v.tabPlOn + '" data-seg="' + (v.tabPlOn ? 'on' : 'off') + '" style="border:none;border-radius:9px;padding:8px 15px;font-size:15.5px;font-weight:500;cursor:pointer;font-family:inherit;white-space:nowrap;background:transparent;color:var(--ink-2);transition:background .12s,color .12s,box-shadow .12s">Planering</button>' +
        '</div>' +
      '</nav>' +
      '<div style="flex:1 1 0;min-width:0;display:flex;justify-content:flex-end;align-items:center;gap:8px">' +
        '<button data-click="' + on(v.toggleTheme) + '" aria-label="Växla tema" title="Växla tema" style="width:38px;height:38px;border-radius:10px;border:1px solid var(--line);background:var(--surface);color:var(--ink-2);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:16px;transition:background .12s">' +
          (v.themeIsLight
            ? '<svg width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M15.5 11.2A6.2 6.2 0 0 1 6.8 2.5 6.2 6.2 0 1 0 15.5 11.2z"></path></svg>'
            : '<svg width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="9" r="3.4"></circle><path d="M9 1.7v1.6M9 14.7v1.6M16.3 9h-1.6M3.3 9H1.7M14.16 3.84l-1.13 1.13M4.97 13.03l-1.13 1.13M14.16 14.16l-1.13-1.13M4.97 4.97 3.84 3.84"></path></svg>') +
        '</button>' +
      '</div>' +
    '</header>';
  }

  // <<<VIEWS_START>>> (Phase-2 views — ported verbatim from prototype, verified)
function viewTranscribe(v){ return `
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
        <div class="ehead ehead--v1">
          <div class="v1-lead">
            <div class="eyebrow" style="margin-bottom:14px">Steg 1 — Källa</div>
            <h1 class="disp" style="font-size:clamp(34px,5.2vw,52px);margin:0">Vad vill du <span class="ser">transkribera?</span></h1>
          </div>
          <p class="ehead_lede v1-lede">Dra in en eller flera filer, eller välj från datorn — allt körs på din egen dator.</p>
        </div>
        <div data-click="${on(v.openPicker)}" data-dragover="${on(v.onDragOver)}" data-dragleave="${on(v.onDragLeave)}" data-drop="${on(v.onDrop)}" role="button" tabindex="0" aria-label="Välj eller dra in ljud- eller videofiler" style="${v.dropzoneStyle}">
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
            <input value="${esc(v.urlInput)}" data-input="${on(v.onUrlInput)}" data-keydown="${on(v.onUrlKey)}" aria-label="YouTube-länk" placeholder="Klistra in en YouTube-länk …" style="flex:1;min-width:0;border:none;outline:none;background:transparent;font-size:15px;color:var(--ink);font-family:inherit">
            <button data-click="${on(v.onAddUrl)}" style="flex:0 0 auto;display:inline-flex;align-items:center;gap:6px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:8px;padding:8px 15px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="background:color-mix(in srgb, var(--btn-bg) 78%, var(--accent)) !important">Lägg till</button>
          </div>
        </div>

        ${ v.hasIncompleteRecs ? `
          <div style="margin-top:14px;background:color-mix(in srgb,var(--accent) 7%,var(--surface));border:1px solid color-mix(in srgb,var(--accent) 30%,transparent);border-radius:12px;padding:13px 15px">
            <div style="font-size:13.5px;font-weight:600;color:var(--ink);margin-bottom:9px">⚠️ Oavslutad inspelning hittad</div>
            <div style="display:flex;flex-direction:column;gap:8px">
              ${ v.incompleteRecs.map(function(r){ return `
                <div style="display:flex;align-items:center;gap:10px;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:8px 11px">
                  <span style="flex:1;min-width:0;font-size:13.5px;color:var(--ink-2)">${esc(r.label)}</span>
                  <button data-click="${on(r.onRecover)}" style="flex:0 0 auto;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:8px;padding:7px 13px;font-size:13px;font-weight:500;cursor:pointer;font-family:inherit">Återställ</button>
                  <button data-click="${on(r.onDiscard)}" style="flex:0 0 auto;background:var(--surface);border:1px solid var(--line);color:var(--ink-2);border-radius:8px;padding:7px 11px;font-size:13px;cursor:pointer;font-family:inherit" data-sh="border-color:var(--bad) !important;color:var(--bad) !important">Släng</button>
                </div>
              `; }).join('') }
            </div>
          </div>
        ` : '' }

        <div style="display:flex;align-items:center;gap:10px;margin-top:12px">
          <span style="font-size:11.5px;text-transform:uppercase;letter-spacing:0.05em;color:var(--ink-2);font-weight:600;flex:0 0 auto">Eller spela in</span>
          <div style="flex:1;display:flex;align-items:center;gap:10px;min-width:0;background:var(--surface);border:1px solid ${ v.recording ? 'color-mix(in srgb,var(--bad) 45%,var(--line))' : 'var(--line)' };border-radius:11px;padding:7px 7px 7px 13px;box-shadow:var(--shadow-sm)">
            ${ v.recording ? `
              <span style="width:9px;height:9px;border-radius:50%;background:var(--bad);flex:0 0 auto;animation:pulse 1.4s ease infinite"></span>
              <span style="font-size:14.5px;color:var(--ink);font-weight:500">Spelar in</span>
              <span style="font-size:14.5px;color:var(--ink-2);font-variant-numeric:tabular-nums">${esc(v.recElapsedFmt)}</span>
              <div style="flex:0 0 70px;height:6px;border-radius:99px;background:var(--track);overflow:hidden" title="Mikrofonnivå"><div style="height:100%;width:100%;transform-origin:left;transform:scaleX(${v.recLevelPct / 100});background:${ v.recSilent ? 'var(--bad)' : 'var(--ok)' };border-radius:99px;transition:transform .12s"></div></div>
              ${ v.recSilent ? `<span style="font-size:12.5px;color:var(--bad);font-weight:500;flex:0 0 auto">Ingen signal?</span>` : '' }
              <div style="flex:1"></div>
              <button data-click="${on(v.onMarkRec)}" title="Markera ett viktigt ögonblick" style="flex:0 0 auto;display:inline-flex;align-items:center;gap:6px;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:8px 13px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--accent) !important;color:var(--accent) !important">🔖 Markera${ v.recMarkerCount ? ' (' + v.recMarkerCount + ')' : '' }</button>
              <button data-click="${on(v.onCancelRec)}" style="flex:0 0 auto;background:var(--surface);border:1px solid var(--line);color:var(--ink-2);border-radius:8px;padding:8px 13px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--ink-3) !important;color:var(--ink) !important">Avbryt</button>
              <button data-click="${on(v.onStopRec)}" style="flex:0 0 auto;display:inline-flex;align-items:center;gap:7px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:8px;padding:8px 15px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit">Stoppa &amp; lägg till</button>
            ` : `
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="var(--ink-3)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" style="flex:0 0 auto"><rect x="5.5" y="1.5" width="5" height="8.5" rx="2.5"></rect><path d="M3.5 7.5a4.5 4.5 0 0 0 9 0"></path><path d="M8 12v2.5"></path></svg>
              <span style="font-size:15px;color:${ v.recSupported ? 'var(--ink-2)' : 'var(--ink-3)' };min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${ v.recSupported ? 'Spela in lektionen direkt — ljudet sparas lokalt' : 'Inspelning kräver mikrofonåtkomst i webbläsaren' }</span>
              <div style="flex:1"></div>
              <button data-click="${on(v.onStartRec)}" ${ v.recSupported ? '' : 'disabled' } style="flex:0 0 auto;display:inline-flex;align-items:center;gap:7px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:8px;padding:8px 15px;font-size:14px;font-weight:500;cursor:${ v.recSupported ? 'pointer' : 'default' };font-family:inherit;opacity:${ v.recSupported ? '1' : '0.55' }" data-sh="background:color-mix(in srgb, var(--btn-bg) 78%, var(--accent)) !important">Starta inspelning</button>
            ` }
          </div>
        </div>

        ${ v.hasRecError ? `
          <div style="display:flex;align-items:center;gap:10px;margin-top:14px;background:color-mix(in srgb,var(--bad) 7%,var(--surface));border:1px solid color-mix(in srgb,var(--bad) 30%,transparent);border-radius:12px;padding:12px 15px">
            <span style="width:20px;height:20px;border-radius:50%;flex:0 0 auto;background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700">!</span>
            <span style="font-size:14.5px;color:var(--ink)">${esc(v.recError)}</span>
          </div>
        ` : '' }

        ${ v.hasFileError ? `
          <div style="display:flex;align-items:center;gap:10px;margin-top:14px;background:color-mix(in srgb,var(--bad) 7%,var(--surface));border:1px solid color-mix(in srgb,var(--bad) 30%,transparent);border-radius:12px;padding:12px 15px">
            <span style="width:20px;height:20px;border-radius:50%;flex:0 0 auto;background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700">!</span>
            <span style="font-size:14.5px;color:var(--ink)">${esc(v.fileError)}</span>
          </div>
        ` : '' }

        <div style="display:flex;align-items:center;gap:9px;margin-top:18px;flex-wrap:wrap">
          <span style="font-size:11.5px;text-transform:uppercase;letter-spacing:0.05em;color:var(--ink-2);font-weight:600">Eller prova med</span>
          <button data-click="${on(v.addSampleNormal)}" style="display:inline-flex;align-items:center;gap:7px;font-size:13.5px;font-weight:500;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:9px;padding:7px 12px;cursor:pointer;font-family:inherit;font-variant-numeric:tabular-nums" data-sh="border-color:var(--ink-3) !important">
            <span style="width:7px;height:7px;border-radius:2px;background:var(--ok);flex:0 0 auto"></span>Prova ett exempel
          </button>
          <button data-click="${on(v.addSampleCorrupt)}" style="display:inline-flex;align-items:center;gap:7px;font-size:13.5px;font-weight:500;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:9px;padding:7px 12px;cursor:pointer;font-family:inherit;font-variant-numeric:tabular-nums" data-sh="border-color:var(--ink-3) !important">
            <span style="width:7px;height:7px;border-radius:2px;background:var(--bad);flex:0 0 auto"></span>skadad_inspelning.m4a
          </button>
        </div>
      </div>
      ` : '' }

      ${ v.stepConfig ? `
      <div data-pane="config" style="flex:1;display:flex;flex-direction:column;min-height:0">
        <div class="ehead">
          <div>
            <div class="eyebrow" style="margin-bottom:18px">Steg 2 — Inställningar</div>
            <h1 class="disp" style="font-size:clamp(30px,4.4vw,44px);margin:0">Så ska det <span class="ser">låta</span></h1>
          </div>
          <p class="ehead_lede">Välj språk och format — rätt modell väljs automatiskt, allt körs lokalt på din dator.</p>
        </div>
        <div class="win" style="margin-bottom:26px">
          <div class="win_top">
            <div style="display:flex;align-items:baseline;gap:10px">
              <span class="win_lbl">Filer i kö</span>
              <span class="fig" style="font-size:16px;color:var(--ink);font-variant-numeric:tabular-nums">${esc(v.queueCount)}</span>
            </div>
            <button data-click="${on(v.goSource)}" style="display:inline-flex;align-items:center;gap:6px;background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:6px 12px;font-size:13px;font-weight:500;cursor:pointer;font-family:inherit;flex:0 0 auto;transition:border-color .14s,background .14s">
              <span style="display:inline-flex;align-items:center;gap:6px;white-space:nowrap"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M8 3v10M3 8h10"></path></svg>Lägg till fler</span>
            </button>
          </div>
          <div style="display:flex;flex-direction:column">
            ${ v.queueItems.map(function(q){ return `
              <div data-key="${esc(q.id)}" style="display:flex;align-items:center;gap:12px;padding:13px 20px;border-bottom:1px solid var(--line);background:var(--surface)">
                <span style="font-family:var(--mono);font-size:10px;font-weight:500;letter-spacing:0.06em;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);border-radius:4px;padding:3px 7px;flex:0 0 auto">${esc(q.ext)}</span>
                <span style="flex:1;min-width:0;font-size:15.5px;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(q.name)}</span>
                <button data-click="${on(q.onRemove)}" aria-label="Ta bort från kön" style="width:36px;height:36px;flex:0 0 auto;border:1px solid var(--line);background:var(--surface);border-radius:8px;cursor:pointer;color:var(--ink-3);display:flex;align-items:center;justify-content:center;transition:border-color .14s,color .14s">
                  <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 3l8 8M11 3l-8 8"></path></svg>
                </button>
              </div>
            `; }).join('') }
          </div>
        </div>

        <div style="background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:17px 19px">
          <div style="font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);margin-bottom:15px">Språk</div>
          <div style="display:flex;align-items:flex-end;gap:14px">
            <div style="flex:1 1 0;min-width:0;display:flex;flex-direction:column;gap:9px">
              <span style="font-size:13px;font-weight:600;color:var(--ink-2)">Talat språk</span>
              <div style="display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:11px">
                ${ v.langOptions.map(function(l){ return `
                  <button data-click="${on(l.onPick)}" aria-pressed="${l.active}" data-seg="${l.active ? 'on' : 'off'}" style="flex:1 1 0;min-width:0;border:none;border-radius:8px;height:38px;font-size:15px;font-weight:500;white-space:nowrap;cursor:pointer;font-family:inherit;background:transparent;color:var(--ink-2);transition:background .12s,color .12s,box-shadow .12s">${esc(l.label)}</button>
                `; }).join('') }
              </div>
            </div>
            <div style="display:flex;flex-direction:column;align-items:center;gap:7px;flex:0 0 auto;padding-bottom:5px">
              <span style="display:flex;color:${v.isTranslating ? 'var(--accent)' : 'var(--ink-3)'};transition:color .25s"><svg width="24" height="14" viewBox="0 0 24 14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M1 7h20M15 2l6 5-6 5"></path></svg></span>
              <span data-q="${v.isTranslating ? '1' : '0'}" style="font-size:10.5px;font-weight:600;border-radius:6px;padding:3px 9px;white-space:nowrap;color:var(--ink-3);background:var(--sunken);border:1px solid var(--line)">${esc(v.transTag)}</span>
            </div>
            <div style="flex:1 1 0;min-width:0;display:flex;flex-direction:column;gap:9px">
              <span style="font-size:13px;font-weight:600;color:var(--ink-2)">Resultatspråk</span>
              <div style="display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:11px">
                ${ v.targetLangOptions.map(function(o){ return `
                  <button data-click="${on(o.onPick)}" aria-pressed="${o.active}" data-seg="${o.active ? 'on' : 'off'}" style="flex:1 1 0;min-width:0;border:none;border-radius:8px;height:38px;font-size:15px;font-weight:500;white-space:nowrap;cursor:pointer;font-family:inherit;background:transparent;color:var(--ink-2);transition:background .12s,color .12s,box-shadow .12s">${esc(o.label)}</button>
                `; }).join('') }
              </div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:10px 16px;margin-top:16px;padding-top:14px;border-top:1px solid var(--line);flex-wrap:wrap">
            <span style="display:inline-flex;align-items:center;gap:8px;font-size:13px;color:var(--ink-2)"><span style="width:8px;height:8px;border-radius:50%;background:${v.curModelDot};flex:0 0 auto"></span><span><b style="color:var(--ink);font-weight:600">${esc(v.curModelName)}</b> · ${esc(v.modelFootMeta)}</span></span>
            <span style="margin-left:auto;font-size:13px;color:var(--ink-2);text-align:right;min-width:0">${esc(v.transHint)}</span>
          </div>
        </div>

        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:12px;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px 16px">
          <span style="font-size:14px;color:var(--ink-2);font-weight:500">Filformat</span>
          <div style="display:flex;gap:6px">
            ${ v.formatChips.map(function(f){ return `
              <button data-click="${on(f.onToggle)}" aria-pressed="${f.active}" data-chip="${f.active ? 'on' : 'off'}" style="border:1px solid var(--line);background:transparent;color:var(--ink-2);border-radius:9px;padding:8px 13px;font-size:14.5px;font-weight:500;cursor:pointer;font-family:inherit;transition:all .12s">${esc(f.label)}</button>
            `; }).join('') }
          </div>
        </div>

        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:12px;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px 14px">
          <div data-click="${on(v.onToggleAudioCorrect)}" role="switch" tabindex="0" aria-checked="${v.audioCorrect}" aria-label="Rätta mot ljudet" style="${v.acSwitchTrack}"><span style="${v.acSwitchKnob}"></span></div>
          <div style="flex:1;min-width:0">
            <div style="font-size:14.5px;font-weight:500;color:var(--ink)">Rätta mot ljudet <span style="font-size:12px;color:var(--ink-3)">· Gemma 4 (experimentell)</span></div>
            <div style="font-size:12.5px;color:var(--ink-2)">Ett andra pass som rättar transkriptet mot vad som faktiskt sägs.</div>
          </div>
          ${ v.audioModelInstalled ? '' : `
            <button data-click="${on(v.onDownloadAudioModel)}" style="flex:0 0 auto;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:7px 13px;font-size:13.5px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--ink) !important">${ v.audioModelDownloading ? 'Laddar ner …' : 'Ladda ner modell' }</button>
          ` }
        </div>

        ${ v.showSubtitleMode ? `
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:12px;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px">
          <span style="font-size:14px;color:var(--ink-2);font-weight:500">Undertext i video</span>
          <div style="display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:11px">
            ${ v.subtitleOptions.map(function(o){ return `<button data-click="${on(o.onPick)}" aria-pressed="${o.active}" style="${o.style}" data-sh="background:var(--surface) !important;color:var(--ink) !important;box-shadow:var(--shadow-sm) !important">${esc(o.label)}</button>`; }).join('') }
          </div>
          ${ v.showEmbed ? `
          <div style="display:flex;gap:3px;padding:4px;background:var(--track);border:1px solid var(--line);border-radius:11px">
            ${ v.embedOptions.map(function(o){ return `<button data-click="${on(o.onPick)}" aria-pressed="${o.active}" style="${o.style}" data-sh="background:var(--surface) !important;color:var(--ink) !important;box-shadow:var(--shadow-sm) !important">${esc(o.label)}</button>`; }).join('') }
          </div>
          ` : '' }
        </div>
        ` : '' }

        <div style="flex:0 0 auto;height:46px"></div>

        <button data-click="${on(v.onStart)}" class="cta" ${v.startReady ? '' : 'aria-disabled="true"'} style="display:flex;align-items:center;justify-content:space-between;gap:16px;width:100%;height:64px;border:1px solid var(--ink);background:var(--btn-bg);color:var(--btn-fg);cursor:pointer;font-family:inherit;padding:0 14px 0 24px">
          ${ v.isRunning ? `
            <span style="display:inline-flex;align-items:center;gap:12px"><span style="width:15px;height:15px;border-radius:50%;border:2px solid color-mix(in srgb,var(--btn-fg) 35%,transparent);border-top-color:var(--btn-fg);animation:spin .7s linear infinite;display:inline-block"></span><span style="font-size:13px;font-weight:500;letter-spacing:0.1em;text-transform:uppercase">${esc(v.startBtnLabel)}</span></span>
          ` : '' }
          ${ v.notRunning ? `
            <span style="font-size:13px;font-weight:500;letter-spacing:0.1em;text-transform:uppercase">${esc(v.startBtnLabel)}</span>
            <span class="cta_arrow"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8h10"></path><path d="M8.5 3.5 13 8l-4.5 4.5"></path></svg></span>
          ` : '' }
        </button>
      </div>
      ` : '' }

      ${ v.stepProcess ? `
      <div data-pane="process" style="flex:1;display:flex;flex-direction:column;min-height:0">
        <div class="ehead">
          <div>
            <div class="eyebrow" style="margin-bottom:18px">Steg 3 — Transkribering</div>
            <h1 class="disp" style="font-size:clamp(30px,4.4vw,44px);margin:0">Bearbetar <span class="ser">lokalt</span></h1>
          </div>
          <p class="ehead_lede">${esc(v.procLede)}</p>
        </div>
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
              <span role="status" aria-live="polite" style="${v.statusBadgeStyle}">${esc(v.statusBadge)}</span>
              <span style="font-size:15.5px;color:var(--ink-2);font-variant-numeric:tabular-nums;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.statusFile)}</span>
            </div>
            <div style="display:flex;align-items:baseline;gap:18px;flex:0 0 auto">
              <span style="display:inline-flex;align-items:baseline;gap:7px"><span class="win_lbl">Tid</span><span style="font-size:14.5px;color:var(--ink-2);font-variant-numeric:tabular-nums">${esc(v.elapsedLabel)}</span></span>
              <span style="display:inline-flex;align-items:baseline;gap:7px"><span class="win_lbl">Klart</span><span class="fig" style="font-size:21px;color:var(--ink);font-variant-numeric:tabular-nums">${esc(v.progressLabel)}</span></span>
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
                <div style="${s.barTrackStyle}"><div style="${s.barFillStyle}"></div></div>
                <div style="display:flex;align-items:center;gap:6px">
                  <span style="${s.dotStyle}">${esc(s.icon)}</span>
                  <span style="${s.labelStyle}">${esc(s.label)}</span>
                </div>
              </div>
            `; }).join('') }
          </div>
          ` : '' }
        </div>

        <div data-click="${on(v.toggleLogExpand)}" role="button" tabindex="0" aria-expanded="${v.logExpand}" aria-label="Visa eller dölj logg" style="border-top:1px solid var(--line);background:var(--surface);cursor:pointer;border-radius:0 0 18px 18px;transition:background .12s" data-sh="background:var(--sunken) !important">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:11px 24px;font-size:13.5px;color:var(--ink-2)">
            <span style="display:flex;align-items:center;gap:8px">
              <span style="width:6px;height:6px;border-radius:50%;background:var(--ink-3)"></span>
              <span style="font-variant-numeric:tabular-nums;letter-spacing:0.02em;text-transform:uppercase;font-size:12.5px">Logg</span>
            </span>
            <span style="display:inline-flex;align-items:center;gap:7px;color:var(--ink);font-size:13px;font-weight:500">${esc(v.logToggleLabel)}
              <span style="width:7px;height:7px;border-right:1.6px solid var(--ink-3);border-bottom:1.6px solid var(--ink-3);transform:rotate(${v.logExpand ? '-135deg' : '45deg'});margin-top:${v.logExpand ? '3px' : '-3px'}"></span>
            </span>
          </div>
          ${ v.logExpand ? `
          <div style="position:relative;padding:6px 24px 16px">
            ${ v.logRows.map(function(r){ return `
              <div style="display:flex;gap:14px">
                <span style="font-variant-numeric:tabular-nums;font-size:12.5px;color:var(--ink-3);width:42px;flex:0 0 auto;text-align:right;padding-top:1px">${esc(r.time)}</span>
                <div style="position:relative;display:flex;flex-direction:column;align-items:center;flex:0 0 auto">
                  <span style="${r.dotStyle}">${esc(r.icon)}</span>
                  <span style="${r.lineStyle}"></span>
                </div>
                <span style="font-variant-numeric:tabular-nums;font-size:13px;color:var(--ink);padding-bottom:13px;line-height:1.45;min-width:0">${esc(r.msg)}</span>
              </div>
            `; }).join('') }
          </div>
          ` : '' }
        </div>
      </div>
      ` : '' }

      ${ v.isRunning ? `
      <div style="display:flex;flex-direction:column;align-items:center;gap:14px;margin-top:24px">
        <div style="display:flex;align-items:center;gap:11px;color:var(--ink-2);font-size:14.5px">
          <span style="width:15px;height:15px;border-radius:50%;border:2px solid var(--line-2);border-top-color:var(--accent);animation:spin .7s linear infinite"></span>
          ${esc(v.runningNote)}
        </div>
        <button data-click="${on(v.onCancelRun)}" style="background:transparent;border:1px solid var(--line);color:var(--ink-2);border-radius:9px;padding:7px 16px;font-size:13px;font-weight:500;cursor:pointer;font-family:inherit;transition:border-color .14s,color .14s" data-sh="border-color:var(--bad) !important;color:var(--bad) !important">Avbryt</button>
      </div>
      ` : '' }
      ${ v.showDone ? `
      <div style="display:flex;align-items:center;justify-content:center;gap:11px;margin-top:24px;color:var(--ink);font-size:15px;font-weight:500;animation:fadeup .3s ease both">
        <span style="width:20px;height:20px;border-radius:50%;background:var(--ok);color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;flex:0 0 auto">✓</span>
        <span>${esc(v.doneNote)}</span>
      </div>
      ` : '' }
        </div>
      </div>
      ` : '' }
    </section>
`; }

function historySection(v){
  if (v.historyEmpty) return '';
  return `
      <div style="margin-top:36px">
        <div style="font-family:var(--mono);font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--ink-3);margin:0 0 12px">Tidigare körningar</div>
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
      </div>
`; }

function viewRecordings(v){
  function filterChip(label, onX){ return '<span style="display:inline-flex;align-items:center;gap:7px;font-size:12.5px;font-weight:500;color:var(--accent);background:var(--accent-weak);border:1px solid color-mix(in srgb,var(--accent) 28%,transparent);border-radius:99px;padding:4px 6px 4px 12px">'+esc(label)+'<button data-click="'+onX+'" aria-label="Ta bort filter" style="width:18px;height:18px;border:none;background:transparent;color:var(--accent);cursor:pointer;display:flex;align-items:center;justify-content:center;font-family:inherit;border-radius:50%"><svg width="10" height="10" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 3l8 8M11 3l-8 8"></path></svg></button></span>'; }
  // Filterknapp + popover-meny (mallens custom dropdown med mjuk hover-stängning)
  function filterDrop(label, selOn, isOpen, onToggle, anim, menuOpts, alignRight){
    return `
        <div style="position:relative" data-enter="${on(v.fEnter)}" data-leave="${on(v.fLeave)}">
          <button data-click="${on(onToggle)}" data-filter-on="${esc(selOn)}" style="display:inline-flex;align-items:center;gap:9px;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:8px 13px;font-size:14px;font-family:inherit;cursor:pointer;white-space:nowrap;transition:border-color .14s">${esc(label)}<svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6l4 4 4-4"></path></svg></button>
          ${ isOpen ? `
            <div data-pop="${esc(anim)}" style="position:absolute;top:100%;${ alignRight ? 'right:0' : 'left:0' };z-index:30;padding-top:6px"><div style="min-width:172px;background:var(--surface);border:1px solid var(--line-2);border-radius:10px;box-shadow:var(--shadow);padding:5px;display:flex;flex-direction:column;gap:1px">
              ${ menuOpts.map(function(o){ return `
                <button data-key="${esc(o.key)}" data-click="${on(o.onSelect)}" data-opt="" style="display:flex;align-items:center;gap:10px;border:none;background:transparent;color:var(--ink);border-radius:7px;padding:8px 11px;font-size:13.5px;font-family:inherit;cursor:pointer;text-align:left;white-space:nowrap">${esc(o.label)}<span style="flex:1;min-width:14px"></span>${ o.isCur ? '<span style="font-weight:600">✓</span>' : '' }</button>
              `; }).join('') }
            </div></div>
          ` : '' }
        </div>`;
  }
  return `
    <section style="padding:32px 0 96px;animation:tabin .28s ease">
      <div style="max-width:820px;margin:10px auto 0;text-align:center">
        <div class="eyebrow" style="margin-bottom:14px;justify-content:center">${esc(v.archiveCountLabel)}</div>
        <h1 class="disp" style="font-size:clamp(34px,4.8vw,48px);margin:0 0 22px">Fråga ditt <span class="ser">arkiv.</span></h1>
      </div>

      ${ spotlightPanel(v.lessonsSearch) }

      ${ v.askScan ? `
      <div style="max-width:960px;margin:24px auto 8px;animation:fadeup .3s ease both">
        ${ scanTheater(v.askScan.theater) }
        ${ v.askScan.ansStarted ? `
        <div data-askwrap="${esc(v.askScan.askZoomFlag)}" data-click="${on(v.askScan.closeAskZoom)}">
        <div data-askzoom="${esc(v.askScan.askZoomFlag)}" data-click="${on(v.askScan.onAskCardClick)}" title="Klicka för att förstora svaret" style="margin-top:16px;border:1px solid var(--line);border-radius:13px;background:var(--surface);box-shadow:var(--shadow-sm);animation:fadeup .3s ease both;overflow:hidden">
          <div style="display:grid;grid-template-columns:minmax(0,1fr) ${ v.askScan.askZoomOn ? '300px' : '224px' };align-items:stretch">
          <div style="min-width:0;padding:${ v.askScan.askZoomOn ? '24px 28px' : '14px 17px' }">
            <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3)">${esc(v.askScan.ansHeadLabel)}</div>
            <div style="font-size:12.5px;color:var(--ink-3);margin-top:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">”${esc(v.askScan.q)}”</div>
            <div data-hidescroll="1" data-askscroll="1" style="max-height:min(52vh,520px);overflow:auto;overscroll-behavior:contain;scrollbar-width:none">
            <p style="margin:8px 0 0;font-size:${ v.askScan.askZoomOn ? '16px' : '15.5px' };line-height:1.8;color:var(--ink);max-width:62ch;white-space:pre-wrap">${ v.askScan.ansTokens ? v.askScan.ansTokens.map(function(tk){ return tk.isText
              ? `<span>${esc(tk.text)}</span>`
              : `<button data-click="${on(tk.onCite)}" data-csup="off" title="${esc(tk.label)}" aria-label="Öppna källa ${esc(tk.num)} — ${esc(tk.label)}" style="display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;padding:0 5px;font-size:11px;font-weight:700;color:var(--accent);background:var(--accent-weak);border:1px solid color-mix(in srgb,var(--accent) 28%,transparent);border-radius:6px;cursor:pointer;vertical-align:2px;margin:0 1.5px;font-family:inherit;transition:transform .1s">${esc(tk.num)}</button>`; }).join('') : esc(v.askScan.answer) }${ v.askScan.ansTyping ? '<span class="ai-blink" style="display:inline-block;width:9px;height:17px;background:var(--accent);vertical-align:-3px;margin-left:3px"></span>' : '' }</p>
            ${ v.askScan.askZoomOn && v.askScan.askFollowups.length ? `
            <div style="margin-top:18px;border-top:1px solid var(--line);padding-top:14px">
              ${ v.askScan.askFollowups.map(function(f){ return `
                <div data-key="${esc(f.key)}" style="display:flex;flex-direction:column;gap:8px;margin-bottom:16px">
                  <div style="align-self:flex-end;max-width:86%;background:var(--accent-weak);color:var(--ink);border:1px solid color-mix(in srgb,var(--accent) 25%,transparent);border-radius:14px 14px 4px 14px;padding:9px 13px;font-size:14px;line-height:1.5">${esc(f.q)}</div>
                  <div style="align-self:stretch;font-size:15px;line-height:1.75;color:var(--ink);white-space:pre-wrap">${esc(f.a)}${ f.typing ? '<span class="ai-blink" style="display:inline-block;width:8px;height:15px;background:var(--accent);vertical-align:-2px;margin-left:3px"></span>' : '' }</div>
                </div>
              `; }).join('') }
            </div>
            ` : '' }
            </div>
            ${ !v.askScan.askZoomOn && v.askScan.askFollowups.length ? `
            <div style="margin-top:10px;font-family:var(--mono);font-size:9.5px;letter-spacing:0.06em;text-transform:uppercase;color:var(--ink-3)">${esc(String(v.askScan.askFollowups.length))} följdfråg${ v.askScan.askFollowups.length === 1 ? 'a' : 'or' } — öppna chattvyn för att fortsätta</div>
            ` : '' }
            ${ v.askScan.askEvent ? `
              <div data-click="${on(v.stop)}" style="margin-top:12px">${ lessonEventBox(v.askScan.askEvent) }</div>
            ` : '' }
            ${ v.askScan.askZoomOn && v.askScan.ansDone ? `
              <div style="display:flex;gap:9px;align-items:center;margin-top:12px">
                <input value="${esc(v.askScan.askFollowInput)}" data-input="${on(v.askScan.setAskFollow)}" data-keydown="${on(v.askScan.onAskFollowKey)}" data-click="${on(v.stop)}" aria-label="Ställ en följdfråga" placeholder="Ställ en följdfråga …" style="flex:1;min-width:0;background:var(--sunken);border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:11px 13px;font-size:14.5px;font-family:inherit;outline:none">
                <button data-click="${on(v.askScan.sendAskFollow)}" style="flex:0 0 auto;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:10px;padding:11px 18px;font-size:14.5px;font-weight:500;cursor:pointer;font-family:inherit;transition:background .15s">Skicka</button>
              </div>
            ` : '' }
          </div>
          <div data-click="${on(v.stop)}" style="display:flex;flex-direction:column;gap:6px;padding:12px;background:var(--sunken);border-left:1px solid var(--line);min-width:0">
            ${ !v.askScan.askZoomOn ? `
            <button data-click="${on(v.askScan.onAskCardClick)}" title="Öppna svaret i en fokuserad chattvy" style="display:inline-flex;align-items:center;justify-content:center;gap:8px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:9px;padding:11px 16px;font-size:13.5px;font-weight:600;font-family:inherit;cursor:pointer;transition:background .15s">Öppna i chattvyn<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="flex:0 0 auto"><path d="M3 8h10M9 4l4 4-4 4"></path></svg></button>
            ` : '' }
            ${ !v.askScan.askEvent ? `
            <button data-click="${on(v.askScan.proposeAskCal)}" title="Skapa en kalenderhändelse utifrån svaret" style="display:inline-flex;align-items:center;justify-content:center;gap:7px;background:transparent;color:var(--ink-2);border:1px solid var(--line);border-radius:9px;padding:10px 14px;font-size:13px;font-weight:500;font-family:inherit;cursor:pointer;transition:border-color .14s,color .14s" data-sh="border-color:var(--line-2) !important;color:var(--ink) !important"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" style="flex:0 0 auto"><rect x="2" y="3" width="12" height="11" rx="2"></rect><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3M8 9v3M6.5 10.5h3"></path></svg>Kalenderhändelse</button>
            ` : '' }
            ${ /* Källpanelen är borttagen — källorna är klickbara siffror inne i
                  svaret (samma källförankring som lektionschatten). */ '' }
          </div>
          </div>
        </div>
        </div>
        ` : '' }
      </div>
      ` : '' }

      <div style="max-width:760px;margin:22px auto 10px;display:flex;gap:9px;justify-content:center;align-items:center;flex-wrap:wrap">
        ${ v.hasGroups ? filterDrop(v.fKlassLabel, v.klassSelOn, v.fKlassOpen, v.fKlassToggle, v.fPopAnim, v.klassMenuOpts) : '' }
        ${ v.hasCourses ? filterDrop(v.fKursLabel, v.kursSelOn, v.fKursOpen, v.fKursToggle, v.fPopAnim, v.kursMenuOpts) : '' }
        ${ v.hasMonths ? filterDrop(v.fDatumLabel, v.datumSelOn, v.fDatumOpen, v.fDatumToggle, v.fPopAnim, v.datumMenuOpts, true) : '' }
        ${ (!v.hasGroups && !v.hasCourses && v.hasMonths) ? `<span style="font-size:12.5px;color:var(--ink-3)">Tilldela klass &amp; kurs på korten för att filtrera på dem</span>` : '' }
        ${ /* Säkerhetskopiera behålls som medveten avvikelse från mallen */ '' }
        <button data-click="${on(v.backup.onRun)}" ${ v.backup.busy ? 'disabled' : '' } title="Säkerhetskopiera lektionsdatabasen + historiken" style="background:var(--surface);border:1px solid var(--line);color:var(--ink-2);border-radius:10px;padding:8px 14px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit;opacity:${ v.backup.busy ? '.6' : '1' }" data-sh="border-color:var(--ink) !important;color:var(--ink) !important">💾 ${ v.backup.busy ? 'Säkerhetskopierar …' : 'Säkerhetskopiera' }</button>
      </div>
      ${ v.hasActiveFilter ? `
      <div style="max-width:760px;margin:0 auto 20px;display:flex;gap:7px;justify-content:center;align-items:center;flex-wrap:wrap">
        ${ v.filterGroupLabel ? filterChip('Klass: ' + v.filterGroupLabel, on(v.onClearGroup)) : '' }
        ${ v.filterCourseLabel ? filterChip('Kurs: ' + v.filterCourseLabel, on(v.onClearCourse)) : '' }
        ${ v.lessonFilterMonth ? filterChip(v.fDatumLabel, on(v.onClearMonth)) : '' }
        <button data-click="${on(v.onClearFilters)}" style="font-size:12.5px;color:var(--ink-2);background:transparent;border:none;cursor:pointer;font-family:inherit;text-decoration:underline;padding:4px">Rensa alla</button>
      </div>
      ` : '<div style="margin-bottom:20px"></div>' }

      ${ agendaPanel(v.agenda) }

      ${ v.prep ? prepPanel(v.prep) : '' }

      ${ v.trends ? trendsPanel(v.trends) : '' }

      ${ v.lessonsEmpty ? `
        <div style="text-align:center;padding:60px 24px;background:var(--surface);border:1px dashed var(--line-2);border-radius:14px;color:var(--ink-2);font-size:16px">Inga inspelningar än. Transkribera en inspelning så dyker den upp här — tilldela den sedan klass och kurs.</div>
      ` : '' }

      <div style="max-width:1000px;margin:0 auto">
        ${ v.weekGroups.map(function(w){ return `
          <div data-key="w-${esc(w.key)}" style="display:flex;align-items:baseline;gap:18px;margin:38px 0 16px;padding-bottom:12px;border-bottom:2px solid var(--ink)">
            <span class="disp" style="font-size:clamp(24px,2.6vw,30px);line-height:1;color:var(--ink);white-space:nowrap;flex:0 0 auto">&#8203;${ w.isWeek ? `<span class="ser" style="color:var(--ink-3)">Vecka</span>&nbsp;${esc(w.num)}` : `<span class="ser" style="color:var(--ink-3)">Tidigare</span>` }</span>
            <span style="font-family:var(--mono);font-size:11.5px;letter-spacing:0.09em;text-transform:uppercase;color:var(--ink-2)">${esc(w.range)}</span>
            <div style="flex:1"></div>
            ${ w.hasHits ? `<span style="display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);font-size:11px;letter-spacing:0.09em;text-transform:uppercase;color:var(--accent)"><span style="width:7px;height:7px;border-radius:50%;background:var(--accent)"></span>${esc(w.hitLabel)}</span>` : '' }
            <span style="font-family:var(--mono);font-size:11px;letter-spacing:0.09em;text-transform:uppercase;color:var(--ink-3)">${esc(w.count)}</span>
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;align-items:start">
            ${ w.cards.map(function(h){ return `
              <div data-key="les-${esc(h.id)}" data-rec-id="${esc(h.id)}" data-stage="${esc(h.stage)}" data-click="${on(h.onOpenChat)}" style="background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:15px 16px;box-shadow:var(--shadow-sm);display:flex;flex-direction:column;gap:10px;cursor:pointer;overflow:hidden" data-sh="border-color:var(--line-2);box-shadow:var(--shadow)">
                ${ h.thumbUrl ? `
                <div style="margin:-15px -16px 3px;aspect-ratio:16/9;background:var(--sunken);border-bottom:1px solid var(--line);position:relative">
                  <img src="${esc(h.thumbUrl)}" alt="" loading="lazy" style="width:100%;height:100%;object-fit:cover;display:block">
                  <span style="position:absolute;left:9px;bottom:8px;display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);font-size:9.5px;letter-spacing:0.06em;text-transform:uppercase;color:#fff;background:rgba(11,11,13,.55);backdrop-filter:blur(3px);border-radius:6px;padding:3px 8px"><svg width="9" height="9" viewBox="0 0 12 12" fill="currentColor"><path d="M3 2.2v7.6l6-3.8z"></path></svg>Video</span>
                </div>
                ` : '' }
                <div style="display:flex;align-items:center;gap:8px">
                  <span data-cc="${esc(h.cc)}" title="${esc(h.tagFull)}" style="border-radius:99px;padding:2px 10px;font-size:11.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:0 1 auto;min-width:0">${esc(h.tagLabel)}</span>
                  ${ h.isHit ? `<span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;color:var(--accent);background:var(--accent-weak);border-radius:99px;padding:2px 9px;flex:0 0 auto"><span style="width:6px;height:6px;border-radius:50%;background:var(--accent)"></span>träff</span>` : '' }
                  <span style="flex:1"></span>
                  <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.05em;text-transform:uppercase;color:var(--ink-3);white-space:nowrap">${esc(h.date)}</span>
                </div>
                <div>
                  <div style="font-size:16px;font-weight:600;color:var(--ink);line-height:1.3;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(h.name)}</div>
                  <div style="display:flex;align-items:center;gap:12px;margin-top:6px">
                    ${ h.meta ? `<span style="font-family:var(--mono);font-size:10px;color:var(--ink-3);font-variant-numeric:tabular-nums;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(h.meta)}</span>` : '' }
                    ${ h.sal ? `<span style="font-family:var(--mono);font-size:10px;color:var(--ink-3);white-space:nowrap">Sal ${esc(h.sal)}</span>` : '' }
                  </div>
                </div>
                <div style="display:flex;align-items:center;gap:7px;border-top:1px solid var(--line);padding-top:10px">
                  <button data-click="${on(h.onOpenChat)}" data-textbtn style="font-family:var(--mono);font-size:10px;letter-spacing:0.07em;text-transform:uppercase;color:var(--accent);background:transparent;border:none;padding:0;cursor:pointer">Öppna &amp; chatta ↗</button>
                  <span style="flex:1"></span>
                  <button data-click="${on(h.onOpen)}" aria-label="Öppna transkriptvyn" title="Öppna transkriptvyn med ljud" style="width:36px;height:36px;border:1px solid var(--line);background:var(--surface);border-radius:8px;cursor:pointer;color:var(--ink-3);display:flex;align-items:center;justify-content:center;transition:border-color .12s,color .12s"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h5l2 2v8H6z"></path><path d="M3 5v8.5h7"></path></svg></button>
                  <button data-click="${on(h.onRename)}" aria-label="Redigera uppgifter" title="Redigera klass, kurs, sal och datum" style="width:36px;height:36px;border:1px solid var(--line);background:var(--surface);border-radius:8px;cursor:pointer;color:var(--ink-3);display:flex;align-items:center;justify-content:center;transition:border-color .12s,color .12s"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.3 2.2l2.5 2.5L5.5 13H3v-2.5z"></path></svg></button>
                  <button data-click="${on(h.onDelete)}" aria-label="Ta bort" style="width:36px;height:36px;border:1px solid var(--line);background:var(--surface);border-radius:8px;cursor:pointer;color:var(--ink-3);display:flex;align-items:center;justify-content:center;transition:border-color .12s,color .12s"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.5 8.5h6l.5-8.5"></path></svg></button>
                </div>
              </div>
            `; }).join('') }
          </div>
        `; }).join('') }
        ${ v.recEmpty ? `
          <div style="text-align:center;color:var(--ink-2);font-size:15px;padding:46px 0;margin-top:24px;background:var(--surface);border:1px dashed var(--line-2);border-radius:14px">Inga inspelningar matchar dina filter.</div>
        ` : '' }
      </div>

      ${ historySection(v) }
    </section>`;
}

function trendsPanel(t){
  if (t.empty) return '';
  return `
    <div style="max-width:760px;margin:0 auto 22px;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:18px 20px;box-shadow:var(--shadow-sm)">
      <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:15px">
        <span style="font-size:17px">📈</span>
        <h2 style="font-size:17px;font-weight:600;color:var(--ink);margin:0">Terminstrender${ t.group ? ' · ' + esc(t.group) : '' }</h2>
        <span style="font-size:13px;color:var(--ink-3);margin-left:auto">${t.analysed} av ${t.lessons} lektioner analyserade</span>
      </div>

      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">
        ${ t.counts.map(function(c){ return `
          <div style="flex:1;min-width:90px;background:var(--sunken);border:1px solid var(--line);border-radius:11px;padding:11px 12px;text-align:center">
            <div style="font-size:22px;font-weight:600;color:var(--ink);font-variant-numeric:tabular-nums">${c.n}</div>
            <div style="font-size:12px;color:var(--ink-3);margin-top:2px">${esc(c.label)}</div>
          </div>
        `; }).join('') }
      </div>

      ${ t.actTotal ? `
        <div style="margin-bottom:16px">
          <div style="display:flex;justify-content:space-between;font-size:12.5px;color:var(--ink-2);margin-bottom:6px">
            <span>Avklarade åtgärder</span><span style="font-variant-numeric:tabular-nums">${t.actDone}/${t.actTotal} · ${t.actPct}%</span>
          </div>
          <div style="height:8px;border-radius:99px;background:var(--track);overflow:hidden"><div style="height:100%;width:${t.actPct}%;background:var(--ok);border-radius:99px"></div></div>
        </div>
      ` : '' }

      ${ t.difficulties.length ? `
        <div style="font-size:12px;font-weight:600;color:var(--ink-3);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px">Återkommande svårigheter</div>
        <div style="display:flex;flex-direction:column;gap:6px">
          ${ t.difficulties.map(function(d){ return `
            <div style="display:flex;align-items:center;gap:10px;font-size:14px;color:var(--ink)">
              <span style="flex:0 0 auto;min-width:26px;height:22px;display:inline-flex;align-items:center;justify-content:center;border-radius:6px;font-size:12px;font-weight:600;font-variant-numeric:tabular-nums;background:${d.recurring?'var(--accent-weak)':'var(--sunken)'};color:${d.recurring?'var(--accent)':'var(--ink-3)'}">${d.count}×</span>
              <span style="flex:1;min-width:0">${esc(d.text)}${ d.refs ? ` <span style="color:var(--ink-3);font-size:12.5px">(${esc(d.refs)})</span>` : '' }</span>
            </div>
          `; }).join('') }
        </div>
      ` : `<div style="font-size:13.5px;color:var(--ink-3)">Inga svårigheter registrerade än — analysera lektioner för att se mönster över terminen.</div>` }
    </div>`;
}

function agendaPanel(a){
  if (!a.loaded || a.total === 0) return '';
  return `
    <div style="max-width:760px;margin:0 auto 16px;background:var(--surface);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow-sm);overflow:hidden">
      <button data-click="${on(a.onToggle)}" style="width:100%;display:flex;align-items:center;gap:11px;background:transparent;border:none;padding:14px 18px;cursor:pointer;font-family:inherit;text-align:left">
        <span style="font-size:17px">📅</span>
        <span style="font-size:14.5px;font-weight:600;color:var(--ink)">Kommande</span>
        <span style="font-size:13px;color:var(--ink-3)">${a.count} öppna${ a.overdueCount ? ` · <span style="color:var(--bad);font-weight:600">${a.overdueCount} försenade</span>` : '' }</span>
        <span style="margin-left:auto;color:var(--ink-3);font-size:13px;transform:rotate(${a.isOpen?'180':'0'}deg);transition:transform .2s">▾</span>
      </button>
      ${ a.isOpen ? `
        <div style="padding:0 18px 16px">
          <div style="display:flex;flex-direction:column;gap:7px">
            ${ a.items.map(function(it){ return `
              <div style="display:flex;align-items:flex-start;gap:10px;background:${it.overdue?'color-mix(in srgb,var(--bad) 8%,var(--sunken))':'var(--sunken)'};border:1px solid ${it.overdue?'color-mix(in srgb,var(--bad) 35%,var(--line))':'var(--line)'};border-radius:10px;padding:9px 11px">
                <button data-click="${on(it.onDone)}" aria-label="Markera klar" title="Markera klar" style="flex:0 0 auto;width:18px;height:18px;margin-top:1px;border-radius:5px;border:1.5px solid ${it.done?'var(--ok)':'var(--line-2)'};background:${it.done?'var(--ok)':'transparent'};cursor:pointer;color:var(--on-ok);font-size:11px;display:flex;align-items:center;justify-content:center">${it.done?'✓':''}</button>
                <div style="flex:1;min-width:0">
                  <div style="font-size:14px;color:${it.done?'var(--ink-3)':'var(--ink)'};${it.done?'text-decoration:line-through':''}">${esc(it.text)}</div>
                  <div style="font-size:12px;color:var(--ink-3);margin-top:2px">${esc(it.meta)}</div>
                </div>
                <span style="flex:0 0 auto;font-size:12px;font-weight:600;font-variant-numeric:tabular-nums;color:${it.overdue?'var(--bad)':(it.today?'var(--accent)':'var(--ink-3)')}">${ it.today ? 'Idag' : esc(it.due) }</span>
              </div>
            `; }).join('') }
          </div>
          <div style="display:flex;justify-content:flex-end;margin-top:12px">
            <button data-click="${on(a.onExport)}" ${a.exporting?'disabled':''} style="display:inline-flex;align-items:center;gap:7px;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:8px 14px;font-size:13.5px;font-weight:500;cursor:${a.exporting?'default':'pointer'};font-family:inherit;opacity:${a.exporting?'0.7':'1'}" data-sh="border-color:var(--ink) !important">${ a.exporting ? 'Exporterar …' : '📆 Exportera till kalender (.ics)' }</button>
          </div>
        </div>
      ` : '' }
    </div>`;
}

// ---- Arkivsökets live-progression (spec 2026-07-18): delad modell + vy ------
// Fas 1 (kartoteket): korten avslöjas i äkta genomsökningsordning med verkliga
// träffantal. Fas 2 (läsbordet): källorna AI:n läser djupt reser sig till en
// egen rad med läsindikator medan svaret streamas; resten läggs åt sidan.
function buildScanModel(cfg){
  var plan = cfg.plan || [];
  var res = cfg.res || {};
  var shown = Math.min(cfg.shown || 0, plan.length);
  var revealDone = plan.length > 0 && shown >= plan.length;
  var effShown = cfg.scanning ? shown : plan.length;
  var deskOn = !!(cfg.deep && cfg.deep.length) && (revealDone || !cfg.scanning);
  var hitsSoFar = 0;
  plan.slice(0, effShown).forEach(function (p) { if ((res[p.key] || 0) > 0) hitsSoFar++; });
  var current = cfg.scanning && !deskOn && plan[Math.min(shown, plan.length - 1)];
  var MAXC = 24, extra = Math.max(0, plan.length - MAXC);
  var cards = plan.slice(0, MAXC).map(function (p, i) {
    var hits = res[p.key] || 0;
    var stt, lbl;
    if (cfg.scanning && i === shown) { stt = 'reading'; lbl = 'Läser …'; }
    else if (!cfg.scanning || i < shown) {
      stt = hits > 0 ? 'hit' : 'read';
      lbl = hits > 0 ? ('● ' + hits + (hits === 1 ? ' träff' : ' träffar')) : 'Läst ✓';
    }
    else { stt = 'queue'; lbl = 'I kö'; }
    return { key: p.key, st: stt, stLabel: lbl, title: p.name || '(namnlös)' };
  });
  if (extra > 0) cards.push({ key: '_more', st: effShown >= plan.length ? 'read' : 'queue',
                              stLabel: '', title: '+ ' + extra + ' till' });
  return {
    active: plan.length > 0,
    scanning: !!cfg.scanning && !deskOn,
    ticker: 'Söker igenom ' + plan.length + ' ' + cfg.noun + (current && current.name ? ' — ' + current.name : ''),
    doneLabel: '✓ Genomsökte ' + plan.length + ' ' + cfg.noun,
    progress: plan.length ? effShown / plan.length : 0,
    hitLabel: hitsSoFar + (hitsSoFar === 1
      ? (cfg.scanning ? ' träff hittills' : ' träff')
      : (cfg.scanning ? ' träffar hittills' : ' träffar')),
    onNew: cfg.onNew,
    cards: cards,
    desk: deskOn ? {
      label: cfg.scanning ? 'AI:n läser nu dessa ' + cfg.deep.length
                          : 'Svaret bygger på dessa ' + cfg.deep.length,
      reading: !!cfg.scanning,
      cards: cfg.deskCards || [],
      aside: plan.length - cfg.deep.length > 0
        ? '… och la ' + (plan.length - cfg.deep.length) + ' åt sidan' : '',
    } : null,
  };
}

function scanTheater(m){
  if (!m || !m.active) return '';
  var mono = 'font-family:var(--mono);letter-spacing:0.08em;text-transform:uppercase';
  return `
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
      ${ m.scanning ? `
        <span class="insp-dots" style="color:var(--accent);flex:0 0 auto"><i></i><i></i><i></i></span>
        <span style="${mono};font-size:10.5px;color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis" aria-live="polite">${esc(m.ticker)}</span>
      ` : `
        <span style="${mono};font-size:10.5px;color:var(--ok);flex:0 0 auto">${esc(m.doneLabel)}</span>
      ` }
      <div class="scan-progress" aria-hidden="true"><i style="transform:scaleX(${m.progress})"></i></div>
      <span style="${mono};font-size:10px;color:var(--accent);flex:0 0 auto">${esc(m.hitLabel)}</span>
      <button data-click="${on(m.onNew)}" style="flex:0 0 auto;border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:7px;padding:5px 10px;${mono};font-size:10px;cursor:pointer">✕ Ny fråga</button>
    </div>
    ${ m.desk ? `
      <div>
        <span style="${mono};font-size:10px;color:var(--ink-3);display:block;margin-bottom:8px">${esc(m.desk.label)}</span>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px">
          ${ m.desk.cards.map(function(dc, i){ return `
            <${ dc.onOpen ? 'button' : 'div' } data-key="desk-${esc(dc.key)}" class="scan-desk-card" ${ dc.onOpen ? `data-click="${on(dc.onOpen)}" title="Öppna källan" data-sh="border-color:var(--accent) !important"` : '' } style="animation-delay:${i * 70}ms;min-width:0;text-align:left;font-family:inherit;border:1px solid color-mix(in srgb,var(--accent) 45%,var(--line));background:color-mix(in srgb,var(--accent-weak) 45%,var(--surface));border-radius:10px;padding:11px 13px;${ dc.onOpen ? 'cursor:pointer' : '' }">
              ${ dc.typLabel ? `<span style="${mono};font-size:9px;letter-spacing:0.07em;color:var(--accent);display:block">${esc(dc.typLabel)}</span>` : '' }
              <div style="font-size:12.5px;font-weight:600;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--ink)">${esc(dc.title)}</div>
              ${ dc.sub ? `<span style="font-size:11px;color:var(--ink-3);display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px">${esc(dc.sub)}</span>` : '' }
              ${ m.desk.reading ? `<span class="scan-readline" aria-hidden="true"><i></i></span>` : '' }
            </${ dc.onOpen ? 'button' : 'div' }>
          `; }).join('') }
        </div>
        ${ m.desk.aside ? `<span class="scan-aside" style="${mono};font-size:10px;color:var(--ink-3);display:block;margin-top:9px">${esc(m.desk.aside)}</span>` : '' }
      </div>
    ` : `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(108px,1fr));gap:8px">
        ${ m.cards.map(function(sc){ return `
          <div data-key="scan-${esc(sc.key)}" data-scan="${esc(sc.st)}" style="min-width:0;border:1px solid var(--line);background:var(--surface);border-radius:9px;padding:10px 12px;transition:opacity .35s ease,box-shadow .35s ease,border-color .35s ease,background .35s ease">
            <span style="${mono};font-size:10px;letter-spacing:0.07em;color:var(--ink-3);display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(sc.stLabel)}</span>
            <div style="font-size:12px;font-weight:600;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(sc.title)}</div>
          </div>
        `; }).join('') }
      </div>
    ` }
`; }

function spotlightPanel(s){
  return `
    <div style="max-width:820px;margin:0 auto 6px">
      <div style="display:flex;align-items:center;gap:13px;background:var(--surface);border:1.5px solid var(--ink);border-radius:14px;padding:9px 10px 9px 18px;box-shadow:var(--shadow)">
        <span class="ai-blink" style="width:9px;height:9px;border-radius:50%;background:var(--accent);flex:0 0 auto"></span>
        <input value="${esc(s.query)}" data-input="${on(s.onInput)}" data-keydown="${on(s.onKey)}"
          aria-label="Sök i arkivet"
          placeholder="${ s.modeAsk ? 'Ställ en fråga, t.ex. när hade vi prov om derivata?' : 'Sök efter vad som sades, t.ex. pythagoras sats' }"
          style="flex:1;min-width:0;background:transparent;border:none;color:var(--ink);padding:8px 0;font-size:16.5px;font-family:inherit;outline:none">
        ${ /* Rensa-knappen upptar alltid sin plats (data-vis) — annars knuffas
              Sök/Fråga-knappen åt höger vid första tecknet och ett klick på
              gamla koordinaterna träffar ✕ i stället. */ '' }
        <button data-click="${on(s.onClear)}" aria-label="Rensa" data-vis="${ s.hasQuery ? '' : 'off' }" style="flex:0 0 auto;width:38px;height:38px;border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:9px;cursor:pointer;font-family:inherit">✕</button>
        <button data-click="${on(s.onRun)}" ${s.busy?'disabled':''} style="flex:0 0 auto;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:9px;padding:10px 18px;font-size:14px;font-weight:600;cursor:${s.busy?'default':'pointer'};font-family:inherit;transition:background .15s;opacity:${s.busy?'0.7':'1'}">${ s.busy ? 'Söker …' : (s.modeAsk ? 'Fråga' : 'Sök') }</button>
      </div>
      <div style="display:flex;align-items:center;gap:8px;margin-top:10px;flex-wrap:wrap">
        <div style="display:inline-flex;gap:3px;padding:3px;background:var(--track);border-radius:9px;border:1px solid var(--line);flex:0 0 auto">
          <button data-click="${on(s.onAsk)}" data-seg="${ s.modeAsk ? 'on' : 'off' }" aria-pressed="${s.modeAsk}" style="border:none;background:transparent;color:var(--ink-3);border-radius:7px;padding:5px 11px;font-size:12px;font-weight:600;cursor:pointer;font-family:inherit;white-space:nowrap">Fråga AI</button>
          <button data-click="${on(s.onKeyword)}" data-seg="${ s.modeKeyword ? 'on' : 'off' }" aria-pressed="${s.modeKeyword}" style="border:none;background:transparent;color:var(--ink-3);border-radius:7px;padding:5px 11px;font-size:12px;font-weight:600;cursor:pointer;font-family:inherit;white-space:nowrap">Sök ord</button>
        </div>
        ${ s.showSuggest ? `<span style="font-family:var(--mono);font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);margin-left:6px;flex:0 0 auto">Prova</span>` : '' }
        ${ s.showSuggest ? s.suggestions.map(function(sg){ return `
          <button data-click="${on(sg.onClick)}" style="display:inline-flex;align-items:center;gap:7px;font-size:12.5px;color:var(--ink-2);background:var(--surface);border:1px solid var(--line);border-radius:99px;padding:6px 12px;cursor:pointer;font-family:inherit;white-space:nowrap;transition:border-color .12s,color .12s"><span style="color:var(--accent)">✻</span>${esc(sg.label)}</button>
        `; }).join('') : '' }
      </div>

      ${ s.modeKeyword ? `
        ${ s.searched ? `
          <div style="margin-top:14px;background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:14px 16px;box-shadow:var(--shadow-sm)">
            ${ s.showNoHits ? `<div style="font-size:13.5px;color:var(--ink-3)">Inga lektioner matchade din sökning.</div>` : `
              <div style="display:flex;flex-direction:column;gap:8px">
                ${ s.hits.map(function(hit){ return `
                  <button data-click="${on(hit.onOpen)}" style="text-align:left;background:var(--sunken);border:1px solid var(--line);border-radius:11px;padding:11px 13px;cursor:pointer;font-family:inherit;display:block;width:100%" data-sh="border-color:var(--accent) !important">
                    <div style="display:flex;align-items:baseline;gap:9px;margin-bottom:4px">
                      <span style="font-size:14px;font-weight:600;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(hit.name)}</span>
                      <span style="font-size:12px;color:var(--ink-3)">${esc(hit.meta)}</span>
                    </div>
                    <div style="font-size:13px;color:var(--ink-2);line-height:1.5">${hit.snippet}</div>
                  </button>
                `; }).join('') }
              </div>
            ` }
          </div>
        ` : '' }
      ` : '' }
    </div>`;
}

function prepPanel(p){ return `
    <div style="background:var(--accent-weak);border:1px solid var(--accent);border-radius:16px;padding:18px 20px;margin-bottom:22px">
      <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:14px">
        <span style="font-size:18px">📋</span>
        <h2 style="font-size:18px;font-weight:600;color:var(--ink);margin:0">Inför nästa lektion${ p.group ? ' · ' + esc(p.group) : '' }</h2>
      </div>

      ${ p.empty ? `
        <div style="font-size:14px;color:var(--ink-2)">Inget att bära med sig ännu — öppna åtgärder och förra lektionens svårigheter dyker upp här när du analyserat lektioner för den här klassen.</div>
      ` : '' }

      ${ p.actions.length ? `
        <div style="font-size:12px;font-weight:600;color:var(--accent);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:7px">Att göra (öppna)</div>
        <div style="display:flex;flex-direction:column;gap:7px;margin-bottom:${ p.difficulties.length ? '16px' : '0' }">
          ${ p.actions.map(function(a){ return `
            <div style="display:flex;align-items:flex-start;gap:10px;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:9px 11px">
              <button data-click="${on(a.onDone)}" aria-label="Markera klar" title="Markera klar" style="flex:0 0 auto;width:18px;height:18px;margin-top:1px;border-radius:5px;border:1.5px solid var(--line-2);background:transparent;cursor:pointer" data-sh="border-color:var(--ok) !important;background:var(--ok) !important"></button>
              <div style="flex:1;min-width:0">
                <div style="font-size:14px;color:var(--ink)">${esc(a.text)}</div>
                <div style="font-size:12px;color:var(--ink-3);margin-top:2px">${esc(a.typLabel)}${ a.ref ? ' · ' + esc(a.ref) : '' }${ a.date ? ' · ' + esc(a.date) : '' }</div>
              </div>
            </div>
          `; }).join('') }
        </div>
      ` : '' }

      ${ p.difficulties.length ? `
        <div style="font-size:12px;font-weight:600;color:var(--accent);text-transform:uppercase;letter-spacing:0.04em;margin-bottom:7px">Repetera — förra lektionens svårigheter${ p.lastDate ? ' (' + esc(p.lastDate) + ')' : '' }</div>
        <div style="display:flex;flex-direction:column;gap:5px">
          ${ p.difficulties.map(function(d){ return `
            <div style="font-size:14px;color:var(--ink);padding-left:14px;position:relative">
              <span style="position:absolute;left:0;color:var(--accent)">•</span>${esc(d.text)}${ d.ref ? ` <span style="color:var(--ink-3);font-size:12.5px">(${esc(d.ref)})</span>` : '' }
            </div>
          `; }).join('') }
        </div>
      ` : '' }
    </div>`;
}

// Delad källförankrad chatt-tråd (meddelanden + citat/källpanel + input + tänk-djupare
// + modell-indikator). Används av resultatvyns "Fråga om lektionen" och per-lektion-modalen.
function chatThread(c){ return `
          ${ c.chatEmpty ? `
          <div style="background:var(--sunken);border:1px solid var(--line);border-radius:13px;padding:13px 15px;color:var(--ink-2);font-size:13.5px;line-height:1.5">Ställ en fråga om innehållet — t.ex. ”Vad var det viktigaste som togs upp?”. Varje påstående i svaret förankras i numrerade källor; klicka en källa så lyser dess ställe upp i transkriptet.</div>
          ` : '' }

          ${ c.chatHasMsgs ? `
            ${ c.chat.map(function(m){ return `
              <div style="${m.rowStyle}">
                ${ m.hasReason ? (m.reasonIsOpen ? `
                  <div style="${m.reasonStyle}"><div data-click="${on(m.onToggleReason)}" role="button" tabindex="0" aria-expanded="true" title="Fäll ihop resonemanget" style="display:flex;align-items:center;gap:6px;font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-3);margin-bottom:4px;cursor:pointer"><span>Resonemang</span><svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="flex:0 0 auto"><path d="M4 10l4-4 4 4"></path></svg></div>${esc(m.reason.replace(/^\s+/, ''))}</div>
                ` : `
                  <button data-click="${on(m.onToggleReason)}" aria-expanded="false" title="Visa modellens resonemang" style="display:inline-flex;align-items:center;gap:6px;background:var(--sunken);border:1px dashed var(--line-2);border-radius:9px;padding:4px 10px;font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-3);cursor:pointer;font-family:inherit">Resonemang<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="flex:0 0 auto"><path d="M4 6l4 4 4-4"></path></svg></button>
                `) : '' }
                ${ m.hasCites ? `
                <div style="align-self:stretch;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:5px 14px 14px 14px;padding:13px 14px;box-shadow:var(--shadow-sm)">
                  <div style="font-size:14px;line-height:1.7;color:var(--ink);min-width:0">
                    ${ m.tokens.map(function(tk){ return tk.isText
                      ? `<span>${renderRichInline(tk.text)}</span>`
                      : `<button data-click="${on(tk.onCite)}" data-csup="${tk.supFlag}" aria-label="Visa källa ${esc(tk.num)} i transkriptet" style="display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;padding:0 5px;font-size:11px;font-weight:700;color:var(--accent);background:var(--accent-weak);border:1px solid color-mix(in srgb,var(--accent) 28%,transparent);border-radius:6px;cursor:pointer;vertical-align:2px;margin:0 1.5px;font-family:inherit;transition:transform .1s">${esc(tk.num)}</button>`; }).join('') }
                  </div>
                </div>
                ` : `
                <div style="${m.bubbleStyle}">${ m.isUser ? esc(m.text) : renderRich(m.text) }</div>
                ` }
              </div>
            `; }).join('') }
            ${ c.chatTyping ? `
            <div style="align-self:flex-start;display:flex;align-items:center;gap:9px;color:var(--ink-2);font-size:13px;padding:4px 0"><span style="width:13px;height:13px;border-radius:50%;border:2px solid var(--line-2);border-top-color:var(--accent);animation:spin .7s linear infinite"></span>Söker i transkriptet …</div>
            ` : '' }
          ` : '' }
          <div data-follow="chatend" style="height:1px"></div>
`; }

// Kompositören i sidopanelens fot — input + Skicka + kompakt "Tänk djupare".
function chatComposer(c){ return `
          <div style="display:flex;gap:8px;align-items:center">
            <input value="${esc(c.chatInput)}" data-input="${on(c.onChatInput)}" data-keydown="${on(c.onChatKey)}" aria-label="Skriv en fråga till lektionen" placeholder="Skriv en fråga …" style="flex:1;min-width:0;background:var(--sunken);border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:10px 12px;font-size:14px;font-family:inherit;outline:none">
            <button data-click="${on(c.onChatSend)}" ${c.chatTyping ? 'disabled' : ''} style="flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:10px;padding:10px 16px;font-size:14px;font-weight:500;cursor:${c.chatTyping ? 'default' : 'pointer'};opacity:${c.chatTyping ? '.5' : '1'};font-family:inherit;box-shadow:var(--shadow-sm);transition:background .15s">Skicka</button>
          </div>
          <div style="display:flex;align-items:center;gap:8px;margin-top:8px">
            <button data-click="${on(c.onToggleChatThink)}" style="${c.chatThinkBtnStyle}" aria-pressed="${c.chatThink ? 'true' : 'false'}" title="${esc(c.chatThinkHint)}">
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8 1.5a4.5 4.5 0 0 0-2.6 8.2c.4.3.6.6.6 1v.8h4v-.8c0-.4.2-.7.6-1A4.5 4.5 0 0 0 8 1.5z"></path><path d="M6 14.5h4"></path></svg>
              Tänk djupare
            </button>
            <span style="flex:1"></span>
            <span style="font-family:var(--mono);font-size:8.5px;letter-spacing:0.07em;text-transform:uppercase;color:var(--ink-3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">svar förankras i transkriptet</span>
          </div>
`; }

// Kalenderförslaget i lektionsoverlayen — "Förslag → Google Kalender" med
// dag/tid-väljare och en kommandorad som justerar tid/titel/anteckning.
// Kalenderförslaget i lektionsoverlayen — "Förslag → Google Kalender" med
// dag/tid-väljare; tid/titel/anteckning ändras via huvudchatten (regex-tolken).
function lessonEventBox(ev){
  return `
    <div style="border:1px dashed var(--line-2);background:var(--sunken);border-radius:10px;padding:11px 13px;animation:fadeup .3s ease both">
      ${ ev.notAdded ? `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:9px">
        <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.07em;text-transform:uppercase;color:var(--ink-3);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">Förslag → Kalender</span>
        <span style="flex:1"></span>
        ${ ev.calKnown ? (ev.calConnected
          ? `<span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.07em;text-transform:uppercase;color:var(--ok);flex:0 0 auto">● ansluten</span>`
          : `<button data-click="${on(ev.onConnect)}" style="flex:0 0 auto;font-family:var(--mono);font-size:9.5px;letter-spacing:0.07em;text-transform:uppercase;color:var(--accent);background:transparent;border:1px solid color-mix(in srgb,var(--accent) 40%,transparent);border-radius:6px;padding:4px 9px;cursor:pointer">Anslut Google-konto</button>`)
          : `<span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.07em;text-transform:uppercase;color:var(--ink-3);flex:0 0 auto">kontrollerar anslutning …</span>` }
        <button data-click="${on(ev.onDismiss)}" aria-label="Avvisa förslaget" title="Avvisa förslaget" style="border:none;background:transparent;color:var(--ink-3);cursor:pointer;font-size:12px;padding:2px 6px;font-family:inherit;border-radius:6px;transition:color .12s;white-space:nowrap;flex:0 0 auto">✕ Avvisa</button>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <input value="${esc(ev.title)}" data-input="${on(ev.setTitle)}" data-keydown="${on(ev.onTitleKey)}" aria-label="Titel" style="flex:2 1 180px;min-width:0;border:1px solid var(--line);background:var(--surface);border-radius:8px;padding:8px 11px;font-size:13.5px;font-weight:500;font-family:inherit;color:var(--ink)">
        <button data-click="${on(ev.onTogglePick)}" title="Välj dag och tid" style="flex:1 1 140px;min-width:0;display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);background:var(--surface);border-radius:8px;padding:8px 11px;font-size:13px;font-family:inherit;color:var(--ink);cursor:pointer;font-variant-numeric:tabular-nums;white-space:nowrap;transition:border-color .14s"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" style="flex:0 0 auto"><rect x="2" y="3" width="12" height="11" rx="2"></rect><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3"></path></svg><span style="min-width:0;overflow:hidden;text-overflow:ellipsis">${esc(ev.when)}</span><span style="flex:1"></span><svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="flex:0 0 auto"><path d="M4 6l4 4 4-4"></path></svg></button>
        <button data-click="${on(ev.onAdd)}" ${ ev.busy ? 'disabled' : '' } style="flex:0 0 auto;display:inline-flex;align-items:center;gap:7px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:8px;padding:9px 15px;font-size:13px;font-weight:600;cursor:${ ev.busy ? 'default' : 'pointer' };font-family:inherit;opacity:${ ev.busy ? '.6' : '1' };transition:background .15s">${ ev.busy ? 'Lägger till …' : 'Lägg till' }</button>
      </div>
      ${ ev.pickOpen ? `
        <div style="display:grid;grid-template-columns:1fr;margin-top:10px;border:1px solid var(--line);border-radius:9px;background:var(--surface);overflow:hidden;animation:ml-popin .2s cubic-bezier(.16,1,.3,1) both">
          <div data-hidescroll style="border-bottom:1px solid var(--line);padding:8px;display:flex;flex-direction:column;gap:1px;max-height:148px;overflow:auto">
            <span style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);padding:3px 8px 6px">Dag</span>
            ${ ev.dayOpts.map(function(d){ return `
              <button data-key="${esc(d.key)}" data-click="${on(d.onPick)}" data-q="${esc(d.curQ)}" style="display:flex;align-items:center;gap:8px;border:1px solid transparent;background:transparent;color:var(--ink);border-radius:6px;padding:6px 8px;font-size:13px;font-family:inherit;cursor:pointer;text-align:left;white-space:nowrap"><span style="min-width:0;overflow:hidden;text-overflow:ellipsis">${esc(d.label)}</span><span style="flex:1"></span>${ d.hasPre ? `<span style="font-family:var(--mono);font-size:8.5px;letter-spacing:0.05em;text-transform:uppercase;color:var(--accent)">${esc(d.pre)}</span>` : '' }</button>
            `; }).join('') }
          </div>
          <div style="padding:8px">
            <span style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);padding:3px 8px 6px;display:block">Tid</span>
            <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:5px">
              ${ ev.timeOpts.map(function(t2){ return `
                <button data-key="${esc(t2.key)}" data-click="${on(t2.onPick)}" data-q="${esc(t2.curQ)}" style="border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:6px;padding:7px 4px;font-size:12.5px;font-family:inherit;cursor:pointer;font-variant-numeric:tabular-nums;text-align:center">${esc(t2.label)}</button>
              `; }).join('') }
            </div>
            <div style="font-size:11px;color:var(--ink-3);padding:8px 8px 2px">Välj dag, sedan tid — stängs automatiskt.</div>
          </div>
        </div>
      ` : '' }
      <div style="margin-top:8px">
        <textarea data-input="${on(ev.setDesc)}" data-ref="${on(ev.descFocusRef)}" data-desc="" placeholder="Anteckning i kalenderposten …" aria-label="Anteckning i kalenderposten" style="width:100%;box-sizing:border-box;border:1px solid var(--line);background:var(--surface);border-radius:8px;padding:8px 11px;font-size:13px;line-height:1.5;font-family:inherit;color:var(--ink);outline:none">${esc(ev.desc)}</textarea>
        <div style="margin-top:6px;font-size:12px;color:var(--ink-3)">Ändra via chatten — ”flytta till onsdag 14:30”, ”kortare titel” eller ”pågå till fredag” för flera dagar.</div>
      </div>
      ` : `
      <div style="display:flex;align-items:center;gap:9px;font-size:13px;font-weight:500;color:var(--ok)"><span style="width:16px;height:16px;border-radius:50%;background:var(--ok);color:var(--on-ok);display:inline-flex;align-items:center;justify-content:center;font-size:9px;animation:okPop .25s cubic-bezier(0.22,1,0.36,1) both">✓</span>Tillagd i Google Kalender — ${esc(ev.title)}</div>
      ` }
    </div>`;
}

function viewModals(v){ return `
  ${ v.anyDDOpen ? `
    <div data-click="${on(v.closeDD)}" style="position:fixed;inset:0;z-index:25"></div>
  ` : '' }

  ${ v.lessonChatOpen ? `
  <div data-click="${on(v.closeLessonChat)}" data-screen-label="Lektion (overlay)" style="position:fixed;inset:0;z-index:120;display:flex;align-items:center;justify-content:center;padding:clamp(10px,3vw,38px);background:color-mix(in srgb,var(--canvas) 58%,transparent);backdrop-filter:blur(9px);animation:modalback .3s ease">
    <div data-click="${on(v.stop)}" data-modal-card role="dialog" aria-modal="true" aria-label="Lektion" data-dialog tabindex="-1" style="width:min(960px,96vw);height:min(88vh,880px);display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--line);border-radius:20px;box-shadow:var(--shadow);overflow:hidden">
      <div style="flex:0 0 auto;display:flex;align-items:center;gap:11px;padding:11px 13px 11px 11px;border-bottom:1px solid var(--line)">
        <button data-click="${on(v.closeLessonChat)}" aria-label="Stäng (Esc)" title="Stäng · Esc" style="flex:0 0 auto;width:36px;height:36px;display:flex;align-items:center;justify-content:center;border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:10px;cursor:pointer;transition:transform .14s cubic-bezier(.2,.8,.25,1),border-color .14s,background .14s,color .14s" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important;color:var(--ink) !important"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8"></path></svg></button>
        <span data-cc="${esc(v.ovCc)}" style="border-radius:99px;padding:3px 11px;font-size:11.5px;font-weight:600;white-space:nowrap;flex:0 0 auto">${esc(v.ovTag)}</span>
        <div style="min-width:0">
          <div style="font-size:15px;font-weight:600;color:var(--ink);letter-spacing:-.01em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.lessonChatName)}</div>
          <div style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.06em;text-transform:uppercase;color:var(--ink-3);margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.ovMeta)}</div>
        </div>
        <span style="flex:1"></span>
        <button data-click="${on(v.ovOpenFull)}" title="Öppna hela transkriptvyn" style="flex:0 0 auto;display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:9px;padding:8px 13px;font-size:12.5px;font-weight:500;cursor:pointer;font-family:inherit;transition:transform .14s cubic-bezier(.2,.8,.25,1),border-color .14s,background .14s,color .14s" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important;color:var(--ink) !important"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" style="flex:0 0 auto"><path d="M6 2.5H3.5A1 1 0 0 0 2.5 3.5V6M10 2.5h2.5a1 1 0 0 1 1 1V6M13.5 10v2.5a1 1 0 0 1-1 1H10M6 13.5H3.5a1 1 0 0 1-1-1V10"></path></svg>Transkript</button>
      </div>
      <div style="flex:1;min-height:0;display:flex">
      ${ v.ovHasHit ? `
      <div data-hidescroll data-ovscroll="1" style="flex:1;min-width:0;overflow:auto;overscroll-behavior:contain;padding:24px 28px 20px;animation:fadeup .25s ease both">
        <div style="max-width:760px;margin:0 auto">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
            <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3)">Transkription</span>
            <div style="flex:1;height:1px;background:var(--line)"></div>
            <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--accent)">Källa · ${esc(v.ovHitT)}</span>
            <button data-click="${on(v.ovHitClear)}" aria-label="Dölj transkriptet" title="Dölj transkriptet" style="border:none;background:transparent;color:var(--ink-3);cursor:pointer;font-size:11px;padding:2px 5px;flex:0 0 auto;font-family:inherit">✕</button>
          </div>
          ${ v.lessonChatLoading ? `
          <div style="display:flex;align-items:center;gap:10px;color:var(--ink-2);font-size:14px;padding:20px 0"><span style="width:15px;height:15px;border-radius:50%;border:2px solid var(--line-2);border-top-color:var(--accent);animation:spin .7s linear infinite;flex:0 0 auto"></span>Läser in transkriptet …</div>
          ` : v.ovRows.map(function(p){ return p.hit ? `
            <div data-key="ovr-${esc(p.t)}" data-ovhit="1" style="display:flex;gap:14px;padding:10px 13px;margin:2px -13px;background:var(--accent-weak);border:1px solid color-mix(in srgb,var(--accent) 38%,var(--line));border-radius:9px">
              <span style="font-variant-numeric:tabular-nums;font-family:var(--mono);font-size:10.5px;color:var(--accent);flex:0 0 auto;width:44px;padding-top:3px;font-weight:500">${esc(p.t)}</span>
              <span style="font-size:14.5px;color:var(--ink);line-height:1.55;font-weight:500">${esc(p.txt)}</span>
            </div>
          ` : `
            <div data-key="ovr-${esc(p.t)}" style="display:flex;gap:14px;padding:7px 0;border-bottom:1px solid color-mix(in srgb,var(--line) 55%,transparent)">
              <span style="font-variant-numeric:tabular-nums;font-family:var(--mono);font-size:10.5px;color:var(--ink-3);flex:0 0 auto;width:44px;padding-top:2px">${esc(p.t)}</span>
              <span style="font-size:14.5px;color:var(--ink-2);line-height:1.55">${esc(p.txt)}</span>
            </div>
          `; }).join('') }
        </div>
      </div>
      ` : '' }
      <div data-side style="flex:${ v.ovHasHit ? '0 0 clamp(330px,36vw,440px)' : '1' };min-width:0;display:flex;flex-direction:column;${ v.ovHasHit ? 'border-left:1px solid var(--line);' : '' }background:var(--surface)">
        <div style="flex:0 0 auto;display:flex;align-items:center;gap:8px;padding:17px max(16px,calc((100% - 720px)/2));border-bottom:1px solid var(--line)">
          <span class="ai-blink" style="width:6px;height:6px;border-radius:50%;background:var(--accent);flex:0 0 auto"></span>
          <span style="font-family:var(--mono);font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3)">Fråga lektionen</span>
          <span style="flex:1"></span>
          <span title="${esc(v.lessonChatThread.ovModelTitle)}" style="font-family:var(--mono);font-size:10px;letter-spacing:0.07em;text-transform:uppercase;color:var(--ink-3);cursor:help">Körs lokalt</span>
        </div>
        <div data-hidescroll style="flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;padding:20px max(16px,calc((100% - 720px)/2));display:flex;flex-direction:column;gap:15px">
          ${ chatThread(v.lessonChatThread) }
        </div>
        ${ v.ovEvent ? (v.ovEvent.added ? `
        <div style="flex:0 0 auto;display:flex;align-items:center;gap:9px;margin:0 max(12px,calc((100% - 720px)/2)) 8px;border:1px solid color-mix(in srgb,var(--ok) 40%,var(--line));background:var(--surface);border-radius:4px;padding:8px 11px;font-size:13px;font-weight:500;color:var(--ok)"><span style="width:16px;height:16px;border-radius:50%;background:var(--ok);color:var(--on-ok);display:inline-flex;align-items:center;justify-content:center;font-size:9px;animation:okPop .25s cubic-bezier(0.22,1,0.36,1) both;flex:0 0 auto">✓</span><span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">Tillagd i Google Kalender — ${esc(v.ovEvent.title)}</span><button data-click="${on(v.ovEvent.onDismiss)}" aria-label="Stäng" style="margin-left:auto;border:none;background:transparent;color:var(--ink-3);cursor:pointer;font-size:11px;padding:2px 4px;flex:0 0 auto">✕</button></div>
        ` : `
        <div style="position:relative;flex:0 0 auto;display:flex;justify-content:flex-end;margin:0 max(12px,calc((100% - 720px)/2)) 8px">
          ${ v.ovEvOpen ? `
          <div data-click="${on(v.stop)}" style="position:absolute;bottom:calc(100% + 9px);right:0;width:min(300px,86vw);z-index:8;background:var(--surface);border:1px solid var(--line);border-radius:5px;box-shadow:var(--shadow);padding:14px 15px;animation:ml-popin .2s cubic-bezier(.16,1,.3,1) both">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:9px">
              <span style="font-family:var(--mono);font-size:9px;letter-spacing:0.07em;text-transform:uppercase;color:var(--accent)">Förslag → Kalender</span>
              <span style="flex:1"></span>
              ${ v.ovEvent.calKnown ? (v.ovEvent.calConnected
                ? `<span style="font-family:var(--mono);font-size:9px;letter-spacing:0.07em;text-transform:uppercase;color:var(--ok);flex:0 0 auto">● ansluten</span>`
                : `<button data-click="${on(v.ovEvent.onConnect)}" style="flex:0 0 auto;font-family:var(--mono);font-size:9px;letter-spacing:0.07em;text-transform:uppercase;color:var(--accent);background:transparent;border:1px solid color-mix(in srgb,var(--accent) 40%,transparent);border-radius:3px;padding:3px 8px;cursor:pointer">Anslut Google-konto</button>`)
                : `<span style="font-family:var(--mono);font-size:9px;letter-spacing:0.07em;text-transform:uppercase;color:var(--ink-3);flex:0 0 auto">kontrollerar …</span>` }
            </div>
            <div style="font-size:13.5px;font-weight:600;color:var(--ink);line-height:1.35">${esc(v.ovEvent.title)}</div>
            <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.04em;text-transform:uppercase;color:var(--ink-2);font-variant-numeric:tabular-nums;margin-top:3px">${esc(v.ovEvent.when)}</div>
            ${ v.ovEvent.desc ? `<div data-click="${on(v.ovDescOpen)}" role="button" tabindex="0" title="Visa hela anteckningen" style="font-size:12px;color:var(--ink-2);margin-top:7px;line-height:1.5;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;cursor:pointer">${esc(v.ovEvent.desc)}</div>` : '' }
            <div style="display:flex;align-items:center;gap:8px;margin-top:11px;padding-top:11px;border-top:1px solid var(--line)">
              <button data-click="${on(v.ovEvent.onAdd)}" ${ v.ovEvent.busy ? 'disabled' : '' } style="flex:0 0 auto;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:4px;padding:7px 14px;font-size:12.5px;font-weight:600;font-family:inherit;cursor:${ v.ovEvent.busy ? 'default' : 'pointer' };opacity:${ v.ovEvent.busy ? '.6' : '1' }">${ v.ovEvent.busy ? 'Lägger till …' : 'Lägg till' }</button>
              <button data-click="${on(v.ovEvent.onDismiss)}" style="flex:0 0 auto;background:transparent;border:none;color:var(--ink-3);font-size:12px;font-weight:500;font-family:inherit;cursor:pointer;padding:7px 6px">Avvisa</button>
              <span style="flex:1"></span>
            </div>
            <div style="margin-top:8px;font-size:11.5px;color:var(--ink-3);line-height:1.45">Ändra titel, tid eller anteckning genom att skriva i chatten.</div>
          </div>
          ` : '' }
          <button data-click="${on(v.toggleOvEv)}" aria-expanded="${ v.ovEvOpen ? 'true' : 'false' }" aria-label="${ v.ovEvOpen ? 'Dölj kalenderförslaget' : 'Visa kalenderförslaget' }" title="${ v.ovEvOpen ? 'Dölj kalenderförslaget' : `Kalenderförslag: ${esc(v.ovEvent.title)} · ${esc(v.ovEvent.when)}` }" style="position:relative;width:32px;height:32px;flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;background:${ v.ovEvOpen ? 'var(--accent-weak)' : 'var(--surface)' };border:1px solid ${ v.ovEvOpen ? 'color-mix(in srgb,var(--accent) 45%,transparent)' : 'var(--line)' };border-radius:50%;color:var(--accent);cursor:pointer;transition:border-color .14s,background .14s">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="3" width="12" height="11" rx="2"></rect><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3"></path></svg>
            ${ v.ovEvOpen ? '' : `<span class="ai-blink" style="position:absolute;top:-1px;right:-1px;width:7px;height:7px;border-radius:50%;background:var(--accent);border:1.5px solid var(--surface)"></span>` }
          </button>
        </div>
        `) : '' }
        <div style="flex:0 0 auto;border-top:1px solid var(--line);padding:10px max(12px,calc((100% - 720px)/2))">
          ${ chatComposer(v.lessonChatThread) }
        </div>
      </div>
      </div>
    </div>
  </div>
  ` : '' }

  ${ v.ovDescView && v.ovEvent ? `
  <div data-click="${on(v.ovDescClose)}" style="position:fixed;inset:0;z-index:135;background:color-mix(in srgb,var(--ink) 32%,transparent);display:flex;align-items:center;justify-content:center;padding:32px;animation:modalback .26s ease">
    <div data-click="${on(v.stop)}" role="dialog" aria-modal="true" aria-label="Anteckning i kalenderförslaget" data-dialog tabindex="-1" style="width:min(560px,92vw);max-height:min(60vh,480px);display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);overflow:hidden;animation:modalpop .42s cubic-bezier(.16,1,.3,1)">
      <div style="flex:0 0 auto;display:flex;align-items:center;gap:10px;padding:14px 18px;border-bottom:1px solid var(--line)">
        <span style="font-family:var(--mono);font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3)">Anteckning · ${esc(v.ovEvent.when)}</span>
        <span style="flex:1"></span>
        <span style="font-size:12px;color:var(--ink-3)">Klicka utanför för att stänga</span>
      </div>
      <div data-hidescroll="1" style="flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;padding:18px 20px;font-size:15px;line-height:1.65;color:var(--ink);white-space:pre-wrap">${esc(v.ovEvent.desc)}</div>
      <div style="flex:0 0 auto;border-top:1px solid var(--line);padding:10px 18px;font-size:11.5px;color:var(--ink-3)">Ändra anteckningen genom att skriva i chatten.</div>
    </div>
  </div>
  ` : '' }

  ${ v.descModalOpen ? `
  <div data-modal-back="${esc(v.descModalAnim)}" data-click="${on(v.closeDescModal)}" style="position:fixed;inset:0;z-index:135;background:color-mix(in srgb,var(--ink) 32%,transparent);display:flex;align-items:center;justify-content:center;padding:32px">
    <div data-modal-card="${esc(v.descModalAnim)}" data-click="${on(v.stop)}" role="dialog" aria-modal="true" aria-label="Anteckning i kalenderposten" data-dialog tabindex="-1" style="width:min(680px,92vw);height:min(64vh,520px);display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--ink);border-radius:14px;box-shadow:var(--shadow);overflow:hidden">
      <div style="display:flex;align-items:center;gap:10px;padding:14px 18px;border-bottom:1px solid var(--line)">
        <span style="font-family:var(--mono);font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3)">Anteckning i kalenderposten</span>
        <span style="flex:1"></span>
        <span style="font-size:12px;color:var(--ink-3)">Sparas direkt · klicka utanför för att stänga</span>
      </div>
      <textarea data-input="${on(v.setDescModalVal)}" data-hidescroll="1" aria-label="Anteckning i kalenderposten — redigering" style="flex:1;min-height:0;width:100%;box-sizing:border-box;border:none;background:var(--surface);padding:18px 20px;font-size:15px;line-height:1.65;font-family:inherit;color:var(--ink);outline:none;resize:none;overflow:auto;scrollbar-width:none">${esc(v.descModalVal)}</textarea>
    </div>
  </div>
  ` : '' }

  ${ v.renameOpen ? `
  <div data-click="${on(v.onRenameCancel)}" style="position:fixed;inset:0;z-index:130;background:rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;padding:24px;animation:fadeup .2s ease">
    <div data-click="${on(v.stop)}" role="dialog" aria-modal="true" aria-label="Redigera lektionsuppgifter" data-dialog tabindex="-1" style="width:min(94vw,460px);background:var(--canvas);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
      <div class="eyebrow" style="margin-bottom:10px">Redigera uppgifter</div>
      <h2 style="font-size:18px;font-weight:600;margin:0 0 14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.renameName)}</h2>
      <datalist id="dl-klass">${ v.lessonGroups.map(function(g){ return '<option value="'+esc(g.namn)+'">'; }).join('') }</datalist>
      <datalist id="dl-kurs">${ v.lessonCourses.map(function(c){ return '<option value="'+esc(c.namn)+'">'; }).join('') }</datalist>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:9px">
        <label style="display:flex;flex-direction:column;gap:4px;font-size:11.5px;color:var(--ink-3)">Klass
          <input value="${esc(v.renameGroup)}" list="dl-klass" data-input="${on(v.onRenameGroup)}" placeholder="t.ex. NA21" style="background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:8px 11px;font-size:14px;font-family:inherit;min-width:0;width:100%;box-sizing:border-box"></label>
        <label style="display:flex;flex-direction:column;gap:4px;font-size:11.5px;color:var(--ink-3)">Kurs
          <input value="${esc(v.renameCourse)}" list="dl-kurs" data-input="${on(v.onRenameCourse)}" placeholder="t.ex. Matematik 2b" style="background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:8px 11px;font-size:14px;font-family:inherit;min-width:0;width:100%;box-sizing:border-box"></label>
        <label style="display:flex;flex-direction:column;gap:4px;font-size:11.5px;color:var(--ink-3)">Sal
          <input value="${esc(v.renameSal)}" data-input="${on(v.onRenameSal)}" placeholder="t.ex. B214" style="background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:8px 11px;font-size:14px;font-family:inherit;min-width:0;width:100%;box-sizing:border-box"></label>
        <label style="display:flex;flex-direction:column;gap:4px;font-size:11.5px;color:var(--ink-3)">Datum
          <input type="date" value="${esc(v.renameDatum)}" data-input="${on(v.onRenameDatum)}" style="background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:8px 11px;font-size:14px;font-family:inherit;min-width:0;width:100%;box-sizing:border-box"></label>
      </div>
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">
        <button data-click="${on(v.onRenameCancel)}" style="background:var(--surface);border:1px solid var(--line);color:var(--ink-2);border-radius:9px;padding:8px 15px;font-size:13.5px;font-weight:500;cursor:pointer;font-family:inherit">Avbryt</button>
        <button data-click="${on(v.onRenameSave)}" style="background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:9px;padding:8px 17px;font-size:13.5px;font-weight:600;cursor:pointer;font-family:inherit">Spara</button>
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
        <input data-tsearch="1" value="${esc(v.searchQuery)}" data-input="${on(v.onTSearch)}" data-keydown="${on(v.onSearchKey)}" aria-label="Sök i transkriptet" placeholder="Sök i transkriptet …" style="border:none;outline:none;background:transparent;font-size:14.5px;color:var(--ink);font-family:inherit;width:200px">
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
            <span data-click="${on(ln.onJump)}" role="button" tabindex="0" aria-label="Hoppa till ${esc(ln.time)}" style="${ln.timeStyle}" data-sh="color:var(--accent) !important">${esc(ln.time)}</span>
            ${ v.editing ? `
              <div data-eline="${esc(ln.idx)}" contentEditable="true" data-input="${on(v.onEditInput)}" style="${ln.editStyle}"></div>
            ` : '' }
            ${ v.notEditing ? `
              <span style="font-size:18px;line-height:1.7;color:var(--ink);flex:1;min-width:0">
                ${ ln.segments.map(function(seg){ return `
                  ${ seg.plain ? `<span>${esc(seg.text)}</span>` : '' }
                  ${ seg.match ? `<span style="background:var(--accent-weak);border-radius:3px;box-shadow:0 0 0 1px var(--accent-weak)">${esc(seg.text)}</span>` : '' }
                  ${ seg.current ? `<span data-current="1" style="background:var(--accent);color:var(--on-accent);border-radius:3px;box-shadow:0 0 0 2px var(--accent)">${esc(seg.text)}</span>` : '' }
                `; }).join('') }
              </span>
            ` : '' }
          </div>
        `; }).join('') }
      </div>
    </div>

    ${ v.hasMediaEl ? `<audio data-ref="${on(v.mediaRef)}" src="${esc(v.mediaUrl)}" preload="metadata" style="display:none"></audio>` : '' }
    ${ v.hasMarkers ? `
    <div style="flex:0 0 auto;border-top:1px solid var(--line);background:color-mix(in srgb,var(--surface) 72%,transparent);padding:9px 28px;display:flex;align-items:center;gap:8px;overflow-x:auto">
      <span style="font-size:12px;font-weight:600;color:var(--ink-3);flex:0 0 auto">🔖 Markörer</span>
      ${ v.markers.map(function(m){ return `
        <span style="flex:0 0 auto;display:inline-flex;align-items:center;gap:5px;background:var(--accent-weak);border:1px solid var(--accent);border-radius:8px;padding:3px 4px 3px 9px">
          <button data-click="${on(m.onSeek)}" title="Hoppa hit" style="background:none;border:none;color:var(--accent);font-size:12.5px;font-weight:600;font-variant-numeric:tabular-nums;cursor:pointer;font-family:inherit;padding:0">${esc(m.label)}</button>
          <button data-click="${on(m.onDelete)}" aria-label="Ta bort markör" style="background:none;border:none;color:var(--accent);opacity:.6;cursor:pointer;font-size:12px;line-height:1;padding:0 2px">✕</button>
        </span>
      `; }).join('') }
    </div>
    ` : '' }
    <div style="flex:0 0 auto;border-top:1px solid var(--line);background:color-mix(in srgb,var(--surface) 72%,transparent);backdrop-filter:saturate(1.3) blur(14px);padding:13px 28px;display:flex;align-items:center;gap:18px">
      <button data-click="${on(v.onTogglePlay)}" aria-label="Spela eller pausa" style="width:46px;height:46px;flex:0 0 auto;border-radius:50%;border:none;background:var(--btn-bg);color:var(--btn-fg);cursor:pointer;display:flex;align-items:center;justify-content:center" data-sh="background:color-mix(in srgb, var(--btn-bg) 78%, var(--accent)) !important">
        ${ v.audioPaused ? `<svg width="17" height="17" viewBox="0 0 16 16" fill="currentColor"><path d="M4.5 3.2v9.6c0 .5.5.8 1 .5l7.3-4.8c.4-.3.4-.8 0-1.1L5.5 2.7c-.5-.3-1 0-1 .5z"></path></svg>` : '' }
        ${ v.audioPlaying ? `<svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor"><rect x="3.5" y="3" width="3.2" height="10" rx="1"></rect><rect x="9.3" y="3" width="3.2" height="10" rx="1"></rect></svg>` : '' }
      </button>
      <span style="font-size:13.5px;color:var(--ink-2);font-variant-numeric:tabular-nums;flex:0 0 auto;width:42px">${esc(v.audioCur)}</span>
      <div data-ref="${on(v.seekTrackRef)}" data-click="${on(v.onSeekClick)}" data-keydown="${on(v.onSeekKey)}" role="slider" tabindex="0" aria-label="Sök i uppspelningen" aria-valuemin="0" aria-valuemax="${v.seekMax}" aria-valuenow="${v.seekNow}" aria-valuetext="${esc(v.audioCur)} av ${esc(v.audioDur)}" style="flex:1;height:42px;display:flex;align-items:stretch;gap:2px;cursor:pointer">
        ${ v.waveBars.map(function(b){ return `<span style="${b.style}"></span>`; }).join('') }
      </div>
      <span style="font-size:13.5px;color:var(--ink-2);font-variant-numeric:tabular-nums;flex:0 0 auto;width:42px;text-align:right">${esc(v.audioDur)}</span>
      <button data-click="${on(v.onAddMarker)}" title="Markera den här punkten" style="flex:0 0 auto;display:inline-flex;align-items:center;gap:6px;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:8px 12px;font-size:13.5px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--accent) !important;color:var(--accent) !important">🔖 Markera</button>
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
            <span style="font-variant-numeric:tabular-nums;font-size:13.5px;color:var(--ink-3);width:52px;flex:0 0 auto;text-align:right;padding-top:2px">${esc(r.time)}</span>
            <div style="position:relative;display:flex;flex-direction:column;align-items:center;flex:0 0 auto">
              <span style="${r.dotStyle}">${esc(r.icon)}</span>
              <span style="${r.lineStyle}"></span>
            </div>
            <span style="font-variant-numeric:tabular-nums;font-size:15px;color:var(--ink);padding-bottom:18px;line-height:1.5;min-width:0">${esc(r.msg)}</span>
          </div>
        `; }).join('') }
      </div>
    </div>
  </div>
  ` : '' }

  ${ v.calSetupOpen ? `
  <div data-click="${on(v.calSetup.onClose)}" style="position:fixed;inset:0;z-index:135;display:flex;align-items:center;justify-content:center;padding:24px;background:color-mix(in srgb,var(--canvas) 64%,transparent);backdrop-filter:blur(7px);animation:modalback .26s ease">
    <div data-click="${on(v.stop)}" role="dialog" aria-modal="true" aria-label="Google Kalender" data-dialog tabindex="-1" style="width:min(94vw,560px);max-height:88vh;overflow:auto;overscroll-behavior:contain;background:var(--surface);border:1px solid var(--line);border-radius:20px;box-shadow:var(--shadow);animation:modalpop .42s cubic-bezier(.16,1,.3,1)">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:14px;padding:22px 24px 14px;border-bottom:1px solid var(--line)">
        <div style="min-width:0">
          <span style="font-family:var(--mono);font-size:10.5px;font-weight:500;letter-spacing:0.08em;color:var(--c-sky);background:color-mix(in srgb,var(--c-sky) 13%,transparent);border:1px solid color-mix(in srgb,var(--c-sky) 28%,transparent);padding:3px 9px;border-radius:6px">GOOGLE KALENDER</span>
          <h2 style="font-size:20px;font-weight:600;letter-spacing:-0.02em;margin:9px 0 0">Koppla Google Kalender</h2>
        </div>
        <button data-click="${on(v.calSetup.onClose)}" aria-label="Stäng" style="flex:0 0 auto;width:36px;height:36px;display:flex;align-items:center;justify-content:center;background:var(--surface);border:1px solid var(--line);border-radius:9px;color:var(--ink-2);cursor:pointer;font-size:15px">✕</button>
      </div>
      <div style="padding:18px 24px 22px">
        ${ v.calSetup.connected ? `
        <div style="display:flex;align-items:center;gap:12px;background:color-mix(in srgb,var(--ok) 9%,var(--surface));border:1px solid color-mix(in srgb,var(--ok) 32%,transparent);border-radius:13px;padding:16px 18px">
          <span style="width:36px;height:36px;border-radius:50%;flex:0 0 auto;background:color-mix(in srgb,var(--ok) 18%,transparent);color:var(--ok);display:flex;align-items:center;justify-content:center;font-size:18px">✓</span>
          <div><div style="font-size:15.5px;font-weight:600;color:var(--ink)">Ansluten till Google Kalender</div><div style="font-size:13.5px;color:var(--ink-2);margin-top:2px">Nu kan du lägga till kalenderförslag med ett klick.</div></div>
        </div>
        <div style="display:flex;justify-content:flex-end;margin-top:16px"><button data-click="${on(v.calSetup.onClose)}" style="background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:11px;padding:11px 20px;font-size:14.5px;font-weight:500;cursor:pointer;font-family:inherit">Klart</button></div>
        ` : `
        <p style="margin:0 0 16px;color:var(--ink-2);font-size:14.5px;line-height:1.55">Händelser skapas i din egen Google Kalender. Det behövs en OAuth-klient <strong style="color:var(--ink)">en gång</strong> — sen räcker inloggningen. Bara den titel och anteckning du godkänner skickas, aldrig transkript eller elevdata.</p>
        ${ v.calSetup.clientReady ? `
        <div style="display:flex;align-items:center;gap:10px;background:var(--sunken);border:1px solid var(--line);border-radius:12px;padding:13px 15px;margin-bottom:14px">
          <span style="width:24px;height:24px;border-radius:50%;flex:0 0 auto;background:color-mix(in srgb,var(--ok) 18%,transparent);color:var(--ok);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700">✓</span>
          <span style="font-size:14px;color:var(--ink)">Google-klient klar — det enda som återstår är inloggningen.</span>
        </div>
        ` : `
        <div style="border:1px solid var(--line);border-radius:13px;padding:15px 16px;margin-bottom:12px;background:var(--sunken)">
          <div style="font-size:14.5px;font-weight:600;color:var(--ink);margin-bottom:5px">1 · Skapa en Google-klient <span style="font-weight:500;color:var(--ink-3)">(engång)</span></div>
          <div style="font-size:13px;color:var(--ink-2);line-height:1.55;margin-bottom:11px">Aktivera <strong style="color:var(--ink-2)">Google Calendar API</strong> och skapa en OAuth-klient av typen <strong style="color:var(--ink-2)">Desktop app</strong>. Ladda sedan ner klient-JSON:en.</div>
          <button data-click="${on(v.calSetup.onOpenConsole)}" style="display:inline-flex;align-items:center;gap:8px;background:var(--surface);border:1px solid var(--line-2);color:var(--ink);border-radius:10px;padding:9px 15px;font-size:13.5px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--ink) !important">Öppna Google Cloud Console<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h7v7"></path><path d="M13 3 6.5 9.5"></path><path d="M11 9v3.5a1 1 0 0 1-1 1H3.5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1H7"></path></svg></button>
        </div>
        <div style="border:1px solid var(--line);border-radius:13px;padding:15px 16px;margin-bottom:14px;background:var(--sunken)">
          <div style="font-size:14.5px;font-weight:600;color:var(--ink);margin-bottom:5px">2 · Installera klientfilen</div>
          <div style="font-size:13px;color:var(--ink-2);line-height:1.55;margin-bottom:11px">Välj den nedladdade JSON-filen — appen lägger den på rätt plats åt dig (inget behöver flyttas manuellt).</div>
          <button data-click="${on(v.calSetup.onPickFile)}" ${ v.calSetup.busy ? 'disabled' : '' } style="display:inline-flex;align-items:center;gap:8px;background:var(--surface);border:1px solid var(--line-2);color:var(--ink);border-radius:10px;padding:9px 15px;font-size:13.5px;font-weight:500;cursor:${ v.calSetup.busy ? 'default' : 'pointer' };font-family:inherit;opacity:${ v.calSetup.busy ? '.6' : '1' }" data-sh="border-color:var(--ink) !important">${ v.calSetup.busy ? 'Installerar …' : 'Välj klientfil …' }</button>
        </div>
        ` }
        <button data-click="${on(v.calSetup.onLogin)}" ${ (!v.calSetup.clientReady || v.calSetup.busy) ? 'disabled' : '' } style="display:flex;align-items:center;justify-content:center;gap:10px;width:100%;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:12px;padding:14px 22px;font-size:15px;font-weight:500;cursor:${ (!v.calSetup.clientReady || v.calSetup.busy) ? 'default' : 'pointer' };font-family:inherit;box-shadow:var(--shadow-sm);opacity:${ (!v.calSetup.clientReady || v.calSetup.busy) ? '.5' : '1' }">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M8 1.7a6.3 6.3 0 1 0 6 4.3H8v2.4h3.4A3.5 3.5 0 1 1 8 4.2c.9 0 1.7.3 2.3.9l1.7-1.7A6.3 6.3 0 0 0 8 1.7z"></path></svg>
          ${ v.calSetup.busy ? 'Loggar in …' : 'Logga in med Google' }
        </button>
        ${ v.calSetup.clientReady ? '' : `<div style="font-size:12px;color:var(--ink-3);text-align:center;margin-top:9px">Knappen blir klickbar när klientfilen är installerad (steg 2).</div>` }
        ` }
      </div>
      <input data-ref="${on(v.calSetup.clientFileRef)}" type="file" accept="application/json,.json" data-change="${on(v.calSetup.onClientFile)}" style="display:none">
    </div>
  </div>
  ` : '' }

  ${ v.diskWarnOpen ? `
  <div data-click="${on(v.onDiskWarnCancel)}" style="position:fixed;inset:0;z-index:130;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(11,11,13,.42);backdrop-filter:blur(3px);animation:modalback .26s ease">
    <div data-click="${on(v.stop)}" role="dialog" aria-modal="true" aria-label="Inte tillräckligt med diskutrymme" data-dialog tabindex="-1" style="width:100%;max-width:440px;background:var(--surface);border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow);padding:26px 26px 22px;animation:modalpop .42s cubic-bezier(.16,1,.3,1)">
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

  ${ v.citePeek ? `
  <div data-click="${on(v.citePeek.onClose)}" data-modal-back="${esc(v.citePeek.anim)}" style="position:fixed;inset:0;z-index:150;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(11,11,13,.42);backdrop-filter:blur(3px)">
    <div data-click="${on(v.stop)}" role="dialog" aria-modal="true" aria-label="Källa i transkriptionen" data-modal-card="${esc(v.citePeek.anim)}" style="width:100%;max-width:560px;background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);overflow:hidden">
      <div style="display:flex;align-items:center;gap:10px;padding:15px 18px;border-bottom:1px solid var(--line)">
        <span style="font-family:var(--mono);font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3)">Källa i transkriptionen</span>
        <span style="flex:1"></span>
        <button data-click="${on(v.citePeek.onClose)}" aria-label="Stäng" style="width:30px;height:30px;border:none;background:transparent;border-radius:7px;cursor:pointer;color:var(--ink-3);font-size:13px;display:flex;align-items:center;justify-content:center" data-sh="background:var(--sunken) !important;color:var(--ink) !important">✕</button>
      </div>
      <div style="padding:14px 18px 4px">
        <div style="font-size:15.5px;font-weight:600;color:var(--ink);letter-spacing:-0.01em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.citePeek.name)}</div>
        ${ v.citePeek.meta ? `<div style="font-family:var(--mono);font-size:10.5px;color:var(--ink-3);font-variant-numeric:tabular-nums;margin-top:3px">${esc(v.citePeek.meta)}</div>` : '' }
      </div>
      <div style="padding:10px 18px 14px;max-height:min(46vh,380px);overflow:auto;overscroll-behavior:contain">
        ${ v.citePeek.loading ? `
        <div style="display:flex;align-items:center;gap:9px;color:var(--ink-2);font-size:13.5px;padding:10px 0"><span style="width:13px;height:13px;border-radius:50%;border:2px solid var(--line-2);border-top-color:var(--accent);animation:spin .7s linear infinite"></span>Hämtar transkriptionen …</div>
        ` : v.citePeek.empty ? `
        <div style="color:var(--ink-2);font-size:13.5px;padding:10px 0">Kunde inte hämta transkriptionen — öppna chattvyn för att läsa hela.</div>
        ` : v.citePeek.rows.map(function(r2){ return `
        <div style="display:flex;gap:12px;align-items:flex-start;padding:7px 9px;border-radius:6px;${r2.hit ? 'background:var(--accent-weak)' : ''}">
          <span style="flex:0 0 auto;font-family:var(--mono);font-size:11px;color:${r2.hit ? 'var(--accent)' : 'var(--ink-3)'};font-weight:${r2.hit ? '700' : '500'};font-variant-numeric:tabular-nums;padding-top:2px">${esc(r2.time)}</span>
          <span style="min-width:0;font-size:14px;line-height:1.6;color:var(--ink)">${esc(r2.text)}</span>
        </div>
        `; }).join('') }
        ${ v.citePeek.more ? `<div style="font-family:var(--mono);font-size:10px;letter-spacing:0.07em;text-transform:uppercase;color:var(--ink-3);padding:9px 9px 0">+ ${esc(String(v.citePeek.more))} ställe${v.citePeek.more === 1 ? '' : 'n'} till — öppna chattvyn för hela transkriptionen</div>` : '' }
      </div>
      <div style="display:flex;gap:10px;justify-content:flex-end;padding:13px 18px;border-top:1px solid var(--line);background:var(--sunken)">
        <button data-click="${on(v.citePeek.onClose)}" style="background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:9px;padding:9px 15px;font-size:13.5px;font-weight:500;cursor:pointer;font-family:inherit">Stäng</button>
        <button data-click="${on(v.citePeek.onOpenChat)}" style="display:inline-flex;align-items:center;gap:7px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:9px;padding:9px 16px;font-size:13.5px;font-weight:500;cursor:pointer;font-family:inherit">Öppna i chattvyn<svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8h10M9 4l4 4-4 4"></path></svg></button>
      </div>
    </div>
  </div>
  ` : '' }

  ${ v.confirmOpen ? `
  <div data-click="${on(v.onConfirmNo)}" style="position:fixed;inset:0;z-index:140;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(11,11,13,.42);backdrop-filter:blur(3px);animation:modalback .26s ease">
    <div data-click="${on(v.stop)}" role="dialog" aria-modal="true" aria-label="Bekräfta" data-dialog tabindex="-1" style="width:100%;max-width:420px;background:var(--surface);border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow);padding:26px;animation:modalpop .42s cubic-bezier(.16,1,.3,1)">
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
  <div role="status" aria-live="polite" aria-atomic="true" style="position:fixed;left:50%;bottom:30px;transform:translate(-50%,0);z-index:200;display:flex;align-items:center;gap:13px;background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:13px 20px 13px 13px;box-shadow:var(--shadow);width:336px;animation:toastin .32s cubic-bezier(.16,1,.3,1)">
    ${ v.toastError ? `
      <span style="width:40px;height:40px;border-radius:12px;flex:0 0 auto;display:flex;align-items:center;justify-content:center;background:color-mix(in srgb,var(--bad) 15%,transparent);color:var(--bad);font-size:20px;font-weight:700">!</span>
    ` : '' }
    ${ v.toastLoading ? `
      <span style="width:40px;height:40px;border-radius:12px;flex:0 0 auto;display:flex;align-items:center;justify-content:center;background:var(--accent-weak);color:var(--accent)">
        <span style="display:flex;animation:dlbounce .85s ease-in-out infinite"><svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v8"></path><path d="M4.5 6.5 8 10l3.5-3.5"></path><path d="M3 13.5h10"></path></svg></span>
      </span>
    ` : '' }
    ${ v.toastDone ? `
      <span style="width:40px;height:40px;border-radius:12px;flex:0 0 auto;display:flex;align-items:center;justify-content:center;background:color-mix(in srgb,var(--ok) 16%,transparent);color:var(--ok);font-size:18px">✓</span>
    ` : '' }
    ${ v.toastError ? `
    <div style="min-width:0;flex:1">
      <div style="font-size:14.5px;font-weight:600;color:var(--ink);letter-spacing:-0.01em;margin-bottom:3px">${esc(v.toastTitle)}</div>
      <div style="font-size:12.5px;color:var(--ink-2);line-height:1.5;word-break:break-word">${esc(v.toastMessage)}</div>
    </div>
    ` : `
    <div style="min-width:0;flex:1">
      <div style="display:flex;align-items:baseline;justify-content:space-between;gap:10px">
        <span style="font-size:14.5px;font-weight:600;color:var(--ink);letter-spacing:-0.01em">${esc(v.toastTitle)}</span>
        <span style="font-size:12.5px;color:var(--ink-2);font-variant-numeric:tabular-nums;flex:0 0 auto">${esc(v.toastName)}</span>
      </div>
      ${ v.toastLoading ? `
      <div style="height:6px;border-radius:99px;background:var(--track);overflow:hidden;margin:7px 0 5px"><div style="${v.toastBarStyle}"></div></div>
      <div style="font-size:12px;color:var(--ink-2);font-variant-numeric:tabular-nums">${esc(v.toastDetail)}</div>
      ` : '' }
    </div>
    ` }
    <button data-click="${on(v.closeToast)}" aria-label="Stäng" style="width:32px;height:32px;flex:0 0 auto;align-self:flex-start;border:none;background:transparent;border-radius:7px;cursor:pointer;color:var(--ink-3);font-size:13px;display:flex;align-items:center;justify-content:center" data-sh="background:var(--sunken) !important;color:var(--ink) !important">✕</button>
  </div>
  ` : '' }
`; }

// Planering (Fas 0/1): tavlan är artefakten — ett uppslag, ingen dashboard.
// Iframen skyddas från morphdom via data-wb-frame (se onBeforeElUpdated).
function viewPlanning(v){
  return `
    <section style="min-height:calc(100vh - 80px);display:flex;flex-direction:column;padding:16px 0 28px">
      <div class="ehead">
        <div>
          <div class="eyebrow" style="margin-bottom:18px">Planering</div>
          <h1 class="disp" style="font-size:clamp(34px,5.2vw,52px);margin:0">Dagens <span class="ser">tavla</span></h1>
        </div>
        <p class="ehead_lede">Beskriv momentet — och välj kurs om du vill — så skrivs tavlan som du annars hade skrivit för hand vid lektionens start. Iterera via chatten tills den sitter.</p>
      </div>

      <div style="display:flex;flex-direction:column;gap:13px;margin-bottom:18px">
        <div style="display:flex;gap:9px;align-items:stretch;flex-wrap:wrap">
          <input value="${esc(v.planMoment)}" data-input="${on(v.onPlanMoment)}" data-keydown="${on(v.onPlanMomentKey)}" aria-label="Moment" placeholder="Moment — t.ex. derivatans definition" style="flex:1;min-width:240px;background:var(--surface);border:1px solid var(--line);border-radius:4px;padding:13px 15px;font-size:15.5px;font-family:inherit;color:var(--ink)">
          <button data-click="${on(v.onPlanStart)}" ${v.planCanStart ? '' : 'disabled'} style="display:inline-flex;align-items:center;gap:7px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:4px;padding:13px 22px;font-size:14.5px;font-weight:500;font-family:inherit;cursor:${v.planCanStart ? 'pointer' : 'default'};opacity:${v.planCanStart ? '1' : '.55'}">${v.planRunning ? 'Skriver …' : 'Skriv tavlan'}</button>
        </div>
        <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
          ${ v.planCourseGroups.map(function(g){ return `
          <div role="group" aria-label="${esc(g.amne)}" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
            <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);margin-right:3px">${esc(g.amne)}</span>
            ${ g.chips.map(function(c){ return `<button data-click="${on(c.onPick)}" data-chip="${c.sel ? 'on' : 'off'}" aria-pressed="${c.sel ? 'true' : 'false'}" title="${esc(c.namn)}" style="font-family:inherit;font-size:13px;font-weight:500;padding:6px 12px;border-radius:3px;background:var(--surface);color:var(--ink-2);border:1px solid var(--line);transition:border-color .14s,background .14s,color .14s">${esc(c.kort)}</button>`; }).join('') }
          </div>
          `; }).join('') }
          ${ v.planHasGroups ? `
          <div role="group" aria-label="Klass" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
            <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);margin-right:3px">Klass</span>
            ${ v.planGroupOpts.map(function(g){ return `<button data-click="${on(g.onPick)}" data-chip="${g.sel ? 'on' : 'off'}" aria-pressed="${g.sel ? 'true' : 'false'}" style="font-family:inherit;font-size:13px;font-weight:500;padding:6px 12px;border-radius:3px;background:var(--surface);color:var(--ink-2);border:1px solid var(--line);transition:border-color .14s,background .14s,color .14s">${esc(g.namn)}</button>`; }).join('') }
          </div>
          ` : '' }
          <span style="flex:1"></span>
          <div style="display:flex;align-items:center;gap:6px">
            <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);margin-right:3px">När</span>
            <input type="date" value="${esc(v.planDatum)}" data-change="${on(v.onPlanDatum)}" aria-label="Datum" style="background:var(--surface);border:1px solid var(--line);border-radius:3px;padding:6px 9px;font-size:13px;font-family:inherit;color:var(--ink-2)">
            <input type="time" value="${esc(v.planStarttid)}" data-change="${on(v.onPlanStarttid)}" aria-label="Starttid" style="background:var(--surface);border:1px solid var(--line);border-radius:3px;padding:6px 9px;font-size:13px;font-family:inherit;color:var(--ink-2)">
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);margin-right:3px">Underlag</span>
          ${ v.planUnderlagBusy ? `
          <span style="display:inline-flex;align-items:center;gap:8px;font-size:13px;color:var(--ink-2)"><span style="width:13px;height:13px;border-radius:50%;border:2px solid var(--line-2);border-top-color:var(--accent);animation:spin .7s linear infinite"></span>Läser och tolkar sidorna …</span>
          ` : v.planUnderlag ? `
          ${ v.planUnderlag.filer.map(function(f){ return `<span title="${esc(f.beskrivning || f.namn)}" style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);border-radius:3px;padding:4px 10px;max-width:220px"><span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(f.namn)}</span></span>`; }).join('') }
          <button data-click="${on(v.onClearUnderlag)}" aria-label="Ta bort underlaget" title="Ta bort underlaget" style="border:none;background:transparent;color:var(--ink-3);cursor:pointer;font-size:12px;padding:2px 6px;font-family:inherit">✕</button>
          <button data-click="${on(v.onPickUnderlag)}" style="border:none;background:transparent;color:var(--ink-2);cursor:pointer;font-size:12.5px;font-family:inherit;padding:2px 4px;text-decoration:underline;text-underline-offset:3px">Byt</button>
          ` : `
          <button data-click="${on(v.onPickUnderlag)}" title="Ladda upp sidor ur läroboken eller uppgifter som lektionen ska bygga på — behandlas lokalt" style="display:inline-flex;align-items:center;gap:7px;border:1px dashed var(--line-2);background:transparent;color:var(--ink-2);border-radius:3px;padding:6px 12px;font-size:12.5px;font-family:inherit;cursor:pointer">＋ Bokssidor eller uppgifter (PNG, JPG, PDF)</button>
          ` }
        </div>
      </div>

      ${ (v.planRunning || v.planUnderlagBusy) && v.planHasLog ? `
        <div role="status" style="display:flex;flex-direction:column;gap:3px;margin-bottom:12px;font-size:13px;color:var(--ink-2)">
          ${ v.planLog.map(function(l){ return `<span>${esc(l)}</span>`; }).join('') }
        </div>
      ` : '' }

      ${ v.planErrCount ? `
        <div role="status" style="display:flex;flex-direction:column;gap:4px;margin-bottom:12px;font-size:13px;color:var(--warn)">
          <span style="font-weight:600">${esc(v.planErrCount)} problem kvarstår efter reparationsförsöken:</span>
          ${ v.planErrors.map(function(e2){ return `<span style="font-family:var(--mono,monospace);font-size:12px;color:var(--ink-2)">${esc(typeof e2 === 'string' ? e2 : (e2.path ? e2.path + ': ' : '') + (e2.message || ''))}</span>`; }).join('') }
        </div>
      ` : '' }

      <div data-wbwrap="${esc(v.wbZoomFlag)}" data-click="${on(v.onWbZoomClose)}">
      <div data-key="wb-card" data-wbzoom="${esc(v.wbZoomFlag)}" data-click="${on(v.onWbCardClick)}" role="${v.wbZoomOn ? 'dialog' : ''}" aria-label="${v.wbZoomOn ? 'Förstorad lektionstavla' : ''}" style="background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px;box-shadow:var(--shadow-sm)">
        <div style="display:flex;align-items:center;gap:10px;margin:2px 2px 10px">
          <span style="font-size:15px;font-weight:600;color:var(--ink)">${esc(v.wbTitle)}</span>
          ${ v.planIsExample ? `<span style="font-size:12px;text-transform:uppercase;letter-spacing:0.05em;color:var(--ink-3);font-weight:600">Exempellektion</span>` : '' }
          <span style="flex:1"></span>
          ${ v.wbZoomFlag ? `
          <button data-click="${on(v.onWbZoomClose)}" aria-label="Stäng förstoringen" title="Stäng (Esc)" style="border:none;background:transparent;color:var(--ink-3);cursor:pointer;font-size:14px;line-height:1;padding:5px 8px;border-radius:3px;font-family:inherit">✕</button>
          ` : `
          <button data-click="${on(v.onWbZoomOpen)}" ${v.wbRendered ? '' : 'disabled'} aria-label="Förstora tavlan" title="Förstora — arbeta med tavlan i helskärm" style="display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:3px;padding:6px 11px;font-size:12.5px;font-weight:500;font-family:inherit;cursor:${v.wbRendered ? 'pointer' : 'default'};opacity:${v.wbRendered ? '1' : '.55'}"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6.5 6.5L2 2m0 0v3.5M2 2h3.5M9.5 6.5L14 2m0 0v3.5M14 2h-3.5M6.5 9.5L2 14m0 0v-3.5M2 14h3.5M9.5 9.5L14 14m0 0v-3.5M14 14h-3.5"></path></svg>Förstora</button>
          ` }
        </div>
        <iframe data-wb-frame data-key="wb-frame" src="/static/whiteboard/board.html" title="Lektionstavla — ${esc(v.wbTitle)}" style="width:100%;height:420px;border:none;display:block;border-radius:8px;background:#2c2c2c"></iframe>
        ${ v.wbZoomFlag ? `
        <div style="display:flex;flex-direction:column;gap:9px;margin-top:11px;flex:0 0 auto">
          ${ v.planId ? `
          <div style="display:flex;align-items:center;gap:8px">
            <input value="${esc(v.planChatInput)}" data-input="${on(v.onPlanChatInput)}" data-keydown="${on(v.onPlanChatKey)}" aria-label="Ändra tavlan" placeholder="Ändra tavlan — t.ex. byt exempel 2 mot ett med decimaltal" style="flex:1;min-width:0;background:var(--surface);border:1px solid var(--line);border-radius:4px;padding:10px 13px;font-size:14.5px;font-family:inherit;color:var(--ink)">
            <button data-click="${on(v.onPlanRefine)}" ${v.planChatInput.trim() && !v.planRunning ? '' : 'disabled'} style="display:inline-flex;align-items:center;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:4px;padding:10px 16px;font-size:14.5px;font-weight:500;font-family:inherit;cursor:${v.planChatInput.trim() && !v.planRunning ? 'pointer' : 'default'};opacity:${v.planChatInput.trim() && !v.planRunning ? '1' : '.55'}">${v.planRunning ? 'Ändrar …' : 'Ändra'}</button>
          </div>
          ` : '' }
          <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
            ${ v.planId ? `
            <button data-click="${on(v.onPlanApprove)}" ${v.wbRendered && !v.planRunning ? '' : 'disabled'} style="display:inline-flex;align-items:center;gap:7px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:4px;padding:10px 17px;font-size:14.5px;font-weight:500;font-family:inherit;cursor:${v.wbRendered && !v.planRunning ? 'pointer' : 'default'};opacity:${v.wbRendered && !v.planRunning ? '1' : '.55'}">Godkänn &amp; spara</button>
            ` : '' }
            <button data-click="${on(v.onWbPrint)}" ${v.wbRendered ? '' : 'disabled'} style="display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:4px;padding:10px 17px;font-size:14.5px;font-weight:500;font-family:inherit;cursor:${v.wbRendered ? 'pointer' : 'default'};opacity:${v.wbRendered ? '1' : '.55'}">Skriv ut</button>
            <button data-click="${on(v.onWbExport)}" ${v.wbRendered && !v.wbExporting ? '' : 'disabled'} style="display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:4px;padding:10px 17px;font-size:14.5px;font-weight:500;font-family:inherit;cursor:${v.wbRendered && !v.wbExporting ? 'pointer' : 'default'};opacity:${v.wbRendered && !v.wbExporting ? '1' : '.55'}">${v.wbExporting ? 'Sparar …' : 'Spara som PNG'}</button>
            ${ v.planRunning ? `<span style="font-size:13.5px;color:var(--ink-2)">Skriver om tavlan …</span>` : '' }
            ${ v.planSavedPath ? `<span role="status" style="font-size:13.5px;color:var(--ink-2);word-break:break-all">Sparad: ${esc(v.planSavedPath)}</span>` : '' }
            ${ v.wbExportMsg ? `<span role="status" style="font-size:13.5px;color:${v.wbExportFailed ? 'var(--bad)' : 'var(--ink-2)'};word-break:break-all">${esc(v.wbExportMsg)}</span>` : '' }
          </div>
        </div>
        ` : '' }
      </div>
      </div>

      ${ v.wbWarnCount ? `
        <div role="status" style="display:flex;flex-direction:column;gap:4px;margin-top:10px;font-size:13px;color:var(--warn)">
          <span style="font-weight:600">Motorn flaggade ${esc(v.wbWarnCount)} ${v.wbWarnCount === 1 ? 'layoutvarning' : 'layoutvarningar'}:</span>
          ${ v.wbWarnings.map(function(w){ return `<span style="font-family:var(--mono,monospace);font-size:12px;color:var(--ink-2)">${esc(w)}</span>`; }).join('') }
        </div>
      ` : '' }

      ${ v.planId ? `
        <div style="display:flex;align-items:center;gap:8px;margin-top:14px">
          <input value="${esc(v.planChatInput)}" data-input="${on(v.onPlanChatInput)}" data-keydown="${on(v.onPlanChatKey)}" aria-label="Ändra tavlan" placeholder="Ändra tavlan — t.ex. byt exempel 2 mot ett med decimaltal" style="flex:1;min-width:0;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 13px;font-size:14.5px;font-family:inherit;color:var(--ink)">
          <button data-click="${on(v.onPlanRefine)}" ${v.planChatInput.trim() && !v.planRunning ? '' : 'disabled'} style="display:inline-flex;align-items:center;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:10px;padding:10px 16px;font-size:14.5px;font-weight:500;font-family:inherit;cursor:${v.planChatInput.trim() && !v.planRunning ? 'pointer' : 'default'};opacity:${v.planChatInput.trim() && !v.planRunning ? '1' : '.55'}">Ändra</button>
        </div>
      ` : '' }

      <div style="display:flex;align-items:center;gap:10px;margin-top:14px;flex-wrap:wrap">
        ${ v.planId ? `
          <button data-click="${on(v.onPlanApprove)}" ${v.wbRendered && !v.planRunning ? '' : 'disabled'} style="display:inline-flex;align-items:center;gap:7px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:10px;padding:10px 17px;font-size:14.5px;font-weight:500;font-family:inherit;cursor:${v.wbRendered && !v.planRunning ? 'pointer' : 'default'};opacity:${v.wbRendered && !v.planRunning ? '1' : '.55'};box-shadow:var(--shadow-sm)">Godkänn &amp; spara</button>
        ` : '' }
        <button data-click="${on(v.onWbPrint)}" ${v.wbRendered ? '' : 'disabled'} style="display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:10px;padding:10px 17px;font-size:14.5px;font-weight:500;font-family:inherit;cursor:${v.wbRendered ? 'pointer' : 'default'};opacity:${v.wbRendered ? '1' : '.55'};box-shadow:var(--shadow-sm)">Skriv ut</button>
        <button data-click="${on(v.onWbExport)}" ${v.wbRendered && !v.wbExporting ? '' : 'disabled'} style="display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:10px;padding:10px 17px;font-size:14.5px;font-weight:500;font-family:inherit;cursor:${v.wbRendered && !v.wbExporting ? 'pointer' : 'default'};opacity:${v.wbRendered && !v.wbExporting ? '1' : '.55'};box-shadow:var(--shadow-sm)">${v.wbExporting ? 'Sparar …' : 'Spara som PNG'}</button>
        ${ !v.wbRendered && !v.wbWarnCount && !v.planRunning ? `<span style="font-size:13.5px;color:var(--ink-3)">Ritar tavlan …</span>` : '' }
        ${ v.planSavedPath ? `<span role="status" style="font-size:13.5px;color:var(--ink-2);font-variant-numeric:tabular-nums;word-break:break-all">Sparad: ${esc(v.planSavedPath)}</span>` : '' }
        ${ v.wbExportMsg ? `<span role="status" style="font-size:13.5px;color:${v.wbExportFailed ? 'var(--bad)' : 'var(--ink-2)'};font-variant-numeric:tabular-nums;word-break:break-all">${esc(v.wbExportMsg)}</span>` : '' }
      </div>

      ${ v.arkiv ? `
      <div style="margin-top:44px">
        <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:16px;flex-wrap:wrap">
          <span class="eyebrow">Arkiv</span>
          <span style="font-size:13.5px;color:var(--ink-3)">Sök bland dina tavlor och prov, eller fråga AI:n vad ni gått igenom.</span>
          <span style="flex:1"></span>
          <span style="font-family:var(--mono);font-size:10.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3)">${esc(String(v.arkiv.count))} ${v.arkiv.count === 1 ? 'post' : 'poster'}</span>
        </div>

        ${ spotlightPanel(v.arkiv.search) }

        ${ v.arkiv.scan ? `
        <div style="margin:20px 0 8px;animation:fadeup .3s ease both">
          ${ scanTheater(v.arkiv.scan.theater) }

          ${ v.arkiv.ansStarted ? `
          <div style="margin-top:16px;border:1px solid var(--line);border-radius:13px;background:var(--surface);box-shadow:var(--shadow-sm);animation:fadeup .3s ease both;overflow:hidden">
            <div style="display:grid;grid-template-columns:minmax(0,1fr) 224px;align-items:stretch">
              <div style="min-width:0;padding:14px 17px">
                <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3)">${esc(v.arkiv.ansHeadLabel)}</div>
                <div style="font-size:12.5px;color:var(--ink-3);margin-top:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">”${esc(v.arkiv.q)}”</div>
                <p style="margin:8px 0 0;font-size:15.5px;line-height:1.8;color:var(--ink);max-width:62ch;white-space:pre-wrap">${esc(v.arkiv.answer)}${ v.arkiv.ansTyping ? '<span class="ai-blink" style="display:inline-block;width:9px;height:17px;background:var(--accent);vertical-align:-3px;margin-left:3px"></span>' : '' }</p>
                ${ v.arkiv.followups.length ? `
                <div style="margin-top:16px;border-top:1px solid var(--line);padding-top:13px">
                  ${ v.arkiv.followups.map(function(f){ return `
                    <div data-key="${esc(f.key)}" style="display:flex;flex-direction:column;gap:8px;margin-bottom:14px">
                      <div style="align-self:flex-end;max-width:86%;background:var(--accent-weak);color:var(--ink);border:1px solid color-mix(in srgb,var(--accent) 25%,transparent);border-radius:14px 14px 4px 14px;padding:9px 13px;font-size:14px;line-height:1.5">${esc(f.q)}</div>
                      <div style="align-self:stretch;font-size:14.5px;line-height:1.75;color:var(--ink);white-space:pre-wrap">${esc(f.a)}${ f.typing ? '<span class="ai-blink" style="display:inline-block;width:8px;height:15px;background:var(--accent);vertical-align:-2px;margin-left:3px"></span>' : '' }</div>
                    </div>
                  `; }).join('') }
                </div>
                ` : '' }
                ${ v.arkiv.ansDone ? `
                <div style="display:flex;gap:9px;align-items:center;margin-top:12px">
                  <input value="${esc(v.arkiv.followInput)}" data-input="${on(v.arkiv.setFollow)}" data-keydown="${on(v.arkiv.onFollowKey)}" aria-label="Ställ en följdfråga" placeholder="Ställ en följdfråga …" style="flex:1;min-width:0;background:var(--sunken);border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:10px 13px;font-size:14px;font-family:inherit;outline:none">
                  <button data-click="${on(v.arkiv.sendFollow)}" style="flex:0 0 auto;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:10px;padding:10px 17px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit;transition:background .15s">Skicka</button>
                </div>
                ` : '' }
              </div>
              <div style="display:flex;flex-direction:column;gap:6px;padding:12px;background:var(--sunken);border-left:1px solid var(--line);min-width:0">
                <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3)">Källor</span>
                ${ v.arkiv.sources.length ? v.arkiv.sources.map(function(s2){ return `
                  <button data-key="${esc(s2.key)}" data-click="${on(s2.onOpen)}" title="Öppna och se exakt vad den innehåller" style="text-align:left;border:1px solid var(--line);background:var(--surface);border-radius:9px;padding:8px 10px;cursor:pointer;font-family:inherit;min-width:0" data-sh="border-color:var(--accent) !important">
                    <span style="font-family:var(--mono);font-size:9px;letter-spacing:0.07em;text-transform:uppercase;color:var(--accent);display:block">${esc(s2.typLabel)}</span>
                    <span style="font-size:12.5px;font-weight:600;color:var(--ink);display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px">${esc(s2.titel)}</span>
                    ${ s2.sub ? `<span style="font-size:11px;color:var(--ink-3);display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:1px">${esc(s2.sub)}</span>` : '' }
                  </button>
                `; }).join('') : `<span style="font-size:12px;color:var(--ink-3)">${ v.arkiv.ansTyping || !v.arkiv.ansDone ? 'Söker …' : 'Inga källor' }</span>` }
              </div>
            </div>
          </div>
          ` : '' }
        </div>
        ` : '' }

        ${ v.arkiv.empty ? `
          <div style="margin-top:18px;text-align:center;padding:42px 24px;background:var(--surface);border:1px dashed var(--line-2);border-radius:13px;color:var(--ink-2);font-size:14.5px">Inga tavlor eller prov än — godkänn en tavla eller skriv ett prov så samlas de här, vecka för vecka.</div>
        ` : v.arkiv.weeks.map(function(w){ return `
          <div data-key="aw-${esc(w.key)}">
            <div style="display:flex;align-items:baseline;gap:18px;margin:30px 0 10px;padding-bottom:10px;border-bottom:2px solid var(--ink)">
              <span class="disp" style="font-size:clamp(21px,2.3vw,26px);line-height:1;color:var(--ink);white-space:nowrap;flex:0 0 auto">&#8203;${ w.isWeek ? `<span class="ser" style="color:var(--ink-3)">Vecka</span>&nbsp;${esc(w.num)}` : `<span class="ser" style="color:var(--ink-3)">Utan datum</span>` }</span>
              <span style="font-family:var(--mono);font-size:11px;letter-spacing:0.09em;text-transform:uppercase;color:var(--ink-2)">${esc(w.range)}</span>
              <span style="flex:1"></span>
              <span style="font-family:var(--mono);font-size:10.5px;letter-spacing:0.09em;text-transform:uppercase;color:var(--ink-3)">${esc(w.count)}</span>
            </div>
            <div style="display:flex;flex-direction:column">
              ${ w.rows.map(function(r2){ return `
                <button data-key="ark-${esc(r2.key)}" data-click="${on(r2.onOpen)}" title="Öppna ${r2.typ === 'tavla' ? 'tavlan i tavelkortet ovanför' : 'provet i provkortet nedanför'}" style="display:flex;align-items:center;gap:12px;width:100%;text-align:left;background:transparent;border:none;border-bottom:1px solid color-mix(in srgb,var(--line) 60%,transparent);padding:10px 6px;font-family:inherit;cursor:pointer;transition:background .14s" data-sh="background:var(--surface) !important">
                  <span style="flex:0 0 76px;font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:${r2.typ === 'tavla' ? 'var(--accent)' : 'var(--ink-2)'}">${esc(r2.typLabel)}</span>
                  <span style="min-width:0;flex:1;font-size:14.5px;font-weight:500;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;${r2.cancelled ? 'text-decoration:line-through;opacity:.55' : ''}">${esc(r2.titel)}</span>
                  <span data-cc="${esc(r2.cc)}" style="flex:0 1 auto;min-width:0;border-radius:99px;padding:2px 10px;font-size:11px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(r2.tag)}</span>
                  ${ r2.held || r2.godkand ? `<span style="flex:0 0 auto;font-family:var(--mono);font-size:9.5px;letter-spacing:0.07em;text-transform:uppercase;color:var(--ok)">✓ ${esc(r2.statusLabel)}</span>` : '' }
                  <span style="flex:0 0 auto;font-family:var(--mono);font-size:10.5px;color:var(--ink-3);font-variant-numeric:tabular-nums">${esc(r2.datum)}${ r2.starttid ? ' · ' + esc(r2.starttid) : '' }</span>
                </button>
              `; }).join('') }
            </div>
          </div>
        `; }).join('') }
      </div>
      ` : '' }

      <div style="margin-top:38px">
        <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:12px">
          <span class="eyebrow">Prov</span>
          <span style="font-size:13.5px;color:var(--ink-3)">NP-lik struktur — uppgifterna är alltid egenformulerade</span>
        </div>

        <div style="display:flex;flex-direction:column;gap:13px;margin-bottom:15px">
          <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
            <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);flex:0 0 68px">Typ</span>
            <div role="group" aria-label="Dokumenttyp" style="display:inline-flex;gap:3px;padding:3px;background:var(--track);border-radius:4px;border:1px solid var(--line)">
              <button data-click="${on(v.onExTypProv)}" aria-pressed="${v.exTyp === 'prov' ? 'true' : 'false'}" data-seg="${v.exTyp === 'prov' ? 'on' : 'off'}" style="border:none;border-radius:3px;padding:7px 15px;font-size:13.5px;font-weight:500;font-family:inherit;background:transparent;color:var(--ink-2);transition:color .18s ease">Prov</button>
              <button data-click="${on(v.onExTypArbetsblad)}" aria-pressed="${v.exTyp === 'arbetsblad' ? 'true' : 'false'}" data-seg="${v.exTyp === 'arbetsblad' ? 'on' : 'off'}" style="border:none;border-radius:3px;padding:7px 15px;font-size:13.5px;font-weight:500;font-family:inherit;background:transparent;color:var(--ink-2);transition:color .18s ease">Arbetsblad</button>
            </div>
          </div>
          <div style="display:flex;align-items:flex-start;gap:14px;flex-wrap:wrap">
            <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);flex:0 0 68px;padding-top:8px">Kurs</span>
            <div style="flex:1;min-width:260px;display:flex;align-items:center;gap:16px;flex-wrap:wrap">
              ${ v.exCourseGroups.map(function(g){ return `
              <div role="group" aria-label="${esc(g.amne)}" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
                <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);margin-right:3px">${esc(g.amne)}</span>
                ${ g.chips.map(function(c){ return `<button data-click="${on(c.onPick)}" data-chip="${c.sel ? 'on' : 'off'}" aria-pressed="${c.sel ? 'true' : 'false'}" title="${esc(c.namn)}" style="font-family:inherit;font-size:13px;font-weight:500;padding:6px 12px;border-radius:3px;background:var(--surface);color:var(--ink-2);border:1px solid var(--line);transition:border-color .14s,background .14s,color .14s">${esc(c.kort)}</button>`; }).join('') }
              </div>
              `; }).join('') }
              ${ v.exGroupOpts.length ? `
              <div role="group" aria-label="Klass" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
                <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);margin-right:3px">Klass</span>
                ${ v.exGroupOpts.map(function(g){ return `<button data-click="${on(g.onPick)}" data-chip="${g.sel ? 'on' : 'off'}" aria-pressed="${g.sel ? 'true' : 'false'}" style="font-family:inherit;font-size:13px;font-weight:500;padding:6px 12px;border-radius:3px;background:var(--surface);color:var(--ink-2);border:1px solid var(--line);transition:border-color .14s,background .14s,color .14s">${esc(g.namn)}</button>`; }).join('') }
              </div>
              ` : '' }
            </div>
          </div>

          ${ v.exContentGroups.length ? `
          <div style="display:flex;align-items:flex-start;gap:14px;flex-wrap:wrap">
            <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);flex:0 0 68px;padding-top:10px">Innehåll</span>
            <div style="flex:1;min-width:300px;display:flex;flex-direction:column;gap:7px">
              ${ v.exContentGroups.map(function(g3){ return `
              <div data-ccg="" data-ccg-open="${g3.open ? 'true' : 'false'}" data-key="ccg-${esc(g3.rubrik)}">
                <button data-ccg-head="" data-click="${on(g3.onToggleOpen)}" aria-expanded="${g3.open ? 'true' : 'false'}">
                  <svg data-ccg-caret="" width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex:0 0 auto;color:var(--ink-3)"><path d="M6 4l4 4-4 4"></path></svg>
                  <span style="font-family:var(--mono);font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-2);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(g3.rubrik)}</span>
                  <span style="flex:1"></span>
                  <span data-ccg-count="${g3.valda ? 'on' : 'off'}" style="font-family:var(--mono);font-size:10px;letter-spacing:0.05em;color:var(--ink-3);font-variant-numeric:tabular-nums;white-space:nowrap">${ g3.valda ? esc(g3.valda) + ' valda av ' + esc(g3.punkter.length) : esc(g3.punkter.length) + ' punkter' }</span>
                </button>
                <div data-ccg-body=""><div>
                  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1px 18px;padding:1px 10px 9px">
                    ${ g3.punkter.map(function(p){ return `
                    <button data-key="cc-${esc(p.id)}" data-ccrow="" data-click="${on(p.onToggle)}" aria-pressed="${p.vald}" aria-label="${esc(p.text)} — ${esc(p.statusText)}" title="${esc(p.text)}">
                      <span data-ck="${p.vald ? 'on' : 'off'}" aria-hidden="true"><svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 6.5l2.4 2.4 4.6-5.3"></path></svg></span>
                      <span style="min-width:0;flex:1;font-size:13px;line-height:1.35;color:${p.vald ? 'var(--ink)' : 'var(--ink-2)'}">${esc(p.kort)}</span>
                      <span aria-hidden="true" title="${esc(p.statusText)}" style="flex:0 0 auto;font-size:11px;color:var(--ink-3)">${ p.provad ? '★' : p.behandlad ? '✓' : '○' }</span>
                    </button>`; }).join('') }
                  </div>
                </div></div>
              </div>
              `; }).join('') }
              <div style="font-size:12px;color:var(--ink-3);margin-top:2px">Valfritt — ${ v.exValdaTotal ? esc(v.exValdaTotal) + ' punkter valda, uppgifterna byggs på dem' : 'utan val väljer modellen fritt ur kursens innehåll' }. &nbsp;○ ej behandlat · ✓ behandlat · ★ redan prövat</div>
            </div>
          </div>
          ` : '' }

          <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
            <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);flex:0 0 68px">Omfång</span>
            <div role="group" aria-label="Omfång" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
              <label style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-3)"><input type="number" min="3" max="20" value="${esc(v.exAntal)}" data-change="${on(v.onExAntal)}" aria-label="Antal uppgifter" style="background:var(--surface);border:1px solid var(--line);border-radius:3px;padding:6px 9px;font-size:13px;font-family:inherit;color:var(--ink-2);width:56px;font-variant-numeric:tabular-nums">uppgifter</label>
              <label style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-3)"><input type="number" min="30" max="300" step="10" value="${esc(v.exTid)}" data-change="${on(v.onExTid)}" aria-label="Provtid (minuter)" style="background:var(--surface);border:1px solid var(--line);border-radius:3px;padding:6px 9px;font-size:13px;font-family:inherit;color:var(--ink-2);width:64px;font-variant-numeric:tabular-nums">min</label>
              <button data-click="${on(v.onExDelar)}" data-chip="${v.exDelar ? 'on' : 'off'}" aria-pressed="${v.exDelar ? 'true' : 'false'}" title="Dela provet i Del B (utan räknare) och Del C (med räknare)" style="font-family:inherit;font-size:13px;font-weight:500;padding:6px 12px;border-radius:3px;background:var(--surface);color:var(--ink-2);border:1px solid var(--line);transition:border-color .14s,background .14s,color .14s">Del B/C</button>
            </div>
            <div style="display:flex;align-items:center;gap:6px">
              <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);margin-right:3px">När</span>
              <input type="date" value="${esc(v.exDatum)}" data-change="${on(v.onExDatum)}" aria-label="Provdatum" style="background:var(--surface);border:1px solid var(--line);border-radius:3px;padding:6px 9px;font-size:13px;font-family:inherit;color:var(--ink-2)">
            </div>
            ${ v.exReferensVal.length ? `
            <div style="display:flex;align-items:center;gap:6px">
              <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);margin-right:3px">Referens</span>
              <div style="position:relative" data-enter="${on(v.exRefEnter)}" data-leave="${on(v.exRefLeave)}">
                <button data-click="${on(v.exRefToggle)}" aria-haspopup="listbox" aria-expanded="${v.exRefOpen ? 'true' : 'false'}" data-filter-on="${esc(v.exRefOn)}" title="Utgå från ett tidigare prov — variera och höj svårighetsgraden" style="display:inline-flex;align-items:center;gap:8px;background:var(--surface);border:1px solid var(--line);color:var(--ink-2);border-radius:3px;padding:6px 12px;font-size:13px;font-weight:500;font-family:inherit;cursor:pointer;white-space:nowrap;max-width:280px;transition:border-color .14s"><span style="min-width:0;overflow:hidden;text-overflow:ellipsis">${esc(v.exRefLabel)}</span><svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="flex:0 0 auto;transition:transform .2s cubic-bezier(.16,1,.3,1);transform:${v.exRefOpen ? 'rotate(180deg)' : 'none'}"><path d="M4 6l4 4 4-4"></path></svg></button>
                ${ v.exRefOpen ? `
                <div data-pop="${esc(v.exRefAnim)}" style="position:absolute;top:100%;left:0;z-index:30;padding-top:6px"><div role="listbox" aria-label="Referensprov" style="min-width:210px;max-width:320px;background:var(--surface);border:1px solid var(--line-2);border-radius:5px;box-shadow:var(--shadow);padding:5px;display:flex;flex-direction:column;gap:1px">
                  ${ v.exRefOpts.map(function(o){ return `
                  <button data-key="${esc(o.key)}" data-click="${on(o.onSelect)}" data-opt="" role="option" aria-selected="${o.isCur ? 'true' : 'false'}" style="display:flex;align-items:center;gap:10px;border:none;background:transparent;color:var(--ink);border-radius:3px;padding:8px 11px;font-size:13.5px;font-family:inherit;cursor:pointer;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(o.label)}<span style="flex:1;min-width:14px"></span>${ o.isCur ? '<span style="font-weight:600">✓</span>' : '' }</button>
                  `; }).join('') }
                </div></div>
                ` : '' }
              </div>
            </div>
            ` : '' }
          </div>

          <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
            <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);flex:0 0 68px">Bilder</span>
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              ${ v.exUnderlagBusy ? `
              <span style="display:inline-flex;align-items:center;gap:8px;font-size:13px;color:var(--ink-2)"><span style="width:13px;height:13px;border-radius:50%;border:2px solid var(--line-2);border-top-color:var(--accent);animation:spin .7s linear infinite"></span>Läser och tolkar bilderna …</span>
              ` : v.exUnderlag ? `
              ${ v.exUnderlag.filer.map(function(f){ return `<span title="${esc(f.beskrivning || f.namn)}" style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);border-radius:3px;padding:4px 10px;max-width:220px"><span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(f.namn)}</span></span>`; }).join('') }
              <button data-click="${on(v.onClearExUnderlag)}" aria-label="Ta bort bilderna" title="Ta bort bilderna" style="border:none;background:transparent;color:var(--ink-3);cursor:pointer;font-size:12px;padding:2px 6px;font-family:inherit">✕</button>
              <button data-click="${on(v.onPickExUnderlag)}" style="border:none;background:transparent;color:var(--ink-2);cursor:pointer;font-size:12.5px;font-family:inherit;padding:2px 4px;text-decoration:underline;text-underline-offset:3px">Byt</button>
              ` : `
              <button data-click="${on(v.onPickExUnderlag)}" title="Ladda upp bilder som byggs in i provuppgifterna — varje bild får en egen uppgift; behandlas lokalt" style="display:inline-flex;align-items:center;gap:7px;border:1px dashed var(--line-2);background:transparent;color:var(--ink-2);border-radius:3px;padding:6px 12px;font-size:12.5px;font-family:inherit;cursor:pointer">＋ Bilder till uppgifter (PNG, JPG, PDF)</button>
              ` }
            </div>
          </div>

          <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding-top:13px;border-top:1px solid color-mix(in srgb,var(--line) 60%,transparent)">
            ${ v.exCanStart || v.exRunning ? '' : `<span style="font-size:13px;color:var(--ink-3)">Välj kurs ovan så kan ${v.exTyp === 'arbetsblad' ? 'arbetsbladet' : 'provet'} skrivas.</span>` }
            <span style="flex:1"></span>
            <button data-click="${on(v.onExStart)}" ${v.exCanStart ? '' : 'disabled'} style="display:inline-flex;align-items:center;gap:7px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:4px;padding:13px 22px;font-size:14.5px;font-weight:500;font-family:inherit;cursor:${v.exCanStart ? 'pointer' : 'default'};opacity:${v.exCanStart ? '1' : '.55'}">${v.exRunning ? 'Skriver …' : (v.exTyp === 'arbetsblad' ? 'Skriv arbetsbladet' : 'Skriv provet')}</button>
          </div>
        </div>

        ${ (v.exRunning || v.exUnderlagBusy) && v.exHasLog ? `
          <div role="status" style="display:flex;flex-direction:column;gap:3px;margin-bottom:12px;font-size:13px;color:var(--ink-2)">
            ${ v.exLog.map(function(l){ return `<span>${esc(l)}</span>`; }).join('') }
          </div>
        ` : '' }

        ${ v.exErrCount ? `
          <div role="status" style="display:flex;flex-direction:column;gap:4px;margin-bottom:12px;font-size:13px;color:var(--warn)">
            <span style="font-weight:600">${esc(v.exErrCount)} problem kvarstår:</span>
            ${ v.exErrors.map(function(e2){ return `<span style="font-family:var(--mono,monospace);font-size:12px;color:var(--ink-2)">${esc(typeof e2 === 'string' ? e2 : (e2.path ? e2.path + ': ' : '') + (e2.message || ''))}</span>`; }).join('') }
          </div>
        ` : '' }

        ${ v.exam ? `
          <div data-key="exam-card" style="background:var(--surface);border:1px solid var(--line);border-radius:5px;padding:16px 18px;animation:fadeup .34s cubic-bezier(.16,1,.3,1) both">
            <div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:6px">
              <span style="font-size:16px;font-weight:600;color:var(--ink)">${esc(v.exam.titel)}</span>
              <span style="font-family:var(--mono);font-size:10.5px;letter-spacing:0.07em;text-transform:uppercase;color:var(--ink-3)">${esc(v.exam.typ)}</span>
              <span style="font-family:var(--mono);font-size:10.5px;letter-spacing:0.07em;text-transform:uppercase;color:${v.exam.godkant ? 'var(--ok)' : 'var(--ink-3)'}">${esc(v.exam.status)}</span>
              <span style="font-size:12.5px;color:var(--ink-3)">${esc(v.exam.versionRad)}</span>
              <span style="flex:1"></span>
              <button data-click="${on(v.onExClose)}" aria-label="Stäng ${v.exam.typ === 'arbetsblad' ? 'arbetsbladet' : 'provet'}" title="Stäng — tillbaka till inställningarna" style="align-self:center;border:none;background:transparent;color:var(--ink-3);cursor:pointer;font-size:14px;line-height:1;padding:5px 8px;border-radius:3px;font-family:inherit">✕</button>
            </div>
            <div style="font-size:13.5px;color:var(--ink-2);font-variant-numeric:tabular-nums">${esc(v.exam.balansRad)}</div>
            <div style="font-size:13px;color:var(--ink-3);font-variant-numeric:tabular-nums;margin-bottom:6px">${esc(v.exam.granserRad)}</div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px">
              ${ v.exam.formagor.map(function(f2){ return `<span data-key="fm-${esc(f2.f)}" style="font-family:var(--mono);font-size:11px;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);border-radius:3px;padding:2px 8px">${esc(f2.f)} ${esc(f2.p)} p</span>`; }).join('') }
            </div>
            ${ v.exDubbletter.length ? `
              <div role="status" style="display:flex;flex-direction:column;gap:4px;margin-bottom:14px;font-size:13px;color:var(--warn)">
                <span style="font-weight:600">${esc(v.exDubbletter.length)} uppgift${v.exDubbletter.length === 1 ? '' : 'er'} liknar tidigare prov:</span>
                ${ v.exDubbletter.map(function(d2){ return `<span style="font-family:var(--mono,monospace);font-size:12px;color:var(--ink-2)">"${esc(d2.text)}" ≈ ${esc(d2.mot_titel)} (${esc(Math.round(d2.likhet * 100))} % likhet)</span>`; }).join('') }
              </div>
            ` : '' }

            ${ v.exam.uppgifter.map(function(u2){ return `
              <div data-key="ex-u-${esc(u2.nummer)}" style="border-top:1px solid color-mix(in srgb,var(--line) 60%,transparent);padding:11px 0">
                <div style="display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;margin-bottom:4px">
                  <span style="font-weight:600;font-size:14px;color:var(--ink)">Uppgift ${esc(u2.nummer)}</span>
                  ${ u2.del ? `<span style="font-family:var(--mono);font-size:10.5px;color:var(--ink-3)">DEL ${esc(u2.del)}</span>` : '' }
                  <span style="font-family:var(--mono);font-size:10.5px;color:var(--ink-3)">${esc(u2.formaga)} · ${esc(u2.typ)}</span>
                  <span style="font-family:var(--mono);font-size:11.5px;color:var(--ink-2)">(${esc(u2.poangStr)})</span>
                </div>
                <div data-math="" style="font-size:14px;color:var(--ink);line-height:1.5;margin-bottom:7px">${esc(u2.text)}</div>
                <div style="display:flex;gap:8px">
                  <input value="${esc(u2.chatValue)}" data-input="${on(u2.onChat)}" aria-label="Ändra uppgift ${esc(u2.nummer)}" placeholder="Ändra uppgiften — t.ex. gör den svårare, byt kontext …" style="flex:1;min-width:0;background:var(--sunken);border:1px solid var(--line);border-radius:4px;padding:7px 11px;font-size:13px;font-family:inherit;color:var(--ink)">
                  <button data-click="${on(u2.onSend)}" ${u2.canSend ? '' : 'disabled'} style="border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:4px;padding:7px 13px;font-size:13px;font-weight:500;font-family:inherit;cursor:${u2.canSend ? 'pointer' : 'default'};opacity:${u2.canSend ? '1' : '.55'}">Ändra</button>
                </div>
              </div>
            `; }).join('') }

            <div style="display:flex;align-items:center;gap:10px;margin-top:14px;flex-wrap:wrap">
              <button data-click="${on(v.onExApprove)}" ${!v.exRunning ? '' : 'disabled'} style="display:inline-flex;align-items:center;gap:7px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:4px;padding:10px 17px;font-size:14.5px;font-weight:500;font-family:inherit;cursor:${!v.exRunning ? 'pointer' : 'default'};opacity:${!v.exRunning ? '1' : '.55'}">${v.exam.godkant ? 'Skapa PDF igen' : 'Godkänn & skapa PDF'}</button>
              ${ v.exam.hasPdf ? `<button data-click="${on(v.onExPdf)}" style="border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:4px;padding:10px 15px;font-size:14px;font-weight:500;font-family:inherit;cursor:pointer">Öppna PDF</button>` : '' }
              ${ v.exam.hasTex ? `<button data-click="${on(v.onExTex)}" style="border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:4px;padding:10px 15px;font-size:14px;font-weight:500;font-family:inherit;cursor:pointer">.tex</button>` : '' }
              ${ v.exam.hasTex ? `<button data-click="${on(v.onExOverleaf)}" title="Tillval: öppnar källan i Overleaf (molntjänst) för manuell finputs — prov innehåller ingen elevdata" style="border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:4px;padding:10px 15px;font-size:14px;font-weight:500;font-family:inherit;cursor:pointer">Öppna i Overleaf</button>` : '' }
              ${ v.exMsg ? `<span role="status" style="font-size:13.5px;color:var(--ink-2);word-break:break-all">${esc(v.exMsg)}</span>` : '' }
              <span style="flex:1"></span>
              ${ v.exDeleteArm ? `
              <span style="display:inline-flex;align-items:center;gap:8px;animation:fadeup .22s cubic-bezier(.16,1,.3,1) both">
                <span style="font-size:13px;color:var(--bad)">Raderas permanent, även filerna.</span>
                <button data-click="${on(v.onExDelete)}" aria-label="Ta bort ${v.exam.typ === 'arbetsblad' ? 'arbetsbladet' : 'provet'} permanent" style="border:1px solid var(--bad);background:transparent;color:var(--bad);border-radius:4px;padding:9px 14px;font-size:13.5px;font-weight:500;font-family:inherit;cursor:pointer">Ja, radera</button>
                <button data-click="${on(v.onExDeleteCancel)}" style="border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:4px;padding:9px 14px;font-size:13.5px;font-weight:500;font-family:inherit;cursor:pointer">Avbryt</button>
              </span>
              ` : `
              <button data-click="${on(v.onExDeleteArm)}" aria-label="Ta bort ${v.exam.typ === 'arbetsblad' ? 'arbetsbladet' : 'provet'}" title="Raderar ${v.exam.typ === 'arbetsblad' ? 'arbetsbladet' : 'provet'} och dess filer permanent" style="border:none;background:transparent;color:var(--ink-3);border-radius:4px;padding:9px 12px;font-size:13.5px;font-weight:500;font-family:inherit;cursor:pointer">Radera</button>
              ` }
            </div>
          </div>
        ` : '' }

      </div>
    </section>
`; }

  // <<<VIEWS_END>>>

  function view(v) {
    return viewHeader(v) +
      '<main style="max-width:1120px;margin:0 auto;padding:0 24px">' +
      (v.tabTranscribe ? viewTranscribe(v) : '') +
      (v.tabRecordings ? viewRecordings(v) : '') +
      (v.tabPlanning ? viewPlanning(v) : '') +
      '</main>' +
      viewModals(v);
  }

  /* ------------------------------------------------------------------ init -- */
  function init() {
    var root = document.getElementById('root');
    bindEvents(root);
    // Tavel-iframen rapporterar sin skalade höjd (board.js postMessage) så
    // ramen kan följa innehållet. Endast meddelanden från vårt eget origin.
    window.addEventListener('message', function (e) {
      if (e.origin !== window.location.origin) return;
      if (e.data && e.data.type === 'wb-height' && _wbFrame) {
        _wbFrame.style.height = (+e.data.px || 420) + 'px';
      }
    });
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('pointerdown', onAnyPress, true);
    syncTheme();
    _prevTab = S.tab; _prevStep = S.step;
    render();
    loadModels().then(loadSettings);   // real catalog, then reflect chosen models disk
    loadHistory();  // load persisted transcription history
    loadAudioModel();  // audio-correction model install status
    loadIncompleteRecs();  // offer to recover a recording that never finished (crash)
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();

  /* Exponera state för e2e-tester (endast med ?e2e=1 i URL:en; aldrig i normal drift). */
  if (/[?&]e2e=1(&|$)/.test(location.search)) { window.S = S; }

})();
