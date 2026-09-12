"""Hjälpmedlen per provdel — lärarens val, inte husets regel.

Bakgrunden står i spåret (spardata/forslag/2026-09-06.md, avsnitt 2c): Rickard
skrev «formelblad ska vara tillåtet på del A och B» TRE gånger på två prov
samma dag, och första gången kostade det ett bortkastat omskrivningsvarv. Det
fanns ingen väg dit utom att be modellen skriva om pappret, för regeln bodde i
prompten och i blad.js — inte i planeringen.

Två frågor prövas här, och den andra är den dyra:

  1. Når valet fram? Prompten ska bära raden, och dokumentets `hjalpmedel` ska
     bära lärarens mening ordagrant — inte modellens omskrivning av den.
  2. KASSETTREGELN: står valet på förvalet ska prompten vara BYTE FÖR BYTE den
     som tests/kassetter spelades in med. Ett block som smyger in vid orört
     val gör varje inspelat band omspelningsmoget, och omspelningen kostar
     riktiga pengar och två vändor (se nivakalibrering-minnet).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import exam_gen, exam_latex, exam_spec

# Dagens papper, och lärarens önskemål ur spåret: formelbladet tillåtet på
# BÅDA delarna (6/9 13:17, 14:32, 15:31).
FORVAL_A, FORVAL_B = "Inga digitala", "Räknare"
AVVIK_A, AVVIK_B = "Formelblad", "Räknare och formelblad"
FORVAL = {"hjalpmedel_a": FORVAL_A, "hjalpmedel_b": FORVAL_B}
AVVIKELSE = {"hjalpmedel_a": AVVIK_A, "hjalpmedel_b": AVVIK_B}


# ──────────────────────────────── regeln ─────────────────────────────────

def test_forvalet_ger_ingen_regel_alls():
    """Dagens papper: del A utan digitala hjälpmedel, del B med räknare. Då
    finns ingenting att skriva in — varken i prompten eller i dokumentet."""
    assert exam_gen.hjalpmedelsregel("Inga digitala", "Räknare") == ""
    assert exam_gen.hjalpmedelsregel("Inga digitala", delar=False) == ""


@pytest.mark.parametrize("a,b", [
    ("", ""),                      # klienten skickade inget
    ("Räknare", ""),               # halvt val: del B saknas
    ("trams", "Räknare"),          # etikett appen inte känner
    ("Inga digitala", "trams"),
])
def test_okanda_eller_halva_val_ger_ingen_regel(a, b):
    """Servern är sista ordet. Ett fält appen inte känner igen får aldrig bli
    en halv mening på ett elevpapper — då står hellre husets regel kvar."""
    assert exam_gen.hjalpmedelsregel(a, b) == ""


def test_regeln_namner_bada_delarna_med_interna_namn():
    """Dokumentet talar INTERNA delnamn (B/C) överallt — skärmen och PDF:en
    räknar om dem till Del A och Del B var för sig. Skrevs regeln med papprets
    namn skulle översättningen köra en gång till och delarna smälta ihop."""
    regel = exam_gen.hjalpmedelsregel(AVVIK_A, AVVIK_B)
    assert regel.startswith("Del B ") and " Del C " in regel
    assert "formelblad" in regel.lower()
    assert "Del A" not in regel
    # Och den är EN mening per del, inte ett stycke: den ska rymmas på
    # försättsbladets Hjälpmedel-rad.
    assert regel.count(".") == 2


def test_en_del_far_en_enda_mening():
    regel = exam_gen.hjalpmedelsregel("Räknare och formelblad", delar=False)
    assert regel == ("Provet skrivs med räknare, digitala hjälpmedel och "
                     "formelblad.")
    assert "Del" not in regel


def test_skarmens_och_papprets_ordlistor_sager_samma_sak():
    """Tre listor beskriver samma fyra lägen: planeringens etiketter
    (plan.js HJALPMEDELSVAL), papprets fraser (blad-bygg.js HJALPMEDELSFRAS)
    och klausulerna här. Glider de isär säger förhandsvisningen och PDF:en
    olika saker om samma prov — och det är precis det felet som gjorde att
    «tillåt räknare på del A» inte syntes på skärmen."""
    js = Path(exam_gen.__file__).with_name("web") / "ui" / "blad-bygg.js"
    kalla = js.read_text(encoding="utf-8")
    for etikett in exam_gen.HJALPMEDEL_KLAUSUL:
        assert f"'{etikett}':" in kalla, f"{etikett} saknas i blad-bygg.js"


# ──────────────────────────── prompten ───────────────────────────────────

def _prov(**k) -> str:
    return exam_gen.build_prompt("Matematik, nivå 2c", "NA25", ["Derivator"],
                                 antal=4, memory="Senaste lektionen.", **k)


def test_forvalet_ger_byte_identisk_prompt():
    """KASSETTKRAVET. Ett orört val ska ge exakt den prompt som gick i väg
    innan raden byggdes — en enda extra radbrytning hade tvingat fram en
    omspelning av alla band."""
    forut = _prov()
    assert _prov(hjalpmedel="") == forut
    assert _prov(hjalpmedel=exam_gen.build_hjalpmedel(
        exam_gen.hjalpmedelsregel(FORVAL_A, FORVAL_B))) == forut
    assert "HJÄLPMEDLEN ÄR LÄRARENS VAL" not in forut


def test_avvikelsen_lagger_raden_i_uppdraget():
    block = exam_gen.build_hjalpmedel(
        exam_gen.hjalpmedelsregel("Formelblad", "Räknare och formelblad"))
    text = _prov(hjalpmedel=block)
    assert "HJÄLPMEDLEN ÄR LÄRARENS VAL" in text
    assert "Del B utan digitala hjälpmedel, formelbladet är tillåtet." in text
    # Raden står i UPPDRAGET, intill delningen den ändrar — inte som ett löst
    # block långt ovanför, där modellen redan glömt att provet har delar.
    assert text.index("HJÄLPMEDLEN ÄR LÄRARENS VAL") > text.rindex("Uppdrag:")


def test_arbetsbladet_har_inga_delar_och_far_ingen_rad():
    """Blocket hör till provet. Ett arbetsblad har ingen del A att tillåta
    något på, och prompten ska vara ordagrant som förut."""
    blad = exam_gen.build_prompt("Matematik, nivå 2c", "NA25", ["Derivator"],
                                 antal=4, profil="arbetsblad")
    med = exam_gen.build_prompt(
        "Matematik, nivå 2c", "NA25", ["Derivator"], antal=4,
        profil="arbetsblad",
        hjalpmedel=exam_gen.build_hjalpmedel(
            exam_gen.hjalpmedelsregel(AVVIK_A, AVVIK_B)))
    assert med == blad


# ───────────────────────────── pappret ───────────────────────────────────

def _doc(hjalpmedel: str):
    from tests.test_exam import _exam
    rad = _exam()
    rad["hjalpmedel"] = hjalpmedel
    doc, fel = exam_spec.validate_exam_json(rad)
    assert not fel, fel
    return doc


def test_delrubriken_i_pdf_foljer_lararens_val():
    """Rubriken sa «Del A – Digitala verktyg är inte tillåtna» ur en
    hårdkodad regel, och kunde alltså säga emot försättsbladets
    Hjälpmedel-rad på samma papper."""
    tex = exam_latex.render_prov(_doc(
        exam_gen.hjalpmedelsregel("Räknare", "Räknare och formelblad")))
    assert r"Del A \textendash{} Digitala verktyg är tillåtna" in tex
    assert r"Del B \textendash{} Digitala verktyg är tillåtna" in tex
    # Och försättsbladet bär samma mening, med papprets delnamn.
    assert (r"\textbf{Hjälpmedel:} Del A med räknare och digitala hjälpmedel."
            in tex)


def test_delrubriken_star_kvar_nar_regeln_tiger_om_delen():
    """Ett prov skrivet före valet — eller en modellmening som inte nämner
    delarna — ska se ut precis som förut."""
    tex = exam_latex.render_prov(_doc("Formelblad och linjal."))
    assert r"Del A \textendash{} Digitala verktyg är inte tillåtna" in tex
    assert r"Del B \textendash{} Digitala verktyg är tillåtna" in tex
    assert exam_latex._del_instruktion("B", True) == (
        "Del A löses utan räknare. Endast svar krävs om inget annat anges.")
    assert exam_latex._del_instruktion("C", False).startswith(
        "Del B löses med räknare. Fullständig redovisning krävs, och du ska")


def test_delen_utan_verktyg_ber_inte_eleven_redovisa_verktyget():
    """NP:s andra mening — «Visa också hur du använder ditt digitala verktyg»
    — hör till delen som HAR ett verktyg. Tillåter läraren inga i del B blir
    den meningen en order eleven inte kan följa."""
    tex = exam_latex.render_prov(_doc(
        exam_gen.hjalpmedelsregel("Inga digitala", "Formelblad")))
    assert r"Del B \textendash{} Digitala verktyg är inte tillåtna" in tex
    assert "Visa också hur du använder ditt digitala verktyg" not in tex
    assert exam_latex._del_instruktion("C", True) == (
        "Del B löses utan räknare. Fullständig redovisning krävs.")
    # … och på det oförändrade provet står den kvar.
    assert ("Visa också hur du använder ditt digitala verktyg"
            in exam_latex.render_prov(_doc(
                "Del B utan räknare. Del C med räknare.")))


# ───────────────────────────── rutten ────────────────────────────────────

def _done(resp) -> dict:
    ev = [json.loads(r[len("data:"):]) for r in resp.text.splitlines()
          if r.startswith("data:")]
    klara = [e for e in ev if e["type"] == "done"]
    assert klara, ev
    return klara[0]["result"]


def _fangad_prompt(monkeypatch) -> list[str]:
    prompter: list[str] = []
    riktig = exam_gen.build_prompt

    def spion(*a, **k):
        p = riktig(*a, **k)
        prompter.append(p)
        return p

    monkeypatch.setattr(exam_gen, "build_prompt", spion)
    return prompter


def _stubba_prov(monkeypatch):
    """Modellen skriver husets vanliga mening — det är just den som inte får
    stå kvar när läraren valt något annat."""
    monkeypatch.setattr(
        exam_gen, "_llm_round",
        lambda *a, **k: {"titel": "Prov", "kurs": "x",
                         "hjalpmedel": "Del B utan räknare. Del C med räknare.",
                         "uppgifter": [{"del": None, "formaga": "P",
                                        "typ": "rutin", "poang": [2, 0, 0],
                                        "text": "Beräkna", "losning": "1",
                                        "bedomning": "+2 E"}]})


def _generera(klient, monkeypatch, **extra):
    cid = klient.post("/api/courses",
                      json={"namn": "Matematik, nivå 2c"}).json()["id"]
    prompter = _fangad_prompt(monkeypatch)
    _stubba_prov(monkeypatch)
    r = klient.post("/api/exams/generate",
                    json={"course_id": cid, "klass": "NA25", "antal": 4,
                          "typ": "prov", "punkter_text": ["Derivator"],
                          **extra})
    assert r.status_code == 200, r.text
    return prompter, _done(r)


def test_rutten_utan_falten_och_med_forvalet_ger_samma_prompt(llm_ready,
                                                              monkeypatch):
    """Kassettregeln på ruttnivå. Klienten skickar inte fälten alls när valet
    står orört (plan.js hjalpmedelsavvikelse) — men servern är sista ordet,
    så förvalet skickat för hand måste ge samma prompt."""
    utan, _ = _generera(llm_ready, monkeypatch)
    med, res = _generera(llm_ready, monkeypatch, **FORVAL)
    assert med[0] == utan[0]
    assert "HJÄLPMEDLEN ÄR LÄRARENS VAL" not in utan[0]
    # Och modellens egen mening står kvar i dokumentet, som förut.
    assert res["exam"]["hjalpmedel"] == "Del B utan räknare. Del C med räknare."


def test_rutten_bar_avvikelsen_hela_vagen_in_i_dokumentet(llm_ready,
                                                          monkeypatch):
    prompter, res = _generera(llm_ready, monkeypatch, **AVVIKELSE)
    assert "HJÄLPMEDLEN ÄR LÄRARENS VAL" in prompter[0]
    # Dokumentet bär LÄRARENS mening, inte modellens: hon kryssade att
    # formelbladet är tillåtet på del A, och försättsbladet får inte säga
    # något annat bara för att modellen skrev husets vanliga rad.
    assert res["exam"]["hjalpmedel"] == exam_gen.hjalpmedelsregel(AVVIK_A,
                                                                  AVVIK_B)
    assert "formelblad" in res["exam"]["hjalpmedel"].lower()


def test_arbetsbladet_far_ingen_regel_ens_om_falten_skickas(llm_ready,
                                                            monkeypatch):
    cid = llm_ready.post("/api/courses",
                         json={"namn": "Matematik, nivå 2c"}).json()["id"]
    prompter = _fangad_prompt(monkeypatch)
    _stubba_prov(monkeypatch)
    r = llm_ready.post("/api/exams/generate",
                       json={"course_id": cid, "klass": "NA25", "antal": 4,
                             "typ": "arbetsblad", "punkter_text": ["Derivator"],
                             **AVVIKELSE})
    assert r.status_code == 200, r.text
    res = _done(r)
    assert "HJÄLPMEDLEN ÄR LÄRARENS VAL" not in prompter[0]
    assert res["exam"]["hjalpmedel"] == "Del B utan räknare. Del C med räknare."
