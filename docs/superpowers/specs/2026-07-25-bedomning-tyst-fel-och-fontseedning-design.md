# Bedömningsanvisningens tysta kompileringsfel + ofullständig fontseedning

**Datum:** 2026-07-25
**Status:** design godkänd
**Berör:** `app/web/routes_exam.py`, `tools/seed_tectonic_cache.py`,
`tests/test_exam.py`, `tests/test_routes_exam.py`, `tests/test_tectonic_seed.py`

---

## Bakgrund

Två separata, redan existerande buggar i `app/` upptäcktes under en skarp
end-to-end-körning 2026-07-25 (riktig Qwen3-14B + riktig Tectonic, via
`e2e/serve_test_app.py --real`). De hänger ihop: den andra buggen var
osynlig just för att den första svalde felet.

Ingen av dem rör Svelte-migrationen.

### Bugg 1 — tyst fel

`app/web/routes_exam.py:350` anropade

```python
exam_pdf.compile_pdf(bed, out_dir, f"{slug} - bedomning")
```

och kastade bort returvärdet. `compile_pdf` returnerar `(pdf_path, log)` och
ger `pdf_path=None` vid misslyckande. När bedömningsanvisningen inte gick att
kompilera hände alltså ingenting: ingen `{"type":"log"}`-rad, ingen post i
`errors`, och kvittot i gränssnittet stod kvar på "PDF skapad: …prov.pdf".
Läraren tror att allt gick igenom och upptäcker det först när
bedömningsanvisningen saknas vid rättningen.

Provets egen kodväg strax ovanför (rad 347–352) kontrollerar däremot
`pdf_path is not None` och har en `fix_latex`-slinga.

### Bugg 2 — ofullständigt seedad fontcache

I samma körning föll bedömningsanvisningen på:

```
warning: Tectonic unable to generate PK font "ntxsy7" (dpi 480) on-the-fly
warning: Could not locate a virtual/physical font for TFM "ntxsy7".
error: Cannot proceed without .vf or "physical" font for PDF output...
note: using only cached resource files
```

Provet självt kompilerade felfritt (23 749 byte, 3 sidor) — bara
bedömningsanvisningen nådde den fontstorleken.

Tabellen nedan byggdes utifrån kraschrapporten ovan — vilka `.tfm`-namn som
redan var kända från loggen — inte en fullständig genomgång av
`bin/tectonic/cache/`. Det är därför den ursprungligen missade en fjärde
lucka helt (familj 3, se tillägget efter tabellen): metrikfilen finns, men
den virtuella fonten saknas:

| TFM i cachen | `.vf` / fysisk font | Betydelse |
| --- | --- | --- |
| `ntxmi.tfm` | ✅ `ntxmi.vf` + `NewTXMI.pfb` | matte-kursiv, textstorlek |
| `ntxmi7.tfm` | ✅ `ntxmi7.vf` + `NewTXMI7.pfb` | script — seedad av `$a^n$`-arbetet |
| `ntxmi5.tfm` | ❌ **saknas** | scriptscript matte-kursiv — latent |
| `ntxsy.tfm` | ✅ `ntxsy.vf` | symbolfont, textstorlek |
| `ntxsy7.tfm` | ❌ **saknas** | **kraschen ovan** |
| `ntxsy5.tfm` | ❌ **saknas** | scriptscript symbolfont — latent |
| `ntxexx.tfm` | ❌ **saknas** | familj 3 (utökningsfamiljen): `\sum`, `\int`, `\left(...\right)`, stor `\sqrt` |
| `ntxexa.tfm` | ❌ **saknas** | familj 3, AMS-utökningen — samma kodvägar som `ntxexx` |

Orsaken: TeX laddar en TFM enbart för att läsa mattens fontdimensioner, men
xdvipdfmx behöver `.vf`/fysisk font först när en glyf faktiskt sätts. Sonden
har aldrig **satt en glyf** i de storlekarna. `ntxmi7` är undantaget just för
att någon tidigare la in `$a^n$` i det representativa dokumentet.

Det är alltså fem luckor, inte en — och samma sorts åtgärd stänger alla fem.
`ntxexx`/`ntxexa` är dock en EGEN matematisk familj, inte en storlek: en
efterföljande granskning visade att storleksstegen i script/scriptscript
(nedan) aldrig sätter en glyf i familj 3, så den luckan krävde ett eget
tillägg (se "Familj 3" nedan).

### Varför testsviten var grön

