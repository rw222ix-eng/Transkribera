I now have the complete picture: initial state, all actions, mock data, derivations, and timers. Here is the structured blueprint.

# Transkribera — Front-End State Machine Blueprint

Extracted from the `<script type="text/x-dc">` runtime (lines 1189-2609). The prototype is a React-like class component (`extends DCLogic`) with a single `state` object, `setState`, `componentDidUpdate`, and a `renderVals()` that derives every binding/boolean the template consumes. All Swedish strings are reproduced verbatim.

---

## 1. Complete State Object (initial values + meaning)

Initial state literal at lines 1191-1261.

| Field | Initial value | Meaning |
|---|---|---|
| `theme` | `'light'` | UI theme; mirrored to `document.documentElement.dataset.theme`. Values: `'light'` / `'dark'`. |
| `tab` | `'transcribe'` | Active top tab. Values: `'transcribe'` / `'models'` / `'history'`. |
| `source` | `'intervju_lund.mkv'` | Current source filename (active queue item name). |
| `dragging` | `false` | Drop-zone is in drag-over state. |
| `step` | `'config'` | Transcribe-tab wizard step. Values: `'source'` / `'config'` / `'process'`. |
| `model` | `'KB-Whisper large'` | Selected Whisper model id. |
| `language` | `'sv'` | Selected language. Values: `''` (Auto) / `'sv'` / `'en'`. |
| `formats` | `{ srt:true, txt:true, vtt:false }` | Output format toggles. |
| `run` | `'idle'` | Transcription run state. Values: `'idle'`/`'running'`/`'done'`/`'error'`/`'cancelled'`. |
| `progress` | `0` | Run progress 0-100. |
| `elapsed` | `0` | Elapsed seconds (fractional). |
| `log` | `[]` | Array of log line strings. |
| `pp` | `'idle'` | Post-process run state. Values: `'idle'`/`'running'`/`'done'`. |
| `ppOp` | `'summary'` | Post-process operation. Values: `'clean'`/`'summary'`/`'chat'` (also `'analyze'` produced by `ppText`/`ppOutTitles` but not in OPS list — legacy). |
| `ppModel` | `'Qwen3 30B-A3B'` | Selected LLM id for post-process/chat. |
| `ppOut` | `''` | Post-process output text. |
| `ppPct` | `0` | Post-process progress 0-100. |
| `ppEnabled` | `false` | Post-process toggle (off by default). |
| `chat` | `[]` | Chat messages: `{ role:'user'|'assistant', text, attach? }`. |
| `chatInput` | `''` | Chat input box value. |
| `chatTyping` | `false` | Assistant "typing" indicator. |
| `chatModalOpen` | `false` | Chat modal open. |
| `chatAttach` | `[]` | Pending attachments: `{ kind:'image'|'file', label }`. |
| `openDD` | `null` | Which dropdown is open. Values: `null`/`'model'`/`'ppmodel'`/`'chatmodel'`/`'disk'`. |
| `search` | `''` | Models-tab online search query. |
| `diskTarget` | `'d'` | Selected disk id for downloads. |
| `onlineSort` | `'fit'` | Online-models sort. Values: `'fit'`/`'size'`/`'name'`. |
| `useCase` | `'all'` | LLM use-case filter. Values: `'all'`/`'text'`/`'sv'`/`'vision'`/`'omni'`. |
| `tip` | `null` | Custom tooltip: `{ text, x, y }`. |
| `installed` | `{ 'KB-Whisper large':true, 'Whisper large-v3':true, 'Qwen3 30B-A3B':true, 'Gemma 3 27B':true }` | Map id→true of installed models. |
| `downloading` | `{}` | Map id→bool currently downloading. |
| `dlProg` | `{}` | Map id→pct download progress. |
| `installing` | `{}` | Map id→bool currently installing. |
| `instProg` | `{}` | Map id→pct install progress. |
| `transcriptOpen` | `false` | Full transcript viewer open. |
| `logOpen` | `false` | Log modal open. |
| `toast` | `null` | Download toast: `{ name, size, pct, done }`. |
| `searchQuery` | `''` | In-transcript search query. |
| `currentMatch` | `0` | Index of current search match. |
| `queue` | `[{ id:'f1', name:'intervju_lund.mkv' }]` | File queue. |
| `qStatus` | `{}` | Map id→`'pending'`/`'running'`/`'done'`/`'error'`. |
| `qProgress` | `{}` | Map id→pct per file. |
| `activeId` | `'f1'` | Currently active queue item id. |
| `fileError` | `''` | Drop-zone validation message. |
| `diarize` | `false` | Speaker diarization enabled (off by default; costs time+VRAM). |
| `spkNames` | `['', '', '']` | Optional user labels for detected speakers. |
| `numSpeakers` | `'auto'` | Expected speaker count hint. Values: `'auto'`/`'2'`-`'6'`. |
| `diaInstallPrompt` | `false` | Show pyannote install gate. |
| `runError` | `null` | `{ title, detail, where }`. |
| `dlFailed` | `{}` | Map id→true (download/install failed/cancelled). |
| `editing` | `false` | Transcript edit mode. |
| `edits` | `{}` | Map lineIndex→edited text. |
| `edited` | `false` | Transcript has been edited (sticky flag). |
| `audioPlaying` | `false` | Audio player playing. |
| `audioT` | `0` | Audio playhead seconds (0-`AUDIO_DUR`=150). |
| `history` | 3 seed items (see §3) | Transcription history. |
| `histViewing` | `null` | History id currently open in transcript viewer. |
| `confirm` | `null` | `{ kind, id, title, body, label, danger }`. |
| `diskWarn` | `null` | `{ id, name, needGB, freeGB, drive }`. |

