"""Tankstrecksvakten (app/textvakt) på alla fyra papper.

Bakgrunden står i modulens docstring: läraren bad om det sex gånger på fyra
papper under veckan 1–6 sep 2026 (spårdata, spardata/forslag/2026-09-06.md),
och varje gång kostade det ett omskrivningsvarv. Anteckningarna hade vakten
sedan augusti; provet, arbetsbladet, gruppuppgiften och tavlan fick den
2026-09-12.

Det som prövas här är REGELN och dess undantag — att felet går in i
reparationsrundan prövas där rundorna bor (test_exam, test_lesson_board,
test_anteckningar)."""
from __future__ import annotations

import pytest

from app import exam_spec, notes_gen, textvakt, whiteboard_spec

EN, EM = "–", "—"


# ── Regeln själv ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tecken", [EN, EM])
def test_bada_tankstrecken_falls(tecken):
    assert textvakt.finn(f"Vi räknar först {tecken} sedan svarar vi") == tecken


@pytest.mark.parametrize("text", [
    "kurs-PM:et och e-postadressen",      # bindestreck i sammansättning
    "$x = -3$ är ett minustecken",        # matematikens minus är ASCII
    "Talet -7 ligger till vänster",
    "",
])
def test_bindestreck_och_minus_ar_fria(text):
    """ASCII-bindestrecket är ett ANNAT tecken, och det är också minus. Utan
    den skillnaden hade vakten inte kunnat gå på uppgiftstexter alls."""
    assert textvakt.finn(text) is None


def test_sifferspannet_ar_undantaget_bara_nar_anroparen_ber_om_det():
    """«s. 27–30» är intervalltecken, inte lärarens em dash — och tavlans
    prompt BER om den formen. Anteckningarna har inga bokhänvisningar och
    behåller den stränga regeln."""
    assert textvakt.finn("Boken s. 27–30, uppg. 1218–1227",
                         tillat_spann=True) is None
    assert textvakt.finn("Boken s. 27–30", tillat_spann=False) == EN
    # Undantaget är SMALT: em dash är aldrig ett spann, och ett tankstreck med
    # luft omkring sig är en paus i en mening hur många siffror som än står
    # runt den.
    assert textvakt.finn("1218 – 1227", tillat_spann=True) == EN
    assert textvakt.finn("s. 27—30", tillat_spann=True) == EM
    # Två spann i rad: det första får inte äta siffran det andra behöver.
    assert textvakt.finn("27–30 och 88–90", tillat_spann=True) is None


def test_meddelandet_sager_vad_som_ska_goras():
    """Ett besked som bara förbjuder ett tecken lagas med ett annat tecken."""
    fel = textvakt.granska([("uppgift 1.text", f"Räkna först {EM} svara sen")])
    assert [f["code"] for f in fel] == ["tankstreck"]
    assert fel[0]["path"] == "uppgift 1.text"
    assert "em dash" in fel[0]["message"]
    assert "Skriv om meningen" in fel[0]["message"]


def test_ett_fynd_per_strang():
    """Modellen ska skriva om meningen, inte byta tecken ett i taget."""
    assert len(textvakt.granska([("a", f"ett {EN} två {EM} tre")])) == 1


# ── Provet, arbetsbladet och gruppuppgiften ─────────────────────────────────

def _exam() -> dict:
    return {
        "titel": "Andragradsfunktioner", "kurs": "Ma2b",
        "hjalpmedel": "Räknare och formelblad.",
        "uppgifter": [
            {"del": "B", "formaga": "B", "typ": "rutin", "poang": [1, 0, 0],
             "text": "Ange nollställena till $f(x) = (x-1)(x+3)$.",
             "losning": "$x = 1$ och $x = -3$.",
             "bedomning": "+1 E korrekt svar"},
        ],
    }


def _tankstreck(fel: list[dict]) -> list[str]:
    return [f["path"] for f in fel if f["code"] == "tankstreck"]


def _fel(exam: dict, profil: str = "prov") -> list[str]:
    """Felen ur den RIKTIGA ingången — validate_exam_json är den
    reparationsloopen kallar, och vakten ska sitta i den."""
    _doc, fel = exam_spec.validate_exam_json(exam, profil)
    return _tankstreck(fel)


def test_rent_prov_slapps_igenom():
    assert _fel(_exam()) == []


