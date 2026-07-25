# Bedömningens tysta kompileringsfel + fontseedning — implementationsplan

> **För agentiska arbetare:** OBLIGATORISK UNDERSKILL: använd
> superpowers:subagent-driven-development (rekommenderas) eller
> superpowers:executing-plans för att genomföra planen uppgift för uppgift.
> Stegen använder kryssrutor (`- [ ]`) för avprickning.

**Mål:** Bedömningsanvisningens kompileringsfel ska synas i SSE-strömmen i
stället för att svaljas, och den seedade Tectonic-cachen ska innehålla de
virtuella fonterna för matte i script- och scriptscript-storlek.

**Arkitektur:** Två oberoende fixar i `app/` som hänger ihop genom att den
första dolde den andra. Del 1 är en lokal ändring i approve-slingans
kompileringsblock: en runda räknas som lyckad först när samtliga dokument
kompilerat, och bedömningens logg går vidare till `fix_latex` i stället för
provets tomma. Del 2 lägger en matte-"storleksstege" i sondens representativa
dokument så att glyfer faktiskt sätts i alla tre mattestorlekar, följt av en
omseedning av den riktiga cachen.

**Teknikstack:** Python 3, FastAPI (SSE via `sse_response`), pytest, Jinja2
(LaTeX-mallar med `((( … )))`-delimitrar), Tectonic.

**Spec:** `docs/superpowers/specs/2026-07-25-bedomning-tyst-fel-och-fontseedning-design.md`

## Globala villkor

- Allt körs lokalt/offline. Ingen elev- eller lektionsdata lämnar maskinen.
- Svenska i UI-strängar, loggrader och användarvända texter.
- Test-grind: `python -m pytest` från repo-roten. Känt undantag:
  `tests/test_hardware.py::test_scan_returns_sane_values` faller i en
  hårdvarulös container — inte en regression.
- Svelte-frontenden berörs inte: `npm run check`/`npm run build` behövs inte.
- Conventional Commits på svenska. En logisk ändring per commit.
- Arbetsgren: `claude/musing-cohen-c9e1b2`. Merge till `main` kräver att
  människan säger till — gör det inte på eget bevåg.
- `escape_mixed` i `app/exam_latex.py` gör om `$…$` till `\( … \)` i den
  renderade LaTeX-koden. Assertions mot renderad tex måste därför matcha
  matte-kroppen **utan** delimitrar.

---

## Filstruktur

| Fil | Ansvar | Uppgift |
| --- | --- | --- |
| `app/web/routes_exam.py` | approve-slingans kompileringsblock | 1 |
| `tests/test_routes_exam.py` | SSE-beteende med stubbad motor | 1 |
| `tests/test_exam.py` | riktig-motor-regression (fontstegen) | 2 |
| `tools/seed_tectonic_cache.py` | sondens representativa dokument + `PROBE_TEX` | 3 |
| `tests/test_tectonic_seed.py` | fäster stegen i sonden | 3 |
| `bin/tectonic/cache/` (gitignorerad) | den faktiska fontcachen | 4 |

---

### Uppgift 1: Bedömningsfelet ska synas i strömmen

**Filer:**
- Ändra: `app/web/routes_exam.py:346-356`
- Test: `tests/test_routes_exam.py` (nytt test efter
  `test_approve_compile_failure_reports_honestly`, ca rad 196)

**Gränssnitt:**
- Använder: `_make_exam`, `_events`, `_done` (finns redan i testfilen);
  `exam_pdf.compile_pdf(tex, out_dir, jobname, **kw) -> (Path | None, str)`;
  `exam_gen.MAX_LATEX_ROUNDS == 2`
- Producerar: en post i `result["errors"]` med `code == "bedomning"` när
  provet kompilerat men bedömningen inte. Befintlig `code == "kompilering"`
  behålls oförändrad för fallet "inget prov alls".

- [ ] **Steg 1: Skriv det fallerande testet**

Lägg till i `tests/test_routes_exam.py` direkt efter
`test_approve_compile_failure_reports_honestly`:

