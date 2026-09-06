"""Markeringarna ska peka på det som ändrades — inte på det läraren bad om.

Regexp-gissningen i plan.js hade en inbyggd lögn: bad läraren om «något
svårare» målades uppgift 3 och 5 röda oavsett vad modellen faktiskt gjorde.
Testerna här låser den ärliga vägen — diffen av dokumentets JSON — och särskilt
de tre fall som är lätta att bygga fel: en INSKJUTEN post får inte märka allt
efter sig, ett oförändrat dokument får inte märka något alls, och tavlans
id-serie måste följa motorns nodräkning och inte sektionslistans index.
"""
from app import dokumentdiff as dd


# ------------------------------------------------------------------ provet --

def _prov(*texter):
    return {"titel": "Prov", "kurs": "Ma2c", "hjalpmedel": "miniräknare",
            "uppgifter": [{"text": t, "poang": [1, 0, 0]} for t in texter]}


def test_oforandrat_prov_marker_ingenting():
    p = _prov("a", "b", "c")
    assert dd.andrade_element("prov", p, dict(p)) == []


def test_en_omskriven_uppgift_marker_bara_den():
    assert dd.andrade_element("prov", _prov("a", "b", "c"),
                              _prov("a", "NY", "c")) == ["uppg2"]


def test_en_inskjuten_uppgift_flyttar_inte_alla_efter_sig():
    """Positionsdiffen skulle säga uppg2, uppg3 OCH uppg4 — men b och c står
    ordagrant kvar, de har bara fått ett nytt nummer."""
    assert dd.andrade_element("prov", _prov("a", "b", "c"),
                              _prov("a", "NY", "b", "c")) == ["uppg2"]


def test_en_borttagen_uppgift_marks_pa_den_som_tog_platsen():
    # Det finns ingen nod kvar att sätta nålen på — läraren ska ändå se VAR.
    assert dd.andrade_element("prov", _prov("a", "b", "c"),
                              _prov("a", "c")) == ["uppg2"]


def test_sidhuvudet_har_eget_id():
    fore = _prov("a")
    efter = _prov("a") | {"titel": "Nytt namn"}
    assert dd.andrade_element("prov", fore, efter) == ["rubrik"]


def test_provtiden_och_hjalpmedlen_sitter_i_provtabellen():
    """Båda fälten nådde förr bara PDF:en, och nålarna satt därefter: `tid_min`
    på sidhuvudet (som inte bär tiden alls) och `hjalpmedel` på
    instruktionsbandet. Nu ritar provtabellen dokumentets fält, och
    hjälpmedelsregeln står EN gång till i OBS-bandet — därför två id."""
    fore = _prov("a")
    assert dd.andrade_element("prov", fore, _prov("a") | {"tid_min": 100}) \
        == ["avtal0"]
    assert dd.andrade_element("prov", fore, _prov("a") | {"hjalpmedel": "inga"}) \
        == ["avtal0", "instr"]


def test_forsattsbildens_portratt_har_eget_id():
    """Läraren ber om «en annan matematiker», modellen byter person — och nålen
    ska sitta på BILDEN på försättsbladet (blad.js markera: `forsatt`), inte på
    rubriken och inte ingenstans. Utan raden i _prov sa panelen «ingenting
    ändrades» om precis det hon bett om."""
    fore = _prov("a")
    napier = {"person": "John Napier (1550–1617), logaritmernas man.",
              "scene": "SCENE. A dim stone study at night. " + "x" * 80}
    euler = dict(napier, person="Leonhard Euler (1707–1783), potensernas man.")
    assert dd.andrade_element("prov", fore, _prov("a") | {"forsattsbild": napier}) \
        == ["forsatt"]
    assert dd.andrade_element(
        "prov", _prov("a") | {"forsattsbild": napier},
        _prov("a") | {"forsattsbild": euler}) == ["forsatt"]
    # Två prov UTAN porträtt är lika — ett valfritt fält får inte märka något.
    assert dd.andrade_element("prov", fore, _prov("a")) == []


def _giltigt(*poang, **extra):
    """Ett dokument som ExamDoc verkligen kan läsa — kravgränserna räknas ur
    poängen, så de går inte att pröva på ett skelett."""
    return {"titel": "Prov", "kurs": "Ma2c", "hjalpmedel": "miniräknare",
            "uppgifter": [{"text": f"uppgift {i + 1}", "poang": list(p),
                           "losning": "svar", "bedomning": "+1",
                           "formaga": "P", "typ": "rutin"}
                          for i, p in enumerate(poang)]} | extra