`tests/test_exam.py::test_compile_pdf_real_engine_produces_all_three_documents`
passerar: dess fixturprov nästlar aldrig matte djupt nog för att begära
`ntxsy7`. Den befintliga grinden täcker inte fallet.

---

## Beslut

| Fråga | Val |
| --- | --- |
| Vad ska ske när bedömningen faller men provet lyckas? | Försök om via `fix_latex`, behåll provet |
| Hur långt ska sondfixen gå? | Systematisk storleksstege + familj 3 (stänger alla fem luckor) |
| Omseedning | Utförs mot den riktiga cachen i `E:\Transkribera` |

---

## Del 1 — bedömningsfelet ska synas

### Ändring

Kompileringsblocket i approve-slingan (`app/web/routes_exam.py`, ca rad
346–408) blir — detta är vad som faktiskt landade, inte utkastet nedan från
det första förslaget:

```python
prov_pdf, log = exam_pdf.compile_pdf(tex, out_dir, slug)
# Ett prov som EN GÅNG kompilerat får inte försvinna för att en senare
# korrigeringsrunda (utlöst av bedömningen) skrev om provet till något
# som inte går att kompilera. Filen ligger kvar i utkatalogen — behåll
# sökvägen så länge den gör det.
if prov_pdf is not None:
    pdf_path = prov_pdf
elif pdf_path is not None and not pdf_path.exists():
    pdf_path = None

bed_path = None
bed_misslyckades = False
if prov_pdf is not None and bed is not None:
    bed_path, bed_log = exam_pdf.compile_pdf(bed, out_dir, f"{slug} - bedomning")
    if bed_path is None:
        bed_misslyckades = True
        log = bed_log            # rätt logg går vidare till fix_latex
if prov_pdf is not None and (bed is None or bed_path is not None):
    errors = []
    break

# Avgör FÖRE loggraden om en korrigering faktiskt följer.
sista_forsoket = (round_ >= exam_gen.MAX_LATEX_ROUNDS
                  or arbiter.ensure_llm() is None)
if bed_misslyckades:
    emit({"type": "log",
          "msg": "Bedömningsanvisningen gick inte att kompilera."
                 if sista_forsoket else
                 "Bedömningsanvisningen gick inte att "
                 "kompilera — försöker korrigera …"})
if sista_forsoket:
    felkod = "bedomning" if pdf_path else "kompilering"
    meddelande = (
        ("Bedömningsanvisningen gick inte att kompilera:\n" + log)
        if felkod == "bedomning" else log)
    errors = [{"path": "latex", "code": felkod, "message": meddelande}]
    break
```

### Motivering

En runda räknas som lyckad först när **samtliga** dokument som ska produceras
har kompilerat. Flera egenskaper faller ut, utöver det ursprungliga förslaget:

1. **`prov_pdf` skiljs från `pdf_path`.** `prov_pdf` är DENNA rundas
   kompileringsresultat; `pdf_path` är "bästa resultat hittills" och nollställs
   bara om den filen är genuint borta. Utan den distinktionen (det ursprungliga
   förslaget satte om `pdf_path` varje runda) kastas ett prov som kompilerade i
   runda 0 bort så fort en SENARE runda — utlöst av att bedömningen misslyckades
   och `fix_latex` skrev om hela provet — själv misslyckas. Se
   `test_approve_prov_fran_tidigare_runda_overlever_senare_kompileringsfel` i
   `tests/test_routes_exam.py`.
2. **`log = bed_log` är den bärande raden** för själva tystnadsbuggen.
   `fix_latex` får bedömningens fel i stället för provets tomma logg. Det är
   vad som gör att omförsöket kan reparera t.ex. en trasig `\frac` i fältet
   `losning` — ett fält som `prov.tex.j2` aldrig renderar, så bedömningsanvisningen
   är det enda dokument som kan avslöja felet.
3. **Loggradens ordalydelse väljs av `sista_forsoket`**, inte skrivs
   ovillkorligt. `sista_forsoket` avgörs INNAN loggraden: antingen är rundorna
   slut (`round_ >= MAX_LATEX_ROUNDS`) eller modellen kan inte startas
   (`arbiter.ensure_llm() is None`) — de två grenarna är slagna ihop till EN,
   så båda väger felkoden från `pdf_path`, inte bara rundgrenen. Om ett
   omförsök faktiskt kommer att ske säger loggen "— försöker korrigera …";
   annars den uppgivna varianten utan tomt löfte om ett omförsök som aldrig
   sker.
