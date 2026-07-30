# Tavla från boksida — överlämning och plan

*Skriven 2026-07-30 när föregående sessions kontext tog slut. Läs den här filen
först i den nya sessionen; den bär allt som beslutades och varför.*

---

## Vad ägaren faktiskt vill ha

Detta är den ursprungliga frågan, och den är fortfarande den viktigaste:

> "Är det några funktioner jag inte tänkt på än så länge?"

Sammanhanget hon gav: hon ska kunna **skapa en tavla som fungerar som mall
under lektionen** — så smidigt och snabbt som möjligt. Underlaget är oftast ett
**foto hon tagit av en läroboksida**, ibland en PDF. Det är den sidan hon ska ha
genomgång på, så tavlan måste följa bokens innehåll, notation och ordning.

Dessutom gör hon ibland **gruppuppgifter**, som är besläktade med arbetsblad men
strukturellt annorlunda (se nedan).

**Det största hålet i appen i dag:** `BuildPanel` frågar vad momentet är i ett
textfält. Men hon sitter med sidan framför sig. Att beskriva i ord vad som står
på en sida hon håller i handen är att mata in information som redan finns —
exakt det designprincip 6 i PRODUCT.md säger ska bort.

---

## Beslutat: OCR via Claude Code, på ägarens prenumeration

En utvärderingsrigg finns i `ocr-eval/` (README där förklarar den). Fem foton av
riktiga boksidor kördes genom tre kandidater med identisk prompt.

| Kandidat | Tecken | Figurtext | `[oläsligt]` | Sek/sida | Betalas av |
|---|---|---|---|---|---|
| Claude Opus 5 (API) | 8 999 | 3 168 | 12,2 | 115 | Tokens |
| **Claude Code** | **7 275** | **2 169** | **9,4** | **96** | **Prenumerationen** |
| Gemini 3.6 Flash | 5 016 | 1 650 | 8,2 | 32 | Tokens |

**Ägarens val: Claude Code.** Skälet är inte bara kostnaden utan att
nyckelhanteringen försvinner helt.

**Så nås prenumerationen:** Claude Code har en EGEN inloggning, skild från
`ANTHROPIC_API_KEY` och från `ant`:s OAuth-profiler. `claude -p` som subprocess
går därför på abonnemanget. Verifierat: ingen `ANTHROPIC_API_KEY` finns i
miljön och `ant` är inte installerad, ändå läser CLI:n bilderna. Det är samma
mekanism Codex använder när man lägger till Claude Code som tillägg.

Adaptern finns i `ocr-eval/adaptrar.py` (`_claude_code`). Två fällor som redan
är lösta där — återinför dem inte:

- Prompten går på **stdin**, inte som argument (Windows kommandorad har en hård
  längdgräns; PROMPT är ~1,5 kB).
- `subprocess` får den **upplösta** sökvägen från `shutil.which()`. Python
  tillämpar PATHEXT i `which` men INTE i `subprocess`, så `["claude", ...]`
  ger `FileNotFoundError` trots att CLI:n finns.

**Kända avvägningar:** takgränser är användningsfönster i stället för
per-token (irrelevant vid fem sidor i veckan, men en klippkant om en hel bok
ska läsas in); appen får en extern dependency på installerad och inloggad
Claude Code, vilket måste dokumenteras i PyInstaller-bygget; och `claude -p`
startar en hel agentloop per sida, därav 96 s mot Flash 32 s.

---

## Utredd 2026-07-30: varför API-anropet skriver mer än Claude Code

Frågan var varför samma modell (`claude-opus-5`) ger ~24 % mer text och ~46 %
mer figurbeskrivning över API:et än genom `claude -p`. **Alla tre hypoteserna
prövades och föll.** Tre variantkandidater ligger kvar i `adaptrar.py` som bevis
— återuppfinn dem inte.

| Kandidat | Vad som ändrades | Tecken | Figurtext | sek |
|---|---|---|---|---|
| `claude` (API) | — | 8 999 | 3 168 | 115 |
| `claude-code-max` | `--effort max` | 7 489 | 2 591 | **334** |
| `claude-code` | (default) | 7 276 | 2 169 | 96 |
| `claude-code-fil` | svaret skrivs till fil | 6 776 | 2 042 | 92 |
| `claude-code-egen` | egen systemprompt | 6 298 | 1 851 | 75 |
| `gemini-flash` | — | 5 016 | 1 651 | 32 |