**Instance (non-state) fields used internally:** `_t` (run interval), `_pp`/`_ppIv` (post-process timers), `_chat` (chat reply timeout), `_au` (audio interval), `_toastIv`/`_toastT2` (toast timers), `_dl{}`/`_inst{}` (per-id download/install intervals), `_glideRAF`, `_editBuf{}`, `_wave[]` (memoized 72-bar waveform), `_lastStart` (double-click guard), `_prevTab/_prevStep/_prevRun/_prevPP/_prevOp/_prevChatLen`, `_wasOpen/_wasEditing/_pyWas`, `_scrollKey`, refs `_file/_search Ref/_scrollRef/_seek/_chatThread/_procScroll`.

---

## 2. Actions / Handlers and State Transitions

### Theme / tabs / dropdowns
- `toggleTheme` → `theme` light↔dark.
- `setTab(t)` → `{ tab:t, openDD:null }`.
- `toggleModelDD` / `togglePPDD` / `toggleChatModelDD` / `toggleDiskDD` → toggle `openDD` between its key and `null`.
- `closeDD` → `openDD:null`. (Backdrop closes any open dropdown; `anyDDOpen = openDD !== null`.)

### Source / queue (lines 1669-1704)
- `onSource(e)` → `source = e.target.value`.
- `ALLOWED` exts: `mp4, mkv, mov, webm, avi, m4v, mp3, wav, m4a, flac, aac, ogg, opus, wma`. `isMedia(n)` checks ext.
- `openPicker` → clears `fileError`, triggers hidden `<input type=file>`.
- `addFiles(names)`: filter good/bad by `isMedia`. If none good → `fileError:'Filformatet stöds inte — välj ljud eller video (MP4, MKV, MOV, MP3, WAV, M4A …).', dragging:false`. Else append non-duplicate items (`{id:'q'+Date.now()+'_'+k, name}`), set `step:'config'`, set `activeId` (keep existing or first), set `source`, and if some bad → `fileError:'Hoppade över N fil(er) — formatet stöds inte.'`
- `removeQ(id)` → remove from queue + `qStatus`; reassign `activeId` if it was removed; `step:'source'` if queue empties.
- `addSample(name)` → clears error, calls `addFiles([name])`. Bound as `addSampleNormal` ('mötesinspelning.mp3') and `addSampleCorrupt` ('skadad_inspelning.m4a').
- `onPickFile(e)` → map `e.target.files` names → `addFiles`; reset input.
- `onDragOver`/`onDragLeave`/`onDrop` → manage `dragging`; drop maps dropped files → `addFiles`.
- `goSource` → `{ step:'source', openDD:null, fileError:'' }`.
- `restart` → clears all timers/intervals and resets a large slice of state back to a fresh "source" screen (`source:'', queue:[], qStatus:{}, qProgress:{}, activeId:null, step:'source', run:'idle', progress:0, elapsed:0, log:[], pp:'idle', ppOp:'summary', ppOut:'', ppEnabled:false, chat:[], chatInput:'', chatTyping:false, chatModalOpen:false, chatAttach:[], openDD:null, transcriptOpen:false, runError:null, editing:false, edits:{}, edited:false, audioPlaying:false, audioT:0, histViewing:null, diaInstallPrompt:false, numSpeakers:'auto'`).

### Config (lines 1705-1741)
- `onSearch(e)` → `search`.
- `toggleFmt(f)` → flip `formats[f]`.
- `pickModel(id)` → `{ model:id, openDD:null }`.
- `pickLang(l)` → `{ language:l, model: recommendModel(l) }`. `recommendModel`: en→Canary-Qwen-2.5B else Whisper large-v3 (if installed); sv→KB-Whisper large; auto→KB-Whisper large then Whisper large-v3; fallback current model.
- `pickOp(o)` → `{ ppOp:o, pp:'idle', ppOut:'' }`; if `'chat'` → `seedChat()` + `openChatModal()`, else `closeChatModal()`.
- `pickPPModel(id)` / `pickChatModel(id)` → `{ ppModel:id, openDD:null }`.
- `pickDisk(id)` → `{ diskTarget:id, openDD:null }`.
- `setUseCase(k)` → `useCase`.
- `onlineSort` set inline via `setState({onlineSort:k})`.