def test_betygsgranserna_marks_nar_poangen_flyttar_dem():
    """Gränserna är ingen fältrad i JSON:en — de RÄKNAS ur poängen
    (exam_spec.kravgranser) och står i sin egen tabell på försättsbladet. Utan
    den här jämförelsen flyttade «sänk E-gränsen» talen på pappret medan
    panelen sa att ingenting hänt."""
    fore = _giltigt((2, 0, 0), (0, 2, 0))
    efter = _giltigt((2, 0, 0), (0, 6, 0))
    ut = dd.andrade_element("prov", fore, efter)
    assert "avtal1" in ut and "uppg2" in ut
    # Samma poäng, ny lydelse: uppgiften märks, gränserna står stilla.
    ny_text = _giltigt((2, 0, 0), (0, 2, 0))
    ny_text["uppgifter"][1]["text"] = "en annan fråga"
    assert dd.andrade_element("prov", fore, ny_text) == ["uppg2"]


def test_gruppuppgiftens_namnrader_och_loftesrad():
    """Metaraden är borttagen från pappret (läraren säger villkoren själv) —
    grupp-fälten syns bara genom namnraderna och bandets löftesrad, och det är
    dit en ändring ska peka. Tiden har ingen synlig rad och märks inte alls."""
    fore = _prov("a") | {"grupp": {"elever": 3, "langd_min": 40,
                                   "redovisning": "muntligt"}}
    efter = _prov("a") | {"grupp": {"elever": 4, "langd_min": 60,
                                    "redovisning": "muntligt"}}
    assert dd.andrade_element("gruppuppgift", fore, efter) == ["namn"]
    bara_tid = _prov("a") | {"grupp": {"elever": 3, "langd_min": 60,
                                       "redovisning": "muntligt"}}
    assert dd.andrade_element("gruppuppgift", fore, bara_tid) == []
    ny_form = _prov("a") | {"grupp": {"elever": 3, "langd_min": 40,
                                      "redovisning": "poster"}}
    assert dd.andrade_element("gruppuppgift", fore, ny_form) == ["instr"]


def test_varje_uppgiftspapper_diffas_som_provet():
    """En typ som saknas i tabellen är inte harmlös: okänd typ ger tom lista,
    och klienten läser tom lista som «ingenting på pappret ändrades». Panelen
    säger alltså just det efter VARJE omskrivning av ett sådant papper.
    Det har hänt en gång, och raden här är vakten."""
    for typ in ("prov", "arbetsblad", "gruppuppgift"):
        assert dd.andrade_element(typ, _prov("a"), _prov("b")) == ["uppg1"], typ
    assert dd.andrade_element("pahitt", _prov("a"), _prov("b")) == []


def test_bandtexten_ar_instruktionen():
    """Läraren pekade på instruktionsrutan och bad att en mening skulle bort.
    Rutan var appens mall och fanns inte i JSON:en — nu gör den det
    (exam_spec.ExamDoc.instruktion), och ändras den ska nålen sitta på
    bandet."""
    fore = _prov("a") | {"instruktion": "Läs uppgiften tillsammans. "
                                        "Redovisas skriftligt: ett gemensamt "
                                        "svar lämnas in vid lektionens slut."}
    efter = _prov("a") | {"instruktion": "Läs uppgiften tillsammans."}
    assert dd.andrade_element("gruppuppgift", fore, efter) == ["instr"]


def test_arbetsblad_diffas_som_prov():
    assert dd.andrade_element("arbetsblad", _prov("a"), _prov("b")) == ["uppg1"]


# ---------------------------------------------------------- anteckningarna --

def _ant(*rubriker, kom=None):
    return {"titel": "Stödpapper", "klass": "NA25",
            "sektioner": [{"rubrik": r, "stycken": [r + "!"]} for r in rubriker],
            "kom_ihag": kom}


def test_en_omskriven_sektion_marks_med_sitt_nummer():
    assert dd.andrade_element("anteckningar", _ant("A", "B", "C"),
                              _ant("A", "NY", "C")) == ["sekt2"]


def test_kom_ihag_ar_en_ruta_hur_manga_rader_den_an_bar():
    assert dd.andrade_element("anteckningar", _ant("A", kom=["x"]),
                              _ant("A", kom=["x", "y"])) == ["komihag"]


