"""Provgeneratorn (Fas 4): schema/balans/kravgränser, LaTeX-rendering,
PDF-modul med stubbat kompilatoranrop samt genereringslooparna."""
import base64
import copy
import json
import re
import subprocess

import pytest

from app import exam_gen, exam_latex, exam_pdf, exam_spec

# Minimal giltig 1×1-pixels PNG (RGB, okomprimerad enda scanline) — samma
# sond som tools/seed_tectonic_cache.py använder för att motionera
# \includegraphics-kodvägen utan att bero på att Pillow finns installerat.
_MINIMAL_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mM4YaMBAAL8"
    "AS3Bfun7AAAAAElFTkSuQmCC"
)


def _exam() -> dict:
    """Balanserat exempelprov, 20 p (E 9 / C 6 / A 5), alla sex förmågor
    representerade. Uppfyller golv, nivåbalans, stigande svårighet (del C)
    och antiklumpning — den kanoniska 'giltiga' fixturen."""
    return {
        "titel": "Prov — Andragradsfunktioner",
        "kurs": "Ma2b", "klass": "SA23", "datum": "2026-10-05",
        "tid_min": 120,
        "hjalpmedel": "Del B utan räknare. Del C med räknare och formelblad.",
        "uppgifter": [
            {"del": "B", "formaga": "B", "typ": "rutin", "poang": [3, 0, 0],
             "text": "Ange nollställena till $f(x) = (x-1)(x+3)$.",
             "innehall": ["nollställen"],
             "losning": "$x = 1$ och $x = -3$.",
             "bedomning": "+3 E för båda nollställena."},
            {"del": "B", "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Lös ekvationen $x^2 - 4x + 3 = 0$.",
             "innehall": ["pq-formeln"],
             "losning": "$x = 1$ eller $x = 3$.",
             "bedomning": "+1 E per korrekt rot."},
            {"del": "C", "formaga": "P", "typ": "redovisning", "poang": [1, 1, 1],
             "text": "Lös ekvationen $x^2 + 6x - 7 = 0$ med kvadratkomplettering.",
             "innehall": ["kvadratkomplettering"],
             "losning": "$(x+3)^2 = 16$ ger $x = 1$ eller $x = -7$.",
             "bedomning": "+1 E ansats, +1 C metod, +1 A generalisering."},
            {"del": "C", "formaga": "PL", "typ": "problem", "poang": [1, 1, 1],
             "text": "En rektangulär hage har omkretsen 60 m. Bestäm de mått "
                     "som maximerar arean.",
             "innehall": ["optimering", "andragradsfunktioner"],
             "losning": "Kvadrat $15 \\times 15$ m ger max.",
             "bedomning": "+1 E modell, +1 C lösning, +1 A motivering av max."},
            {"del": "C", "formaga": "M", "typ": "problem", "poang": [1, 0, 1],
             "text": "En population beskrivs av $N(t) = 200 \\cdot 1{,}05^t$. "
                     "Bestäm när populationen har fördubblats.",
             "innehall": ["exponentiell modell"],
             "losning": "$1{,}05^t = 2$ ger $t \\approx 14{,}2$ år.",
             "bedomning": "+1 E ansats, +1 A korrekt tolkning av modellen."},
            {"del": "C", "formaga": "R", "typ": "resonemang", "poang": [1, 1, 1],
             "text": "Avgör om påståendet stämmer: en andragradsfunktion med "
                     "$a < 0$ saknar minsta värde. Motivera.",
             "innehall": ["andragradsfunktioner"],
             "losning": "Sant — grafen är en nedåtriktad parabel.",
             "bedomning": "+1 E ställningstagande, +1 C motivering, +1 A stringens."},
            {"del": "C", "formaga": "K", "typ": "redovisning", "poang": [0, 3, 1],
             "text": "Förklara med graf och ord hur symmetrilinjen bestäms "
                     "för $f(x) = x^2 - 6x + 5$.",
             "innehall": ["symmetrilinje"],
             "losning": "$x = 3$ via $-b/(2a)$ eller nollställenas mittpunkt.",
             "bedomning": "+3 C tydlig förklaring, +1 A flera representationer."},
        ],
    }


def _exam_med_deluppgifter() -> dict:
    """_exam() med uppgift 7 (K) uppdelad i två deluppgifter som ärver
    K/redovisning och summerar till [0,3,1] — aggregatet är oförändrat, så
    hela provet ska fortfarande passera alla balansregler."""
    data = _exam()
    data["uppgifter"][6] = {
        "del": "C", "formaga": "K", "typ": "redovisning", "poang": [0, 0, 0],
        "text": "Undersök symmetrilinjen för $f(x) = x^2 - 6x + 5$.",
        "innehall": ["symmetrilinje"], "losning": "", "bedomning": "",
        "deluppgifter": [
            {"poang": [0, 2, 0],
             "text": "Bestäm symmetrilinjens ekvation.",
             "losning": "$x = 3$ via $-b/(2a)$.",
             "bedomning": "+2 C korrekt linje med metod."},
            {"poang": [0, 1, 1],
             "text": "Förklara med graf och ord varför den ligger där.",
             "losning": "Mittpunkt mellan nollställena; grafen är symmetrisk.",
             "bedomning": "+1 C förklaring, +1 A flera representationer."},
        ],
    }
    return data


def _exam_med_flerval() -> dict:
    """_exam() med uppgift 2 som flervalsfråga (oförändrad poäng/förmåga)."""
    data = _exam()
    data["uppgifter"][1] = {
        "del": "B", "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
        "text": "Vilket är ett nollställe till $f(x) = x^2 - 4x + 3$?",
        "innehall": ["nollställen"],
        "alternativ": ["$x = 0$", "$x = 1$", "$x = 2$", "$x = 4$"],
        "ratt_alternativ": 1,
        "losning": "$x = 1$ ger $f(1) = 0$.",
        "bedomning": "+2 E för rätt alternativ (B)."}
    return data


def _exam_med_notis() -> dict:
    """_exam() med en notis (inramad instruktionsruta) på uppgift 1."""
    data = _exam()
    data["uppgifter"][0]["notis"] = "Rita gärna en teckenrad som stöd."
    return data


# ------------------------------------------------------- JSON-parsning ----

def test_parse_exam_repairs_eaten_latex_backslashes():
    """Modellen skriver "\\times" oescapat i JSON — json.loads tolkar \\t som
    TAB och kvar blir "2 <TAB>imes 3". Reparationen återställer kommandot
    inuti $…$-segment men rör inte äkta radbrytningar i löptext."""
    raw = ('{"titel": "T", "uppgifter": ['
           '{"text": "Beräkna $2 \\times (3 + 4)$."},'
           '{"text": "Visa att $a \\neq b$."},'
           '{"text": "rad1\\nrad2 utanför matte lämnas orörd"}]}')
    exam = exam_gen._parse_exam(raw)
    assert exam["uppgifter"][0]["text"] == "Beräkna $2 \\times (3 + 4)$."
    assert exam["uppgifter"][1]["text"] == "Visa att $a \\neq b$."
    assert exam["uppgifter"][2]["text"] == "rad1\nrad2 utanför matte lämnas orörd"


