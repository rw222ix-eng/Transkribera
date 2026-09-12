"""Klassens yrke i prompten. Lärarens fynd 2026-09-12.

Bakgrunden är hennes egen dom: «Superappen är asdålig på att komma upp med egna
förslag.» Exempel 3 på en tavla om division av bråk för en byggklass blev en
abstrakt tallinje («En halv meter list, 5 lika bitar. Vad visar märket?»). Det
hon skrev själv i stället var färgburkarna: en burk rymmer 3/4 liter, väggen
kräver 4½ liter, alltså sex burkar, och kontrollen 6 · 3/4 = 4½. Skillnaden är
inte matematiken. Den är att situationen är elevernas egen och att svaret går
att kontrollera på plats.

Fältet bor i klassprofilen (app/web/ui/profil.js «Inriktning», PUT
/api/klassprofil) och reser med skrivjobben. Tavlans halva prövas i
tests/test_lesson_board.py och tests/test_routes_planning.py; här prövas
papprens.

Två frågor, och den andra är den dyra:

  1. Når yrket fram? Prompten ska bära regeln, omskrivningen också, och de två
     domarna på gruppuppgiften ska veta att sammanhanget är BESTÄLLT.
  2. KASSETTREGELN: utan inriktning ska varje prompt vara BYTE FÖR BYTE den
     som tests/kassetter spelades in med. En rad som smyger in vid tomt fält
     gör varje inspelat band omspelningsmoget, och omspelningen kostar riktiga
     pengar och två vändor (se nivakalibrering-minnet).
"""
from __future__ import annotations

import json

import pytest

from app import db, exam_gen

YRKE = "Bygg och anläggning"
# Lärarens egen mening, den som ska synas i prompten som nivåmått.
BURKEN = "En burk färg rymmer 3/4 liter"


# ───────────────────────────── regeln ────────────────────────────────────

@pytest.mark.parametrize("tomt", ["", "   ", None])
def test_utan_inriktning_finns_ingen_regel(tomt):
    assert exam_gen.build_yrke(tomt) == ""
    assert exam_gen.build_yrke(tomt, "gruppuppgift") == ""


def test_regeln_bar_yrket_exemplet_och_undantaget():
    regel = exam_gen.build_yrke(YRKE)
    assert f"YRKET: klassen går {YRKE}" in regel
    assert BURKEN in regel
    assert "KONTROLLERA PÅ PLATS" in regel
    # Det som INTE får ätas upp av yrket står uttryckligen i regeln: talen,
    # nivåerna, förmågorna och att uppgifterna är egna.
    assert "talreglerna" in regel and "aldrig bokens" in regel
    # En ren räkneuppgift ska förbli ren. Ett påklistrat yrke är en kuliss,
    # och kulisser är precis det läraren strök.
    assert "ska fortsatt vara ren" in regel


def test_gruppuppgiften_har_inga_rena_rakneuppgifter_att_undanta():
    """Provets kortsvar («Lös ekvationen») har inget sammanhang att göra
    yrkesnära. Gruppuppgiftens fyra rutor har det alla fyra."""
    assert "Varje uppgift som har ett SAMMANHANG" in exam_gen.build_yrke(YRKE)
    assert "Varje uppgift ska utspela sig" in exam_gen.build_yrke(
        YRKE, "gruppuppgift")


def test_yrket_kapas_och_blir_en_rad():
    regel = exam_gen.build_yrke("  Bygg\noch\tanläggning " + "x" * 300)
    namnet = regel.split("YRKET: klassen går ")[1].split(".")[0]
    assert namnet.startswith("Bygg och anläggning x")
    assert len(namnet) == exam_gen.MAX_INRIKTNING
    assert "\n" not in namnet and "\t" not in namnet


# ───────────────────────────── prompten ──────────────────────────────────

def _prompt(profil: str, **extra) -> str:
    return exam_gen.build_prompt("Matematik, nivå 1a", "BA24",
                                 ["Aritmetik"], antal=4, profil=profil,
                                 **extra)


@pytest.mark.parametrize("profil", ["prov", "arbetsblad", "gruppuppgift"])
def test_utan_inriktning_ar_prompten_byte_identisk(profil):
    """Kassettregeln. Tomt fält, tomt block, oförändrad prompt."""
    utan = _prompt(profil)
    assert utan == _prompt(profil, inriktning="")
    assert utan == _prompt(profil, inriktning="   ")
    assert "YRKET:" not in utan


