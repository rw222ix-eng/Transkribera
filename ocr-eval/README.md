# OCR-utvärdering — läroboksidor till tavelunderlag

Ska appen kunna skriva en tavla utifrån en fotad boksida måste något först läsa
sidan. Den här riggen avgör **vad** som ska göra det, på bevis i stället för på
rykte.

## Vad som faktiskt mäts

Inte "OCR-noggrannhet" i abstrakt mening. Kriteriet är smalare och hårdare:

> **Räcker utdatan för att generera en tavla som håller under en genomgång?**

Det ställer tre krav som vanliga OCR-jämförelser inte mäter:

1. **Matematiken måste bli rätt.** Ett tappat exponenttecken eller ett bråkstreck
   på fel ställe ger en tavla som är fel på tavlan, inför klassen.
2. **Figurerna måste beskrivas, inte hoppas över.** En graf eller en geometrisk
   skiss bär ofta hela poängen med avsnittet. Modellen som sedan skriver tavlan
   (Qwen3) ser inga bilder — den får bara texten. Duger inte figurbeskrivningen
   finns figuren inte.
3. **Inget får hittas på.** Det här är den viktigaste. En modell som gissar sig
   igenom en suddig formel producerar något som *ser* rätt ut och är fel. Tyst
   fel är värre än synligt fel, för det upptäcks först framför klassen.

## Din del: fem sidor

Lägg fem foton i `sidor/`. Filnamnet spelar ingen roll, ordningen inte heller.

Fota **som du faktiskt gör** — det är hela poängen. Inte uppställt, inte rätvinkligt,
inte i studiobelysning. Sned vinkel, skugga från handen, klassrumsljus. Riggen ska
mäta verkligheten, inte ett bästa fall du aldrig får.

Ta gärna med spridning:

- minst en sida med **en figur som betyder något** — en graf, en geometrisk skiss,
  något där bilden bär innehållet
- minst en med **tät notation** — index, exponenter, bråk, rotuttryck
- minst en **vanlig genomgångssida** av den sorten du oftast utgår från
- gärna en som är **lite dåligt fotad**. Om en kandidat klarar den vet vi något
  värdefullt; om alla faller på den vet vi också det.

Mappen är gitignorerad. Läroboksidor hamnar aldrig i repot.

## Köra

```bash
python ocr-eval/kor.py
```

Riggen kör **samma prompt** genom varje kandidat den kan nå, och hoppar över
resten med besked om varför. Utdata hamnar i `resultat/` som en markdownfil per
sida och kandidat.

Sedan:

```bash
python ocr-eval/jamfor.py
```

Bygger `resultat/jamfor.html` — fotot till vänster, varje kandidats utläsning
bredvid. Det är den sidan beslutet fattas på.

`python ocr-eval/matt.py` räknar dessutom ihop det som går att räkna — tecken,
figurtext, `[oläsligt]` och väntetid per sida. Det måttet finns för en smalare
fråga än beslutet: när samma kandidat körs om med en ändrad inställning, rörde
sig något? Det svarar aldrig på om utläsningen blev *rätt*.

De fyra `claude-code`-raderna är samma CLI med en sak ändrad var — effort,
systemprompt respektive leveranssätt. De ligger kvar som bevis: var och en av
dem prövade en förklaring till varför API-anropet skriver mer, och ingen av dem
stängde gapet. Se plandokumentet `docs/superpowers/plans/2026-07-30-tavla-fran-boksida.md`
innan du prövar samma sak igen.

## Kandidater

| Kandidat | Var | Kräver | Modellnamn styrs av |
|---|---|---|---|
| `claude-code` | prenumerationen | `claude` på PATH, inloggad | CLI:ns egen modell |
| `claude-code-max` | prenumerationen | d:o | d:o |
| `claude-code-egen` | prenumerationen | d:o | d:o |
| `claude-code-fil` | prenumerationen | d:o | d:o |
| `tesseract` | lokalt | `tesseract` på PATH + svenskt språkdata | — |
| `qwen-vl` | lokalt | llama.cpp-server på `LLAMACPP_VL_URL` | serverns modell |
| `gemini-pro` | API | `GEMINI_API_KEY` | `GEMINI_MODEL` |
| `gemini-flash` | API | `GEMINI_API_KEY` | `GEMINI_FLASH_MODEL` |
| `claude` | API | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` |
| `mistral` | API | `MISTRAL_API_KEY` | `MISTRAL_MODEL` |

**Modellnamnen är färskvara.** Gemini 3.5 kom i juni 2026, 3.6 Flash och 3.5
Flash-Lite den 21 juli, Claude Opus 5 den 24 juli. Publicerade dokument-benchmarks
(OmniDocBench, OCRBench) ligger ett kvartal efter och saknar helt siffror för allt
som släppts de senaste veckorna. Kolla defaultnamnen i `adaptrar.py` mot vad som
faktiskt finns när du kör, och styr med miljövariablerna ovan.

`gemini-flash` ligger med som **egen kandidat**, inte som en billigare reservutväg.
Det du betalar för i det här steget är väntetid — OCR är momentet du står och väntar
på. Är Flash lika bra på dina sidor är den rätt val oavsett pris.

Tesseract ligger med som **golv**, inte som kandidat. Den kan ingen matematik och
inga figurer. Poängen är att se hur långt ifrån användbart ren OCR ligger, så att
de andras resultat får en skala.

## Vad som får lämna datorn

Ägarens beslut, 2026-07-28: **boksidor får gå ut, lektionsmaterial aldrig.**

Regeln i appen är inte "ingenting får lämna datorn" utan **"elevdata får aldrig
lämna datorn"** — och den skrevs för lektionsljudet, som är det enda materialet
som bär något känsligt. En sida ur en tryckt lärobok bär ingen elev, inget namn,
ingen röst. Samma sorts undantag som kalenderposterna, som också går ut efter
godkännande.

Den här riggen rör därför **bara** filerna i `sidor/`. Den läser inte
`Transkriberingar/`, inte databasen, inte historiken. Den gränsen är inte en
konvention utan hela skälet till att API-kandidaterna får finnas med.

Kvar är en upphovsrättsfråga — att skicka inskannade läromedel till tredje part är
en licensfråga, inte en integritetsfråga. Den ligger hos ägaren.