@pytest.mark.parametrize("falt,vantad", [
    ("titel", "titel"),
    ("hjalpmedel", "hjalpmedel"),
    ("instruktion", "instruktion"),
    ("nyckelfraga", "nyckelfraga"),
])
def test_dokumentets_egna_texter_granskas(falt, vantad):
    exam = _exam()
    exam[falt] = f"Läs uppgiften {EM} svara sedan"
    assert _fel(exam) == [vantad]


@pytest.mark.parametrize("falt", ["text", "losning", "bedomning", "notis"])
def test_uppgiftens_fritext_granskas(falt):
    """Uppgiftstexten, FACIT och bedömningsanvisningen — läraren läser alla
    tre, och det var i facit och bedömningen tankstrecken satt."""
    exam = _exam()
    exam["uppgifter"][0][falt] = f"Först detta {EN} sedan detta"
    assert _fel(exam) == [f"uppgift 1.{falt}"]


def test_deluppgiftens_bokstav_star_i_sokvagen():
    """Sökvägen ska peka ut fältet i dokumentets eget språk: «uppgift 1b»,
    inte «uppgifter[0].deluppgifter[1]»."""
    exam = _exam()
    exam["uppgifter"][0].update({
        "poang": [0, 0, 0], "losning": "", "bedomning": "",
        "deluppgifter": [
            {"poang": [1, 0, 0], "text": "Ange $x$.", "losning": "$x = 1$.",
             "bedomning": "+1 E svar"},
            {"poang": [1, 0, 0], "text": f"Rita grafen {EM} märk ut nollställena.",
             "losning": "Parabel.", "bedomning": "+1 E figur"},
        ]})
    assert _fel(exam) == ["uppgift 1b.text"]


def test_tabeller_svarsfalt_och_alternativ_granskas():
    exam = _exam()
    exam["uppgifter"][0].update({
        "svarsfalt": [f"Ekvation {EN} svar"],
        "tabell": {"rubriker": ["År", f"Antal {EM} totalt"],
                   "rader": [["2024", "12"]]},
        "alternativ": ["Ett", "Två", f"Tre {EN} fyra"],
        "ratt_alternativ": 0})
    assert _fel(exam) == ["uppgift 1.svarsfalt 1",
                          "uppgift 1.alternativ 3",
                          "uppgift 1.tabell.rubrik 2"]


def test_elevlosningarnas_rader_och_domar_granskas():
    """Elevlösningarna är bedömningens papper och skrivs av modellen — samma
    prosa som allt annat."""
    exam = _exam()
    exam["uppgifter"][0]["elevlosningar"] = [
        {"etikett": "Elevlösning A",
         "partier": [{"rader": [f"$x = 1$ {EN} fel tecken"], "poang": [0, 0, 0],
                      "dom": f"Ingen poäng {EM} tecknet är fel."}]}]
    assert _fel(exam) == ["uppgift 1.Elevlösning A.parti 1.rad 1",
                          "uppgift 1.Elevlösning A.parti 1.dom"]


def test_bildtexten_pa_forsattsbladet_granskas():
    """Lärarens ord 2026-09-06 om just den här texten: «Det kan vara tre
    meningar. … Men det ska vara kort och utan em dash.»"""
    exam = _exam()
    exam["forsattsbild"] = {
        "person": "Muhammad al-Khwarizmi (ca 780–850), algebrans namngivare.",
        "scene": "SCENE. A scholar in a ninth-century Baghdad study, bent over "
                 "a manuscript by lamplight. Intended use: exam cover portrait.",
        "bildtext": f"En lärd man i Bagdad {EM} han gav algebran dess namn."}
    # Personradens «780–850» är ett sifferspann och står kvar.
    assert _fel(exam) == ["forsattsbild.bildtext"]


def test_bokhanvisningens_sidspann_star_kvar_pa_pappret():
    exam = _exam()
    exam["uppgifter"][0]["text"] = "Använd metoden från boken s. 34–36."
    assert _fel(exam) == []


def test_gruppuppgiften_far_samma_vakt():
    exam = _exam()
    exam["grupp"] = {"elever": 3, "langd_min": 45, "redovisning": "muntligt"}
    exam["instruktion"] = f"Läs tillsammans {EM} skriv ett svar."
    assert _fel(exam, "gruppuppgift") == ["instruktion"]


