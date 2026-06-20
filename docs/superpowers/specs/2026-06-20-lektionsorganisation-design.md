# Transkribera — Lektionsorganisation & pedagogisk kunskapsbas — Design

**Datum:** 2026-06-20
**Status:** Förslag — inväntar godkännande
**Bygger på:**
- `2026-06-16-transkribera-backend-core-loop-design.md` (kärnloopen, historik-shape)
- PR #6 `app/output_store.py` + `app/media.py` (daterade resultatmappar under `Transkriberingar/`, säker radering) — **lagringsfundamentet detta vilar på**
- `2026-06-19-llamacpp-long-context-design.md` (Qwen3-14B, 40k kontext — hela lektioner ryms i ett LLM-pass)

## Vision (från användaren)

Spela in egna mattelektioner (med samtycke) → transkribera → använd transkriptet för att
(1) minnas vad som hände, (2) plocka ut **kalenderposter**, och (3) inför nästa lektion med
samma klass minnas **vad eleverna hade svårt för**, **åtgärder** (vilka som satt i grupprum,
"sluta tidigare nästa gång"), och **önskat material** (arbetsblad m.m.). Allt organiserat per
**datum, klass och kurs** som en personlig databas för egen utveckling.

## Mål

Utveckla Transkribera från en generisk transkriberare till en **lärarens kunskapsbas**:
1. Knyt varje transkribering till en **lektion** (datum, klass, kurs, sal).
2. Kör en **LLM-extraktion** som plockar ut strukturerade insikter (kalender/svårighet/åtgärd/grupprum/material) — granskningsbara, redigerbara, aldrig auto-sanning.
3. En **Nästa lektion-vy** per klass som lyfter fram öppna åtgärder + förra lektionens svårigheter (carry-forward).
4. **Inbyggd inspelning** i appen så hela flödet sker på ett ställe.

> **Notering:** GDPR/samtycke/gallring hanteras **utanför appen** och ingår inte i den här designen.

## Designprinciper

- **Lokalt/offline.** Allt stannar på maskinen, precis som idag — ingen molntjänst, samma
  arkitektur som resten av Transkribera. (Supabase/Google Calendar finns i miljön men används inte.)
- **Människa i loopen.** Klassrumsljud är stökigt; LLM-extraktion gissar fel. Insikter visas som
  **redigerbara kort** läraren bekräftar — verktyget föreslår, läraren beslutar.
- **Inga nya tunga beroenden.** Persistens via `sqlite3` (Python-standardbiblioteket). Inspelning
  via webbläsarens `MediaRecorder`. Återanvänd `postprocess`/`llm_client`/`output_store`.
- **Bakåtkompatibelt.** Befintlig `history.json` migreras in i DB:n vid första start; gammalt UI-flöde fortsätter fungera.

## Känd begränsning: diarisering är borttagen

Talarseparation togs bort i commit `9deda13`. Appen kan alltså **inte** själv avgöra *vem* som
talar. Konsekvens för "vilken elev frågade":
- Svårigheter och frågor fångas på **gruppnivå** (ämne/uppgift/frågetyp), inte per namngiven elev,
  om inte namnet sägs högt i ljudet.
- `insights.ref` är ett **fritt** fält (uppgift/ämne/initialer/plats/grupp) som läraren fyller i — inte
  något LLM:en påstår säkert.

## Datamodell (SQLite — ny `app/db.py`)

En fil `transkribera.db` bredvid exe:n (samma plats som `history.json` idag). `sqlite3`, WAL-läge,
enkel migrerings-tabell (`schema_version`).

```sql
courses  (id INTEGER PK, namn TEXT UNIQUE)              -- "Matematik 2b", "Matematik 3c"
groups   (id INTEGER PK, namn TEXT UNIQUE)              -- klassen/gruppen, t.ex. "NA21"
lessons  (id INTEGER PK,
          datum TEXT,            -- ISO-datum, auto från inspelning, redigerbart
          starttid TEXT,         -- valfritt
          group_id INTEGER FK,   -- klass
          course_id INTEGER FK,  -- kurs
          sal TEXT,
          transcript_folder TEXT,-- pekar på output_store-mappen (PR #6) / resultatfilernas mapp
          recording_path TEXT,
          summary TEXT,          -- LLM-sammanfattning (postprocess 'summary')
          created_at TEXT)
insights (id INTEGER PK,
          lesson_id INTEGER FK,
          typ TEXT,              -- 'kalender' | 'svårighet' | 'åtgärd' | 'grupprum' | 'material' | 'övrigt'
          text TEXT,
          due_date TEXT,         -- för 'kalender'/'åtgärd', valfritt
          ref TEXT,              -- fritt: uppgift/ämne/initialer/plats — aldrig LLM-påstått namn
          status TEXT,           -- 'öppen' | 'klar' (driver carry-forward)
          source TEXT)           -- 'llm' | 'manuell' (spårbarhet — vad kom från extraktion)
```