4. **Ett fungerande prov kastas aldrig bort.** `pdf_path` håller kvar provets
   sökväg över rundor (punkt 1), så `result["pdf"]` pekar på provet och
   kvittot förblir sant — samtidigt som `errors` bär en synlig post.
5. **Skild `code`, med svensk prefix på det som PERSISTERAS.** `"bedomning"`
   mot `"kompilering"` låter gränssnittet skilja "inget prov alls" från
   "provet är klart, anvisningen saknas". SSE-loggraden i punkt 3 är transient
   (den försvinner när körningen är klar, se `exRunning`-gaten i `app.js`) —
   det som sparas är `errors[].message`, som gränssnittet renderar rått utan
   att läsa `code`. Vid `code == "bedomning"` prefixas därför `message` med
   samma svenska mening, så en engelsk Tectonic-loggrad aldrig står ensam
   bredvid ett kvitto som säger "PDF skapad". Den befintliga assertionen i
   `test_approve_compile_failure_reports_honestly`
   (`any(e["code"] == "kompilering" …)`) berörs inte, eftersom `pdf_path` är
   `None` i det testet.

Kostnaden är att ett miljöfel (som fontbuggen) bränner upp till två
LLM-rundor innan det redovisas. Det accepteras: tystnaden är den bugg som
åtgärdas, och rundorna inträffar bara vid fel.

Accepterad restrisk: om en senare rundas Tectonic-körning lämnar en TRASIG
`{slug}.pdf` bakom sig men ändå returnerar fel (icke-noll) skulle den
kvarhållna sökvägen i punkt 1 peka på den filen. Det byggs ingen ny maskineri
mot det — den observerade felvägen avbryter innan filen skrivs.

### Utanför omfattningen

Bedömningsanvisningens PDF spåras inte i databasen (`set_exam_artifacts` tar
bara `tex_path`/`pdf_path`, och `_serve_artifact` slår upp `{kind}_path` på
versionsraden). Den ligger som fil bredvid provet. Det ändras inte här.

---

## Del 2 — sonden måste sätta glyfer i alla mattestorlekar

### Ändring

Ett uttryck läggs till i fältet `text` på **problemuppgiften** (föräldern med
deluppgifter, populationsmodellen) i `_representative_doc()` i
`tools/seed_tectonic_cache.py` — samma uppgift som redan bär
bokstavsexponenten `$a^{t}$`, så motiveringen hamnar i det befintliga
kommentarsblocket:

```latex
$x^{a \cdot \sqrt{b}}$ och $y^{\frac{c \cdot d}{e}}$
```

- `x^{a \cdot \sqrt{b}}` — script style sätter en bokstav (`ntxmi7`, redan
  seedad) **och en symbolglyf: `\cdot` → `ntxsy7`**
- `y^{\frac{c \cdot d}{e}}` — bråket ligger i script style, så täljare och
  nämnare faller till scriptscript: **bokstäver → `ntxmi5`, `\cdot` →
  `ntxsy5`**

`\sqrt`s rotsymbol är inte dekoration: den sätts via `\radical"270370` —
`\mathchar"1270` är i stället `\surd`s definition (den fristående
bock-symbolen, inte rottecknet `\sqrt` bygger). Slutsatsen är densamma: den
(icke-extensibla) rotsymbolen hämtas ur familj 2 = symbolfonten. Det ger
samma täckning som `\cdot` en gång till, så stegen håller även om en framtida
ändring skulle råka ta bort den ena.

Uttrycket formuleras som en rimlig svensk uppgiftstext så att det
representativa dokumentet förblir trovärdigt.

### Varför fältet `text`

`bedomning.tex.j2:32` renderar `text` som `{\small\itshape …}` medan
`prov.tex.j2` renderar samma fält i normalstorlek. En enda ändring motionerar
alltså båda kontexterna.

Fontfilerna slås upp på **namn** (`ntxsy7`), inte på skalad storlek — därför
räcker det att varje mattestil träffas en gång, oavsett om det sker i
`\small` eller normalstorlek. Någon kryssprodukt `\small` × storlek behövs
inte.

Stegen speglas även in i `PROBE_TEX`, enligt den belt-and-braces-konvention
som redan finns där för `\pic`-figuren.

### Familj 3 (tillägg efter en efterföljande granskning)

