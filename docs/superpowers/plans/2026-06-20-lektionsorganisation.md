# Transkribera — Lektionsorganisation — Implementationsplan

**Datum:** 2026-06-20
**Status:** Förslag — inväntar godkännande
**Spec:** `docs/superpowers/specs/2026-06-20-lektionsorganisation-design.md`

Varje fas är en egen, mergebar PR med gröna tester. Faserna är ordnade så att varje PR ger värde
för sig och inte kräver senare faser. **Förutsättning:** PR #6 (output_store/daterade mappar) landad.

---

## Fas 0 — Förberedelse (ingen ny funktion)
- [~] PR #6 ej mergad ännu — Fas 1 bygger på `media.parent` som `transcript_folder` tills vidare;
      byt till `output_store`-mappen när #6 landar.
- [x] Lägg `transkribera.db` (+ `-wal`/`-shm`) i `.gitignore` (bredvid `history.json`).

## Fas 1 — Datamodell + Lektioner-tab  *(fundamentet)* — KLAR
**Mål:** organisera transkript per datum/klass/kurs; filtrera.
- [x] `app/db.py`: `sqlite3`-anslutning (WAL, FK), `user_version`-schema, schema enligt spec.
- [x] **Engångsmigrering** av `history.json` → `lessons` vid start (idempotent på `history_id`; JSON kvar).
- [x] CRUD-funktioner: courses, groups, lessons, insights (GUI-oberoende, testbara).
- [x] `server.py`: `GET/PATCH/DELETE /api/lessons`, `GET /api/lessons/{id}`,
      `GET/POST /api/courses`, `GET/POST /api/groups`.
- [x] `/api/transcribe` `done` speglar resultatet till en `lesson` (best-effort; bryter aldrig transkribering).
- [x] Frontend: ny **Lektioner-flik** — lista per datum, filter (klass/kurs via `<select>`),
      inline-tilldelning av klass/kurs/sal/datum (PATCH med get-or-create), öppna/ta bort.
      Lades till **vid sidan av** Historik (utökar, inte ersätter) för att hålla risken låg.
- [x] Tester: `test_db.py` (9, schema/migrering/CRUD/filter), `test_web_server.py` (+7 endpoint-tester).

**Status:** `python -m pytest` → 117 passerar (enda röda `test_hardware` är den kända hårdvaru-/RAM-lösa
container-bristen, faller även på ren `main`). `node --check app.js` grön.

**Återstår live-verifiering (GPU-lös container):** transkribera en fil → posten dyker upp i Lektioner →
tilldela klass/kurs/sal/datum → filtrera → ladda om appen och se att tilldelningen kvarstår.

## Fas 2 — LLM-extraktion av insikter — KLAR
**Mål:** plocka ut kalender/svårigheter/åtgärder/grupprum/material som redigerbara kort.
- [x] `postprocess.py`: `extract()` med JSON-schema-tvingad output (`EXTRACT_RESPONSE_FORMAT`),
      robust parsning (giltig JSON → first-`{...}`-block → tom struktur), ett LLM-pass över hela transkriptet.
- [x] `llm_client.generate`/`_stream_chat`: vidarebefordrar `response_format` till llama.cpp.
- [x] Svensk systemprompt: hellre utelämna än hitta på; initialer/plats i stället för namn.
- [x] `server.py`: `POST /api/lessons/{id}/extract` (SSE, under GPU-arbitern, ersätter tidigare
      `source='llm'` men behåller manuella), `GET/POST /api/lessons/{id}/insights`,
      `PATCH/DELETE /api/insights/{id}`. `db.py`: `update_insight`, `delete_insights_by_source`, `get_insight`.
- [x] Frontend: utfällbar **Insikter**-panel per lektion — "Analysera lektion"-knapp, kort grupperade
      per typ med AI-märke, klar/öppen-toggle, redigera/radera, samt manuell tilläggsrad.
