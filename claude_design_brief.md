# Transkribera — designuppdrag till Claude Design

**Syfte:** Bygg vidare på det befintliga projektet *"Omdesign till minimalistisk UI"*. Backenden har fått nya funktioner (en andra transkriberingsmotor + ett ljud-grundat korrigeringspass) som ska in i designen, och ett par saker ska **tas bort**. Behåll designspråket; ändra bara det som står här.

Appen är en lokal svensk/engelsk transkriberingsapp (allt körs lokalt på användarens dator, RTX 4090). Den laddar ner/öppnar ljud- och videofiler eller en YouTube-URL, transkriberar till SRT/TXT/VTT, och kan efterbehandla texten.

---

## 1. Designspråk att BEHÅLLA (oförändrat)
- Geist-typsnitt, ljust + mörkt tema, samma färgtokens och skuggor.
- Sticky header med logga (equalizer-staplar) + segmenterad flik-nav: **Transkribera · Historik · Modeller** + "Ansluten"-prick + temaväxlare.
- Transkribera-fliken som **3-stegsguide: Källa → Inställningar → Resultat**, med stegindikatorn.
- Korten, knapparna (inkl. den animerade "Starta"-streckgubben), conic-gradient-ringen på Kör-knappen, modalerna, toasten, tooltipsen — allt det visuella är redan bra och ska bevaras.
- Centrerad kolumn (~780 px), tabulär-siffror, generösa marginaler.

---

## 2. LÅST — får INTE ändras
- **Transkriberingsmodeller: exakt två, inga fler får bli valbara.**
  - **KB-Whisper large** — svenska.
  - **Parakeet TDT 0.6B v3** — engelska. *(NY — se §4a.)*
- **Textkorrigering & analys: Gemma 4 26B** (en modell, via Ollama). Oförändrad.
- **Ljudkorrigering: intern modell, INGET användarval** (Gemma 4 E4B — visas aldrig som valbar modell). *(NY funktion — se §4b.)*
- **Inga andra modeller** får visas som valbara (ingen "fler modeller online", inga demo-modeller).
- **Behåll BÅDE lokala filer OCH YouTube-URL** i källsteget (dra-och-släpp + filväljare **och** ett URL-fält).

---

## 3. TA BORT från den förra designen
- **All diarisering / "vem talar när" / talaridentifiering.** Ta bort: diariserings-toggeln och dess install-gate i Inställningar, "Förväntat antal talare", de namngivningsbara talarraderna, talar-prickar/etiketter i transkript-vyn, "Diariseringsmodell"-raden i Modeller, och "N talare" i historik-metadata. **Funktionen finns inte.**
- **De aspirationella demo-modellerna** (Canary-Qwen, Whisper large-v3, Canary 1B, Qwen3 / Qwen3-VL / Qwen3-Omni, gpt-oss, online-modeller m.fl.). Modeller-fliken ska bara visa de låsta modellerna i §2 (se §5).

---

## 4. NYTT / ÄNDRAT att designa

### 4a. Parakeet som transkriberingsval (engelska)
Modell-dropdownen i steg **Inställningar** har nu **två** alternativ:
- **KB-Whisper large** — "Svenska", rekommenderad för svenska.
- **Parakeet TDT 0.6B v3** — "Engelska", rekommenderad för engelska. Snabb (~50× realtid), körs på GPU.

Designa:
- Hur man väljer modell, och gärna att **språkvalet (Auto / Svenska / Engelska) föreslår rätt modell** (Svenska→KB-Whisper, Engelska→Parakeet). Visa modellens språk + kort kvalitetshint.
- Samma rad-/dropdown-stil som idag (färgad fit-prick, namn, meta-chip).
- States: vald / ej nedladdad (visa nedladdningsknapp som för andra modeller) / nedladdad / rekommenderad-badge.

### 4b. "Rätta mot ljudet" — ljud-grundat korrigeringspass (NYTT)
Ett **andra, separat korrigeringspass** som körs EFTER transkriberingen och rättar texten **mot själva ljudet** (inte bara mot texten). Det fångar hör- och stavfel som en ren textkorrigering missar. Samma trohetsprincip: rättar bara fel, hittar inte på, behåller betydelsen.

Skilj det tydligt från den **befintliga** efterbearbetningen (som jobbar på texten via Ollama):
- Befintligt idag: **Korrekturläs** (text), **Summera**, **Chatta**.
- Nytt: **Rätta mot ljudet** (ljud-grundat) — placera det i resultat-/efterbearbetnings-sektionen som ett eget val/knapp, gärna märkt som det mest noggranna korrigeringssteget ("lyssnar på ljudet").

Designa states:
- **idle:** knapp/sektion "Rätta mot ljudet".
- **kör:** progress (passet går segment för segment — visa procent/förlopp, samma stil som Kör-ringen).
- **klar:** visar den korrigerade transkriptionen + nedladdning (en `_rattad.srt`/`.txt`/`.vtt`). Gärna en diff-känsla mot originalet, men inget krav.
- **fel:** felmeddelande + försök igen.
- **gate:** om den interna ljudmodellen inte är nedladdad (se §4c), visa nedladdnings-prompten i stället för att köra.

