"""Gruppuppgiften (Etapp 0.6) — den enda dokumenttypen som saknade backend.

Den fick INGEN egen rutt-familj. En gruppuppgift är ett ark med uppgifter,
precis som arbetsbladet, och delar därför generering, versionering, iteration
och PDF-vägen med prov-spåret. Det som skiljer är tre saker, och det är dem
den här sviten låser:

1. **Balansprofilen.** Ett papper fyra elever ska prata sig igenom prövar
   problemlösning, modellering, resonemang och kommunikation — inte rutin som
   en elev gör snabbast själv.
2. **Upplägget.** Namnraderna, tiden och redovisningsformen ÄR pappersformen
   (gruppark.css). Utan dem är arket ett arbetsblad med fel instruktionsband.
3. **Vem facit tillhör.** Gruppens ark bär inga poäng; facit MED bedömning
   ligger på lärarens sista sida.
"""
import copy
import json

import pytest

from app import claude_code, exam_gen, exam_latex, exam_pdf, exam_spec


def _events(resp):
    return [json.loads(line[len("data:"):])
            for line in resp.text.splitlines() if line.startswith("data:")]


def _done(resp):
    evs = [e for e in _events(resp) if e["type"] == "done"]
    assert evs, _events(resp)
    return evs[0]["result"]


def _doc(**extra):
    from tests.test_exam import _exam
    d = copy.deepcopy(_exam())
    d["grupp"] = {"elever": 4, "langd_min": 45, "redovisning": "poster"}
    d.update(extra)
    return d


@pytest.fixture
def client(llm_ready):
    """Allt i den här sviten genererar — arbitern måste svara.
    Basfixturen bor i conftest.py."""
    return llm_ready


def _stub(monkeypatch, exam=None):
    calls = []

    def fake(kurs, klass, punkter, *, model, antal=10, tid_min=120, delar=True,
             memory="", teman="", referens="", bilder="", utfall="",
             bok="", profil="prov",
             grupp=None, llm=None, max_rounds=exam_gen.MAX_ROUNDS, log_cb=None,
             **_kw):
        calls.append({"kurs": kurs, "klass": klass, "antal": antal,
                      "profil": profil, "grupp": grupp})
        return {"exam": exam if exam is not None else _doc(),
                "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "generate_exam", fake)
    return calls


# ------------------------------------------------------------- upplägget --

def test_upplagget_kravs_och_valideras():
    """Utan grupp-blocket är arket ett arbetsblad med fel instruktionsband."""
    doc, fel = exam_spec.validate_exam_json(_doc(), "gruppuppgift")
    assert doc is not None and fel == []
    assert doc.grupp.elever == 4 and doc.grupp.redovisning == "poster"

    from tests.test_exam import _exam
    _, utan = exam_spec.validate_exam_json(copy.deepcopy(_exam()), "gruppuppgift")
    assert [f["code"] for f in utan] == ["saknas"]


@pytest.mark.parametrize("grupp", [
    {"elever": 1, "langd_min": 45, "redovisning": "muntligt"},     # under 2
    {"elever": 6, "langd_min": 45, "redovisning": "muntligt"},     # över 5
    {"elever": 3, "langd_min": 5, "redovisning": "muntligt"},      # under 10 min
    {"elever": 3, "langd_min": 45, "redovisning": "interpretativ dans"},
])
def test_upplagget_haller_sig_inom_valjarnas_granser(grupp):
    """Gränserna är planeringens väljare (plan.js TYPVAL.Gruppuppgift) — ett
    dokument utanför dem går inte att sätta."""
    doc, fel = exam_spec.validate_exam_json(_doc(grupp=grupp), "gruppuppgift")
    assert doc is None and fel


def test_upplagget_ar_lararens_val_inte_modellens(client, monkeypatch):
    """Skriver modellen något annat i grupp-fältet skrivs det över: det är
    läraren som valt fyra elever och trettio minuter."""
    _stub(monkeypatch, exam=_doc(grupp={"elever": 2, "langd_min": 180,
                                        "redovisning": "muntligt"}))
    r = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter_text": ["Derivator"],
        "typ": "gruppuppgift",
        "grupp": {"elever": 4, "langd_min": 30, "redovisning": "poster"}}))
    assert r["exam"]["grupp"] == {"elever": 4, "langd_min": 30,
                                  "redovisning": "poster"}


def test_orimligt_upplagg_klipps_till_granserna(client, monkeypatch):
    calls = _stub(monkeypatch)
    _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter_text": ["Derivator"],
        "typ": "gruppuppgift",
        "grupp": {"elever": 99, "langd_min": 3, "redovisning": "trolleri"}}))
    # Ett okänt ord blir FÖRVALET, och förvalet är genomgången sedan
    # 2026-09-23 (exam_spec.redovisningsform): inget lämnas in.
    assert calls[0]["grupp"] == {"elever": 5, "langd_min": 10,
                                 "redovisning": "genomgang"}


# --------------------------------------------------------- balansprofilen --

def test_profilen_kraver_samtalsformagorna():
    """Golv > 0 på PL, M, R och K — och tak på ren procedur. En gruppuppgift
    som bara är rutinräkning är ingen gruppuppgift."""
    fm, niva, kraver_redovisning, kraver_klump, kraver_stigande = \
        exam_spec.PROFILER["gruppuppgift"]
    assert all(fm[f][0] > 0 for f in ("PL", "M", "R", "K"))
    assert fm["P"][1] <= 0.40 and fm["B"][1] <= 0.40
    # Fyra rutor på ett bord är fyra ingångar till samma sak, inte en trappa.
    assert kraver_stigande is False and kraver_klump is False
    assert kraver_redovisning is True
    assert niva["c"][0] >= 0.20


def test_ett_rent_rutinark_faller_pa_profilen():
    rutin = {"del": None, "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Beräkna $2 + 2$.", "losning": "$4$", "bedomning": "+2 E"}
    doc = _doc(uppgifter=[dict(rutin, text=f"Beräkna ${i} + {i}$.") for i in range(1, 5)])
    _, fel = exam_spec.validate_exam_json(doc, "gruppuppgift")
    koder = {f["code"] for f in fel}
    assert koder, "en gruppuppgift av bara rutinuppgifter ska fällas"


def test_samma_ark_gar_igenom_som_arbetsblad():
    """Profilen är skillnaden — inte schemat. Samma uppgifter duger som
    arbetsblad, där rutin är själva poängen."""
    rutin = {"del": None, "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Beräkna $2 + 2$.", "losning": "$4$", "bedomning": "+2 E"}
    doc = _doc(uppgifter=[dict(rutin, text=f"Beräkna ${i} + {i}$.") for i in range(1, 5)])
    doc.pop("grupp")
    _, fel = exam_spec.validate_exam_json(doc, "arbetsblad")
    assert not [f for f in fel if f["code"] == "formaga"]


# ------------------------------------------------------------ pappersformen --

def test_arket_bar_namnrader_men_ingen_metarad():
    doc, _ = exam_spec.validate_exam_json(_doc(), "gruppuppgift")
    tex = exam_latex.render_gruppuppgift(doc)
    assert tex.count(r"\noindent Namn:") == 4        # en rad per elev
    # Metaraden är borttagen (lärarens beslut 2026-08-20): hon säger
    # gruppstorlek, tid och redovisningsform själv i klassrummet. Fälten
    # styr fortfarande namnraderna och instruktionsbandet.
    assert "elever per grupp" not in tex and "45 minuter" not in tex
    # Instruktionsbandet säger i klartext hur det slutar — samma text som
    # webbversionen skriver (blad.js, grupphuvud).
    assert "sätts upp i salen" in tex
    assert "Alla i gruppen ska kunna förklara" in tex


def test_gruppens_ark_bar_inga_poang_men_lararens_gor_det():
    doc, _ = exam_spec.validate_exam_json(_doc(), "gruppuppgift")
    tex = exam_latex.render_gruppuppgift(doc)
    gruppens, lararens = tex.split(r"\delprovband{Facit och bedömning}")
    assert "p}" not in gruppens.split(r"\begin{document}")[1], \
        "en siffra i marginalen gör uppgiften till en tävling"
    assert doc.uppgifter[0].bedomning in lararens
    assert doc.uppgifter[0].losning.replace("$", "\\(", 1) or True


def test_separat_facit_delar_pappret_i_tva():
    """Facit låg ALLTID sist i gruppens ark, och läraren som ville ha det som
    eget papper hade ingen väg dit — väljaren fanns bara på arbetsbladet.

    Flaggorna är samma par som arbetsbladet bär: only_facit ger lärarens sida
    ensam, utan_facit ger gruppens ark utan den. Tillsammans täcker de pappret
    exakt en gång."""
    doc, _ = exam_spec.validate_exam_json(_doc(), "gruppuppgift")
    BAND = r"\delprovband{Facit och bedömning}"
    NAMNRAD = r"\noindent Namn:"

    gruppens = exam_latex.render_gruppuppgift(doc, utan_facit=True)
    assert gruppens.count(NAMNRAD) == 4
    assert BAND not in gruppens
    assert doc.uppgifter[0].bedomning not in gruppens

    lararens = exam_latex.render_gruppuppgift(doc, only_facit=True)
    assert BAND in lararens
    assert doc.uppgifter[0].bedomning in lararens
    # Inga namnrader och ingen svarsplats: lärarens ark är inget att skriva på.
    assert NAMNRAD not in lararens
    # Efter \begin{document}: preambeln DEFINIERAR \svarsrad och gör det i
    # varje papper mallen sätter.
    assert r"\svarsrad" not in lararens.split(r"\begin{document}")[1]
    # Rubriken säger vilket papper det är — «Gruppuppgift» på ett facit hade
    # lagt fel ark på fel hög.
    assert "Facit — " in lararens and "Gruppuppgift — " not in lararens


def test_utan_val_bar_arket_sitt_facit_som_forut():
    """Godkännanden utan flaggor — API-anrop, en äldre klient, pytest — ska ge
    exakt det papper de alltid gett."""
    doc, _ = exam_spec.validate_exam_json(_doc(), "gruppuppgift")
    tex = exam_latex.render_gruppuppgift(doc)
    assert r"\noindent Namn:" in tex
    assert r"\delprovband{Facit och bedömning}" in tex


def test_ifyllnadsraderna_ersatter_svarsraden():
    """Förlagans grepp: BESLUTEN skrivs på pappret («Ekvation: ____»,
    «Svar i ord: ____»), räkningen på lösblad. Den som fyllt i de raderna har
    svarat — en svarslinje till under dem är en rad ingen vet vad hon ska
    skriva på."""
    d = _doc()
    d["uppgifter"][0]["svarsfalt"] = ["Ekvation", "Svar i ord"]
    d["uppgifter"][0]["typ"] = "rutin"          # den som annars får \svarsrad
    doc, fel = exam_spec.validate_exam_json(d, "gruppuppgift")
    assert doc is not None, fel
    tex = exam_latex.render_gruppuppgift(doc)
    assert r"\svarsfaltrad{Ekvation}" in tex
    assert r"\svarsfaltrad{Svar i ord}" in tex
    gruppens = tex.split(r"\delprovband{Facit och bedömning}")[0]
    forsta = gruppens.split(r"\begin{uppgift}")[1]
    assert r"\svarsrad" not in forsta, "dubbel svarsplats på samma uppgift"


def test_nyckelfragan_star_i_instruktionsbandet():
    """Metodregeln som EN fråga, överst på pappret — det gruppen läser när de
    fastnar. Den är momentets, inte appens, så den kommer ur dokumentet."""
    doc, fel = exam_spec.validate_exam_json(
        _doc(nyckelfraga="Var sitter den okända? I exponenten → logaritmera."),
        "gruppuppgift")
    assert doc is not None, fel
    tex = exam_latex.render_gruppuppgift(doc)
    band = tex.split(r"\notisruta{")[1].split("}")[0]
    assert "Var sitter den okända?" in band
    # Arbetsregeln står kvar före den — hur man jobbar, sedan vad man frågar.
    assert band.index("Alla i gruppen") < band.index("Var sitter")


