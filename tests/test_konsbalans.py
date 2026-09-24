"""Lärarens dom 2026-09-24 över bladen inför proven, som kod: bilderna
visade nästan bara kvinnor. «Borde vara lite män också. Lite pojkar.»

Bilden följer namnet (personvakt), och modellen valde Nora, Saga, Ella,
Alva, Sara och Elsa. Scener utan namngiven person fick också oftast en ung
kvinna. konsbalansvakt räknar båda sorterna på hela pappret.
"""
from app import exam_gen
from app.web import routes_exam

KVINNA = ("SCENE. A young woman stands by a wooden fence in a green meadow, "
          "seen from the side. The sky is open and calm on the left.\n"
          "Intended use: omkrets")
MAN = ("SCENE. A young man stands by a wooden fence in a green meadow, seen "
       "from the side. The sky is open and calm on the left.\n"
       "Intended use: omkrets")


def _u(text, scene=None):
    u = {"text": text}
    if scene:
        u["scen"] = {"begrepp": "omkrets", "filnamn": "a-01-hage",
                     "scene": scene}
    return u


def _papper(*uppgifter):
    return {"uppgifter": list(uppgifter)}


def _bladet_infor_proven():
    """Bladet i domen: sex kvinnonamn, varje bild en ung kvinna."""
    return _papper(
        _u("Nora köper $3$ kg äpplen för $24$ kr/kg. Vad betalar hon?",
           KVINNA),
        _u("Lös ekvationen $2x + 3 = 11$."),
        _u("Saga cyklar $12$ km på $40$ minuter. Beräkna hennes fart.",
           KVINNA),
        _u("Ella sparar $150$ kr i veckan. Hur mycket har hon efter ett år?",
           KVINNA),
        _u("Alva mäter en hage som är $8$ m lång och $5$ m bred.", KVINNA),
        _u("Förenkla $3(x + 2) - x$."),
        _u("Sara säljer bullar för $15$ kr styck. Hon säljer $40$ bullar.",
           KVINNA),
        _u("Elsa läser $30$ sidor per dag. När är boken på $270$ sidor slut?",
           KVINNA))


def test_bladet_i_domen_falls():
    fel = exam_gen.konsbalansvakt(_bladet_infor_proven())
    assert [f["code"] for f in fel] == ["konsbalans"] * 3
    # Sex kvinnor ger tre byten, varannan så att de sprids över pappret.
    assert [f["path"] for f in fel] == ["uppgift 3", "uppgift 5", "uppgift 8"]
    assert "Bilderna på pappret visar 6 personer, och 6 av dem är kvinnor"         in fel[0]["message"]
    assert "Byt Saga i uppgift 3 mot en man eller pojke" in fel[0]["message"]
    assert "mansnamn" in fel[0]["message"]
    assert "«a man» eller «a boy»" in fel[0]["message"]


def test_blandat_papper_slapps():
    tre_tre = _papper(
        _u("Nora köper äpplen.", KVINNA), _u("Hugo köper päron.", MAN),
        _u("Saga cyklar.", KVINNA), _u("Elias springer.", MAN),
        _u("Ella sparar."), _u("Liam lånar."))
    assert exam_gen.konsbalansvakt(tre_tre) == []
    # Två och en är gränsen: exakt två tredjedelar är ingen obalans.
    tva_en = _papper(_u("Nora köper."), _u("Saga cyklar."), _u("Ali lånar."))
    assert exam_gen.konsbalansvakt(tva_en) == []
    # Färre än tre personer räknas inte alls.
    assert exam_gen.konsbalansvakt(
        _papper(_u("Nora köper."), _u("Saga cyklar."))) == []


def test_obalans_at_andra_hallet_ocksa():
    fel = exam_gen.konsbalansvakt(_papper(
        _u("Hugo köper."), _u("Elias cyklar."), _u("Noah lånar."),
        _u("Leo springer.")))
    assert len(fel) == 2
    assert "Pappret har 4 personer" in fel[0]["message"]
    assert "en kvinna eller flicka" in fel[0]["message"]
    assert "kvinnonamn" in fel[0]["message"]
    # Ingen av dem står på en bild, så scenen nämns inte.
    assert "scenen" not in fel[0]["message"]


def test_bilderna_raknas_for_sig():
    """Blad 138: fyra mansnamn och fem kvinnonamn, men tre kvinnor och en
    man på bilderna. Det var bilderna läraren såg."""
    blad = _papper(
        _u("Saga köper äpplen.", KVINNA), _u("Nora cyklar.", KVINNA),
        _u("Leo sparar.", MAN), _u("Sara lånar.", KVINNA),
        _u("Liam springer."), _u("Hugo läser."), _u("Ali bakar."),
        _u("Alva målar."), _u("Ella simmar."))
    fel = exam_gen.konsbalansvakt(blad)
    assert [f["path"] for f in fel] == ["uppgift 2"]
    assert fel[0]["message"].startswith(
        "Bilderna på pappret visar 4 personer, och 3 av dem är kvinnor")
    assert "«a man» eller «a boy» i scenen" in fel[0]["message"]
    # Bytet på bilderna räknas som bytt i den andra räkningen. Utan Alva och
    # Ella blir det fem män mot två kvinnor, och en man utan bild byts.
    fel = exam_gen.konsbalansvakt(_papper(*blad["uppgifter"][:7]))
    assert [f["path"] for f in fel] == ["uppgift 2", "uppgift 5"]
    assert "Byt Liam i uppgift 5 mot en kvinna eller flicka" in         fel[1]["message"]
    # Namnet utan människa i scenen står inte på bilden.
    assert exam_gen._uppgiftens_personer(_u(
        "Hugo köper päron.", "SCENE. A wooden table with pears.")) == [
        ("Hugo", "man", False)]


