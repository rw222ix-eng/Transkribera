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

## Öppen fråga: varför är API-anropet noggrannare än Claude Code?

Samma underliggande modell (`claude-opus-5`), ändå ger API-adaptern ~24 % mer
text och ~46 % mer figurbeskrivning. Ägaren undrar om det är en
tankeinställning. **Detta är obesvarat och bör utredas först i nya sessionen.**

Tre hypoteser, i fallande sannolikhet:

1. **Claude Codes systemprompt drar mot korthet.** Den är en kodagent, optimerad
   för terse output. Vår OCR-prompt konkurrerar med den; API-anropet har bara
   vår prompt. Detta är den troligaste förklaringen.
2. **Read-verktyget kan skala ned bilden** innan modellen ser den. Sker det
   förlorar vi figurdetaljer som ett rakt API-anrop behåller. Testa genom att
   jämföra utläsningen av en tät figur.
3. **Effort/thinking skiljer sig.** Minst trolig — båda kör Opus 5 med thinking
   på, och Claude Code kör `xhigh` som default.

**Konkret lever att testa:** `claude -p` har `--system-prompt` (ersätter) och
`--append-system-prompt` (lägger till), plus
`--exclude-dynamic-system-prompt-sections`. Byt ut standardpromten mot en som är
skriven för transkribering i stället för kodning och mät om gapet stänger.
Riggen är byggd för precis den jämförelsen — lägg till en variantkandidat och
kör `python ocr-eval/kor.py --bara <namn>`.

Om gapet stänger: kör Claude Code med egen systemprompt. Om det inte gör det:
hypotes 2 är kvar, och då är nedskalningen i Read en hård gräns som talar för
API-vägen trots nyckelhanteringen.

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
- **Bygg aldrig med Impeccables live-tagg injicerad i `index.html`** — den
  bakas in i e2e-bygget och äter Escape och klick. Det gav nio falska fel.
- Fejkserverns databas förorenas av avbrutna e2e-körningar. Ser du dubbletter
  eller `409` på DELETE: starta om servern, den wipar basmappen vid start.