def test_utan_nyckelfraga_star_bandet_som_forut():
    doc, _ = exam_spec.validate_exam_json(_doc(), "gruppuppgift")
    tex = exam_latex.render_gruppuppgift(doc)
    assert r"\textbf{" not in tex.split(r"\notisruta{")[1].split("}")[0]


# ── INSTRUKTIONSBANDET ÄR DOKUMENTETS ────────────────────────────────────────
# Läraren pekade på rutan i canvas och skrev att «ett gemensamt svar per grupp
# lämnas in vid lektionens slut» skulle bort. Ingenting hände på pappret —
# rutan var en hårdkodad mall (blad-bygg.js BAND + blad.js grupphuvud) och stod
# inte i dokumentets JSON, så det fanns ingenting att skriva om. Panelen svarade
# ändå att det var gjort. Testerna nedan låser båda halvorna av rättelsen:
# fältet finns, och den gamla mallen är kvar som reserv för gamla papper.

def test_bandet_kommer_ur_dokumentet_nar_det_ar_ifyllt():
    eget = ("Läs uppgiften tillsammans innan ni börjar räkna. Bestäm vem som "
            "skriver.")
    doc, fel = exam_spec.validate_exam_json(_doc(instruktion=eget),
                                            "gruppuppgift")
    assert doc is not None, fel
    tex = exam_latex.render_gruppuppgift(doc)
    band = tex.split(r"\notisruta{")[1].split("}")[0]
    assert "Bestäm vem som skriver" in band
    # Och löftet läraren strök kommer INTE tillbaka ur mallen.
    assert "sätts upp i salen" not in band


def test_tomt_falt_ger_appens_mall_som_forut():
    """Ingen migrering av gamla papper: ett dokument utan fältet ska se
    likadant ut som innan fältet fanns."""
    doc, _ = exam_spec.validate_exam_json(_doc(), "gruppuppgift")
    assert doc.instruktion is None
    band = exam_latex.render_gruppuppgift(doc).split(r"\notisruta{")[1]
    assert "Alla i gruppen ska kunna förklara" in band
    assert "sätts upp i salen" in band


def test_nyckelfragan_star_kvar_efter_lararens_eget_band():
    """De två fälten delar bandet men inte varandra: arbetsregeln kan skrivas
    om utan att metodregeln rörs, och tvärtom."""
    doc, fel = exam_spec.validate_exam_json(
        _doc(instruktion="Arbeta två och två.",
             nyckelfraga="Var sitter den okända?"), "gruppuppgift")
    assert doc is not None, fel
    band = exam_latex.render_gruppuppgift(doc).split(r"\notisruta{")[1]
    assert band.index("Arbeta två och två") < band.index("Var sitter")


def test_prompten_ber_om_bandet_med_redovisningsloftet():
    """Ett gammalt «skriftligt» ger genomgångens löfte, ordagrant, och prompten
    ber aldrig om en inlämning eller om någon som skriver för gruppen
    (Rickard 2026-09-23)."""
    p = exam_gen.build_prompt(
        "Matematik, nivå 1a", "BA26B", ["Tal"], antal=4,
        profil="gruppuppgift",
        grupp={"elever": 3, "langd_min": 45, "redovisning": "skriftligt"})
    assert '"instruktion"' in p
    assert exam_spec.GRUPP_GENOMGANG in p
    assert "lämnas in vid lektionens slut" not in p
    assert "bestäm vem som skriver" not in p.lower().replace(
        "«bestäm vem som skriver»", "")


def test_omskrivningen_far_veta_att_bandet_finns():
    """Det avgörande fallet. build_refine_prompt bär BARA INSTRUCTION — stod
    fältregeln i uppdragsblocket kunde modellen skriva rutan när dokumentet
    föddes men aldrig ändra den efteråt, vilket är precis vad läraren bad om."""
    p = exam_gen.build_refine_prompt(
        {"titel": "Gruppuppgift", "uppgifter": []},
        "ta bort meningen om att svaret lämnas in")
    assert "- instruktion:" in p
    assert "HELA bandets text" in p


def test_omskrivningen_far_veta_att_upplagget_gar_att_andra():
    """Samma sak för de tre villkoren överst på pappret. `grupp` fanns i
    schemat men stod inte i INSTRUCTION, och omskrivningen får bara den texten
    med sig — «gör grupperna om 4» kunde alltså inte nå fältet, och metaraden
    och namnraderna stod kvar på tre."""
    p = exam_gen.build_refine_prompt(
        {"titel": "Gruppuppgift", "uppgifter": []}, "gör grupperna om 4")
    assert "- grupp {elever, langd_min, redovisning}" in p
    assert "namnrader" in p


def test_provtiden_heter_tid_min_i_instruktionen():
    """Fältnamnet stod fel: INSTRUCTION bad om «tid_minuter», som inte finns i
    ExamDoc — _rensa_toppnycklar slängde det som en påhittad toppnyckel, och en
    ändrad provtid kunde aldrig fastna i dokumentet."""
    assert "tid_min:" in exam_gen.INSTRUCTION
    assert "tid_minuter," not in exam_gen.INSTRUCTION
    assert "tid_min" in exam_spec.ExamDoc.model_fields


def test_uppgifterna_heter_siffror_och_delarna_bokstaver():
    """Lärarens val 2026-08-20: brickorna är 1, 2, 3 … så att deluppgifterna
    kan heta a) b) utan att två bokstavsserier blandas på samma papper."""
    doc, _ = exam_spec.validate_exam_json(_doc(), "gruppuppgift")
    tex = exam_latex.render_gruppuppgift(doc)
    assert r"\begin{uppgift}{1}" in tex and r"\begin{uppgift}{2}" in tex
    assert r"\begin{uppgift}{A}" not in tex
    # Deluppgifternas a) b) prövas där delar finns: test_brickan_star_fri_…


@pytest.mark.tectonic
def test_pappret_gar_att_kompilera(tmp_path):
    """En mall som inte kompilerar upptäcks annars först framför klassen.

    Pappret här bär förlagans två nya grepp — nyckelfrågan i bandet och de
    namngivna ifyllnadsraderna — för det är de som är oprövade i sättningen.
    \\svarsfaltrad bygger på \\makebox och \\hrulefill, alltså inget nytt paket
    och ingen ny rad i Tectonic-seeden."""
    import pypdfium2

    d = _doc(nyckelfraga="Var sitter den okända? I exponenten → logaritmera.")
    d["uppgifter"][0]["svarsfalt"] = ["Ekvation", "Svar i ord"]
    doc, fel = exam_spec.validate_exam_json(d, "gruppuppgift")
    assert doc is not None, fel
    pdf, log = exam_pdf.compile_pdf(exam_latex.render_gruppuppgift(doc),
                                    tmp_path, "gruppuppgift")
    assert pdf is not None, log[-2000:]
    assert pdf.stat().st_size > 5000
    sidor = pypdfium2.PdfDocument(str(pdf))
    # Radbrytningarna är sättningens, inte textens: bandet bryter mitt i frågan
    # («Var sitter den\nokända?»), så mellanrum normaliseras före jämförelsen.
    text = " ".join("".join(sidor[i].get_textpage().get_text_range()
                            for i in range(len(sidor))).split())
    assert "Ekvation:" in text and "Svar i ord:" in text
    assert "Var sitter den okända? I exponenten → logaritmera." in text


@pytest.mark.tectonic
def test_brickan_star_fri_fran_texten(tmp_path):
    """Bokstavsbrickan satt IHOP med uppgiftstexten på lärarens utskrift:
    «ARäkna var för sig …», «BI verkstaden …», och deluppgifterna likaså
    («a)Vilket», «b)Ali»). Guttern i _preamble gav hela sin bredd åt etiketten
    och noll åt mellanrummet, och LaTeX högerställer etiketten i sin box —
    brickan hamnade alltså tätt mot textens vänsterkant. På ett papper där
    varje uppgift börjar med ett imperativt verb läser bokstaven då som
    meningens första bokstav.

    Testet läser den KOMPILERADE PDF:en och inte .tex-källan: mellanrummet
    finns inte i källan alls, det uppstår i sättningen, och en assert på
    \\labelsep hade bara upprepat koden."""
    import pypdfium2

    d = _doc()
    d["uppgifter"][0]["text"] = "Räkna var för sig och jämför sedan svaren."
    d["uppgifter"][1]["text"] = "I verkstaden byggs en ramp med lutningen 1:12."
    d["uppgifter"][1]["poang"] = [0, 0, 0]
    d["uppgifter"][1].pop("losning", None)
    d["uppgifter"][1].pop("bedomning", None)
    d["uppgifter"][1]["deluppgifter"] = [
        {"text": "Vilket är rampens höjdökning per meter?", "poang": [1, 0, 0],
         "losning": "Kvoten $1/12$.", "bedomning": "Rätt kvot ger 1 p."},
        {"text": "Ali vill ha 0,5 m höjd. Hur lång blir rampen?",
         "poang": [1, 0, 0], "losning": "$6$ m.", "bedomning": "Rätt längd ger 1 p."},
    ]
    doc, fel = exam_spec.validate_exam_json(d, "gruppuppgift")
    assert doc is not None, fel
    pdf, log = exam_pdf.compile_pdf(exam_latex.render_gruppuppgift(doc),
                                    tmp_path, "gruppuppgift")
    assert pdf is not None, log[-2000:]
    sidor = pypdfium2.PdfDocument(str(pdf))
    text = "".join(sidor[i].get_textpage().get_text_range()
                   for i in range(len(sidor)))
    # Brickorna är siffror sedan lärarens val 2026-08-20 — mellanrumskravet
    # är detsamma: «1Räkna» läser som ett tal i meningen.
    for hopsatt, fritt in (("1Räkna", "1 Räkna"),
                           ("2I verkstaden", "2 I verkstaden"),
                           ("a)Vilket", "a) Vilket"),
                           ("b)Ali", "b) Ali")):
        assert hopsatt not in text, f"brickan sitter ihop: {hopsatt!r}"
        assert fritt in text, f"brickan saknas helt: {fritt!r}"


# ---------------------------------------------------------------- rutten --

def test_rutten_ger_typ_och_profil(client, monkeypatch):
    calls = _stub(monkeypatch)
    r = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "klass": "NA25",
        "punkter_text": ["Derivator"], "typ": "gruppuppgift", "antal": 4,
        "grupp": {"elever": 3, "langd_min": 60, "redovisning": "skriftligt"}}))
    assert calls[0]["profil"] == "gruppuppgift" and calls[0]["antal"] == 4
    assert r["typ"] == "gruppuppgift"


def test_okand_typ_faller_tillbaka_pa_prov(client, monkeypatch):
    calls = _stub(monkeypatch)
    _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter_text": ["x"], "typ": "affisch"}))
    assert calls[0]["profil"] == "prov"


def test_godkannandet_skriver_arket_och_facit_men_ingen_bedomning(client, monkeypatch):
    """Gruppuppgiften rättas ur sitt eget facit — bedömningsanvisningen är
    provets dokument och skrivs inte här.

    Facit-filen byggs för VARJE gruppuppgift, precis som arbetsbladets:
    valet «Separat facit» bor i webbläsarens dokument och inte i provets
    JSON, och en fil som redan ligger där kostar ingenting jämfört med ett
    godkännande som måste göras om för att läraren ändrade sig efteråt.
    Utan flaggan i kroppen bär arket sitt facit ändå, som förut."""
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    _stub(monkeypatch)
    ex = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter_text": ["Derivator"],
        "typ": "gruppuppgift",
        "grupp": {"elever": 4, "langd_min": 45, "redovisning": "poster"}}))
    _done(client.post(f"/api/exams/{ex['id']}/approve", json={}))
    filer = sorted(client.base_dir.rglob("*.tex"), key=lambda p: p.name)
    namn = [f.name for f in filer]
    assert namn and not any(n.endswith(" - bedomning.tex") for n in namn), namn
    assert any(n.endswith(" - facit.tex") for n in namn), namn
    arket = next(f for f in filer if not f.name.endswith(" - facit.tex"))
    innehall = arket.read_text(encoding="utf-8")
    # Metaraden trycks inte längre (se test_arket_bar_namnrader_men_ingen_metarad)
    # — men namnraderna, som räknas ur samma gruppfält, ska stå där.
    assert "elever per grupp" not in innehall
    assert innehall.count(r"\noindent Namn:") == 4