# ------------------------------------------------------------------ schema --

def test_valid_exam_passes():
    doc, errors = exam_spec.validate_exam_json(_exam())
    assert doc is not None
    assert errors == []


def test_gruppera_per_del_bevarar_elevens_ordning():
    """Delgrupperingen måste ge exakt den sekvens eleven ser: B, C, D,
    sedan del-lösa. Både renderingen och ordningsreglerna bygger på den."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    grupper = exam_spec.gruppera_per_del(doc.uppgifter)
    koder = [kod for kod, _items in grupper]
    assert koder == ["B", "C"]                 # _exam() har bara B och C
    # varje grupp behåller uppgifterna i inläst ordning
    assert [it.formaga for it in grupper[0][1]] == ["B", "P"]
    # tomma delar utelämnas (ingen D-grupp)
    assert all(items for _kod, items in grupper)


def test_gruppera_per_del_lagger_dellosa_sist():
    """Uppgifter med del=None hamnar i en egen grupp sist."""
    data = _exam()
    data["uppgifter"][0]["del"] = None
    doc, _ = exam_spec.validate_exam_json(data)
    grupper = exam_spec.gruppera_per_del(doc.uppgifter)
    assert grupper[-1][0] is None
    assert len(grupper[-1][1]) == 1


def test_schema_rejects_unknown_fields_and_values():
    bad = _exam()
    bad["uppgifter"][0]["formaga"] = "X"
    doc, errors = exam_spec.validate_exam_json(bad)
    assert doc is None and any(e["code"] == "schema" for e in errors)

    bad2 = _exam()
    bad2["uppgifter"][0]["hitta_pa"] = 1
    assert exam_spec.validate_exam_json(bad2)[0] is None


def test_response_format_shape():
    rf = exam_spec.to_response_format()
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "matteprov"
    assert "uppgifter" in rf["json_schema"]["schema"]["properties"]


def test_schema_godkanner_deluppgifter():
    # Schema-acceptans; att provet BALANSERAR (errors == []) kräver den
    # rekursiva poangsummor/balansen som landar i Task 2–3
    # (test_nastlat_prov_passerar_balans).
    doc, _errors = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    assert doc is not None
    assert doc.uppgifter[6].deluppgifter is not None
    assert len(doc.uppgifter[6].deluppgifter) == 2


def test_schema_kraver_noll_poang_pa_foralder_med_deluppgifter():
    bad = _exam_med_deluppgifter()
    bad["uppgifter"][6]["poang"] = [1, 0, 0]      # förälder får inte ha poäng
    doc, errors = exam_spec.validate_exam_json(bad)
    assert doc is None and any(e["code"] == "schema" for e in errors)


def test_schema_kraver_losning_pa_lov():
    bad = _exam()
    bad["uppgifter"][0]["losning"] = ""           # löv utan lösning
    doc, errors = exam_spec.validate_exam_json(bad)
    assert doc is None and any(e["code"] == "schema" for e in errors)


def test_schema_flerval_kraver_minst_tre_alternativ_och_giltigt_index():
    bad = _exam_med_flerval()
    bad["uppgifter"][1]["alternativ"] = ["$x=1$", "$x=2$"]   # bara två
    assert exam_spec.validate_exam_json(bad)[0] is None
    bad2 = _exam_med_flerval()
    bad2["uppgifter"][1]["ratt_alternativ"] = 9              # utanför intervall
    assert exam_spec.validate_exam_json(bad2)[0] is None


def test_schema_godkanner_flerval_och_notis():
    assert exam_spec.validate_exam_json(_exam_med_flerval())[0] is not None
    assert exam_spec.validate_exam_json(_exam_med_notis())[0] is not None


def test_schema_kraver_losning_pa_deluppgift():
    """Regressionsskydd: SubItem saknade tidigare motsvarigheten till
    ExamItems _kontrollera_struktur — en deluppgift med tom lösning
    kunde smyga sig förbi schemat trots att det är just DÄR lösningarna
    hör hemma."""
    bad = _exam_med_deluppgifter()
    bad["uppgifter"][6]["deluppgifter"][0]["losning"] = ""
    assert exam_spec.validate_exam_json(bad)[0] is None


def test_schema_avvisar_ratt_alternativ_utan_alternativ():
    bad = _exam()
    bad["uppgifter"][1]["ratt_alternativ"] = 0    # utan alternativ
    assert exam_spec.validate_exam_json(bad)[0] is None


def test_schema_avvisar_nastlade_deluppgifter():
    """Deluppgifter får inte själva ha deluppgifter (en nivå djupt)."""
    bad = _exam_med_deluppgifter()
    bad["uppgifter"][6]["deluppgifter"][0]["deluppgifter"] = [
        {"poang": [0, 1, 0], "text": "x", "losning": "y", "bedomning": "z"}]
    assert exam_spec.validate_exam_json(bad)[0] is None


# -------------------------------------------------------- poängsummor --

def test_poangsummor_oforandrad_for_platt_prov():
    """Rekursionen får inte ändra summan för ett prov utan deluppgifter."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    s = exam_spec.poangsummor(doc)
    assert s["total"] == 20 and s["e"] == 9 and s["c"] == 6 and s["a"] == 5


def test_poangsummor_summerar_deluppgifter():
    """Nästlad och platt variant ger samma summa (uppg 7 = [0,3,1] i båda)."""
    platt, _ = exam_spec.validate_exam_json(_exam())
    nast, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    assert exam_spec.poangsummor(nast) == exam_spec.poangsummor(platt)


def test_poangenheter_arver_foralderns_formaga():
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    enheter = exam_spec.poangenheter(doc.uppgifter[6])
    assert len(enheter) == 2
    assert all(f == "K" for f, _t, _p in enheter)     # ärvt från föräldern
    assert all(t == "redovisning" for _f, t, _p in enheter)


def test_poangenheter_barnets_egna_formaga_vinner():
    """En deluppgift med EGEN formaga/typ bidrar med sina egna, inte
    förälderns — annars glider en regression i override-grenen igenom."""
    data = _exam_med_deluppgifter()
    data["uppgifter"][6]["deluppgifter"][0]["formaga"] = "R"
    data["uppgifter"][6]["deluppgifter"][0]["typ"] = "resonemang"
    doc, _ = exam_spec.validate_exam_json(data)
    enheter = exam_spec.poangenheter(doc.uppgifter[6])
    assert enheter[0][0] == "R" and enheter[0][1] == "resonemang"   # barnets egna
    assert enheter[1][0] == "K" and enheter[1][1] == "redovisning"  # ärvt


def test_uppg_poang_aggregerar():
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    assert exam_spec.uppg_poang(doc.uppgifter[6]) == (0, 3, 1)
    assert exam_spec.uppg_poang(doc.uppgifter[0]) == (3, 0, 0)   # löv