def test_tom_lista_och_saknat_falt_ar_samma_sak():
    assert dd.andrade_element("anteckningar", _ant("A", kom=None),
                              _ant("A", kom=[])) == []


# ------------------------------------------------------------------ tavlan --

def _brade(*sektioner, annotations=None):
    return {"title": "T", "boards": [{"width": 900, "height": 780,
                                      "sections": list(sektioner),
                                      "annotations": annotations or []}]}


def _txt(t):
    return {"kind": "text", "text": t}


def test_tavelrutan_marks_med_sitt_domindex():
    assert dd.andrade_element("tavla", _brade(_txt("a"), _txt("b")),
                              _brade(_txt("a"), _txt("NY"))) == ["tav1"]


def test_spacer_far_ingen_nod_och_ska_inte_rakna_upp_serien():
    """`spacer` flyttar bara ner y i motorn — den blir ingen `.wb-element`, och
    räknas den ändå pekar varje nål efter den på fel ruta."""
    fore = _brade(_txt("a"), {"kind": "spacer", "size": 20}, _txt("b"))
    efter = _brade(_txt("a"), {"kind": "spacer", "size": 20}, _txt("NY"))
    assert dd.andrade_element("tavla", fore, efter) == ["tav1"]


def test_understruken_rubrik_lagger_beslag_pa_ett_extra_nummer():
    """Motorn ritar understrykningen som en EGEN `.wb-element` direkt efter
    rubriken (tavla-wb.js layoutFlow). Rutan efter blir alltså tav2, inte
    tav1."""
    rub = {"kind": "heading", "text": "Derivator", "underline": {}}
    assert dd.andrade_element("tavla", _brade(rub, _txt("a")),
                              _brade(rub, _txt("NY"))) == ["tav2"]


def test_kolumner_raknas_i_ordning_och_sections_ignoreras():
    """Har brädet `columns` ritar renderBoard dem och rör aldrig `sections`."""
    def doc(sista):
        return {"title": "T", "boards": [{
            "width": 900, "height": 780,
            "sections": [_txt("ignoreras helt")],
            "columns": [{"sections": [_txt("v1"), _txt("v2")]},
                        {"sections": [_txt("h1"), _txt(sista)]}]}]}
    assert dd.andrade_element("tavla", doc("h2"), doc("NY")) == ["tav3"]


def test_annotationerna_kommer_efter_sektionerna():
    fore = _brade(_txt("a"), annotations=[{"kind": "circle", "x": 1, "y": 2}])
    efter = _brade(_txt("a"), annotations=[{"kind": "circle", "x": 9, "y": 2}])
    assert dd.andrade_element("tavla", fore, efter) == ["tav1"]


def test_tva_braden_delar_en_enda_serie():
    """`taggaTavla` numrerar hela värden på en gång — inte om från noll per
    bräde."""
    def doc(sista):
        return {"title": "T", "boards": [
            {"width": 900, "height": 780, "sections": [_txt("a"), _txt("b")]},
            {"width": 900, "height": 780, "sections": [_txt("c"), _txt(sista)]}]}
    assert dd.andrade_element("tavla", doc("d"), doc("NY")) == ["tav3"]


# --------------------------------------------------------- barnen i raden --
# Läraren 2026-09-05: «jag kan inte markera allt heller, allting är inte
# markerbart». Hela figur-och-formler-raden var EN ruta. Nu bär motorn `wb-del`
# på barnen (tavla-wb.js renderSection), blad.js taggaTavla ger dem förälderns
# id plus sitt eget index med punkt, och serien här måste räknas EXAKT likadant
# — annars pekar nålen på fel ruta.


def _mat(t):
    return {"kind": "math", "latex": t}


def _rad(*barn, **falt):
    return {"kind": "row", "children": list(barn), **falt}


def test_barnen_i_en_rad_far_punktserie_ur_foraldern():
    fore = _brade(_txt("a"), _rad(_mat("x"), _mat("y")))
    efter = _brade(_txt("a"), _rad(_mat("x"), _mat("NY")))
    assert dd.andrade_element("tavla", fore, efter) == ["tav1.1"]


def test_barnbarn_i_en_kolumn_gar_hela_vagen_ned():
    """`tav0.1.2` — index bland syskonen, rekursivt, precis som JSON:ens
    `children[1].children[2]`."""
    def doc(sista):
        return _brade(_rad(_mat("v"),
                           {"kind": "col",
                            "children": [_txt("a"), _txt("b"), _txt(sista)]}))
    assert dd.andrade_element("tavla", doc("c"), doc("NY")) == ["tav0.1.2"]