- [x] Tester: `test_postprocess.py` (+4: schema skickas, parsning, tomt/skräp), `test_web_server.py`
      (+7: extract skriver/ersätter, behåller manuella, 400/409, manuell CRUD, patch 404).

**Status:** `python -m pytest` → 128 passerar (enda röda `test_hardware`, känd container-brist). `node --check` grön.

**Återstår live-verifiering (GPU-lös container):** kör "Analysera lektion" på en riktig lektion → rimliga
svenska insikter i rätt kategorier, ingen engelsk/JSON-läcka, omkörning ersätter AI-korten men behåller
manuella, och redigering/klarmarkering kvarstår efter omladdning.

## Fas 3 — Nästa lektion-vy (carry-forward) — KLAR
**Mål:** vid lektionsstart se öppna åtgärder + förra lektionens svårigheter för klassen.
- [x] `db.py`: `next_prep(group_id)` — öppna `åtgärd/grupprum/material` över klassens alla lektioner
      + **senaste** lektionens svårigheter (med lektionskontext); läcker inte mellan klasser.
- [x] `server.py`: `GET /api/next-prep?group_id=` (prep är per klass, inte per lektion).
- [x] Frontend: prep-panel högst upp i Lektioner-fliken som visas när man **filtrerar på en klass**;
      bocka av åtgärd → `status='klar'` (panel + insiktscache uppdateras). Refreshas även efter
      analys/radering/statusändring.
- [x] Tester: `test_db.py` (+3: carry-forward öppna vs klara/rätt klass/senaste lektionen, update_insight,
      tom grupp), `test_web_server.py` (+1: `/api/next-prep` end-to-end).

**Status:** `python -m pytest` → 132 passerar (enda röda `test_hardware`, känd container-brist). `node --check` grön.

**Återstår live-verifiering:** välj en klass i Lektioner → panelen "Inför nästa lektion" listar öppna
åtgärder + förra lektionens svårigheter; bocka av en åtgärd → försvinner och kvarstår borta efter omladdning.

## Fas 4 — Inbyggd inspelning — KLAR
**Mål:** spela in lektionen direkt i appen.
- [x] `server.py`: `POST /api/upload?name=` sparar rå body (Blob) i `downloads/` (ingen
      multipart-dep), plattar ut filnamn (ingen directory-traversal) → returnerar `{path, name}`.
- [x] Frontend: `MediaRecorder` (endast ljud), löpande tid, tydlig "spelar in"-indikator,
      Stoppa & lägg till / Avbryt → laddar upp och matar in i **samma** transkriberingskö som filer/länkar.
      Graciös degradering när mikrofon/`MediaRecorder` saknas (knapp inaktiverad + förklaring).
- [~] Lång inspelning: nuvarande flöde duger; Parakeet-chunkning (PR #5-spåret) kvarstår som
      framtida hårdning vid minnesbrist.
- [x] Tester: `test_web_server.py` (+3: sparar, avvisar tomt, plattar ut `../`).

**Status:** `python -m pytest` → 135 passerar (enda röda `test_hardware`, känd container-brist). `node --check` grön.

**Återstår live-verifiering:** tillåt mikrofon → starta/stoppa inspelning → posten hamnar i kön och
kan transkriberas; webm/opus avkodas av Whisper-flödet.

> **Notering:** GDPR/samtycke/gallring hanteras utanför appen och ingår inte i planen.

---

## Senare (egen plan vid behov)
- Tagga svårigheter mot centralt innehåll/kunskapskrav + terminstrender.
- Fritextsök över transkript + insikter.
- LLM-genererat lektionsförslag inför nästa pass.
- Grupprumsrotation utifrån tidigare placering.

## Verifiering (live, RTX 4090 / Windows)
Som övriga GPU-beroende PR:er byggs/testas detta i container med mockad LLM/GPU. Live-verifiering
krävs för: extraktionens JSON-kvalitet på riktigt klassrumsljud och inspelning end-to-end. Skriv
verifieringsnoteringar i `docs/superpowers/notes/` per fas.
