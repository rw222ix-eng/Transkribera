"""Förlagan — källdörr 4 och pardokumentets andra hand (efter Etapp 4).

Fyndet som gjorde den här sviten nödvändig: `refDok` lades på pappret, rutan i
steg 3 visade den, och skrivplanen skrev «Läser förlagan · Tavla · derivator» —
men varken `/api/planning/generate` eller `/api/exams/generate` hade ett fält
för förlagan. Raden lovade en läsning som aldrig skedde. Pardokumentets andra
hand («Arbetsbladet skrivs PÅ tavlan du godkände») var samma tomma löfte.

Testerna frågar därför en enda sak, i fyra former: går förlagan att LÄSA UPP ur
prompten som gick till modellen? Allt annat — att rutan visas, att raden står i
planen — var redan sant när felet fanns.
"""
from __future__ import annotations

import copy
import json

import pytest

from app import exam_gen, forlaga, lesson_board


# Ett papper som frontenden lagrar det (app/web/ui/plan.js fardigt()).
def papper(**extra) -> dict:
    return {
        "typ": "Prov", "moment": "derivator", "klass": "NA25",
        "kurs": "Matematik, nivå 2c", "datum": "2026-09-03",
        "inst": {"antal": 3, "nivamix": "Balanserat"},
        "uppgifter": [
            {"nr": 1, "p": 2, "niva": "E", "t": "Ange derivatan till f(x) = 3x^2."},
            {"nr": 2, "p": 4, "niva": "C", "t": "Bestäm största värdet för f(x) = -x^2 + 4x.",
             "del": ["skissa grafen", "motivera med derivatan"]},
            {"nr": 3, "p": 3, "niva": "A", "t": "Visa att sambandet gäller generellt."},
        ],
        **extra,
    }


def tavla_papper(**extra) -> dict:
    return {
        "typ": "Tavla", "moment": "derivatans definition", "klass": "NA25",
        "kurs": "Matematik, nivå 2c", "datum": "2026-09-01",
        "wb": {"title": "Derivatans definition", "boards": [{
            "name": "teori", "width": 900, "height": 780, "chrome": "aluminium",
            "padding": {"top": 24, "right": 26, "bottom": 24, "left": 30},
            "sections": [
                {"kind": "heading", "text": "Derivatans definition", "size": 30},
                {"kind": "text", "text": "Ändringskvoten när h går mot noll.",
                 "size": 19},
                {"kind": "math", "latex": "f'(x)=\\lim_{h\\to 0}\\frac{f(x+h)-f(x)}{h}",
                 "size": 21},
            ]}]},
        **extra,
    }


# ─────────────────────────────── blocket ────────────────────────────────

def test_utan_forlaga_star_ingenting_om_en():
    """Ingen förlaga → inget block. Prompten ska inte innehålla en mening om
    en förlaga som inte finns; modellen skulle leta efter den."""
    assert forlaga.build_forlaga(None) == ""
    assert forlaga.build_forlaga({}) == ""
    assert forlaga.build_forlaga(None, "samma men som arbetsblad") == ""


def test_provets_uppgifter_star_i_blocket():
    text = forlaga.build_forlaga(papper())
    assert "FÖRLAGA" in text
    assert "Prov" in text and "derivator" in text and "NA25" in text
    for u in papper()["uppgifter"]:
        assert u["t"][:40] in text
    # Poäng och nivå följer med — de bär svårighetsgraden som ska följas.
    assert "2 p" in text and "E" in text and "4 p" in text
    # Deluppgifterna står som a) och b).
    assert "a) skissa grafen" in text and "b) motivera" in text


def test_tavlans_innehall_star_i_blocket():
    """Tavlan är strukturerad JSON. Det modellen behöver se är vad som STOD på
    brädena — rubriken, texten och matematiken — inte schemat runt det."""
    text = forlaga.build_forlaga(tavla_papper())
    assert "Derivatans definition" in text
    assert "Ändringskvoten när h går mot noll." in text
    assert "\\lim_{h\\to 0}" in text
    # Rubriken står en gång, inte två (title + heading är samma sträng).
    assert text.count("Derivatans definition") <= 2


def test_lararens_egen_mening_vager_tyngst():
    text = forlaga.build_forlaga(
        tavla_papper(), "Följer tavlan: samma exempel och begrepp, men som arbetsblad.")
    assert "lärarens ord" in text
    assert "samma exempel och begrepp, men som arbetsblad" in text