def test_raden_sjalv_marks_nar_det_ar_raden_som_andrades():
    """Byter raden gap eller justering är det RADEN nålen ska sitta på, inte
    ett av barnen."""
    fore = _brade(_rad(_mat("x"), _mat("y"), gap=10))
    efter = _brade(_rad(_mat("x"), _mat("y"), gap=40))
    assert dd.andrade_element("tavla", fore, efter) == ["tav0"]


def test_spacer_i_en_rad_raknas_i_indexet_men_blir_ingen_ruta():
    """Motorn ritar varje barn i en row, också en `spacer` — den blir en tom
    ruta utan klass. Den är alltså inte markerbar, men den TAR sitt nummer, och
    räknas den bort pekar nålen på fel barn."""
    def doc(sista):
        return _brade(_rad(_mat("x"), {"kind": "spacer", "size": 8}, _mat(sista)))
    assert dd.andrade_element("tavla", doc("y"), doc("NY")) == ["tav0.2"]
    # …och en ändring som BARA gäller spacern har ingen ruta att sitta på: då
    # är det raden som är ändringen.
    fore = _brade(_rad(_mat("x"), {"kind": "spacer", "size": 8}))
    efter = _brade(_rad(_mat("x"), {"kind": "spacer", "size": 30}))
    assert dd.andrade_element("tavla", fore, efter) == ["tav0"]


def test_callouten_ar_en_ruta_och_dess_barn_numreras_inte():
    """Callouten lägger sina barn genom layoutFlow, där en spacer försvinner
    helt och en understruken rubrik tar en extra nod. Två räkneregler i en
    serie går isär förr eller senare — callouten är därför en ruta."""
    def doc(sista):
        return _brade({"kind": "callout", "children": [_txt("a"), _txt(sista)]})
    assert dd.andrade_element("tavla", doc("b"), doc("NY")) == ["tav0"]


def test_tavelvag_ger_elementkartans_vag():
    doc = _brade(_txt("a"), _rad(_mat("x"),
                                 {"kind": "col", "children": [_txt("q")]}))
    assert dd.tavelvag(doc, "tav0") == "boards[0].sections[0]"
    assert dd.tavelvag(doc, "tav1.1") == "boards[0].sections[1].children[1]"
    assert dd.tavelvag(doc, "tav1.1.0") == \
        "boards[0].sections[1].children[1].children[0]"
    # Ett id som inte finns ger None — och då finns inget mål att låsa.
    assert dd.tavelvag(doc, "tav9") is None
    assert dd.tavelvag(doc, "") is None


def test_tavelvag_raknar_kolumner_och_understrykningens_reserverade_nummer():
    rub = {"kind": "heading", "text": "Derivator", "underline": {}}
    doc = {"title": "T", "boards": [{
        "width": 900, "height": 780,
        "columns": [{"sections": [rub, _txt("v")]},
                    {"sections": [_rad(_mat("h"))]}]}]}
    # tav1 är understrykningens egen nod: motorn ritar den, dokumentet har
    # ingen sektion där, och vägen finns alltså inte.
    assert dd.tavelvag(doc, "tav0") == "boards[0].columns[0].sections[0]"
    assert dd.tavelvag(doc, "tav1") is None
    assert dd.tavelvag(doc, "tav2") == "boards[0].columns[0].sections[1]"
    assert dd.tavelvag(doc, "tav3.0") == \
        "boards[0].columns[1].sections[0].children[0]"


# ------------------------------------------------------------------ ramen --

def test_okand_typ_och_trasiga_dokument_ger_tom_lista():
    # Tomt betyder «vi har inget att säga» — klienten faller då tillbaka på sin
    # egen läsning i stället för att stå utan markering.
    assert dd.andrade_element("nagot-annat", _prov("a"), _prov("b")) == []
    assert dd.andrade_element("prov", None, _prov("b")) == []
    assert dd.andrade_element("prov", _prov("a"), "inte ett dokument") == []


def test_samma_id_kommer_bara_en_gang():
    fore = _prov("a") | {"hjalpmedel": "x", "nyckelfraga": "y"}
    efter = _prov("a") | {"hjalpmedel": "X", "nyckelfraga": "Y"}
    assert dd.andrade_element("prov", fore, efter) == ["avtal0", "instr"]