**Hypotes 1 (systemprompten drar mot korthet) — motbevisad, åt fel håll.** En
systemprompt skriven för avläsning, som uttryckligen kräver fullständighet och
förbjuder sammanfattning, gav *mindre* text än kodagentens egen. Kodagentens
systemprompt är alltså inte bromsen; den bidrar snarare.

**Hypotes 2 (Read skalar ned bilden) — motbevisad, med mätning.** Tre `claude -p`-
körningar med `--output-format json`, identiska så när som på bilden, gav
32 199 / 33 052 / 36 309 cache-token för ingen bild / 768 px / originalet. Read
levererar alltså ~3 850 bildtoken, mot API-anropets 4 748 (`count_tokens`) — inte
en hårt nedskalad bild utan ~81 %. Och det avgör saken: API-kandidaten matad med
**1568 px, bara 2 360 token**, gav ändå 10 214 tecken / 3 826 figurtecken mot
Claude Codes 8 814 / 2 910 med *fler* pixlar på samma sida. Gapet handlar inte om
vad modellen ser.

*Bifynd som motsäger dokumentationen:* Anthropics API skalar **inte** ned allt
över 1568 px längsta sida. En 4096×3072-bild kostar 4 748 token, ungefär dubbelt
mot vad den gränsen skulle tillåta. Upplösning är en verklig variabel i
API-vägen, inte en utjämnad — vilket också syntes i utläsningen: 11 095 tecken
vid 4096 px, 10 214 vid 1568, 8 924 vid 768.

**Hypotes 3 (effort) — motbevisad som lösning, men inte som mekanism.**
`--effort max` är den enda varianten som rör sig uppåt, och mest på den axel som
betyder något (figurtext 2 169 → 2 591, alltså 82 % av API:ets). Priset är 334 s
per sida mot 96, med en sida på 559 s. Ingen lärare väntar nio minuter på en
boksida.

**Hypotes 4, som planen inte hade: leveranssättet.** Ett agentsvar är en replik
i ett samtal och kortas därefter; en fil är ett dokument. `claude-code-fil` lät
agenten skriva avläsningen med Write i stället för att svara i chatten. Det
hjälpte inte heller (6 776 tecken).

### Vad som återstår, och vad det betyder

Ingen inställning som går att nå utifrån `claude -p` stänger gapet. Kvar står
själva agentramen — att bilden kommer som ett verktygsresultat inne i en loop i
stället för som uppgiftens egen indata — och den går inte att ställa av.

**Håll isär två saker som utvärderingen inte höll isär:** det som mätts är
MÄNGD text, inte att texten är RÄTT. Att API:et skriver 46 % mer om figurerna
säger att det beskriver utförligare, inte att Claude Code har fel. Ska "noggrann"
beläggas krävs att någon läser båda utläsningarna mot fotot på ett par ställen
där notationen är tät. `resultat/jamfor.html` är byggd för precis det, och
beslutet ligger hos ägaren.

**Konsekvens för appen: de två vägarna i punkt 1 nedan har olika krav.**
Per lektion står läraren och väntar, och då är 96 s redan mycket och 334 s
uteslutet. Engångsimporten av en hel bok körs obevakad, och där är väntetiden
gratis — den vägen bör köra `--effort max`, eller API:et. Samma avläsare behöver
alltså inte betjäna båda.

### Ägarens beslut, 2026-07-30 (efter mätningen)

**Claude Code, `claude -p`, för per-lektionsvägen.** Gapet mot API:et är mätt,
känt och accepterat: ~24 % mindre text och ~46 % mindre figurbeskrivning mot
noll nyckelhantering och ingen tokenfaktura. Bygg avläsaren mot CLI:n, med
`ocr-eval/adaptrar.py:_claude_code_kor` som referens — de två fällorna där
(prompten på stdin, den upplösta sökvägen från `shutil.which`) gäller
fortfarande, och `--bare` får aldrig användas eftersom den flyttar
autentiseringen till `ANTHROPIC_API_KEY`.

Det gör CLI:n till en **extern körtidsberoende** för appen: installerad,
inloggad och på PATH. Det måste synas i PyInstaller-bygget och ge ett begripligt
felmeddelande i UI:t när den saknas — inte en tyst tom avläsning.

---

## Modellbytet — ägarens beslut 2026-07-30

Qwen3-14B och vision-Gemman utgår. Claude Code CLI tar över deras arbete.
**Detta är beslutat, inte föreslaget.**