def test_blocket_sager_att_det_inte_ar_en_kopia():
    """En förlaga som läses som «skriv av det här» ger läraren samma papper en
    gång till — och det är inte vad hon bad om."""
    text = forlaga.build_forlaga(papper())
    assert "EGNA formuleringar" in text
    assert "inte" in text and "kopia" in text


def test_en_jattetavla_ater_inte_hela_prompten():
    """Tavlor kan vara 30 kB. Blocket har ett tak — annars trängs boken,
    minnet och utfallet ut ur kontexten av ett enda papper."""
    stor = tavla_papper()
    stor["wb"]["boards"][0]["sections"] = [
        {"kind": "text", "text": f"Rad {i} med rätt mycket text på den {i}"}
        for i in range(400)]
    text = forlaga.build_forlaga(stor)
    assert len(text) < forlaga.MAX_TECKEN + 1200
    assert "[…]" in text


def test_en_lang_uppgiftslista_kapas_med_besked():
    langt = papper()
    langt["uppgifter"] = [{"nr": i, "p": 2, "t": f"Uppgift {i}"} for i in range(1, 31)]
    text = forlaga.build_forlaga(langt)
    assert "uppgifter till" in text          # «… och N uppgifter till»
    assert "Uppgift 30" not in text


def test_ett_papper_med_konstiga_falt_faller_inte():
    """Pappret kommer från klienten och kan vara vad som helst — en gammal
    version, en halv kopia, ett fält som blivit null."""
    for trasigt in ({"typ": "Prov", "uppgifter": None},
                    {"typ": "Tavla", "wb": None},
                    {"typ": "Arbetsblad", "uppgifter": ["inte ett objekt", 42]},
                    {"typ": None, "moment": None, "wb": {"boards": [None, 7]}}):
        forlaga.build_forlaga(trasigt, "hur som helst")   # får inte kasta


# ────────────────────────────── prompterna ──────────────────────────────

def test_tavelprompten_bar_forlagan():
    text = lesson_board.build_prompt(
        "Matematik, nivå 2c", "NA25", "derivator",
        forlaga=forlaga.build_forlaga(papper(), "samma uppgiftstyper"))
    assert "FÖRLAGA" in text
    assert "samma uppgiftstyper" in text
    assert "Ange derivatan" in text
    # Uppdraget står SIST — förlagan får inte skjuta undan det.
    assert text.rindex("Uppdrag:") > text.rindex("FÖRLAGA")


@pytest.mark.parametrize("profil", ["prov", "arbetsblad", "gruppuppgift"])
def test_provprompten_bar_forlagan_i_alla_profiler(profil):
    grupp = ({"elever": 3, "langd_min": 45, "redovisning": "muntligt"}
             if profil == "gruppuppgift" else None)
    text = exam_gen.build_prompt(
        "Matematik, nivå 2c", "NA25", ["Derivator"], antal=4, profil=profil,
        grupp=grupp, forlaga=forlaga.build_forlaga(
            tavla_papper(), "samma exempel, men som uppgifter"))
    assert "FÖRLAGA" in text
    assert "samma exempel, men som uppgifter" in text
    assert "Ändringskvoten" in text
    # Uppdragsraden ligger sist i blocklistan.
    assert text.rindex("Uppdrag:") > text.rindex("FÖRLAGA")


def test_forlagan_och_undvik_listan_sager_inte_emot_varandra():
    """«Följ förlagan» och «undvik tidigare provs teman» är motsatta order.
    Referensläget löser det genom att släppa teman — förlagan gör detsamma, och
    det avgörs i rutten (routes_exam), inte i prompten."""
    text = exam_gen.build_prompt(
        "Matematik, nivå 2c", "NA25", ["Derivator"], antal=4,
        teman="Derivata av polynom", forlaga=forlaga.build_forlaga(papper()))
    # Står båda med är det ett fel någon annanstans — här prövas bara att
    # ordningen är förlaga FÖRE undvik-listan, så den sista instruktionen
    # modellen läser är uppdraget.
    assert text.index("FÖRLAGA") < text.index("UNDVIK")


# ─────────────────────────────── rutterna ───────────────────────────────

def _events(resp) -> list[dict]:
    return [json.loads(r[len("data:"):]) for r in resp.text.splitlines()
            if r.startswith("data:")]


def _done(resp) -> dict:
    ev = [e for e in _events(resp) if e["type"] == "done"]
    assert ev, _events(resp)
    return ev[0]["result"]


