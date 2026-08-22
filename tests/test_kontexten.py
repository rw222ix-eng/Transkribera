"""Når källorna fram till generatorn? (Etapp 3)

Läraren väljer källor i fem dörrar — förra lektionen, boken, egna filer, ett
tidigare papper, ett rättat prov — och lägger till Gy25-punkter, ett moment och
klassens minne. Allt det är valen hon gör INNAN hon trycker Skriv, och de är
värdelösa om de inte hamnar i prompten. Ett tapp där syns inte: modellen svarar
ändå, texten ser rimlig ut, och tavlan handlar om något klassen inte läser.

Kontraktet är därför: varje källa som väljs ska gå att LÄSA UPP ur prompten,
för tavlan, provet, arbetsbladet och gruppuppgiften.

Provets väg är prövad sedan Fas 4 (tests/test_routes_exam.py); här är tavlans,
arbetsbladets och gruppuppgiftens — plus escapningen, som är det som avgör om
ett elevnamn med & i sig blir ett papper eller ett LaTeX-fel.
"""
from __future__ import annotations

import copy
import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app import exam_gen, exam_latex, exam_pdf, exam_spec, lesson_board


def _events(resp):
    return [json.loads(rad[len("data:"):])
            for rad in resp.text.splitlines() if rad.startswith("data:")]


def _done(resp):
    evs = [e for e in _events(resp) if e["type"] == "done"]
    assert evs, _events(resp)
    return evs[0]["result"]


@pytest.fixture
def client(llm_ready):
    return llm_ready


# ══════════════════════════════════════════════════ tavlan ══════════════

def _stub_board(monkeypatch):
    """Fångar ALLA argument generatorn får — prompten byggs sedan av dem."""
    calls = []

    def fake(course, group, moment, *, model, memory="", underlag="",
             utfall="", bok="", llm=None, max_rounds=lesson_board.MAX_ROUNDS,
             log_cb=None, token_cb=None, **_kw):
        calls.append({"course": course, "group": group, "moment": moment,
                      "memory": memory, "underlag": underlag,
                      "utfall": utfall, "bok": bok})
        return {"board": copy.deepcopy(lesson_board.FEW_SHOTS[0][1]),
                "errors": [], "rounds": 1}
    monkeypatch.setattr(lesson_board, "generate_board", fake)
    return calls


def test_tavlans_kallor_nar_generatorn(client, monkeypatch):
    calls = _stub_board(monkeypatch)
    r = client.post("/api/planning/generate", json={
        "moment": "Derivatans definition", "klass": "NA25",
        "kurs": "Matematik, nivå 2c",
        # Källdörr 5 tar utfallet som pappret bär det: namnet och rättningen,
        # inte en färdigskriven mening (routes_planning.utfall_text).
        "utfall": {"namn": "Prov 12 maj", "rattat": {
            "andel": 0.62, "elever": 22,
            "svaga": [{"kod": "4b", "andel": 0.31, "formaga": "Procedur",
                       "text": "Derivera med kedjeregeln"}]}},
    })
    assert r.status_code == 200
    _done(r)
    assert calls and calls[0]["moment"] == "Derivatans definition"
    assert "kedjeregeln" in calls[0]["utfall"]
    assert "Prov 12 maj" in calls[0]["utfall"]
    assert "62 %" in calls[0]["utfall"]


def test_tavlans_prompt_bar_varje_kalla_den_fatt():
    """Prompten är det enda modellen ser. Faller en källa ur den är valet
    läraren gjorde bortkastat — och ingenting säger ifrån."""
    prompt = lesson_board.build_prompt(
        "Matematik 3c", "NA25", "Derivatans definition",
        memory="Förra lektionen: gränsvärden, klassen hann till s. 214.",
        underlag="Bokuppslag s. 210–217: ändringskvot, sekant, tangent.",
        utfall="Rättat prov: 4b, 7 elever föll på kedjeregeln.",
        bok="Matematik 5000+ 3c, s. 210–217: Derivatans definition.")
    for bit in ("Derivatans definition", "NA25", "Matematik 3c",
                "s. 214", "sekant", "kedjeregeln", "Matematik 5000+ 3c"):
        assert bit in prompt, f"{bit!r} nådde aldrig prompten"
    # Ordningen är inte kosmetisk: uppdraget står SIST, närmast svaret.
    assert prompt.rstrip().endswith("Svara med enbart JSON.")
    assert prompt.index("Uppdrag:") > prompt.index("sekant")