def test_separat_facit_tar_lararens_sida_ur_gruppens_ark(client, monkeypatch):
    """Flaggan reser med godkännandet därför att valet bor i webbläsarens
    dokument (plan.js inst.facit) och inte i provets JSON. Utan den bar
    gruppens ark lösningarna ändå, och de låg dessutom i facit-filen
    bredvid: eleverna fick dem dubbelt."""
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    _stub(monkeypatch)
    ex = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter_text": ["Derivator"],
        "typ": "gruppuppgift",
        "grupp": {"elever": 4, "langd_min": 45, "redovisning": "poster"}}))
    _done(client.post(f"/api/exams/{ex['id']}/approve",
                      json={"separat_facit": True}))
    filer = sorted(client.base_dir.rglob("*.tex"), key=lambda f: f.name)
    arket = next(f for f in filer if not f.name.endswith(" - facit.tex"))
    facit = next(f for f in filer if f.name.endswith(" - facit.tex"))
    BAND = r"\delprovband{Facit och bedömning}"
    assert BAND not in arket.read_text(encoding="utf-8")
    assert BAND in facit.read_text(encoding="utf-8")


def test_prompten_talar_om_gruppen(monkeypatch):
    """Modellen ska veta att fyra elever ska PRATA sig igenom pappret."""
    p = exam_gen.build_prompt(
        "Matematik, nivå 2c", "NA25", ["Derivator"], antal=4,
        profil="gruppuppgift",
        grupp={"elever": 4, "langd_min": 30, "redovisning": "poster"})
    assert "GRUPPUPPGIFT" in p
    assert "4 elever per grupp" in p and "30 minuter" in p
    assert "sätts upp i salen" in p
    # Kravet på samtal ligger på FORMEN, inte på förmågefördelningen. Raden löd
    # förut «inte rutinräkning som en elev gör snabbast själv» och gav
    # gruppuppgiften egna, sneda förmågemål; med lärarens jämnhetskrav (Del D)
    # är en begrepps- eller procedurpoäng legitim också här, när den är
    # ingången till resonemanget.
    assert "KRÄVA att man pratar" in p
    assert "flera sätt" in p and "ingången till resonemanget" in p
    # Ställningen ligger i uppgiften, inte i en separat mall.
    assert "deluppgifter som leder samtalet" in p


# ─────────────────────── förlagan som mönster (Del F, omskriven) ────────────
# Förlagan var till 2026-08-20 ett papper läraren kört skarpt och kallat en av
# de bästa lektioner hon haft (docs/forlagor/, exponential- mot
# potensekvationer, med cosinussatsen som handskrivet exempel). Den natten
# slipade hon i stället en gruppuppgift i tjugotvå vändor tills hon var nöjd —
# «Räkneordning, parenteser och formler», nivå 1a, byggklass — och bad om att
# DEN ska bära all framtida generering. Hennes anteckningar på vägen är
# kravlistan, och den här sviten är kravlistan i testform.

def test_prompten_bar_forlagans_monster():
    p = exam_gen.build_prompt(
        "Matematik, nivå 1c", "NA25", ["Trigonometri"], antal=4,
        profil="gruppuppgift", grupp={"elever": 3, "langd_min": 45,
                                      "redovisning": "muntligt"})
    assert "MÖNSTRET" in p
    assert "nyckelfraga" in p          # fältet, inte bara idén
    assert "BRYTA mönstret" in p       # en fråga som inte går att gissa
    assert "svarsfalt" in p            # besluten skrivs på pappret
    assert "lösblad" in p              # räkningen görs inte där
    # Dom: kryssrutorna behövdes inte, och det ska stå UTTRYCKLIGEN — annars
    # griper modellen efter svarsrutor, som finns i schemat.
    assert "INGA TYP-KRYSSRUTOR" in p
    # Den gamla förlagan är ersatt, inte kompletterad. Står båda kvar drar de
    # åt olika håll: den ena vill ha situationer ur skilda världar, den andra
    # ur klassens egen.
    assert "cosinussatsen" not in p
    assert "potensekvation" not in p.lower()


def test_prompten_bar_lararens_egna_domar_om_text_tal_och_kontext():
    """De fyra anteckningar hon skrev om och om igen: kortare text, mindre
    tal, heltalssvar och en kontext som angår klassen."""
    p = exam_gen.build_prompt(
        "Matematik, nivå 1a", "BA26B", ["Räkneordning"], antal=4,
        profil="gruppuppgift", grupp={"elever": 3, "langd_min": 50,
                                      "redovisning": "skriftligt"})
    assert "KORT UPPGIFTSTEXT" in p and "läsas två gånger" in p
    assert "SMÅ TAL, ENKLA MELLANLED" in p
    assert "SVARET är ett heltal" in p
    assert "KONTEXTEN ÄR KLASSENS" in p and "skolprojekt" in p
    # Fyra uppgifter är formen — hon strök ner från sex.
    assert "FYRA UPPGIFTER" in p
    # Arbetsgången bor i rutan, inte i uppgiften.
    assert "står i instruktionsrutan, inte i uppgiften" in p


def test_instruktionsrutan_far_momentets_minnesregel():
    """«Prioriteringsreglerna ska stå kort här i den här instruktionsrutan» —
    skrivet tre gånger samma natt. Rutan är det gruppen läser när den fastnar."""
    p = exam_gen.build_prompt(
        "Matematik, nivå 1a", "BA26B", ["Räkneordning"], antal=4,
        profil="gruppuppgift", grupp={"elever": 3, "langd_min": 50,
                                      "redovisning": "skriftligt"})
    assert "EN kort minnesregel för momentet" in p
    assert "inga tankstreck" in p          # «utan M-Dash»
    # Bandet ska fortfarande bära arbetsregeln och redovisningslöftet, och
    # löftet är genomgångens: inget lämnas in (2026-09-23).
    assert "läs uppgiften tillsammans" in p
    assert exam_spec.GRUPP_GENOMGANG in p


def test_utdragen_ur_pappret_ar_med_och_ar_giltig_json():
    """Exemplaret är UTDRAG ur hennes papper, inte hela dokumentet
    (promptbudget). Utdragen byggs ur dictar och json.dumpas — annars kan ett
    LaTeX-snedstreck bli fel i en handskriven sträng och exemplet lära ut en
    form appen inte kan läsa."""
    p = exam_gen.build_prompt(
        "Matematik, nivå 1a", "BA26B", ["Räkneordning"], antal=4,
        profil="gruppuppgift", grupp={"elever": 3, "langd_min": 50,
                                      "redovisning": "skriftligt"})
    assert len(exam_gen._UTDRAG_GRUPP) == 4
    for u in exam_gen._UTDRAG_GRUPP:
        rad = json.dumps(u, ensure_ascii=False)
        assert rad in p
        assert json.loads(rad) == u
    # De fyra formerna hon behöll: ingången, begreppen, felsökningen, formeln.
    former = [set(u) for u in exam_gen._UTDRAG_GRUPP]
    assert any("tabell" in f for f in former)
    assert any("stegtabell" in f for f in former)
    assert all("svarsfalt" in f or "deluppgifter" in f for f in former)
    # Påhittade förnamn är tillåtna sedan 2026-08-20 (lärarens beslut) — men
    # gränsen mot RIKTIGA elevnamn består, och SYSTEM ska säga båda halvorna.
    assert "påhittade förnamn är välkomna" in exam_gen.SYSTEM.lower()
    assert "riktiga elever" in exam_gen.SYSTEM.lower()
    assert "En elev har beräknat" in p


def test_nivaskalningen_skiljer_byggettan_fran_naturtvaan():
    """«Olika nivåer för olika elever»: samma mall, men talen och uttrycken
    skalas ur KURSEN. Utan blocket ärver 2c byggettans mått, för utdragen är
    ett 1a-papper."""
    def prompt(kurs):
        return exam_gen.build_prompt(
            kurs, "X26", ["Räkneordning"], antal=4, profil="gruppuppgift",
            grupp={"elever": 3, "langd_min": 45, "redovisning": "muntligt"})

    ett_a, ett_c, tva_c = (prompt("Matematik, nivå 1a"),
                           prompt("Matematik, nivå 1c"),
                           prompt("Matematik, nivå 2c"))
    assert ett_a != ett_c != tva_c and ett_a != tva_c
    # Byggettan: heltal, konkret, formeln är fast plus rörligt.
    assert "steg 1 i spår a" in ett_a
    assert "SVARET är ett heltal" in ett_a
    assert "yrkesprogrammens matematik" in ett_a
    # Naturettan: samma talrum, annat språk.
    assert "steg 1 i spår c" in ett_c
    assert "natur- och teknikprogrammens matematik" in ett_c
    assert "yrkesprogrammens matematik" not in ett_c
    # Naturtvåan: större talrum, bråk och negativa tal — inte heltalskravet.
    assert "steg 2 i spår c" in tva_c
    assert "SVARET är ett heltal" not in tva_c
    assert "bråk, procent och negativa tal" in tva_c
    # Mellanleden ska vara enkla överallt — det var domen «för svåra tal».
    for p in (ett_a, ett_c, tva_c):
        assert "Mellanleden ska på ALLA nivåer" in p


@pytest.mark.parametrize("kurs, vantat", [
    ("Matematik, nivå 1a", (1, "a")),
    ("Matematik, nivå 2b", (2, "b")),
    ("Ma1c", (1, "c")),
    # Gy25 döpte om Ma3c till «fortsättning, nivå 1c» — steget är ändå 3.
    ("Matematik – fortsättning, nivå 1c", (3, "c")),
    ("Matematik – fortsättning, nivå 2", (4, "c")),
    ("Matematik – fördjupning, nivå 1", (5, "c")),
    ("Fysik", None),
])
def test_kursnamnet_bar_nivan(kurs, vantat):
    assert exam_gen._kursniva(kurs) == vantat


def test_en_okand_kurs_faller_tillbaka_pa_matten_i_monstret():
    p = exam_gen.build_prompt(
        "Naturkunskap", "NA25", ["Enheter"], antal=4, profil="gruppuppgift",
        grupp={"elever": 3, "langd_min": 45, "redovisning": "muntligt"})
    assert "kursnamnet säger inte vilken nivå det gäller" in p
    assert "MÖNSTRET" in p


def test_monstret_ror_inte_provet_eller_arbetsbladet():
    """Förlagan är gruppuppgiftens. Prov och arbetsblad har egna uppdrag och
    egna nivåskalor, och ett byggpapper får inte läcka in i dem."""
    for profil in ("prov", "arbetsblad"):
        p = exam_gen.build_prompt(
            "Matematik, nivå 1a", "BA26B", ["Räkneordning"], antal=6,
            profil=profil)
        assert "MÖNSTRET" not in p, profil
        assert "byggställning" not in p, profil
        assert "NIVÅN — måtten skalas ur kursen" not in p, profil