### Diarization (lines 1744-1759)
- `PYANNOTE_ID = 'pyannote community-1'`.
- `toggleDiarize`: if on→turn off (`diarize:false, diaInstallPrompt:false`); if off and pyannote not installed→`diaInstallPrompt:true`; else `diarize:true`.
- `installPyannote` → if not busy/installed, `_startDownload(PYANNOTE_ID)`.
- `dismissDiaPrompt` → `diaInstallPrompt:false`.
- In `componentDidUpdate`: when pyannote becomes installed while prompt was open → auto `{ diarize:true, diaInstallPrompt:false }`.
- `setSpkName(i,v)` → update `spkNames[i]`. `addSpeaker` → push `''` (max 6). `removeSpeaker(i)` → remove (min 1). `setNumSpeakers(n)` → `numSpeakers`.

### Confirm modal / uninstall / history actions (lines 1762-1782)
- `askUninstall(id)` → `confirm:{ kind:'uninstall', id, title:'Ta bort '+id+'?', body:'Modellen raderas från disken (DRIVE). Du kan ladda ner den igen när som helst.', label:'Ta bort', danger:true }`.
- `askRerun(h)` → `confirm:{ kind:'rerun', id:h.id, title:'Transkribera om?', body:'"NAME" körs igenom på nytt med dina nuvarande inställningar (modell, språk och format). Den läggs i kön på Transkribera-fliken.', label:'Kör om', danger:false }`.
- `askDeleteHistory(id,name)` → `confirm:{ kind:'history', id, title:'Ta bort transkriberingen?', body:'"NAME" tas bort ur historiken. Filer du redan sparat på disken påverkas inte.', label:'Ta bort', danger:true }`.
- `confirmYes`: `uninstall`→delete `installed[id]` (and pick fallback model if current removed); `history`→filter out of `history`; `rerun`→`reRunHistory(h)`. All set `confirm:null`.
- `confirmNo` → `confirm:null`.
- `openHistory(h)` → `{ transcriptOpen:true, histViewing:h.id }`.
- `reRunHistory(h)` → `{ tab:'transcribe', step:'config', queue:[{id,name:h.name}], qStatus:{}, qProgress:{}, run:'idle', progress:0, elapsed:0, activeId:id, source:h.name, fileError:'', runError:null, openDD:null }`.

### Audio player (lines 1785-1794)
- `togglePlay`: if playing→stop interval, `audioPlaying:false`; else (if at end, reset `audioT:0`) `audioPlaying:true` + start interval ticking `audioT += 0.2` every 200ms until `AUDIO_DUR`(150), then stop.
- `onSeekClick(e)` → set `audioT` from click X fraction × 150.
- `jumpToLine(i)` → `audioT = parseTS(TRANSCRIPT[i].time)`; auto-play if paused.

### Transcript editing (lines 1797-1810)
- `toggleEdit`: if editing→`_commitEdits()` + `editing:false`; else `_editBuf={}`, stop audio, `{ editing:true, audioPlaying:false }`.
- `onEditInput(e)` → buffer `_editBuf[dataEline] = textContent`.
- `_commitEdits` → merge buffer into `edits` (delete entry if equals original; set `edited:true` if any change).
- `componentDidUpdate` populates each `[data-eline]` element's textContent with `lineText(i)` when edit mode turns on.

### Transcript viewer + search (lines 1465-1499)
- `openTranscript` → `{ transcriptOpen:true, histViewing:null }`.
- `closeTranscript` → commit edits if editing, stop audio, `{ transcriptOpen:false, editing:false, audioPlaying:false }`.
- `onTSearch(e)` → `{ searchQuery, currentMatch:0 }`.
- `countMatches()` counts substring matches across `lineText` of all transcript lines.
- `nextMatch`/`prevMatch` → cycle `currentMatch` mod count. `onSearchKey` → Enter=next, Shift+Enter=prev.
- Keyboard (`onKeyDown`): Esc closes chat modal / log / transcript (in that priority); Ctrl/Cmd+F focuses search when transcript open.

### Log modal
- `openLog` → `logOpen:true`. `closeLog` → `logOpen:false`.

### Download toast (lines 1470-1494) — for SRT/TXT/VTT/history file downloads
- `downloadFile(name,size)`: clears toast timers, `toast:{name,size||'24 KB',pct:0,done:false}`, then interval (140ms) increments `pct += 11..28`; at 100 → `done:true`, auto-clear after 2600ms.
- `closeToast` → clears timers, `toast:null`.

### Run / transcription engine (lines 1812-1924)
- `start`: guards (already running, empty queue, 400ms double-click). If `diarize && !pyInstalled` → `diaInstallPrompt:true` and abort. Sets all `qStatus` to `'pending'`, `activeId`=first, `source`=first.name, `runError:null`. Plays config-pane fly-out animation then calls `_runActive()`.
- `_runActive`: builds log `script` array (see §3), sets `{ run:'running', step:'process', progress:0, elapsed:0, pp:'idle', ppOut:'', chat:[], chatTyping:false, runError:null, source, qStatus[active]='running', log:[initial 2 lines] }`. Starts interval (`_t`, 420ms): `progress += 5..13`, `elapsed += 0.45`, pushes next script line (~85% chance/tick).
  - If filename matches `/skadad|corrupt/i` and `progress>=26` → stop, push ffmpeg error lines, `{ run:'error', runError:{title:'Kunde inte läsa ljudet', detail:'Filen "NAME" verkar skadad eller saknar ett giltigt ljudspår. Prova en annan fil, eller konvertera om den till WAV och försök igen.', where:'extract'}, qStatus[active]='error', qProgress[active]=pct }`.
  - At `progress>=100` → flush remaining script, push `'[klar] Färdig på MM:SS'`, `{ run:'done', qStatus[active]='done', qProgress[active]=100 }`, call `_archive(active, elapsed)`. If another `pending` exists → after 800ms set `run:'idle'`, advance `activeId`, `_runActive()` again. Else after 450ms `afterDone()`.