| Modell | Vad den gör i dag | Beslut |
|---|---|---|
| KB-Whisper (lokal) | transkriberingen | **stannar** — fungerar som den ska |
| Gemma 4 E4B (lokal, `audio_model.py`) | andra passet som rättar texten **mot ljudet** | **stannar** — Claude kan inte ta emot ljud, så den har ingen ersättare |
| Qwen3-14B Q8 (~15 GB) | rättning, sammanfattning, extraktion, arkivchatt, tavla, prov, arbetsblad | **utgår** → Claude Code |
| Gemma 3 4B vision (~3,3 GB) | bildtolkning av uppladdade boksidor | **utgår** → Claude Code |

### Vad som följer av det, och som måste hanteras

**1. Elevdata lämnar datorn.** Transkripten går till Anthropic. Ägaren är
informerad och har valt det ändå; det är hens data och hens beslut. Men appens
grundregel var det motsatta, så `PRODUCT.md` är omskriven i samma veva — en
strategitext som påstår "allt körs lokalt" när det inte stämmer är värre än
ingen strategitext. **Följden för gränssnittet:** appen måste vara ärlig om
vilka moment som går ut, på samma sätt som kalenderförslagen redan granskas före
sändning. Det är en designfråga, inte en implementationsdetalj — den ligger i
Claude Design-briefen.

**2. Den garanterade JSON:en försvinner — den största tekniska risken.**
llama.cpp *grammatiktvingar* utdatan: modellen kan fysiskt inte skriva ogiltig
JSON, och provets balans låses per uppgift med `prefixItems`/`const`
(`exam_spec.to_response_format`). `claude -p --json-schema` **validerar** i
stället, vilket är något annat. Reparationsloopen i `exam_gen` går därmed från
skyddsnät till bärande konstruktion, och skelettets balansgaranti måste
kontrolleras i efterhand i stället för att vara sann by construction.

**3. GPU-arbitern förenklas men försvinner inte.** Den 21 GB stora LLM:en är
borta, så Whisper slipper konkurrera om kortet — men ljud-Gemman finns kvar och
behöver fortfarande serialiseras mot Whisper.

**4. Väntetiden byter form.** En lokal modell strömmar token direkt; `claude -p`
startar en agentloop och tiger i 1–2 minuter. Varje ställe som i dag visar
strömmande text (tavlan, provet, chatten) får en annan väntekaraktär, och prov
med flera reparationsrundor kan bli flera minuter. Det är en designfråga för
Claude Design: hur ser väntan ut när den inte längre kan visa framsteg?

**5. Modellhanteraren krymper.** Nedladdning, VRAM-rekommendationer och
installationsstatus för LLM:er utgår; kvar blir Whisper, ljud-Gemman och ett
nytt tillstånd: *Claude Code saknas / är inte inloggad*. Det senare måste vara
ett begripligt besked, aldrig en tyst tom utdata.

**6. Appen blir nätberoende.** Utan internet fungerar transkriberingen och
ljudrättningen, men ingenting annat. Takgränserna blir dessutom
användningsfönster i stället för tokenkostnad.

---

## Gruppuppgift är en egen dokumenttyp

Appen har `prov.tex.j2` och `arbetsblad.tex.j2`. Ägarens gruppuppgift
(`Från_text_till_ekvation_gruppuppgift.pdf`, gjord för hand) visar vad som
saknas:

- **Namnfält för gruppmedlemmarna** (två i hennes)
- **Ifyllnadsställning per uppgift** — `Ekvation:` / `Typ: ☐ ☐` / `Svar i ord:`
- **Metodinstruktion överst** — en strategi, inte en uppgift
- **Inget facit på bladet** (grupparbete i klassrummet)
- **Nivåmärkning** och verkliga kontexter (labb, bro, Tjernobyl)

**VIKTIGT — ägaren korrigerade mig här:** ifyllnadsställningen är INTE en
återanvändbar mall. Varje gruppuppgift kan handla om något helt annat.
Strukturen ska **följa av vad uppgiften kräver**, inte väljas ur ett bibliotek.
Ett bibliotek hade dragit alla gruppuppgifter mot samma form.

### Två användningar, och den andra är särskild

1. **Mitt i ett kapitel** — variera arbetssättet. Nära ett arbetsblad, i grupp.
2. **Som brygga mellan kapitel** — eleverna återanvänder det de kan, undersöker
   något, och **kommer fram till ett samband eller en formel** de sedan ska
   arbeta med. Löses tillsammans med läraren som lots.

Den andra är **ledd upptäckt, inte träning**. Genereringen behöver veta tre
saker prov och arbetsblad aldrig frågar efter: vad eleverna kan sedan innan,
vilken formel de ska landa i, och att uppgiften ska klara att lösas gemensamt.
Att generera den som "ett arbetsblad fast i grupp" ger fel sorts uppgift varje
gång.

---