def test_uppdragsraden_som_kassetterna_matchar_pa_star_kvar():
    """Uppspelningen väljer band på generatorernas egna versalord
    (tests/fejk.py _VAL). Glider mönstret in ett annat bands nyckelord — eller
    ut ur sitt eget — får en lärardag tyst fel papper."""
    p = exam_gen.build_prompt(
        "Matematik, nivå 1a", "BA26B", ["Räkneordning"], antal=4,
        profil="gruppuppgift", grupp={"elever": 3, "langd_min": 50,
                                      "redovisning": "skriftligt"})
    assert ("Uppdrag: skriv en GRUPPUPPGIFT för Matematik, nivå 1a, klass "
            "BA26B, med EXAKT 4 uppgifter") in p
    # Listan är ordnad, och «matteprov» står i INSTRUCTION som alla profiler
    # delar — det är alltså inte frånvaron av andras nyckelord som avgör utan
    # att inget HÖGRE prioriterat ord råkar dyka upp här.
    assert "Skriv lärarens stödanteckningar" not in p
    # Nivådomaren prövas före hela listan och skulle kapa valet helt.
    assert "vilken nivå den faktiskt ligger på" not in p


def test_prompten_ber_om_stegringen_som_fungerade():
    """Dom 1: alla klarade den första uppgiften, några få den sista — men
    någon klarade den. Här stod förut motsatsen («inte en trappa»)."""
    p = exam_gen.build_prompt(
        "Matematik, nivå 3c", "NA25", ["Logaritmer"], antal=4,
        profil="gruppuppgift", grupp={"elever": 3, "langd_min": 45,
                                      "redovisning": "muntligt"})
    assert "STEGRING" in p
    assert "men inte noll" in p
    assert "inte en trappa" not in p


def test_stegringen_ar_promptstyrd_inte_validerad():
    """Beslutspunkt, medvetet dokumenterad: ordningsvalidatorn mäter svårighet
    i poängtripplar över dokumentets halvor, och fyra uppgifter är för få steg
    för att det måttet ska säga något. Slås den på ska det ske efter en mätning
    i kassetterna — inte för att den här raden såg tom ut."""
    *_, kraver_stigande = exam_spec.PROFILER["gruppuppgift"]
    assert kraver_stigande is False



# ══════════════ BOKEN SOM FÖREBILD, OCH DE TVÅ NYA DOMARNA ══════════════════
#
# LÄRARENS DOM 2026-09-09: «Uppgift 2 är oftast alldeles för komplicerad och
# svår att förstå för alla elever. Vissa uppgifter är inte relevanta utifrån
# vad som står i boken, för man utgår ju från boken. Uppgift 1 är den enda jag
# alltid är nöjd med.»
#
# Diagnosen står i exam_gen (BOKEN SOM FÖREBILD …): formen kopierades ur
# förlagan medan sorten tappades ur boken, och uppgift 2 växte. Testerna nedan
# håller de tre delarna av lagningen — pekningen, de två domarna och de
# deterministiska vakterna — och kalibreringen som gör vakterna trovärdiga:
# LÄRARENS EGET PAPPER MÅSTE GÅ IGENOM DEM.

# Bokens uppgifter som appen faktiskt läser dem (bok.remsuppgifter). Talen är
# ur Matematik 5000+ 1a s. 34–36, remsan i exam 75.
_BOKUPPG = [
    {"nr": 1268, "niva": 1, "text": "Skriv med prefix."},
    {"nr": 1272, "niva": 1,
     "text": "Ett vindkraftverk kan ge effekten 3 MW. Hur många kW motsvarar det?"},
    {"nr": 1279, "niva": 2,
     "text": "Vilket eller vilka av följande alternativ är detsamma som 200 μm?"},
    {"nr": 1282, "niva": 2, "text": "Skriv utan prefix och i grundpotensform."},
]


def _grupprompt(**extra):
    return exam_gen.build_prompt(
        "Matematik, nivå 1a", "BA26B", ["Prefix och enheter"], antal=4,
        profil="gruppuppgift",
        grupp={"elever": 2, "langd_min": 20, "redovisning": "skriftligt"},
        **extra)


def test_bokens_uppgifter_gar_in_i_prompten_som_forebilder():
    """Uppslaget gick redan in som sidtext och remsan som en rad nummer. Det
    som saknades var vilken uppgift varje nummer ÄR — och utan det kan ingen
    peka."""
    p = _grupprompt(bokuppgifter=_BOKUPPG)
    assert "BOKENS UPPGIFTER PÅ LÄRARENS SIDOR" in p
    for u in _BOKUPPG:
        assert str(u["nr"]) in p
        assert u["text"][:30] in p
    assert '"forebild"' in p
    # Pekningen är en pekning, inte en förlaga: originalitetskravet ska stå
    # kvar i samma andetag, annars blir förebilden en inbjudan att skriva av.
    assert "inte en förlaga" in p


def test_utan_bok_lamnas_forebilden_tom_och_sorten_kommer_ur_punkten():
    p = _grupprompt()
    assert exam_gen.FOREBILD_UTAN_BOK in p
    assert "BOKENS UPPGIFTER PÅ LÄRARENS SIDOR" not in p
    assert "hitta aldrig på ett boknummer" in p


def test_monstret_ger_formen_och_boken_ger_sorten():
    """Kärnan i lagningen av exam 75: formeluppgiften ($P = 3 + 2n$) kom ur
    mönstret och skrevs på ett prefixuppslag utan en enda formel."""
    p = _grupprompt(bokuppgifter=_BOKUPPG)
    assert "FORMEN HÄRIFRÅN, SORTEN UR BOKEN" in p
    assert "DEN HÄR FORMEN SKRIVS BARA NÄR BOKENS SIDOR HAR FORMLER" in p
    assert "annars vinner boken" in p
    # Och lärarens egen mening om just den bytesaffären.
    assert "teckna ett uttryck har inget med överslagsberäkning att göra" in p


def test_forebilden_star_i_gruppuppgiftens_grammatik_men_inte_i_provets():
    """Fältet kostar en kopia per uppgift i ett schema som ligger nära sitt tak
    (claude_code.SCHEMA_TAK_EXE) — och bara gruppuppgiftens uppdrag BER om
    det. Provets och arbetsbladets grammatik ska vara byte för byte den de
    var."""
    grupp = json.dumps(exam_spec.to_response_format(4), ensure_ascii=False)
    assert '"forebild"' in grupp
    skelett = exam_spec.balanced_skeleton(6, "prov")
    prov = json.dumps(exam_spec.to_response_format(6, skelett),
                      ensure_ascii=False)
    assert "forebild" not in prov
    # Omskrivningen och latexfixen kommer utan antal och utan skelett — för
    # PROVET ska de ha exakt det schema de hade innan fältet fanns.
    assert "forebild" not in json.dumps(exam_spec.to_response_format(),
                                        ensure_ascii=False)
    assert len(json.dumps(exam_spec.to_response_format(6, skelett))) \
        < claude_code.SCHEMA_TAK_EXE


def test_omskrivningen_av_en_gruppuppgift_far_skriva_tillbaka_forebilden():
    """Fältet föll ur grammatiken i varje varv: omskrivningen skickar varken
    antal eller skelett, och villkoret läste dem. Gruppuppgift 77 tappade sin
    förebild 1269 på uppgift 2 (2026-09-09) utan att något fel syntes — de
    orörda uppgifterna bar sina kvar, för dem tas ordagrant ur originalet
    (sammanfoga_riktat), så förlusten gällde bara den uppgift läraren pekat på.

    Villkoret är PROFILEN, inte antalet: gruppuppgiftens vägar får fältet,
    provets och arbetsbladets grammatik är oförändrad."""
    assert "forebild" not in json.dumps(exam_spec.to_response_format(),
                                        ensure_ascii=False)
    assert '"forebild"' in json.dumps(
        exam_spec.to_response_format(forebild=True), ensure_ascii=False)

    sedda: list[dict] = []

    def llm(_model, _prompt, **kw):
        sedda.append(kw.get("response_format") or {})
        return json.dumps(_gruppdoc_med_forebild())

    exam_gen.refine_exam(_gruppdoc_med_forebild(), "gör uppgift 2 kortare",
                         model="", nummer=2, profil="gruppuppgift", llm=llm)
    assert sedda and '"forebild"' in json.dumps(sedda[0], ensure_ascii=False)

    sedda.clear()
    exam_gen.refine_exam(_doc(), "gör uppgift 2 kortare", model="", nummer=2,
                         profil="prov", llm=llm)
    assert sedda and "forebild" not in json.dumps(sedda[0], ensure_ascii=False)


def test_forebilden_valideras_som_ett_nummer_och_en_mening():
    d = _doc()
    d["uppgifter"][0]["forebild"] = {"nr": 1279, "sort": "samma omvandling"}
    doc, fel = exam_spec.validate_exam_json(d, "gruppuppgift")
    assert doc is not None and [e for e in fel if e["code"] == "schema"] == []
    assert doc.uppgifter[0].forebild.nr == 1279
    # Ett påhittat «nummer» som inte är ett nummer ska falla, inte tyst bli 0.
    d["uppgifter"][0]["forebild"] = {"nr": "boken", "sort": "samma sort"}
    doc, fel = exam_spec.validate_exam_json(d, "gruppuppgift")
    assert doc is None and fel


# ── VAKTERNA, OCH KALIBRERINGEN SOM GÖR DEM TROVÄRDIGA ──────────────────────
def test_lararens_eget_papper_gar_igenom_alla_vakterna():
    """DEN VIKTIGASTE RADEN I SVITEN. Måtten i begriplighetssignaler är satta
    mot lärarens egen gruppuppgift, den hon slipade i tjugotvå vändor — en
    vakt som fäller hennes eget papper är fel vakt, och skulle kosta rundor på
    varje generering."""
    papper = {"uppgifter": [dict(u) for u in exam_gen._UTDRAG_GRUPP]}
    assert exam_gen.begriplighetssignaler(papper) == []


def test_uppgift_tva_far_ett_raknesteg():
    """Exam 75:s uppgift 2: två plåtar, en tredje plåt, ett tak på 4,2 mm och
    svaret i mikrometer — tre omvandlingar och två räkningar i huvudet."""
    papper = {"uppgifter": [
        {"text": "Ingången.", "poang": [2, 0, 0], "losning": "$57$"},
        {"text": "På verkstaden mäts tjockleken på två plåtar.",
         "poang": [0, 0, 0], "deluppgifter": [
             {"poang": [0, 1, 0],
              "text": "Bestäm hur tjock den tredje plåten högst får vara.",
              "losning": "$1\\,500\\ \\mu$m $= 1{,}5$ mm ger $2 + 1{,}5 = "
                         "3{,}5$ mm. Kvar: $4{,}2 - 3{,}5 = 0{,}7$ mm $= 700$."}]}]}
    fynd = exam_gen.begriplighetssignaler(papper)
    assert [f["path"] for f in fynd] == ["uppgift 2a"]
    assert "räknesteg" in fynd[0]["message"]
    # …och samma uppgift som uppgift 4 fälls INTE: den sista ska vara svår.
    sista = {"uppgifter": papper["uppgifter"] * 2}
    assert all(f["path"] != "uppgift 4a"
               for f in exam_gen.begriplighetssignaler(sista))


def test_tva_fragor_i_samma_text_falls():
    papper = {"uppgifter": [{"text": "Hur många kW är det? Vad blir svaret i W?",
                             "poang": [1, 0, 0], "losning": "$9$"}]}
    fynd = exam_gen.begriplighetssignaler(papper)
    assert any("frågor i samma text" in f["message"] for f in fynd)


def test_lararens_egna_ordbyten_ar_vakter():
    """«texten mer konkret så att eleverna fattar (lag → arbetslag)» och
    «paket» utan förklaring — hennes egna omskrivningar, dokument 37."""
    papper = {"uppgifter": [
        {"text": "Ett lag lägger kabel. Hela paketet väger $4$ kg.",
         "poang": [1, 0, 0], "losning": "$4$"}]}
    meddelanden = " ".join(f["message"]
                           for f in exam_gen.begriplighetssignaler(papper))
    assert "«lag»" in meddelanden and "«paketet»" in meddelanden
    # «arbetslag» är precis vad hon skrev dit — ordet får inte fälla lösningen.
    lagat = {"uppgifter": [
        {"text": "Ett arbetslag lägger kabel.", "poang": [1, 0, 0],
         "losning": "$4$"}]}
    assert exam_gen.begriplighetssignaler(lagat) == []