def test_appens_egna_falt_rors_aldrig():
    """`klockslag` och `granser` sätts av LÄRARENS val i routen, aldrig av
    modellen. Ett tankstreck där är kodens eget och får inte kosta en runda."""
    exam = _exam()
    exam["klockslag"] = "12:45–14:15"
    exam["granser"] = {"E": 8, "C": 14, "A": 20}
    assert _fel(exam) == []


# ── Tavlan ──────────────────────────────────────────────────────────────────

def _board(*sections) -> dict:
    return {"title": "Derivatans definition",
            "boards": [{"width": 900, "height": 780,
                        "sections": list(sections)}]}


def _board_fel(doc: dict) -> list[str]:
    _d, fel = whiteboard_spec.validate_board_json(doc)
    return _tankstreck(fel)


@pytest.mark.parametrize("kind", ["text", "heading"])
def test_tavlans_text_och_rubriker_granskas(kind):
    fel = _board_fel(_board({"kind": kind, "text": f"Förkorta först {EN} sedan"}))
    assert fel == ["boards[0].sections[0].text"]


def test_listpunkter_granskas_men_punkttecknet_ar_fritt():
    """`bullet` ÄR ett tankstreck i appens egna few-shot-exempel: det är
    listans punkt i marginalen, inte en mening."""
    fel = _board_fel(_board(
        {"kind": "list", "bullet": EN,
         "items": ["Vad satsen betyder", f"Två exempel {EM} tillsammans"]}))
    assert fel == ["boards[0].sections[0].items[1]"]


def test_agendans_sidspann_faller_inte():
    """Prompten (lesson_board regel 2) ber uttryckligen om «Boken s. 27–30,
    uppg. 1218–1227». Fälldes den skulle vakten slåss med prompten."""
    assert _board_fel(_board(
        {"kind": "list", "bullet": EN,
         "items": ["Vad satsen betyder", "Boken s. 88–90, uppg. 3110–3118"]})) == []


def test_latex_rors_aldrig():
    """I matematiken betyder strecken något annat, och math-sektionen är
    dessutom inte den prosa läraren klagade på."""
    assert _board_fel(_board(
        {"kind": "math", "latex": f"f(x) {EN} g(x)"})) == []


def test_tankstreck_inuti_en_row_hittas():
    """Figur till vänster, formler till höger — texten inuti behållaren är
    lika mycket tavla som den utanför."""
    fel = _board_fel(_board(
        {"kind": "row", "children": [
            {"kind": "text", "text": "Lutningen"},
            {"kind": "text", "text": f"Låt $h$ gå mot noll {EN} hastigheten"}]}))
    assert fel == ["boards[0].sections[0].children[1].text"]


def test_kolumntavlan_granskas_ocksa():
    doc = {"title": "T", "boards": [{"width": 900, "height": 780, "columns": [
        {"weight": 1, "sections": [{"kind": "text",
                                    "text": f"Först {EM} sedan"}]}]}]}
    assert _board_fel(doc) == ["boards[0].columns[0].sections[0].text"]


# ── Anteckningarna ──────────────────────────────────────────────────────────

def test_anteckningarna_beter_sig_som_forut():
    """Femte dokumenttypen hade vakten först och ska inte ha ändrats av att
    den flyttade: samma felkod, samma sökväg, samma besked — och INGET
    sifferspannsundantag (pappret bär inga bokhänvisningar)."""
    def _anteckningar(forsta: str) -> notes_gen.NoteDoc:
        # Tre sektioner: taket MIN_SEKTIONER är ett eget fel och ska inte
        # skymma det som mäts här.
        return notes_gen.NoteDoc(
            titel="Första lektionen",
            sektioner=[notes_gen.Sektion(rubrik="Boken", stycken=[forsta]),
                       notes_gen.Sektion(rubrik="Rutiner",
                                         stycken=["Vi börjar kvart över."]),
                       notes_gen.Sektion(rubrik="Provet",
                                         stycken=["Provet ligger i vecka 42."])])

    fel = notes_gen.validate_notes(
        _anteckningar(f"Vi arbetar i boken {EN} alla får ett."))
    assert [f["code"] for f in fel] == ["tankstreck"]
    assert fel[0]["path"] == "sektion 1.stycke 1"
    assert "utan tankstreck" in fel[0]["message"]

    strangt = notes_gen.validate_notes(
        _anteckningar("Läs s. 12–14 till fredag."))
    assert [f["code"] for f in strangt] == ["tankstreck"]
