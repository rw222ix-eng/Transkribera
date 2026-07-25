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

En genomgång av `bin/tectonic/cache/` visar att felet är bredare än den
rapporterade fonten. Metrikfilen finns, men den virtuella fonten saknas:

| TFM i cachen | `.vf` / fysisk font | Betydelse |
| --- | --- | --- |
| `ntxmi.tfm` | ✅ `ntxmi.vf` + `NewTXMI.pfb` | matte-kursiv, textstorlek |
| `ntxmi7.tfm` | ✅ `ntxmi7.vf` + `NewTXMI7.pfb` | script — seedad av `$a^n$`-arbetet |
| `ntxmi5.tfm` | ❌ **saknas** | scriptscript matte-kursiv — latent |
| `ntxsy.tfm` | ✅ `ntxsy.vf` | symbolfont, textstorlek |
| `ntxsy7.tfm` | ❌ **saknas** | **kraschen ovan** |
| `ntxsy5.tfm` | ❌ **saknas** | scriptscript symbolfont — latent |

Orsaken: TeX laddar en TFM enbart för att läsa mattens fontdimensioner, men
xdvipdfmx behöver `.vf`/fysisk font först när en glyf faktiskt sätts. Sonden
har aldrig **satt en glyf** i de storlekarna. `ntxmi7` är undantaget just för
att någon tidigare la in `$a^n$` i det representativa dokumentet.

Det är alltså tre luckor, inte en — och samma sorts åtgärd stänger alla tre.

### Varför testsviten var grön

`tests/test_exam.py::test_compile_pdf_real_engine_produces_all_three_documents`
passerar: dess fixturprov nästlar aldrig matte djupt nog för att begära
`ntxsy7`. Den befintliga grinden täcker inte fallet.

---

## Beslut

| Fråga | Val |
| --- | --- |
| Vad ska ske när bedömningen faller men provet lyckas? | Försök om via `fix_latex`, behåll provet |
| Hur långt ska sondfixen gå? | Systematisk storleksstege (stänger alla tre luckor) |
| Omseedning | Utförs mot den riktiga cachen i `E:\Transkribera` |

---

## Del 1 — bedömningsfelet ska synas

### Ändring

Kompileringsblocket i approve-slingan (`app/web/routes_exam.py`, ca rad
346–356) blir:

```python
pdf_path, log = exam_pdf.compile_pdf(tex, out_dir, slug)
bed_path = None
if pdf_path is not None and bed is not None:
    bed_path, bed_log = exam_pdf.compile_pdf(bed, out_dir, f"{slug} - bedomning")
    if bed_path is None:
        emit({"type": "log", "msg": "Bedömningsanvisningen gick inte att kompilera …"})
        log = bed_log            # rätt logg går vidare till fix_latex
if pdf_path is not None and (bed is None or bed_path is not None):
    errors = []
    break
if round_ >= exam_gen.MAX_LATEX_ROUNDS:
    errors = [{"path": "latex", "code": "bedomning" if pdf_path else "kompilering",
               "message": log}]
    break
```

### Motivering

En runda räknas som lyckad först när **samtliga** dokument som ska produceras
har kompilerat. Tre egenskaper faller ut:

1. **`log = bed_log` är den bärande raden.** `fix_latex` får bedömningens fel
   i stället för provets tomma logg. Det är vad som gör att omförsöket kan
   reparera t.ex. en trasig `\frac` i fältet `losning` — ett fält som
   `prov.tex.j2` aldrig renderar, så bedömningsanvisningen är det enda
   dokument som kan avslöja felet. Med LLM-genererat innehåll är den
   felklassen realistisk.
2. **Ett fungerande prov kastas aldrig bort.** När rundorna tar slut håller
   `pdf_path` fortfarande provets sökväg, så `result["pdf"]` pekar på provet
   och kvittot förblir sant — samtidigt som `errors` nu bär en synlig post.
3. **Skild `code`.** `"bedomning"` mot `"kompilering"` låter gränssnittet
   skilja "inget prov alls" från "provet är klart, anvisningen saknas".
   Den befintliga assertionen i `test_approve_compile_failure_reports_honestly`
   (`any(e["code"] == "kompilering" …)`) berörs inte, eftersom `pdf_path` är
   `None` i det testet.

Kostnaden är att ett miljöfel (som fontbuggen) bränner upp till två
LLM-rundor innan det redovisas. Det accepteras: tystnaden är den bugg som
åtgärdas, och rundorna inträffar bara vid fel.

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

`\sqrt` är inte dekoration: rottecknet är `\mathchar"1270`, alltså familj 2 =
symbolfonten. Det ger samma täckning som `\cdot` en gång till, så stegen
håller även om en framtida ändring skulle råka ta bort den ena.

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

---

## Del 3 — tester

| Fil | Test | Vad det låser |
| --- | --- | --- |
| `tests/test_exam.py` | riktig motor: bedömning med stegen ger PDF | Eftersom `bin/tectonic/cache/.seeded` finns lägger `compile_pdf` på `--only-cached` — testet återskapar produktionsvillkoret exakt och blir rött på en oseedad cache. Hoppas över när motorn saknas, som sina grannar. |
| `tests/test_routes_exam.py` | stubbad motor: provet lyckas, `… - bedomning` faller | Att en `{"type":"log"}`-rad nämner bedömningen, att `errors` bär posten, och att `res["pdf"]` fortfarande pekar på provet. |
| `tests/test_tectonic_seed.py` | stegen finns i sonden | Samma mönster som `test_probe_laddar_amssymb_fore_newtxmath`. |

---

## Del 4 — omseedning (det som faktiskt lagar produktionen)

Cachen är gitignorerad. Ingen commit kan laga en maskin — `python -m
tools.seed_tectonic_cache` måste köras med internet påslaget.

Skriptet tar bort `.seeded` **före** kompileringen, vilket gör att
`compile_pdf` utelämnar `--only-cached`. De saknade `.vf`-filerna hämtas
därmed ner i den befintliga cachen; någon total rensning krävs inte för att
stänga just den här luckan.

**Acceptans efter körning:**

1. `ntxsy7.vf`, `ntxsy5.vf` och `ntxmi5.vf` (eller deras fysiska motsvarigheter)
   finns i `bin/tectonic/cache/`.
2. `.seeded` är återskriven.
3. Det nya regressionstestet i `tests/test_exam.py` är grönt.

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