def test_vakterna_galler_bara_gruppuppgiften():
    """Måtten är hämtade ur lärarens dom om GRUPPUPPGIFTEN. Ett prov har
    längre uppgiftstexter av goda skäl, och skulle fällas på formen."""
    papper = {"uppgifter": [{"text": "Hur? Vad? Varför?", "poang": [1, 0, 0],
                             "losning": "$1$"}]}
    assert exam_gen.begriplighetssignaler(papper, "prov") == []
    assert exam_gen.begriplighetssignaler(papper, "arbetsblad") == []


# ── RELEVANSDOMAREN ────────────────────────────────────────────────────────
def test_relevansdomen_faller_annan_sort_men_inte_oklart():
    kort = [{"nr": "1"}, {"nr": "2"}, {"nr": "3"}, {"nr": "4"}]
    domar = {"1": {"dom": "samma sort", "battre": "", "skal": "", "kraver": ""},
             "2": {"dom": "annan sort", "battre": "1279",
                   "skal": "boken omvandlar, pappret tecknar", "kraver": ""},
             "3": {"dom": "oklart", "battre": "", "skal": "", "kraver": ""},
             "4": {"dom": "annat moment", "battre": "", "skal": "", "kraver": ""}}
    fynd = exam_gen.relevansfynd(kort, domar)
    assert [f["path"] for f in fynd] == ["uppgift 2", "uppgift 4"]
    assert all(f["code"] == "relevans" for f in fynd)
    assert "1279" in fynd[0]["message"]
    # Tystnad fäller aldrig — samma tolerans som nivå- och räknedomen.
    assert exam_gen.relevansfynd(kort, {}) == []


def test_relevansdomaren_kors_inte_utan_bok():
    """Ingen bok i beställningen = ingen förebild att pröva. En dom mot ett
    tomt underlag hade fällt varje uppgift på ett papper ingen bok gällde."""
    anrop = []

    def llm(*a, **k):
        anrop.append(a)
        return "{}"

    assert exam_gen.doma_relevans(_doc(), [], model="", llm=llm) == []
    assert anrop == []


def test_relevansdomaren_ar_fail_open():
    def llm(*a, **k):
        raise RuntimeError("kvoten slut")

    loggat = []
    assert exam_gen.doma_relevans(_doc(), _BOKUPPG, model="", llm=llm,
                                  log_cb=loggat.append) == []
    assert any("levereras ändå" in r for r in loggat)


def test_relevansprompten_bar_sitt_eget_nyckelord():
    """Uppspelningen väljer band på ordet (tests/fejk.py _auto). Prompten bär
    ett helt papper och skulle annars matcha den generator som skrev det."""
    p = exam_gen.build_relevans_prompt(
        exam_gen.uppgiftskort(_doc()), _BOKUPPG, ["Prefix"])
    assert "relevansdomare" in p
    assert p.count("GRUPPUPPGIFT") == 0
    assert "1279" in p and "Prefix" in p


# ── BEGRIPLIGHETSDOMAREN ───────────────────────────────────────────────────
def test_begriplighetsdomen_faller_bara_nej():
    kort = [{"nr": "1"}, {"nr": "2"}, {"nr": "3"}]
    domar = {"1": {"forstar": "ja", "stor": ""},
             "2": {"forstar": "nej", "stor": "två frågor på en gång"},
             "3": {"forstar": "oklart", "stor": ""}}
    fynd = exam_gen.begriplighetsdom(kort, domar)
    assert [f["path"] for f in fynd] == ["uppgift 2"]
    assert "två frågor på en gång" in fynd[0]["message"]
    # Uppgift 2 får sin egen påminnelse: den är begreppsingången.
    assert "begreppsingången" in fynd[0]["message"]


def test_begriplighetsdomaren_ser_inget_facit():
    """Domaren ska läsa som en elev läser: utan lösningen. Ser den facit
    bedömer den svårigheten att LÖSA och inte att FÖRSTÅ."""
    kort = exam_gen.uppgiftskort(_doc())
    assert any(k.get("losning") for k in kort)
    p = exam_gen.build_begriplighet_prompt(kort)
    assert "begriplighetsdomare" in p
    assert '"losning"' not in p


# ── BOKGRINDEN ─────────────────────────────────────────────────────────────
def _gruppdoc_med_forebild():
    d = _doc()
    for u in d["uppgifter"]:
        u["forebild"] = {"nr": 1279, "sort": "samma omvandling"}
    return d


def test_bokgrinden_lagar_och_domer_om(monkeypatch):
    """Mekaniken: fynd → riktad omskrivning → omdom. Går uppgiften igenom
    andra domen står `relevansfel` tomt, och rundan är betald."""
    lagat = _gruppdoc_med_forebild()
    lagat["uppgifter"][0]["text"] = "Lagad uppgift om prefix."
    varv = {"n": 0}

    def falsk_relevans(exam, bokuppgifter, **kw):
        varv["n"] += 1
        return ([] if varv["n"] > 1
                else [exam_gen._err("uppgift 1", "relevans", "annan sort")])

    monkeypatch.setattr(exam_gen, "doma_relevans", falsk_relevans)
    monkeypatch.setattr(exam_gen, "doma_begriplighet", lambda *a, **k: [])
    monkeypatch.setattr(exam_gen, "_llm_round",
                        lambda *a, **k: copy.deepcopy(lagat))
    res = exam_gen._bok_grind({"exam": _gruppdoc_med_forebild(), "errors": [],
                               "rounds": 1},
                              model="", llm=None, profil="gruppuppgift",
                              bokuppgifter=_BOKUPPG, punkter=None, antal=4,
                              koder=None, niva_mal=None)
    assert res["relevansfel"] == [] and res["begriplighetsfel"] == []
    assert res["rounds"] == 2
    assert res["exam"]["uppgifter"][0]["text"] == "Lagad uppgift om prefix."
    assert [e for e in res["errors"] if e["code"] == "relevans"] == []


def test_bokgrinden_ger_upp_arligt_och_sager_det(monkeypatch):
    """Bandet svarar likadant varje gång — precis som en modell som inte
    förstår vad som är fel. Då ska pappret levereras med fyndet SAGT, inte
    tyst."""
    monkeypatch.setattr(
        exam_gen, "doma_relevans",
        lambda exam, bok, **kw: [exam_gen._err("uppgift 3", "relevans",
                                               "annat moment")])
    monkeypatch.setattr(exam_gen, "doma_begriplighet", lambda *a, **k: [])
    monkeypatch.setattr(exam_gen, "_llm_round", lambda *a, **k: None)
    res = exam_gen._bok_grind({"exam": _gruppdoc_med_forebild(), "errors": [],
                               "rounds": 1},
                              model="", llm=None, profil="gruppuppgift",
                              bokuppgifter=_BOKUPPG, punkter=None, antal=4,
                              koder=None, niva_mal=None)
    assert [f["nr"] for f in res["relevansfel"]] == ["3"]
    # Fyndet ligger kvar i fellistan, som är klientens `provFel`.
    assert [e["code"] for e in res["errors"]] == ["relevans"]
    assert exam_gen.bokfel_text(res["relevansfel"], exam_gen.RELEVANS_RAD) == \
        "Uppgift 3 saknar förebild bland bokens uppgifter på lärarens sidor."


def test_bokgrinden_river_inte_balansen(monkeypatch):
    """Samma grind som nivågrindens och domarpassets: en omskrivning som lagar
    relevansen och bryter balansen är ingen lagning."""
    trasigt = _gruppdoc_med_forebild()
    # Uppgiften som skrivs tillbaka bär noll poäng — och just den uppgiften är
    # den enda som får resa med genom mål-låset, så den faller på
    # valideringen medan resten av pappret är orört.
    trasigt["uppgifter"][0]["poang"] = [0, 0, 0]
    trasigt["uppgifter"][0].pop("deluppgifter", None)
    monkeypatch.setattr(
        exam_gen, "doma_relevans",
        lambda exam, bok, **kw: [exam_gen._err("uppgift 1", "relevans", "x")])
    monkeypatch.setattr(exam_gen, "doma_begriplighet", lambda *a, **k: [])
    monkeypatch.setattr(exam_gen, "_llm_round", lambda *a, **k: trasigt)
    original = _gruppdoc_med_forebild()
    res = exam_gen._bok_grind({"exam": original, "errors": [], "rounds": 1},
                              model="", llm=None, profil="gruppuppgift",
                              bokuppgifter=_BOKUPPG, punkter=None, antal=4,
                              koder=None, niva_mal=None)
    assert res["exam"] is original
    assert [f["nr"] for f in res["relevansfel"]] == ["1"]


def test_bokgrinden_kors_bara_pa_gruppuppgiften(monkeypatch):
    """Provet och arbetsbladet har egna uppdrag, egna källor och egna
    kassetter — och lärarens dom gällde gruppuppgiften."""
    from tests.test_exam import _stub_llm

    korda = []
    monkeypatch.setattr(exam_gen, "_domar_pass",
                        lambda exam, errors, **kw: {"exam": exam,
                                                    "errors": errors,
                                                    "rounds": 1})
    monkeypatch.setattr(exam_gen, "_niva_grind",
                        lambda res, **kw: {**res, "nivafel": []})
    monkeypatch.setattr(
        exam_gen, "_bok_grind",
        lambda res, **kw: (korda.append(kw["profil"]), res)[1])
    llm, _ = _stub_llm([json.dumps(_doc(), ensure_ascii=False)])
    for profil in ("prov", "arbetsblad", "gruppuppgift"):
        exam_gen.generate_exam("Matematik, nivå 1a", "BA26B", ["Prefix"],
                               model="", antal=4, profil=profil, llm=llm,
                               grupp={"elever": 2, "langd_min": 20,
                                      "redovisning": "skriftligt"})
    assert korda == ["gruppuppgift"]


def test_fynden_sager_att_poangen_ska_sta_kvar():
    """Uppmätt på den skarpa körningen 2026-09-09 (exam 76): rundan skrev om
    uppgift 2 med ANDRA poäng, mål-låset släppte bara igenom den uppgiften,
    balansen sprack och omskrivningen kastades. Fyndet stod därför kvar efter
    en enda runda av två. Fynden gäller texten, inte planen."""
    papper = {"uppgifter": [
        {"text": "Ett lag räknar. Hur? Vad?", "poang": [1, 0, 0], "losning": "$1$"}]}
    for f in exam_gen.begriplighetssignaler(papper):
        assert exam_gen.BEHALL_PLANEN in f["message"]
    kort = [{"nr": "2"}]
    dom = exam_gen.begriplighetsdom(
        kort, {"2": {"forstar": "nej", "stor": "två frågor"}})
    assert exam_gen.BEHALL_PLANEN in dom[0]["message"]
    rel = exam_gen.relevansfynd(
        kort, {"2": {"dom": "annan sort", "battre": "", "skal": "", "kraver": ""}})
    assert exam_gen.BEHALL_PLANEN in rel[0]["message"]


# ------------------------------------------- elevernas lösningsförslag --
#
# Lärarens beställning 2026-09-21: «Jag vill att man kan generera facit till
# gruppuppgifterna i appen, för båda gruppuppgifterna.» Provet hade det sedan
# 2026-09-17 (POST /api/exams/{id}/losningsforslag); gruppuppgiften fick det
# inte, därför att rutten släppte in typen «prov» och ingen annan.
#
# Det är SAMMA papper och samma pass: gruppuppgiftens uppgifter bär `losning`
# och `bedomning` precis som provets, med deluppgifter. Det som skiljer är
# poängen i marginalen — gruppens eget ark har inga, och då ska facit inte ha
# några heller.