def test_tavlan_utan_kallor_ar_fortfarande_en_giltig_prompt():
    prompt = lesson_board.build_prompt("Matematik 3c", "NA25", "Integraler")
    assert "Integraler" in prompt and "Uppdrag:" in prompt
    assert "Ur lektionsminnet" not in prompt      # inga tomma rubriker


# ═══════════════════════════════════════ arbetsblad + gruppuppgift ══════

def _stub_exam(monkeypatch):
    calls = []

    def fake(kurs, klass, punkter, *, model, antal=10, tid_min=120, delar=True,
             memory="", teman="", referens="", bilder="", utfall="", bok="",
             profil="prov", grupp=None, llm=None,
             max_rounds=exam_gen.MAX_ROUNDS, log_cb=None, **_kw):
        from tests.test_exam import _exam
        calls.append({"kurs": kurs, "klass": klass, "punkter": punkter,
                      "memory": memory, "teman": teman, "referens": referens,
                      "bilder": bilder, "utfall": utfall, "bok": bok,
                      "profil": profil, "grupp": grupp, "antal": antal})
        data = _exam()
        if profil == "gruppuppgift":
            data["grupp"] = grupp or {"elever": 3, "langd_min": 45,
                                      "redovisning": "muntligt"}
        return {"exam": data, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "generate_exam", fake)
    return calls


def _kurs_id(client, namn="Matematik, nivå 2b"):
    for k in client.get("/api/courses").json():
        if k["namn"] == namn:
            return k["id"]
    raise AssertionError("kursen saknas — seedningen?")


def test_arbetsbladets_kallor_nar_generatorn(client, monkeypatch):
    calls = _stub_exam(monkeypatch)
    r = client.post("/api/exams/generate", json={
        "course_id": _kurs_id(client), "typ": "arbetsblad", "antal": 4,
        "utfall": {"namn": "Provet", "rattat": {
            "andel": 0.55,
            "svaga": [{"kod": "4b", "andel": 0.28, "formaga": "Procedur",
                       "text": "Kedjeregeln"}]}},
        "punkter_text": ["Derivata"]})
    assert r.status_code == 200
    _done(r)
    assert calls[0]["profil"] == "arbetsblad"
    assert calls[0]["antal"] == 4
    assert "4b" in calls[0]["utfall"]
    assert calls[0]["punkter"] == ["Derivata"]


def test_gruppuppgiftens_upplagg_nar_generatorn(client, monkeypatch):
    """Elever, längd och redovisningsform ÄR gruppuppgiftens form (namnrader,
    tiden i klartext, redovisningsraden). Tappas de blir arket ett arbetsblad
    med en annan rubrik."""
    calls = _stub_exam(monkeypatch)
    r = client.post("/api/exams/generate", json={
        "course_id": _kurs_id(client), "typ": "gruppuppgift", "antal": 3,
        "grupp": {"elever": 4, "langd_min": 30, "redovisning": "poster"},
        "punkter_text": ["Statistik"]})
    assert r.status_code == 200
    _done(r)
    assert calls[0]["profil"] == "gruppuppgift"
    assert calls[0]["grupp"] == {"elever": 4, "langd_min": 30,
                                 "redovisning": "poster"}


def test_provets_prompt_bar_utfallet_och_boken():
    """Samma krav som tavlans, en nivå ner: det som skickas in ska stå i
    prompten, inte bara i anropet."""
    prompt = exam_gen.build_prompt(
        "Matematik 3c", "NA25", ["Derivata", "Gränsvärden"],
        antal=6, tid_min=90,
        memory="Klassen har läst kapitel 4.",
        utfall="Rättat prov: 4b, 7 elever föll på kedjeregeln.",
        bok="Matematik 5000+ 3c s. 210–217.")
    for bit in ("Derivata", "Gränsvärden", "kapitel 4", "kedjeregeln",
                "Matematik 5000+ 3c"):
        assert bit in prompt, f"{bit!r} nådde aldrig provets prompt"


# ═══════════════════════════════════════════════════ escapningen ════════
# Elevnamn, kategorinamn och lärarens fritext går rakt in i LaTeX. Ett & i
# «Ek & Söner» eller ett % i «15 % rabatt» är inte ett kantfall — det är en
# vanlig uppgiftstext, och obehandlat är det ett kompileringsfel läraren möter
# fem minuter innan lektionen.

FARLIGT = "& % # _ { } ~ ^ \\ $ \" åäö ÅÄÖ"