### 4c. Nedladdning av ljudmodellen (engångs, ~16 GB)
Ljud-passet kräver en intern modell (~16 GB) som laddas ner en gång. Den är **inte** ett användarval och ska **inte** ligga i modell-listorna — men användaren behöver kunna ladda ner den.

Designa en nedladdnings-prompt (samma visuella stil som modell-nedladdning i Modeller-fliken: knapp → progressbar → klar):
- Visas när användaren väljer "Rätta mot ljudet" men modellen inte är nedladdad ("Ladda ner ljudmodellen (~16 GB) för att rätta mot ljudet").
- States: ej nedladdad → laddar (progress) → klar (då körs passet).

---

## 5. Modeller-fliken (exakt innehåll)
Behåll hårdvarukortet (VRAM/RAM/Disk-mätare, disk-väljare, spec-rad) oförändrat. Modell-listorna ska visa **endast**:
- **Transkriberingsmodeller:** KB-Whisper large (sv) + Parakeet TDT 0.6B v3 (en) — ranked rader, fit-prick, chips (språk, VRAM, ×realtid), storlek, nedladdningsknapp (samma `ModelDLButton`-faser).
- **Språk- och videomodeller:** endast **Gemma 4 26B** (textkorrigering & analys). Ta bort användningsfall-filtret/demo-modellerna, ELLER behåll filtret men med bara denna modell.
- **Ljudmodell (info, ej valbar):** valfritt — en liten info-rad om den interna ljudmodellen med nedladdningsstatus/knapp (§4c). Den ska tydligt INTE se ut som en valbar transkriberings-/LLM-modell.

---

## 6. Datakontrakt (referens — så designen matchar verklig data; en kodare wirar API:t sen)
Allt är lokala `/api/*`-anrop; långa jobb strömmar Server-Sent Events (`progress` / `log` / `token` / `done` / `error`).

- **`GET /api/models`** → `{ hardware, ollama_running, whisper:[…], llm:[…], online:[], audio_model:{id, installed} }`
  - `whisper[]`: `{ id, label, lang ("sv"|"en"), engine ("faster-whisper"|"parakeet"), size, vram, rtf, fit, installed, recommended, useFor }` — nu **två** rader.
  - `llm[]`: endast Gemma 4 26B. `online` är alltid tom.
  - `audio_model`: `{ id, installed }` — driver gaten i §4b/§4c.
- **`POST /api/transcribe`** `{ source, model_id, language ("",|"sv"|"en"), formats:["srt","txt","vtt"] }` → SSE; `done.result = { files:[{name,ext,size,path}], transcript:[{start,end,text}], media }`. `source` = lokal sökväg **eller** http(s)-URL (YouTube). `media` = den färdiga ljud-/videosökvägen (skicka tillbaka den till ljud-passet).
- **`POST /api/audio_correct`** `{ source, segments:[{start,end,text}], formats }` → SSE; `done.result = { files, transcript }`. Använd `source = transcribe-resultatets media` och `segments = transcribe-resultatets transcript`. Skriver `<namn>_rattad.srt`.
- **`POST /api/download/audio_model`** `{}` → SSE progress (~16 GB).
- **`POST /api/postprocess`** `{ operation:"cleanup"|"summary"|"bullets", transcript, model }` → SSE token-ström (befintlig textkorrigering/analys).
- **`POST /api/chat`** `{ messages, transcript, model }` → SSE token-ström (befintlig chatt).
- **`POST /api/download/whisper`** `{ id }` och **`/api/download/llm`** `{ name }` → SSE progress (samma för Parakeet, den ligger i whisper-listan).
- **`GET /api/history`**, **`DELETE /api/history/{id}`**, **`GET /api/hardware`** — oförändrade.

---

## 7. States-checklista (täck dessa i designen)
- **Källa:** tom / fil(er) i kö / filfel / YouTube-URL ifylld.
- **Modellval:** rekommenderad / vald / ej nedladdad (nedladdningsknapp) / laddar / nedladdad.
- **Transkribering:** förbereder → kör (progress + logg) → klar (filer + transkript-förhandsvisning) → fel → avbruten. Flera filer i kö med per-fil-status.
- **Textkorrigering (befintlig):** Korrekturläs / Summera / Chatta — idle / kör / klar.
- **Rätta mot ljudet (nytt):** gate (ladda ner ljudmodell) → idle → kör (per-segment progress) → klar (korrigerad text + nedladdning) → fel.
- **Historik:** tom / lista (utan "talare").

---

## 8. Arbetsdelning
Claude Design gör det **visuella** (skärmar, komponenter, states, copy). En kodande agent portar det sedan till den befintliga vanilla-JS/morphdom-frontenden och kopplar `/api/*` enligt §6 — så designen behöver inte implementera nätverkslogik, bara täcka rätt vyer/states/data och hålla designspråket.