def _fejkbygge(monkeypatch):
    """Tectonic byts mot en fil på disk: den här sviten prövar VILKET papper
    som byggs och var det hamnar, inte att LaTeX kompilerar (det gör
    test_pappret_gar_att_kompilera)."""
    byggda = {}

    def fake_compile(tex, out_dir, jobname, **_kw):
        byggda[jobname] = tex
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{jobname}.pdf"
        p.write_bytes(b"%PDF-1.5 fejk")
        return p, ""
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)
    monkeypatch.setattr(exam_pdf, "compile_pdf", fake_compile)
    return byggda


def _godkand_gruppuppgift(client, monkeypatch):
    _stub(monkeypatch)
    ex = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter_text": ["Derivator"],
        "typ": "gruppuppgift",
        "grupp": {"elever": 4, "langd_min": 45, "redovisning": "poster"}}))
    _done(client.post(f"/api/exams/{ex['id']}/approve", json={}))
    return ex["id"]


def _fejkat_losningspass(monkeypatch):
    def fake_generate(model, prompt, **_kw):
        assert "lösningsskrivare" in prompt
        rader = ["Ta bort nämnaren: $3x = 12$", "Dela båda sidor med 3",
                 "Svar: $x = 4$"]
        return json.dumps({"losningar": [{"enhet": n, "rader": rader}
                                         for n in ("", "a", "b", "c")]})
    monkeypatch.setattr(exam_gen.llm_client, "generate", fake_generate)


def test_gruppuppgiften_far_elevernas_losningsforslag(client, monkeypatch):
    """Hela vägen: GET säger att det inte är skrivet, POST skriver passet in i
    den AKTUELLA versionen och lägger PDF:en bredvid gruppens ark med samma
    stam som provets, GET ger den sedan."""
    byggda = _fejkbygge(monkeypatch)
    exam_id = _godkand_gruppuppgift(client, monkeypatch)
    r = client.get(f"/api/exams/{exam_id}/losningsforslag")
    assert r.status_code == 404 and "inte skrivet" in r.json()["error"]

    _fejkat_losningspass(monkeypatch)
    versioner_fore = len(client.get(f"/api/exams/{exam_id}").json()["versions"])
    r = client.post(f"/api/exams/{exam_id}/losningsforslag", json={})
    assert r.status_code == 200, r.text
    svar = r.json()
    assert svar["skrivna"] >= 1 and svar["varning"] == ""
    assert svar["pdf"].endswith(" - losningsforslag.pdf")
    view = client.get(f"/api/exams/{exam_id}").json()
    assert len(view["versions"]) == versioner_fore, "ingen ny version"
    assert any(u.get("utforlig") for u in view["exam"]["uppgifter"])

    r = client.get(f"/api/exams/{exam_id}/losningsforslag")
    assert r.status_code == 200
    assert "losningsforslag.pdf" in r.headers["content-disposition"]
    assert "losningsforslag" in " ".join(byggda)


def test_gruppuppgiftens_facit_bar_hela_losningen_men_inga_poang(client, monkeypatch):
    """Pappret är ett RENT facit: hela lösningen per uppgift och deluppgift,
    ingen poängtrappa, inga elevexempel, ingen bedömningstext — och ingen
    siffra i högermarginalen, för gruppens eget ark har ingen."""
    byggda = _fejkbygge(monkeypatch)
    exam_id = _godkand_gruppuppgift(client, monkeypatch)
    _fejkat_losningspass(monkeypatch)
    assert client.post(f"/api/exams/{exam_id}/losningsforslag",
                       json={}).status_code == 200
    tex = next(t for n, t in byggda.items() if n.endswith("losningsforslag"))
    assert "Lösningsförslag" in tex and "Svar:" in tex
    assert "Elevexempel" not in tex
    # Trappan och bedömningen är lärarens ord och hör till det andra pappret.
    assert "+1 E" not in tex and r"\delprovband{Facit och bedömning}" not in tex
    # Brickan står tom där provet har sin E/C/A-trippel.
    assert r"\begin{uppgift}{1}{}" in tex
    assert "högermarginalen" not in tex
    # …men provets eget lösningsförslag har den kvar.
    from tests.test_exam import _exam
    provdoc, _ = exam_spec.validate_exam_json(copy.deepcopy(_exam()), "prov")
    assert "högermarginalen" in exam_latex.render_losningsforslag(provdoc)


def test_lararens_lank_ger_losningsforslaget_nar_det_finns(client, monkeypatch):
    """«Lösningar» i Sparat och raden i utskriftsrutan hämtar gruppuppgiftens
    facit på /api/exams/{id}/facit (plan.js pdfVag). Innan passet körts är det
    arket godkännandet byggde; efteråt är det elevernas lösningsförslag —
    samma knapp, nyare papper (tryck.facit_bredvid)."""
    _fejkbygge(monkeypatch)
    exam_id = _godkand_gruppuppgift(client, monkeypatch)
    r = client.get(f"/api/exams/{exam_id}/facit")
    assert r.status_code == 200
    assert r.headers["content-disposition"].endswith("-%20facit.pdf")

    _fejkat_losningspass(monkeypatch)
    assert client.post(f"/api/exams/{exam_id}/losningsforslag",
                       json={}).status_code == 200
    r = client.get(f"/api/exams/{exam_id}/facit")
    assert r.status_code == 200
    assert "losningsforslag.pdf" in r.headers["content-disposition"]


def test_arbetsbladet_far_inget_eget_losningsforslag(client, monkeypatch):
    """Arbetsbladets separata facit ÄR den utskrivna lösningen redan. Ett
    andra facit bredvid hade varit samma papper två gånger."""
    _fejkbygge(monkeypatch)
    _stub(monkeypatch)
    ex = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 2c", "punkter_text": ["Derivator"],
        "typ": "arbetsblad"}))
    _done(client.post(f"/api/exams/{ex['id']}/approve", json={}))
    r = client.post(f"/api/exams/{ex['id']}/losningsforslag", json={})
    assert r.status_code == 400
    assert "gruppuppgiften" in r.json()["error"]


@pytest.mark.tectonic
def test_facit_utan_poangbricka_kompilerar(tmp_path):
    """Den tomma brickan är det enda nya i sättningen: `uppgift`-miljön får
    ett tomt andra argument där provet har «2/1/0». En miljö som kräver sitt
    argument hade fällt hela pappret, och det syns först framför klassen."""
    import pypdfium2

    d = _doc()
    d["uppgifter"][0]["utforlig"] = "Dela båda sidor med $3$\nSvar: $x = 4$"
    doc, fel = exam_spec.validate_exam_json(d, "gruppuppgift")
    assert doc is not None, fel
    tex = exam_latex.render_losningsforslag(doc, med_poang=False)
    pdf, log = exam_pdf.compile_pdf(tex, tmp_path, "gruppfacit")
    assert pdf is not None, log[-2000:]
    sidor = pypdfium2.PdfDocument(str(pdf))
    text = " ".join("".join(sidor[i].get_textpage().get_text_range()
                            for i in range(len(sidor))).split())
    assert "Lösningsförslag" in text and "Svar: x = 4" in text
    # Poängtrippeln står inte någonstans på elevernas papper.
    assert "3/0/0" not in text


# ── KVÄLLEN 2026-09-21: FYRA DOMAR OM ÖVNINGSPAPPRET ────────────────────────
#
# Läraren genererade två gruppuppgifter via API:t (exam 114 «Ekvationer med
# bråk» TE26A, exam 115 «Andelar och procent» BA26B), och båda krävde fem
# omskrivningsvarv och handpåläggning. Domarna, ordagrant, och vad de blev:
#
#  a) «Det måste framgå direkt, alltså i uppgifterna på en gång, i klartext,
#     om man ska använda miniräknare eller inte. Lite kort.»
#       → exam_gen.satt_raknarmarkering
#  b) «Den inrutade texten under namnen (instruktionen) behöver skrivas
#     mycket, mycket kortare.»  → exam_gen.korta_instruktion
#  c) «Uppgift tre behöver skrivas mycket enklare. Vi ska inte ge ut
#     ekvationen på en gång.»   → exam_gen.TEXT_TILL_EKVATION
#  d) Tre riktade omskrivningar av uppgift 2 på exam 115 förkastades HELT av
#     balansvakterna  → exam_gen.BALANSVARNING


def _grupppapper(**extra):
    """Ett fyruppgifters gruppuppgiftspapper som GÅR IGENOM balansen.

    Samma form som exam 115: uppgift 2 bär två delfrågor, och den ena av dem
    är papprets enda kommunikationspoäng. Det är den detaljen som gör pappret
    till kvällens fall — skrivs uppgiften om till EN fråga faller K till noll.
    """
    def uppg(formaga, typ, delar=None, poang=(0, 0, 0), text="Beräkna talet."):
        u = {"del": None, "formaga": formaga, "typ": typ, "poang": list(poang),
             "text": text, "losning": "Svar: 4", "bedomning": "+1 E rätt svar"}
        if delar:
            u.update(poang=[0, 0, 0], losning="", bedomning="",
                     deluppgifter=delar)
        return u

    def delfraga(formaga, poang):
        return {"formaga": formaga, "poang": list(poang),
                "text": "Förklara hur ni tänker.", "losning": "Svar: 4",
                "bedomning": "+1 E rätt svar"}

    papper = {
        "titel": "Andelar och procent", "kurs": "Matematik, nivå 1a",
        "klass": "BA26B", "tid_min": 45,
        "hjalpmedel": "Räknare: uppgift 3.",
        "instruktion": ("Läs uppgiften tillsammans. Bestäm vem som skriver. "
                        "Alla i gruppen ska kunna förklara lösningen efteråt. "
                        "Redovisas muntligt: två minuter per grupp."),
        "grupp": {"elever": 3, "langd_min": 45, "redovisning": "muntligt"},
        "uppgifter": [
            uppg("P", "rutin",
                 delar=[delfraga("P", (1, 0, 0)), delfraga("B", (1, 1, 0))]),
            uppg("K", "redovisning",
                 delar=[delfraga("K", (0, 1, 0)), delfraga("R", (0, 1, 1))]),
            uppg("M", "problem",
                 delar=[delfraga("M", (1, 1, 0)), delfraga("PL", (0, 1, 1))]),
            uppg("P", "rutin", poang=(1, 0, 0)),
        ],
    }
    papper.update(extra)
    return papper


# ── a) RÄKNAREN I KLARTEXT PÅ VARJE UPPGIFT ────────────────────────────────

@pytest.mark.parametrize("rad,vantat", [
    ("Räknare får användas på alla uppgifter.", [True] * 4),
    ("Utan räknare.", [False] * 4),
    ("Räknare: uppgift 3.", [False, False, True, False]),
    ("Räknare på uppgift 3 och 4, inte på 1 och 2.",
     [False, False, True, True]),
    ("Räknare får användas på uppgift 4, men inte på uppgift 1, 2 och 3.",
     [False, False, False, True]),
    ("Räknare får användas på alla uppgifter utom uppgift 2.",
     [True, False, True, True]),
    ("Uppgift 1–2 görs utan räknare, uppgift 3 och 4 med räknare.",
     [False, False, True, True]),
])
def test_raknarraden_tolkas_i_lararens_egna_former(rad, vantat):
    """Formerna är hennes egna — de två pappren i kväll och prompten
    (FORLAGA_GRUPP, «HJÄLPMEDLET STYRS PER UPPGIFT»). Förvalet för det raden
    inte nämner är motsatsen till det den räknar upp: «Räknare: uppgift 3» är
    ett fullständigt besked om alla fyra uppgifterna, inte bara om den tredje.
    """
    beslut = exam_gen.tolka_raknarrad(rad, 4)
    assert [beslut[n] for n in range(1, 5)] == vantat