@pytest.mark.parametrize("profil", ["prov", "arbetsblad", "gruppuppgift"])
def test_regeln_star_narmast_uppdraget(profil):
    """Yrket är ingen KÄLLA utan en order om hur uppgifterna ska se ut, och
    det ska läsas i samma andetag som uppdraget det gäller."""
    p = _prompt(profil, inriktning=YRKE)
    assert f"YRKET: klassen går {YRKE}" in p and BURKEN in p
    # Efter yrket kommer bara uppdragsblocket (och bildkrysset på de två
    # profiler som har ett).
    efter = p.split("YRKET:")[1]
    assert "Uppdrag:" in efter
    # Talreglerna och originalitetskravet står kvar, orörda.
    assert "TALEN — mätta i tio nationella prov" in p


def test_omskrivningen_bar_yrket():
    """Varvet SKRIVER OM uppgifter. Utan regeln skriver det tillbaka
    färgburkarna till x, och läraren får skriva samma mening igen."""
    exam = {"titel": "Prov", "uppgifter": []}
    utan = exam_gen.build_refine_prompt(exam, "gör uppgift 2 enklare")
    assert utan == exam_gen.build_refine_prompt(exam, "gör uppgift 2 enklare",
                                                inriktning="")
    assert "YRKET:" not in utan
    med = exam_gen.build_refine_prompt(exam, "gör uppgift 2 enklare",
                                       inriktning=YRKE)
    assert f"YRKET: klassen går {YRKE}" in med
    # Lärarens egen mening står fortfarande SIST, närmast svaret.
    assert med.rstrip().endswith("Svara med enbart JSON.")
    assert med.index("YRKET:") < med.index("Lärarens önskemål en gång till")


# ───────────────────────────── domarna ───────────────────────────────────
# Båda domarna på gruppuppgiften kan fälla ett yrkesnära sammanhang av
# misstag: relevansdomaren för att bokens uppgift ser annorlunda ut,
# begriplighetsdomaren för att «list» och «reglar» är ovanliga ord i en
# matematikbok. De är inte ovanliga för de här eleverna.

_KORT = [{"nr": "1", "text": "Hur många burkar färg behövs?"}]
_BOK = [{"nr": "12", "text": "Beräkna $9/2 \\div 3/4$."}]


def test_domarprompterna_ar_byte_identiska_utan_inriktning():
    assert (exam_gen.build_relevans_prompt(_KORT, _BOK)
            == exam_gen.build_relevans_prompt(_KORT, _BOK, None, ""))
    assert (exam_gen.build_begriplighet_prompt(_KORT)
            == exam_gen.build_begriplighet_prompt(_KORT, ""))


def test_relevansdomaren_far_veta_att_sammanhanget_ar_bestallt():
    p = exam_gen.build_relevans_prompt(_KORT, _BOK, None, YRKE)
    assert f"KLASSEN GÅR {YRKE.upper()}" in p
    assert "aldrig ett fynd i sig" in p
    # Domen faller fortfarande på SORTEN, inte på situationen.
    assert "Döm bara på SORTEN" in p


def test_begriplighetsdomaren_vet_att_yrkets_ord_ar_vardagsord():
    p = exam_gen.build_begriplighet_prompt(_KORT, YRKE)
    assert f"KLASSEN GÅR {YRKE.upper()}" in p
    assert "vardagsord för de här" in p
    # Uppgift 2 döms fortfarande hårdast, och på förståelsen.
    assert "UPPGIFT 2 är begreppsingången" in p


# ───────────────────────────── rutten ────────────────────────────────────

def _done(resp) -> dict:
    ev = [json.loads(r[len("data:"):]) for r in resp.text.splitlines()
          if r.startswith("data:")]
    klara = [e for e in ev if e["type"] == "done"]
    assert klara, ev
    return klara[0]["result"]


class _Prompter(list):
    """En lista av prompter som också bär anropens kwargs."""

    def __init__(self):
        super().__init__()
        self.val: list[dict] = []


def _fangade_prompter(monkeypatch) -> _Prompter:
    """Prompterna som gick i väg, och vad rutten skickade in i dem. Listan bär
    strängarna; `prompter.val` bär kwargs, för kassettregeln prövas enklast på
    argumentet: två genereringar i SAMMA testklient delar databas, och den
    andra får därför variationsvaktens undvik-lista med den förstas uppgift i.
    Att prompten är byte-identisk utan inriktning prövas ovan, på build_prompt
    självt."""
    prompter = _Prompter()
    riktig = exam_gen.build_prompt

    def spion(*a, **k):
        p = riktig(*a, **k)
        prompter.append(p)
        prompter.val.append(k)
        return p

    monkeypatch.setattr(exam_gen, "build_prompt", spion)
    return prompter