```python
def test_approve_bedomning_failure_surfaces_and_keeps_prov(client, monkeypatch):
    """Bedömningsanvisningens returvärde kastades bort: föll den kom varken
    logg eller errors-post, och kvittot stod kvar på 'PDF skapad'. Läraren
    upptäckte det först vid rättningen. Felet ska SYNAS — men ett fungerande
    prov får inte kastas bort bara för att det sekundära dokumentet föll."""
    result, _ = _make_exam(client, monkeypatch)
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)

    sedda_loggar = []

    def fake_compile(tex, out_dir, jobname, **kw):
        if jobname.endswith("bedomning"):
            return None, ('Could not locate a virtual/physical font for '
                          'TFM "ntxsy7".')
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{jobname}.pdf"
        p.write_bytes(b"%PDF-1.5 fejk")
        return p, ""
    monkeypatch.setattr(exam_pdf, "compile_pdf", fake_compile)

    def fake_fix(exam, log, **kw):
        sedda_loggar.append(log)
        return {"exam": exam, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "fix_latex", fake_fix)

    r = client.post(f"/api/exams/{result['id']}/approve", json={})
    evs = _events(r)
    res = _done(r)

    assert any(e["type"] == "log" and "edömningsanvisningen" in e.get("msg", "")
               for e in evs), "felet nämndes aldrig i strömmen"
    bed = [e for e in res["errors"] if e["code"] == "bedomning"]
    assert bed, f"ingen bedömningspost i errors: {res['errors']}"
    assert "ntxsy7" in bed[0]["message"]
    assert res["pdf"], "det fungerande provet ska INTE kastas bort"
    assert res["status"] == "godkänt"
    # fix_latex måste få BEDÖMNINGENS logg — provets är tom, och en tom logg
    # ger modellen ingenting att korrigera.
    assert sedda_loggar and all("ntxsy7" in lg for lg in sedda_loggar)
```

- [ ] **Steg 2: Kör testet och bekräfta att det faller**

```bash
python -m pytest tests/test_routes_exam.py::test_approve_bedomning_failure_surfaces_and_keeps_prov -v
```

Förväntat: FAIL på `assert any(e["type"] == "log" …)` — "felet nämndes aldrig
i strömmen". Nuvarande kod kastar bort returvärdet, så inget emitteras.

- [ ] **Steg 3: Ändra kompileringsblocket**

I `app/web/routes_exam.py`, ersätt raderna 346–356:

```python
                    emit({"type": "log", "msg": "Kompilerar PDF …"})
                    pdf_path, log = exam_pdf.compile_pdf(tex, out_dir, slug)
                    if pdf_path is not None:
                        if bed is not None:
                            exam_pdf.compile_pdf(bed, out_dir, f"{slug} - bedomning")
                        errors = []
                        break
                    if round_ >= exam_gen.MAX_LATEX_ROUNDS:
                        errors = [{"path": "latex", "code": "kompilering",
                                   "message": log}]
                        break
```

med (detta utkast visade sig ha två hål som en efterföljande granskning
hittade — se "Efterföljande granskning" i slutet av denna uppgift för vad
som faktiskt landade):

```python
                    emit({"type": "log", "msg": "Kompilerar PDF …"})
                    pdf_path, log = exam_pdf.compile_pdf(tex, out_dir, slug)
                    # En runda är lyckad först när SAMTLIGA dokument som ska
                    # produceras har kompilerat. Bedömningens returvärde
                    # kastades tidigare bort: föll den syntes ingenting alls
                    # och kvittot ljög om att allt gått bra.
                    bed_path = None
                    if pdf_path is not None and bed is not None:
                        bed_path, bed_log = exam_pdf.compile_pdf(
                            bed, out_dir, f"{slug} - bedomning")
                        if bed_path is None:
                            emit({"type": "log",
                                  "msg": "Bedömningsanvisningen gick inte att "
                                         "kompilera — försöker korrigera …"})
                            # Bedömningsmallen renderar losning/bedomning, som
                            # prov.tex.j2 aldrig rör. Ett trasigt fält där kan
                            # bara avslöjas här — och fix_latex behöver DEN
                            # loggen, inte provets tomma.
                            log = bed_log
                    if pdf_path is not None and (bed is None or bed_path is not None):
                        errors = []
                        break
                    if round_ >= exam_gen.MAX_LATEX_ROUNDS:
                        # Provet behålls om det kompilerade: ett fungerande
                        # prov kastas inte bort för att det sekundära
                        # dokumentet föll. Skild kod låter gränssnittet skilja
                        # "inget prov alls" från "anvisningen saknas".
                        errors = [{"path": "latex",
                                   "code": "bedomning" if pdf_path else "kompilering",
                                   "message": log}]
                        break
```