# ------------------------------------------------------------------ balans --

def test_all_e_points_flagged():
    bad = _exam()
    for u in bad["uppgifter"]:
        u["poang"] = [3, 0, 0]
    doc, errors = exam_spec.validate_exam_json(bad)
    assert any(e["code"] == "nivabalans" for e in errors)


def test_zero_point_item_flagged():
    bad = _exam()
    bad["uppgifter"][0]["poang"] = [0, 0, 0]
    doc, errors = exam_spec.validate_exam_json(bad)
    assert any(e["code"] == "poang" for e in errors)


def test_nastlat_prov_passerar_balans():
    """Hela det nästlade provet ska validera rent (aggregatet är oförändrat)."""
    _doc, errors = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    assert errors == []


def test_deluppgift_med_noll_poang_flaggas():
    bad = _exam_med_deluppgifter()
    bad["uppgifter"][6]["deluppgifter"][0]["poang"] = [0, 0, 0]
    _doc, errors = exam_spec.validate_exam_json(bad)
    assert any(e["code"] == "poang" for e in errors)


def test_missing_rutin_flagged():
    bad = _exam()
    for u in bad["uppgifter"]:
        u["typ"] = "redovisning"
    doc, errors = exam_spec.validate_exam_json(bad)
    assert any(e["code"] == "blandning" for e in errors)


def test_deluppgifts_egen_typ_raknas_i_blandning():
    """Typ-blandningen mäts per enhet: en deluppgifts EGEN typ (rutin)
    ska räknas även om ingen toppnivå-uppgift är rutin."""
    data = _exam_med_deluppgifter()
    for u in data["uppgifter"]:            # ta bort all rutin på toppnivå
        if u["typ"] == "rutin":
            u["typ"] = "redovisning"
    data["uppgifter"][6]["deluppgifter"][0]["typ"] = "rutin"   # enda rutin-källan
    _doc, errors = exam_spec.validate_exam_json(data)
    assert not any(e["code"] == "blandning" and "rutin" in e["message"]
                   for e in errors)
    # tas den enda rutin-källan bort ska blandning flaggas
    data["uppgifter"][6]["deluppgifter"][0]["typ"] = "redovisning"
    _doc2, errors2 = exam_spec.validate_exam_json(data)
    assert any(e["code"] == "blandning" and "rutin" in e["message"]
               for e in errors2)


def test_formaga_concentration_flagged():
    bad = _exam()
    for u in bad["uppgifter"]:
        u["formaga"] = "P"
    doc, errors = exam_spec.validate_exam_json(bad)
    assert any(e["code"] == "formagabalans" for e in errors)


def test_saknad_modellering_flaggas():
    """Med M-golvet höjt ska ett prov helt utan modellering underkännas."""
    bad = _exam()
    bad["uppgifter"][4]["formaga"] = "P"     # M-uppgiften blir procedur
    _doc, errors = exam_spec.validate_exam_json(bad)
    assert any(e["code"] == "formagabalans" and "M" in e["path"]
               for e in errors)


# --------------------------------------------------- ordning: svårighet+klump --

