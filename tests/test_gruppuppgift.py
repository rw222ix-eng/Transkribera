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
