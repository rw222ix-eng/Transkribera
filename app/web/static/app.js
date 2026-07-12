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
    pp: 'idle',
    ppOp: 'clean',
    ppModel: 'Qwen3 14B (Q8_0)',   // fast intern LLM för korrektur + chatt
    ppOut: '',
    ppPct: 0,
    ppEnabled: false,
    chat: [],
    chatInput: '',
    chatTyping: false,
    chatThink: false,           // Qwen3 "tänk djupare" — bara i chatten, default av
    chatAttach: [],
    chatCiteSel: null,          // valt citat i chatten: "<msgIdx>:<segIdx>" eller null
    // Per-lektion chattmodal (Chatta-knapp på inspelnings-kortet) — egen isolerad chatt
    lessonChatId: null,         // öppen lektions history-id (även "overlay öppen"-flagga)
    lessonChatName: '',
    lessonChatSegs: [],         // lektionens transkript-segment ({time,text})
    lessonChat: [],
    lessonChatInput: '',
    lessonChatTyping: false,
    lessonChatCiteSel: null,
    lessonChatThink: false,
    lessonChatMeta: null,       // overlay-huvudets metadata: {lessonId,date,dur,model,lang,group,course,cc}
    lessonChatHitT: null,       // tidsstämpel (mm:ss) att markera i overlay-transkriptet
    lessonChatEvent: null,      // kalenderförslag: {title,when,desc,added,busy,aiMsgs,aiInput,aiBusy}
    evPick: null,               // öppen dag/tid-väljare i kalenderförslaget
    calConnected: null,         // Google Kalender-status: null = okänd, annars bool
    calClientReady: null,       // finns en OAuth-klient (inbyggd/installerad)?
    calHint: '',                // senaste hjälptext från /api/calendar/status
    calSetupOpen: false,        // guidat "Koppla Google Kalender"-fönster
    calBusy: false,             // installation/inloggning pågår
    ovAnalyzing: false,         // Analysera lektion pågår (overlayens header)
    ovReportBusy: false,        // Rapport-export pågår (overlayens header)
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
    cleanText: null,            // senaste korrekturlästa transkriptet (behålls även om annan pp körs)
    cleanModalOpen: false,      // KORREKTURLÄST-modalen med markerade rättelser
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
    askScanIdx: 0,             // kartotekets skannings-koreografi (kosmetisk position)
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
  };

  /* instance (non-state) fields */
  var _t, _pp, _ppIv, _chat, _au, _toastIv, _toastT2, _glideRAF, _progRAF, _disp, _lastStart, _runToken = 0;
  var _fltTimer = null, _scanTimer = null, _askRun = 0;
  var _dl = {}, _inst = {}, _editBuf = {}, _wave = null;
  var _file, _seek, _searchRef, _scrollRef, _procScroll, _imgInput, _media, _clientFile;
  var _rec = null, _recChunks = [], _recStream = null, _recTimer = null;
  var _recMarkers = [], _recMarkersByPath = {};   // live-markörer under inspelning
  var _recSession = null, _recUploadChain = null; // inkrementell flush till disk
  var _recAudioCtx = null, _recAnalyser = null, _recLevelTimer = null, _recSilenceSecs = 0;
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
    clearInterval(_t); clearTimeout(_pp); clearInterval(_ppIv); clearTimeout(_chat); clearInterval(_au);
    Object.values(_dl || {}).forEach(clearInterval);
    setState({ source: '', queue: [], qStatus: {}, qProgress: {}, activeId: null, fileError: '', step: 'source', run: 'idle', progress: 0, elapsed: 0, log: [], pp: 'idle', ppOp: 'summary', ppOut: '', ppEnabled: false, chat: [], chatInput: '', chatTyping: false, chatThink: false, chatAttach: [], openDD: null, transcriptOpen: false, runError: null, editing: false, edits: {}, edited: false, audioPlaying: false, audioT: 0, audioDur: 0, mediaUrl: null, runMedia: null, histViewing: null, resultId: null, transcriptRaw: null, logExpand: false, cleanText: null, cleanModalOpen: false, chatCiteSel: null });
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
  function pickOp(o) { setState({ ppOp: o, pp: 'idle', ppOut: '' }); }
  // Qwen3 "thinking": off by default (fast, no English chain-of-thought leak); on only
  // for hard multi-step chat questions. Correction/summary never think.
  function toggleChatThink() { setState(function (s) { return { chatThink: !s.chatThink }; }); }
  function selectChatCite(mi, segIdx) {
    var key = mi + ':' + segIdx;
    setState(function (s) { return { chatCiteSel: s.chatCiteSel === key ? null : key }; });
  }
  // Bygger renderbara chatt-meddelanden (bubblor + källförankrade citat/källpanel).
  // Delas av resultatvyns "Fråga om lektionen" och per-lektion-chattmodalen.
  function buildChatMessages(messages, segs, citeSel, onCite) {
    return messages.map(function (m, mi) {
      var cited = (m.role !== 'user' && m.text) ? parseChatCites(m.text, segs) : null;
      return {
        text: m.text, isUser: m.role === 'user', hasAttach: !!m.attach, attach: m.attach || '',
        reason: m.reason || '', hasReason: !!(m.reason && m.reason.length),
        rowStyle: 'display:flex;flex-direction:column;gap:5px;align-items:' + (m.role === 'user' ? 'flex-end' : 'flex-start'),
        bubbleStyle: m.role === 'user' ? 'max-width:82%;background:var(--btn-bg);color:var(--btn-fg);border-radius:15px 15px 4px 15px;padding:11px 15px;font-size:15.5px;line-height:1.5' : 'max-width:82%;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:15px 15px 15px 4px;padding:11px 15px;font-size:15.5px;line-height:1.5',
        attachStyle: 'display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);border-radius:8px;padding:4px 9px;font-variant-numeric:tabular-nums',
        reasonStyle: 'max-width:82%;background:var(--sunken);border:1px dashed var(--line-2);color:var(--ink-2);border-radius:13px;padding:9px 13px;font-size:13px;line-height:1.5;white-space:pre-wrap',
        hasCites: !!cited,
        tokens: cited ? cited.tokens.map(function (tk) {
          if (tk.cite === undefined) return { isText: true, text: tk.text };
          return { isCite: true, num: tk.cite, supFlag: citeSel === (mi + ':' + tk.segIdx) ? 'on' : 'off', onCite: function () { onCite(mi, tk.segIdx); } };
        }) : [],
        sources: cited ? cited.refs.map(function (r) {
          return { num: r.num, time: r.time, text: r.text, rowFlag: citeSel === (mi + ':' + r.segIdx) ? 'on' : 'off', onPick: function () { onCite(mi, r.segIdx); } };
        }) : [],
      };
    });
  }
  // Parsar [n]-markörer i ett assistentsvar till klickbara citat. Numren pekar på
  // segmenten som skickades till modellen (1-baserat); visningsnumren räknas om
  // per meddelande i citeringsordning. Ogiltiga nummer lämnas kvar som text.
  function parseChatCites(text, segs) {
    var tokens = [], refs = [], seen = {};
    var re = /\[(\d{1,3})\]/g, last = 0, m;
    while ((m = re.exec(text))) {
      var n = parseInt(m[1], 10);
      if (!(n >= 1 && n <= segs.length)) continue;
      var before = text.slice(last, m.index);
      if (before) tokens.push({ text: before });
      var segIdx = n - 1;
      if (!(segIdx in seen)) {
        seen[segIdx] = refs.length + 1;
        refs.push({ num: refs.length + 1, segIdx: segIdx, time: segs[segIdx].time || '', text: segs[segIdx].text || '' });
      }
      tokens.push({ cite: seen[segIdx], segIdx: segIdx });
      last = m.index + m[0].length;
    }
    if (!refs.length) return null;
    var rest = text.slice(last);
    if (rest) tokens.push({ text: rest });
    return { tokens: tokens, refs: refs };
  }
  function stopProp(e) { e.stopPropagation(); }
  // Chatten bor inline i Fråga om lektionen-kortet — följ med till slutankaret
  // när ett nytt meddelande läggs till.
  function scrollChatBottom() { requestAnimationFrame(function () { var el = document.querySelector('[data-follow="chatend"]'); if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'end' }); }); }
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
    setState({ lessonSearch: '', searchHits: null, askAnswer: '', askSources: null, askQ: '', asking: false, askScanIdx: 0 });
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
  function runAsk(q) {
    var run = ++_askRun;
    // Kartotekets skanningskoreografi: kosmetisk läsposition som tickar fram
    // medan det riktiga RAG-svaret hämtas — korten markeras Läser/Läst/Träff.
    if (_scanTimer) clearInterval(_scanTimer);
    _scanTimer = setInterval(function () {
      setState(function (s) { return s.asking ? { askScanIdx: s.askScanIdx + 1 } : null; });
    }, 340);
    setState({ asking: true, askAnswer: '', askSources: null, searchHits: null, askQ: q, askScanIdx: 0 });
    streamPost('/api/search/ask', { q: q }, function (ev) {
      if (run !== _askRun) return;               // en nyare fråga (eller Esc) har tagit över
      if (ev.type === 'token') {
        setState(function (s) { return { askAnswer: s.askAnswer + ev.text }; });
      } else if (ev.type === 'done') {
        if (_scanTimer) { clearInterval(_scanTimer); _scanTimer = null; }
        setState({ asking: false, askScanIdx: 999, askSources: (ev.result && ev.result.sources) || [] });
      } else if (ev.type === 'error') {
        if (_scanTimer) { clearInterval(_scanTimer); _scanTimer = null; }
        setState({ asking: false, askScanIdx: 999, askAnswer: 'Kunde inte söka: ' + (ev.message || 'okänt fel') });
      }
    });
  }
  function openSearchHit(hit) { openLesson({ id: hit.lesson_id, history_id: hit.history_id }); }

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
    // Korrekturen (auto efter förra körningen) håller GPU-låset — startar vi nu
    // avvisar arbitern jobbet med 409 och körningen felar direkt. Vänta tills den
    // är klar; knappen är blockerad under tiden (startReady/startBtnLabel nedan).
    if (S.pp === 'running') return;
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
    clearInterval(_t); clearInterval(_ppIv);   // stoppa ev. korrektur-progress från förra körningen
    var active = S.queue.find(function (q) { return q.id === S.activeId; });
    if (!active) return;
    var token = ++_runToken;
    var src = baseNameOf(active.name);
    setState({
      run: 'running', step: 'process', progress: 0, dispProgress: 0, elapsed: 0, pp: 'idle', ppOp: 'clean', ppOut: '', cleanText: null,
      chat: [], chatTyping: false, runError: null, transcript: null, resultFilesReal: null,
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
    _runToken++; clearInterval(_t);
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
  var PHASE_HI = [12, 28, 92, 100];        // övre gräns per steg (Förbereder…Färdigställer)
  function _progFrame() {
    _progRAF = 0;
    var run = S.run;
    if (run !== 'running' && run !== 'done') return;           // avbruten/fel/idle → stoppa
    var real = Math.max(0, Math.min(100, S.progress || 0));
    if (run === 'done') {
      _disp += (100 - _disp) * 0.16;                            // glid sista biten upp till 100
      if (_disp > 99.8) _disp = 100;
    } else {
      var ph = real < 12 ? 0 : real < 28 ? 1 : real < 92 ? 2 : 3;
      var ceil = PHASE_HI[ph] - 0.5;                            // stanna inom aktuellt steg
      if (real > _disp) _disp += (Math.min(real, 99) - _disp) * 0.12;   // hinn ikapp servern
      else if (_disp < ceil) _disp += (ceil - _disp) * 0.012;           // långsam framåtläckage
      if (_disp > 99) _disp = 99;
    }
    if (Math.round(_disp) !== Math.round(S.dispProgress || 0)) setState({ dispProgress: _disp });
    if (run === 'running' || (run === 'done' && _disp < 100)) _progRAF = requestAnimationFrame(_progFrame);
    else if (run === 'done' && S.dispProgress !== 100) setState({ dispProgress: 100 });
  }
  function _startProgress() { _disp = S.dispProgress || 0; if (!_progRAF) _progRAF = requestAnimationFrame(_progFrame); }

  // BACKEND: real LLM post-process via /api/postprocess SSE token stream (Ollama).
  function runPP() {
    if (S.pp === 'running') return;
    clearTimeout(_pp); clearInterval(_ppIv);
    // Korrektur-strömmen hör till den AKTUELLA körningen. Startar en ny körning
    // (som ökar _runToken) medan denna strömmar, ignoreras den gamla strömmens
    // events — annars skrevs förra inspelningens ppOut/cleanText in i den nya
    // körningens state. _runActive rensar dessutom _ppIv-intervallet.
    var token = _runToken;
    setState({ pp: 'running', ppPct: 0, ppOut: '' });
    _ppIv = setInterval(function () { setState(function (s) { return { ppPct: Math.min(95, (s.ppPct || 0) + (3 + Math.random() * 5)) }; }); }, 200);
    var op = 'cleanup';
    var text = getTranscript().map(function (l) { return l.text; }).join(' ');
    var acc = '';
    streamPost('/api/postprocess', { operation: op, transcript: text, model: S.ppModel }, function (ev) {
      if (token !== _runToken) return;   // en ny körning har startat — släpp den gamla strömmen
      if (ev.type === 'token') { acc += ev.text; setState({ ppOut: acc }); }
      else if (ev.type === 'error') { clearInterval(_ppIv); setState({ pp: 'done', ppPct: 100, ppOut: acc || ('Fel: ' + (ev.message || 'okänt')) }); }
      else if (ev.type === 'done') {
        clearInterval(_ppIv); var r = ev.result || {}; var out = r.text || acc;
        setState({ pp: 'done', ppPct: 100, ppOut: out });
        // Korrekturläst text behålls separat — chatten arbetar vidare på den
        // och kortet kan visa rättelserna även om en annan pp körs efteråt.
        if (out && S.ppOp === 'clean') setState({ cleanText: out });
      }
    });
  }
  function runCleanNow() { if (S.pp === 'running') return; setState({ ppOp: 'clean' }); runPP(); }
  function toggleLogExpand() { setState(function (s) { return { logExpand: !s.logExpand }; }); }
  function openCleanModal() { setState({ cleanModalOpen: true }); }
  function closeCleanModal() { setState({ cleanModalOpen: false }); }

  // Ord-diff original -> korrekturläst (design: markera rättelser i texten).
  // Greedy tvåpekar-jämförelse med resynk-fönster — klarar långa transkript
  // utan kvadratisk LCS. Ord vars normaliserade form finns kvar men vars
  // skiljetecken/skiftläge ändrats markeras också (språk & skiljetecken).
  function _normWord(w) { return w.toLowerCase().replace(/[.,!?;:"'»«…()\-–—]+/g, ''); }
  function diffWords(origText, cleanedText) {
    var A = (origText || '').split(/\s+/).filter(Boolean);
    var B = (cleanedText || '').split(/\s+/).filter(Boolean);
    var out = [], i = 0, j = 0, W = 14;
    while (j < B.length) {
      if (i < A.length && _normWord(A[i]) === _normWord(B[j])) {
        out.push({ s: B[j], ch: A[i] !== B[j] });
        i++; j++; continue;
      }
      // resynk: hitta närmaste matchning inom fönstret
      var bi = -1, bj = -1, best = W * 2 + 1;
      for (var dj = 0; dj <= W && j + dj < B.length; dj++) {
        for (var di = 0; di <= W && i + di < A.length; di++) {
          if (di + dj < best && _normWord(A[i + di]) === _normWord(B[j + dj])) { best = di + dj; bi = di; bj = dj; }
        }
      }
      if (bi < 0) { out.push({ s: B[j], ch: true }); j++; i++; continue; }
      for (var k = 0; k < bj; k++) { out.push({ s: B[j + k], ch: true }); }
      i += bi; j += bj;
    }
    return out;
  }
  var _diffMemo = { key: null, parts: null };
  function cleanDiffParts() {
    if (!S.cleanText) return [];
    var key = S.cleanText.length + ':' + S.cleanText.slice(0, 40);
    if (_diffMemo.key !== key) {
      var orig = getTranscript().map(function (l) { return l.text; }).join(' ');
      _diffMemo = { key: key, parts: diffWords(orig, S.cleanText) };
    }
    return _diffMemo.parts;
  }
  function togglePPEnabled() { var next = !S.ppEnabled; setState({ ppEnabled: next }); if (next && S.run === 'done' && S.ppOp !== 'chat') runPP(); }
  // Korrekturläsningen är inget val — den startar tyst och automatiskt så fort
  // transkriberingen är klar, sömlöst i bakgrunden (låser sedan upp chatten).
  function afterDone() { if (S.pp !== 'running') { setState({ ppOp: 'clean' }); runPP(); } }
  function onChatInput(e) { setState({ chatInput: e.target.value }); }
  function onChatKey(e) { if (e.key === 'Enter') sendChat(); }
  // BACKEND: real conversational chat via /api/chat (Ollama /api/chat) over the transcript.
  function sendChat() {
    // Blockera ny sändning medan ett svar strömmar — annars skrivs den pågående
    // assistent-turen över och en andra /api/chat-förfrågan skickas.
    if (S.chatTyping) return;
    var q = S.chatInput.trim();
    if (!q) return;
    // push the user turn + an empty assistant placeholder we stream into
    setState(function (s) { return { chat: s.chat.concat([{ role: 'user', text: q }, { role: 'assistant', text: '', reason: '' }]), chatInput: '', chatTyping: true, chatCiteSel: null }; });
    var msgs = S.chat.filter(function (m) { return !(m.role === 'assistant' && !m.text); })
      .map(function (m) { return { role: m.role, content: m.text }; });
    // Källförankrat läge: transkriptet skickas som numrerade, tidsstämplade
    // segment och modellen citerar med [n]-markörer som UI:t gör klickbara.
    var transcript = getTranscript().map(function (l, i) { return '[' + (i + 1) + '] (' + (l.time || '') + ') ' + l.text; }).join('\n');
    var acc = '', accReason = '';
    var setLast = function (text, reason, typing) { setState(function (s) { var c = s.chat.slice(); if (c.length) c[c.length - 1] = { role: 'assistant', text: text, reason: reason }; return { chat: c, chatTyping: !!typing }; }); };
    streamPost('/api/chat', { messages: msgs, transcript: transcript, model: S.ppModel, think: S.chatThink, cite: true }, function (ev) {
      if (ev.type === 'reasoning') { accReason += ev.text; setLast(acc, accReason, true); }
      else if (ev.type === 'token') { acc += ev.text; setLast(acc, accReason, false); }
      else if (ev.type === 'error') { setLast(acc || ('Fel: ' + (ev.message || 'okänt')), accReason, false); }
      else if (ev.type === 'done') { var r = ev.result || {}; setLast(r.text || acc, accReason, false); }
    });
  }

  // ---- Lektionsoverlay (fullskärm): transkript + samma källförankrade chatt
  // men mot EN lektions transkript, isolerat från resultatvyns chatt. ---------
  function openLessonChat(l, hitT) {
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
               lessonChatTyping: false, lessonChatCiteSel: null,
               lessonChatEvent: null, evPick: null,
               ovAnalyzing: false, ovReportBusy: false });
    getJSON('/api/history/' + encodeURIComponent(hid)).then(function (h) {
      var segs = ((h && h.transcript) || []).map(function (g) { return { time: fmtTime(g.start), text: g.text }; });
      setState({ lessonChatSegs: segs });
    }).catch(function () {});
  }
  function closeLessonChat() { setState({ lessonChatId: null, lessonChat: [], lessonChatInput: '', lessonChatCiteSel: null, lessonChatMeta: null, lessonChatHitT: null, lessonChatEvent: null, evPick: null }); }
  // Resultatvyn chattar inte inline längre. Den här knappen byter till fliken
  // Inspelningar och öppnar chatten för just den här inspelningen — precis som
  // att klicka sig in på inspelningen och trycka "Chatta" där.
  function chatAboutResult() {
    var hid = S.resultId;
    if (!hid) return;
    // Slå upp den riktiga lektionsposten (den bär lesson-id:t) så chatten får
    // med "Analysera lektion"/"Rapport" — annars saknades de fast lektionen fanns
    // i DB. Faller tillbaka på history-/filnamnsposten om listan inte är laddad.
    var lesson = (S.lessons || []).find(function (x) { return x.history_id === hid; });
    if (!lesson) {
      var h = (S.history || []).find(function (x) { return x.id === hid; });
      lesson = h
        ? { history_id: h.id, name: h.name, date: h.date || (h.ts || '').slice(0, 10),
            dur: h.dur, model: h.model, lang: h.lang, group: h.group || '', course: h.course || '' }
        : { history_id: hid, name: baseName() };
    }
    setTab('recordings');       // byt till Inspelningar (laddar om lektionslistan)
    openLessonChat(lesson);     // öppna lektionschatten för inspelningen
  }
  // Analysera lektion + Rapport bor i overlayens header sedan Insikter-panelen
  // togs bort med kartotek-omdesignen — extraktionen matar Kommande/Inför
  // nästa lektion/Terminstrender, rapporten öppnas i webbläsaren.
  function analyzeLesson() {
    var lid = (S.lessonChatMeta || {}).lessonId;
    if (!lid || S.ovAnalyzing) return;
    setState({ ovAnalyzing: true });
    streamPost('/api/lessons/' + encodeURIComponent(lid) + '/extract', {}, function (ev) {
      if (ev.type === 'done') {
        setState({ ovAnalyzing: false, toast: { title: 'Lektionen analyserad', name: 'Insikterna syns under Kommande och Terminstrender', done: true } });
        loadAgenda(); loadPrep(); loadTrends();
        clearTimeout(_toastT2); _toastT2 = setTimeout(function () { setState({ toast: null }); }, 3200);
      } else if (ev.type === 'error') {
        setState({ ovAnalyzing: false, toast: { title: 'Analys misslyckades', name: ev.message || '', done: false } });
        clearTimeout(_toastT2); _toastT2 = setTimeout(function () { setState({ toast: null }); }, 5200);
      }
    });
  }
  function exportLessonReport() {
    var lid = (S.lessonChatMeta || {}).lessonId;
    if (!lid || S.ovReportBusy) return;
    setState({ ovReportBusy: true });
    fetch('/api/lessons/' + encodeURIComponent(lid) + '/report?format=html')
      .then(function (r) { return r.json(); }).then(function (res) {
        setState({ ovReportBusy: false });
        if (res && res.path) { fetch('/api/open', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: res.path }) }).catch(function () {}); }
      }).catch(function () { setState({ ovReportBusy: false }); });
  }
  function onLessonChatInput(e) { setState({ lessonChatInput: e.target.value }); }
  function onLessonChatKey(e) { if (e.key === 'Enter') sendLessonChat(); }
  function toggleLessonChatThink() { setState(function (s) { return { lessonChatThink: !s.lessonChatThink }; }); }
  function selectLessonChatCite(mi, segIdx) {
    var key = mi + ':' + segIdx;
    setState(function (s) { return { lessonChatCiteSel: s.lessonChatCiteSel === key ? null : key }; });
  }
  function sendLessonChat(qArg) {
    if (S.lessonChatTyping) return;
    var q = (typeof qArg === 'string' && qArg ? qArg : S.lessonChatInput).trim();
    if (!q) return;
    // "Skapa läxpåminnelse …" o.dyl. föreslår en kalenderhändelse vid sidan av svaret.
    if (/påminn|kalender|prov|läx|förhör|inlämning/i.test(q) && !S.lessonChatEvent) proposeLessonEvent();
    setState(function (s) { return { lessonChat: s.lessonChat.concat([{ role: 'user', text: q }, { role: 'assistant', text: '', reason: '' }]), lessonChatInput: '', lessonChatTyping: true, lessonChatCiteSel: null }; });
    var msgs = S.lessonChat.filter(function (m) { return !(m.role === 'assistant' && !m.text); })
      .map(function (m) { return { role: m.role, content: m.text }; });
    var transcript = S.lessonChatSegs.map(function (l, i) { return '[' + (i + 1) + '] (' + (l.time || '') + ') ' + l.text; }).join('\n');
    var acc = '', accReason = '';
    var setLast = function (text, reason, typing) { setState(function (s) { var c = s.lessonChat.slice(); if (c.length) c[c.length - 1] = { role: 'assistant', text: text, reason: reason }; return { lessonChat: c, lessonChatTyping: !!typing }; }); };
    streamPost('/api/chat', { messages: msgs, transcript: transcript, model: S.ppModel, think: S.lessonChatThink, cite: true }, function (ev) {
      if (ev.type === 'reasoning') { accReason += ev.text; setLast(acc, accReason, true); }
      else if (ev.type === 'token') { acc += ev.text; setLast(acc, accReason, false); }
      else if (ev.type === 'error') { setLast(acc || ('Fel: ' + (ev.message || 'okänt')), accReason, false); }
      else if (ev.type === 'done') { var r = ev.result || {}; setLast(r.text || acc, accReason, false); }
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
      when: days[2].label + ' · 08:00',
      desc: 'Uppföljning av "' + (S.lessonChatName || 'lektionen') + '"' + (m.course ? ' i ' + m.course : '') + '. Läxförhör på begreppen från lektionen.',
      added: false, busy: false, aiMsgs: [], aiInput: '', aiBusy: false,
    }, evPick: null });
    if (S.calConnected === null) loadCalStatus();
  }
  function setLessonEvent(k, v) {
    setState(function (s) { return s.lessonChatEvent ? { lessonChatEvent: Object.assign({}, s.lessonChatEvent, kv(k, v)) } : null; });
  }
  function toggleEvPick() { setState(function (s) { return { evPick: s.evPick ? null : 'lesson' }; }); }
  function pickEvPart(part, val) {
    var ev = S.lessonChatEvent; if (!ev) return;
    var bits = (ev.when || ' · ').split(' · ');
    var when = (part === 'day' ? val : (bits[0] || '')) + ' · ' + (part === 'time' ? val : (bits[1] || '09:00'));
    setLessonEvent('when', when);
    if (part === 'time') setState({ evPick: null });
  }
  // "dag mån · HH:MM" -> ISO-start för API:t (dagens etikett slås upp mot evDays()).
  function _evWhenToStart(when) {
    var bits = (when || '').split(' · ');
    var day = evDays().filter(function (d) { return d.label === bits[0]; })[0];
    var time = /^\d{2}:\d{2}$/.test(bits[1] || '') ? bits[1] : '08:00';
    return (day ? day.iso : new Date().toISOString().slice(0, 10)) + 'T' + time + ':00';
  }
  function addLessonEvent() {
    var ev = S.lessonChatEvent; if (!ev || ev.busy || ev.added) return;
    setLessonEvent('busy', true);
    fetch('/api/calendar/event', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: ev.title, start: _evWhenToStart(ev.when), description: ev.desc || '' })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); }).then(function (res) {
      if (res.ok) { setState(function (s) { return s.lessonChatEvent ? { lessonChatEvent: Object.assign({}, s.lessonChatEvent, { busy: false, added: true }) } : null; }); }
      else {
        setLessonEvent('busy', false);
        var msg = (res.j && res.j.error) || 'kunde inte skapa händelsen';
        setState({ toast: { title: 'Google Kalender', detail: msg, kind: 'error', done: false } });
        clearTimeout(_toastT2); _toastT2 = setTimeout(function () { setState({ toast: null }); }, 9000);
      }
    }).catch(function () { setLessonEvent('busy', false); });
  }
  function onEvAiInput(e) { setLessonEvent('aiInput', e.target.value); }
  function onEvAiKey(e) { if (e.key === 'Enter') { e.preventDefault(); sendEvAi(); } }
  function sendEvAi(qArg) {
    var ev = S.lessonChatEvent; if (!ev || ev.aiBusy) return;
    var q = (typeof qArg === 'string' && qArg) || (ev.aiInput || '').trim();
    if (!q) return;
    setState(function (s) { return s.lessonChatEvent ? { lessonChatEvent: Object.assign({}, s.lessonChatEvent, { aiInput: '', aiBusy: true, aiMsgs: (s.lessonChatEvent.aiMsgs || []).concat([{ who: 'u', text: q }]) }) } : null; });
    setTimeout(function () {
      setState(function (s) {
        var cur = s.lessonChatEvent; if (!cur) return null;
        var r = applyEventCommand(cur, q);
        return { lessonChatEvent: Object.assign({}, cur, r.patch, { aiBusy: false, aiMsgs: (cur.aiMsgs || []).concat([{ who: 'a', text: r.reply }]) }) };
      });
    }, 350);
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
    // dag — veckodagar, idag/imorgon, nästa vecka
    var days = evDays();
    var W = [['måndag', 'mån'], ['tisdag', 'tis'], ['onsdag', 'ons'], ['torsdag', 'tors'], ['fredag', 'fre'], ['lördag', 'lör'], ['söndag', 'sön']];
    var nd = null;
    if (low.indexOf('imorgon') >= 0 || low.indexOf('i morgon') >= 0) nd = days[1];
    else if (low.indexOf('nästa vecka') >= 0) nd = days[7];
    else if (low.indexOf('idag') >= 0 || low.indexOf('i dag') >= 0) nd = days[0];
    else { for (var wi = 0; wi < W.length; wi++) { var w = W[wi]; if (low.indexOf(w[0]) >= 0 || new RegExp('(^|\\s)' + w[1] + '(\\s|$)').test(low)) { nd = days.slice(1).filter(function (d) { return d.label.indexOf(w[1] + ' ') === 0; })[0] || null; break; } } }
    if (nd) { day = nd.label; whenChanged = true; done.push('dagen till ' + nd.label); }
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
    if (S.editingLesson && e.key === 'Escape') { cancelEditLesson(); return; }
    if (S.lessonChatId && e.key === 'Escape') {
      if (S.evPick) { setState({ evPick: null }); return; }
      closeLessonChat(); return;
    }
    if (S.logOpen && e.key === 'Escape') { closeLog(); return; }
    if (S.cleanModalOpen && e.key === 'Escape') { closeCleanModal(); return; }
    if (S.filterOpen && e.key === 'Escape') { setState({ filterOpen: null, filterClosing: false }); return; }
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
    var cur = isDone ? STEPS.length : (prog < 12 ? 0 : prog < 28 ? 1 : prog < 92 ? 2 : 3);

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

    var PHASE_LO2 = [0, 12, 28, 92], PHASE_HI2 = [12, 28, 92, 100];
    var steps = STEPS.map(function (label, idx) {
      var done = idx < cur, active = idx === cur && !isDone;
      // Aktivt steg fylls proportionellt mot hur långt prog kommit i just det
      // steget → baren växer mjukt och kontinuerligt istället för att blinka helt.
      var frac = (done || isDone) ? 1 : active ? Math.max(0, Math.min(1, (prog - PHASE_LO2[idx]) / (PHASE_HI2[idx] - PHASE_LO2[idx]))) : 0;
      var pctW = (done || isDone) ? 100 : active ? Math.max(3, frac * 100) : 0;
      return {
        label: label, icon: done || isDone ? '✓' : (idx + 1),
        barTrackStyle: 'height:4px;border-radius:99px;background:var(--line);overflow:hidden',
        barFillStyle: 'height:100%;border-radius:99px;background:' + (done || isDone ? 'var(--ok)' : 'var(--accent)') + ';width:' + pctW.toFixed(1) + '%;transition:width .22s linear' + (active ? ';background-image:linear-gradient(90deg,var(--accent) 0,var(--accent) 55%,color-mix(in srgb,var(--accent) 35%,#fff) 78%,var(--accent));background-size:26px 100%;animation:flow .8s linear infinite' : ''),
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

    var OPS = [['clean', 'Korrekturläs', 'Rättar stavfel & småfel — skriver inte om'], ['chat', 'Chatta', 'Ställ frågor om innehållet']];
    var ppOps = OPS.map(function (p) { return { key: p[0], label: p[1], sub: p[2], onPick: function () { pickOp(p[0]); }, selected: st.ppOp === p[0], unselected: st.ppOp !== p[0] }; });
    var ppOpLabel = (ppOps.find(function (o) { return o.key === st.ppOp; }) || {}).label;
    var chatSegs = getTranscript();
    var chat = buildChatMessages(st.chat, chatSegs, st.chatCiteSel, selectChatCite);


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
    var askTerms = askActive ? (st.askQ || '').toLowerCase().split(/\s+/).filter(function (w) { return w.length >= 3; }) : [];
    function prelimHit(l) {
      var hay = ((l.name || '') + ' ' + (l.group || '') + ' ' + (l.course || '')).toLowerCase();
      return askTerms.some(function (w) { return hay.indexOf(w) >= 0; });
    }
    function lessonHit(l) { return askSourceIds ? !!askSourceIds[l.id] : prelimHit(l); }

    // Skannings-koreografin: kosmetisk läsposition över de synliga korten medan
    // det riktiga RAG-svaret hämtas; Läser/Läst/Träff drivs av askScanIdx.
    var scanList = st.lessons.slice(0, 8);
    var scanning = st.asking;
    var scanIdx = Math.min(st.askScanIdx, scanList.length);
    var scannedIds = {};
    scanList.slice(0, scanning ? scanIdx : scanList.length).forEach(function (l) { scannedIds[l.id] = true; });
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
        tagLabel: l.group ? (l.group + (l.course ? ' · ' + l.course : '')) : (l.course || 'Ej tilldelad'),
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
      onTabT: function () { setTab('transcribe'); }, onTabIn: function () { setTab('recordings'); },
      tabTOn: st.tab === 'transcribe', tabInOn: st.tab === 'recordings',
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
        scanning: scanning,
        afterScan: !scanning,
        total: scanList.length,
        ticker: scanList.length
          ? ('Läser: ' + ((scanList[Math.min(scanIdx, scanList.length - 1)] || {}).name || '…'))
          : 'Läser …',
        hitLabel: (function () {
          var n = scanning
            ? lessonItems.filter(function (it) { return it.isHit; }).length
            : (askSourceIds ? Object.keys(askSourceIds).length : 0);
          return n + (n === 1 ? (scanning ? ' träff hittills' : ' träff') : (scanning ? ' träffar hittills' : ' träffar'));
        })(),
        cards: scanList.map(function (l, i) {
          var hit = lessonHit(l);
          var stt, lbl;
          if (scanning && i === scanIdx) { stt = 'reading'; lbl = 'Läser …'; }
          else if (!scanning || i < scanIdx) { stt = hit ? 'hit' : 'read'; lbl = hit ? 'Träff ●' : 'Läst ✓'; }
          else { stt = 'queue'; lbl = 'I kö'; }
          return { key: l.id, st: stt, stLabel: lbl, title: l.name || '(namnlös)' };
        }),
        q: st.askQ,
        onNew: clearSearch,
        ansStarted: !!st.askAnswer,
        ansTyping: st.asking && !!st.askAnswer,
        ansDone: !st.asking && !!st.askAnswer,
        ansHeadLabel: (!st.asking && st.askAnswer)
          ? ('Svar — ' + (st.askSources || []).length + ((st.askSources || []).length === 1 ? ' källa' : ' källor'))
          : 'Svar — skrivs medan källorna läses',
        answer: st.askAnswer,
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
      fKlassLabel: (st.groups.find(function (g) { return String(g.id) === String(st.lessonFilterGroup); }) || {}).namn || 'Alla klasser',
      fKursLabel: (st.courses.find(function (c) { return String(c.id) === String(st.lessonFilterCourse); }) || {}).namn || 'Alla kurser',
      fDatumLabel: st.lessonFilterMonth
        ? (function () { var p = st.lessonFilterMonth.split('-'); return (_MON_SV[parseInt(p[1], 10) - 1] || p[1]) + ' ' + p[0]; })()
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
      onTogglePlay: togglePlay, onSeekClick: onSeekClick, seekTrackRef: seekTrackRef,
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
      acSwitchKnob: 'position:absolute;top:3px;left:3px;width:19px;height:19px;border-radius:50%;background:#fff;border:1px solid var(--line);box-shadow:0 1px 2px rgba(0,0,0,.2);transition:transform .15s;transform:translateX(' + (st.audioCorrect ? '17px' : '0') + ')',

      onStart: start, isRunning: isRunning, notRunning: !isRunning, startReady: st.catalogReady && st.pp !== 'running',
      startBtnLabel: !st.catalogReady ? 'Laddar modeller…' : (st.catalogReady && !st.model) ? 'Ladda ner en modell först' : st.pp === 'running' ? 'Väntar på korrekturen…' : isRunning ? 'Transkriberar…' : isDone ? 'Kör igen' : (st.queue.length > 1 ? 'Starta · ' + st.queue.length + ' filer' : 'Starta transkribering'),
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
      toastBarStyle: 'height:100%;width:' + (st.toast ? Math.round(st.toast.pct || 0) : 0) + '%;background:var(--accent);border-radius:99px;transition:width .14s linear',
      transcriptOpen: st.transcriptOpen, openTranscript: openTranscript, closeTranscript: closeTranscript, transcriptFile: baseName() + '.txt',
      searchQuery: st.searchQuery, onTSearch: onTSearch, onSearchKey: onSearchKey, searchRef: searchRef, scrollRef: scrollRef,
      nextMatch: nextMatch, prevMatch: prevMatch, matchLabel: matchLabel, tLines: tLines,

      showResults: isDone, resultCount: resultFiles.length, resultDuration: fmtTime(st.elapsed), resultFiles: resultFiles,
      transcript: getTranscript().slice(0, 3).map(function (ln, idx) { return { time: ln.time, text: lineText(idx) }; }),

      ppEnabled: st.ppEnabled, ppOff: !st.ppEnabled, togglePPEnabled: togglePPEnabled,
      ppSwitchTrack: 'position:relative;width:42px;height:25px;border-radius:999px;flex:0 0 auto;background:' + (st.ppEnabled ? 'var(--ink)' : 'var(--line-2)') + ';transition:background .15s',
      ppSwitchKnob: 'position:absolute;top:3px;left:3px;width:19px;height:19px;border-radius:50%;background:#fff;border:1px solid var(--line);box-shadow:0 1px 2px rgba(0,0,0,.2);transition:transform .15s;transform:translateX(' + (st.ppEnabled ? '17px' : '0') + ')',
      ppOps: ppOps, ppModel: st.ppModel,
      showPP: isDone, ppOpLabel: ppOpLabel, ppShowRun: st.ppOp !== 'chat', onRunPP: runPP, ppRunLabel: 'Kör',
      ppRunBtnStyle: primaryBtn(st.pp === 'running') + ';min-width:152px', ppRunIdle: st.pp !== 'running', ppPct: Math.round(st.ppPct || 0),
      ppRingStyle: 'position:relative;width:22px;height:22px;border-radius:50%;flex:0 0 auto;background:conic-gradient(var(--accent) ' + (Math.round(st.ppPct || 0) * 3.6) + 'deg, color-mix(in srgb,var(--ink-3) 18%,transparent) 0);animation:ppglow 1.6s ease-in-out infinite;transition:background .13s linear',
      ppShowText: st.ppOp !== 'chat' && st.pp !== 'idle', ppShowChat: st.ppOp === 'chat', ppRunning: st.pp === 'running', ppShowOut: st.pp === 'done',
      ppOut: st.ppOut,
      // KORREKTUR-kortet (design): körning, resultat med markerade rättelser, lås för chatten
      cleanRunning: st.pp === 'running' && st.ppOp === 'clean',
      cleanDone: !!st.cleanText,
      cleanFailed: st.pp === 'done' && !st.cleanText,          // körde men gav inget resultat
      cleanPending: st.pp === 'idle' && !st.cleanText,         // väntar på att auto-starta
      cleanBtnLabel: '↻ Kör igen',
      cleanPct: Math.round(st.ppPct || 0),
      cleanBarW: Math.round(st.ppPct || 0) + '%',
      cleanLegendAudio: !!st.audioCorrect,
      cleanPreviewParts: st.cleanText ? cleanDiffParts().slice(0, 70) : [],
      cleanFullParts: st.cleanText ? cleanDiffParts() : [],
      cleanChangeCount: st.cleanText ? cleanDiffParts().filter(function (p) { return p.ch; }).length : 0,
      runClean: runCleanNow,
      onChatInRecordings: chatAboutResult, resultReady: !!st.resultId,
      cleanModalOpen: st.cleanModalOpen, openCleanModal: openCleanModal, closeCleanModal: closeCleanModal,
      ppLocked: !st.cleanText, activeLlmShort: st.ppModel,
      logExpand: st.logExpand, toggleLogExpand: toggleLogExpand,
      logToggleLabel: st.logExpand ? 'Dölj' : 'Visa',
      chat: chat, chatTyping: st.chatTyping, chatInput: st.chatInput, onChatInput: onChatInput, onChatKey: onChatKey, onChatSend: sendChat,
      stop: stopProp, chatEmpty: st.chat.length === 0, chatHasMsgs: st.chat.length > 0,
      chatThink: st.chatThink, onToggleChatThink: toggleChatThink,
      chatThinkBtnStyle: 'display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:500;font-family:inherit;cursor:pointer;border-radius:99px;padding:6px 12px;border:1px solid ' + (st.chatThink ? 'color-mix(in srgb,var(--accent) 40%,transparent);background:var(--accent-weak);color:var(--accent)' : 'var(--line);background:var(--surface);color:var(--ink-2)'),
      chatThinkHint: st.chatThink ? 'Tänker djupare före svar — bättre på svåra flerstegsfrågor, men något långsammare.' : 'Snabbt svar utan synligt resonemang. Slå på för svåra flerstegsfrågor.',

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
      ovOpenFull: function () { openLesson({ history_id: st.lessonChatId }); },
      ovHasLesson: !!(st.lessonChatMeta && st.lessonChatMeta.lessonId),
      ovAnalyzing: st.ovAnalyzing, onAnalyze: analyzeLesson,
      ovReportBusy: st.ovReportBusy, onOvReport: exportLessonReport,
      ovAskSum: function () { sendLessonChat('Sammanfatta lektionen i tre punkter'); },
      ovAskStud: function () { sendLessonChat('Vilka elever nämns och varför?'); },
      ovAskRemind: function () { sendLessonChat('Skapa en läxpåminnelse utifrån lektionen'); },
      proposeOvEvent: proposeLessonEvent,
      ovEvent: st.lessonChatEvent ? (function () {
        var ev = st.lessonChatEvent;
        return {
          notAdded: !ev.added, added: ev.added, busy: ev.busy,
          title: ev.title, when: ev.when, desc: ev.desc || '',
          calKnown: st.calConnected !== null, calConnected: st.calConnected === true,
          onConnect: startCalConnect,
          setTitle: function (e) { setLessonEvent('title', e.target.value); },
          setDesc: function (e) { setLessonEvent('desc', e.target.value); },
          onAdd: addLessonEvent,
          pickOpen: st.evPick === 'lesson',
          onTogglePick: function (e) { if (e) e.stopPropagation(); toggleEvPick(); },
          dayOpts: evDays().map(function (d) {
            return { key: d.label, label: d.label, pre: d.pre, hasPre: !!d.pre,
                     curQ: (ev.when || '').indexOf(d.label) === 0 ? '1' : '',
                     onPick: function (e) { if (e) e.stopPropagation(); pickEvPart('day', d.label); } };
          }),
          timeOpts: EV_TIMES.map(function (t2) {
            return { key: t2, label: t2, curQ: (ev.when || '').slice(-5) === t2 ? '1' : '',
                     onPick: function (e) { if (e) e.stopPropagation(); pickEvPart('time', t2); } };
          }),
          aiMsgs: (ev.aiMsgs || []).map(function (m) { return { text: m.text, isUser: m.who === 'u', isAi: m.who === 'a' }; }),
          aiEmpty: !(ev.aiMsgs || []).length && !ev.aiBusy,
          aiBusy: ev.aiBusy, aiInput: ev.aiInput || '',
          onAiInput: onEvAiInput, onAiKey: onEvAiKey, onAiSend: function () { sendEvAi(); },
          aiChip1: function () { sendEvAi('Flytta till fredag 10:00'); },
          aiChip2: function () { sendEvAi('Lägg till läxan i anteckningen'); },
          aiChip3: function () { sendEvAi('Kortare titel'); },
        };
      })() : null,
      lessonChatThread: {
        chatEmpty: st.lessonChat.length === 0,
        chatHasMsgs: st.lessonChat.length > 0,
        chat: buildChatMessages(st.lessonChat, st.lessonChatSegs, st.lessonChatCiteSel, selectLessonChatCite),
        chatTyping: st.lessonChatTyping,
        chatInput: st.lessonChatInput,
        onChatInput: onLessonChatInput, onChatKey: onLessonChatKey, onChatSend: sendLessonChat,
        chatThink: st.lessonChatThink, onToggleChatThink: toggleLessonChatThink,
        chatThinkBtnStyle: 'display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:500;font-family:inherit;cursor:pointer;border-radius:99px;padding:6px 12px;border:1px solid ' + (st.lessonChatThink ? 'color-mix(in srgb,var(--accent) 40%,transparent);background:var(--accent-weak);color:var(--accent)' : 'var(--line);background:var(--surface);color:var(--ink-2)'),
        chatThinkHint: st.lessonChatThink ? 'Tänker djupare före svar — bättre på svåra flerstegsfrågor, men något långsammare.' : 'Snabbt svar utan synligt resonemang. Slå på för svåra flerstegsfrågor.',
        ppModel: st.ppModel, openTranscript: null,
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
        <div class="ehead">
          <div>
            <div class="eyebrow" style="margin-bottom:18px">Steg 1 — Källa</div>
            <h1 class="disp" style="font-size:clamp(34px,5.2vw,52px);margin:0">Vad vill du <span class="ser">transkribera?</span></h1>
          </div>
          <p class="ehead_lede">Dra in en eller flera filer, eller välj från datorn — allt körs på din egen dator.</p>
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
              <div style="flex:0 0 70px;height:6px;border-radius:99px;background:var(--track);overflow:hidden" title="Mikrofonnivå"><div style="height:100%;width:${v.recLevelPct}%;background:${ v.recSilent ? 'var(--bad)' : 'var(--ok)' };border-radius:99px;transition:width .12s"></div></div>
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
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M8 3v10M3 8h10"></path></svg>Lägg till fler
            </button>
          </div>
          <div style="display:flex;flex-direction:column">
            ${ v.queueItems.map(function(q){ return `
              <div data-key="${esc(q.id)}" style="display:flex;align-items:center;gap:12px;padding:13px 20px;border-bottom:1px solid var(--line);background:var(--surface)">
                <span style="font-family:var(--mono);font-size:10px;font-weight:500;letter-spacing:0.06em;color:var(--ink-2);background:var(--sunken);border:1px solid var(--line);border-radius:4px;padding:3px 7px;flex:0 0 auto">${esc(q.ext)}</span>
                <span style="flex:1;min-width:0;font-size:15.5px;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(q.name)}</span>
                <button data-click="${on(q.onRemove)}" aria-label="Ta bort från kön" style="width:30px;height:30px;flex:0 0 auto;border:1px solid var(--line);background:var(--surface);border-radius:8px;cursor:pointer;color:var(--ink-3);display:flex;align-items:center;justify-content:center;transition:border-color .14s,color .14s">
                  <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 3l8 8M11 3l-8 8"></path></svg>
                </button>
              </div>
            `; }).join('') }
          </div>
        </div>

        <div style="font-family:var(--mono);font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--ink-3);margin:2px 0 14px">Inställningar</div>

        <div style="background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:17px 19px;box-shadow:var(--shadow-sm)">
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

        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:12px;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px 16px;box-shadow:var(--shadow-sm)">
          <span style="font-size:14px;color:var(--ink-2);font-weight:500">Filformat</span>
          <div style="display:flex;gap:6px">
            ${ v.formatChips.map(function(f){ return `
              <button data-click="${on(f.onToggle)}" aria-pressed="${f.active}" data-chip="${f.active ? 'on' : 'off'}" style="border:1px solid var(--line);background:transparent;color:var(--ink-2);border-radius:9px;padding:8px 13px;font-size:14.5px;font-weight:500;cursor:pointer;font-family:inherit;transition:all .12s">${esc(f.label)}</button>
            `; }).join('') }
          </div>
        </div>

        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:12px;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px 14px;box-shadow:var(--shadow-sm)">
          <div data-click="${on(v.onToggleAudioCorrect)}" style="${v.acSwitchTrack}"><span style="${v.acSwitchKnob}"></span></div>
          <div style="flex:1;min-width:0">
            <div style="font-size:14.5px;font-weight:500;color:var(--ink)">Rätta mot ljudet <span style="font-size:12px;color:var(--ink-3)">· Gemma 4 (experimentell)</span></div>
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
            <div class="eyebrow" style="margin-bottom:18px">Steg 3 — Resultat</div>
            <h1 class="disp" style="font-size:clamp(30px,4.4vw,44px);margin:0">Ditt <span class="ser">transkript</span></h1>
          </div>
          <p class="ehead_lede">Bearbetas lokalt i steg. Korrekturläs, städa språket och ställ frågor — när du är klar.</p>
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
              <span style="${v.statusBadgeStyle}">${esc(v.statusBadge)}</span>
              <span style="font-size:15.5px;color:var(--ink-2);font-variant-numeric:tabular-nums;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.statusFile)}</span>
            </div>
            <div style="display:flex;align-items:baseline;gap:18px;flex:0 0 auto">
              <span style="display:inline-flex;align-items:baseline;gap:7px"><span class="win_lbl">Tid</span><span style="font-size:14.5px;color:var(--ink-2);font-variant-numeric:tabular-nums">${esc(v.elapsedLabel)}</span></span>
              <span style="display:inline-flex;align-items:baseline;gap:7px"><span class="win_lbl">Klart</span><span class="fig" style="font-size:21px;color:var(--ink);font-variant-numeric:tabular-nums">${esc(v.progressLabel)}</span></span>
              ${ v.isRunning ? `
                <button data-click="${on(v.onCancelRun)}" style="background:transparent;border:1px solid var(--line);color:var(--ink-2);border-radius:9px;padding:6px 13px;font-size:13.5px;font-weight:500;cursor:pointer;font-family:inherit;align-self:center">Avbryt</button>
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

        <div data-click="${on(v.toggleLogExpand)}" style="border-top:1px solid var(--line);background:var(--surface);cursor:pointer;border-radius:0 0 18px 18px;transition:background .12s" data-sh="background:var(--sunken) !important">
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
              <span style="font-variant-numeric:tabular-nums;font-size:12.5px;font-weight:500;color:var(--accent);background:var(--accent-weak);padding:5px 9px;border-radius:7px;letter-spacing:0.03em">${esc(r.type)}</span>
              <span style="flex:1;min-width:0;font-size:16px;font-variant-numeric:tabular-nums;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.name)}</span>
              <span style="font-size:14px;color:var(--ink-2);font-variant-numeric:tabular-nums">${esc(r.size)}</span>
              <button data-click="${on(r.onDownload)}" style="display:inline-flex;align-items:center;gap:8px;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:8px 14px 8px 12px;font-size:14.5px;font-weight:500;cursor:pointer;font-family:inherit;transition:background .14s,border-color .14s,color .14s" data-sh="border-color:var(--ink) !important;background:var(--ink) !important;color:var(--btn-fg) !important">
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2.5v7.5"></path><path d="M4.5 6.5 8 10l3.5-3.5"></path><path d="M3 13.5h10"></path></svg>Ladda ner
              </button>
            </div>
          `; }).join('') }
        </div>

        <div data-reveal data-click="${on(v.openTranscript)}" style="background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px 20px;box-shadow:var(--shadow-sm);cursor:pointer;transition:border-color .12s,box-shadow .12s" data-sh="border-color:var(--line-2) !important;box-shadow:var(--shadow) !important">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px">
            <span style="font-size:12.5px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink-2)">Förhandsvisning</span>
            <span style="display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:500;color:var(--accent)">Visa hela transkriptet<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3.5 10.5 8 6 12.5"></path></svg></span>
          </div>
          ${ v.transcript.map(function(t, idx){ return `
            <div data-key="${esc(idx)}" style="display:flex;gap:14px;padding:5px 0">
              <span style="font-variant-numeric:tabular-nums;font-size:13.5px;color:var(--ink-3);flex:0 0 auto;width:46px;padding-top:2px">${esc(t.time)}</span>
              <span style="font-size:16px;color:var(--ink);line-height:1.5">${esc(t.text)}</span>
            </div>
          `; }).join('') }
          <div style="margin-top:9px;font-size:13px;color:var(--ink-3)">… klicka för att läsa hela transkriptet</div>
        </div>
      </div>
      ` : '' }

      ${ v.showPP ? `
      <div data-sec="pp" data-follow="clean" data-reveal style="margin-top:28px;background:var(--surface);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);padding:22px 24px 20px">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
          <span style="font-family:var(--mono);font-size:10.5px;font-weight:500;letter-spacing:0.08em;color:var(--c-mustard);background:color-mix(in srgb,var(--c-mustard) 13%,transparent);border:1px solid color-mix(in srgb,var(--c-mustard) 30%,transparent);padding:3px 9px;border-radius:6px">KORREKTUR</span>
          <h2 style="font-size:19px;font-weight:600;letter-spacing:-0.02em;margin:0">Korrekturläs transkriptet</h2>
        </div>
        <p style="margin:0 0 18px;color:var(--ink-2);font-size:15px">Körs automatiskt direkt efter transkriberingen — rättar stavfel och småfel och städar språket (skiljetecken och meningslängd) med ${esc(v.activeLlmShort)}.</p>

        ${ v.cleanDone && !v.cleanRunning ? `
        <div data-click="${on(v.openCleanModal)}" style="background:var(--sunken);border:1px solid var(--line);border-radius:13px;padding:16px 18px;margin-bottom:14px;cursor:pointer;transition:border-color .14s,box-shadow .14s" data-sh="border-color:var(--line-2) !important;box-shadow:var(--shadow-sm) !important">
          <div style="display:flex;align-items:center;gap:14px;margin-bottom:12px;flex-wrap:wrap">
            <span style="font-size:11.5px;text-transform:uppercase;letter-spacing:0.05em;color:var(--accent);font-weight:600">Korrekturläst</span>
            ${ v.cleanLegendAudio ? `<span style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-2)"><span style="width:12px;height:12px;border-radius:4px;background:color-mix(in srgb,var(--ok) 20%,transparent);border:1px solid color-mix(in srgb,var(--ok) 45%,transparent)"></span>mot ljudet</span>` : '' }
            <span style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-2)"><span style="width:12px;height:12px;border-radius:4px;background:color-mix(in srgb,var(--accent) 16%,transparent);border:1px solid color-mix(in srgb,var(--accent) 45%,transparent)"></span>språk &amp; skiljetecken</span>
            <span style="margin-left:auto;display:inline-flex;align-items:center;gap:5px;font-size:13px;font-weight:500;color:var(--accent)">Visa hela<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3.5 10.5 8 6 12.5"></path></svg></span>
          </div>
          <div style="font-size:15px;color:var(--ink);line-height:1.65">
            ${ v.cleanPreviewParts.map(function(p){ return p.ch ? `<span style="background:color-mix(in srgb,var(--accent) 15%,transparent);color:var(--accent);border-radius:4px;padding:0 3px;font-weight:500">${esc(p.s)}</span>` : `<span>${esc(p.s)}</span>`; }).join(' ') } …
          </div>
          <div style="margin-top:9px;font-size:13px;color:var(--ink-3)">${esc(v.cleanChangeCount)} markerade rättelser · klicka för att öppna hela</div>
        </div>
        ` : '' }

        ${ v.cleanRunning ? `
        <div style="background:var(--sunken);border:1px solid var(--line);border-radius:13px;padding:15px 17px;margin-bottom:14px">
          <div style="display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:11px">
            <span style="display:inline-flex;align-items:center;gap:9px;font-size:14px;font-weight:600;color:var(--ink)"><span style="width:14px;height:14px;border-radius:50%;border:2px solid var(--line-2);border-top-color:var(--accent);animation:spin .7s linear infinite;flex:0 0 auto"></span>Korrekturläser …</span>
            <span style="color:var(--ink);letter-spacing:-0.01em"><span class="fig" style="font-size:30px;font-variant-numeric:tabular-nums">${esc(v.cleanPct)}</span><span class="fig-unit" style="font-size:16px;margin-left:1px">%</span></span>
          </div>
          <div style="height:9px;border-radius:99px;background:var(--track);overflow:hidden;margin-bottom:11px"><div style="height:100%;width:${v.cleanBarW};background:var(--accent);transition:width .2s"></div></div>
          <div style="display:flex;align-items:center;gap:8px;font-size:13px;color:var(--ink-2)"><span style="width:7px;height:7px;border-radius:50%;background:var(--accent);animation:pulse 1.2s ease-in-out infinite;flex:0 0 auto"></span>Städar språket …</div>
        </div>
        ` : '' }

        ${ !v.cleanRunning && v.cleanDone ? `
        <div style="display:flex;align-items:center;gap:13px;flex-wrap:wrap">
          <button data-click="${on(v.runClean)}" style="display:inline-flex;align-items:center;justify-content:center;gap:8px;background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:11px;padding:9px 16px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit;transition:border-color .15s,background .15s" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important">${esc(v.cleanBtnLabel)}</button>
          <span style="margin-left:auto;display:inline-flex;align-items:center;gap:8px;font-size:12.5px;color:var(--ink-3)"><span style="width:7px;height:7px;border-radius:50%;flex:0 0 auto;background:var(--ok)"></span>Lokalt med <strong style="color:var(--ink-2);font-weight:600">${esc(v.ppModel)}</strong></span>
        </div>
        ` : '' }

        ${ !v.cleanRunning && v.cleanFailed ? `
        <div style="display:flex;align-items:center;gap:13px;flex-wrap:wrap">
          <span style="display:inline-flex;align-items:center;gap:8px;font-size:14px;color:var(--ink-2)"><span style="width:20px;height:20px;border-radius:50%;flex:0 0 auto;background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px">!</span>Korrekturläsningen gick inte igenom.</span>
          <button data-click="${on(v.runClean)}" style="display:inline-flex;align-items:center;justify-content:center;gap:8px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:11px;padding:9px 18px;font-size:14px;font-weight:500;cursor:pointer;font-family:inherit;box-shadow:var(--shadow-sm);transition:background .15s">↻ Försök igen</button>
        </div>
        ` : '' }

        ${ !v.cleanRunning && v.cleanPending ? `
        <div style="display:flex;align-items:center;gap:13px;flex-wrap:wrap;font-size:14px;color:var(--ink-2)">
          <span style="display:inline-flex;align-items:center;gap:9px"><span style="width:14px;height:14px;border-radius:50%;border:2px solid var(--line-2);border-top-color:var(--accent);animation:spin .7s linear infinite;flex:0 0 auto"></span>Korrekturläsning startar automatiskt …</span>
          <span style="margin-left:auto;display:inline-flex;align-items:center;gap:8px;font-size:12.5px;color:var(--ink-3)"><span style="width:7px;height:7px;border-radius:50%;flex:0 0 auto;background:var(--ok)"></span>Lokalt med <strong style="color:var(--ink-2);font-weight:600">${esc(v.ppModel)}</strong></span>
        </div>
        ` : '' }
      </div>

      <div data-follow="llm" style="margin-top:16px;background:var(--surface);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);padding:22px 24px 20px">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
          <span style="font-family:var(--mono);font-size:10.5px;font-weight:500;letter-spacing:0.08em;color:var(--c-sky);background:color-mix(in srgb,var(--c-sky) 13%,transparent);border:1px solid color-mix(in srgb,var(--c-sky) 28%,transparent);padding:3px 9px;border-radius:6px">LLM</span>
          <h2 style="font-size:19px;font-weight:600;letter-spacing:-0.02em;margin:0">Fråga om lektionen</h2>
        </div>
        <p style="margin:0 0 18px;color:var(--ink-2);font-size:15px">Chatten bor bland dina inspelningar. Öppna den här inspelningen under <strong style="color:var(--ink);font-weight:600">Inspelningar</strong> så kan du ställa frågor om innehållet — svaren förankras i numrerade källor i transkriptet.</p>
        <button data-click="${on(v.onChatInRecordings)}" style="display:inline-flex;align-items:center;justify-content:center;gap:10px;width:100%;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:12px;padding:14px 22px;font-size:15px;font-weight:500;cursor:pointer;font-family:inherit;box-shadow:var(--shadow-sm);transition:background .15s" data-sh="background:color-mix(in srgb, var(--btn-bg) 82%, var(--accent)) !important">
          <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4.5h12a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H8l-4 3v-3H4a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1z"></path></svg>
          Chatta om inspelningen
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8h10"></path><path d="M8.5 3.5 13 8l-4.5 4.5"></path></svg>
        </button>
      </div>
      ` : '' }
        </div>
        <button data-click="${on(v.restart)}" style="margin-top:16px;flex:0 0 auto;align-self:center;display:inline-flex;align-items:center;justify-content:center;gap:8px;background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:11px;padding:11px 22px;font-size:15px;font-weight:500;cursor:pointer;font-family:inherit" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important">
          <span style="font-size:16px;line-height:1">↺</span>Ny transkribering — börja om
        </button>
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
  function filterDrop(label, selOn, isOpen, onToggle, anim, menuOpts){
    return `
        <div style="position:relative" data-enter="${on(v.fEnter)}" data-leave="${on(v.fLeave)}">
          <button data-click="${on(onToggle)}" data-filter-on="${esc(selOn)}" style="display:inline-flex;align-items:center;gap:9px;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:10px;padding:8px 13px;font-size:14px;font-family:inherit;cursor:pointer;white-space:nowrap;transition:border-color .14s">${esc(label)}<svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6l4 4 4-4"></path></svg></button>
          ${ isOpen ? `
            <div data-pop="${esc(anim)}" style="position:absolute;top:100%;left:0;z-index:30;padding-top:6px"><div style="min-width:172px;background:var(--surface);border:1px solid var(--line-2);border-radius:10px;box-shadow:var(--shadow);padding:5px;display:flex;flex-direction:column;gap:1px">
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
      <div style="max-width:960px;margin:22px auto 8px;animation:fadeup .3s ease both">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:11px">
          ${ v.askScan.scanning ? `
            <span class="insp-dots" style="color:var(--accent);flex:0 0 auto"><i></i><i></i><i></i></span>
            <span style="font-family:var(--mono);font-size:10.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(v.askScan.ticker)}</span>
          ` : `
            <span style="font-family:var(--mono);font-size:10.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ok);flex:0 0 auto">✓ Genomsökte ${esc(v.askScan.total)} inspelningar</span>
          ` }
          <div style="flex:1;height:1px;background:var(--line)"></div>
          <span style="font-family:var(--mono);font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--accent);flex:0 0 auto">${esc(v.askScan.hitLabel)}</span>
          <button data-click="${on(v.askScan.onNew)}" style="flex:0 0 auto;border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:7px;padding:5px 10px;font-family:var(--mono);font-size:10px;letter-spacing:0.08em;text-transform:uppercase;cursor:pointer">✕ Ny fråga</button>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(108px,1fr));gap:9px">
          ${ v.askScan.cards.map(function(sc){ return `
            <div data-key="scan-${esc(sc.key)}" data-scan="${esc(sc.st)}" style="min-width:0;border:1px solid var(--line);background:var(--surface);border-radius:9px;padding:9px 11px;transition:opacity .35s ease,box-shadow .35s ease,border-color .35s ease,background .35s ease">
              <span style="font-family:var(--mono);font-size:8.5px;letter-spacing:0.07em;text-transform:uppercase;color:var(--ink-3);display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(sc.stLabel)}</span>
              <div style="font-size:12px;font-weight:600;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(sc.title)}</div>
            </div>
          `; }).join('') }
        </div>
        ${ v.askScan.ansStarted ? `
        <div style="margin-top:14px;border:1px solid var(--line);border-radius:13px;background:var(--surface);padding:20px 24px;box-shadow:var(--shadow-sm);animation:fadeup .3s ease both">
          <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:12px">
            <span style="font-family:var(--mono);font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);flex:0 0 auto">${esc(v.askScan.ansHeadLabel)}</span>
            <span style="font-size:12.5px;color:var(--ink-3);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-left:auto">”${esc(v.askScan.q)}”</span>
          </div>
          <p style="margin:0;font-size:16px;line-height:2;color:var(--ink);max-width:72ch;white-space:pre-wrap">${esc(v.askScan.answer)}${ v.askScan.ansTyping ? '<span class="ai-blink" style="display:inline-block;width:9px;height:17px;background:var(--accent);vertical-align:-3px;margin-left:3px"></span>' : '' }</p>
          ${ v.askScan.sources.length ? `
          <div style="display:flex;gap:9px;flex-wrap:wrap;margin-top:15px">
            ${ v.askScan.sources.map(function(src){ return `
              <button data-click="${on(src.onCite)}" title="Öppna lektionen och chatta" style="display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--ink);white-space:nowrap;max-width:280px;overflow:hidden;text-overflow:ellipsis;background:var(--surface);border:1px solid color-mix(in srgb,var(--accent) 45%,var(--line));border-radius:8px;padding:5px 10px;cursor:pointer;font-family:inherit;transition:border-color .12s,background .12s"><span style="width:6px;height:6px;border-radius:2px;background:var(--accent);flex:0 0 auto"></span>${esc(src.rec)}<span style="font-family:var(--mono);font-size:9.5px;color:var(--ink-3)">${ src.sub ? esc(src.sub) + ' ' : '' }↗</span></button>
            `; }).join('') }
          </div>
          ` : '' }
        </div>
        ` : '' }
      </div>
      ` : '' }

      <div style="max-width:760px;margin:22px auto 10px;display:flex;gap:9px;justify-content:center;align-items:center;flex-wrap:wrap">
        ${ v.hasGroups ? filterDrop(v.fKlassLabel, v.klassSelOn, v.fKlassOpen, v.fKlassToggle, v.fPopAnim, v.klassMenuOpts) : '' }
        ${ v.hasCourses ? filterDrop(v.fKursLabel, v.kursSelOn, v.fKursOpen, v.fKursToggle, v.fPopAnim, v.kursMenuOpts) : '' }
        ${ v.hasMonths ? filterDrop(v.fDatumLabel, v.datumSelOn, v.fDatumOpen, v.fDatumToggle, v.fPopAnim, v.datumMenuOpts) : '' }
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
                  <span data-cc="${esc(h.cc)}" style="border-radius:99px;padding:2px 10px;font-size:11.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:0 1 auto;min-width:0">${esc(h.tagLabel)}</span>
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
                  <span style="font-family:var(--mono);font-size:10px;letter-spacing:0.07em;text-transform:uppercase;color:var(--accent)">Öppna &amp; chatta ↗</span>
                  <span style="flex:1"></span>
                  <button data-click="${on(h.onOpen)}" aria-label="Öppna transkriptvyn" title="Öppna transkriptvyn med ljud" style="width:29px;height:29px;border:1px solid var(--line);background:var(--surface);border-radius:8px;cursor:pointer;color:var(--ink-3);display:flex;align-items:center;justify-content:center;transition:border-color .12s,color .12s"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h5l2 2v8H6z"></path><path d="M3 5v8.5h7"></path></svg></button>
                  <button data-click="${on(h.onRename)}" aria-label="Redigera uppgifter" title="Redigera klass, kurs, sal och datum" style="width:29px;height:29px;border:1px solid var(--line);background:var(--surface);border-radius:8px;cursor:pointer;color:var(--ink-3);display:flex;align-items:center;justify-content:center;transition:border-color .12s,color .12s"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.3 2.2l2.5 2.5L5.5 13H3v-2.5z"></path></svg></button>
                  <button data-click="${on(h.onDelete)}" aria-label="Ta bort" style="width:29px;height:29px;border:1px solid var(--line);background:var(--surface);border-radius:8px;cursor:pointer;color:var(--ink-3);display:flex;align-items:center;justify-content:center;transition:border-color .12s,color .12s"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.5 8.5h6l.5-8.5"></path></svg></button>
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
                <button data-click="${on(it.onDone)}" aria-label="Markera klar" title="Markera klar" style="flex:0 0 auto;width:18px;height:18px;margin-top:1px;border-radius:5px;border:1.5px solid ${it.done?'var(--ok)':'var(--line-2)'};background:${it.done?'var(--ok)':'transparent'};cursor:pointer;color:#fff;font-size:11px;display:flex;align-items:center;justify-content:center">${it.done?'✓':''}</button>
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

function spotlightPanel(s){
  return `
    <div style="max-width:820px;margin:0 auto 6px">
      <div style="display:flex;align-items:center;gap:13px;background:var(--surface);border:1.5px solid var(--ink);border-radius:14px;padding:9px 10px 9px 18px;box-shadow:var(--shadow)">
        <span class="ai-blink" style="width:9px;height:9px;border-radius:50%;background:var(--accent);flex:0 0 auto"></span>
        <input value="${esc(s.query)}" data-input="${on(s.onInput)}" data-keydown="${on(s.onKey)}"
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
        <span style="flex:1"></span>
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
          <div style="background:var(--sunken);border:1px solid var(--line);border-radius:13px;padding:15px 18px;margin-bottom:12px;color:var(--ink-2);font-size:14px;line-height:1.5">Ställ en fråga om innehållet — t.ex. ”Vad var det viktigaste som togs upp?”. Varje påstående i svaret förankras i numrerade källor som visas bredvid.</div>
          ` : '' }

          ${ c.chatHasMsgs ? `
          <div style="display:flex;flex-direction:column;gap:11px;margin-bottom:14px">
            ${ c.chat.map(function(m){ return `
              <div style="${m.rowStyle}">
                ${ m.hasReason ? `
                  <div style="${m.reasonStyle}"><span style="display:block;font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--ink-3);margin-bottom:4px">Resonemang</span>${esc(m.reason)}</div>
                ` : '' }
                ${ m.hasCites ? `
                <div style="align-self:stretch;background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:5px 15px 15px 15px;padding:15px 17px;box-shadow:var(--shadow-sm)">
                  <div style="display:grid;grid-template-columns:1fr 244px;gap:18px;align-items:start">
                    <div style="font-size:15px;line-height:1.78;color:var(--ink);min-width:0">
                      ${ m.tokens.map(function(tk){ return tk.isText
                        ? `<span>${renderRichInline(tk.text)}</span>`
                        : `<button data-click="${on(tk.onCite)}" data-csup="${tk.supFlag}" aria-label="Visa källa ${esc(tk.num)} i transkriptet" style="display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;padding:0 5px;font-size:11px;font-weight:700;color:var(--accent);background:var(--accent-weak);border:1px solid color-mix(in srgb,var(--accent) 28%,transparent);border-radius:6px;cursor:pointer;vertical-align:2px;margin:0 1.5px;font-family:inherit;transition:transform .1s">${esc(tk.num)}</button>`; }).join('') }
                    </div>
                    <div style="background:var(--sunken);border:1px solid var(--line);border-radius:13px;padding:12px">
                      <div style="display:flex;align-items:center;gap:7px;font-size:10.5px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--ink-3);margin-bottom:10px"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 3h10v10H3z" stroke-linejoin="round"></path><path d="M6 6.5h4M6 9.5h4" stroke-linecap="round"></path></svg>Källor i transkriptet</div>
                      ${ m.sources.map(function(src){ return `
                      <div data-click="${on(src.onPick)}" data-crow="${src.rowFlag}" style="display:flex;flex-direction:column;gap:3px;padding:9px 10px;border-radius:9px;cursor:pointer;border:1px solid transparent;margin-bottom:5px;transition:box-shadow .18s,border-color .18s">
                        <span style="display:flex;align-items:center;gap:7px;font-size:12px;font-weight:700;color:var(--accent);font-variant-numeric:tabular-nums"><span data-rownum style="width:16px;height:16px;border-radius:5px;background:var(--accent-weak);color:var(--accent);font-size:10px;display:flex;align-items:center;justify-content:center;font-weight:700;flex:0 0 auto">${esc(src.num)}</span>${esc(src.time)}</span>
                        <span style="font-size:12.5px;line-height:1.45;color:var(--ink-2)">${esc(src.text)}</span>
                      </div>
                      `; }).join('') }
                      ${ c.openTranscript ? `<span data-click="${on(c.openTranscript)}" style="display:inline-flex;align-items:center;gap:5px;margin-top:3px;color:var(--accent);font-size:12px;font-weight:600;cursor:pointer">Hela transkriptet<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3.5 10.5 8 6 12.5"></path></svg></span>` : '' }
                    </div>
                  </div>
                </div>
                ` : `
                <div style="${m.bubbleStyle}">${ m.isUser ? esc(m.text) : renderRich(m.text) }</div>
                ` }
              </div>
            `; }).join('') }
            ${ c.chatTyping ? `
            <div style="align-self:flex-start;display:flex;align-items:center;gap:9px;color:var(--ink-2);font-size:13.5px;padding:8px 12px;background:var(--surface);border:1px solid var(--line);border-radius:14px 14px 14px 4px"><span style="width:13px;height:13px;border-radius:50%;border:2px solid var(--line-2);border-top-color:var(--accent);animation:spin .7s linear infinite;flex:0 0 auto"></span>Söker i transkriptet<span class="insp-dots" style="color:var(--ink-3)"><i></i><i></i><i></i></span></div>
            ` : '' }
          </div>
          ` : '' }

          <div style="display:flex;gap:10px;align-items:center">
            <input value="${esc(c.chatInput)}" data-input="${on(c.onChatInput)}" data-keydown="${on(c.onChatKey)}" placeholder="Skriv en fråga …" style="flex:1;min-width:0;background:var(--sunken);border:1px solid var(--line);color:var(--ink);border-radius:11px;padding:12px 14px;font-size:15px;font-family:inherit;outline:none">
            <button data-click="${on(c.onChatSend)}" ${c.chatTyping ? 'disabled' : ''} style="flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;gap:8px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:11px;padding:12px 20px;font-size:15px;font-weight:500;cursor:${c.chatTyping ? 'default' : 'pointer'};opacity:${c.chatTyping ? '.5' : '1'};font-family:inherit;box-shadow:var(--shadow-sm);transition:background .15s">Skicka</button>
          </div>

          <div style="display:flex;align-items:center;gap:10px;margin-top:11px;flex-wrap:wrap;padding:0 2px">
            <button data-click="${on(c.onToggleChatThink)}" style="${c.chatThinkBtnStyle}" aria-pressed="${c.chatThink ? 'true' : 'false'}">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8 1.5a4.5 4.5 0 0 0-2.6 8.2c.4.3.6.6.6 1v.8h4v-.8c0-.4.2-.7.6-1A4.5 4.5 0 0 0 8 1.5z"></path><path d="M6 14.5h4"></path></svg>
              Tänk djupare
            </button>
            <span style="font-size:12px;color:var(--ink-3);flex:1;min-width:120px">${esc(c.chatThinkHint)}</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;margin-top:9px;padding:0 2px;flex-wrap:wrap">
            <span style="width:7px;height:7px;border-radius:50%;flex:0 0 auto;background:var(--ok)"></span>
            <span style="font-size:12.5px;color:var(--ink-2)">Lokalt med <strong style="color:var(--ink);font-weight:600">${esc(c.ppModel)}</strong></span>
          </div>
          <div data-follow="chatend" style="height:1px"></div>
`; }