Storleksstegen ovan sätter aldrig en glyf i familj 3 (`ntxexx`/`ntxexa`,
newtxmaths utökningsfamilj) — det är inte en storlek utan en EGEN matematisk
familj. `\sum` och `\int` är familj 3 direkt (`\sum` är `\mathchar"1350`,
`\int` är `\mathchar"1352`), och en extensibel parentes
(`\left(...\right)`) samt en stor `\sqrt` över ett bråk når familj 3 genom
att delimiter- respektive rottecknets charlist byggs av staplade familj
3-glyfer. Det bekräftades empiriskt: en bedömning vars uppgiftstext
innehåller

```latex
$\sum_{i=1}^{n} i^2$ och $\int_0^1 f(x)\,dx$ samt
$\left(\frac{n(n+1)}{2}\right)$ och $\sqrt{\frac{x}{2}}$
```

faller under `--only-cached` med samma sorts fel som `ntxsy7`-kraschen, fast
på `"ntxexx"`. Summor och integraler är minst lika vanliga i riktiga
Ma3/Ma4-prov som djupt nästlade exponenter, så luckan var lika angelägen att
täppa till.

Samma uttryck lades därför till i problemuppgiftens `text`-fält (direkt
efter storleksstegen, i samma kommentarsblock) och speglades in i
`PROBE_TEX`, med samma motivering som ovan: `text` motionerar både
`\small`-kontexten i bedömningen och normalstorleken i provet.

---

## Del 3 — tester

| Fil | Test | Vad det låser |
| --- | --- | --- |
| `tests/test_exam.py` | riktig motor: bedömning med storleksstegen OCH familj 3 ger PDF | Eftersom `bin/tectonic/cache/.seeded` finns lägger `compile_pdf` på `--only-cached` — testet återskapar produktionsvillkoret exakt och blir rött på en oseedad cache. Hoppas över när motorn saknas, som sina grannar. |
| `tests/test_routes_exam.py` | stubbad motor: provet lyckas, `… - bedomning` faller | Att en `{"type":"log"}`-rad nämner bedömningen, att `errors` bär posten (med svensk prefix på `message`), att `res["pdf"]` fortfarande pekar på ett prov som EN GÅNG kompilerat (även om en senare runda misslyckas), och att en icke-sista rundas loggrad lovar ett omförsök. |
| `tests/test_tectonic_seed.py` | storleksstegen OCH familj 3-uttrycken finns i sonden | Samma mönster som `test_probe_laddar_amssymb_fore_newtxmath`. |

---

## Del 4 — omseedning (det som faktiskt lagar produktionen)

Cachen är gitignorerad. Ingen commit kan laga en maskin — `python -m
tools.seed_tectonic_cache` måste köras med internet påslaget.

Skriptet tar bort `.seeded` **före** kompileringen, vilket gör att
`compile_pdf` utelämnar `--only-cached`. De saknade `.vf`-filerna hämtas
därmed ner i den befintliga cachen; någon total rensning krävs inte för att
stänga just den här luckan.

**Acceptans efter körning:**

1. `ntxsy7.vf`, `ntxsy5.vf`, `ntxmi5.vf`, `ntxexx.vf` och `ntxexa.vf` (eller
   deras fysiska motsvarigheter) finns i `bin/tectonic/cache/`.
2. `.seeded` är återskriven.
3. Det nya regressionstestet i `tests/test_exam.py` är grönt (både
   storleksstegen och familj 3-uttrycken).

### Logistik

`bin/` finns inte i arbetsgrenens worktree (gitignorerad), så
riktig-motor-testerna hoppas över där. En katalogförbindelse (junction) från
worktreens `bin/` till `E:\Transkribera\bin` gör att de kan köras.
Omseedningen skriver alltså om den riktiga cachen i huvudutcheckningen —
vilket är precis avsikten.

---

## Risk / återställning

- **Del 1** är en lokal ändring i en slinga; återställs med en revert. Värsta
  utfallet är att ett miljöfel kostar två LLM-rundor innan det redovisas.
- **Del 2** ändrar bara sondens innehåll — inga mallar, ingen apparatur i
  drift.
- **Del 4** är den enda ändringen utanför git. Om omseedningen faller lämnas
  cachen **omarkerad** (`.seeded` borta), vilket är det säkra läget:
  `compile_pdf` faller då tillbaka på nätåtkomst i stället för att fastna i
  `--only-cached`. Kör om skriptet med nät på.

---

## Test-grind

`python -m pytest` från repo-roten. Känt undantag enligt `CLAUDE.md`:
`tests/test_hardware.py::test_scan_returns_sane_values` faller i en
hårdvarulös container — inte en regression. Svelte-frontenden berörs inte, så
`npm run check`/`npm run build` behövs inte för den här ändringen.