- `cancelRun` → stop interval, `{ run:'cancelled', qStatus[activeId]='pending' }`.
- `resumeRun` → `run:'idle'` then `_runActive()`.
- `retryRun` → `{ run:'idle', runError:null, progress:0, elapsed:0 }` then `_runActive()`.
- `_archive(file, secs)` → prepend a new `history` entry (dedupes same name+"Just nu"): `{ id:'h'+..., name, date:'Just nu', dur:fmtTime(secs), model, lang:('Engelska'|'Svenska'|'Auto'), formats:(SRT/TXT/VTT enabled, default ['TXT']), speakers: diarize?3:1, words: 2800+rand(0..500) }`.

### Post-process / chat (lines 1926-1985)
- `runPP`: guard if running. `{ pp:'running', ppPct:0 }`, interval (`_ppIv`, 130ms) `ppPct += 4..11`; at 100 → after 220ms `{ pp:'done', ppOut:ppText(), ppPct:100 }`.
- `togglePPEnabled` → flip `ppEnabled`; if turning on while `run==='done'` → if `ppOp==='chat'` `seedChat()` else `runPP()`.
- `afterDone()` (post-run): if `ppEnabled` → chat→`seedChat()` else `runPP()`.
- `seedChat` → if chat empty, seed assistant message: `'Transkriptet är klart. Fråga mig vad som helst — t.ex. "Vad var besluten?" eller "Sammanfatta på en mening."'`
- `onChatInput`/`onChatKey` (Enter sends).
- `sendChat`: require text or attachment. Push user message `{role:'user', text:q||'Titta på det bifogade.', attach:joinedLabels}`, clear input/attachments, `chatTyping:true`; after 950ms push assistant reply (`imageReply()` if any image attached, else `chatReply(q)`), `chatTyping:false`.
- `chatReply(q)` keyword matching (verbatim outputs below in §3).
- `ppText()` returns `summary`/`analyze` strings or, for `clean`, the joined transcript text (the clean path is actually rendered line-by-line, not via ppOut).
- Chat modal: `openChatModal`/`closeChatModal`, `stopProp`, `attachImage` (pushes `{kind:'image', label:'skärmbild-N.png'}`), `attachFile(fmt)` (pushes `{kind:'file', label:'dokument.EXT'}`), `removeAttach(i)`.

### Models download/install lifecycle (lines 1987-2055)
- `modelAction(id)`: if installed → `{ model:id, tab:'transcribe' }`; if downloading/installing → no-op; if `needGB > disk.free-3` → set `diskWarn`; else `_startDownload(id)`.
- `modelNeedGB(id)` = `ceil(parseFloat(size)*1.6)`.
- `diskWarnUseBest` → pick highest-free disk, `_startDownload`. `diskWarnCancel` → `diskWarn:null`.
- `_startDownload(id)`: `{ diskWarn:null, dlFailed[id]:false, downloading[id]:true, dlProg[id]:0 }`; interval (`_dl[id]`, 190ms) `+=5..14`; at 100 → seamlessly flip to `installing[id]:true, instProg[id]:0` and call `runInstallTimer(id)`.
- `runInstallTimer(id)`: interval (`_inst[id]`, 185ms) `instProg +=4..9`; at 100 → `{ installed[id]:true, installing[id]:false }`.
- `cancelDownload(id)` → clear both intervals, `{ downloading[id]:false, installing[id]:false, dlFailed[id]:true }`.
- `retryDownload(id)` → `dlFailed[id]:false` then `_startDownload(id)`.
- Detail text helpers: `dlDetail(size,pct)` = "X / Y GB · N MB/s"; `instDetail(pct)` = `'Packar upp filer…'` (<55), `'Verifierar kontrollsumma…'` (<90), `'Slutför…'` (≥90).

### Tooltips
- `showTip(e,text)` → `tip:{text, x, y}` positioned at element top-center. `hideTip` → `tip:null`. `infoBadge(text)` returns `{onEnter, onLeave}` handlers.

---

## 3. Mock / Demo Data Shapes

### `WHISPER` (lines 1504-1510) — transcription models
Shape: `{ id, size, vram, rtf, score, lang('sv'|'en'|'multi'), recommended?, useFor }`
1. `KB-Whisper large` — 3.1 GB, vram 4.7, rtf 4, score 5.5, sv, **recommended**, useFor: `'Svenska — bäst precision (KB-Labb). Körs även via easytranscriber'`
2. `Canary-Qwen-2.5B` — 5.0 GB, vram 6.5, rtf 9, score 5, en, `'Engelska — toppresultat, marginellt tyngre'`
3. `Whisper large-v3` — 3.1 GB, vram 4.7, rtf 4, score 4.5, multi, `'Flerspråkigt allround — robust på de flesta språk'`
4. `Canary 1B v2` — 2.0 GB, vram 3.2, rtf 13, score 4, multi, `'Flerspråkigt och snabbt — bra balans kvalitet/fart'`
5. `Parakeet TDT 0.6B v3` — 1.2 GB, vram 2.0, rtf 25, score 3.5, multi, `'Snabbast — realtid och stora batchar'`