**VARNING — detta utkast är INTE vad som landade.** En efterföljande
granskning hittade två hål:

1. Loggraden skrivs ovillkorligt med "— försöker korrigera …", även på den
   SISTA rundan (`round_ >= MAX_LATEX_ROUNDS`), när inget omförsök längre
   sker. Grenen `arbiter.ensure_llm() is None` (ingen körande modell) saknas
   också helt — den föll fortfarande tillbaka på den hårdkodade
   `"kompilering"`-koden i stället för `"bedomning"`.
2. `pdf_path` sätts om till DENNA rundas kompileringsresultat varje varv. Om
   provet kompilerar i runda 0 men bedömningen faller, och `fix_latex` i en
   SENARE runda skriver om provet till något som inte längre går att
   kompilera, blev `pdf_path` `None` — trots att runda 0:s fungerande
   prov-PDF fortfarande låg kvar i utkatalogen. Ett fullt användbart prov
   blev då oåtkomligt för läraren.

Det som faktiskt landade (se `app/web/routes_exam.py`, ca rad 346–408, och
Del 1 i spec-dokumentet för den fullständiga motiveringen):

```python
                    emit({"type": "log", "msg": "Kompilerar PDF …"})
                    prov_pdf, log = exam_pdf.compile_pdf(tex, out_dir, slug)
                    # Ett prov som EN GÅNG kompilerat får inte försvinna för att
                    # en senare korrigeringsrunda (utlöst av bedömningen) skrev
                    # om provet till något som inte går att kompilera. Filen
                    # ligger kvar i utkatalogen — behåll sökvägen så länge den
                    # gör det.
                    if prov_pdf is not None:
                        pdf_path = prov_pdf
                    elif pdf_path is not None and not pdf_path.exists():
                        pdf_path = None
                    # En runda är lyckad först när SAMTLIGA dokument som ska
                    # produceras har kompilerat. Bedömningens returvärde
                    # kastades tidigare bort: föll den syntes ingenting alls
                    # och kvittot ljög om att allt gått bra.
                    bed_path = None
                    bed_misslyckades = False
                    if prov_pdf is not None and bed is not None:
                        bed_path, bed_log = exam_pdf.compile_pdf(
                            bed, out_dir, f"{slug} - bedomning")
                        if bed_path is None:
                            bed_misslyckades = True
                            # Bedömningsmallen renderar losning/bedomning, som
                            # prov.tex.j2 aldrig rör. Ett trasigt fält där kan
                            # bara avslöjas här — och fix_latex behöver DEN
                            # loggen, inte provets tomma.
                            log = bed_log
                    if prov_pdf is not None and (bed is None or bed_path is not None):
                        errors = []
                        break
                    # Avgör FÖRE loggraden om en korrigering faktiskt följer —
                    # annars lovar strömmen ett omförsök som aldrig sker.
                    sista_forsoket = (round_ >= exam_gen.MAX_LATEX_ROUNDS
                                      or arbiter.ensure_llm() is None)
                    if bed_misslyckades:
                        emit({"type": "log",
                              "msg": "Bedömningsanvisningen gick inte att kompilera."
                                     if sista_forsoket else
                                     "Bedömningsanvisningen gick inte att "
                                     "kompilera — försöker korrigera …"})
                    if sista_forsoket:
                        # Provet behålls om det NÅGON gång kompilerat: ett
                        # fungerande prov kastas inte bort för att en SENARE
                        # rundas kompilering (utlöst av bedömningen) föll.
                        felkod = "bedomning" if pdf_path else "kompilering"
                        # message PERSISTERAS (loggraden ovan är transient) —
                        # prefixa med svensk mening så gränssnittet, som
                        # renderar message rått utan att läsa code, aldrig
                        # visar en ensam engelsk Tectonic-loggrad.
                        meddelande = (
                            ("Bedömningsanvisningen gick inte att kompilera:\n"
                             + log) if felkod == "bedomning" else log)
                        errors = [{"path": "latex", "code": felkod,
                                   "message": meddelande}]
                        break
```

Motsvarande test i `tests/test_routes_exam.py` utökades med
`test_approve_prov_fran_tidigare_runda_overlever_senare_kompileringsfel`
(hål 2), assertions på det svenskprefixade `message` (svensk prefix), och en
pinning av att en icke-sista rundas loggrad faktiskt lovar ett omförsök (hål
1, `bed_loggar[:-1]`).