def _stubba(monkeypatch):
    monkeypatch.setattr(
        exam_gen, "_llm_round",
        lambda *a, **k: {"titel": "Prov", "kurs": "x",
                         "uppgifter": [{"del": None, "formaga": "P",
                                        "typ": "rutin", "poang": [2, 0, 0],
                                        "text": "Hur många burkar färg går åt?",
                                        "losning": "6",
                                        "bedomning": "+2 E"}]})


def _generera(klient, monkeypatch, **extra):
    cid = klient.post("/api/courses",
                      json={"namn": "Matematik, nivå 1a"}).json()["id"]
    prompter = _fangade_prompter(monkeypatch)
    _stubba(monkeypatch)
    r = klient.post("/api/exams/generate",
                    json={"course_id": cid, "klass": "BA24", "antal": 4,
                          "typ": "arbetsblad", "punkter_text": ["Aritmetik"],
                          **extra})
    assert r.status_code == 200, r.text
    return prompter, _done(r)


def test_rutten_utan_faltet_ger_samma_prompt(llm_ready, monkeypatch):
    """Kassettregeln på ruttnivå: fältet saknas, eller står tomt, och
    build_prompt får tom sträng, alltså inget block alls."""
    utan, _ = _generera(llm_ready, monkeypatch)
    assert utan.val[0]["inriktning"] == ""
    assert "YRKET:" not in utan[0]
    tomt, _ = _generera(llm_ready, monkeypatch, inriktning="  ")
    assert tomt.val[0]["inriktning"] == ""
    assert "YRKET:" not in tomt[0]


def test_rutten_bar_yrket_in_i_prompten(llm_ready, monkeypatch):
    prompter, _res = _generera(llm_ready, monkeypatch, inriktning=YRKE)
    assert f"YRKET: klassen går {YRKE}" in prompter[0]
    assert BURKEN in prompter[0]


def test_rutten_kapar_fritexten(llm_ready, monkeypatch):
    prompter, _res = _generera(llm_ready, monkeypatch,
                               inriktning="  Bygg\noch\tanläggning  ")
    assert f"YRKET: klassen går {YRKE}." in prompter[0]


def test_omskrivningsrutten_skickar_yrket_vidare(llm_ready, monkeypatch):
    _prompter, res = _generera(llm_ready, monkeypatch, inriktning=YRKE)
    eid = res["id"]
    sett = {}

    def fake_refine(exam, message, **kw):
        sett.update(kw)
        return {"exam": exam, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)
    r = llm_ready.post(f"/api/exams/{eid}/refine",
                       json={"message": "gör uppgift 1 enklare",
                             "inriktning": YRKE})
    assert r.status_code == 200, r.text
    _done(r)
    assert sett["inriktning"] == YRKE


def test_omskrivningsrutten_utan_faltet_ar_som_forut(llm_ready, monkeypatch):
    _prompter, res = _generera(llm_ready, monkeypatch)
    eid = res["id"]
    sett = {}

    def fake_refine(exam, message, **kw):
        sett.update(kw)
        return {"exam": exam, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)
    _done(llm_ready.post(f"/api/exams/{eid}/refine",
                         json={"message": "gör uppgift 1 enklare"}))
    assert sett["inriktning"] == ""


# ───────────────────────── klassprofilen ────────────────────────────────
# Fältet är fritext i profilen och sparas som resten av den: hela minnet i ett
# svep (PUT /api/klassprofil). Servern är en låda och har ingen egen åsikt om
# vad en klass går, men lådan måste bära fältet hem igen.

def test_inriktningen_sparas_och_lases_tillbaka(tmp_path):
    fil = tmp_path / "t.db"
    conn = db.connect(fil)
    try:
        db.save_klassprofil(conn, {"BA24": {"kurs": "Matematik, nivå 1a",
                                            "inriktning": YRKE}})
        assert db.get_klassprofil(conn)["BA24"]["inriktning"] == YRKE
    finally:
        conn.close()


def test_profilrutten_bar_yrket_hela_vagen(client):
    r = client.put("/api/klassprofil",
                   json={"BA24": {"kurs": "Matematik, nivå 1a",
                                  "inriktning": YRKE}})
    assert r.status_code == 200, r.text
    assert r.json()["BA24"]["inriktning"] == YRKE
    assert client.get("/api/klassprofil").json()["BA24"]["inriktning"] == YRKE