### `LLM` (lines 1512-1519) — local language/vision models
Shape: `{ id, size, vram, toks, ctx, score, recommended?, uses[], modality?, useFor, caps:{vision, files[]} }`
1. `Qwen3 30B-A3B` — 18 GB, vram 17, 95 tok/s, ctx 256k, score 5.5, **recommended**, uses `['text','sv']`, useFor `'Textresonemang & svenska — MoE, snabb och stark vid 24 GB'`, caps `{vision:false, files:['PDF','TXT','Markdown','DOCX','CSV']}`
2. `Qwen3 32B` — 20 GB, vram 20, 22 tok/s, 128k, score 5.3, uses `['text','sv']`, `'Tätt resonemang — högsta kvalitet när tid finns'`, files `['PDF','TXT','Markdown','DOCX','CSV']`
3. `Gemma 3 27B` — 17 GB, vram 17, 28 tok/s, 128k, score 5, uses `['text','sv']`, `'Stark flerspråkig — verifiera svenska mot ScandEval'`, files `['PDF','TXT','Markdown','DOCX']`
4. `gpt-oss 20B` — 12 GB, vram 13, 70 tok/s, 128k, score 4.5, uses `['text']`, `'Lättare textmodell — snabb allround'`, files `['PDF','TXT','Markdown']`
5. `Qwen3-VL-30B-A3B` — 18 GB, vram 17, 90 tok/s, 256k, score 5.2, uses `['vision']`, modality `'Bildanalys'`, `'Videoanalys (bild) — MoE, snabb på bildrutor'`, vision true, files `['Bilder (PNG/JPG)','Video (MP4)','PDF','TXT']`
6. `Qwen3-VL-32B` — 21 GB, vram 20, 20 tok/s, 256k, score 5, uses `['vision']`, modality `'Bildanalys'`, `'Videoanalys (bild) — högsta visuella precisionen'`, vision true, files `['Bilder (PNG/JPG)','Video (MP4)','PDF','TXT']`
7. `Qwen3-VL-8B` — 5.5 GB, vram 6, 110 tok/s, 256k, score 4, uses `['vision']`, modality `'Bildanalys'`, `'Videoanalys (bild) — lättvikt, lämnar gott om VRAM över'`, vision true, files `['Bilder (PNG/JPG)','Video (MP4)','TXT']`
8. `Qwen3-Omni-30B-A3B` — 19 GB, vram 17, 85 tok/s, 64k, score 5, uses `['vision','omni']`, modality `'Bild + tal'`, `'Videoanalys (bild + tal) — ser bild och hör ljud i ett'`, vision true, files `['Bilder (PNG/JPG)','Video (MP4)','Ljud (WAV/MP3)','TXT']`

### `ONLINE` (lines 1561-1566) — online/installable extra models
Shape: `{ id, size, tag, uses[] }`
1. `deepseek-r1:8b` — 4.9 GB, `'Resonemang'`, uses `['reason','code']`
2. `phi4:14b` — 9.1 GB, `'Kompakt, kraftfull'`, uses `['reason','chat','code']`
3. `command-r:35b` — 20 GB, `'Lång kontext'`, uses `['rag','chat']`
4. `nemotron-mini` — 2.7 GB, `'Lättviktig'`, uses `['speed','chat']`

### Quantization ladders
- `LQUANTS` (1522-1529): `{id,label,mult,sweet?,note}` — Q2_K(0.58), Q3_K_M(0.78), Q4_K_M(1.00, sweet), Q5_K_M(1.18), Q6_K(1.38), Q8_0(1.80). (Swedish notes verbatim in source.)
- `WQUANTS` (1530-1533): int8(0.62), fp16(1.00, sweet).
- `pickQuant` picks highest quality fitting `HW.vram.free` with 1.2 GB margin.

### `HW` (1567-1577) — hardware
`{ gpu:'RTX 4090', arch:'Ada Lovelace', cc:'8.9', cuda:'12.4', precisions:'fp16 · int8 · int4', cpu:'Ryzen 9 7900X · 12 kärnor', vram:{total:24, free:22.5}, ram:{total:64, free:52}, disks:[ {id:'c',drive:'C:',name:'System · NVMe SSD',total:512,free:11}, {id:'d',drive:'D:',name:'Lagring · NVMe SSD',total:2048,free:1640}, {id:'x',drive:'X:',name:'Extern · USB-C SSD',total:4096,free:3720} ] }`

### `STEPS` (1617) — process step labels
`['Förbereder', 'Extraherar ljud', 'Transkriberar', 'Färdigställer']`