- [ ] **Steg 4: Kör testet och bekräfta att det passerar**

```bash
python -m pytest tests/test_routes_exam.py -v
```

Förväntat: PASS, inklusive det befintliga
`test_approve_compile_failure_reports_honestly` (där `pdf_path` är `None`, så
koden förblir `"kompilering"`) och
`test_approve_with_stubbed_engine_sets_pdf` (där båda kompileringarna lyckas).

- [ ] **Steg 5: Commit**

```bash
git add app/web/routes_exam.py tests/test_routes_exam.py
git commit -m "fix(prov): bedömningsanvisningens kompileringsfel svaldes tyst"
```

---

### Uppgift 2: Riktig-motor-regression som återskapar ntxsy7-kraschen

Testet blir **rött** och förblir rött till och med uppgift 4. Det är avsikten:
det är kraschen från den skarpa körningen, fångad i sviten.

**Filer:**
- Skapa: katalogförbindelse `bin` → `E:\Transkribera\bin` (utanför git)
- Test: `tests/test_exam.py` (nytt test efter
  `test_compile_pdf_real_engine_produces_all_three_documents`, ca rad 1098)

**Gränssnitt:**
- Använder: `_exam()`, `copy`, `pytest`, `exam_spec.validate_exam_json`,
  `exam_latex.render_bedomning`, `exam_pdf.compile_pdf`,
  `exam_pdf.engine_available` — allt redan importerat i filen.
- Producerar: inget som senare uppgifter konsumerar.

- [ ] **Steg 1: Länka in motorn i worktreen**

`bin/` är gitignorerad och finns inte i worktreen, så alla riktig-motor-tester
hoppas över där. Kör i PowerShell:

```powershell
New-Item -ItemType Junction -Path "E:\Transkribera\.claude\worktrees\frosty-thompson-621419\bin" -Target "E:\Transkribera\bin"
```

- [ ] **Steg 2: Bekräfta att motorn nu syns**

```bash
python -c "from app import exam_pdf; print(exam_pdf.engine_available(), exam_pdf.engine_dir())"
```

Förväntat: `True E:\...\frosty-thompson-621419\bin\tectonic`

Kör sedan den befintliga riktig-motor-testen för att bekräfta att den
verkligen körs (inte hoppas över) och är grön på nuvarande cache:

```bash
python -m pytest tests/test_exam.py::test_compile_pdf_real_engine_produces_all_three_documents -v
```

Förväntat: PASS (inte SKIPPED). Fixturprovet nästlar aldrig matte djupt nog
för att begära `ntxsy7` — det är just därför luckan kunde smyga förbi.

- [ ] **Steg 3: Skriv det fallerande testet**

Lägg till i `tests/test_exam.py` direkt efter
`test_compile_pdf_real_engine_produces_all_three_documents`:

```python
def test_compile_pdf_real_engine_bedomning_med_djupt_nastlad_matte(tmp_path):
    """Fältet text renderas som {\\small\\itshape …} i bedomning.tex.j2.
    Matte som nästlar ner i script- och scriptscript-storlek hämtar då
    symbolfonten och matte-kursiven i 7 pt och 5 pt (ntxsy7/ntxsy5/ntxmi5).
    Cachen hade bara metrikfilerna (.tfm) för dem — aldrig de virtuella
    fonterna — eftersom sonden aldrig SATT en glyf i de storlekarna: TeX
    laddar en .tfm enbart för mattens fontdimensioner, medan xdvipdfmx
    behöver .vf först när en glyf faktiskt sätts. Med --only-cached (aktivt
    så fort .seeded finns) kraschade Tectonic på skarpa prov med
    'Could not locate a virtual/physical font for TFM "ntxsy7"' medan provet
    kompilerade felfritt."""
    if not exam_pdf.engine_available():
        pytest.skip("Tectonic-motorn saknas (bin/tectonic/tectonic.exe)")

    data = copy.deepcopy(_exam())
    # \cdot i en exponent → symbolglyf i script-storlek (ntxsy7).
    # \frac i en exponent → täljare/nämnare i scriptscript (ntxmi5/ntxsy5).
    data["uppgifter"][0]["text"] = (
        "Förenkla $x^{a \\cdot \\sqrt{b}}$ och bestäm sedan "
        "$y^{\\frac{c \\cdot d}{e}}$ då $b = 4$.")
    doc, errors = exam_spec.validate_exam_json(data)
    assert doc is not None and errors == []

    pdf, logg = exam_pdf.compile_pdf(
        exam_latex.render_bedomning(doc), tmp_path, "bedomning")
    assert pdf is not None and pdf.exists(), f"bedömningen misslyckades: {logg}"
    assert pdf.stat().st_size > 0
```