def test_ordning_godkanner_balanserad_fixtur():
    """Den kanoniska fixturen ska passera ordningsreglerna rent."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    assert exam_spec.validate_ordning(doc) == []


def test_svarighet_pa_aggregat():
    """En uppgifts svårighet räknas på summan av dess deluppgifter."""
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    # uppg 7 aggregat = [0,3,1] → (3 + 2)/4 = 1.25
    assert abs(exam_spec._svarighet(exam_spec.uppg_poang(doc.uppgifter[6]))
               - 1.25) < 1e-9


def test_ordning_flaggar_fallande_svarighet():
    """En del vars andra halva är klart lättare än första underkänns."""
    data = _exam()
    # Gör Del C fallande: flytta A-tyngden till de första uppgifterna.
    # Del C:s första uppgift behåller 1 E-poäng (inte [0, 0, 3]) så att den
    # separata "första uppgift saknar E-poäng"-regeln INTE också triggas —
    # annars blir testet grönt oavsett om halva-jämförelsen fungerar.
    data["uppgifter"][2]["poang"] = [1, 0, 2]   # svår men har E-poäng
    data["uppgifter"][3]["poang"] = [0, 0, 3]
    data["uppgifter"][6]["poang"] = [3, 0, 0]   # lätt sist
    doc, _ = exam_spec.validate_exam_json(data)
    assert any(e["code"] == "svarighet" for e in exam_spec.validate_ordning(doc))


def test_ordning_flaggar_forsta_uppgift_utan_e():
    """Delens första uppgift måste ha minst 1 E-poäng."""
    data = _exam()
    data["uppgifter"][2]["poang"] = [0, 2, 1]   # Del C:s första saknar E
    doc, _ = exam_spec.validate_exam_json(data)
    assert any(e["code"] == "svarighet" and "första" in e["message"]
               for e in exam_spec.validate_ordning(doc))


def test_ordning_flaggar_klumpade_typer():
    """Fler än tre uppgifter i rad med samma typ underkänns."""
    data = _exam()
    for i in (2, 3, 4, 5, 6):                     # hela Del C samma typ (5 i rad)
        data["uppgifter"][i]["typ"] = "redovisning"
    doc, _ = exam_spec.validate_exam_json(data)
    fel = exam_spec.validate_ordning(doc)
    assert any(e["code"] == "klumpning" for e in fel)


def test_antiklumpning_gransen_ar_exakt_tre():
    """Spikar tröskeln MAX_LIKA_I_RAD: exakt tre i rad tillåts, fyra
    underkänns — så en off-by-one mellan 3 och 4 fångas."""
    tre = _exam()
    for i in (2, 3, 4):                          # tre redovisning i rad i Del C
        tre["uppgifter"][i]["typ"] = "redovisning"
    tre["uppgifter"][5]["typ"] = "resonemang"
    tre["uppgifter"][6]["typ"] = "problem"       # bryter serien vid tre
    doc3, _ = exam_spec.validate_exam_json(tre)
    assert not any(e["code"] == "klumpning"
                   for e in exam_spec.validate_ordning(doc3))
    fyra = _exam()
    for i in (2, 3, 4, 5):                        # fyra redovisning i rad
        fyra["uppgifter"][i]["typ"] = "redovisning"
    fyra["uppgifter"][6]["typ"] = "problem"
    doc4, _ = exam_spec.validate_exam_json(fyra)
    assert any(e["code"] == "klumpning"
               for e in exam_spec.validate_ordning(doc4))


def test_ordning_hoppar_over_korta_delar():
    """Delar med färre än fyra uppgifter mäts inte på svårighetsordning."""
    data = _exam()
    # Del B har bara två uppgifter; gör dess första E-lös — ska INTE flaggas.
    data["uppgifter"][0]["poang"] = [0, 1, 0]
    doc, _ = exam_spec.validate_exam_json(data)
    fel = exam_spec.validate_ordning(doc)
    assert not any("Del B" in e["path"] for e in fel)


def test_ordning_undantar_arbetsblad():
    """Ordningsreglerna är en prov-kvalitet. Arbetsbladet får medvetet drilla
    samma uppgiftstyp i rad (procedurträning) — validate_balance ska inte
    flagga klumpning för arbetsbladsprofilen, men väl för provprofilen."""
    data = _exam()
    for u in data["uppgifter"]:
        u["del"] = None
        u["typ"] = "rutin"          # sju rutinuppgifter i rad
    _ab, ab_fel = exam_spec.validate_exam_json(data, "arbetsblad")
    assert not any(e["code"] == "klumpning" for e in ab_fel)
    _pv, pv_fel = exam_spec.validate_exam_json(data, "prov")
    assert any(e["code"] == "klumpning" for e in pv_fel)


def test_ordning_arbetsblad_kraver_stigande_svarighet():
    """Arbetsbladet undantas bara från antiklumpning — stigande svårighet
    gäller ÄVEN där, eftersom arbetsblad.tex.j2 lovar eleven att uppgifterna
    blir svårare längre ner (och exam_gen ber uttryckligen om det för
    arbetsblad). Bygg ett tydligt FALLANDE arbetsblad (A-tyngd först,
    E-tyngd sist, alla del=None, fyra uppgifter) och kräv att det flaggas."""
    data = {
        "titel": "Arbetsblad — fallande svårighet", "kurs": "Ma2b",
        "hjalpmedel": "Räknare",
        "uppgifter": [
            {"del": None, "formaga": "P", "typ": "rutin", "poang": [0, 0, 3],
             "text": "Svår uppgift 1.", "losning": "...", "bedomning": "..."},
            {"del": None, "formaga": "P", "typ": "rutin", "poang": [0, 1, 2],
             "text": "Svår uppgift 2.", "losning": "...", "bedomning": "..."},
            {"del": None, "formaga": "P", "typ": "rutin", "poang": [1, 1, 0],
             "text": "Lättare uppgift 3.", "losning": "...", "bedomning": "..."},
            {"del": None, "formaga": "P", "typ": "rutin", "poang": [3, 0, 0],
             "text": "Lätt uppgift 4.", "losning": "...", "bedomning": "..."},
        ],
    }
    _doc, fel = exam_spec.validate_exam_json(data, "arbetsblad")
    assert any(e["code"] == "svarighet" for e in fel)
    # antiklumpning ska fortfarande vara avstängd, trots samma typ/förmåga
    # i alla fyra uppgifterna (skulle annars också flaggat).
    assert not any(e["code"] == "klumpning" for e in fel)


# --------------------------------------------------------- genomförbarhet --

def test_genomforbarhet_kraver_en_uppgift_per_formagegolv():
    """Färre uppgifter än förmågor med positivt golv går inte att balansera."""
    fel = exam_spec.genomforbarhet(4, "prov")
    assert fel and fel[0]["code"] == "genomforbarhet"
    assert exam_spec.genomforbarhet(6, "prov") == []
    assert exam_spec.genomforbarhet(10, "prov") == []


def test_genomforbarhet_arbetsblad_ar_tillatande():
    """Arbetsbladet har inga golv > 0 utom P — korta arbetsblad är okej."""
    assert exam_spec.genomforbarhet(3, "arbetsblad") == []


# ------------------------------------------------------------- kravgränser --

def test_kravgranser_np_model():
    doc, _ = exam_spec.validate_exam_json(_exam())
    g = exam_spec.kravgranser(doc)
    assert g["total"] == 20
    assert g["E"]["minst"] == 5            # ceil(20 * 0.25)
    assert g["C"]["minst"] == 9            # ceil(20 * 0.45)
    assert g["C"]["varav_ca"] == 4         # ceil((6+5) * 0.30) = ceil(3,3)
    assert g["A"]["minst"] == 13           # ceil(20 * 0.65)
    assert g["A"]["varav_a"] == 2          # ceil(5 * 0.40)
    assert "reproducerbar" not in g["regel"]   # regeln är själva texten
    assert "25" in g["regel"] and "65" in g["regel"]


def test_kravgranser_configurable():
    doc, _ = exam_spec.validate_exam_json(_exam())
    g = exam_spec.kravgranser(doc, {"e_andel": 0.5})
    assert g["E"]["minst"] == 10


# ---------------------------------------------------------------- escaping --

def test_escape_latex_specials():
    assert exam_latex.escape_latex("50% & #1_a {b}") == \
        r"50\% \& \#1\_a \{b\}"
    assert "textbackslash" in exam_latex.escape_latex("a\\b")


def test_escape_mixed_preserves_math():
    out = exam_latex.escape_mixed("Andelen är 50% eftersom $x^2 \\ge 0$ gäller.")
    assert r"50\%" in out
    assert r"\(x^2 \ge 0\)" in out
    # kontrolltecken strippas (o-escapad backslash i JSON)
    assert "\x0c" not in exam_latex.escape_mixed("a\x0cb")


def test_escape_mixed_har_hard_space_fore_procent():
    """15,9 % ska sättas med icke-brytande space (~) så tal och tecken inte
    delas över radbrytning. Vanlig text-procent, inte matte."""
    out = exam_latex.escape_mixed("Andelen ökade med 15,9 % på ett år.")
    assert r"15,9~\%" in out
    # ingen hård space där det inte finns någon siffra före
    assert exam_latex.escape_mixed("procent %").count("~") == 0
    # ett procenttecken INUTI matte får inte röras — och samma sträng med
    # både text- och matteprocent ska bara sätta ~ i texten
    assert "~" not in exam_latex.escape_mixed(r"Sannolikheten är $4 \%$.")
    blandat = exam_latex.escape_mixed(r"50 % men $p \le 5 \%$ i modellen.")
    assert r"50~\%" in blandat and r"\(p \le 5 \%\)" in blandat


# --------------------------------------------------------- _build_view -----

def test_build_view_deluppgifter():
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    vy = exam_latex._build_view(doc)
    u7 = vy["delar"][-1]["uppgifter"][-1]        # sista uppgiften (K)
    assert u7["har_deluppgifter"] is True
    assert u7["poang_str"] == "4p"               # aggregat 0+3+1
    assert [d["bokstav"] for d in u7["deluppgifter"]] == ["a", "b"]
    assert u7["deluppgifter"][0]["poang_str"] == "2p"


def test_build_view_flerval_har_bokstaver_och_ratt():
    doc, _ = exam_spec.validate_exam_json(_exam_med_flerval())
    vy = exam_latex._build_view(doc)
    u2 = vy["delar"][0]["uppgifter"][1]
    assert [a["bokstav"] for a in u2["flerval"]] == ["A", "B", "C", "D"]
    assert u2["ratt_bokstav"] == "B"             # ratt_alternativ = 1


def test_build_view_notis():
    doc, _ = exam_spec.validate_exam_json(_exam_med_notis())
    vy = exam_latex._build_view(doc)
    assert vy["delar"][0]["uppgifter"][0]["notis"] is not None


def test_build_view_platt_oforandrad():
    """Ett löv utan struktur behåller sina fält (svarsutrymme m.m.)."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    vy = exam_latex._build_view(doc)
    u1 = vy["delar"][0]["uppgifter"][0]
    assert u1["har_deluppgifter"] is False
    assert u1["flerval"] is None and u1["notis"] is None
    assert "utrymme_mm" in u1 and "losning" in u1


