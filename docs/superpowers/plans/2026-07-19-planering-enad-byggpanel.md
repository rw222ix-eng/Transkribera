# Planering enad byggpanel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** En byggpanel i Planering med typväljare Tavla|Prov|Arbetsblad, delade fältvärden, en gemensam ändringschatt och klickbar elementmarkering som styr ändringarna.

**Architecture:** Backend-stackarna behålls (`/api/planning/*` för tavla, `/api/exams/*` för prov/arbetsblad). Enandet sker i `app/web/static/app.js` (vanilla JS, morphdom): delade state-nycklar för gemensamma fält, `byggTyp` styr fält/CTA/resultatkort, en chattkomponent som ruttar till rätt refine-endpoint, selektionsprimitiv i exam-kortet (uppgiftsnummer) och i `WBHost` (sektionsindex).

**Tech Stack:** Vanilla JS + morphdom, FastAPI, pytest, Playwright e2e (fake-läge), `node --check`.

## Global Constraints

- Svenska i alla UI-strängar.
- DESIGN.md: `data-seg`-segment, chips (sky-wash vald), EN solid CTA per skärm, skarpa hörn, inga nested cards.
- Inga schemaändringar, inga nya beroenden.
- `python -m pytest` grönt + `node --check app/web/static/app.js` efter varje task; commit + push per task (Conventional Commits, svenska).
- WBHost-namnrymden i board-dokumentet är obligatorisk.
- Spec: `docs/superpowers/specs/2026-07-19-planering-enad-byggpanel-design.md`.

---

### Task 1: Delade fältvärden + typväljare

**Files:**
- Modify: `app/web/static/app.js` (state ~156-221, logik 609-1306, VM 3360-3548, render 5605-5995)
- Test: `node --check`, pytest (oförändrat grönt), Playwright fake-läge

**Interfaces (Produces):**
- State: `byggTyp: 'tavla'|'prov'|'arbetsblad'` (default `'tavla'`), delade `byggCourseId`, `byggGroupId`, `byggDatum`, `byggUnderlag`, `byggUnderlagBusy` (ersätter `planCourseId`/`exCourseId`, `planGroupId`/`exGroupId`, `planDatum`/`exDatum`, `planUnderlag`/`exUnderlag` + busy).
- `byggPickTyp(t)` sätter `byggTyp` (ersätter `exPickTyp`); exam-payloadens `typ` härleds: `byggTyp === 'arbetsblad' ? 'arbetsblad' : 'prov'`.

**Steps:**
- [ ] Döp om till delade nycklar överallt (grep på gamla namnen; generate-payloads, content-status-laddning, VM:er).
- [ ] Rendera EN byggpanel i `viewPlanning`: segment `Tavla|Prov|Arbetsblad` överst (samma `data-seg`-mönster som exTyp-segmentet), därunder delade fält (kurschips, klasschips, datum, underlag), därunder typspecifika fält — tavla: moment + starttid; prov: innehåll, antal, tid, Del B/C, referens; arbetsblad: innehåll, antal, referens (ingen tid, inga delar; tid skickas ändå med default i payloaden så backend är oförändrad).
- [ ] En CTA: "Skriv tavlan"/"Skriv provet"/"Skriv arbetsbladet" efter typ; ruttar till `startPlanGenerate()` resp. `startExamGenerate()`.
- [ ] Resultatkorten: tavelkortet visas för `byggTyp==='tavla'`, provkortet för prov/arbetsblad (arkivöppning får sätta `byggTyp` till rätt typ).
- [ ] Kör `node --check app/web/static/app.js` → OK; `python -m pytest -q` → grönt; verifiera i förhandsvisningen (typväxling behåller kurs/klass).
- [ ] Commit + push: `feat(planering): en byggpanel med typväljare och delade fält`

### Task 2: Gemensam ändringschatt

**Files:**
- Modify: `app/web/static/app.js` (sendPlanRefine/sendExamRefine/exChat/render av chattbarer)

**Interfaces:**
- Consumes: `byggTyp` från Task 1.
- Produces: `byggChatInput` (ersätter `planChatInput` och per-uppgift `exChat`), `sendByggChat()` som ruttar: `byggTyp==='tavla' && S.planId` → POST `/api/planning/{planId}/refine` `{message}`; annars `S.exam` → POST `/api/exams/{id}/refine` `{message, nummer?}`.