### `SPEAKERS` (1618) / colors
`['Talare 1', 'Talare 2', 'Talare 3']`. `speakerColor(i)` hues `[264,150,52]` (oklch). `speakerWeak(i)` lighter variant.

### `TRANSCRIPT` (1624-1644) — 19 demo lines
Shape: `{ time, spk(0-2), text }`. `AUDIO_DUR=150`. Verbatim lines (time · speaker · text):
- 00:00 · 0 · `Hej och välkomna till veckans avsnitt av vårt uppföljningsmöte.`
- 00:06 · 0 · `Idag fortsätter vi på det vi pratade om förra veckan.`
- 00:13 · 1 · `Precis, och då blir nästa steg att fördela ansvaret mellan oss.`
- 00:21 · 0 · `Jag tänkte att vi börjar med att gå igenom tidsplanen tillsammans.`
- 00:28 · 1 · `Bra idé. Vi ligger ungefär två dagar efter den ursprungliga planen.`
- 00:36 · 0 · `Det är hanterbart om vi prioriterar rätt saker den här veckan.`
- 00:44 · 1 · `Håller med. Vad ser ni som det viktigaste att bli klar med först?`
- 00:52 · 2 · `Transkriberingsflödet behöver testas ordentligt innan release.`
- 01:01 · 2 · `Och vi måste bekräfta att modellerna fungerar på all hårdvara.`
- 01:10 · 1 · `Jag tar ansvar för testningen och återkommer med besked på fredag.`
- 01:18 · 0 · `Perfekt. Då tar jag dokumentationen och release-noterna.`
- 01:27 · 2 · `Ska vi boka ett kort avstämningsmöte i mitten av veckan?`
- 01:34 · 0 · `Ja, låt oss säga onsdag klockan tio — ett kvarts möte räcker.`
- 01:42 · 2 · `Låter bra. Då skickar jag en kalenderinbjudan direkt efter mötet.`
- 01:50 · 0 · `Finns det något annat vi behöver ta upp innan vi avslutar?`
- 01:57 · 1 · `Bara en sak — vi bör informera supportteamet om ändringarna.`
- 02:05 · 2 · `Sant, jag lägger till det i mina anteckningar och hör av mig.`
- 02:13 · 0 · `Då tror jag vi är klara för idag. Tack för ett bra möte allihop.`
- 02:20 · 1 · `Tack själv, och tack för att ni lyssnade — vi hörs nästa vecka.`

### `history` seed (1252-1256)
Shape: `{ id, name, date, dur, model, lang, formats[], speakers, words }`
1. `h1` · `styrgruppsmöte_q1.mp3` · `Idag · 09:14` · 18:42 · KB-Whisper large · Svenska · [SRT,TXT] · 3 talare · 2940 ord
2. `h2` · `kundintervju_03.wav` · `Igår · 16:30` · 42:11 · KB-Whisper large · Svenska · [TXT] · 2 · 6810
3. `h3` · `webinar_inspelning.mp4` · `12 jun` · 01:03:20 · Whisper large-v3 · Flerspråkig · [SRT,VTT,TXT] · 1 · 9120

### Run log `script` (built per-run, 1863-1876) — verbatim
Initial two lines pushed at start: `'› transkribera "BASE" --model MODEL[ --diarize pyannote][ --num-speakers N]'` and `'[00:00] Laddar modell MODEL …'`. Then script array:
```
[00:01] GPU: RTX 4090 · CUDA 12.4
[00:02] Extraherar ljudspår (ffmpeg) …
[00:04] Ljud: 24:18, 16 kHz mono
[00:05] VAD: 142 talsegment funna
[00:06] Diarisering (pyannote): separerar röster[, antal talare = N]      ← only if diarize
[00:07] Diarisering: 3 talare funna[ → märkta NAMES]                       ← only if diarize
[00:08] Segment   1/142  ›  "Hej och välkomna till …"
[00:12] Segment  38/142  ›  "… det vi pratade om förra veckan"
[00:17] Segment  77/142  ›  "Precis, och då blir nästa steg …"
[00:22] Segment 119/142  ›  "Tack för att ni lyssnade."
[00:24] Sammanfogar segment …
[00:25] Skriver utdata-filer …
```
End line: `'[klar] Färdig på MM:SS'`. Corrupt-file error lines: `'[00:04] Extraherar ljudspår (ffmpeg) …'`, `'[fel] ffmpeg: invalid data — kunde inte läsa ström 0:1'`.

### Post-process outputs (`ppText`, 1980-1985) — verbatim
- `summary`: `'Samtalet inleds med en återkoppling till föregående veckas diskussion och övergår sedan till nästa steg i projektet. Deltagarna är överens om tidsplanen och fördelar ansvaret för de kommande uppgifterna. Avsnittet avslutas med en kort sammanfattning och tack till lyssnarna.'`
- `analyze`: `'Teman:  projektuppföljning · ansvarsfördelning · tidsplan\nTon:  konstruktiv och samstämmig\n\nÅtgärdspunkter\n•  Fördela ansvaret inför nästa steg\n•  Bekräfta tidsplanen\n•  Boka nästa möte'`
- `clean`: joined transcript text (rendered line-by-line instead).