def test_foralder_vy_har_hela_lovets_nyckeluppsattning():
    """En förälder med deluppgifter måste ha varje nyckel ett löv har —
    mallarna (även de befintliga) läser dem ovillkorligt per uppgift, och
    StrictUndefined kraschar på en saknad nyckel."""
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    vy = exam_latex._build_view(doc)
    lov = next(u for d in vy["delar"] for u in d["uppgifter"]
               if not u["har_deluppgifter"])
    foralder = next(u for d in vy["delar"] for u in d["uppgifter"]
                    if u["har_deluppgifter"])
    saknade = set(lov) - set(foralder)
    assert not saknade, f"föräldern saknar löv-nycklar: {saknade}"


def test_render_alla_mallar_pa_deluppgifter_utan_krasch():
    """Alla tre mallar ska rendera ett deluppgifts-prov utan StrictUndefined
    (regressionsvakt: föräldern måste ha varje nyckel mallen läser)."""
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    for render in (exam_latex.render_prov, exam_latex.render_arbetsblad,
                   exam_latex.render_bedomning):
        assert isinstance(render(doc), str)


# --------------------------------------------------------------- rendering --

def test_render_prov_golden_markers():
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_prov(doc)
    # fast preamble — modellen styr aldrig den
    # Designsystemet: 12 pt Times, 17 mm marginal (PR 1)
    assert tex.lstrip().startswith("\\documentclass[12pt,a4paper]{article}")
    assert "\\usepackage{newtxtext,newtxmath}" in tex
    assert "margin=17mm" in tex
    # amssymb MÅSTE ligga före newtxmath — omvänd ordning ger
    # "Command \openbox already defined"
    assert tex.index("amssymb") < tex.index("newtxmath")
    # bläckfärgerna ur designsystemets colors.css
    assert "\\definecolor{ink900}{HTML}{1C1B19}" in tex
    assert "\\definecolor{ink700}{HTML}{3A3835}" in tex
    assert "\\usepackage[swedish]{babel}" in tex
    # försättsblad med kravgränser och poäng
    assert "Kravgränser" in tex
    assert "minst 5 poäng" in tex and "minst 13 poäng" in tex
    # regelns %-tecken är escapade (annars kommenterar de bort resten av raden)
    assert r"25\?" not in tex
    assert r"25\% av totalpoängen" in tex
    # elevens prov visar endast totalsumman — E/C/A hör till bedömningsanvisningen
    assert "20 poäng" in tex and "(9/6/5)" not in tex
    # delar + numrerade uppgifter med poängrutor
    assert r"\delprovband{Del B}" in tex and r"\delprovband{Del C}" in tex
    # numret bärs av uppgift-miljöns hängande etikett
    assert r"\begin{uppgift}{1}" in tex and r"\begin{uppgift}{6}" in tex
    # poängen bärs nu av uppgift-miljöns andra argument (som i sin tur
    # anropar \poang-makrot internt) — endast totalpoäng i elevens prov
    assert r"\begin{uppgift}{3}{3p}" in tex and r"\begin{uppgift}{7}{4p}" in tex
    assert r"\poang{1/1/1}" not in tex and "{1/1/1}" not in tex
    # matte bevarad, rutinuppgift får svarsrad
    assert r"\(x^2 - 4x + 3 = 0\)" in tex
    assert "\\svarsrad" in tex
    # lösningar hör INTE hemma i provet
    assert "lösningsförslag" not in tex.lower()


def test_preamble_definierar_layoutmakron():
    """Designsystemets layoutprimitiver ska finnas som makron, så att
    mallarna anropar dem i stället för att upprepa formateringen."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_prov(doc)
    assert r"\newcommand{\delprovband}" in tex
    assert r"\newenvironment{uppgift}" in tex
    assert r"\newcommand{\ramruta}" in tex
    assert r"\newcommand{\elevruta}" in tex
    # måtten ur designsystemet: 10,5 mm gutter och 8,5 mm uppgiftsrytm
    assert "10.5mm" in tex and "8.5mm" in tex


def test_preamble_har_strukturmakron():
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_prov(doc)
    assert r"\newcommand{\kryssruta}" in tex
    assert r"\newcommand{\notisruta}" in tex
    assert r"\newenvironment{deluppgift}" in tex or \
           r"\newcommand{\deluppgift}" in tex


def test_prov_anvander_layoutmakron():
    """Provmallen ska anropa makrona, inte upprepa formateringen."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_prov(doc)
    # Sök i dokumentkroppen, inte i preambeln: makrodefinitionerna ligger
    # i den delade _preamble.tex.j2, så en sökning i hela strängen skulle
    # passera även om mallen slutade anropa dem.
    kropp = tex.split(r"\begin{document}", 1)[1]
    assert r"\elevruta" in kropp
    assert r"\delprovband{Del B}" in kropp and r"\delprovband{Del C}" in kropp
    assert r"\begin{uppgift}{1}{3p}" in tex
    # \section* ersatt av bandet
    assert r"\section*{Del B}" not in tex
    # oförändrat: elevens prov visar bara totalpoäng
    assert "20 poäng" in tex and "(9/6/5)" not in tex


def test_render_bedomning_contains_solutions():
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_bedomning(doc)
    assert "Bedömningsanvisning" in tex
    assert "Lösningsförslag" in tex
    assert "Problemlösning" in tex          # förmågenamn
    assert r"\(x = 1\)" in tex or "x = 1" in tex
    # lärardokumentet behåller E/C/A-poängen (elevens prov visar bara
    # totalen). Uppgiftsloopen anropar numera den delade uppgift-miljön
    # (\begin{uppgift}{n}{e/c/a}) i stället för att skriva \poang{...}
    # direkt i mallen, så \poang{1/1/1} som RÅ SUBSTRÄNG förekommer aldrig
    # i den Python-renderade .tex-källan (bara efter att LaTeX expanderat
    # miljön vid kompilering) — jfr test_prov_anvander_layoutmakron.
    assert r"\begin{uppgift}{3}{1/1/1}" in tex