**Steps:**
- [ ] Inför `byggChatInput` + `sendByggChat()`; en chattbar under det aktiva resultatkortet (behåll bara EN tavelchatt — ta bort dubbletten; zoomvyn behåller sin).
- [ ] Ta bort per-uppgift-chattarna: state `exChat`, `onExChat`, `sendExamRefine(nummer)`-bindningen per kort och renderingen av fälten (refine-funktionen behålls, anropas från `sendByggChat`).
- [ ] `node --check` + pytest + förhandsvisning (chatt når rätt endpoint för tavla resp. prov).
- [ ] Commit + push: `feat(planering): gemensam ändringschatt för tavla, prov och arbetsblad`

### Task 3: Elementmarkering — prov/arbetsblad

**Files:**
- Modify: `app/web/static/app.js` (exam-kortets uppgiftsrender + chattbaren)

**Interfaces:**
- Produces: `byggSel: [{kind:'uppgift', nummer}]`, `toggleByggSel(sel)`, chips-rad ovanför chatten med ×, `clearByggSel()`. Vid skick: exakt en vald uppgift → `nummer` i refine-payloaden (befintlig scoping); flera → prefix i meddelandet: `[Gäller uppgift 3 och 5] <text>`; efter lyckat skick rensas valet.

**Steps:**
- [ ] Klick på uppgiftskort togglar markering (ram i markörfärg via style, `aria-pressed`).
- [ ] Chips + skick-logik enligt Interfaces; markeringar rensas när nytt resultat genereras.
- [ ] `node --check` + pytest + förhandsvisning.
- [ ] Commit + push: `feat(planering): markera uppgifter som mål för chattändringar`

### Task 4: Elementmarkering — tavla (WBHost)

**Files:**
- Modify: `app/web/static/whiteboard/board.js` (WBHost), ev. `layout.js` (sektionsnoder), `app/web/static/app.js`
- Test: `tests/test_lesson_board.py`/`tests/test_whiteboard_spec.py` om spec berörs (annars e2e)

**Interfaces:**
- Produces: `WBHost.setSelectMode(on, cb)` — i selektionsläge taggas varje sektionsrotnod `data-wbsec="<index>"`; klick togglar visuell markering (outline i markörfärg) och anropar `cb({index, label, selected})` där `label` är sektionens rubrik/typ ur specen. `WBHost.clearSelection()`. Val överlever inte om boarden renderas om.
- `app.js`: `byggSel` får `{kind:'sektion', index, label}`; refine-meddelandet prefixas `[Gäller sektion 2: Exempel — …] <text>`.

**Steps:**
- [ ] Undersök hur `WBLayout.renderWhiteboard` strukturerar sektioner; tagga rotnoder med index + label vid render.
- [ ] Implementera `setSelectMode`/`clearSelection` + klickhantering i board.js (iframe), koppla i app.js (aktiveras när tavelresultat visas), chips som i Task 3.
- [ ] `node --check` båda filerna + pytest + skarp förhandsvisning (markera sektion, skicka ändring, sektionen ändras).
- [ ] Commit + push: `feat(planering): markera tavelsektioner som mål för chattändringar`

### Task 5: Helhetsverifiering

- [ ] Skarpt flöde i appen: bygg tavla → markera sektion → chatta ändring; byt till prov → fälten växlar, kurs/klass kvarstår → generera → markera uppgift → chatta ändring; arbetsblad utan tid/delar-fält.
- [ ] Playwright fake-läge för regressionerna ovan där det går utan GPU.
- [ ] DESIGN.md-koll: en solid CTA, chips-mönster, inga nya kortnästlingar.
- [ ] Commit + push av ev. justeringar.

## Self-review

- Speckrav → tasks: typväljare/fält (1), CTA (1), gemensam chatt + borttagna per-uppgift-fält (2), markering prov (3), markering tavla (4), verifiering (5). Inga luckor.
- Inga placeholders; signaturer konsekventa (`byggSel`, `sendByggChat`, `WBHost.setSelectMode`).
- Omfångskoll: ett sammanhängande UI-arbete i en fil + board.js; en plan räcker.