## Kvarstående funktioner, i prioritetsordning

**1. Boksidan som källa** (det stora hålet). Två nivåer:
   - Per lektion: dra in foto/PDF-sida → tavlan skrivs utifrån den.
   - En gång: importera boken, indexera per kapitel, välj "3.4
     Exponentialekvationer" ur en lista som i dag med Gy25-innehåll. Noll
     inmatning per lektion — det är den som faktiskt sparar tid.

**2. Automatisk genomgång efter varje transkribering.** Står redan i PRODUCT.md
   under "Avsett men obyggt". Appen ska själv leta datum, åtaganden och
   uppföljningar och lägga fram dem som granskningsbara förslag. I dag sker det
   bara när läraren frågar — vilket förutsätter att hon kommer ihåg att fråga,
   och att komma ihåg är precis problemet appen finns för att lösa.

**3. Klass, kurs och namn vid inläsning.** Sätts i dag först i arkivet.
   Inläsningen är enda punkten där hon säkert vet vilken lektion det är.

**4. Gruppuppgift som fjärde dokumenttyp** (se ovan).

**5. Tavla och gruppuppgift ur samma källa i en körning.** Hon går igenom X,
   sen gör de en gruppuppgift på X. Samma källa, två dokument.

**6. Transkriptet som indata till nästa tavla.** Den jag tror är mest förbisedd:
   arkivet vet vad som *faktiskt* hände förra lektionen. Fastnade de på när man
   ska logaritmera borde nästa tavla veta det. Det knyter ihop appens två
   halvor, som i dag är två verktyg i samma skal.

**7. Massradering i kartoteket.** Ägaren har godkänt den. Designen:
   kryssruta per rad i `Lektionskort`, `markerade` som id→true-karta i storen,
   rad ovanför kartoteket med "3 valda" + *Radera markerade* / *Avmarkera*,
   samma bekräftelsedialog med antalet, sekventiella
   `DELETE /api/lessons/{id}`, fortsätt vid fel och sammanfatta, en omhämtning
   på slutet. Enkelraderingens generationsvakter rörs inte. Storefälten fanns
   påbörjade men återställdes — de var död kod utan läsare.

---

## Vad som redan är gjort (rör inte om)

Sju commits på `main` 2026-07-30, alla med grön gate (`python -m pytest` 803,
`npm run check` 0 fel, e2e 107/107):

- Fyra användarvända texter slutade hänvisa till den pensionerade vanilla-appen
- Miniatyren faller till textlayout när `/api/thumb` svarar 404
- `Segment.svelte` ersatte fem segmentformer (enval = platta, flerval = chips)
- Kartoteket blev en lista med hårlinjer i stället för kortrutnät
- Flikraden blev en riktig `tablist` med roving tabindex
- Vyrubrikerna: en röst, Instrument Serif kursiv 3.2rem, rent `#000`
- `design-system/`-spegeln om-seedad; Claude Design har nu `app.html`,
  `foundations.html`, `components.html`, `styles.css` som redigeringsyta

DESIGN.md och PRODUCT.md är omskrivna efter ägarens faktiska val. **Stående
regel: vid varje designändring skrivs DESIGN.md om i samma commit.**

---

## Praktiskt för nya sessionen

- Läroboksfotona ligger i `ocr-eval/sidor/` (gitignorerade, finns lokalt).
- Jämförelsen byggs med `python ocr-eval/jamfor.py` → `resultat/jamfor.html`.
- Siffrorna i tabellen ovan kommer ur `python ocr-eval/matt.py`, som räknar om
  allt i `resultat/`. Kör den efter varje ny variant i stället för att jämföra
  fem markdownfiler mot fem andra i huvudet.
- **Läs `oläsligt`-kolumnen försiktigt.** `claude-code-max` satte 0,2 markörer
  per sida men skrev 1 200 tecken under OSÄKERT — den redovisar i prosa i
  stället för att märka i texten. Låg siffra är inte självsäkerhet förrän du
  läst avsnittet.
- Konsollen på den här maskinen är cp1252 och kvävs på `ä` i skriptutdata. Kör
  `PYTHONIOENCODING=utf-8 python ocr-eval/matt.py` så slipper du en
  `UnicodeEncodeError` som ser ut som ett fel i riggen.
- **Bygg aldrig med Impeccables live-tagg injicerad i `index.html`** — den
  bakas in i e2e-bygget och äter Escape och klick. Det gav nio falska fel.
- Fejkserverns databas förorenas av avbrutna e2e-körningar. Ser du dubbletter
  eller `409` på DELETE: starta om servern, den wipar basmappen vid start.