### Chat replies (`chatReply`, 1972-1979) — verbatim, keyword-matched
- `/beslut|ansvar|åtgärd/` → `'Det viktigaste beslutet var att fördela ansvaret inför nästa steg — det kommer upp kring 00:13 i transkriptet.'`
- `/sammanfatt|en mening|kort/` → `'Ett kort uppföljningsmöte där teamet stämde av förra veckans punkter och enades om tidsplan och ansvarsfördelning.'`
- `/ton|känsla|stämning/` → `'Tonen är konstruktiv och samstämmig — deltagarna är överens och avslutar positivt.'`
- `/tid|plan|möte|när/` → `'De bekräftar tidsplanen och nämner att nästa möte bokas inom kort.'`
- default → `'Utifrån transkriptet: de återkopplar till förra veckan (00:06), fördelar ansvaret (00:13) och avslutar med tack (00:21). Vill du att jag fördjupar någon del?'`
- `imageReply()` → `'Jag ser bilden. Den verkar visa en skärmdump kopplad till mötet — vill du att jag beskriver innehållet, läser av text i den (OCR) eller jämför den mot transkriptet?'`

### Post-process op definitions `OPS` (2269-2273)
`[['clean','Korrekturläs','Rättar stavfel & småfel — skriver inte om'], ['summary','Summera','Korta ner till det viktiga'], ['chat','Chatta','Ställ frågor om innehållet']]`. `ppOutTitles = { summary:'Sammanfattning', clean:'Korrekturläst text', analyze:'Analys' }`.

### Other label sets
- Languages (2156): `[['','Auto'],['sv','Svenska'],['en','Engelska']]`.
- Formats (2160): `['srt','txt','vtt']` → uppercase chips.
- Online sort (2260): `[['fit','Passar din dator'],['size','Storlek']]`.
- Use-cases `USECASES` (2263): `[['all','Alla'],['text','Textresonemang'],['sv','Svensk text'],['vision','Videoanalys · bild'],['omni','Videoanalys · bild + tal']]`.
- Num-speaker options (2444): `['auto','2','3','4','5','6']` (Auto label for `'auto'`).
- Step defs (2185): `[['source','Källa'],['config','Inställningar'],['process','Resultat']]`; order `['source','config','process']`.
- Queue status words (2373): `{pending:'Väntar', running:'Kör', done:'Klar', error:'Fel'}` with colors `{pending:var(--ink-3), running:var(--accent), done:var(--ok), error:var(--bad)}`.
- Result file meta (2177): `{srt:['SRT','38 KB'], txt:['TXT','21 KB'], vtt:['VTT','40 KB']}`.
- Fit-text helpers: `fitText`→ ok=`'Passar din hårdvara'`, warn=`'Tungt för din hårdvara'`, bad=`'För stort för din hårdvara'`.

---

## 4. Tab / Step / Screen-State Derivations (from `renderVals`, 2406-2607)

### Tabs
- `tabTranscribe = tab === 'transcribe'`
- `tabModels = tab === 'models'`
- `tabHistory = tab === 'history'`

### Transcribe-tab wizard steps
- `stepSource = step === 'source'`
- `stepConfig = step === 'config'`
- `stepProcess = step === 'process'`
- `stepItems` derives done/active/todo from `stepOrder.indexOf(step)`.

### Source/queue derivations
- `hasSource = !!source.trim()`, `noSource = !hasSource`
- `hasQueue = queue.length > 0`, `multiQueue = queue.length > 1`, `queueCount`, `queueDoneCount = count(qStatus==='done')`, `queueSummary = 'N av M klara'`
- `hasFileError = !!fileError`
- per-item: `isActive = id===activeId && step==='process'`; `canRemove = step !== 'process'`; `showBar = status==='running'||'done'`.

### Empty/installed model gating
- `noWhisper = !WHISPER.some(m => installed[m.id])`, `hasWhisper = !noWhisper` (drives the "no model installed" empty state on transcribe tab).

### Run/process state
- `isRunning = run === 'running'`, `notRunning = !isRunning`
- `isDone = run === 'done'`
- `isError = run === 'error'`, `isCancelled = run === 'cancelled'`, `notErrorState = run !== 'error' && run !== 'cancelled'`
- `showStatus = step === 'process'`
- `showResults = isDone`, `showPP = isDone`
- `statusBadge`: error→`'FEL'`, cancelled→`'AVBRUTEN'`, done→`'KLAR'`, else `'KÖR'` (with matching color: bad/ink-3/ok/accent).
- `startBtnLabel`: running→`'Transkriberar…'`, done→`'Kör igen'`, queue>1→`'Starta · N filer'`, else `'Starta'`.
- Step progress index `cur` (2138): `isDone? 4 : progress<12?0 : <28?1 : <92?2 : 3`.
- `logClipped = logRows.length > 3`.

### Post-process derivations
- `ppOff = !ppEnabled`
- `ppShowRun = ppOp !== 'chat'`
- `ppShowChat = ppOp === 'chat'`
- `ppShowText = ppOp !== 'chat' && pp !== 'idle'`
- `ppRunning = pp === 'running'`, `ppRunIdle = pp !== 'running'`
- `ppShowOut = pp === 'done'`
- `ppTextDone = pp === 'done' && ppOp !== 'clean'`
- `ppCleanDone = pp === 'done' && ppOp === 'clean'`
- `ppDDOpen = openDD === 'ppmodel'`