- [ ] **Steg 4: Kör testet och bekräfta att det faller — med RÄTT fel**

```bash
python -m pytest tests/test_exam.py::test_compile_pdf_real_engine_bedomning_med_djupt_nastlad_matte -v
```

Förväntat: FAIL med `bedömningen misslyckades:` följt av
`Could not locate a virtual/physical font for TFM "ntxsy7"`.

Faller det på något annat — stanna och läs loggen. Ett annat fel betyder att
testet reproducerar fel sak.

- [ ] **Steg 5: Commit**

Testet committas rött, med motiveringen i commit-meddelandet. Det görs grönt
av uppgift 3 + 4.

```bash
git add tests/test_exam.py
git commit -m "test(prov): fånga ntxsy7-kraschen i bedömningen (röd tills cachen seedats om)"
```

---

### Uppgift 3: Storleksstege i sonden

**Filer:**
- Ändra: `tools/seed_tectonic_cache.py` — `PROBE_TEX` (ca rad 80) och
  `_representative_doc()`s problemuppgift (ca rad 173)
- Test: `tests/test_tectonic_seed.py`

**Gränssnitt:**
- Använder: `seed_tectonic_cache.PROBE_TEX`,
  `seed_tectonic_cache._representative_doc() -> exam_spec.ExamDoc`,
  `exam_latex.render_bedomning(doc, bilder=None) -> str`
- Producerar: sondens dokument innehåller `x^{a \cdot \sqrt{b}}` och
  `y^{\frac{c \cdot d}{e}}`, vilket uppgift 4 seedar in i cachen.

- [ ] **Steg 1: Skriv det fallerande testet**

Lägg till överst i `tests/test_tectonic_seed.py` en import, och testet sist i
filen:

```python
from app import exam_latex
```

```python
def test_sonden_satter_glyfer_i_alla_mattestorlekar():
    """ntxsy7/ntxsy5/ntxmi5 hämtas ner först när en glyf FAKTISKT sätts i
    script- respektive scriptscript-storlek. Enbart en \\frac räcker inte:
    bråkstrecket är en linje, inte en glyf, och TeX nöjer sig då med .tfm-
    metriken — xdvipdfmx faller senare på 'Could not locate a virtual/
    physical font'. Därför måste både en symbol (\\cdot, \\sqrt) och en
    bokstav finnas på varje nivå.

    escape_mixed gör om $…$ till \\(…\\), så matte-kroppen matchas utan
    delimitrar."""
    tex = exam_latex.render_bedomning(
        seed_tectonic_cache._representative_doc())
    assert r"x^{a \cdot \sqrt{b}}" in tex, \
        "symbolglyf i script-storlek (ntxsy7) seedas aldrig"
    assert r"y^{\frac{c \cdot d}{e}}" in tex, \
        "glyfer i scriptscript-storlek (ntxmi5/ntxsy5) seedas aldrig"
    # Sonden speglar stegen (belt and braces, som \pic-figuren) så att den
    # står kvar även om det representativa dokumentet skrivs om.
    assert r"x^{a \cdot \sqrt{b}}" in seed_tectonic_cache.PROBE_TEX
    assert r"y^{\frac{c \cdot d}{e}}" in seed_tectonic_cache.PROBE_TEX
```

- [ ] **Steg 2: Kör testet och bekräfta att det faller**

```bash
python -m pytest tests/test_tectonic_seed.py -v
```

Förväntat: FAIL på "symbolglyf i script-storlek (ntxsy7) seedas aldrig".

- [ ] **Steg 3: Lägg stegen i det representativa dokumentet**

I `tools/seed_tectonic_cache.py`, i `_representative_doc()`, byt
problemuppgiftens `text` (populationsmodellen, ca rad 173) från:

```python
                text=r"En population modelleras av $N(t) = N_0 \cdot a^{t}$. "
                     r"Undersök hur populationen växer.",
```

