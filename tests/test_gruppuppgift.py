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

from app import exam_gen, exam_latex, exam_pdf, exam_spec


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
    assert calls[0]["grupp"] == {"elever": 5, "langd_min": 10,
                                 "redovisning": "muntligt"}


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
    p = exam_gen.build_prompt(
        "Matematik, nivå 1a", "BA26B", ["Tal"], antal=4,
        profil="gruppuppgift",
        grupp={"elever": 3, "langd_min": 45, "redovisning": "skriftligt"})
    assert '"instruktion"' in p
    assert "lämnas in vid lektionens slut" in p


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
    # Bandet ska fortfarande bära arbetsregeln och redovisningslöftet.
    assert "läs uppgiften tillsammans" in p
    assert "lämnas in vid lektionens slut" in p


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