History-posten (PR #6:s `folder`/`video` + befintliga fält) blir en `lesson`-rad; `transcript`-segmenten
ligger kvar i resultatmappen (SRT/TXT i `Transkriberingar/`), inte i DB:n.

## LLM-extraktion (utöka `app/postprocess.py`)

Nytt läge `extract` vid sidan av `cleanup`/`summary`/`bullets`. Ett **enda** pass över hela
transkriptet (40k kontext räcker för ~60 min). Tvinga **strukturerad JSON** via llama.cpp:s
`response_format`/JSON-schema (servern kör redan `--jinja`), så svaret alltid parsar.

Schema som returneras (mappar 1:1 mot `insights.typ`):
```json
{
  "kalender":  [{"text": "...", "due_date": "2026-05-21"}],
  "svarigheter":[{"text": "pq-formeln, teckenfel", "ref": "uppgift 3.14"}],
  "atgarder":  [{"text": "ta med arbetsblad derivata", "due_date": null}],
  "grupprum":  [{"text": "...", "ref": "plats/grupp"}],
  "material":  [{"text": "facit till kap 3"}]
}
```
Svensk systemprompt med instruktion att hellre utelämna än hitta på. Resultatet skrivs till
`insights` med `source='llm'` och visas som redigerbara kort innan något sparas som bekräftat.

## API-kontrakt (utökar `app/web/server.py`)

```
GET    /api/lessons?group=&course=&from=&to=   -> [{lesson + counts}]   (filtrera/sök)
GET    /api/lessons/{id}                        -> {lesson, insights[], summary}
POST   /api/lessons                             -> skapa/koppla (vid transcribe done)
PATCH  /api/lessons/{id}                        -> redigera datum/klass/kurs/sal
POST   /api/lessons/{id}/extract                -> SSE; kör LLM-extraktion -> insights (source='llm')
GET    /api/lessons/{id}/next-prep             -> aggregerar öppna åtgärder + förra svårigheter
PATCH  /api/insights/{id}                       -> redigera text/typ/status/ref/due_date
DELETE /api/insights/{id}
GET/POST /api/courses, /api/groups             -> CRUD för dropdowns
```
`/api/transcribe` (befintlig) utökas: `done` skapar en `lesson` och returnerar `lesson_id`; klass/kurs/datum
kan skickas med i request (annars sätts efteråt via PATCH).

## Inbyggd inspelning (frontend + lätt backend)

Webb-UI:t spelar in mikrofon med `MediaRecorder` (`getUserMedia({audio:true})`) → Blob → POST till
nytt `/api/upload` som lägger filen i `downloads/` → matas in i **samma** transkriberingsflöde.
- **Endast ljud** som standard (ingen video av klassrummet).
- Paus/återuppta, löpande tid, tydlig "spelar in"-indikator.
- Lång lektion: Whisper-flödet hanterar redan långa filer; om minnet trycker används Parakeet-chunkningen
  som planeras i PR #5-spåret.

## Bonusidéer (utanför MVP, noteras för senare)

- Tagga svårigheter mot **centralt innehåll/kunskapskrav** → terminstrender per klass (egen utveckling + bedömning).
- **Fritextsök** över alla transkript + insikter.
- **Lektionsförslag**: LLM drar ihop carry-forward + svårigheter till ett utkast inför nästa pass.
- **Grupprumsrotation**: föreslå nästa placering utifrån vilka som satt där sist.

## Testning

- `app/db.py`: schema-init, migrering från `history.json`, CRUD, carry-forward-query — allt mot temp-DB.
- `postprocess.extract`: JSON-schema parsas, pseudonymiseringsprompt, tomt transkript → tomma listor (LLM mockad).
- `server.py`: nya endpoints (lessons/insights/extract/next-prep), `/api/transcribe` skapar lesson, `/api/upload`.
- `python -m pytest` förblir grönt; befintliga tester orörda (history-shim kvar).

## Faser

Se planen: `docs/superpowers/plans/2026-06-20-lektionsorganisation.md`.

## Beroenden / sekvensering

1. **Landa PR #6 först** (output_store/daterade mappar) — `lessons.transcript_folder` pekar dit.
2. Fas 1 (DB + Lektioner-tab) är fundamentet allt annat hänger på.
3. Extraktion (fas 2) och inspelning (fas 4) är oberoende av varandra.