till:

```python
                text=r"En population modelleras av $N(t) = N_0 \cdot a^{t}$. "
                     r"Undersök hur populationen växer. Förenkla också "
                     r"$x^{a \cdot \sqrt{b}}$ och $y^{\frac{c \cdot d}{e}}$.",
```

Utöka samma uppgifts kommentarsblock (det som redan förklarar
bokstavsexponenten) med storleksstegen — lägg till sist i blocket, före
`text=`:

```python
                # STORLEKSSTEGE: fontfilerna slås upp på NAMN (ntxsy7), inte
                # på skalad storlek, så det räcker att varje mattestil träffas
                # en gång — men den måste träffas av en riktig GLYF.
                #   x^{a \cdot \sqrt{b}} → script: bokstav (ntxmi7) OCH symbol
                #                          (\cdot, \sqrt → familj 2 = ntxsy7)
                #   y^{\frac{c \cdot d}{e}} → bråket ligger i script, så
                #                          täljare/nämnare faller till
                #                          scriptscript: ntxmi5 + ntxsy5
                # Utan detta hämtades bara .tfm-metriken och --only-cached
                # kraschade på skarpa prov med "Could not locate a virtual/
                # physical font for TFM ntxsy7" (skarp körning 2026-07-25).
```

- [ ] **Steg 4: Spegla stegen i PROBE_TEX**

I samma fil, i `PROBE_TEX`, byt raderna:

```latex
Sond för cacheseedning. Matematik: $x^2 - 4x + 3 = 0$,
$\frac{a}{b} \geq \sqrt{c} \neq \pm\infty$, $\alpha \cdot \beta \leq \Sigma$.
```

till:

```latex
Sond för cacheseedning. Matematik: $x^2 - 4x + 3 = 0$,
$\frac{a}{b} \geq \sqrt{c} \neq \pm\infty$, $\alpha \cdot \beta \leq \Sigma$.
Storleksstege (text → script → scriptscript, glyf på varje nivå):
$x^{a \cdot \sqrt{b}}$ och $y^{\frac{c \cdot d}{e}}$.
```

- [ ] **Steg 5: Kör testerna och bekräfta att de passerar**

```bash
python -m pytest tests/test_tectonic_seed.py -v
```

Förväntat: PASS, alla fem tester.

- [ ] **Steg 6: Commit**

```bash
git add tools/seed_tectonic_cache.py tests/test_tectonic_seed.py
git commit -m "fix(seed): sonden sätter glyfer i script- och scriptscript-storlek"
```

**Efterföljande granskning: familj 3 saknades fortfarande.** Stegen ovan
sätter aldrig en glyf i familj 3 (`ntxexx`/`ntxexa`, newtxmaths
utökningsfamilj) — det är inte en storlek utan en EGEN matematisk familj.
`\sum`/`\int` är familj 3 direkt, och `\left(...\right)` samt en stor
`\sqrt` över ett bråk når familj 3 genom delimiter- respektive
rottecknets charlist. Verifierat empiriskt: en bedömning med

```latex
$\sum_{i=1}^{n} i^2$ och $\int_0^1 f(x)\,dx$ samt
$\left(\frac{n(n+1)}{2}\right)$ och $\sqrt{\frac{x}{2}}$
```

i uppgiftstexten faller under `--only-cached` med samma sorts fel som
`ntxsy7`-kraschen, fast på `"ntxexx"`. Samma uttryck lades till direkt
efter storleksstegen i problemuppgiftens `text`-fält och speglades in i
`PROBE_TEX`, och pinnades i `tests/test_tectonic_seed.py` samt i
`test_compile_pdf_real_engine_bedomning_med_djupt_nastlad_matte` i
`tests/test_exam.py` (se Del 2/"Familj 3" i spec-dokumentet). Committat
separat: `fix(seed): sonden når aldrig mattefamilj 3 (ntxexx/ntxexa)`.

---

### Uppgift 4: Seeda om cachen

Detta är steget som faktiskt lagar produktionen — cachen är gitignorerad, så
ingen commit kan laga en maskin.

**Filer:**
- Ändra: `bin/tectonic/cache/` (via junction → `E:\Transkribera\bin`)

**Gränssnitt:**
- Använder: `tools/seed_tectonic_cache.main()` via `python -m`
- Producerar: en cache som gör uppgift 2:s test grönt.