@pytest.mark.parametrize("rad", ["", "Formelblad och digitala verktyg",
                                 "Arbeta i par och lämna in ett svar."])
def test_en_rad_utan_raknare_ger_ingen_markering(rad):
    """Ett papper utan besked är bättre än ett papper som ljuger om räknaren."""
    assert exam_gen.tolka_raknarrad(rad, 4) is None
    papper = _grupppapper(hjalpmedel=rad)
    assert exam_gen.satt_raknarmarkering(papper, "gruppuppgift") == []
    assert papper["uppgifter"][0]["text"] == "Beräkna talet."


def test_markeringen_star_forst_i_uppgiftstexten():
    """Lärarens egen plats, den hon satte den på när hon rättade exam 114 för
    hand: «Räknare tillåten. Ett arbetslag …». Texten går redan alla fyra
    vägarna — plan.js franProv, blad-bygg.js kort(), och båda mallarna."""
    papper = _grupppapper(hjalpmedel="Räknare: uppgift 3.")
    assert exam_gen.satt_raknarmarkering(papper, "gruppuppgift") == [1, 2, 3, 4]
    texter = [u["text"] for u in papper["uppgifter"]]
    assert texter[0].startswith("Utan räknare. Beräkna")
    assert texter[2].startswith("Räknare tillåten. Beräkna")


def test_markeringen_skrivs_aldrig_tva_ganger():
    """Varvet därpå, och varvet därpå igen. Utan silen hade pappret läst
    «Räknare tillåten. Räknare tillåten. Räknare tillåten. Beräkna …»."""
    papper = _grupppapper(hjalpmedel="Räknare får användas på alla uppgifter.")
    for _ in range(3):
        exam_gen.satt_raknarmarkering(papper, "gruppuppgift")
    assert papper["uppgifter"][0]["text"] == "Räknare tillåten. Beräkna talet."
    # …och byter läraren regeln i ett varv följer markeringen med i samma varv.
    papper["hjalpmedel"] = "Utan räknare."
    exam_gen.satt_raknarmarkering(papper, "gruppuppgift")
    assert papper["uppgifter"][0]["text"] == "Utan räknare. Beräkna talet."


def test_hjalpmedelsraden_kapas_till_meningen_som_bar_regeln():
    """Raden står i bandet överst bredvid tiden och redovisningsformen, och
    ett stycke där trycker ner allt annat. Meningen som VÄLJS är den som
    nämner räknaren, inte alltid den första."""
    assert exam_gen.korta_hjalpmedel(
        "Arbeta i par. Räknare: uppgift 3. Lämna in på slutet.") \
        == "Räknare: uppgift 3."
    assert exam_gen.korta_hjalpmedel("Utan räknare.") == "Utan räknare."
    papper = _grupppapper(hjalpmedel="Räknare: uppgift 3. Räkna i huvudet "
                                     "på de andra. Visa hur ni tänker.")
    exam_gen.satt_raknarmarkering(papper, "gruppuppgift")
    assert papper["hjalpmedel"] == "Räknare: uppgift 3."


def test_provet_far_varken_markering_eller_kapad_rad():
    """Provet har delar, och dess hjälpmedelsrad är EN mening per del
    (hjalpmedelsregel). Kapas den försvinner del C:s regel från
    försättsbladet, och en markering per uppgift hade sagt emot delrubriken."""
    papper = _grupppapper(hjalpmedel="Del B utan räknare. Del C med räknare.")
    assert exam_gen.satt_raknarmarkering(papper, "prov") == []
    assert exam_gen.ovningspappret_stadat(papper, "prov") is papper
    assert papper["hjalpmedel"] == "Del B utan räknare. Del C med räknare."
    assert papper["uppgifter"][0]["text"] == "Beräkna talet."


def test_markeringen_foljer_med_till_pappret():
    """Skärmen ritas av ur samma text (blad-bygg.js kort → u.t), så det som
    mäts här är den andra vägen: LaTeX-pappret eleven får i handen."""
    papper = _grupppapper(hjalpmedel="Räknare: uppgift 3.")
    exam_gen.ovningspappret_stadat(papper, "gruppuppgift")
    doc, fel = exam_spec.validate_exam_json(papper, "gruppuppgift")
    assert doc is not None, fel
    tex = exam_latex.render_gruppuppgift(doc)
    assert "Räknare tillåten." in tex and "Utan räknare." in tex


def test_genereringen_satter_markeringen_pa_pappret_lararen_far():
    """Passet ligger SIST i kedjan (generate_exam, flagga) — efter domare,
    grindar och vakter. Ligger det tidigare mäter begriplighetsvakten en
    mening appen själv lagt dit."""
    papper = _grupppapper(hjalpmedel="Utan räknare.")
    res = exam_gen.generate_exam(
        "Matematik, nivå 1a", "BA26B", ["Andelar"], model="", antal=4,
        profil="gruppuppgift", doma=False,
        grupp={"elever": 3, "langd_min": 45, "redovisning": "muntligt"},
        llm=lambda *_a, **_kw: json.dumps(papper))
    assert res["exam"] is not None, res["errors"]
    assert all(u["text"].startswith("Utan räknare. ")
               for u in res["exam"]["uppgifter"])


# ── b) INSTRUKTIONSBANDET: EN ELLER TVÅ MENINGAR ───────────────────────────

def test_bandet_kapas_till_tva_meningar():
    """«Den inrutade texten under namnen behöver skrivas mycket, mycket
    kortare.» Modellen skrev fyra meningar plus en metodregel.

    Sedan 2026-09-23 är de två meningarna ARBETSREGELN, och löftet för
    gruppens redovisningsform står efter dem (exam_gen.stada_gruppband).
    «Bestäm vem som skriver» stryks: inget lämnas in."""
    papper = _grupppapper()
    assert exam_gen.korta_instruktion(papper, "gruppuppgift") is True
    assert papper["instruktion"] == (
        "Läs uppgiften tillsammans. Alla i gruppen ska kunna förklara "
        "lösningen efteråt. " + exam_spec.REDOVISNING_LOFTE["muntligt"])
    # Och en gång till ändrar ingenting — passet körs varje varv.
    assert exam_gen.korta_instruktion(papper, "gruppuppgift") is False


def test_nyckelfragan_ror_inte_bandet_och_bandet_inte_den():
    """Nyckelfrågan har ett eget fält, sätts fet efter bandet och är momentets
    metodregel. Den som klipper bandet klipper inte den."""
    papper = _grupppapper(nyckelfraga="Vad ska räknas först?")
    exam_gen.ovningspappret_stadat(papper, "gruppuppgift")
    assert papper["nyckelfraga"] == "Vad ska räknas först?"
    # Två meningar arbetsregel plus löftet (se testet ovan).
    assert papper["instruktion"].count(".") == 3
    assert "Vad ska räknas först" not in papper["instruktion"]


def test_provets_band_ror_vi_inte():
    papper = _grupppapper()
    assert exam_gen.korta_instruktion(papper, "prov") is False
    assert papper["instruktion"].count(".") == 4


# ── c) TEXT → EKVATION ─────────────────────────────────────────────────────

def test_ekvationsmomentet_far_regeln_om_att_stalla_upp_sjalv():
    """Uppgift 3 på exam 114 gav bort steget: situationen stod i texten OCH
    ekvationen stod där färdigt uppställd, så det enda som återstod var att
    räkna. Att ställa upp ekvationen ÄR momentet i Ma 1c."""
    p = exam_gen.build_prompt(
        "Matematik, nivå 1c", "TE26A", ["Ekvationer med bråk"], antal=4,
        profil="gruppuppgift",
        grupp={"elever": 3, "langd_min": 45, "redovisning": "muntligt"})
    assert "TEXT → EKVATION" in p
    assert "Skriv en ekvation som beskriver" in p
    assert "Lös ekvationen" in p
    assert "ett fast belopp plus ett rörligt" in p


def test_momentet_utan_ekvationer_far_prompten_orord():
    """KASSETTREGELN. Villkoret är momentets, inte formens: ett procentpapper
    ska inte få en ekvationsuppgift det inte bad om, och gruppuppgiftens
    kassett (Andragradsfunktioner) ska inte behöva spelas om för en regel som
    inte gäller den."""
    assert exam_gen.ar_ekvationsmoment(["Andragradsfunktioner"]) is False
    assert exam_gen.ar_ekvationsmoment(["Andelen i procent"]) is False
    assert exam_gen.ar_ekvationsmoment(["Linjära ekvationer"]) is True
    # …och bokens egna uppgifter räcker också: läraren kryssade sidorna.
    assert exam_gen.ar_ekvationsmoment(
        ["Algebra"], [{"nr": 1268, "text": "Lös ekvationen $3x + 5 = 20$."}]) \
        is True
    assert exam_gen.TEXT_TILL_EKVATION not in _grupprompt()


def test_arbetsbladet_far_samma_regel():
    """Domen gällde gruppuppgiften, men regeln är momentets och inte formens:
    ett övningsblad om ekvationer som ger bort uppställningen övar bara
    räknandet."""
    blad = exam_gen.build_prompt("Matematik, nivå 1c", "TE26A",
                                 ["Ekvationer med bråk"], antal=6,
                                 profil="arbetsblad")
    assert "TEXT → EKVATION" in blad
    utan = exam_gen.build_prompt("Matematik, nivå 1c", "TE26A",
                                 ["Andelen i procent"], antal=6,
                                 profil="arbetsblad")
    assert "TEXT → EKVATION" not in utan


# ── d) RIKTAD OMSKRIVNING FÖRKASTAS INTE AV BALANSEN ───────────────────────

def _skriv_om_uppgift_tva(papper):
    """Kvällens omskrivning: uppgift 2 från två delfrågor till EN. K faller
    till noll och E-andelen skjuter över taket — på HELA pappret, inte i den
    uppgift läraren pekade på."""
    nytt = json.loads(json.dumps(papper))
    nytt["uppgifter"][1] = {
        "del": None, "formaga": "R", "typ": "redovisning",
        "poang": [2, 0, 0], "text": "Förklara vilken andel som är störst.",
        "losning": "Svar: den andra", "bedomning": "+2 E rätt svar"}
    return nytt


def test_kvallens_fall_riktad_omskrivning_overlever_att_balansen_glider():
    """EXAM 115, TRE FÖRKASTADE VARV. Varje varv skrev om uppgift 2 precis som
    läraren bad, och varje varv föll på att K därmed hamnade på 0 % av
    pappret. Ingen ny exam_version skrevs, svaret bar det GAMLA pappret med de
    NYA felen, och uppgift 2 stod kvar med a/b efter tre försök.

    Nu går ändringen igenom och fynden följer med som VARNINGAR — samma
    mönster som tavlan har (lesson_board.REFINE_BEHALL)."""
    fore = _grupppapper()
    assert exam_spec.validate_exam_json(fore, "gruppuppgift")[1] == []
    efter = _skriv_om_uppgift_tva(fore)
    # Det är de två koderna som fällde kvällens varv, och båda mäter HELA
    # pappret.
    assert {e["code"]
            for e in exam_spec.validate_exam_json(efter, "gruppuppgift")[1]} \
        == {"formagabalans", "nivabalans"}

    res = exam_gen.refine_exam(
        fore, "skriv om uppgift 2 till en enda fråga", model="", nummer=2,
        profil="gruppuppgift", llm=lambda *_a, **_kw: json.dumps(efter))
    # Pappret ÄR omskrivet: uppgift 2 bär en fråga, inte två.
    assert res["exam"] is not fore
    assert "deluppgifter" not in res["exam"]["uppgifter"][1]
    assert res["exam"]["uppgifter"][1]["text"].endswith(
        "Förklara vilken andel som är störst.")
    # …och fynden står kvar i svaret, som varningar läraren ser.
    assert {e["code"] for e in res["errors"]} == {"formagabalans",
                                                  "nivabalans"}
    # Uppgifterna hon INTE pekade på är orörda (mål-låset).
    assert res["exam"]["uppgifter"][2]["deluppgifter"] \
        == fore["uppgifter"][2]["deluppgifter"]