def test_scenen_utan_namn_raknas():
    """Scener utan namngiven person fick oftast en ung kvinna."""
    tre = _papper(_u("En hage är $8$ m lång.", KVINNA),
                  _u("En åker är $40$ m bred.", KVINNA),
                  _u("En damm växer igen.", KVINNA))
    fel = exam_gen.konsbalansvakt(tre)
    assert len(fel) == 1
    assert "människan på bilden" in fel[0]["message"]
    assert "skriv «a man» eller «a boy» i scenen" in fel[0]["message"]
    # En man på en av bilderna räcker för tre.
    tre["uppgifter"][1]["scen"]["scene"] = MAN
    assert exam_gen.konsbalansvakt(tre) == []
    # «figure» och «person» bär inget kön och räknas inte.
    figur = _papper(*[_u("En hage.", "SCENE. A small faceless figure.")] * 4)
    assert exam_gen.konsbalansvakt(figur) == []
    # «Intended use:»-raden är svensk, och där är «man» ett pronomen.
    svensk = _papper(*[_u("En hage.", "SCENE. A meadow.\nIntended use: "
                          "hur man mäter")] * 4)
    assert exam_gen.konsbalansvakt(svensk) == []


def test_namnet_och_bilden_ar_en_person():
    """Hugo i texten och «a young man» på bilden är samma människa."""
    assert exam_gen._uppgiftens_personer(
        _u("Hugo köper päron.", MAN)) == [("Hugo", "man", True)]
    # Två namn i samma uppgift är två, genitivet räknas till namnet, och ett
    # namn räknas en gång per uppgift.
    assert exam_gen._uppgiftens_personer(_u(
        "Alva och Leo delar en pizza. Alvas bit är större än Leos bit.",
        KVINNA)) == [("Alva", "kvinna", True), ("Leo", "man", True)]
    # Deluppgifterna läses också.
    u = _u("En butik säljer bullar.")
    u["deluppgifter"] = [{"text": "Maja köper tre. Vad betalar hon?"}]
    assert exam_gen._uppgiftens_personer(u) == [("Maja", "kvinna", False)]


def test_vanliga_ord_forst_i_meningen_ar_inga_personer():
    for text in ("Hans lön är $300$ kr. Beräkna hans skatt.",
                 "Liv på jorden kräver vatten.",
                 "Beräkna arean. Figuren visar en hage.",
                 "Lös $N(t) = Ae^{kt}$."):
        assert exam_gen._uppgiftens_personer(_u(text)) == [], text
    # Mitt i meningen är det ett namn.
    assert exam_gen._uppgiftens_personer(
        _u("Lönen som Hans får är $300$ kr.")) == [("Hans", "man", False)]


def test_instruktionens_tolv_har_ratt_kon():
    """Namnlistan i INSTRUCTION och personvaktens kön säger samma sak som
    konsbalansvaktens."""
    for namn, kon in exam_gen._NAMN_KON.items():
        assert exam_gen._kon_ur_namn(namn) == kon, namn
    assert not exam_gen._MANSNAMN & exam_gen._KVINNONAMN


def test_domen_star_i_instruktionen():
    r = exam_gen.INSTRUCTION
    assert "BLANDA KÖNEN" in r
    assert "BÅDE MÄN OCH KVINNOR PÅ BILDERNA" in r
    # Förlagan i scenregeln sa «a person», som regeln själv förbjuder.
    assert "silhouette of a person" not in r
    assert "silhouette of a boy" in r


def test_vaktkedjan_och_efterkontrollen_ser_det():
    blad = _bladet_infor_proven()
    fel = exam_gen._raknade_fynd(blad, avsnitt=None, antal=None,
                                 delmoment=None, profil="arbetsblad")
    assert [f["path"] for f in fel if f["code"] == "konsbalans"] == [
        "uppgift 3", "uppgift 5", "uppgift 8"]
    fynd = routes_exam._konsfynd(blad)
    assert [f["kod"] for f in fynd] == ["konsbalans"] * 3
    # LAGBART: «Laga fynden» låser omskrivningen till de tre uppgifterna.
    assert routes_exam.efterkontroll_nummer(fynd) == [3, 5, 8]
    assert "konsbalans" in routes_exam._ATGARD
    assert "det andra könet" in routes_exam.efterkontroll_instruktion(fynd)