// Kalenderförslaget i lektionsoverlayen — "Förslag → Google Kalender" med
// dag/tid-väljare och en kommandorad som justerar tid/titel/anteckning.
function lessonEventBox(ev){
  return `
    <div style="border:1px dashed var(--line-2);background:var(--sunken);border-radius:10px;padding:11px 13px;margin-bottom:12px;animation:fadeup .3s ease both">
      ${ ev.notAdded ? `
      <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:9px">
        <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.07em;text-transform:uppercase;color:var(--ink-3)">Förslag → Google Kalender</span>
        ${ ev.calKnown ? (ev.calConnected
          ? `<span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.07em;text-transform:uppercase;color:var(--ok)">● ansluten</span>`
          : `<button data-click="${on(ev.onConnect)}" style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.07em;text-transform:uppercase;color:var(--accent);background:transparent;border:1px solid color-mix(in srgb,var(--accent) 40%,transparent);border-radius:6px;padding:4px 9px;cursor:pointer">Anslut Google-konto</button>`)
          : `<span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.07em;text-transform:uppercase;color:var(--ink-3)">kontrollerar anslutning …</span>` }
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <input value="${esc(ev.title)}" data-input="${on(ev.setTitle)}" style="flex:2 1 220px;min-width:0;border:1px solid var(--line);background:var(--surface);border-radius:8px;padding:8px 11px;font-size:13.5px;font-weight:500;font-family:inherit;color:var(--ink)">
        <button data-click="${on(ev.onTogglePick)}" title="Välj dag och tid" style="flex:1 1 160px;min-width:0;display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);background:var(--surface);border-radius:8px;padding:8px 11px;font-size:13px;font-family:inherit;color:var(--ink);cursor:pointer;font-variant-numeric:tabular-nums;white-space:nowrap;transition:border-color .14s"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" style="flex:0 0 auto"><rect x="2" y="3" width="12" height="11" rx="2"></rect><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3"></path></svg><span style="min-width:0;overflow:hidden;text-overflow:ellipsis">${esc(ev.when)}</span><span style="flex:1"></span><svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="flex:0 0 auto"><path d="M4 6l4 4 4-4"></path></svg></button>
        <button data-click="${on(ev.onAdd)}" ${ ev.busy ? 'disabled' : '' } style="flex:0 0 auto;display:inline-flex;align-items:center;gap:7px;background:var(--btn-bg);color:var(--btn-fg);border:none;border-radius:8px;padding:9px 15px;font-size:13px;font-weight:600;cursor:${ ev.busy ? 'default' : 'pointer' };font-family:inherit;opacity:${ ev.busy ? '.6' : '1' }">${ ev.busy ? 'Lägger till …' : 'Lägg till ✓' }</button>
      </div>
      ${ ev.pickOpen ? `
        <div style="display:grid;grid-template-columns:180px 1fr;margin-top:10px;border:1px solid var(--line);border-radius:9px;background:var(--surface);overflow:hidden;animation:ml-popin .2s cubic-bezier(.16,1,.3,1) both">
          <div data-hidescroll style="border-right:1px solid var(--line);padding:8px;display:flex;flex-direction:column;gap:1px;max-height:224px;overflow:auto">
            <span style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);padding:3px 8px 6px">Dag</span>
            ${ ev.dayOpts.map(function(d){ return `
              <button data-key="${esc(d.key)}" data-click="${on(d.onPick)}" data-q="${esc(d.curQ)}" style="display:flex;align-items:center;gap:8px;border:1px solid transparent;background:transparent;color:var(--ink);border-radius:6px;padding:6px 8px;font-size:13px;font-family:inherit;cursor:pointer;text-align:left;white-space:nowrap"><span style="min-width:0;overflow:hidden;text-overflow:ellipsis">${esc(d.label)}</span><span style="flex:1"></span>${ d.hasPre ? `<span style="font-family:var(--mono);font-size:8.5px;letter-spacing:0.05em;text-transform:uppercase;color:var(--accent)">${esc(d.pre)}</span>` : '' }</button>
            `; }).join('') }
          </div>
          <div style="padding:8px">
            <span style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);padding:3px 8px 6px;display:block">Tid</span>
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:5px">
              ${ ev.timeOpts.map(function(t2){ return `
                <button data-key="${esc(t2.key)}" data-click="${on(t2.onPick)}" data-q="${esc(t2.curQ)}" style="border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:6px;padding:7px 4px;font-size:12.5px;font-family:inherit;cursor:pointer;font-variant-numeric:tabular-nums;text-align:center">${esc(t2.label)}</button>
              `; }).join('') }
            </div>
            <div style="font-size:11px;color:var(--ink-3);padding:8px 8px 2px">Välj dag, sedan tid — stängs automatiskt.</div>
          </div>
        </div>
      ` : '' }
      <div style="margin-top:9px">
        <div style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3);margin-bottom:5px">Anteckning i kalenderposten</div>
        <textarea data-input="${on(ev.setDesc)}" rows="2" style="width:100%;box-sizing:border-box;resize:vertical;border:1px solid var(--line);background:var(--surface);border-radius:8px;padding:8px 11px;font-size:13px;line-height:1.5;font-family:inherit;color:var(--ink);outline:none">${esc(ev.desc)}</textarea>
      </div>
      <div style="margin-top:10px;border-top:1px dashed var(--line-2);padding-top:10px">
        <div style="display:flex;align-items:center;gap:7px;margin-bottom:8px">
          <span class="ai-blink" style="width:6px;height:6px;border-radius:50%;background:var(--accent);flex:0 0 auto"></span>
          <span style="font-family:var(--mono);font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3)">Ändra förslaget — tid, datum &amp; innehåll</span>
        </div>
        ${ ev.aiMsgs.map(function(am){ return am.isUser ? `
          <div style="display:flex;justify-content:flex-end;margin-bottom:6px"><span style="max-width:82%;background:var(--ink);color:var(--canvas);border-radius:9px 9px 3px 9px;padding:6px 10px;font-size:12.5px;line-height:1.5">${esc(am.text)}</span></div>
        ` : `
          <div style="display:flex;justify-content:flex-start;margin-bottom:6px"><span style="max-width:88%;background:var(--surface);border:1px solid var(--line);border-radius:9px 9px 9px 3px;padding:6px 10px;font-size:12.5px;line-height:1.5;color:var(--ink)">${esc(am.text)}</span></div>
        `; }).join('') }
        ${ ev.aiBusy ? `
          <div style="display:flex;align-items:center;gap:8px;color:var(--ink-2);font-size:12px;margin-bottom:7px"><span style="width:11px;height:11px;border-radius:50%;border:2px solid var(--line-2);border-top-color:var(--accent);animation:spin .7s linear infinite;flex:0 0 auto"></span>Uppdaterar förslaget …</div>
        ` : '' }
        ${ ev.aiEmpty ? `
          <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">
            <button data-click="${on(ev.aiChip1)}" style="border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:99px;padding:5px 11px;font-size:12px;font-family:inherit;cursor:pointer;transition:border-color .12s,color .12s">”Flytta till fredag 10:00”</button>
            <button data-click="${on(ev.aiChip2)}" style="border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:99px;padding:5px 11px;font-size:12px;font-family:inherit;cursor:pointer;transition:border-color .12s,color .12s">”Lägg till läxan i anteckningen”</button>
            <button data-click="${on(ev.aiChip3)}" style="border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:99px;padding:5px 11px;font-size:12px;font-family:inherit;cursor:pointer;transition:border-color .12s,color .12s">”Kortare titel”</button>
          </div>
        ` : '' }
        <div style="display:flex;gap:7px">
          <input value="${esc(ev.aiInput)}" data-input="${on(ev.onAiInput)}" data-keydown="${on(ev.onAiKey)}" placeholder="T.ex. ”flytta till onsdag 14:30” eller ”lägg till att de ska repetera bråken” …" style="flex:1;min-width:0;border:1px solid var(--line);background:var(--surface);border-radius:8px;padding:8px 11px;font-size:13px;font-family:inherit;color:var(--ink);outline:none">
          <button data-click="${on(ev.onAiSend)}" style="flex:0 0 auto;background:var(--accent-weak);color:var(--accent);border:1px solid var(--accent);border-radius:8px;padding:8px 13px;font-size:12.5px;font-weight:600;cursor:pointer;font-family:inherit">Ändra ✨</button>
        </div>
      </div>
      ` : `
      <div style="display:flex;align-items:center;gap:9px;font-size:13px;font-weight:500;color:var(--ok)"><span style="width:16px;height:16px;border-radius:50%;background:var(--ok);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:9px">✓</span>Tillagd i Google Kalender — ${esc(ev.title)}</div>
      ` }
    </div>`;
}