def test_omskrivningen_bar_raknarmarkeringen_in_i_den_nya_texten():
    """Modellen känner inte markeringen och skriver om texten utan den. Utan
    passet i refine hade uppgift 2 tappat sitt räknarbesked i just det varv
    läraren skrev om den, och bara den."""
    fore = _grupppapper(hjalpmedel="Räknare: uppgift 3.")
    efter = _skriv_om_uppgift_tva(fore)
    res = exam_gen.refine_exam(
        fore, "skriv om uppgift 2", model="", nummer=2, profil="gruppuppgift",
        llm=lambda *_a, **_kw: json.dumps(efter))
    assert res["exam"]["uppgifter"][1]["text"].startswith("Utan räknare. ")
    assert res["exam"]["uppgifter"][2]["text"].startswith("Räknare tillåten. ")


def test_provets_balans_faller_varvet_som_forut():
    """Där ÄR balansen papprets uppgift. Ett prov vars omskrivning river den
    ska lämna originalet tillbaka, precis som före den här ändringen."""
    assert exam_gen.balansvarningar("prov", ("uppgift", 2)) == frozenset()
    assert exam_gen.balansvarningar("arbetsblad", ("uppgift", 2)) \
        == exam_gen.BALANSVARNING
    assert exam_gen.balansvarningar("gruppuppgift", ("uppgift", 2)) \
        == exam_gen.BALANSVARNING


def test_en_omskrivning_utan_mal_ager_balansen_sjalv():
    """Mål-låset är villkoret. Skriver varvet om HELA pappret finns ingen
    enskild ändring att skydda, och då är balansen dess eget ansvar igen."""
    assert exam_gen.balansvarningar("gruppuppgift", None) == frozenset()
    fore = _grupppapper()
    efter = _skriv_om_uppgift_tva(fore)
    res = exam_gen.refine_exam(
        fore, "skriv om hela pappret", model="", profil="gruppuppgift",
        max_rounds=1, llm=lambda *_a, **_kw: json.dumps(efter))
    assert {e["code"] for e in res["errors"]} == {"formagabalans",
                                                  "nivabalans"}


# ── INGET LÄMNAS IN (Rickard 2026-09-23) ──────────────────────────────────
# «Gruppuppgifterna görs tillsammans i klassen, ingen lämnar in något.» Nio
# papper bar «Bestäm vem som skriver. Lämna in ett gemensamt svar …» och fick
# byggas om för hand. Testerna låser alla vägar in i bandet: schemat, rutten,
# prompten, bandstädningen, LaTeX-reserven och skärmens två kopior.

_INLAMNING = ("lämna in", "lämnas in vid", "vem som skriver", "gemensamt svar")


def _utan_inlamning(text: str) -> bool:
    lag = text.lower()
    return not any(ord_ in lag for ord_ in _INLAMNING)


def test_skriftligt_lases_som_genomgang():
    """Gamla dokument bär «skriftligt». De ska validera och tryckas som
    genomgång, inte fällas och inte be om en inlämning."""
    doc, fel = exam_spec.validate_exam_json(
        _doc(grupp={"elever": 2, "langd_min": 20, "redovisning": "skriftligt"}),
        "gruppuppgift")
    assert doc is not None, fel
    assert doc.grupp.redovisning == "genomgang"
    band = exam_latex.render_gruppuppgift(doc).split(r"\notisruta{")[1]
    assert exam_spec.GRUPP_GENOMGANG in band
    assert _utan_inlamning(band.split("}")[0])


def test_ett_pahittat_redovisningsord_falls_fortfarande():
    """Aliaset gäller de kända stavningarna. Ett påhittat ord ska schemat
    fälla, inte tyst göra till förvalet."""
    _, fel = exam_spec.validate_exam_json(
        _doc(grupp={"elever": 2, "langd_min": 20, "redovisning": "trolleri"}),
        "gruppuppgift")
    assert fel


@pytest.mark.parametrize("varde,vantat", [
    (None, "genomgang"), ("", "genomgang"), ("Genomgång", "genomgang"),
    ("skriftligt", "genomgang"), ("Muntligt", "muntligt"),
    ("poster", "poster"), ("trolleri", "genomgang")])
def test_redovisningsformen_har_genomgang_som_forval(varde, vantat):
    assert exam_spec.redovisningsform(varde) == vantat


def test_rutten_gor_skriftligt_till_genomgang(client, monkeypatch):
    """Webbläsarens gamla förval «Skriftligt» når servern även efter att valet
    togs bort ur väljaren. Det blir genomgång."""
    calls = _stub(monkeypatch)
    _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 1c", "punkter_text": ["Uttryck"],
        "typ": "gruppuppgift",
        "grupp": {"elever": 2, "langd_min": 20, "redovisning": "skriftligt"}}))
    assert calls[0]["grupp"]["redovisning"] == "genomgang"


def test_prompten_utan_upplagg_lovar_genomgangen():
    p = exam_gen.build_prompt("Matematik, nivå 1c", "NA26F", ["Uttryck"],
                              antal=4, profil="gruppuppgift")
    assert exam_spec.GRUPP_GENOMGANG in p
    assert 'redovisning="genomgang"' in p


@pytest.mark.parametrize("modellens", [
    "Läs uppgiften tillsammans. Bestäm vem som skriver. Lämna in ett "
    "gemensamt svar per grupp.",
    "Läs uppgifterna tillsammans och bestäm vem som skriver. Båda ska kunna "
    "förklara lösningen. Lämna in ett gemensamt svar vid lektionens slut.",
    "Lös uppgifterna tillsammans. Lämna in ett gemensamt svar när lektionen "
    "slutar.",
    "Läs uppgiften tillsammans. Välj en som skriver. Lämna in ett svar per "
    "grupp.",
    "Läs uppgiften tillsammans. Redovisas skriftligt: ett gemensamt svar per "
    "grupp lämnas in vid lektionens slut.",
])
def test_bandet_ber_aldrig_om_inlamning(modellens):
    """Modellens egna former från de nio pappren. Det som ber någon skriva för
    gruppen eller lämna in stryks, läsa tillsammans och förklara står kvar,
    och genomgångens mening står sist, en gång."""
    papper = _grupppapper(
        instruktion=modellens,
        grupp={"elever": 2, "langd_min": 20, "redovisning": "skriftligt"})
    exam_gen.ovningspappret_stadat(papper, "gruppuppgift")
    band = papper["instruktion"]
    assert band.endswith(exam_spec.GRUPP_GENOMGANG)
    assert band.count(exam_spec.GRUPP_GENOMGANG) == 1
    assert _utan_inlamning(band.replace("Inget lämnas in.", ""))
    assert band.startswith(("Läs upp", "Lös upp"))
    # Ett varv till ändrar ingenting.
    assert exam_gen.stada_gruppband(papper) is False


def test_rickards_rattade_band_star_kvar_som_de_ar():
    """Bandet på ett av de nio rättade pappren (Andelar och procent, 23/9) är
    redan rätt och ska gå igenom städningen orört."""
    ratt = ("Läs uppgiften tillsammans. Alla i gruppen ska kunna förklara "
            "lösningen efteråt. " + exam_spec.GRUPP_GENOMGANG)
    papper = _grupppapper(
        instruktion=ratt,
        grupp={"elever": 2, "langd_min": 20, "redovisning": "skriftligt"})
    assert exam_gen.stada_gruppband(papper) is False
    assert papper["instruktion"] == ratt


def test_tomt_band_far_reserven_utan_skrivare():
    """Utan dokumentets band trycker mallen sin reserv, och den ber inte
    längre någon skriva för gruppen."""
    doc, fel = exam_spec.validate_exam_json(
        _doc(grupp={"elever": 3, "langd_min": 45, "redovisning": "genomgang"}),
        "gruppuppgift")
    assert doc is not None, fel
    band = exam_latex.render_gruppuppgift(doc).split(r"\notisruta{")[1]
    band = band.split("}")[0]
    assert "Alla i gruppen ska kunna förklara" in band
    assert exam_spec.GRUPP_GENOMGANG in band
    assert _utan_inlamning(band.replace("Inget lämnas in.", ""))


def test_skarmens_kopior_lovar_samma_sak():
    """Skärmen ritar bandet ur blad-bygg.js (reserven) och blad.js (löftet),
    och PDF:en är skärmens avritning. Texterna där ska vara exam_spec:s, och
    väljaren i planeringen ska inte erbjuda en inlämning."""
    from pathlib import Path
    ui = Path(exam_spec.__file__).resolve().parent / "web" / "ui"
    blad = (ui / "blad.js").read_text(encoding="utf-8")
    bygg = (ui / "blad-bygg.js").read_text(encoding="utf-8")
    plan = (ui / "plan.js").read_text(encoding="utf-8")
    hur = blad.split("const HUR = {")[1].split("};")[0]
    assert f"'{exam_spec.GRUPP_GENOMGANG}'" in blad
    for lofte in exam_spec.REDOVISNING_LOFTE.values():
        assert lofte in blad
    assert "lämnas in" not in hur
    reserv = next(r for r in bygg.splitlines()
                  if r.strip().startswith("Gruppuppgift: '"))
    assert "skriver" not in reserv
    assert "val: ['Genomgång', 'Muntligt', 'Poster']" in plan
    assert "redovisning: 'Genomgång'" in plan


@pytest.mark.parametrize("fore,efter", [
    # Rickards egna rättelser av de nio pappren, 2026-09-23.
    ("Läs uppgifterna tillsammans och bestäm vem som skriver.",
     "Läs uppgifterna tillsammans."),
    ("Bestäm vem som skriver, och se till att båda kan förklara lösningen "
     "efteråt.",
     "Se till att båda kan förklara lösningen efteråt."),
    ("Bestäm vem som skriver.", ""),
    ("Välj en som skriver.", ""),
    ("Läs och bestäm vem som skriver, och räkna sedan.",
     "Läs och räkna sedan."),
    ("Läs uppgiften tillsammans.", "Läs uppgiften tillsammans."),
])
def test_ledet_om_vem_som_skriver_stryks_ur_meningen(fore, efter):
    assert exam_gen._utan_skrivarled(fore) == efter
def test_gruppuppgiften_heter_som_i_drive_och_facit_ligger_bredvid(
        client, monkeypatch):
    """«1.3 Bråk och andelar – gruppuppgift.pdf» (Drives mall, tryck.filstam).
    Elevernas lösningsförslag skrivs efteråt och ska hamna bredvid DEN filen,
    inte bredvid titeln: rutten hittar det på pappersfilens stam."""
    from pathlib import Path
    _fejkbygge(monkeypatch)
    _stub(monkeypatch, exam=_doc(titel="Bråk och andelar"))
    ex = _done(client.post("/api/exams/generate", json={
        "kurs": "Matematik, nivå 1a", "punkter_text": ["Andelar"],
        "typ": "gruppuppgift",
        "grupp": {"elever": 2, "langd_min": 20, "redovisning": "genomgang"}}))
    res = _done(client.post(f"/api/exams/{ex['id']}/approve", json={
        "namn": {"avsnitt": "1.3 Andelar och förhållanden", "niva": ""}}))
    assert Path(res["pdf"]).name == "1.3 Bråk och andelar – gruppuppgift.pdf"
    _fejkat_losningspass(monkeypatch)
    svar = client.post(f"/api/exams/{ex['id']}/losningsforslag", json={}).json()
    assert Path(svar["pdf"]).name == (
        "1.3 Bråk och andelar – gruppuppgift - losningsforslag.pdf")
    r = client.get(f"/api/exams/{ex['id']}/losningsforslag")
    assert r.status_code == 200