def test_bedomning_behaller_eca_och_far_makron():
    """Lärarens dokument visar E/C/A — det är dess syfte. Elevens gör det inte."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_bedomning(doc)
    assert r"\begin{uppgift}{1}{3/0/0}" in tex
    assert "Lösningsförslag" in tex and "Bedömning" in tex
    # kontrollera motsatsen på elevens prov
    prov = exam_latex.render_prov(doc)
    assert "3/0/0" not in prov


def test_render_escapes_model_text():
    e = _exam()
    e["uppgifter"][0]["text"] = "Rabatten är 25% & gäller {alla}."
    doc, _ = exam_spec.validate_exam_json(e)
    tex = exam_latex.render_prov(doc)
    assert r"25\% \& g" in tex
    assert "{alla}" not in tex


def test_prov_renderar_deluppgifter_utan_facit():
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    tex = exam_latex.render_prov(doc)
    assert r"\begin{deluppgift}{a}" in tex and r"\begin{deluppgift}{b}" in tex
    # elevens prov visar aggregatet på uppgiften, aldrig E/C/A
    assert r"\begin{uppgift}{7}{4p}" in tex
    assert "0/3/1" not in tex


def test_prov_renderar_flerval_utan_ratt_svar():
    doc, _ = exam_spec.validate_exam_json(_exam_med_flerval())
    tex = exam_latex.render_prov(doc)
    assert r"\kryssruta" in tex
    # facit (rätt bokstav B) FÅR INTE finnas på elevens papper
    assert "Rätt:" not in tex and "Rätt svar" not in tex


def test_prov_renderar_notis():
    doc, _ = exam_spec.validate_exam_json(_exam_med_notis())
    tex = exam_latex.render_prov(doc)
    assert r"\notisruta{" in tex


# ------------------------------------------------------ skyddsnät: \par ----

def test_par_avslutar_poangraden_dar_markor_renderas():
    """Skyddsnät mot regressionen 2026-07-20 (668 gröna tester medan tre
    mallar ändå klistrade ihop poängmarkören med uppgiftstexten).

    \\poang använder \\hfill för att trycka markören till högermarginalen,
    men \\hfill delar bara \\parfillskip (och skjuter alltså markören ända
    till marginalen) om ett \\par avslutar stycket omedelbart efter
    \\begin{uppgift}{...}{...}-raden. Saknas det \\par:et hamnar markören
    mitt i uppgiftstexten i stället för ensam i marginalen.

    Ren strängkontroll — inget PyMuPDF eller annat nytt beroende. Kravet
    gäller bara uppgifter där en markör FAKTISKT renderas (icke-tomt andra
    argument). Arbetsbladets \\begin{uppgift}{n}{} (visa_poang=False, och
    alltid i facit-sektionen) ska INTE ha \\par där — det skulle flytta
    ned uppgiftstexten även när ingen markör visas."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    doc_del, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())

    # Både \begin{uppgift} och \begin{deluppgift} bär samma \hfill-fälla.
    rad = re.compile(r"\\begin\{(?:del)?uppgift\}\{[^{}]*\}\{([^{}]*)\}(\\par)?")

    def kontrollera(tex: str, namn: str) -> None:
        träffar = list(rad.finditer(tex))
        assert träffar, f"{namn}: hittade inga \\begin{{uppgift}}-rader"
        for m in träffar:
            markor, par = m.group(1), m.group(2)
            if markor:
                assert par == r"\par", (
                    f"{namn}: uppgift med poängmarkör {markor!r} saknar "
                    r"\par direkt efter \begin{uppgift}-raden — markören "
                    "riskerar att glida in i uppgiftstexten i stället för "
                    "att hamna ensam i högermarginalen"
                )
            else:
                assert par is None, (
                    f"{namn}: uppgift UTAN poängmarkör fick ändå ett "
                    r"\par, vilket flyttar ned uppgiftstexten i onödan"
                )

    # prov: både rutinuppgifter (med "Endast svar krävs") och
    # redovisningsuppgifter — båda bär en poängmarkör och kräver \par.
    kontrollera(exam_latex.render_prov(doc), "prov")
    # arbetsblad: visa_poang=True ska kräva \par, visa_poang=False (default,
    # och alltid i facit-sektionen) ska INTE ha det.
    kontrollera(exam_latex.render_arbetsblad(doc, visa_poang=True),
                "arbetsblad (visa_poang=True)")
    kontrollera(exam_latex.render_arbetsblad(doc, visa_poang=False),
                "arbetsblad (visa_poang=False)")
    # bedömningsanvisningen visar alltid (E/C/A) — alltid en markör.
    kontrollera(exam_latex.render_bedomning(doc), "bedomning")

    # Samma disciplin för deluppgifts-miljön — exakt den nya riskytan. Alla
    # tre mallar renderas mot deluppgifts-fixturen så att en framtida
    # deluppgift utan (eller med felplacerat) \par fångas.
    kontrollera(exam_latex.render_prov(doc_del), "prov (deluppgifter)")
    kontrollera(exam_latex.render_arbetsblad(doc_del, visa_poang=True),
                "arbetsblad deluppg (visa_poang=True)")
    kontrollera(exam_latex.render_arbetsblad(doc_del, visa_poang=False),
                "arbetsblad deluppg (visa_poang=False)")
    kontrollera(exam_latex.render_bedomning(doc_del), "bedomning (deluppgifter)")


# ------------------------------------------------------------- exam_pdf ----

def test_compile_pdf_success_with_stub(tmp_path, monkeypatch):
    monkeypatch.setattr(exam_pdf, "engine_path", lambda: tmp_path / "tectonic.exe")

    def fake_runner(cmd, **kw):
        out = tmp_path / "ut"
        (out / "prov.pdf").write_bytes(b"%PDF-1.5 fejk")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    pdf, log = exam_pdf.compile_pdf("\\documentclass{article}", tmp_path / "ut",
                                    "prov", runner=fake_runner)
    assert pdf is not None and pdf.exists()
    assert log == ""
    assert (tmp_path / "ut" / "prov.tex").exists()     # källan lämnas kvar


def test_compile_pdf_failure_writes_log(tmp_path, monkeypatch):
    monkeypatch.setattr(exam_pdf, "engine_path", lambda: tmp_path / "tectonic.exe")

    def fail_runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout="",
                                           stderr="! Undefined control sequence.")

    pdf, log = exam_pdf.compile_pdf("x", tmp_path / "ut", "prov",
                                    runner=fail_runner)
    assert pdf is None
    assert "Undefined control sequence" in log
    assert (tmp_path / "ut" / "prov.log.txt").exists()


def test_compile_pdf_engine_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(exam_pdf, "engine_path", lambda: None)
    pdf, log = exam_pdf.compile_pdf("x", tmp_path / "ut", "prov")
    assert pdf is None and "Tectonic" in log


def test_compile_pdf_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(exam_pdf, "engine_path", lambda: tmp_path / "tectonic.exe")

    def slow_runner(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)

    pdf, log = exam_pdf.compile_pdf("x", tmp_path / "ut", "prov",
                                    timeout=1, runner=slow_runner)
    assert pdf is None and "avbröts" in log