@given(text=st.text(alphabet=st.characters(blacklist_categories=("Cs",)),
                    max_size=200))
@settings(max_examples=400, deadline=None)
def test_escapad_text_lamnar_inga_oskyddade_specialtecken(text):
    ut = exam_latex.escape_latex(text)
    # Varje kvarvarande specialtecken måste vara föregånget av ett bakstreck
    # (det escapade formen) — annars är det TeX som får se det rått.
    for i, ch in enumerate(ut):
        # {} och ~^ ingår i de ESCAPADE formerna själva (	extbackslash{},
        # 	extasciitilde{}) och kan därför stå «rått» — de fem nedan kan det
        # aldrig.
        if ch in "&%#_$":
            assert i > 0 and ut[i - 1] == "\\", f"oskyddat {ch!r} i {ut!r}"


@given(text=st.text(alphabet=st.characters(blacklist_categories=("Cs",)),
                    max_size=200))
@settings(max_examples=400, deadline=None)
def test_escapningen_tappar_aldrig_bokstaver(text):
    """Escapning får skydda, aldrig radera: bokstäverna som fanns ska finnas
    kvar (kontrolltecken undantagna — de strippas med flit).

    «Kvar» betyder som TECKEN eller som KOMMANDO. Ett par bokstäver saknar glyf
    i T1 och måste skrivas som ett TS1-kommando i stället — mikrotecknet µ är en
    sådan (Unicode kallar den en gemen bokstav), och utan kommandot trycktes ett
    helt annat tecken på pappret. \\textmu{} är alltså inte en förlust utan
    samma bokstav sagd på LaTeX."""
    kvar = "".join(c for c in text if c.isalpha())
    ut = exam_latex.escape_latex(text)
    for c in kvar:
        assert c in ut or exam_latex._LATEX_SPECIALS.get(c, "\0") in ut


def test_matten_bevaras_men_texten_runt_omkring_escapas():
    ut = exam_latex.escape_mixed("Ek & Söner säljer 15 % av $x^2 + 3$ st.")
    assert r"\&" in ut and r"\%" in ut
    assert r"\(x^2 + 3\)" in ut          # matten orörd, som \( … \)
    assert "$" not in ut                  # dollartecknen är omgjorda


def test_hard_space_mellan_tal_och_procent():
    """NP sätter «15,9 %» utan att tal och tecken kan brytas isär."""
    assert r"15,9~\%" in exam_latex.escape_mixed("15,9 % av eleverna")


@given(namn=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖabcdefghijklmnopqrstuvwxyzåäö &%#_{}$~^\\",
                    min_size=1, max_size=40))
@settings(max_examples=200, deadline=None)
def test_ett_namn_i_fritext_gar_escapat_in_i_mallens_vy(namn):
    """Vägen fritext → schema → mallens vy. Vyn är det mallen skriver ut, och
    där får inget oskyddat specialtecken finnas kvar. (Själva .tex-filen kan
    inte prövas så: mallen är LaTeX och har sina egna & i tabularx.)"""
    from tests.test_exam import _exam
    data = _exam()
    data["uppgifter"][0]["text"] = f"{namn} räknar ut $x^2$."
    doc, fel = exam_spec.validate_exam_json(data)
    assert doc is not None, fel
    vy = exam_latex._build_view(doc)
    text = vy["delar"][0]["uppgifter"][0]["text"]
    utanfor_matten = text.split(r"\(")[0]
    for i, ch in enumerate(utanfor_matten):
        if ch in "&%#_$":
            assert utanfor_matten[i - 1] == "\\", f"oskyddat {ch!r} i vyn: {text!r}"


@pytest.mark.tectonic
def test_ett_ovanligt_namn_kompilerar_pa_riktigt(tmp_path):
    """Egenskapen ovan säger att strängen är escapad. Det här säger att den
    escapade strängen faktiskt går genom Tectonic — en gång, med allt på en
    rad, för det är där en escapning som «ser rätt ut» ändå faller."""
    from tests.test_exam import _exam
    data = _exam()
    data["uppgifter"][0]["text"] = (
        r"Ek & Söner #3 säljer 15 % av x_1 {till} ~50 kr \ per st: "
        r"beräkna $x^2$ för A. L. och B_O."
    )
    doc, fel = exam_spec.validate_exam_json(data)
    assert doc is not None, fel
    pdf, logg = exam_pdf.compile_pdf(exam_latex.render_prov(doc), tmp_path, "prov")
    assert pdf is not None, logg