### Diarization derivations
- `diaInstallPrompt = state.diaInstallPrompt && !pyInstalled`
- `pyInstalled`, `diaPromptBusy = !!(pyDl||pyIng)`, `diaPromptIdle = !busy`
- `diaPhase`: downloading/installing/failed/installed/idle (from pyannote download/install maps)
- `canAddSpeaker = spkNames.length < 6`, per-row `canRemove = spkNames.length > 1`.
- `showSpeakers`: when viewing history → `viewingHist.speakers > 1`; else `diarize`.

### Transcript viewer derivations
- `viewingHist = histViewing ? history.find(...) : null`
- `transcriptFileName = viewingHist ? viewingHist.name : baseName()+'.txt'`
- `curLine`: highest transcript index with `parseTS(time) <= audioT`
- per-line `isCurrent = idx===curLine && (audioPlaying || audioT>0)`
- `showSpk` toggled only when speaker changes from previous line
- search: builds highlighted `segments` (plain/match/current), `matchLabel = (currentMatch+1)+'/'+total` or `'0/0'`
- `editing`/`notEditing`, `editBtnLabel = editing?'✓ Klar':'Redigera'`, `transcriptEdited = edited`
- waveform: `_wave` 72 bars; `aPct = audioT/150*100`; bars before playhead use `--accent`.

### Modal open flags
- `confirmOpen = !!confirm`, `diskWarnOpen = !!diskWarn`, `chatModalOpen`, `logOpen`, `transcriptOpen`, `tipOpen = !!tip`, `anyDDOpen = openDD !== null`.
- Dropdown opens: `modelDDOpen = openDD==='model'`, `diskDDOpen = openDD==='disk'`, `chatModelDDOpen = openDD==='chatmodel'`.

### Models tab derivations
- `whisperRows` = `rankModels(WHISPER,'whisper')`, each with `phase` ∈ downloading/installing/failed/installed/idle, `pct`, `detail`, `verdict`, `chips`, `removable`/`notRemovable`.
- `llmRows` = filtered by `useCase` then ranked; `disabled = fit.tier==='bad'` → phase `'incompatible'`; `llmEmpty` when none.
- `onlineRows` = `ONLINE` filtered by useCase + search query (matches id/tag/size/fit-word) and sorted by `onlineSort`; `onlineEmpty` when none.
- Chat-modal adapts to selected model `caps`: `chatHasVision`/`chatNoVision`, `chatKind` (`'bild + tal'`/`'bildanalys'`/`'textmodell'`), `chatFileChips` from `caps.files`, `chatCaps` chips.

---

## 5. Timers / Intervals (to recreate)

| Timer | Field | Interval | Per-tick | Termination |
|---|---|---|---|---|
| Transcription run | `_t` | 420ms | `progress += 5..13`, `elapsed += 0.45`, push ~1 log line (85% chance) | At 100 → done + archive + advance queue; corrupt file at ≥26 → error |
| Post-process | `_ppIv` | 130ms | `ppPct += 4..11` | At 100 → 220ms later `pp:'done'` |
| Post-process finalize | `_pp` | 220ms timeout | sets `pp:'done'`, `ppOut` | one-shot |
| Chat reply | `_chat` | 950ms timeout | appends assistant message | one-shot |
| Audio playhead | `_au` | 200ms | `audioT += 0.2` | At `AUDIO_DUR`=150 → stop |
| Per-model download | `_dl[id]` | 190ms | `dlProg += 5..14` | At 100 → start install timer |
| Per-model install | `_inst[id]` | 185ms | `instProg += 4..9` | At 100 → `installed[id]=true` |
| Download toast | `_toastIv` | 140ms | `toast.pct += 11..28` | At 100 → `done:true`, auto-clear after 2600ms (`_toastT2`) |

`start()` also schedules a 360-460ms config-pane exit animation before `_runActive()`. Queue advance uses an 800ms delay between files; `afterDone()` fires 450ms after the last file completes. All timers cleared in `componentWillUnmount` and `restart`.

---

## 6. Notes for the real implementation
- The component is React-class-shaped: replicate with a single `state` object + a `setState`/`render` cycle (or a small reactive store). Every binding the HTML template uses comes from the `renderVals()` return object (lines 2406-2607) — that object is effectively the view-model contract.
- `componentDidUpdate` side effects to reproduce: theme sync to `data-theme`, focus search input on transcript open, auto-scroll current match into view, smooth-scroll/reveal animations on `run==='done'` / post-process transitions / new chat messages, populating contenteditable transcript lines on entering edit mode, and the pyannote-installed→auto-enable-diarize transition.
- Source file: `C:\Users\bolun\Downloads\_design_handoff_extract\omdesign-till-minimalistisk-ui\project\Transkribera.dc.html` (state machine in lines 1189-2609; initial state 1191-1261; actions 1453-2055; mock data 1504-1644 + 1252-1256; derivations/view-model 2134-2607).