- [ ] **Steg 1: Dokumentera utgångsläget**

```bash
find bin/tectonic/cache -iname "ntxsy7.*" -o -iname "ntxsy5.*" -o -iname "ntxmi5.*" \
  -o -iname "ntxexx.*" -o -iname "ntxexa.*"
```

Förväntat före omseedning: bara `.tfm`-filer, inga `.vf` (familj 3-tillägget
i denna plans Uppgift 3 lades till EFTER att detta ursprungligen skrevs —
`ntxexx`/`ntxexa` täcktes inte av den första omseedningen).

- [ ] **Steg 2: Kör omseedningen**

Kräver internet. Skriptet tar bort `.seeded` först, vilket gör att
`compile_pdf` utelämnar `--only-cached` och kan hämta det som saknas. Fyra
kompileringar (prov, arbetsblad, bedömning, sond) — räkna med några minuter.

```bash
python -m tools.seed_tectonic_cache
```

Förväntat: `KLART: cachen är seedad (prov, arbetsblad, bedömning, tikz/pgfplots)`

Faller den: cachen lämnas **omarkerad** (`.seeded` borta), vilket är det säkra
läget — `compile_pdf` faller då tillbaka på nätåtkomst i stället för att
fastna i `--only-cached`. Läs felmeddelandet och kör om med nät på.

- [ ] **Steg 3: Verifiera att fonterna nu finns**

```bash
find bin/tectonic/cache -iname "ntxsy7.*" -o -iname "ntxsy5.*" -o -iname "ntxmi5.*" \
  -o -iname "ntxexx.*" -o -iname "ntxexa.*"
```

Förväntat: nu även `.vf` (eller motsvarande fysiska fonter) för alla fem.
Bekräfta också att markören är återskriven:

```bash
ls -la bin/tectonic/cache/.seeded
```

- [ ] **Steg 4: Bekräfta att uppgift 2:s röda test blivit grönt**

```bash
python -m pytest tests/test_exam.py -k real_engine -v
```

Förväntat: PASS för samtliga riktig-motor-tester, inklusive
`test_compile_pdf_real_engine_bedomning_med_djupt_nastlad_matte`.

Detta är det avgörande beviset: `.seeded` finns igen, så `compile_pdf` kör med
`--only-cached` — testet bevisar att cachen själv innehåller fonterna.

- [ ] **Steg 5: Ingen commit**

Cachen är gitignorerad; det finns inget att committa här. Notera i stället
resultatet från steg 3 och 4 i rapporten till människan.

---

### Uppgift 5: Full grind och slutrapport

**Filer:** inga ändringar — enbart verifiering.

- [ ] **Steg 1: Kör hela sviten**

```bash
python -m pytest
```

Förväntat: grönt, med det kända undantaget
`tests/test_hardware.py::test_scan_returns_sane_values` om körningen sker utan
hårdvara.

- [ ] **Steg 2: Kontrollera diffen mot main**

```bash
git diff main...HEAD --stat
```

Förväntat: `app/web/routes_exam.py`, `tools/seed_tectonic_cache.py`,
`tests/test_exam.py`, `tests/test_routes_exam.py`,
`tests/test_tectonic_seed.py` samt spec- och plandokumenten. Inga hemligheter,
ingen felsökningsutskrift, ingen bortkommenterad kod.

- [ ] **Steg 3: Rapportera till människan**

Redovisa: testresultat ordagrant, vilka fontfiler som tillkom i cachen, och
att merge till `main` väntar på besked. Push till arbetsgrenen är förhandsgodkänt.

---

## Kända fallgropar

- **Testet i uppgift 2 hoppas över utan junction.** `pytest` rapporterar då
  SKIPPED, inte FAILED — grönt betyder ingenting. Kontrollera alltid att
  `engine_available()` är `True` innan slutsatser dras.
- **`escape_mixed` skriver om `$…$` till `\(…\)`.** Assertions mot renderad
  LaTeX måste matcha matte-kroppen utan delimitrar.
- **`\frac` ensamt räcker inte.** Bråkstrecket är en linje, inte en glyf.
  Utan `\cdot`/`\sqrt` och en bokstav på varje nivå hämtas bara `.tfm`.
- **Ta inte bort `.seeded` för hand.** Seedningsskriptet gör det själv, i rätt
  ordning. En halvfärdig cache med markören kvar låser `--only-cached` för gott.