def _fangad_prompt(monkeypatch, modul) -> list[str]:
    """Fångar prompten som verkligen gick till modellen."""
    prompter: list[str] = []
    riktig = modul.build_prompt

    def spion(*a, **k):
        p = riktig(*a, **k)
        prompter.append(p)
        return p

    monkeypatch.setattr(modul, "build_prompt", spion)
    return prompter


def test_planeringsrutten_laser_forlagan_ur_sitt_eget_papper(llm_ready, monkeypatch):
    """Den sanna vägen: klienten skickar bara ett id, och servern läser pappret
    ur sin egen dokumenttabell — samma mönster som utfallet (Etapp 0.7)."""
    skapat = llm_ready.post("/api/dokument",
                            json={"dokument": papper(), "status": "godkant"})
    assert skapat.status_code == 200
    did = skapat.json()["id"]

    prompter = _fangad_prompt(monkeypatch, lesson_board)
    board = copy.deepcopy(lesson_board.FEW_SHOTS[0][1])
    monkeypatch.setattr(lesson_board, "_llm_round", lambda *a, **k: board)
    r = llm_ready.post("/api/planning/generate",
                       json={"moment": "repetition", "klass": "NA25",
                             "kurs": "Matematik, nivå 2c",
                             "forlaga_dokument_id": did,
                             "forlaga_hur": "samma uppgiftstyper, nya tal"})
    assert r.status_code == 200
    _done(r)
    assert prompter, "prompten byggdes aldrig"
    assert "FÖRLAGA" in prompter[0]
    assert "Ange derivatan" in prompter[0]
    assert "samma uppgiftstyper, nya tal" in prompter[0]


def test_planeringsrutten_tar_forlagan_inline_nar_id_saknas(llm_ready, monkeypatch):
    prompter = _fangad_prompt(monkeypatch, lesson_board)
    board = copy.deepcopy(lesson_board.FEW_SHOTS[0][1])
    monkeypatch.setattr(lesson_board, "_llm_round", lambda *a, **k: board)
    r = llm_ready.post("/api/planning/generate",
                       json={"moment": "repetition", "forlaga": tavla_papper()})
    assert r.status_code == 200
    _done(r)
    assert "Ändringskvoten" in prompter[0]


def test_provrutten_laser_forlagan_och_slapper_undvik_listan(llm_ready, monkeypatch):
    """Pardokumentets andra hand: arbetsbladet som skrivs PÅ den godkända
    tavlan. Och när en förlaga finns ska undvik-listan släppas — «följ det här»
    och «undvik det du gjort» kan inte båda gälla."""
    skapat = llm_ready.post("/api/dokument",
                            json={"dokument": tavla_papper(), "status": "godkant"})
    did = skapat.json()["id"]
    cid = llm_ready.post("/api/courses",
                         json={"namn": "Matematik, nivå 2c"}).json()["id"]

    prompter = _fangad_prompt(monkeypatch, exam_gen)
    monkeypatch.setattr(exam_gen, "_llm_round",
                        lambda *a, **k: {"titel": "Arbetsblad", "kurs": "x",
                                         "hjalpmedel": "", "uppgifter": [
                                             {"del": None, "formaga": "P",
                                              "typ": "rutin", "poang": [2, 0, 0],
                                              "text": "Beräkna", "losning": "1",
                                              "bedomning": "+2 E"}]})
    r = llm_ready.post("/api/exams/generate",
                       json={"course_id": cid, "klass": "NA25", "antal": 4,
                             "typ": "arbetsblad", "forlaga_dokument_id": did,
                             "forlaga_hur": "samma exempel som tavlan"})
    assert r.status_code == 200
    _done(r)
    assert "FÖRLAGA" in prompter[0]
    assert "samma exempel som tavlan" in prompter[0]
    assert "Ändringskvoten" in prompter[0]
    assert "UNDVIK" not in prompter[0], "undvik-listan står kvar mot förlagan"


def test_ett_okant_forlage_id_gor_ingen_skada(llm_ready, monkeypatch):
    prompter = _fangad_prompt(monkeypatch, lesson_board)
    board = copy.deepcopy(lesson_board.FEW_SHOTS[0][1])
    monkeypatch.setattr(lesson_board, "_llm_round", lambda *a, **k: board)
    r = llm_ready.post("/api/planning/generate",
                       json={"moment": "repetition", "forlaga_dokument_id": 9999})
    assert r.status_code == 200
    _done(r)
    assert "FÖRLAGA" not in prompter[0]