def _exam_med_matte_i_bedomningen() -> dict:
    """_exam() men med matte även i bedömningsfältet — det fältet saknar
    annars helt $…$ (se _exam() ovan). Ofarlig extra täckning: den faktiska
    orsaken till kraschen var matte i FÄLTET text i \\small-kontext (i
    bedomning.tex.j2 renderas bara uppgiftens text inuti {\\small\\itshape
    …} — losning och bedomning renderas i normal storlek, se den mallen).
    Den handskrivna sonden i tools/seed_tectonic_cache.py hade ingen matte
    i förminskad textstorlek, så \\small-matte-fontmetrikerna hämtades
    aldrig ner, och --only-cached kunde då inte hämta dem i efterhand
    (access violation i stället för ett läsbart LaTeX-fel)."""
    data = copy.deepcopy(_exam())
    data["uppgifter"][0]["bedomning"] = (
        "+2 E om båda nollställena $x=1$ och $x=-3$ anges, annars 0 p "
        "(jämför $\\alpha \\neq \\beta$).")
    return data


def test_compile_pdf_real_engine_produces_all_three_documents(tmp_path):
    """Skyddsnät mot att sonden och mallarna glider isär tyst: kompilerar
    med den RIKTIGA Tectonic-motorn (ingen stubbad runner/compile_fn) och
    kräver att prov, arbetsblad OCH bedömningsanvisning verkligen ger en
    PDF — inklusive bildvägen (\\includegraphics i prov.tex.j2/
    arbetsblad.tex.j2), som annars aldrig motioneras av de stubbade
    testerna i den här filen. Alla andra tester i den här filen stubbar
    compile_pdf — det var just därför bugginen (bedömningsanvisningens
    PDF gick inte att producera) kunde smyga sig förbi en grön testsvit."""
    if not exam_pdf.engine_available():
        pytest.skip("Tectonic-motorn saknas (bin/tectonic/tectonic.exe)")

    data = _exam_med_matte_i_bedomningen()
    data["uppgifter"][0]["bild"] = 1
    doc, errors = exam_spec.validate_exam_json(data)
    assert doc is not None and errors == []

    bild_fil = "bild-01.png"
    (tmp_path / bild_fil).write_bytes(base64.b64decode(_MINIMAL_PNG_B64))
    bilder = {1: bild_fil}

    for jobname, tex in (
        ("prov", exam_latex.render_prov(doc, bilder=bilder)),
        ("arbetsblad", exam_latex.render_arbetsblad(doc, bilder=bilder)),
        ("bedomning", exam_latex.render_bedomning(doc, bilder=bilder)),
    ):
        pdf, logg = exam_pdf.compile_pdf(tex, tmp_path, jobname)
        assert pdf is not None and pdf.exists(), f"{jobname} misslyckades: {logg}"
        assert pdf.stat().st_size > 0
        # bildvägen ska verkligen ha kompilerats, inte bara renderats i
        # minnet — bildfilens namn måste finnas i den genererade .tex-källan.
        assert bild_fil in (tmp_path / f"{jobname}.tex").read_text(encoding="utf-8")


# ------------------------------------------------------------- exam_gen ----

def _stub_llm(responses: list[str]):
    calls: list[dict] = []

    def llm(model, prompt, system=None, options=None, response_format=None,
            max_tokens=None, token_cb=None):
        calls.append({"prompt": prompt, "system": system,
                      "response_format": response_format})
        return responses[min(len(calls) - 1, len(responses) - 1)]

    return llm, calls


def test_generate_exam_valid_first_try():
    llm, calls = _stub_llm([json.dumps(_exam())])
    res = exam_gen.generate_exam("Ma2b", "SA23", ["pq-formeln"], model="m", llm=llm)
    assert res["errors"] == [] and res["rounds"] == 1
    assert res["exam"]["titel"].startswith("Prov")
    assert calls[0]["response_format"]["json_schema"]["name"] == "matteprov"
    assert "pq-formeln" in calls[0]["prompt"]


def test_generate_exam_repairs_imbalance():
    bad = _exam()
    for u in bad["uppgifter"]:
        u["poang"] = [3, 0, 0]
    llm, calls = _stub_llm([json.dumps(bad), json.dumps(_exam())])
    res = exam_gen.generate_exam("Ma2b", "SA23", [], model="m", llm=llm)
    assert res["rounds"] == 2 and res["errors"] == []
    assert "nivabalans" in calls[1]["prompt"] or "E-poängen" in calls[1]["prompt"]


def test_generate_exam_gives_up_after_budget():
    bad = _exam()
    for u in bad["uppgifter"]:
        u["poang"] = [3, 0, 0]
    llm, calls = _stub_llm([json.dumps(bad)])
    res = exam_gen.generate_exam("Ma2b", "SA23", [], model="m", llm=llm)
    assert res["rounds"] == exam_gen.MAX_ROUNDS
    assert res["errors"] and res["exam"] is not None


def test_generate_exam_avvisar_ogenomforbart_utan_llm():
    """Förkontrollen ska stoppa före modellanropet — inget LLM-anrop alls."""
    anrop = []

    def spion_llm(*a, **kw):
        anrop.append(1)
        return "{}"

    res = exam_gen.generate_exam("Ma2b", "SA23", [], model="x", antal=4,
                                 llm=spion_llm)
    assert res["exam"] is None
    assert res["errors"][0]["code"] == "genomforbarhet"
    assert anrop == []          # modellen anropades aldrig


def test_refine_exam_targets_item():
    updated = _exam()
    updated["uppgifter"][3]["text"] = "Ny optimeringsuppgift med decimaltal."
    llm, calls = _stub_llm([json.dumps(updated)])
    res = exam_gen.refine_exam(_exam(), "byt mot ett med decimaltal",
                               nummer=4, model="m", llm=llm)
    assert res["errors"] == []
    assert "uppgift 4" in calls[0]["prompt"]


def test_fix_latex_rounds_cap():
    llm, calls = _stub_llm([json.dumps(_exam())])
    res = exam_gen.fix_latex(_exam(), "! Missing $ inserted.", model="m", llm=llm)
    assert res["rounds"] == 1 and res["errors"] == []
    assert "Missing $" in calls[0]["prompt"]
    # budgeten slut → inget LLM-anrop
    res2 = exam_gen.fix_latex(_exam(), "fel", model="m", llm=llm,
                              rounds_used=exam_gen.MAX_LATEX_ROUNDS)
    assert res2["rounds"] == exam_gen.MAX_LATEX_ROUNDS
    assert any(e["code"] == "kompilering" for e in res2["errors"])
    assert len(calls) == 1


# ------------------------------------------------------ Fas 5: arbetsblad --

def _arbetsblad() -> dict:
    """E-tungt övningsblad utan redovisningsuppgifter — ok som arbetsblad,
    obalanserat som prov."""
    return {
        "titel": "Arbetsblad — pq-formeln", "kurs": "Ma2b",
        "hjalpmedel": "Räknare",
        "uppgifter": [
            {"del": None, "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Lös $x^2 - 5x + 6 = 0$.", "innehall": ["pq-formeln"],
             "losning": "$x = 2$ eller $x = 3$.", "bedomning": "+2 E."},
            {"del": None, "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Lös $x^2 + 2x - 8 = 0$.", "innehall": ["pq-formeln"],
             "losning": "$x = 2$ eller $x = -4$.", "bedomning": "+2 E."},
            {"del": None, "formaga": "B", "typ": "rutin", "poang": [1, 1, 0],
             "text": "Vad kallas talet under rottecknet i pq-formeln?",
             "innehall": ["pq-formeln"], "losning": "Diskriminantuttrycket.",
             "bedomning": "+1 E, +1 C."},
            {"del": None, "formaga": "PL", "typ": "rutin", "poang": [1, 1, 1],
             "text": "Hitta två tal med summan 7 och produkten 12.",
             "innehall": ["ekvationer"], "losning": "3 och 4.",
             "bedomning": "+1 E, +1 C, +1 A."},
        ],
    }