function viewModals(v){ return `
  ${ v.anyDDOpen ? `
    <div data-click="${on(v.closeDD)}" style="position:fixed;inset:0;z-index:25"></div>
  ` : '' }

  ${ v.lessonChatOpen ? `
  <div data-click="${on(v.closeLessonChat)}" data-screen-label="Lektion (overlay)" style="position:fixed;inset:0;z-index:120;display:flex;align-items:center;justify-content:center;padding:clamp(10px,3vw,38px);background:color-mix(in srgb,var(--canvas) 58%,transparent);backdrop-filter:blur(9px);animation:modalback .3s ease">
    <div data-click="${on(v.stop)}" data-modal-card style="width:min(960px,96vw);height:min(88vh,880px);display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--line);border-radius:20px;box-shadow:var(--shadow);overflow:hidden">
      <div style="flex:0 0 auto;display:flex;align-items:center;gap:11px;padding:11px 13px 11px 11px;border-bottom:1px solid var(--line)">
        <button data-click="${on(v.closeLessonChat)}" aria-label="Stäng (Esc)" title="Stäng · Esc" style="flex:0 0 auto;width:34px;height:34px;display:flex;align-items:center;justify-content:center;border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:10px;cursor:pointer;transition:transform .14s cubic-bezier(.2,.8,.25,1),border-color .14s,background .14s,color .14s" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important;color:var(--ink) !important"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8"></path></svg></button>
        <span data-cc="${esc(v.ovCc)}" style="border-radius:99px;padding:3px 11px;font-size:11.5px;font-weight:600;white-space:nowrap;flex:0 0 auto">${esc(v.ovTag)}</span>
        <div style="min-width:0">
          <div style="font-size:15px;font-weight:600;color:var(--ink);letter-spacing:-.01em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.lessonChatName)}</div>
          <div style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.06em;text-transform:uppercase;color:var(--ink-3);margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.ovMeta)}</div>
        </div>
        <span style="flex:1"></span>
        ${ v.ovHasLesson ? `
        <button data-click="${on(v.onAnalyze)}" ${ v.ovAnalyzing ? 'disabled' : '' } title="Extrahera kalenderposter, åtgärder och svårigheter till Kommande och Terminstrender" style="flex:0 0 auto;display:inline-flex;align-items:center;gap:7px;background:var(--accent-weak);color:var(--accent);border:1px solid color-mix(in srgb,var(--accent) 38%,transparent);border-radius:9px;padding:8px 13px;font-size:12.5px;font-weight:600;cursor:${ v.ovAnalyzing ? 'default' : 'pointer' };font-family:inherit;opacity:${ v.ovAnalyzing ? '.6' : '1' };transition:transform .14s cubic-bezier(.2,.8,.25,1),border-color .14s,background .14s" data-sh="background:color-mix(in srgb,var(--accent) 15%,transparent) !important">${ v.ovAnalyzing ? `<span style="width:13px;height:13px;border-radius:50%;border:2px solid color-mix(in srgb,var(--accent) 35%,transparent);border-top-color:var(--accent);animation:spin .7s linear infinite;flex:0 0 auto"></span>Analyserar …` : `<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" style="flex:0 0 auto"><path d="M8 1.8l1.4 3.6 3.6 1.4-3.6 1.4L8 11.8 6.6 8.2 3 6.8l3.6-1.4z"></path></svg>Analysera lektion` }</button>
        <button data-click="${on(v.onOvReport)}" ${ v.ovReportBusy ? 'disabled' : '' } title="Exportera rapport (öppnas i webbläsaren, skriv ut som PDF)" style="flex:0 0 auto;display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:9px;padding:8px 13px;font-size:12.5px;font-weight:500;cursor:${ v.ovReportBusy ? 'default' : 'pointer' };font-family:inherit;opacity:${ v.ovReportBusy ? '.6' : '1' };transition:transform .14s cubic-bezier(.2,.8,.25,1),border-color .14s,background .14s,color .14s" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important;color:var(--ink) !important"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="flex:0 0 auto"><path d="M9 2H4.5A1.5 1.5 0 0 0 3 3.5v9A1.5 1.5 0 0 0 4.5 14h7A1.5 1.5 0 0 0 13 12.5V6z"></path><path d="M9 2v4h4M6 9h4M6 11.2h4"></path></svg>${ v.ovReportBusy ? 'Exporterar …' : 'Rapport' }</button>
        ` : '' }
        <button data-click="${on(v.ovOpenFull)}" title="Öppna hela transkriptvyn" style="flex:0 0 auto;display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);background:var(--surface);color:var(--ink-2);border-radius:9px;padding:8px 13px;font-size:12.5px;font-weight:500;cursor:pointer;font-family:inherit;transition:transform .14s cubic-bezier(.2,.8,.25,1),border-color .14s,background .14s,color .14s" data-sh="border-color:var(--line-2) !important;background:var(--sunken) !important;color:var(--ink) !important"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" style="flex:0 0 auto"><path d="M6 2.5H3.5A1 1 0 0 0 2.5 3.5V6M10 2.5h2.5a1 1 0 0 1 1 1V6M13.5 10v2.5a1 1 0 0 1-1 1H10M6 13.5H3.5a1 1 0 0 1-1-1V10"></path></svg>Transkript</button>
      </div>
      <div data-hidescroll style="flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;padding:18px 22px 6px">
        <div style="max-width:760px;margin:0 auto">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
            <span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--ink-3)">Transkription</span>
            <div style="flex:1;height:1px;background:var(--line)"></div>
            ${ v.ovHasHit ? `<span style="font-family:var(--mono);font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--accent)">Källa · ${esc(v.ovHitT)}</span>` : '' }
          </div>
          ${ v.lessonChatLoading ? `
          <div style="display:flex;align-items:center;gap:10px;color:var(--ink-2);font-size:14px;padding:20px 0"><span style="width:15px;height:15px;border-radius:50%;border:2px solid var(--line-2);border-top-color:var(--accent);animation:spin .7s linear infinite;flex:0 0 auto"></span>Läser in transkriptet …</div>
          ` : v.ovRows.map(function(p){ return p.hit ? `
            <div data-key="ovr-${esc(p.t)}" style="display:flex;gap:14px;padding:10px 13px;margin:2px -13px;background:var(--accent-weak);border:1px solid color-mix(in srgb,var(--accent) 38%,var(--line));border-radius:9px">
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
      <div style="flex:0 0 auto;border-top:1px solid var(--line);background:var(--sunken)">
        <div data-hidescroll style="max-height:44vh;overflow:auto;overscroll-behavior:contain;padding:13px 18px 14px">
          ${ v.lessonChatThread.chatEmpty ? `
          <div style="display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-bottom:12px">
            <button data-click="${on(v.ovAskSum)}" style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-2);background:var(--surface);border:1px solid var(--line);border-radius:99px;padding:7px 13px;cursor:pointer;font-family:inherit;transition:transform .14s cubic-bezier(.2,.8,.25,1),border-color .14s,color .14s,background .14s" data-sh="border-color:var(--line-2) !important;color:var(--ink) !important">Sammanfatta lektionen</button>
            <button data-click="${on(v.ovAskStud)}" style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-2);background:var(--surface);border:1px solid var(--line);border-radius:99px;padding:7px 13px;cursor:pointer;font-family:inherit;transition:transform .14s cubic-bezier(.2,.8,.25,1),border-color .14s,color .14s,background .14s" data-sh="border-color:var(--line-2) !important;color:var(--ink) !important">Vilka elever nämns?</button>
            <button data-click="${on(v.ovAskRemind)}" style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-2);background:var(--surface);border:1px solid var(--line);border-radius:99px;padding:7px 13px;cursor:pointer;font-family:inherit;transition:transform .14s cubic-bezier(.2,.8,.25,1),border-color .14s,color .14s,background .14s" data-sh="border-color:var(--line-2) !important;color:var(--ink) !important">Skapa läxpåminnelse</button>
            <button data-click="${on(v.proposeOvEvent)}" style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;font-weight:600;color:var(--accent);background:var(--accent-weak);border:1px solid color-mix(in srgb,var(--accent) 40%,transparent);border-radius:99px;padding:7px 13px;cursor:pointer;font-family:inherit;transition:transform .14s cubic-bezier(.2,.8,.25,1),border-color .14s,background .14s" data-sh="background:color-mix(in srgb,var(--accent) 15%,transparent) !important"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" style="flex:0 0 auto"><rect x="2" y="3" width="12" height="11" rx="2"></rect><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3M8 9v3M6.5 10.5h3"></path></svg>Kalenderhändelse</button>
          </div>
          ` : '' }
          ${ v.ovEvent ? lessonEventBox(v.ovEvent) : '' }
          ${ chatThread(v.lessonChatThread) }
        </div>
      </div>
    </div>
  </div>
  ` : '' }

  ${ v.renameOpen ? `
  <div data-click="${on(v.onRenameCancel)}" style="position:fixed;inset:0;z-index:130;background:rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;padding:24px;animation:fadeup .2s ease">
    <div data-click="${on(v.stop)}" style="width:min(94vw,460px);background:var(--canvas);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);padding:20px 22px">
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
      <div data-ref="${on(v.seekTrackRef)}" data-click="${on(v.onSeekClick)}" style="flex:1;height:42px;display:flex;align-items:stretch;gap:2px;cursor:pointer">
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

  ${ v.cleanModalOpen ? `
  <div data-click="${on(v.closeCleanModal)}" style="position:fixed;inset:0;z-index:125;display:flex;align-items:center;justify-content:center;padding:24px;background:color-mix(in srgb,var(--canvas) 64%,transparent);backdrop-filter:blur(7px);animation:modalback .26s ease">
    <div data-click="${on(v.stop)}" style="width:min(94vw,680px);max-height:84vh;display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--line);border-radius:20px;box-shadow:var(--shadow);overflow:hidden;animation:modalpop .42s cubic-bezier(.16,1,.3,1)">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:14px;padding:24px 26px 14px;border-bottom:1px solid var(--line);flex:0 0 auto">
        <div style="min-width:0">
          <span style="font-size:11.5px;font-weight:600;letter-spacing:0.05em;color:var(--accent);background:var(--accent-weak);padding:3px 9px;border-radius:6px;display:inline-block;margin-bottom:9px">KORREKTURLÄST</span>
          <h2 style="font-size:20px;font-weight:600;letter-spacing:-0.02em;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(v.statusFile)}</h2>
          <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-top:11px">
            ${ v.cleanLegendAudio ? `<span style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-2)"><span style="width:12px;height:12px;border-radius:4px;background:color-mix(in srgb,var(--ok) 20%,transparent);border:1px solid color-mix(in srgb,var(--ok) 45%,transparent)"></span>mot ljudet</span>` : '' }
            <span style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--ink-2)"><span style="width:12px;height:12px;border-radius:4px;background:color-mix(in srgb,var(--accent) 16%,transparent);border:1px solid color-mix(in srgb,var(--accent) 45%,transparent)"></span>språk &amp; skiljetecken</span>
            <span style="font-size:12.5px;color:var(--ink-3);font-variant-numeric:tabular-nums">${esc(v.cleanChangeCount)} rättelser</span>
          </div>
        </div>
        <button data-click="${on(v.closeCleanModal)}" aria-label="Stäng" style="flex:0 0 auto;width:34px;height:34px;display:flex;align-items:center;justify-content:center;background:var(--surface);border:1px solid var(--line);border-radius:9px;color:var(--ink-2);cursor:pointer;font-size:15px">✕</button>
      </div>
      <div data-hidescroll="1" style="overflow:auto;overscroll-behavior:contain;padding:18px 26px 24px;min-height:0">
        <div style="font-size:16px;color:var(--ink);line-height:1.7">
          ${ v.cleanFullParts.map(function(p){ return p.ch ? `<span style="background:color-mix(in srgb,var(--accent) 15%,transparent);color:var(--accent);border-radius:4px;padding:0 3px;font-weight:500">${esc(p.s)}</span>` : `<span>${esc(p.s)}</span>`; }).join(' ') }
        </div>
      </div>
    </div>
  </div>
  ` : '' }

  ${ v.calSetupOpen ? `
  <div data-click="${on(v.calSetup.onClose)}" style="position:fixed;inset:0;z-index:135;display:flex;align-items:center;justify-content:center;padding:24px;background:color-mix(in srgb,var(--canvas) 64%,transparent);backdrop-filter:blur(7px);animation:modalback .26s ease">
    <div data-click="${on(v.stop)}" style="width:min(94vw,560px);max-height:88vh;overflow:auto;overscroll-behavior:contain;background:var(--surface);border:1px solid var(--line);border-radius:20px;box-shadow:var(--shadow);animation:modalpop .42s cubic-bezier(.16,1,.3,1)">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:14px;padding:22px 24px 14px;border-bottom:1px solid var(--line)">
        <div style="min-width:0">
          <span style="font-family:var(--mono);font-size:10.5px;font-weight:500;letter-spacing:0.08em;color:var(--c-sky);background:color-mix(in srgb,var(--c-sky) 13%,transparent);border:1px solid color-mix(in srgb,var(--c-sky) 28%,transparent);padding:3px 9px;border-radius:6px">GOOGLE KALENDER</span>
          <h2 style="font-size:20px;font-weight:600;letter-spacing:-0.02em;margin:9px 0 0">Koppla Google Kalender</h2>
        </div>
        <button data-click="${on(v.calSetup.onClose)}" aria-label="Stäng" style="flex:0 0 auto;width:34px;height:34px;display:flex;align-items:center;justify-content:center;background:var(--surface);border:1px solid var(--line);border-radius:9px;color:var(--ink-2);cursor:pointer;font-size:15px">✕</button>
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
      <div style="height:6px;border-radius:99px;background:var(--track);overflow:hidden;margin:7px 0 5px"><div style="${v.toastBarStyle}"></div></div>
      <div style="font-size:12px;color:var(--ink-2);font-variant-numeric:tabular-nums">${esc(v.toastDetail)}</div>
    </div>
    ` }
    <button data-click="${on(v.closeToast)}" aria-label="Stäng" style="width:26px;height:26px;flex:0 0 auto;align-self:flex-start;border:none;background:transparent;border-radius:7px;cursor:pointer;color:var(--ink-3);font-size:13px;display:flex;align-items:center;justify-content:center" data-sh="background:var(--sunken) !important;color:var(--ink) !important">✕</button>
  </div>
  ` : '' }
`; }

  // <<<VIEWS_END>>>

  function view(v) {
    return viewHeader(v) +
      '<main style="max-width:1120px;margin:0 auto;padding:0 24px">' +
      (v.tabTranscribe ? viewTranscribe(v) : '') +
      (v.tabRecordings ? viewRecordings(v) : '') +
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
    loadIncompleteRecs();  // offer to recover a recording that never finished (crash)
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();

  /* Exponera state för e2e-tester (endast med ?e2e=1 i URL:en; aldrig i normal drift). */
  if (/[?&]e2e=1(&|$)/.test(location.search)) { window.S = S; }

})();