def test_arbetsblad_profile_accepts_worksheet_balance():
    doc, errors = exam_spec.validate_exam_json(_arbetsblad(), "arbetsblad")
    assert doc is not None and errors == []
    # samma dokument faller som PROV (saknar redovisning, för E-tungt)
    _doc2, prov_errors = exam_spec.validate_exam_json(_arbetsblad(), "prov")
    assert any(e["code"] == "blandning" for e in prov_errors)


def test_render_arbetsblad_has_facit_no_kravgranser():
    doc, _ = exam_spec.validate_exam_json(_arbetsblad(), "arbetsblad")
    tex = exam_latex.render_arbetsblad(doc)
    assert "Arbetsblad" in tex
    assert "Facit" in tex
    assert "Kravgränser" not in tex
    assert r"\(x = 2\)" in tex                    # facit = lösningarna
    # Poäng dolda som standard. Kontrollen gäller RENDERADE poäng, inte
    # makrots förekomst. Uppgiftsloopen anropar numera den delade
    # uppgift-miljön (\begin{uppgift}{n}{poäng}) i stället för att skriva
    # \poang{...} direkt i mallen — \poang{2p} som RÅ SUBSTRÄNG förekommer
    # därför aldrig i den Python-renderade .tex-källan (bara efter att
    # LaTeX expanderat miljön vid kompilering). Kontrollen görs i stället
    # mot uppgift-miljöns andra argument, precis som provmallens
    # motsvarande test (test_prov_anvander_layoutmakron).
    assert r"\begin{uppgift}{1}{2p}" not in tex
    tex_p = exam_latex.render_arbetsblad(doc, visa_poang=True)
    assert r"\begin{uppgift}{1}{2p}" in tex_p


def test_arbetsblad_anvander_layoutmakron():
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_arbetsblad(doc)
    assert r"\begin{uppgift}{1}" in tex
    # Sök i dokumentkroppen, inte i preambeln: \newcommand{\elevruta} i den
    # delade _preamble.tex.j2 innehåller alltid substrängen "\elevruta",
    # så en sökning i hela strängen skulle träffa preambeln även om
    # mallen aldrig anropade makrot (jfr test_prov_anvander_layoutmakron).
    kropp = tex.split(r"\begin{document}", 1)[1]
    assert r"\elevruta" not in kropp
    assert "Kravgränser" not in tex
    # facit finns kvar
    assert "Facit" in tex


def test_arbetsblad_utan_poang_ger_tomt_argument_inte_tom_parentes():
    """visa_poang=False ska ge INGEN poängmarkör. Skickas \\relax eller ett
    blanktecken skriver \\poang ut ett tomt parentespar i marginalen."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_arbetsblad(doc, visa_poang=False)
    assert r"\begin{uppgift}{1}{}" in tex
    # Sök i dokumentkroppen: \ramruta i preambeln innehåller alltid
    # "...\fboxsep\relax}..." (dimexpr-uttrycket), så en sökning i hela
    # strängen skulle träffa preambeln oavsett mallens innehåll.
    kropp = tex.split(r"\begin{document}", 1)[1]
    assert r"\relax}" not in kropp
    # med poäng påslaget kommer markören tillbaka
    med = exam_latex.render_arbetsblad(doc, visa_poang=True)
    assert r"\begin{uppgift}{1}{3p}" in med


def test_build_referens_numbers_and_instructs():
    ref = exam_gen.build_referens(["Lös $x^2 = 4$.", "Optimera hagen."])
    assert "1. Lös" in ref and "2. Optimera" in ref
    assert "HÖJ" in ref and "ALDRIG" in ref


def test_build_prompt_arbetsblad_profile():
    p = exam_gen.build_prompt("Ma2b", "SA23", [], profil="arbetsblad")
    assert "ARBETSBLAD" in p
    assert "del: null" in p


def test_generate_exam_respects_profile():
    llm, _ = _stub_llm([json.dumps(_arbetsblad())])
    res = exam_gen.generate_exam("Ma2b", "SA23", [], model="m", llm=llm,
                                 profil="arbetsblad")
    assert res["errors"] == [] and res["rounds"] == 1


def test_find_similar_exam_items(tmp_path):
    from app import db as appdb
    conn = appdb.connect(tmp_path / "t.db")
    cid = appdb.get_or_create_course(conn, "Ma2b")
    gammalt = appdb.create_exam(conn, exam=_exam(), course_id=cid,
                                datum="2026-09-01")
    # bara godkända prov räknas
    assert appdb.find_similar_exam_items(
        conn, cid, ["Lös ekvationen $x^2 - 4x + 3 = 0$."]) == []
    appdb.set_exam_artifacts(conn, gammalt["id"], approve=True)

    flaggor = appdb.find_similar_exam_items(
        conn, cid, ["Lös ekvationen $x^2 - 4x + 3 = 0$.",
                    "Beräkna integralen av $\\sin x$ mellan 0 och pi."])
    assert len(flaggor) == 1
    assert flaggor[0]["index"] == 0
    assert flaggor[0]["mot_exam_id"] == gammalt["id"]
    assert flaggor[0]["likhet"] >= 0.9
    # exkludering av det egna provet
    assert appdb.find_similar_exam_items(
        conn, cid, ["Lös ekvationen $x^2 - 4x + 3 = 0$."],
        exclude_exam_id=gammalt["id"]) == []


def test_prompt_includes_memory_and_themes():
    p = exam_gen.build_prompt("Ma2b", "SA23", ["pq-formeln"],
                              memory="Klassen har arbetat med kvadrering.",
                              teman="2026-09-01 — Prov 1: lös ekvationen …")
    assert "kvadrering" in p
    assert "UNDVIK" in p
    assert "egenformulerade" in exam_gen.SYSTEM


def test_prompt_har_np_rost():
    """Prompten ska bära det nationella provets register: imperativ,
    fasta fraser, förbud mot emoji och utropstecken, decimalkomma."""
    txt = exam_gen.SYSTEM + exam_gen.INSTRUCTION
    for fras in ("imperativ", "Endast svar krävs", "Motivera ditt svar",
                 "decimalkomma", "utropstecken", "emoji"):
        assert fras in txt, f"prompten nämner inte {fras!r}"
    # några av NP:s imperativa verb ska nämnas som ledord
    assert any(v in txt for v in ("Beräkna", "Bestäm", "Avgör", "Förenkla"))
