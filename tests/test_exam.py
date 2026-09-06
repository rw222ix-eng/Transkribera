"""Provgeneratorn (Fas 4): schema/balans/kravgränser, LaTeX-rendering,
PDF-modul med stubbat kompilatoranrop samt genereringslooparna."""
import base64
import copy
import json
import re
import subprocess
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app import exam_gen, exam_latex, exam_pdf, exam_spec, niva_rubrik

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
        # Porträttet på försättsbladet: utan det skickar exam_gen.forsattsignaler
        # provet till reparation, och fixturen ska vara det GILTIGA provet.
        "forsattsbild": {"person": "Muhammad al-Khwarizmi (ca 780–850), som "
                                   "gav algebran dess namn och metod.",
                         "scene": "SCENE. A scholar in a ninth-century Baghdad "
                                  "study, bent over a manuscript by lamplight, "
                                  "dust motes in a shaft of morning sun. "
                                  "Intended use: exam cover portrait."},
        "uppgifter": [
            {"del": "B", "formaga": "B", "typ": "rutin", "poang": [3, 0, 0],
             "text": "Ange nollställena till $f(x) = (x-1)(x+3)$.",
             "innehall": ["nollställen"],
             "losning": "$x = 1$ och $x = -3$.",
             # Bedömningen är en TRAPPA: en rad per poäng med sin nivå, som i
             # nationella provets anvisningar (exam_spec.bedomningsrader).
             # Fixturen är den kanoniskt giltiga och måste hålla också den
             # formen — exam_gen.bedomningssignaler räknar raderna mot poängen.
             "bedomning": "+1 E anger det ena nollstället\n"
                          "+1 E anger det andra nollstället\n"
                          "+1 E korrekt svar med båda nollställena",
             },
            {"del": "B", "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Lös ekvationen $x^2 - 4x + 3 = 0$.",
             "innehall": ["pq-formeln"],
             "losning": "$x = 1$ eller $x = 3$.",
             "bedomning": "+1 E en korrekt rot\n+1 E båda rötterna korrekta"},
            {"del": "C", "formaga": "P", "typ": "redovisning", "poang": [1, 1, 1],
             "text": "Lös ekvationen $x^2 + 6x - 7 = 0$ med kvadratkomplettering.",
             "innehall": ["kvadratkomplettering"],
             "losning": "$(x+3)^2 = 16$ ger $x = 1$ eller $x = -7$.",
             "bedomning": "+1 E ansats\n+1 C korrekt kvadratkomplettering\n"
                          "+1 A generell metod"},
            {"del": "C", "formaga": "PL", "typ": "problem", "poang": [1, 1, 1],
             "text": "En rektangulär hage har omkretsen 60 m. Bestäm de mått "
                     "som maximerar arean.",
             "innehall": ["optimering", "andragradsfunktioner"],
             "losning": "Kvadrat $15 \\times 15$ m ger max.",
             "bedomning": "+1 E tecknar arean\n+1 C löser ut måtten\n"
                          "+1 A motiverat maximum"},
            {"del": "C", "formaga": "M", "typ": "problem", "poang": [1, 0, 1],
             "text": "En population beskrivs av $N(t) = 200 \\cdot 1{,}05^t$. "
                     "Bestäm när populationen har fördubblats.",
             "innehall": ["exponentiell modell"],
             "losning": "$1{,}05^t = 2$ ger $t \\approx 14{,}2$ år.",
             "bedomning": "+1 E tecknar ekvationen\n"
                          "+1 A korrekt tolkning av modellen"},
            {"del": "C", "formaga": "R", "typ": "resonemang", "poang": [1, 1, 1],
             "text": "Avgör om påståendet stämmer: en andragradsfunktion med "
                     "$a < 0$ saknar minsta värde. Motivera.",
             "innehall": ["andragradsfunktioner"],
             "losning": "Sant — grafen är en nedåtriktad parabel.",
             "bedomning": "+1 E ställningstagande\n+1 C motivering\n"
                          "+1 A stringent resonemang"},
            {"del": "C", "formaga": "K", "typ": "redovisning", "poang": [0, 3, 1],
             "text": "Förklara med graf och ord hur symmetrilinjen bestäms "
                     "för $f(x) = x^2 - 6x + 5$.",
             "innehall": ["symmetrilinje"],
             "losning": "$x = 3$ via $-b/(2a)$ eller nollställenas mittpunkt.",
             "bedomning": "+1 C anger symmetrilinjen\n+1 C förklarar metoden\n"
                          "+1 C tydlig förklaring i ord\n+1 A flera representationer"},
        ],
    }


def _trappa(poang) -> str:
    """Bedömningstrappan för en poängtrippel: en rad per poäng, i ordning
    E→C→A — nationella provets form (exam_spec.bedomningsrader)."""
    return "\n".join(f"+1 {niva} steg {i + 1}"
                     for niva, antal in zip("ECA", poang)
                     for i in range(antal))


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
             "bedomning": "+1 C korrekt linje\n+1 C redovisad metod"},
            {"poang": [0, 1, 1],
             "text": "Förklara med graf och ord varför den ligger där.",
             "losning": "Mittpunkt mellan nollställena; grafen är symmetrisk.",
             "bedomning": "+1 C förklaring\n+1 A flera representationer"},
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
        "bedomning": "+1 E rätt alternativ (B)\n+1 E motiverat val"}
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


def test_schema_avvisar_for_manga_alternativ():
    """_VERSAL/_BOKSTAV i exam_latex har bara 12 bokstäver (A–L). 13
    flervalsalternativ är annars schema-giltigt men kraschar renderingen
    med IndexError — gränsen ska stoppa det som ett rent valideringsfel."""
    bad = _exam_med_flerval()
    bad["uppgifter"][1]["alternativ"] = [f"${'x'}={i}$" for i in range(13)]
    bad["uppgifter"][1]["ratt_alternativ"] = 0
    assert exam_spec.validate_exam_json(bad)[0] is None


def test_schema_avvisar_for_manga_deluppgifter():
    """Samma _BOKSTAV-gräns (12 bokstäver) gäller deluppgifter."""
    bad = _exam_med_deluppgifter()
    lov = bad["uppgifter"][6]["deluppgifter"][0]
    bad["uppgifter"][6]["deluppgifter"] = [
        {**lov, "poang": [0, 1, 0]} for _ in range(13)]
    assert exam_spec.validate_exam_json(bad)[0] is None


def _exam_med_figur(figur: dict) -> dict:
    """_exam() med en figur på uppgift 3 (poäng/förmåga oförändrade)."""
    data = _exam()
    data["uppgifter"][2]["figur"] = figur
    return data


def test_schema_godkanner_alla_figurtyper():
    figurer = [
        {"typ": "linjar", "k": 0.8, "m": 1},
        {"typ": "andragrad", "a": 1, "b": -4, "c": 3},
        {"typ": "exponential", "C": 1, "bas": 2},
        {"typ": "normalfordelning", "mu": 0, "sigma": 1},
        {"typ": "triangel", "a": 5, "b": 4, "c": 3},
        {"typ": "enhetscirkel", "vinkel": 40},
        {"typ": "stapeldiagram", "kategorier": ["A", "B", "C"], "varden": [3, 5, 2]},
        {"typ": "ladagram", "min": 2, "q1": 5, "median": 8, "q3": 11, "max": 14},
    ]
    for f in figurer:
        doc, _ = exam_spec.validate_exam_json(_exam_med_figur(f))
        assert doc is not None, f"{f['typ']} avvisades"
        assert doc.uppgifter[2].figur.typ == f["typ"]


def test_schema_lasersparametrar_per_figurtyp():
    """Diskriminerad union: linjär kräver k/m, inte a — grammatiktvånget
    speglar detta."""
    bad = _exam_med_figur({"typ": "linjar", "a": 1, "b": 2, "c": 3})
    assert exam_spec.validate_exam_json(bad)[0] is None


def test_schema_figur_och_bild_utesluter_varandra():
    data = _exam_med_figur({"typ": "linjar", "k": 1, "m": 0})
    data["uppgifter"][2]["bild"] = 1
    assert exam_spec.validate_exam_json(data)[0] is None


@pytest.mark.parametrize("figur", [
    {"typ": "triangel", "a": 1, "b": 1, "c": 5},          # bryter triangelolikheten
    {"typ": "ladagram", "min": 2, "q1": 8, "median": 5,   # icke-stigande
     "q3": 11, "max": 14},
    {"typ": "stapeldiagram", "kategorier": ["A", "B", "C"],
     "varden": [3, 5]},                                    # olika längd
    {"typ": "exponential", "C": 1, "bas": 0},              # bas måste vara > 0
    {"typ": "normalfordelning", "mu": 0, "sigma": 0},      # sigma måste vara > 0
])
def test_schema_avvisar_ogiltiga_figurparametrar(figur):
    """Figurmodellernas egna validatorer (triangelolikhet, stigande lådagram,
    lika-långa serier, bas>0, sigma>0) ska avvisa ogiltiga parametrar."""
    assert exam_spec.validate_exam_json(_exam_med_figur(figur))[0] is None


def test_response_format_har_figur_diskriminator():
    import json
    rf = exam_spec.to_response_format()
    assert "discriminator" in json.dumps(rf["json_schema"]["schema"])


def test_to_response_format_kapar_antal_uppgifter():
    """Med antal satt tvingar grammatiken exakt så många toppuppgifter
    (min=max) — llama.cpp hedrar min/maxItems, så modellen kan inte
    överproducera. Utan antal finns ingen övre gräns."""
    upp = exam_spec.to_response_format(6)["json_schema"]["schema"] \
        ["properties"]["uppgifter"]
    assert upp["maxItems"] == 6 and upp["minItems"] == 6
    upp0 = exam_spec.to_response_format()["json_schema"]["schema"] \
        ["properties"]["uppgifter"]
    assert "maxItems" not in upp0


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

def test_genomforbarhet_kraver_plats_for_bada_uppgiftstyperna():
    """Regeln var «färre uppgifter än förmågor med positivt golv går inte att
    balansera». Den föll när alla sex förmågor fick golv (Del D1): då hade ett
    arbetsblad på tre uppgifter blivit ogenomförbart. Täckningsregeln tog över
    den frågan (och gör den bättre, på ENHETER). Kvar är det som fortfarande är
    omöjligt: ett prov måste rymma både en rutinuppgift och en med fullständig
    lösning."""
    fel = exam_spec.genomforbarhet(1, "prov")
    assert fel and fel[0]["code"] == "genomforbarhet"
    for antal in (2, 4, 6, 10):
        assert exam_spec.genomforbarhet(antal, "prov") == []


def test_genomforbarhet_arbetsblad_ar_tillatande():
    """Arbetsbladet kräver ingen redovisningsuppgift — ett papper räcker."""
    assert exam_spec.genomforbarhet(1, "arbetsblad") == []
    assert exam_spec.genomforbarhet(3, "arbetsblad") == []


def test_smafallsregeln_kraver_en_formaga_per_uppgift():
    """Under sex FÖRMÅGEBÄRARE kan det jämna bandet inte gälla — då kräver
    täckningsregeln i stället att varje bärare bär sin egen förmåga."""
    # Nivåerna hålls innanför arbetsbladets band (E 40–85 %) så att det ENDA
    # som kan fälla bladet är förmågetäckningen.
    def blad(formagor):
        poang = [[2, 0, 0], [1, 1, 0], [0, 1, 0]]
        return {"titel": "x", "kurs": "Ma2b", "hjalpmedel": "x", "uppgifter": [
            {"del": None, "formaga": f, "typ": "rutin", "poang": poang[i],
             "text": f"Uppgift {i + 1}.", "losning": "L.", "bedomning": "B."}
            for i, f in enumerate(formagor)]}

    _d, fel = exam_spec.validate_exam_json(blad(["P", "P", "P"]), "arbetsblad")
    assert [e["code"] for e in fel] == ["formagabalans"]
    assert "3 uppgifter täcker bara 1 förmågor" in fel[0]["message"]
    _d, rent = exam_spec.validate_exam_json(blad(["P", "B", "M"]), "arbetsblad")
    assert rent == []
    # Deluppgifter som deklarerar EGEN förmåga är egna bärare: två uppgifter
    # kan bära fyra förmågor, och då mäts täckningen mot fyra. (En deluppgift
    # som ÄRVER förälderns förmåga är däremot ingen ny bärare — se
    # test_arvande_deluppgifter_hojer_inte_kravet nedan.)
    med_del = {"titel": "x", "kurs": "Ma2b", "hjalpmedel": "x", "uppgifter": [
        {"del": None, "formaga": "P", "typ": "rutin", "poang": [0, 0, 0],
         "text": "Stam.", "deluppgifter": [
             {"formaga": f, "poang": p, "text": f"del {f}",
              "losning": "L.", "bedomning": "B."}
             for f, p in (("P", [2, 0, 0]), ("B", [1, 0, 0]))]},
        {"del": None, "formaga": "M", "typ": "rutin", "poang": [0, 0, 0],
         "text": "Stam.", "deluppgifter": [
             {"formaga": f, "poang": p, "text": f"del {f}",
              "losning": "L.", "bedomning": "B."}
             for f, p in (("M", [1, 1, 0]), ("R", [0, 1, 0]))]},
    ]}
    _d, fel4 = exam_spec.validate_exam_json(med_del, "arbetsblad")
    assert fel4 == []


# ------------------------------------------------------------- kravgränser --

def test_kravgranser_np_model():
    doc, _ = exam_spec.validate_exam_json(_exam())
    g = exam_spec.kravgranser(doc)
    assert g["total"] == 20
    assert g["E"]["minst"] == 6            # ceil(20 * 0.26)
    assert g["C"]["minst"] == 11           # ceil(20 * 0.54)
    assert g["C"]["varav_ca"] == 4         # ceil((6+5) * 0.34) = ceil(3,74)
    assert g["A"]["minst"] == 16           # ceil(20 * 0.79)
    assert g["A"]["varav_a"] == 3          # ceil(5 * 0.50)
    assert "reproducerbar" not in g["regel"]   # regeln är själva texten
    assert "26" in g["regel"] and "79" in g["regel"]
    # Papprets betygstabell har fyra rader (F/E/C/A) — mellanbetygen räknas
    # bara på begäran och får aldrig smyga sig in i regeltexten.
    assert "D:" not in g["regel"] and "B:" not in g["regel"]
    assert "D" not in g and "B" not in g


# ── Kalibreringen mot nationella provet ──────────────────────────────────────
# NpMa2a vt2017 och vt2022, gränserna på provets sida 1. Båda 55 poäng. Testet
# är hela skälet till att KRAV_DEFAULT har de tal den har: ändrar någon en
# procentsats faller det här och inte elevens betyg ett halvår senare.
#
# ±1 poäng är golvet och inte slarv: E var 14 p vt17 och 15 p vt22 på samma
# totalpoäng, alltså kan ingen fast procentsats träffa båda åren exakt.

_NP = {
    #        summor {total,e,c,a}                     facit: E, D(+varav), C(+varav), B(+varav), A(+varav)
    "vt17": ({"total": 55, "e": 23, "c": 19, "a": 13},
             {"E": 14, "D": (22, 6), "C": (29, 11), "B": (37, 4), "A": (43, 6)}),
    "vt22": ({"total": 55, "e": 23, "c": 20, "a": 12},
             {"E": 15, "D": (23, 6), "C": (30, 11), "B": (38, 4), "A": (44, 7)}),
}


@pytest.mark.parametrize("ar", ["vt17", "vt22"])
def test_np_kalibrering_traffar_riktiga_provets_granser(ar):
    summor, facit = _NP[ar]
    g = exam_spec.kravgranser_ur_summor(summor, {"mellanbetyg": True})
    assert abs(g["E"]["minst"] - facit["E"]) <= 1
    for b, (minst, varav) in ((k, v) for k, v in facit.items() if k != "E"):
        falt = "varav_a" if b in ("A", "B") else "varav_ca"
        assert abs(g[b]["minst"] - minst) <= 1, f"{ar} {b} total"
        assert abs(g[b][falt] - varav) <= 1, f"{ar} {b} varav"


def test_np_kalibrering_varav_kraven_ar_exakta():
    """C:s varav-krav är 11 av 32 C+A-poäng båda åren, D:s 6 och B:s 4 — där
    finns inget spann att missa, och där är gränsen alltså exakt NP:s."""
    for ar in ("vt17", "vt22"):
        summor, facit = _NP[ar]
        g = exam_spec.kravgranser_ur_summor(summor, {"mellanbetyg": True})
        assert g["C"]["varav_ca"] == facit["C"][1]
        assert g["D"]["varav_ca"] == facit["D"][1]
        assert g["B"]["varav_a"] == facit["B"][1]


def test_np_kalibrering_ligger_aldrig_under_np():
    """PRINCIPEN, och den är hela kalibreringens dom: 0 ≤ appens gräns − NP:s
    gräns ≤ 1, för varje gräns och båda årgångarna.

    En gräns UNDER NP:s delar ut ett betyg NP inte hade gett — det får inte
    hända på ett papper som säger «NP-modellen». Ett snäpp ÖVER är strängare än
    NP och går att försvara. Faller det här testet är det inte talen som ska
    justeras förrän någon förklarat vilken elev som ska förlora på det."""
    for ar in ("vt17", "vt22"):
        summor, facit = _NP[ar]
        g = exam_spec.kravgranser_ur_summor(summor, {"mellanbetyg": True})
        krav = [("E", "minst", facit["E"])]
        for b in ("D", "C", "B", "A"):
            falt = "varav_a" if b in ("A", "B") else "varav_ca"
            krav += [(b, "minst", facit[b][0]), (b, falt, facit[b][1])]
        for b, falt, np in krav:
            assert 0 <= g[b][falt] - np <= 1, f"{ar} {b}.{falt}: {g[b][falt]} mot NP:s {np}"


# ── Provet bär sina egna gränser ─────────────────────────────────────────────

def test_pappret_trycks_med_sina_sparade_granser(monkeypatch):
    """Ett godkänt prov bär `granser` i JSON:en, och DE talen står i TeX:en —
    även efter att KRAV_DEFAULT ändrats.

    Utan fältet räknades gränserna om vid varje tryck: ett prov från i maj hade
    tryckts om i juni med juni-regelns siffror, och PDF:en i högen hade sagt
    något annat än pappret klassen skrev."""
    rad = _exam()
    rad["granser"] = {"total": 20, "E": {"minst": 5},
                      "C": {"minst": 9, "varav_ca": 4},
                      "A": {"minst": 13, "varav_a": 2},
                      "regel": "Regeln som gällde i maj."}
    doc, fel = exam_spec.validate_exam_json(rad)
    assert fel == [] and doc is not None
    # Regeln görs om helt under fötterna på pappret.
    monkeypatch.setitem(exam_spec.KRAV_DEFAULT, "e_andel", 0.90)
    monkeypatch.setitem(exam_spec.KRAV_DEFAULT, "c_andel", 0.95)
    assert exam_spec.kravgranser(doc)["E"]["minst"] == 5      # inte 18
    tex = exam_latex.render_prov(doc)
    # Betygstabellens spann byggs ur gränserna: F 0–4, E 5–8, C 9–12, A 13–20.
    # Med dagens regel hade E-raden börjat på 6 och C på 11.
    for spann in (r"0\textendash{}4", r"5\textendash{}8",
                  r"9\textendash{}12", r"13\textendash{}20"):
        assert spann in tex, spann
    # Bedömningsanvisningen läser samma gränser och ska säga samma sak.
    bed = exam_latex.render_bedomning(doc)
    assert "E minst 5" in bed and "C minst 9 varav 4 C/A" in bed
    assert "A minst 13 varav 2 A" in bed


def test_papper_utan_sparade_granser_raknas_ur_dagens_regel():
    """Gamla dokument — skrivna före stämpeln — har inget fält. Då gäller
    KRAV_DEFAULT, och det är allt appen kan veta."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    assert doc.granser is None
    assert exam_spec.kravgranser(doc) ==         exam_spec.kravgranser_ur_summor(exam_spec.poangsummor(doc))


def test_papprets_egna_granser_gar_fore_nar_dokumentet_bar_dem():
    """Mellansteget: dokumentet i basen bär `granser` (plan.js sätter dem) men
    prov-JSON:en gör det inte. Papprets tal gäller ändå."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    papper = {"granser": {"total": 20, "E": {"minst": 5},
                          "C": {"minst": 9, "varav_ca": 4},
                          "A": {"minst": 13, "varav_a": 2},
                          "regel": "Papprets regel."}}
    assert exam_spec.kravgranser(doc, papper=papper)["C"]["minst"] == 9


def test_granser_for_en_annan_poangsumma_raknas_om():
    """Uppgifterna går att redigera efter stämpeln. Gränser för 55 poäng säger
    ingenting om ett prov som ger 20 — då är raden skräp, inte ett löfte."""
    rad = _exam()
    rad["granser"] = {"total": 55, "E": {"minst": 15},
                      "C": {"minst": 30, "varav_ca": 11},
                      "A": {"minst": 44, "varav_a": 7}, "regel": "Annat papper."}
    doc, _ = exam_spec.validate_exam_json(rad)
    g = exam_spec.kravgranser(doc)
    assert g["total"] == 20 and g["E"]["minst"] == 6


def test_granserna_star_inte_i_grammatiken():
    """Ser modellen fältet fyller den i det — och då hade den skrivit en
    betygstabell den hittat på, rakt på försättsbladet. Samma regel som
    `klockslag` och `scen.plat`."""
    schema = exam_spec.to_response_format()["json_schema"]["schema"]
    assert "granser" not in schema["properties"]
    assert "klockslag" not in schema["properties"]


def test_kravgranser_configurable():
    doc, _ = exam_spec.validate_exam_json(_exam())
    g = exam_spec.kravgranser(doc, {"e_andel": 0.5})
    assert g["E"]["minst"] == 10


# ---------------------------------------------------------------- escaping --

def test_escape_latex_specials():
    assert exam_latex.escape_latex("50% & #1_a {b}") == \
        r"50\% \& \#1\_a \{b\}"
    assert "textbackslash" in exam_latex.escape_latex("a\\b")


def test_escape_latex_escapar_dubbelfnutt():
    """Svensk babel gör " till en aktiv genväg i huvuddokumentet (ingen
    \\shorthandoff där). Escapa " så ett citattecken i text/kategorinamn
    renderas bokstavligt i stället för att tolkas som babel-genväg."""
    assert exam_latex.escape_latex('säger "hej"') == \
        r"säger \textquotedbl{}hej\textquotedbl{}"


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

def test_hjalpmedelsraden_oversatts_till_papprets_delnamn():
    """Modellen skriver regeln med de interna namnen (prompten säger Del B/
    Del C) — pappret räknar från A, så försättsbladets rad översätts. Kedjan
    B→A, C→B är ordnad: ett redan översatt «Del A» rörs inte igen."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_prov(doc)
    assert "Del A utan räknare. Del B med räknare och formelblad." in tex
    assert "Del C" not in tex


def test_hjalpmedelsraden_oversatts_bara_en_gang():
    """Regression: kedjan B→A, C→B, D→C skjuter varje namn ett steg neråt, så
    en text som REDAN bär papprets namn översattes en gång till och två delar
    smälte ihop. Vägen in är verklig: läraren pekar på provtabellen,
    granskningen skickar skärmtexten, modellen svarar med det den såg — och
    försättsbladet fick «Del A utan räknare. Del A med räknare.»"""
    papprets = "Del A utan räknare. Del B med räknare och formelblad."
    assert exam_latex._delnamn_visning(papprets) == papprets
    # Idempotens, inte bara en specialfall: f(f(x)) == f(x) för det interna.
    internt = "Del B utan räknare. Del C med räknare och formelblad."
    en_gang = exam_latex._delnamn_visning(internt)
    assert en_gang == papprets
    assert exam_latex._delnamn_visning(en_gang) == papprets
    # Trepartsprovet också: B/C/D → A/B/C, och sedan stilla.
    tre = exam_latex._delnamn_visning("Del B, del C och Del D.")
    assert tre == "Del A, del B och Del C."
    assert exam_latex._delnamn_visning(tre) == tre
    # Hela vägen ut på pappret: dokumentet bär redan papprets namn.
    doc, _ = exam_spec.validate_exam_json(_exam() | {"hjalpmedel": papprets})
    tex = exam_latex.render_prov(doc)
    assert papprets in tex


def test_blad_bygg_speglar_delnamnsoversattningen():
    """Skärmen och PDF:en måste säga samma sak om samma prov — glider
    speglarna isär står «Del A» på skärmen och «Del A/Del A» i PDF:en. Vakten
    mot att bara den ena sidan får idempotensfixen."""
    js = (Path(__file__).resolve().parent.parent / "app" / "web" / "ui"
          / "blad-bygg.js").read_text(encoding="utf-8")
    assert "DELNAMN_REDAN" in js, "blad-bygg.js saknar redan-översatt-vakten"
    assert "DELNAMN_REDAN.test(s) ? s :" in js


def test_forhandsvisningen_ger_deluppgiften_svarsrad_och_figur():
    """Samma vakt, nya former. Pappret sätter \\svarsrad{Svar:} under VARJE
    kortsvarsdeluppgift (förlagans uppgift 1) och ritar deluppgiftens egen
    figur där frågan står — skärmen gjorde varken det ena eller det andra:
    `behoverRad` stänger av uppgiftens svarsrad så fort det finns
    deluppgifter, och deluppgifterna hade ingen. Förhandsvisningen lovade
    alltså ett papper utan svarsplats."""
    ui = Path(__file__).resolve().parent.parent / "app" / "web" / "ui"
    js = (ui / "blad-bygg.js").read_text(encoding="utf-8")
    plan = (ui / "plan.js").read_text(encoding="utf-8")
    css = (ui / "prov.css").read_text(encoding="utf-8")
    assert "delsvar" in js and "delfigur" in js
    # Raden bara på kortsvaren — det som redovisas på lösblad ska inte ha en
    # linje som inbjuder till motsatsen.
    assert "u.ut === 'kort'" in js
    # Figuren måste FÖLJA MED från prov-JSON:en, annars finns inget att rita.
    assert "ut.delfig" in plan and "ut.delbild" in plan
    # …och den får inte hamna i poängspalten: raden är ett rutnät med tre
    # spalter, och varje nytt barn tar nästa ruta.
    assert ".prdel[data-avdelad]>li>.prsvar" in css
    assert "grid-column:2/-1" in css


def test_render_prov_golden_markers():
    """PROVET ÄR LÄRARENS EGEN FÖRLAGA. Hon lämnade in LaTeX-källan till sitt
    Overleaf-prov (Ma 2c, kapitel 2, NA25) och sa «typ exakt så här vill jag
    att mina prov ska se ut». Markörerna nedan är hennes recept, rad för rad —
    ändras något av dem ser pappret inte längre ut som hennes."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_prov(doc)
    # exam-klassen med addpoints — och INTE newtx: förlagan är Computer Modern
    assert tex.lstrip().startswith("\\documentclass[12pt, a4paper, addpoints]{exam}")
    assert "newtxtext" not in tex
    assert "top=25mm, bottom=25mm, left=25mm, right=25mm" in tex
    assert "\\usepackage{booktabs}" in tex
    assert "\\usepackage[swedish]{babel}" in tex
    # poängen i högermarginalen, formaterade «2 p» och utan ordet «poäng»
    assert "\\pointsinrightmargin" in tex
    assert "\\pointformat{\\thepoints~p}" in tex
    assert "\\pointname{}" in tex
    # SIDHUVUDET: bara delen, i högra hörnet, med linje under. Vänstra
    # fältet bar provets namn på varje blad fram till 2026-09-06, då
    # läraren strök det: «Att ha denna typ av text på varje provblad är
    # onödigt. Det krävs bara på försättsidan. Däremot kan del A och del B
    # i högra hörnet vara kvar.»
    assert "\\pagestyle{headandfoot}" in tex
    assert "\\runningheader{}{}{\\rightmark}" in tex
    assert "\\runningheadrule" in tex
    assert "\\firstpageheader{}{}{}" in tex
    # … och provrubriken står i INGET runningheader.
    for rad in tex.splitlines():
        if rad.startswith("\\runningheader"):
            assert rad == "\\runningheader{}{}{\\rightmark}", rad
    # försättsbladets ordning
    assert "Provtid:" in tex and "Hjälpmedel:" in tex
    # Lärarens provrutin: båda delarna delas ut samtidigt, räknaren hämtas
    # först när Del A är inlämnad (2026-08-22).
    assert ("Du lämnar in Del A innan du tar fram digitala verktyg och "
            "börjar på Del B." in tex)
    assert "Provet kan ge totalt \\textbf{20 poäng}" in tex
    assert "Instruktioner" in tex and "Poängen för varje uppgift anges" in tex
    assert "\\textbf{Namn:} \\hrulefill" in tex
    # elevens prov visar endast totalsumman — E/C/A hör till bedömningen
    assert "(9/6/5)" not in tex and "3/0/0" not in tex
    # delrubrikerna räknar från A (lärarens beslut 2026-08-20)
    assert (r"Del A \textendash{} Digitala verktyg är inte tillåtna"
            in tex)
    assert r"Del B \textendash{} Digitala verktyg är tillåtna" in tex
    # uppgifterna i exam-klassens questions/parts, med kravetiketten i kursiv
    assert "\\begin{questions}" in tex and "\\setcounter{question}{0}" in tex
    assert "\\question[3] \\pfkrav{Endast svar krävs.}" in tex
    assert "\\question[4] \\pfkrav{Fullständig lösning krävs.}" in tex
    # matte bevarad, kortsvarsuppgiften får förlagans svarslinje
    assert r"\(x^2 - 4x + 3 = 0\)" in tex
    assert "\\svarsrad{Svar:}" in tex
    # lösningar hör INTE hemma i provet
    assert "lösningsförslag" not in tex.lower()


def test_preamble_definierar_layoutmakron():
    """Designsystemets layoutprimitiver ska finnas som makron, så att
    mallarna anropar dem i stället för att upprepa formateringen.

    Mätt på ARBETSBLADET och inte på provet: provet lämnade designsystemet när
    lärarens förlaga blev mall (exam-klassen, egna mått), medan arbetsbladet,
    gruppuppgiften har kvar sin egen form."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_arbetsblad(doc)
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


def test_preamble_laddar_tikz_villkorligt():
    """med_tikz styr om tikz + angles/quotes-biblioteket laddas — flaggan
    är villkorlig precis som med_grafik/med_svarsrad."""
    from app import exam_latex
    tex_med = exam_latex._environment().get_template(
        "_preamble.tex.j2").render(sidhuvud="x", med_grafik=False,
                                   med_svarsrad=False, med_tikz=True)
    assert r"\usepackage{tikz}" in tex_med
    assert r"\usetikzlibrary{angles,quotes}" in tex_med
    # svensk babel gör " till ett aktivt genvägstecken som krockar med tikz
    # quotes-biblioteket (\pic["$v$"]); shorthandoff släcker det. Måste ligga
    # kvar — annars kraschar figur-kompileringen tyst.
    assert r'\AtBeginDocument{\shorthandoff{"}}' in tex_med
    tex_utan = exam_latex._environment().get_template(
        "_preamble.tex.j2").render(sidhuvud="x", med_grafik=False,
                                   med_svarsrad=False, med_tikz=False)
    assert r"\usepackage{tikz}" not in tex_utan
    assert r"\shorthandoff" not in tex_utan     # bara när tikz laddas


def test_build_view_figur_tex():
    """_build_view lägger rå TikZ (ur exam_figures.render_figur) i vyns
    figur_tex — INTE escapad, till skillnad från text/losning/bedomning."""
    data = _exam()
    data["uppgifter"][2]["figur"] = {"typ": "andragrad", "a": 1, "b": -4, "c": 3}
    doc, _ = exam_spec.validate_exam_json(data)
    vy = exam_latex._build_view(doc)
    u3 = vy["delar"][1]["uppgifter"][0]     # första Del C-uppgiften
    assert u3["figur_tex"] is not None
    assert r"\begin{tikzpicture}" in u3["figur_tex"]
    # löv utan figur → None
    assert vy["delar"][0]["uppgifter"][0]["figur_tex"] is None


def test_prov_renderar_figuren():
    data = _exam()
    data["uppgifter"][2]["figur"] = {"typ": "linjar", "k": 1, "m": 0}
    doc, _ = exam_spec.validate_exam_json(data)
    tex = exam_latex.render_prov(doc)
    assert r"\begin{tikzpicture}" in tex
    assert r"\usetikzlibrary{angles,quotes}" in tex   # med_tikz slogs på


def test_prov_utan_figur_laddar_tikz_men_inte_pgfplots():
    """Provet laddar numera ALLTID tikz: vändmärket i sidfoten ritar sin pil
    med det (lärarens begäran 2026-08-22, se _preamble.tex.j2 VÄNDMÄRKET).

    Det som fortfarande hänger på figurerna är det DYRA — pgfplots är buntens
    tyngsta paket, och biblioteken angles/quotes behövs bara av figurreceptens
    vinkelbågar. Ett prov utan figurer ska inte betala för dem, och bara det
    provet slipper babels genvägsavstängning."""
    tex = exam_latex.render_prov(exam_spec.validate_exam_json(_exam())[0])
    assert r"\usepackage{tikz}" in tex
    assert r"\usepackage{pgfplots}" not in tex
    assert r"\usetikzlibrary" not in tex
    assert r"\shorthandoff" not in tex
    # Bedömningsanvisningen (samma preamble, inget vändmärke) laddar det inte.
    bed = exam_latex.render_bedomning(exam_spec.validate_exam_json(_exam())[0])
    assert r"\usepackage{tikz}" not in bed


def test_prov_anvander_layoutmakron():
    """Provmallen ska anropa makrona, inte upprepa formateringen.

    Makrona är numera förlagans: \\pfkrav för kravetiketten, \\svarsrad för
    svarslinjen och exam-klassens egna question/parts. Designsystemets band och
    elevruta hör till de andra pappren."""
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_prov(doc)
    # Sök i dokumentkroppen, inte i preambeln: makrodefinitionerna ligger
    # i den delade _preamble.tex.j2, så en sökning i hela strängen skulle
    # passera även om mallen slutade anropa dem.
    kropp = tex.split(r"\begin{document}", 1)[1]
    assert r"\pfkrav{" in kropp
    assert r"\svarsrad{" in kropp
    assert r"\begin{questions}" in kropp and r"\question" in kropp
    # designsystemets grepp ska INTE stå på provet längre
    assert r"\elevruta" not in kropp
    assert r"\delprovband" not in kropp
    assert r"\section*{Del A}" not in tex and r"\section*{Del B}" not in tex
    # oförändrat: elevens prov visar bara totalpoäng
    assert "20 poäng" in tex and "(9/6/5)" not in tex


def test_render_bedomning_contains_solutions():
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_bedomning(doc)
    assert "Bedömningsanvisning" in tex
    # Facit står i bedömningstabellens översta rad (\bedrad), inte längre
    # under rubriken «Lösningsförslag:» — pappret heter numera hela vägen
    # Bedömningsanvisning.
    assert r"\bedrad{Facit {\normalfont\textperiodcentered} full pott}" in tex
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
    assert r"\bedrad{Facit" in tex and r"\bedsteg{" in tex
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
    """Deluppgifterna sätts av exam-klassens parts, som i förlagan: «(a)»,
    «(b)» och poängen på DELUPPGIFTEN. Uppgiften själv bär ingen poäng då —
    en summa i marginalen bredvid numret hade bara varit ett tredje tal."""
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    tex = exam_latex.render_prov(doc)
    assert r"\begin{parts}" in tex and r"\end{parts}" in tex
    assert r"\part[" in tex
    # föräldern får INGEN poängmarkör
    assert r"\question \pfkrav{" in tex
    # elevens prov visar aldrig E/C/A
    assert "0/3/1" not in tex


def test_prov_renderar_flerval_utan_ratt_svar():
    doc, _ = exam_spec.validate_exam_json(_exam_med_flerval())
    tex = exam_latex.render_prov(doc)
    assert r"\kryssruta" in tex
    # facit (rätt bokstav B) FÅR INTE finnas på elevens papper
    assert "Rätt:" not in tex and "Rätt svar" not in tex


def test_prov_renderar_notis():
    """På PROVET är notisen förlagans kursiva ledtråd, inte en inramad ruta:
    «Tips: Gör en skiss och kalla bredden för $x$ cm.» En låda mitt i en
    uppgift läser som ett villkor, kursiven som en hjälpande hand."""
    doc, _ = exam_spec.validate_exam_json(_exam_med_notis())
    tex = exam_latex.render_prov(doc)
    assert r"\pftips{" in tex
    assert r"\notisruta{" not in tex.split(r"\begin{document}", 1)[1]


def test_deluppgifts_notis_renderas_i_prov_och_arbetsblad():
    """Regressionsskydd: _enhet_vy beräknar d.notis för varje deluppgift,
    men INGEN mall renderade den (tyst dataförlust — en modellskriven
    notis på en deluppgift försvann från både elevens papper och facit).
    Bedömningsanvisningen ska INTE ha notisrutan (notis är en
    elevinstruktion, inte en bedömningsanvisning) — se den separata
    kontrollen mot render_bedomning."""
    data = _exam_med_deluppgifter()
    data["uppgifter"][6]["deluppgifter"][0]["notis"] = "Tänk på tecknet."
    doc, errors = exam_spec.validate_exam_json(data)
    assert doc is not None and errors == []

    prov = exam_latex.render_prov(doc)
    arbetsblad = exam_latex.render_arbetsblad(doc)
    bedomning = exam_latex.render_bedomning(doc)
    # Provet sätter den som förlagans kursiva ledtråd, arbetsbladet som sin
    # egen inramade ruta — samma fält, två papper, två former.
    assert r"\pftips{Tänk på tecknet.}" in prov
    assert r"\notisruta{Tänk på tecknet.}" in arbetsblad
    # bedömningsanvisningen ska inte innehålla notisrutan
    assert r"\notisruta{Tänk på tecknet.}" not in bedomning


def test_bedomning_visar_deluppgifternas_facit():
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    tex = exam_latex.render_bedomning(doc)
    assert r"\begin{deluppgift}{a}{0/2/0}" in tex   # per-deluppgift E/C/A
    assert "symmetrilinjens ekvation" in tex        # deluppgiftstext
    # Varje deluppgift som bär poäng får sin EGEN facitrad med sin egen trappa
    # bredvid (lärarens beställning 2026-08-23).
    assert r"\bedrad{Facit a) {\normalfont\textperiodcentered} full pott}" in tex
    assert r"\bedrad{Facit b) {\normalfont\textperiodcentered} full pott}" in tex


def test_bedomning_visar_flervalsfacit():
    doc, _ = exam_spec.validate_exam_json(_exam_med_flerval())
    tex = exam_latex.render_bedomning(doc)
    assert "Rätt: B" in tex                          # facit hör hemma HÄR


def test_arbetsblad_facit_har_deluppgifternas_losningar():
    doc, _ = exam_spec.validate_exam_json(_exam_med_deluppgifter())
    tex = exam_latex.render_arbetsblad(doc)
    assert r"\begin{deluppgift}{a}" in tex           # struktur på övningssidan
    assert "Facit" in tex


def test_arbetsbladets_instruktionsband_ar_dokumentets():
    """Skärmen och pappret får inte lova olika saker: skriver läraren om
    instruktionsrutan i granskningen (exam_spec.instruktion) ska HENNES text
    stå på arket, inte mallens rad. Facit-löftet står kvar i båda fallen — det
    är papprets besked om var lösningarna hamnar, inte en arbetsregel."""
    data = _exam()
    data["instruktion"] = "Arbeta i par. Skriv svaret på svarsraden."
    doc, fel = exam_spec.validate_exam_json(data)
    assert doc is not None, fel
    tex = exam_latex.render_arbetsblad(doc)
    assert "Arbeta i par." in tex
    assert "Öva i egen takt" not in tex
    assert "Facit finns" in tex
    # Tomt fält → raden som förut, för alla papper som skrevs innan fältet fanns.
    utan, _ = exam_spec.validate_exam_json(_exam())
    assert "Öva i egen takt" in exam_latex.render_arbetsblad(utan)


def test_omskrivningen_haller_ihop_uppgift_och_facit_at_bada_hall():
    """Lärarens ord: «Om jag ändrar något i facit så ska uppgiften också
    ändras … enklare, mindre tal, och svaret ska bli ett heltal.» Hon pekar på
    facitposten och beskriver SVARET — men det är uppgiftens tal som bestämmer
    svaret, och ett facit som räknar på andra tal än uppgiften är värre än
    inget."""
    p = exam_gen.build_refine_prompt({"titel": "Prov", "uppgifter": []},
                                     "gör talen mindre så svaret blir ett heltal")
    assert "facit får aldrig beskriva en tidigare version" in p   # uppgift→facit
    assert "BÅDA håll" in p                                       # facit→uppgift
    assert "text och TAL ändras" in p


def test_omskrivningen_kraver_en_uppgift_som_gar_att_rakna_pa():
    """Lärarens gruppuppgift 2026-08-26: hon markerade uppgift 2 och skrev att
    uppgiften var otydlig och att det inte gick att räkna på den. Varvet skrev
    om uppgiftens a) och lämnade b) — «Markera den första rad som är fel» —
    ordagrant kvar. Den sortens dom är ett krav på FULLSTÄNDIGHET, inte en
    beställning på putsat språk, och prompten måste säga det."""
    p = exam_gen.build_refine_prompt(
        {"titel": "Gruppuppgift", "uppgifter": []},
        "uppgiften är otydlig, det går inte att räkna på den", nummer=2)
    assert "gå att LÖSA av det som står i den" in p
    assert "stegtabell, tabell, figur, alternativ" in p
    assert "komplett och beräkningsbar" in p


def test_lararens_mening_star_sist_i_omskrivningen():
    """Önskemålet stod bara mitt i prompten, före ett halvt sidlångt block med
    allmänna regler — och det är blockets ord modellen har i handen när den
    börjar skriva. Meningen står nu också SIST, närmast svaret."""
    p = exam_gen.build_refine_prompt(
        {"titel": "Prov", "uppgifter": []}, "ta bort deluppgift b)", nummer=4)
    svans = p.rstrip()[-300:]
    assert "ta bort deluppgift b)" in svans
    assert "väger tyngst" in svans
    assert svans.endswith("Svara med enbart JSON.")
    # Den står KVAR på sin gamla plats också: målraden och uppgiftsnumret hör
    # ihop med den, och en mening som bara står sist tappar sitt «gäller
    # uppgift 4».
    assert "Lärarens önskemål gäller uppgift 4: ta bort deluppgift b)" in p


def test_malslaset_galler_gruppuppgiften_ocksa():
    """Gruppuppgiften går genom /api/exams/{id}/refine som provet, och `uppg2`
    ska låsa omskrivningen till uppgift 2 där lika väl. Utan låset skriver
    modellen om hela pappret och «förbättrar» de uppgifter läraren var nöjd
    med."""
    assert exam_gen.riktat_mal(2, {"el": "uppg2", "namn": "Uppgift 2"}) \
        == ("uppgift", 2)
    original = {"titel": "Gruppuppgift",
                "uppgifter": [{"text": "ett"}, {"text": "två"}, {"text": "tre"}]}
    kandidat = {"titel": "Ett annat namn",
                "uppgifter": [{"text": "PETAD"}, {"text": "två, fullständig"},
                              {"text": "PETAD"}]}
    ihop, skal = exam_gen.sammanfoga_riktat(original, kandidat, ("uppgift", 2))
    assert skal == ""
    assert ihop["uppgifter"] == [{"text": "ett"}, {"text": "två, fullständig"},
                                 {"text": "tre"}]
    assert ihop["titel"] == "Gruppuppgift"


def test_bedomning_platt_oforandrad():
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_bedomning(doc)
    assert r"\begin{uppgift}{1}{3/0/0}" in tex       # löv oförändrat


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

    # PROVET MÄTS INTE HÄR LÄNGRE. Det sätts sedan lärarens förlaga blev mall
    # av exam-klassen, som placerar poängen med \pointsinrightmargin i stället
    # för med \hfill — \hfill-fällan finns alltså inte där, och det finns inga
    # \begin{uppgift}-rader att mäta. Bedömningsanvisningen använder däremot
    # kvar miljön och mäts nedan.
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


@pytest.mark.tectonic
def test_compile_pdf_real_engine_produces_all_three_documents(tmp_path):
    """Skyddsnät mot att sonden och mallarna glider isär tyst: kompilerar
    med den RIKTIGA Tectonic-motorn (ingen stubbad runner/compile_fn) och
    kräver att prov, arbetsblad OCH bedömningsanvisning verkligen ger en
    PDF — inklusive bildvägen (\\includegraphics i prov.tex.j2/
    arbetsblad.tex.j2), som annars aldrig motioneras av de stubbade
    testerna i den här filen. Alla andra tester i den här filen stubbar
    compile_pdf — det var just därför bugginen (bedömningsanvisningens
    PDF gick inte att producera) kunde smyga sig förbi en grön testsvit."""

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


@pytest.mark.tectonic
def test_compile_pdf_real_engine_bedomning_med_djupt_nastlad_matte(tmp_path):
    """Fältet text renderas som {\\small\\itshape …} i bedomning.tex.j2.
    Matte som nästlar ner i script- och scriptscript-storlek hämtar då
    symbolfonten och matte-kursiven i 7 pt och 5 pt (ntxsy7/ntxsy5/ntxmi5).
    Cachen hade bara metrikfilerna (.tfm) för dem — aldrig de virtuella
    fonterna — eftersom sonden aldrig SATT en glyf i de storlekarna: TeX
    laddar en .tfm enbart för mattens fontdimensioner, medan xdvipdfmx
    behöver .vf först när en glyf faktiskt sätts. Med --only-cached (aktivt
    så fort .seeded finns) kraschade Tectonic på skarpa prov med
    'Could not locate a virtual/physical font for TFM "ntxsy7"' medan provet
    kompilerade felfritt.

    Testet täcker även FAMILJ 3 (newtxmaths utökningsfamilj, ntxexx/ntxexa),
    som är en egen matematisk familj och alltså inte täcks av storleksstegen
    ovan: \\sum och \\int är familj 3 direkt, och en extensibel parentes
    (\\left(...\\right)) samt en stor \\sqrt över ett bråk når familj 3 genom
    delimiter- respektive rottecknets charlist. Summor och integraler är
    vanliga i riktiga Ma3/Ma4-prov, så luckan var minst lika angelägen som
    ntxsy7-kraschen."""

    data = copy.deepcopy(_exam())
    # \cdot i en exponent → symbolglyf i script-storlek (ntxsy7).
    # \frac i en exponent → täljare/nämnare i scriptscript (ntxmi5/ntxsy5).
    # \sum/\int → familj 3 (ntxexx) direkt. \left(...\right) och en stor
    # \sqrt över ett bråk → familj 3 via delimiter-/rotteckningens charlist.
    data["uppgifter"][0]["text"] = (
        "Förenkla $x^{a \\cdot \\sqrt{b}}$ och bestäm sedan "
        "$y^{\\frac{c \\cdot d}{e}}$ då $b = 4$. Beräkna även "
        "$\\sum_{i=1}^{n} i^2$ och $\\int_0^1 f(x)\\,dx$ samt förenkla "
        "$\\left(\\frac{n(n+1)}{2}\\right)$ och $\\sqrt{\\frac{x}{2}}$.")
    doc, errors = exam_spec.validate_exam_json(data)
    assert doc is not None and errors == []

    pdf, logg = exam_pdf.compile_pdf(
        exam_latex.render_bedomning(doc), tmp_path, "bedomning")
    assert pdf is not None and pdf.exists(), f"bedömningen misslyckades: {logg}"
    assert pdf.stat().st_size > 0


@pytest.mark.tectonic
def test_compile_pdf_real_engine_compiles_deluppgifter_och_flerval(tmp_path):
    """Skyddsnät mot att en STRUKTURSPECIFIK kompileringsregression aldrig
    blir röd: test_compile_pdf_real_engine_produces_all_three_documents
    ovan kompilerar bara det PLATTA provet — all deluppgifts-/flerval-/
    notis-rendering testas annars bara som strängar mot en stubbad
    compile_pdf. Kompilerar BÅDE ett deluppgifts-prov (med en notis på en
    deluppgift, se Fynd 1) och ett flervalsprov genom alla tre mallarna
    med den RIKTIGA Tectonic-motorn."""

    del_data = _exam_med_deluppgifter()
    del_data["uppgifter"][6]["deluppgifter"][0]["notis"] = "Tänk på tecknet."
    doc_del, errors_del = exam_spec.validate_exam_json(del_data)
    assert doc_del is not None and errors_del == []

    doc_flerval, errors_flerval = exam_spec.validate_exam_json(
        _exam_med_flerval())
    assert doc_flerval is not None and errors_flerval == []

    for namn, doc in (("deluppgifter", doc_del), ("flerval", doc_flerval)):
        for jobname, tex in (
            ("prov", exam_latex.render_prov(doc)),
            ("arbetsblad", exam_latex.render_arbetsblad(doc)),
            ("bedomning", exam_latex.render_bedomning(doc)),
        ):
            ut = tmp_path / namn
            pdf, logg = exam_pdf.compile_pdf(tex, ut, jobname)
            assert pdf is not None and pdf.exists(), (
                f"{namn}/{jobname} misslyckades: {logg}")
            assert pdf.stat().st_size > 0


@pytest.mark.tectonic
def test_compile_pdf_real_engine_figur_pa_foralder_med_deluppgifter(tmp_path):
    """Figuren ligger på uppgiftsnivå; en FÖRÄLDER med deluppgifter kan alltså
    bära figur_tex. Just den kombinationen är StrictUndefined-risken — kompilera
    den genom alla tre mallar med riktiga motorn (inte bara stubbad)."""
    data = _exam_med_deluppgifter()
    data["uppgifter"][6]["figur"] = {"typ": "andragrad", "a": 1, "b": -4, "c": 3}
    doc, errors = exam_spec.validate_exam_json(data)
    assert doc is not None and errors == []
    for jobname, tex in (("prov", exam_latex.render_prov(doc)),
                         ("arbetsblad", exam_latex.render_arbetsblad(doc)),
                         ("bedomning", exam_latex.render_bedomning(doc))):
        # figuren måste faktiskt landa i .tex:en (inte bara "kompilerar utan
        # StrictUndefined") — annars kunde en förälder tappa figuren tyst
        assert r"\begin{tikzpicture}" in tex, f"{jobname}: figuren saknas i .tex:en"
        pdf, logg = exam_pdf.compile_pdf(tex, tmp_path / jobname, jobname)
        assert pdf is not None and pdf.exists(), f"{jobname}: {logg}"


# ------------------------------------------------------------- exam_gen ----

def _stub_llm(responses: list[str]):
    calls: list[dict] = []

    def llm(model, prompt, system=None, options=None, response_format=None,
            max_tokens=None, token_cb=None):
        calls.append({"prompt": prompt, "system": system,
                      "response_format": response_format})
        return responses[min(len(calls) - 1, len(responses) - 1)]

    return llm, calls


def _stub_strommande_llm(responses: list[str], *, bit: int = 7):
    """Som _stub_llm, men matar svaret i småbitar till `token_cb` först — så
    som claude_code gör med strömmen från CLI:t. Bitstorleken är med flit
    obekväm: nycklar och klamrar KAPAS mitt itu, och räknaren måste tåla det."""
    calls: list[dict] = []

    def llm(model, prompt, system=None, options=None, response_format=None,
            max_tokens=None, token_cb=None):
        svar = responses[min(len(calls), len(responses) - 1)]
        calls.append({"prompt": prompt})
        for i in range(0, len(svar), bit):
            if token_cb:
                token_cb(svar[i:i + bit])
        return svar

    return llm, calls


def test_stromraknaren_ger_en_rad_per_uppgift():
    """«Skriver uppgift 4 av 12 …» ur strömmen — en rad per uppgift, i ordning.

    Utan detta stod «Claude skriver provet» stilla i sju till tio minuter."""
    exam = _exam()
    n = len(exam["uppgifter"])
    llm, _ = _stub_strommande_llm([json.dumps(exam, ensure_ascii=False)])
    rader: list[str] = []
    exam_gen.generate_exam("Ma2b", "SA23", ["pq-formeln"], antal=n, model="m",
                           llm=llm, doma=False, log_cb=rader.append)
    skrivna = [r for r in rader if r.startswith("Skriver uppgift ")]
    assert skrivna == [f"Skriver uppgift {i} av {n} …" for i in range(1, n + 1)]


def test_stromraknaren_dubbelraknar_inte_deluppgifter():
    """Deluppgifterna är inte uppgifter. En uppgift med två delar bär tre
    `"poang"` och fyra `"text"` — därför räknas klamrar på arrayens egen nivå
    och inte nycklar."""
    exam = _exam_med_deluppgifter()
    text = json.dumps(exam, ensure_ascii=False)
    rader: list[str] = []
    raknare = exam_gen._Uppgiftsraknare(None, rader.append, "Skriver")
    for i in range(0, len(text), 5):
        raknare(text[i:i + 5])
    assert raknare.skrivna == len(exam["uppgifter"])
    assert rader[-1] == f"Skriver uppgift {len(exam['uppgifter'])} …"


def test_stromraknaren_luras_inte_av_klamrar_i_latex():
    """`\\frac{1}{2}` i en uppgiftstext är inga uppgifter — strängarna hoppas
    över, flykttecknen med."""
    rader: list[str] = []
    raknare = exam_gen._Uppgiftsraknare(2, rader.append, "Skriver")
    raknare('{"titel": "x", "uppgifter": [{"text": "$\\\\frac{1}{2}$ och \\" {"},')
    raknare('{"text": "sista"}]}')
    assert raknare.skrivna == 2
    assert rader == ["Skriver uppgift 1 av 2 …", "Skriver uppgift 2 av 2 …"]


def test_reparationsrundan_sager_vilken_runda_den_ar_pa():
    """Reparationen är ett eget varv och ska säga det — annars ser läraren
    «Skriver uppgift 3 av 8» två gånger och tror att den hakat upp sig."""
    trasigt = _exam()
    trasigt["uppgifter"][0]["poang"] = [0, 0, 0]      # faller på valideringen
    llm, _ = _stub_strommande_llm([json.dumps(trasigt, ensure_ascii=False),
                                   json.dumps(_exam(), ensure_ascii=False)])
    rader: list[str] = []
    exam_gen.generate_exam("Ma2b", "SA23", ["pq-formeln"], model="m", llm=llm,
                           doma=False, log_cb=rader.append)
    assert any(r.startswith("Justerar provet (runda 2 av ") and "uppgift 1" in r
               for r in rader), rader


def test_generate_exam_valid_first_try():
    llm, calls = _stub_llm([json.dumps(_exam())])
    res = exam_gen.generate_exam("Ma2b", "SA23", ["pq-formeln"], model="m", llm=llm)
    assert res["errors"] == [] and res["rounds"] == 1
    assert res["exam"]["titel"].startswith("Prov")
    assert calls[0]["response_format"]["json_schema"]["name"] == "matteprov"
    assert "pq-formeln" in calls[0]["prompt"]


def test_generate_exam_trar_antal_till_grammatiken():
    """generate_exam(antal=N) ska sätta grammatik-taket (maxItems=N) i det
    response_format som skickas till modellen — inte bara i prompten."""
    llm, calls = _stub_llm([json.dumps(_exam())])
    exam_gen.generate_exam("Ma2b", "SA23", [], model="m", antal=6, llm=llm)
    upp = calls[0]["response_format"]["json_schema"]["schema"] \
        ["properties"]["uppgifter"]
    assert upp["maxItems"] == 6


def test_validate_variation_flaggar_upprepade():
    """Två toppuppgifter med (nästan) identisk frågeformulering ska flaggas —
    modellen upprepar annars samma frågetyp (skarp körning)."""
    data = _exam()
    data["uppgifter"][1]["text"] = data["uppgifter"][0]["text"]  # exakt dubblett
    doc, _ = exam_spec.validate_exam_json(data, "prov")
    errs = exam_spec.validate_variation(doc)
    assert any(e["code"] == "variation" for e in errs)


def test_validate_variation_slapper_distinkta():
    """Den kanoniska (distinkta) fixturen ska INTE flaggas."""
    doc, _ = exam_spec.validate_exam_json(_exam(), "prov")
    assert exam_spec.validate_variation(doc) == []


def test_generate_flode_undantar_arbetsblad_fran_variation():
    """Variationskontrollen körs bara på PROV — arbetsbladet får drilla samma
    frågetyp i rad, precis som antiklumpningen."""
    dup = _exam()
    dup["uppgifter"][1]["text"] = dup["uppgifter"][0]["text"]
    _d1, errs_prov = exam_gen._validate(dup, "prov")
    _d2, errs_ab = exam_gen._validate(dup, "arbetsblad")
    assert any(e["code"] == "variation" for e in errs_prov)
    assert not any(e["code"] == "variation" for e in errs_ab)


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

    res = exam_gen.generate_exam("Ma2b", "SA23", [], model="x", antal=1,
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


def test_refine_exam_bar_elementet_som_inte_ar_en_uppgift():
    """Läraren pekar också på sidhuvudet, instruktionen och namnraderna — de har
    inget uppgiftsnummer, och utan elementet gick önskemålet ut som «gör den
    kortare» utan att säga vad «den» var. Bär önskemålet ett nummer är numret
    precisare och elementet tigs om."""
    llm, calls = _stub_llm([json.dumps(_exam()), json.dumps(_exam())])
    exam_gen.refine_exam(_exam(), "skriv om den", model="m", llm=llm,
                         mal={"namn": "Instruktionen",
                              "innehall": "Miniräknare får användas på del B."})
    assert "PEKADE PÅ «Instruktionen»" in calls[0]["prompt"]
    assert "Miniräknare får användas" in calls[0]["prompt"]
    exam_gen.refine_exam(_exam(), "gör den svårare", model="m", llm=llm,
                         nummer=4, mal={"namn": "Uppgift 4", "innehall": "…"})
    assert "uppgift 4" in calls[1]["prompt"]
    assert "PEKADE PÅ" not in calls[1]["prompt"]


# ── Riktad omskrivning: servern håller promptens löfte ─────────────────────
#
# Skarpa fallet: läraren pekade på uppgift D och bad «ta bort deluppgift b)».
# Modellen skrev om alla fyra uppgifterna och bytte sammanhanget (bygg → pizza)
# trots promptens «Övriga uppgifter lämnas oförändrade». Hon fick ångra allt.
# Sviten nedan låser att SERVERN håller löftet, inte prompten.

def _skriv_om_allt(**topp) -> dict:
    """Kandidaten som modellen «råkade» svara med: varje uppgift utbytt mot ett
    annat sammanhang, och toppfälten med."""
    d = _exam()
    for i, u in enumerate(d["uppgifter"], start=1):
        u["text"] = f"På pizzerian säljs {i} pizzor. Beräkna intäkten."
        u["losning"] = f"Svaret är {i}."
        u["bedomning"] = "Rätt svar ger poängen."
    d.update({"titel": "Prov — Pizzor", "instruktion": "Arbeta i par.",
              "hjalpmedel": "Inga hjälpmedel.", "tid_min": 60})
    d.update(topp)
    return d


def test_riktad_omskrivning_ror_bara_maluppgiften():
    """Kandidatens uppgift N skrivs in i originalet; övriga uppgifter tas
    ORDAGRANT ur originalet, hur mycket modellen än skrev om dem."""
    llm, _calls = _stub_llm([json.dumps(_skriv_om_allt())])
    fore = _exam()
    res = exam_gen.refine_exam(fore, "ta bort deluppgift b)", nummer=4,
                               model="m", llm=llm)
    assert res["errors"] == []
    efter = res["exam"]
    assert efter["uppgifter"][3]["text"].startswith("På pizzerian")
    for i, u in enumerate(fore["uppgifter"]):
        if i != 3:
            assert efter["uppgifter"][i] == u, f"uppgift {i + 1} rördes"
    # Toppfälten hör inte till en uppgift och står kvar.
    assert efter["titel"] == fore["titel"]
    assert efter["hjalpmedel"] == fore["hjalpmedel"]


def test_riktat_falt_ror_inte_uppgifterna():
    """Pekar läraren på instruktionsbandet är det bandet som ändras — inte
    uppgifterna, inte hjälpmedelsregeln (den är provtabellens fält)."""
    llm, _calls = _stub_llm([json.dumps(
        _skriv_om_allt(instruktion="Läs tillsammans först.",
                       nyckelfraga="Var sitter den okända?"))])
    fore = _exam()
    res = exam_gen.refine_exam(fore, "skriv om den", model="m", llm=llm,
                               mal={"el": "instr", "namn": "Instruktionen"})
    efter = res["exam"]
    assert efter["instruktion"] == "Läs tillsammans först."
    assert efter["nyckelfraga"] == "Var sitter den okända?"
    assert efter["uppgifter"] == fore["uppgifter"]
    assert efter["titel"] == fore["titel"]
    assert efter["hjalpmedel"] == fore["hjalpmedel"]
    assert efter["tid_min"] == fore["tid_min"]


def test_riktad_rubrik_byter_bara_titeln():
    """Sidhuvudet visar kurs, klass och datum också — men de är lärarens val,
    inte modellens, och ett önskemål om rubriken får inte döpa om klassen."""
    llm, _calls = _stub_llm([json.dumps(
        _skriv_om_allt(titel="Prov — Pizzor", klass="XX99", datum="2026-01-01"))])
    fore = _exam()
    res = exam_gen.refine_exam(fore, "kortare rubrik", model="m", llm=llm,
                               mal={"el": "rubrik", "namn": "Sidhuvudet"})
    assert res["exam"]["titel"] == "Prov — Pizzor"
    assert res["exam"]["klass"] == fore["klass"]
    assert res["exam"]["datum"] == fore["datum"]
    assert res["exam"]["uppgifter"] == fore["uppgifter"]


def test_utan_mal_ar_hela_dokumentet_spelplanen():
    """«Gör hela provet lättare» ska få röra allt — och då VET läraren det."""
    kandidat = _skriv_om_allt()
    llm, _calls = _stub_llm([json.dumps(kandidat)])
    res = exam_gen.refine_exam(_exam(), "gör hela provet lättare",
                               model="m", llm=llm)
    assert res["exam"]["uppgifter"] == kandidat["uppgifter"]
    assert res["exam"]["titel"] == "Prov — Pizzor"


def test_omalat_element_ar_ocksa_hela_dokumentet():
    """Betygsgränserna räknas ur poängen och går bara att flytta genom att
    uppgifterna ändras — de avgränsar alltså inget fält."""
    kandidat = _skriv_om_allt()
    llm, _calls = _stub_llm([json.dumps(kandidat)])
    res = exam_gen.refine_exam(_exam(), "höj gränsen för C", model="m", llm=llm,
                               mal={"el": "avtal1", "namn": "Betygsgränserna"})
    assert res["exam"]["uppgifter"] == kandidat["uppgifter"]


def test_reparationsrundan_far_ocksa_bara_rora_malet():
    """Rättningsrundan är också en omskrivning av hela dokumentet. Utan samma
    grind smiter det förbjudna in i runda två — den runda läraren aldrig ser."""
    trasig = _skriv_om_allt()
    trasig["uppgifter"][3]["poang"] = [99, 0, 0]        # spräcker balansen
    llm, calls = _stub_llm([json.dumps(trasig),
                            json.dumps(_skriv_om_allt())])
    fore = _exam()
    res = exam_gen.refine_exam(fore, "gör den svårare", nummer=4,
                               model="m", llm=llm)
    # Två rundor + bedömningspassets ENA anrop: bara uppgift 4 ändrades, och
    # de övriga bär redan sina elevexempel (exam_gen.andrade_uppgifter).
    assert len(calls) == 3, "reparationsrundan kördes inte"
    assert sum("bedömningsskrivare" in c["prompt"] for c in calls) == 1
    assert res["errors"] == []
    for i, u in enumerate(fore["uppgifter"]):
        if i != 3:
            assert res["exam"]["uppgifter"][i] == u, f"uppgift {i + 1} rördes"


def test_malet_som_inte_gar_igenom_ger_originalet_tillbaka():
    """Går målets ändring inte att validera ens efter reparation lämnas
    ORIGINALET tillbaka med felen kvar. Ett halvt genomfört önskemål på ett
    papper läraren tror är helt upptäcks först framför klassen."""
    trasig = _skriv_om_allt()
    trasig["uppgifter"][3]["poang"] = [99, 0, 0]
    llm, _calls = _stub_llm([json.dumps(trasig)])
    fore = _exam()
    res = exam_gen.refine_exam(fore, "gör den svårare", nummer=4,
                               model="m", llm=llm)
    assert res["errors"], "felen ska redovisas"
    assert res["exam"] == fore


def test_svar_utan_maluppgiften_ror_ingenting():
    """Bär svaret ingen uppgift 4 finns målet inte i det — och då är originalet
    svaret, med skälet skrivet."""
    kort = _exam()
    kort["uppgifter"] = kort["uppgifter"][:2]
    llm, _calls = _stub_llm([json.dumps(kort)])
    fore = _exam()
    res = exam_gen.refine_exam(fore, "gör den svårare", nummer=4,
                               model="m", llm=llm)
    assert res["exam"] == fore
    assert res["errors"][0]["code"] == "mal"
    assert "uppgift 4" in res["errors"][0]["message"]


# ── Flera mål i samma önskemål ──────────────────────────────────────────────
# Läraren markerar uppgift 4 OCH uppgift 6 i canvasen och skriver en mening för
# båda. Grinden är densamma som för ett mål, men spelplanen är unionen: allt
# hon pekade på får ändras, och ingenting annat.

def _skriv_om_allt_med_tva_sammanhang() -> dict:
    """Som _skriv_om_allt, men uppgift 6 får ett EGET sammanhang: tas två av
    pizzauppgifterna in på samma papper är de för lika varandra, och det är
    variationsvakten som svarar — inte målgrinden vi mäter här."""
    d = _skriv_om_allt()
    d["uppgifter"][5]["text"] = ("Ett tåg kör i 80 km/h. Hur långt hinner det "
                                 "på 45 minuter?")
    d["uppgifter"][5]["losning"] = "$80 \\cdot 0{,}75 = 60$ km."
    return d


def test_flera_mal_slapper_igenom_alla_de_markerade_uppgifterna():
    llm, _calls = _stub_llm([json.dumps(_skriv_om_allt_med_tva_sammanhang())])
    fore = _exam()
    res = exam_gen.refine_exam(
        fore, "gör dem kortare", nummer=[4, 6], model="m", llm=llm,
        malen=[{"el": "uppg4", "namn": "Uppgift 4"},
               {"el": "uppg6", "namn": "Uppgift 6"}])
    assert res["errors"] == []
    efter = res["exam"]
    assert efter["uppgifter"][3]["text"].startswith("På pizzerian")
    assert efter["uppgifter"][5]["text"].startswith("Ett tåg")
    for i, u in enumerate(fore["uppgifter"]):
        if i not in (3, 5):
            assert efter["uppgifter"][i] == u, f"uppgift {i + 1} rördes"
    assert efter["titel"] == fore["titel"]


def test_flera_mal_kan_blanda_uppgift_och_falt():
    """Rubriken och en uppgift på en gång: båda ändras, resten står kvar.
    Numret ensamt hade dolt rubriken (den vägen släpper ingen målrad igenom),
    och rubriken ensam hade dolt uppgiften."""
    llm, _calls = _stub_llm([json.dumps(_skriv_om_allt(titel="Prov — Pizzor",
                                                       klass="XX99"))])
    fore = _exam()
    res = exam_gen.refine_exam(
        fore, "byt sammanhang", nummer=4, model="m", llm=llm,
        malen=[{"el": "uppg4", "namn": "Uppgift 4"},
               {"el": "rubrik", "namn": "Sidhuvudet"}])
    efter = res["exam"]
    assert efter["titel"] == "Prov — Pizzor"
    assert efter["klass"] == fore["klass"], "klassen är lärarens, inte modellens"
    assert efter["uppgifter"][3]["text"].startswith("På pizzerian")
    assert efter["uppgifter"][0] == fore["uppgifter"][0]


def test_ett_okant_mal_bland_flera_gor_hela_dokumentet_till_spelplan():
    """Betygsgränserna avgränsar inget fält. Att låsa till de mål vi RÅKAR
    känna igen hade tyst tappat bort den delen av önskemålet."""
    assert exam_gen.riktat_mal(None, None,
                               [{"el": "uppg4"}, {"el": "avtal1"}]) is None
    kandidat = _skriv_om_allt()
    llm, _calls = _stub_llm([json.dumps(kandidat)])
    res = exam_gen.refine_exam(
        _exam(), "höj gränsen och gör 4 svårare", model="m", llm=llm,
        malen=[{"el": "uppg4", "namn": "Uppgift 4"},
               {"el": "avtal1", "namn": "Betygsgränserna"}])
    assert res["exam"]["uppgifter"] == kandidat["uppgifter"]


def test_riktningen_ar_unionen_av_alla_mal():
    assert exam_gen.riktat_mal([6, 4], None,
                               [{"el": "uppg4"}, {"el": "uppg6"}]) \
        == {"uppgifter": [4, 6], "falt": ()}
    # Blandat: numret från klienten och fälten ur elementen.
    assert exam_gen.riktat_mal(4, None, [{"el": "uppg4"}, {"el": "rubrik"}]) \
        == {"uppgifter": [4], "falt": ("titel",)}
    # Två fältmål: nycklarna läggs ihop utan dubbletter.
    assert exam_gen.riktat_mal(None, None,
                               [{"el": "instr"}, {"el": "forsatt"}]) \
        == {"uppgifter": [], "falt": ("instruktion", "nyckelfraga",
                                      "forsattsbild")}
    # ETT mål är inte flerval: dagens par kommer tillbaka, oförändrat.
    assert exam_gen.riktat_mal(4, {"el": "uppg4"}) == ("uppgift", 4)
    assert exam_gen.riktat_mal(None, {"el": "rubrik"},
                               [{"el": "rubrik"}]) == ("falt", ("titel",))


def test_sammanfogningen_tar_unionen_ur_kandidaten():
    original = {"titel": "Potenser", "instruktion": "Skriv tydligt.",
                "uppgifter": [{"text": "ett"}, {"text": "två"},
                              {"text": "tre"}]}
    kandidat = {"titel": "Något annat", "instruktion": "Läs ihop först.",
                "uppgifter": [{"text": "ETT"}, {"text": "TVÅ"},
                              {"text": "TRE"}]}
    ihop, skal = exam_gen.sammanfoga_riktat(
        original, kandidat, {"uppgifter": [1, 3], "falt": ("instruktion",)})
    assert skal == ""
    assert [u["text"] for u in ihop["uppgifter"]] == ["ETT", "två", "TRE"]
    assert ihop["instruktion"] == "Läs ihop först."
    assert ihop["titel"] == "Potenser"        # inte pekat på → orört


def test_ett_saknat_mal_faller_hela_sammanfogningen():
    """Fyra genomförda ändringar av fem är den halvfärdiga sortens papper som
    upptäcks framför klassen."""
    original = {"uppgifter": [{"text": "ett"}, {"text": "två"},
                              {"text": "tre"}]}
    kandidat = {"uppgifter": [{"text": "ETT"}]}
    ihop, skal = exam_gen.sammanfoga_riktat(
        original, kandidat, {"uppgifter": [1, 3], "falt": ()})
    assert ihop is None and "uppgift 3" in skal


def test_flera_andrade_uppgifter_bedoms_var_for_sig():
    """Bedömningspasset kostar ett anrop per ÄNDRAD uppgift — två mål ska ge
    två, inte ett och inte elva."""
    llm, calls = _stub_llm([json.dumps(_skriv_om_allt_med_tva_sammanhang())])
    exam_gen.refine_exam(_exam(), "gör dem kortare", nummer=[4, 6],
                         model="m", llm=llm,
                         malen=[{"el": "uppg4", "namn": "Uppgift 4"},
                                {"el": "uppg6", "namn": "Uppgift 6"}])
    assert sum("bedömningsskrivare" in c["prompt"] for c in calls) == 2


def test_enkelmalets_prompt_ar_orord_av_flervalet():
    """KASSETTERNA. Banden i sviten är nycklade på promptens text: ett mål (och
    inget mål) måste ge exakt samma prompt som innan flervalet fanns."""
    doc = {"titel": "Prov", "uppgifter": [{"text": "ett"}]}
    mal = {"el": "rubrik", "namn": "Sidhuvudet", "innehall": "Ma2b · SA23"}
    for nummer, mal_in in ((None, None), (3, None), (None, mal), (3, mal)):
        utan = exam_gen.build_refine_prompt(doc, "gör om", nummer, mal_in)
        med = exam_gen.build_refine_prompt(doc, "gör om", nummer, mal_in,
                                           "", None, None)
        assert utan == med
        # En lista med ETT mål är inte heller flerval.
        assert utan == exam_gen.build_refine_prompt(
            doc, "gör om", nummer, mal_in, "", None, [mal])
        assert "flera element" not in utan


def test_flervalets_prompt_raknar_upp_malen():
    doc = {"titel": "Prov", "uppgifter": [{"text": "ett"}]}
    p = exam_gen.build_refine_prompt(
        doc, "gör dem kortare", [4, 6], None, "", None,
        [{"el": "uppg4", "namn": "Uppgift 4", "innehall": "Beräkna arean."},
         {"el": "uppg6", "namn": "Uppgift 6"}])
    assert "«Uppgift 4» och «Uppgift 6»" in p
    assert "Beräkna arean." in p
    assert "gäller uppgift 4 och uppgift 6: gör dem kortare" in p
    assert "låt allt annat i dokumentet stå oförändrat" in p


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
    obalanserat som prov.

    Bladet hade fyra uppgifter på tre förmågor (P, P, B, PL) och gick igenom så
    länge arbetsbladsprofilen tillät golv 0 på fem av sex förmågor. Med lärarens
    jämnhetskrav (Del D1) gäller i stället täckningsregeln för små dokument:
    varje uppgift ska bära sin egen förmåga. Bladet drillar fortfarande
    pq-formeln — det är formen, inte förmågefördelningen, som gör det till en
    övning."""
    return {
        "titel": "Arbetsblad — pq-formeln", "kurs": "Ma2b",
        "hjalpmedel": "Räknare",
        "uppgifter": [
            {"del": None, "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Lös $x^2 - 5x + 6 = 0$.", "innehall": ["pq-formeln"],
             "losning": "$x = 2$ eller $x = 3$.",
             # Trappan: en rad per poäng (exam_gen.bedomningssignaler).
             "bedomning": "+1 E en korrekt rot\n+1 E båda rötterna"},
            {"del": None, "formaga": "M", "typ": "rutin", "poang": [2, 0, 0],
             "text": "En rektangel har arean 8 och är 2 längre än den är bred. "
                     "Teckna en ekvation för bredden.",
             "innehall": ["pq-formeln"], "losning": "$b(b + 2) = 8$.",
             "bedomning": "+1 E inför en beteckning\n+1 E korrekt ekvation"},
            {"del": None, "formaga": "B", "typ": "rutin", "poang": [1, 1, 0],
             "text": "Vad kallas talet under rottecknet i pq-formeln?",
             "innehall": ["pq-formeln"], "losning": "Diskriminantuttrycket.",
             "bedomning": "+1 E namnger uttrycket\n+1 C förklarar dess roll"},
            {"del": None, "formaga": "PL", "typ": "rutin", "poang": [1, 1, 1],
             "text": "Hitta två tal med summan 7 och produkten 12.",
             "innehall": ["ekvationer"], "losning": "3 och 4.",
             "bedomning": "+1 E ett par tal\n+1 C systematisk prövning\n"
                          "+1 A generell metod"},
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
    # Likvärdigt, inte svårare: helt nya uppgifter på samma nivå.
    assert "HELT NYA" in ref and "ALDRIG" in ref
    assert "HÖJ" not in ref


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


def test_prompt_beskriver_strukturkomponenterna():
    """Prompten måste instruera modellen om deluppgifter, flerval och notis —
    annars förblir strukturmaskineriet vilande (modellen använder det aldrig)."""
    txt = exam_gen.INSTRUCTION
    assert "deluppgifter" in txt
    assert "alternativ" in txt and "ratt_alternativ" in txt
    assert "notis" in txt
    # och att de ska användas omdömesfullt, inte överallt — alla tre moderations-
    # signaler ska finnas kvar (deluppgifter, flerval, notis)
    assert "pedagogiskt" in txt
    assert "sparsamt" in txt        # flerval
    # notisen är numera förlagans kursiva ledtråd, och måttfullheten står som
    # ett tak i stället för som ordet «sällan»
    assert "var tredje uppgift" in txt
    # flerval får inte kombineras med deluppgifter — förbudet ska stå i prompten
    assert "aldrig på en uppgift som redan har deluppgifter" in txt


def test_prompt_beskriver_figurer():
    """Prompten måste instruera modellen om figurer — annars förblir
    figurmaskineriet (schema, rendering, mallar) vilande."""
    txt = exam_gen.INSTRUCTION
    assert "figur" in txt
    # några figurtyper ska nämnas som alternativ
    assert any(t in txt for t in ("andragrad", "normalfordelning", "enhetscirkel"))
    # figur och bild utesluter varandra ska framgå
    assert "figur ELLER bild" in txt or "utesluter" in txt


def test_prompt_kraver_exakt_antal():
    """Prompten ska kräva EXAKT antal uppgifter (inte 'ungefär') så den inte
    förhandlar bort antalet — modellen överproducerade annars (skarp körning)."""
    p = exam_gen.build_prompt("Ma2b", "SA23", [], antal=8, profil="prov")
    # ANTALET ska vara hårt (inte "ungefär N uppgifter"). "ungefär" får däremot
    # förekomma i förmågefördelningen — den är en riktlinje, inte ett exakt tal.
    assert "EXAKT 8 uppgifter" in p and "ungefär 8 uppgifter" not in p
    pa = exam_gen.build_prompt("Ma2b", "SA23", [], antal=5, profil="arbetsblad")
    assert "EXAKT 5 uppgifter" in pa and "ungefär 5 uppgifter" not in pa


def test_instruction_kraver_variation():
    """INSTRUCTION ska be modellen variera uppgifterna (mot repetitionen som
    den skarpa körningen visade)."""
    low = exam_gen.INSTRUCTION.lower()
    assert "variera" in low or "distinkt" in low


@pytest.mark.parametrize("antal", [6, 7, 8, 9, 10, 11, 12])
def test_balanced_skeleton_validerar_rent(antal):
    """Skelettet ska vara balanserat OCH ordnat BY CONSTRUCTION — appen
    garanterar hela balansen (förmåga + nivå + ordning), modellen skriver bara
    innehållet. Skelettet grammatik-tvingas, så om det validerar rent gör
    provet det också."""
    sk = exam_spec.balanced_skeleton(antal, "prov")
    assert len(sk) == antal
    doc = exam_spec.ExamDoc(
        titel="x", kurs="Ma2b", hjalpmedel="x",
        uppgifter=[exam_spec.ExamItem(
            del_=s["del"], formaga=s["formaga"], typ=s["typ"],
            poang=tuple(s["poang"]), text="Uppgift.", losning="L.", bedomning="B.")
            for s in sk])
    assert exam_spec.validate_balance(doc, profil="prov") == [], \
        f"antal={antal}: balansfel"
    assert exam_spec.validate_ordning(doc) == [], f"antal={antal}: ordningsfel"


@pytest.mark.parametrize("antal", list(range(3, 21)))
@pytest.mark.parametrize("delar", [True, False])
def test_provets_antalsgranser_ar_serverns_och_inte_en_smaksak(antal, delar):
    """Väljaren i planeringen (plan.js TYPVAL.Prov.antal) står på 3–20, och den
    siffran är inte vald — den är MÄTT här.

    Förut stod den på 4–12 och klampade tyst: en lärare som ville ha ett kort
    diagnostiskt prov eller ett långt terminsprov fick inte veta varför vredet
    tog emot. Nu ska varje antal i spannet ge ett skelett som validerar rent i
    BÅDA uppläggen — «En del» och «Del A + Del B» — för det är de två väljaren
    erbjuder. Faller något av dem ljuger raden i appen, och då ska det synas
    här och inte hos läraren."""
    sk = exam_spec.balanced_skeleton(antal, "prov", delar=delar)
    assert len(sk) == antal
    assert exam_spec.genomforbarhet(antal, "prov") == []
    doc = exam_spec._skeleton_doc(sk)
    assert exam_spec.validate_balance(doc, profil="prov") == [], \
        f"antal={antal} delar={delar}: balansfel"
    assert exam_spec.validate_ordning(doc) == [], \
        f"antal={antal} delar={delar}: ordningsfel"


def test_golvet_tre_ar_serverns_eget_krav():
    """Varför just 3 — och varför appen inte får erbjuda mindre.

    1 fälls av förkontrollen: provet måste rymma både en rutinuppgift och en
    med fullständig lösning. 2 tar sig förbi den men går inte att balansera —
    två poängtripplar räcker inte för att träffa NP:s nivåband, och skelettets
    poängsökning ger upp. Läraren hade fått ett prov med balansfel på pappret,
    vilket är värre än en gräns som säger vad den är."""
    assert exam_spec.genomforbarhet(1, "prov"), "en uppgift borde fällas"
    assert exam_spec.genomforbarhet(2, "prov") == []      # förkontrollen släpper
    tva = exam_spec._skeleton_doc(exam_spec.balanced_skeleton(2, "prov"))
    assert exam_spec.validate_balance(tva, profil="prov"), \
        "två uppgifter borde INTE kunna balanseras — flyttades bandet?"


@pytest.mark.parametrize("antal", [16, 17, 20, 26, 27, 30, 40])
def test_balanced_skeleton_kapas_inte_vid_16(antal):
    """Fyllnadslistan var tio element lång och tog slut vid len(golv) + 10 = 16
    slots. zip():en kapade då skelettet TYST: läraren som bad om 20 uppgifter
    fick ett prov på 16, utan fel och utan varning — grammatiken låser
    minItems/maxItems till skelettets längd, så den motsäger radens «EXAKT 20
    uppgifter». Från antal ≥ 27 validerade det kapade skelettet inte ens rent
    (8 fel), så poängsökningen gav upp och lämnade ifrån sig ett obalanserat
    prov. Fyllnaden cyklar nu, och skelettet når alltid `antal`."""
    sk = exam_spec.balanced_skeleton(antal, "prov")
    assert len(sk) == antal, f"antal={antal}: skelettet kapat till {len(sk)}"
    doc = exam_spec._skeleton_doc(sk)
    assert exam_spec.validate_balance(doc, profil="prov") == [], \
        f"antal={antal}: balansfel"
    assert exam_spec.validate_ordning(doc) == [], f"antal={antal}: ordningsfel"
    # Det läraren faktiskt drabbades av: grammatikens antal uppgifter.
    upp = exam_spec.to_response_format(skeleton=sk)["json_schema"]["schema"] \
        ["properties"]["uppgifter"]
    assert upp["minItems"] == upp["maxItems"] == antal
    # K har ingen E-nivå (se balanced_skeleton) — regeln måste överleva
    # cyklingen, som ger fler K-slots än den gamla fasta fyllnaden gjorde.
    k_slots = [s for s in sk if s["formaga"] == "K"]
    assert k_slots and all(s["poang"][0] == 0 for s in k_slots)


def _los(schema: dict, nod):
    """Följ en $ref till sin definition. Schemat hyvlas (exam_spec._hyvla):
    delscheman som står på flera ställen bor i $defs och pekas ut med $ref, så
    en test som läser en constraint måste följa pekaren."""
    while isinstance(nod, dict) and "$ref" in nod:
        nod = schema["$defs"][nod["$ref"].rsplit("/", 1)[-1]]
    return nod


def test_to_response_format_skeleton_last_per_index():
    """Med skeleton ska del/formaga/typ/poang låsas per uppgift via prefixItems
    (llama.cpp hedrar det — bekräftat i skarp körning)."""
    sk = exam_spec.balanced_skeleton(8, "prov")
    schema = exam_spec.to_response_format(skeleton=sk)["json_schema"]["schema"]
    upp = schema["properties"]["uppgifter"]
    assert upp["maxItems"] == 8 and len(upp["prefixItems"]) == 8
    # Den första PLATTA raden — en rad med deluppgifter bär sin poäng i barnen
    # och prövas i test_skelettets_deluppgifter_tvingas_av_grammatiken.
    i = next(i for i, s in enumerate(sk) if not s.get("delar"))
    it0 = upp["prefixItems"][i]["properties"]
    assert it0["del"] == {"const": sk[i]["del"]}
    assert it0["formaga"] == {"const": sk[i]["formaga"]}
    assert it0["typ"] == {"const": sk[i]["typ"]}
    assert _los(schema, it0["poang"])["prefixItems"] == \
        [{"const": p} for p in sk[i]["poang"]]
    # icke-tom text/losning/bedomning: minLength≥1 OCH required, annars kunde
    # modellen utelämna/null:a losning (den har default "" → ej required) och
    # falla på valideringen.
    assert _los(schema, it0["text"])["minLength"] == 1
    assert _los(schema, it0["losning"])["minLength"] == 1
    assert _los(schema, it0["bedomning"])["minLength"] == 1
    req = upp["prefixItems"][i].get("required", [])
    assert "losning" in req and "bedomning" in req


def test_prompt_har_skelettplan_for_alla_profiler():
    """Alla tre profilerna ska få den balanserade uppgiftsplanen (Del D1b) —
    jämn förmågetäckning ska vara räknad, inte hoppas på. Provet och
    arbetsbladet grammatiklåses (planen säger LÅSTA); gruppuppgiften får planen
    som instruktion, eftersom en låst rad inte kan ha deluppgifter och det är
    deluppgifterna som bär gruppens samtal."""
    p = exam_gen.build_prompt("Ma2b", "SA23", [], antal=8, profil="prov")
    assert "Uppgiftsplan" in p and "LÅSTA" in p
    for f in ("B", "P", "PL", "M", "R", "K"):
        assert f"({f})" in p
    pa = exam_gen.build_prompt("Ma2b", "SA23", [], antal=6, profil="arbetsblad")
    assert "Uppgiftsplan" in pa and "LÅSTA" in pa
    # Platt papper, inga delar. Vakten mätte förut på strängen «Del B», och den
    # råkar numera stå i TALREGLER — som BESKRIVNING av vilka talregler som
    # gäller utan räknare, inte som en begäran om delar. Mätningen sitter
    # därför på uppdragsraden som faktiskt beställer delar, plus på fältkravet.
    assert "Dela provet i Del B" not in pa
    assert "del: null" in pa
    pg = exam_gen.build_prompt("Ma2b", "SA23", [], antal=6,
                               profil="gruppuppgift")
    assert "Uppgiftsplan" in pg and "LÅSTA" not in pg
    assert "deluppgifter" in pg


# ───────────────────────── jämn förmågetäckning + NP-fördelning (Del D) ──

@settings(deadline=None, max_examples=40)
@given(antal=st.integers(min_value=4, max_value=20),
       profil=st.sampled_from(["prov", "arbetsblad", "gruppuppgift"]))
def test_skelettet_ar_balanserat_for_alla_storlekar_och_profiler(antal, profil):
    """Egenskapen läraren bad om: jämn förmågetäckning i ALLA tre
    dokumenttyperna, oavsett storlek. Skelettet ska (a) validera rent mot sin
    profil, (b) inte lämna någon förmåga på noll när dokumentet är stort nog att
    bära sex, och (c) för prov ligga innanför NP:s nivåband."""
    sk = exam_spec.balanced_skeleton(antal, profil,
                                     delar=(profil == "prov"))
    assert len(sk) == antal
    doc = exam_spec._skeleton_doc(sk)
    assert exam_spec.validate_balance(doc, profil=profil) == []
    s = exam_spec.poangsummor(doc)
    if antal >= exam_spec.MIN_BARARE_FOR_BAND:
        assert all(s["formagor"][f] > 0 for f in exam_spec.FORMAGA_NAMN)
    else:
        assert sum(1 for p in s["formagor"].values() if p > 0) >= antal
    if profil == "prov":
        for niva, (lo, hi) in niva_rubrik.niva_mal_prov().items():
            assert lo <= s[niva] / s["total"] <= hi


@pytest.mark.parametrize("antal", [6, 9, 12, 15, 18])
def test_skelettet_delar_provet_som_np(antal):
    """NP lägger 54–62 % av uppgifterna i den räknarfria delen, och den delen är
    INTE E-delen: alla tre nivåerna finns i båda delarna. Skelettet lade förut
    en eller två rutinuppgifter i Del B och resten i Del C."""
    sk = exam_spec.balanced_skeleton(antal, "prov", delar=True)
    b = [s for s in sk if s["del"] == "B"]
    c = [s for s in sk if s["del"] == "C"]
    assert b and c
    assert 0.4 <= len(b) / antal <= 0.8
    if antal >= 9:                       # med färre får inte alla nivåer plats
        assert any(s["poang"][2] for s in b), "Del B saknar A-poäng"


def test_jamna_band_ligger_runt_en_sjattedel():
    """Lärarens krav, som data: samma band för alla sex förmågor i alla tre
    profilerna, och 1/6 ska ligga innanför det."""
    for mal in (exam_spec.FORMAGA_MAL, exam_spec.ARBETSBLAD_FORMAGA_MAL,
                exam_spec.GRUPP_FORMAGA_MAL):
        assert set(mal) == set(exam_spec.FORMAGA_NAMN)
        assert len(set(mal.values())) == 1, "banden ska vara lika för alla sex"
        (lo, hi), = set(mal.values())
        assert lo > 0, "ingen förmåga får sakna poäng"
        assert lo <= exam_spec.JAMN_FORMAGA <= hi


def test_np_fordelningen_ar_intern_konsistent():
    """NP_FORDELNING är mätdata och ska gå att räkna om ur NP_MATNING."""
    for namn, m in niva_rubrik.NP_MATNING.items():
        u, r = m["utan_raknare"], m["med_raknare"]
        assert tuple(a + b for a, b in zip(u["poang"], r["poang"])) \
            == m["poang"], namn
        assert u["uppgifter"] + r["uppgifter"] == m["uppgifter"], namn
        assert sum(m["karaktar"]) == m["uppgifter"], namn
    assert set(niva_rubrik.NP_MATNING) <= {p.split(" —")[0]
                                           for p in niva_rubrik.ANALYSERADE_PROV}
    for niva, (lo, hi) in niva_rubrik.NP_FORDELNING["poangandel"].items():
        i = niva_rubrik.NIVAER.index(niva)
        matt = [m["poang"][i] / sum(m["poang"])
                for m in niva_rubrik.NP_MATNING.values()]
        # Bandet ska rymma varje mätpunkt (halv procentenhet för avrundningen).
        assert lo <= min(matt) + 0.005 and max(matt) - 0.005 <= hi, niva
    # Målen är mätningen plus marginal — aldrig snävare än den.
    for niva, (lo, hi) in niva_rubrik.NP_FORDELNING["poangandel"].items():
        mlo, mhi = niva_rubrik.niva_mal_prov()[niva.lower()]
        assert mlo <= lo and mhi >= hi


def test_np_tripplarna_har_ratt_karaktar():
    """Varje trippel ska ha den karaktär den står under — annars skulle
    skelettet bygga en A-uppgift av en trippel utan A-poäng."""
    for kar, tripplar in niva_rubrik.NP_TRIPPLAR.items():
        assert tripplar
        for t in tripplar:
            assert exam_spec._karaktar(list(t)) == kar, (kar, t)


def test_arvande_deluppgifter_hojer_inte_kravet():
    """Fyndet ur den skarpa gruppuppgiftsinspelningen: fyra uppgifter, två av
    dem delade i deluppgifter som ÄRVER förälderns förmåga. Sex poängbärande
    enheter — men fortfarande bara fyra förmågor att fördela, för en ärvande
    deluppgift lägger till en poängpost och inte en bärare. Bandet slog ändå
    till och krävde alla sex täckta, vilket dokumentet aldrig kunde leverera:
    uppgiftsplanen hade fyra rader och modellen följde den exakt."""
    def uppg(formaga, poang, delar=None):
        u = {"del": None, "formaga": formaga, "typ": "problem",
             "text": "Uppgift.", "poang": [0, 0, 0] if delar else poang,
             "losning": "" if delar else "L.", "bedomning": "" if delar else "B."}
        if delar:
            u["deluppgifter"] = [{"poang": p, "text": "del", "losning": "L.",
                                  "bedomning": "B."} for p in delar]
        return u

    doc = {"titel": "x", "kurs": "Ma2b", "hjalpmedel": "x", "grupp": {
        "elever": 3, "langd_min": 45, "redovisning": "muntligt"}, "uppgifter": [
            uppg("P", [2, 0, 0]),
            uppg("B", None, [[0, 1, 0], [0, 1, 0]]),
            uppg("M", None, [[1, 0, 0], [0, 1, 0]]),
            uppg("PL", [0, 0, 1])]}
    d, fel = exam_spec.validate_exam_json(doc, "gruppuppgift")
    assert d is not None
    assert exam_spec.formagebarare(d) == 4, "ärvande deluppgifter räknades som bärare"
    assert [e for e in fel if e["code"] == "formagabalans"] == [], fel

    # Deklarerar deluppgifterna EGNA förmågor är de däremot bärare — och då
    # höjs kravet. Två deluppgifter som båda tar Procedur ger fem bärare men
    # bara tre täckta förmågor, och det ska fällas.
    doc2 = json.loads(json.dumps(doc))
    for d_ in doc2["uppgifter"][1]["deluppgifter"]:
        d_["formaga"] = "P"
    d2, fel2 = exam_spec.validate_exam_json(doc2, "gruppuppgift")
    assert exam_spec.formagebarare(d2) == 5
    assert any(e["code"] == "formagabalans" for e in fel2), fel2


# ───────────────────────── lärarens nivåval (NIVAVAL) ────────────────────

def _bara_e_prov() -> dict:
    """_exam() omlagd till «Bara E»: nästan alla poäng på E, K-uppgiften bär C
    (ingen EK-poäng finns). 16 p (E 14 / C 2 / A 0) — träffar Bara E-banden
    men INTE NP-banden, så samma dokument skiljer de två målvärldarna åt."""
    data = _exam()
    for u, poang in zip(data["uppgifter"],
                        [[3, 0, 0], [2, 0, 0], [2, 0, 0], [3, 0, 0],
                         [2, 0, 0], [2, 0, 0], [0, 2, 0]]):
        u["poang"] = poang
        # Poängen flyttades, alltså flyttas trappan med: en rad per poäng, på
        # den nivå poängen faktiskt ligger (exam_gen.bedomningssignaler mäter
        # just det, och en fixtur som säger emot sig själv mäter ingenting).
        u["bedomning"] = _trappa(poang)
    return data


def test_nivaval_defaultlagen_ar_none():
    """Defaultlägena («Balanserat»/«Blandat»), okända etiketter och profiler
    utan väljare ska alla ge None — det är regeln som gör en tom ruta till
    exakt samma begäran som före fältet (kassettregeln)."""
    assert exam_spec.nivaval("prov", "Balanserat") is None
    assert exam_spec.nivaval("arbetsblad", "Blandat") is None
    assert exam_spec.nivaval("prov", "") is None
    assert exam_spec.nivaval("prov", None) is None
    assert exam_spec.nivaval("prov", "påhittat läge") is None
    # Gruppuppgiften har ingen väljare alls.
    assert exam_spec.nivaval("gruppuppgift", "Bara E") is None
    # …och de riktiga etiketterna ger mix + band.
    for profil, val in (("prov", "Bara E"), ("prov", "E-tyngd"),
                        ("prov", "C/A-tyngd"), ("arbetsblad", "E-nivå"),
                        ("arbetsblad", "C-nivå"), ("arbetsblad", "A-nivå")):
        nv = exam_spec.nivaval(profil, val)
        assert nv and set(nv) == {"mix", "mal"}, (profil, val)


@pytest.mark.parametrize("profil,val", [
    (p, v) for p, valen in exam_spec.NIVAVAL.items() for v in valen])
@pytest.mark.parametrize("antal", [3, 6, 9, 12, 16, 20])
def test_nivaval_skelettet_traffar_lararens_band(profil, val, antal):
    """Väljaren var en dekoration: inget av värdena nådde servern, och
    fördelningen kom alltid ur profilens KARAKTARSMIX. Nu ska varje val ge
    ett skelett som validerar rent mot VALETS band — i väljarens hela
    antalsspann, för det är de kombinationer appen erbjuder."""
    nv = exam_spec.NIVAVAL[profil][val]
    for delar in ((True, False) if profil == "prov" else (False,)):
        sk = exam_spec.balanced_skeleton(antal, profil, delar=delar,
                                         mix=nv["mix"], niva_mal=nv["mal"])
        assert len(sk) == antal
        doc = exam_spec._skeleton_doc(sk)
        assert exam_spec.validate_balance(
            doc, niva_mal=nv["mal"], profil=profil) == [], \
            f"{profil}/{val} antal={antal} delar={delar}"


def test_nivaval_bara_e_ger_inga_a_poang_och_k_bar_c():
    """«Bara E» är inte riktigt bara E — K-uppgifter har ingen E-nivå och
    lyfts till C i skelettet. Men A-poäng ska det aldrig bli, och varje
    K-rad ska bära sina poäng på C."""
    nv = exam_spec.NIVAVAL["prov"]["Bara E"]
    sk = exam_spec.balanced_skeleton(12, "prov", delar=True,
                                     mix=nv["mix"], niva_mal=nv["mal"])
    assert all(s["poang"][2] == 0 for s in sk), "Bara E fick A-poäng"
    k = [s for s in sk if s["formaga"] == "K"]
    assert k and all(s["poang"][0] == 0 and s["poang"][1] > 0 for s in k)


def test_validate_exam_json_mater_mot_lararens_band():
    """Samma dokument, två domar: ett Bara E-prov ska fällas av NP-banden
    (det ÄR inte NP-format) men frias av sitt eget nivåval. Det är exakt
    skillnaden som gör att reparationsloopen inte slåss mot skelettet."""
    data = _bara_e_prov()
    mal = exam_spec.NIVAVAL["prov"]["Bara E"]["mal"]
    doc, fel_default = exam_spec.validate_exam_json(data, "prov")
    assert doc is not None
    assert any(e["code"] == "nivabalans" for e in fel_default)
    doc2, fel_val = exam_spec.validate_exam_json(data, "prov", mal)
    assert doc2 is not None and fel_val == [], fel_val


def test_generate_exam_reparerar_mot_nivavalets_band():
    """Kedjans mitt: med niva_mal ska ett Bara E-svar gå rent igenom
    valideringen — utan hade samma svar fått nivabalansfel och bränt
    reparationsrundor på att dra pappret mot NP."""
    nv = exam_spec.NIVAVAL["prov"]["Bara E"]
    llm, _calls = _stub_llm([json.dumps(_bara_e_prov())])
    res = exam_gen.generate_exam("Ma2b", "SA23", [], model="m", llm=llm,
                                 antal=7, niva_mal=nv["mal"])
    assert res["errors"] == [] and res["rounds"] == 1
    # Kontrastet: utan bandet fastnar exakt samma svar i nivabalansen.
    llm2, _ = _stub_llm([json.dumps(_bara_e_prov())])
    res2 = exam_gen.generate_exam("Ma2b", "SA23", [], model="m", llm=llm2,
                                  antal=7)
    assert any(e["code"] == "nivabalans" for e in res2["errors"])


def test_refine_exam_mater_mot_dokumentets_nivaval():
    """REFINE-fällan: ett Bara E-prov som skrivs om ska dömas mot sitt eget
    val, inte profilens defaultband — annars får varje varv nivabalansfel
    och riktade ändringar vägras («ingenting ändrades»)."""
    nv = exam_spec.NIVAVAL["prov"]["Bara E"]
    fore = _bara_e_prov()
    efter = _bara_e_prov()
    efter["uppgifter"][0]["text"] = "Ange nollställena till $g(x) = (x-2)(x+5)$."
    llm, _ = _stub_llm([json.dumps(efter)])
    res = exam_gen.refine_exam(fore, "byt tal i uppgift 1", nummer=1,
                               model="m", llm=llm, niva_mal=nv["mal"])
    assert res["errors"] == []
    assert res["exam"]["uppgifter"][0]["text"] == efter["uppgifter"][0]["text"]
    # Utan valet: samma varv fälls, och den riktade ändringen backas.
    llm2, _ = _stub_llm([json.dumps(efter)])
    res2 = exam_gen.refine_exam(fore, "byt tal i uppgift 1", nummer=1,
                                model="m", llm=llm2)
    assert any(e["code"] == "nivabalans" for e in res2["errors"])
    assert res2["exam"] == fore, "riktad ändring utan mål-band ska backas"


# ══════════════ DELUPPGIFTERNA I SKELETTET ══════════════
# «Tänk på hur jag har strukturerat deluppgifterna», sa läraren om sitt eget
# prov. Generatorn kunde aldrig leverera dem: skelettet låste `poang` per
# uppgift med `const`, och en uppgift med poäng får per schemat inga
# deluppgifter. Mallen bar formen; ingenting fyllde den.


def _doc_med_delar(sk: list[dict]) -> exam_spec.ExamDoc:
    """Skelettet som ett FÄRDIGT dokument, deluppgifter och allt — det som
    modellen ska svara med. `_skeleton_doc` bygger den platta versionen (bara
    aggregaten), och skillnaden mellan de två är hela frågan: delningen får
    inte flytta en enda poäng."""
    uppgifter = []
    for s in sk:
        if s.get("delar"):
            uppgifter.append(exam_spec.ExamItem(
                del_=s["del"], formaga=s["formaga"], typ=s["typ"],
                poang=(0, 0, 0), text="_", deluppgifter=[
                    exam_spec.SubItem(poang=tuple(d), text="_", losning="_",
                                      bedomning="_") for d in s["delar"]]))
        else:
            uppgifter.append(exam_spec.ExamItem(
                del_=s["del"], formaga=s["formaga"], typ=s["typ"],
                poang=tuple(s["poang"]), text="_", losning="_",
                bedomning="_"))
    return exam_spec.ExamDoc(titel="_", kurs="_", hjalpmedel="_",
                             uppgifter=uppgifter)


@pytest.mark.parametrize("antal", [6, 8, 10, 12, 16, 20])
def test_skelettet_ger_provet_deluppgifter(antal):
    """Provet SKA få deluppgifter, och de ska summera till radens poäng.

    Två mönster, båda nationella provets: kortsvarsparet (en rutinrad värd två
    poäng på en nivå blir a) och b) om SAMMA sak — NpMa2a vt17 delprov B,
    uppgift 1, 2, 3, 4 och 9) och stegringen inne i uppgiften (a) tar de lägre
    nivåerna, b) den högsta — förlagans uppgift 5)."""
    sk = exam_spec.balanced_skeleton(antal, "prov")
    delade = [s for s in sk if s.get("delar")]
    assert delade, f"antal={antal}: inte en enda uppgift fick deluppgifter"
    for s in delade:
        summa = [sum(d[i] for d in s["delar"]) for i in range(3)]
        assert summa == list(s["poang"]), \
            f"{s['delar']} summerar till {summa}, inte {s['poang']}"
        assert all(sum(d) > 0 for d in s["delar"]), "en deluppgift utan poäng"
        assert len(s["delar"]) >= 2, "en ensam deluppgift är ingen deluppgift"
    # Kortsvarsparet: enpoängsfrågor, alla på SAMMA nivå (NP:s (1/0/0)+(1/0/0),
    # (0/1/0)+(0/1/0), (0/0/1)+(0/0/1)) — aldrig en E-fråga bredvid en A-fråga
    # under samma nummer.
    for s in delade:
        if s["typ"] == "rutin":
            assert all(sum(d) == 1 for d in s["delar"]), s["delar"]
            assert len({tuple(d) for d in s["delar"]}) == 1, s["delar"]


@pytest.mark.parametrize("antal", [6, 8, 10, 12, 16, 20])
def test_delningen_flyttar_inga_poang(antal):
    """DELNINGEN ÄR EN OMFÖRDELNING, INTE ETT TILLSKOTT.

    Nivåsummor, förmågesummor och totalen ska vara exakt desamma med och utan
    deluppgifter — annars räknar nivåbalansen, kravgränserna och tidsmodellen
    på ett annat prov än det som skrivs ut. Deluppgifterna ärver förälderns
    förmåga (de deklarerar ingen egen), så förmågefördelningen står stilla."""
    sk = exam_spec.balanced_skeleton(antal, "prov")
    platt = exam_spec.poangsummor(exam_spec._skeleton_doc(sk))
    delat = exam_spec.poangsummor(_doc_med_delar(sk))
    assert platt == delat
    # TIDEN MÄTS PÅ HUVUDUPPGIFTER. NP-kalibreringen räknades så: vt17 delprov
    # B+C har 15 huvuduppgifter och 22 deluppgifter, och MIN_PER_UPPGIFT sattes
    # mot de 15. Antalet huvuduppgifter är orört av delningen, så tiden är det
    # också.
    doc = _doc_med_delar(sk)
    assert len(doc.uppgifter) == antal
    assert exam_spec.tidsatgang(delat, len(doc.uppgifter)) == \
        exam_spec.tidsatgang(platt, antal)
    # Och balansen håller på det RIKTIGA dokumentet, inte bara på aggregaten.
    assert exam_spec.validate_balance(doc, profil="prov") == []
    assert exam_spec.validate_ordning(doc) == []


@pytest.mark.parametrize("antal", [6, 8, 10, 12, 16, 20])
def test_np_delordningen_kortsvar_i_del_a_fullstandiga_i_del_b(antal):
    """NP:s egen delordning (NpMa2a vt17 och vt22, sidan 1):

        delprov B — «Endast svar krävs», utan digitala verktyg
        delprov C — «Fullständiga lösningar krävs», utan digitala verktyg
        delprov D — fullständiga lösningar MED digitala verktyg

    Lärarens Del A är NP:s B+C och hennes Del B är NP:s D. Alltså: kortsvaren
    först i Del A, sedan de fullständiga — och inga kortsvar alls i Del B."""
    sk = exam_spec.balanced_skeleton(antal, "prov")
    del_a = [s for s in sk if s["del"] == "B"]
    del_b = [s for s in sk if s["del"] == "C"]
    assert del_a and del_b
    assert not any(s["typ"] == "rutin" for s in del_b), \
        "räknardelen har ett kortsvar — NP:s delprov D har inga"
    typer = [s["typ"] == "rutin" for s in del_a]
    assert typer[0], "Del A börjar inte med ett kortsvar"
    # Ingen rutinrad efter den första fullständiga: blocket är sammanhängande.
    assert typer == sorted(typer, reverse=True), \
        f"kortsvaren ligger utspridda i Del A: {[s['typ'] for s in del_a]}"
    assert 1 <= sum(typer) <= exam_spec.MAX_LIKA_I_RAD


def test_skelettets_deluppgifter_tvingas_av_grammatiken():
    """Grammatiken ska tvinga formen, inte bara tillåta den: föräldern låses
    till [0, 0, 0], antalet deluppgifter till planens, och varje deluppgifts
    poängtrippel till sin egen `const`. Utan det skrev modellen en platt
    uppgift och kom undan med det."""
    sk = exam_spec.balanced_skeleton(10, "prov")
    schema = exam_spec.to_response_format(skeleton=sk)["json_schema"]["schema"]
    prefix = schema["properties"]["uppgifter"]["prefixItems"]
    delade = [(i, s) for i, s in enumerate(sk) if s.get("delar")]
    assert delade
    for i, s in delade:
        props = prefix[i]["properties"]
        assert _los(schema, props["poang"])["prefixItems"] == \
            [{"const": 0}] * 3
        d = _los(schema, props["deluppgifter"])
        assert d["minItems"] == d["maxItems"] == len(s["delar"])
        assert "deluppgifter" in prefix[i]["required"]
        for gren, trippel in zip(d["prefixItems"], s["delar"]):
            sub = _los(schema, gren)
            assert _los(schema, sub["properties"]["poang"])["prefixItems"] == \
                [{"const": p} for p in trippel]
            # Deluppgiften BÄR lösningen och bedömningen när föräldern är tom.
            for fält in ("text", "losning", "bedomning"):
                assert fält in sub["required"]
                assert _los(schema, sub["properties"][fält])["minLength"] == 1
    # En PLATT rad får inga deluppgifter alls — poängen får inte delas två
    # gånger, och `const: null` säger det på en tiondel av tecknen.
    for i, s in enumerate(sk):
        if not s.get("delar"):
            assert prefix[i]["properties"]["deluppgifter"] == {"const": None}


@pytest.mark.parametrize("antal", [6, 8, 10, 12, 16, 20])
def test_kortsvaren_ar_egna_numrerade_uppgifter(antal):
    """LÄRARENS DOM 2026-08-22: «Uppgift 1 har deluppgift a och b men de är
    inte relaterade till varandra. Om det ska vara deluppgifter då ska det
    handla om samma sak. Kolla hur nationella provet är gjort.»

    NpMa2a vt17 delprov B (s. 2–7): nio kortsvarsuppgifter med EGET NUMMER,
    värda en eller två poäng. Fyra är enkla frågor; fem har a) och b), och
    varje par delar en graf, en ekvationstyp eller ett uttryck. «Samlingen» —
    en hög orelaterade E-frågor under ett nummer — finns inte i NP och finns
    inte längre här."""
    sk = exam_spec.balanced_skeleton(antal, "prov")
    kort = [s for s in sk if s["typ"] == "rutin"]
    assert kort, "provet fick inga kortsvar alls"
    for s in kort:
        assert 1 <= sum(s["poang"]) <= 3,             f"kortsvaret är värt {sum(s['poang'])} p — NP:s ger en till tre"
        delar = s.get("delar")
        if delar is None:
            continue
        # Paret är NP:s: två (eller tre) frågor à en poäng på SAMMA nivå.
        assert 2 <= len(delar) <= 3, delar
        assert all(sum(d) == 1 for d in delar), delar
        assert len({tuple(d) for d in delar}) == 1,             f"kortsvarets delar ligger på olika nivåer: {delar}"


def test_kortsvarsparet_foljer_np_tripplarna():
    """NP:s egna par, rad för rad (vt17 delprov B): uppgift 1 och 2 är
    (1/0/0)+(1/0/0), uppgift 4 är (0/1/0)+(0/1/0), uppgift 9 är
    (0/0/1)+(0/0/1). En ensam poäng är en enkel fråga (uppgift 5, 7, 8), och
    en trippel över två nivåer är inget kortsvar alls."""
    d = exam_spec._dela_poang
    assert d([2, 0, 0], "rutin") == [[1, 0, 0], [1, 0, 0]]
    assert d([0, 2, 0], "rutin") == [[0, 1, 0], [0, 1, 0]]
    assert d([0, 0, 2], "rutin") == [[0, 0, 1], [0, 0, 1]]
    assert d([3, 0, 0], "rutin") == [[1, 0, 0]] * 3
    assert d([1, 0, 0], "rutin") is None
    assert d([0, 1, 0], "rutin") is None
    assert d([1, 1, 0], "rutin") is None


def test_kortsvaret_kraver_en_stam():
    """Stammen är det som gör a) och b) till SAMMA uppgift — «Figuren visar
    grafen till andragradsfunktionen f», «Lös ekvationerna och svara exakt».
    Grammatiken lät förut en kortsvarsrad lämna texten tom; det var
    samlingens undantag, och samlingen är borta."""
    sk = exam_spec.balanced_skeleton(10, "prov")
    schema = exam_spec.to_response_format(skeleton=sk)["json_schema"]["schema"]
    prefix = schema["properties"]["uppgifter"]["prefixItems"]
    kort = [i for i, s in enumerate(sk)
            if s.get("delar") and s["typ"] == "rutin"]
    assert kort
    for i in kort:
        assert _los(schema, prefix[i]["properties"]["text"])["minLength"] == 1
    plan = exam_gen._skelett_plan(sk)
    assert "KORTSVAR MED a) OCH b)" in plan and "SAMMA sak" in plan
    assert "text TOM" not in plan
    # Deluppgifternas poäng står i planen — grammatiken låser dem, men bara
    # planen säger vad de ska handla om.
    assert "deluppgifter: a) [1, 0, 0]" in plan


def test_prompten_kraver_att_deluppgifter_hor_ihop():
    """Regeln kan inte tvingas av grammatiken: poängtripplar vet ingenting om
    innehåll. Den står därför i prompten, med NP:s eget exempel som form, och
    den måste stå i INSTRUCTION — omskrivningen (build_refine_prompt) får bara
    den texten med sig, och «gör om uppgift 1» ska inte kunna återinföra två
    orelaterade frågor under samma nummer."""
    i = exam_gen.INSTRUCTION
    assert "DELUPPGIFTERNA HÖR ALLTID TILL SAMMA SAK" in i
    assert "Bestäm funktionens största värde" in i
    assert "TVÅ" in i and "numrerade uppgifter" in i


def test_deluppgift_far_bara_egen_figur_eller_bild():
    """Figuren sitter DÄR DEN FRÅGAS OM (exam_spec.SubItem). Förlagans 1(a) har
    grafen inne i deluppgiften medan b)–e) är rena räknefrågor; på föräldern
    hade den sett ut att gälla alla fem."""
    d = exam_spec.SubItem(poang=(1, 0, 0), text="Bestäm symmetrilinjen.",
                          losning="$x = 3$.", bedomning="+1 E.",
                          figur={"typ": "andragrad", "a": -1, "b": 6, "c": -5})
    assert d.figur is not None
    with pytest.raises(Exception):
        exam_spec.SubItem(poang=(1, 0, 0), text="_", losning="_",
                          bedomning="_", bild=1,
                          figur={"typ": "linjar", "k": 1, "m": 0})


def test_klockslagen_ar_lararens_och_star_inte_i_grammatiken():
    """«Provtid: kl. 12.45–14.15 (90 minuter).» — förlagans form. Klockslagen
    kommer ur panelen (plan.js provNar), inte ur modellen, och står därför inte
    i schemat alls: ett fält modellen ser är ett fält modellen fyller i."""
    schema = exam_spec.to_response_format()["json_schema"]["schema"]
    assert "klockslag" not in schema["properties"]
    doc = exam_spec.ExamDoc(titel="Kapitel 2", kurs="Matematik 2c",
                            tid_min=90, klockslag="12:45–14:15",
                            hjalpmedel="Formelblad.",
                            uppgifter=[exam_spec.ExamItem(
                                formaga="P", typ="rutin", poang=(1, 0, 0),
                                text="_", losning="_", bedomning="_")])
    vy = exam_latex._forsatt_vy(doc, [])
    assert vy["provtid"] == r"kl.\ 12.45\textendash{}14.15 (90 minuter)."
    utan = doc.model_copy(update={"klockslag": None})
    assert exam_latex._forsatt_vy(utan, [])["provtid"] == "90 minuter."


@pytest.mark.parametrize("titel,kurs,vantad", [
    # Modellens egen långa titel — 58 tecken, tryckt rakt igenom delnamnet i
    # sidhuvudet innan rubriken byggdes här. Kursen faller före momentet.
    ("Prov: Potenser, rötter och algebraiska uttryck", "Matematik 1c",
     "Prov Potenser, rötter och algebraiska…"),
    # 43 tecken med kursen — ett för mycket för sidhuvudet, så kursen faller
    # och momentet står helt. På försättsbladet (taket 60) står båda, se
    # test_forsattsbladets_rubrik_far_plats_med_kursen.
    ("Derivata och gränsvärden", "Matematik 3c",
     "Prov Derivata och gränsvärden"),
    # Lärarens egen: rörs inte.
    ("Kapitel 2", "Matematik 2c", "Prov Kapitel 2 – Matematik 2c"),
    # Kursen står redan i titeln — den ska inte tryckas två gånger.
    ("Prov Kapitel 2 – Matematik 2c", "Matematik 2c",
     "Prov Kapitel 2 – Matematik 2c"),
    # Appens interna kursform («Matematik, nivå 2c») är kursväljarens, inte
    # papprets.
    ("Derivata", "Matematik, nivå 3c", "Prov Derivata – Matematik 3c"),
])
def test_provrubriken_ar_forlagans_korta_form(titel, kurs, vantad):
    """«Prov Kapitel 2 – Matematik 2c» — 29 tecken. Rubriken BYGGS ur momentet
    och kursen i stället för att klistras ihop ur modellens titel."""
    assert exam_latex._provrubrik(titel, kurs) == vantad
    assert len(vantad) <= exam_latex._RUBRIK_TAK


def test_forsattsbladets_rubrik_far_plats_med_kursen():
    """Två tak, och de mäter olika saker: sidhuvudet är smalt därför att
    delrutan står bredvid, försättsbladets rubrik står centrerad i \\LARGE över
    hela satsytan. En titel som inte ryms i sidhuvudet ska alltså ändå bära
    kursen på försättsbladet."""
    doc = exam_spec.ExamDoc(
        titel="Derivata och gränsvärden", kurs="Matematik 3c", tid_min=90,
        hjalpmedel="Formelblad.",
        uppgifter=[exam_spec.ExamItem(formaga="P", typ="rutin",
                                      poang=(1, 0, 0), text="_",
                                      losning="_", bedomning="_")])
    vy = exam_latex._forsatt_vy(doc, [])
    assert vy["titelrad"] == "Prov Derivata och gränsvärden"
    assert vy["sidhuvud"] == "Prov Derivata och gränsvärden"
    # Kursen försvinner inte från pappret, den flyttar till underraden.
    assert vy["underrad"] == "Matematik 3c"
    # Och rymmer rubriken både momentet och kursen står båda kvar — det är
    # förlagans egen form («Prov Kapitel 2 – Matematik 2c»). Tankstrecket är
    # ett KOMMANDO i utdatan: Computer Modern har ingen glyf på U+2013.
    kort = doc.model_copy(update={"titel": "Kapitel 2", "kurs": "Matematik 2c"})
    vy2 = exam_latex._forsatt_vy(kort, [])
    assert vy2["titelrad"] == r"Prov Kapitel 2 \textendash{} Matematik 2c"
    assert vy2["underrad"] is None


# ══════════════ BEDÖMNINGSTRAPPAN ══════════════
#
# Lärarens granskning av det skarpa provet 2026-08-23: «på fleruppgifter
# framgår inte vad varje poäng ges för», och «elevlösningarna hoppar över
# steg». Formen är nationella provets bedömningsanvisningar (Ma 1c vt22,
# Ma 2c vt22): godtagbart svar överst, sedan EN RAD PER POÄNG med nivån.


def test_bedomningsrader_delar_trappan():
    rader = exam_spec.bedomningsrader(
        "+1 E tecknar sambandet\n+1 C lösning med korrekt svar")
    assert [(r["poang"], r["niva"], r["krav"]) for r in rader] == [
        (1, "E", "tecknar sambandet"), (1, "C", "lösning med korrekt svar")]


def test_bedomningsrader_laser_de_gamla_dokumentens_enradare():
    """Proven som redan ligger i basen skrev trappan på EN rad med komman.
    De ska fortsätta gå att läsa — men decimalkommat i «25,6» får inte klippa
    raden, och notraden (det väntade felet) är ingen poäng."""
    rader = exam_spec.bedomningsrader(
        "+1 E korrekt svar 25,6 mm, +1 C fullständig lösning; "
        "vanligt fel: basen multipliceras först")
    assert [r["poang"] for r in rader] == [1, 1, 0]
    assert rader[0]["krav"] == "korrekt svar 25,6 mm"
    assert rader[-1]["not"] and rader[-1]["krav"].startswith("Vanligt fel")


# ── LÄRARENS GRANSKNING AV PROV 40 (2026-09-06) ───────────────────────
# Fyra domar i samma pass: bildtext under försättsbladets bild, hennes egen
# bild ska faktiskt tryckas där, provets namn bort ur sidhuvudet på varje blad,
# och «Vanligt fel» bort ur bedömningsanvisningen till förmån för korta rader.


def _exam_med_forsattsbild(bildtext=None):
    data = copy.deepcopy(_exam())
    data["forsattsbild"] = {
        "person": "John Napier (1550–1617), skotten som räknade fram de "
                  "första logaritmtabellerna.",
        "scene": "SCENE. A dim stone study at night. " + "x" * 80,
    }
    if bildtext is not None:
        data["forsattsbild"]["bildtext"] = bildtext
    doc, fel = exam_spec.validate_exam_json(data)
    assert doc is not None and fel == [], fel
    return doc


def _forsattsbladet(tex):
    """Allt före den första sidbrytningen: försättsbladet och bara det."""
    return tex.split("\\newpage")[0]


def test_forsattsbladets_egna_bild_trycks_med_sin_bildtext():
    """Läraren släppte sin egen bild i porträttrutan och bad om «en liten
    figurtext till denna, centrerad under bilden». Bilden reste aldrig till
    mallen (nyckeln «forsatt» är ingen uppgift) och bildtexten fanns inte som
    fält, så pappret fick varken bilden eller raden."""
    doc = _exam_med_forsattsbild(
        "Napier & hans tabeller vid ljuset i arbetsrummet.")
    tex = exam_latex.render_prov(doc, forsatt_bild="egen-forsatt.png")
    forsatt = _forsattsbladet(tex)
    # 58 mm och inte 70: höjden är mätt mot vad som är kvar under
    # namnraderna när bildtexten tar två rader (se prov.tex.j2).
    assert (r"\includegraphics[width=0.7\textwidth,height=58mm,"
            r"keepaspectratio]{egen-forsatt.png}") in forsatt
    # Bildtexten står under bilden, i \small\itshape, och ESCAPAD: den är ren
    # text och ett «&» i den skulle annars spräcka kompileringen.
    assert r"{\small\itshape Napier \& hans tabeller vid ljuset i " \
        r"arbetsrummet.}" in forsatt
    assert "Napier & hans" not in forsatt


def test_forsattsbladet_utan_egen_bild_star_som_forut():
    """Bilden är LÄRARENS och kommer bara med godkännandet. Utan den ska
    försättsbladet se ut precis som innan. Ingen tom ram, ingen includegraphics
    som pekar på en fil som inte finns."""
    doc = _exam_med_forsattsbild("En rad som inte ska tryckas utan bild.")
    forsatt = _forsattsbladet(exam_latex.render_prov(doc))
    assert "includegraphics" not in forsatt
    assert "En rad som inte ska tryckas utan bild." not in forsatt
    # Och ett prov helt utan porträtt kompilerar likaså utan rad.
    doc_utan, _ = exam_spec.validate_exam_json(_exam())
    assert "includegraphics" not in _forsattsbladet(
        exam_latex.render_prov(doc_utan, forsatt_bild=None))


def test_bedomningsanvisningen_trycker_inte_notraden():
    """LÄRAREN (2026-09-06): «detta med vanliga fel kan vi ta bort helt och
    hållet så att vi sparar plats». Raden är ingen poäng, den stod sist i
    högerspalten och åt den plats trappan behöver.

    PARSERN rör vi inte: proven i basen bär raden och ska fortsätta gå att
    läsa (test_bedomningsrader_laser_de_gamla_dokumentens_enradare). Det är
    TRYCKET som slutar sätta den."""
    trappa = ("+1 E tecknar sambandet\n+1 C fullständig lösning\n"
              "Vanligt fel: minustecknet tappas när $-3$ kvadreras")
    # Parsern ser tre rader, varav en not …
    assert len(exam_spec.bedomningsrader(trappa)) == 3
    # … pappret ser två.
    rader = exam_latex._bedomning_rader(trappa)
    assert [r["niva"] for r in rader] == ["+1 E", "+1 C"]
    assert not any("Vanligt fel" in r["krav"] for r in rader)

    data = copy.deepcopy(_exam())
    data["uppgifter"][0]["bedomning"] = trappa
    data["uppgifter"][0]["poang"] = [1, 1, 0]
    doc, fel = exam_spec.validate_exam_json(data)
    assert doc is not None, fel
    assert "Vanligt fel" not in exam_latex.render_bedomning(doc)


def test_prompterna_ber_om_korta_rader_och_ingen_notrad():
    """Samma dom, i prompten: ingen extra rad efter trappan, och radernas
    språk ska bli «otroligt mycket kortare så att det blir mycket tydligare
    för mig som lärare att läsa dem»."""
    assert "Vanligt fel" not in exam_gen.INSTRUCTION
    assert "Vanligt fel" not in exam_gen.FALLGROPAR
    underlag = exam_gen.bedomningsunderlag(_exam())[0]
    prompt = exam_gen.build_bedomning_prompt(underlag)
    # Kassettregeln: markörfrasen står kvar, annars hittar fejk.py inget band.
    assert "bedömningsskrivare" in prompt
    assert "Vanligt fel" not in prompt
    # Trappraderna: ett tak i ord, inte «kort och konkret».
    assert "ÅTTA ord" in prompt
    # Kommentaren: EN mening, tolv ord, och exemplet håller den längden.
    assert "HÖGST TOLV ORD" in prompt
    assert "+1 C för potensen i täljaren, förenklar sedan inte." in prompt
    # Elevens papper kortas med en rad.
    assert "högst FEM rader" in prompt


def test_bedomningssignal_faller_flera_poang_pa_samma_rad():
    """«+3 E för båda nollställena» är en rad för tre poäng — och då syns inte
    var gränsen mellan 1 p, 2 p och 3 p går."""
    exam = _exam()
    exam["uppgifter"][0]["bedomning"] = "+3 E för båda nollställena."
    fel = exam_gen.bedomningssignaler(exam)
    assert [f["code"] for f in fel] == ["bedomningssignal"]
    assert "EN rad per poäng" in fel[0]["message"]


def test_bedomningssignal_faller_niva_som_sager_emot_poangen():
    """Poängtripplen är den som räknas till betyget; en C-uppgift vars trappa
    delar ut E-poäng säger emot sitt eget dokument."""
    exam = _exam()
    exam["uppgifter"][2]["bedomning"] = "+1 E a\n+1 E b\n+1 E c"   # är [1,1,1]
    fel = exam_gen.bedomningssignaler(exam)
    assert [f["code"] for f in fel] == ["bedomningssignal"]
    assert "trappan delar ut 3/0/0" in fel[0]["message"]


def test_bedomningssignal_slapper_igenom_np_formen():
    """Den kanoniska fixturen ÄR skriven i NP:s form — vakten ska tiga."""
    assert exam_gen.bedomningssignaler(_exam()) == []
    assert exam_gen.bedomningssignaler(_exam_med_deluppgifter()) == []


def test_bedomningssignal_faller_elevlosningar_som_hoppar_over_steg():
    """Lärarens fynd: «0 av 3», sedan 2 och 3 — ettpoängsteget saknas, och det
    är just den gränsen som är svår att dra.

    Stegen som ska täckas är 0 … tak−1: full pott står som FACITRADEN överst i
    tabellen (lärarens beställning 2026-08-23) och skrivs inte en gång till."""
    exam = _exam()
    exam["uppgifter"][2]["elevlosningar"] = [
        {"etikett": "0 p",
         "partier": [{"rader": ["fel"], "poang": [0, 0, 0], "dom": "d"}]},
        {"etikett": "2 p",
         "partier": [{"rader": ["halvt"], "poang": [1, 1, 0], "dom": "d"}]},
    ]
    fel = exam_gen.bedomningssignaler(exam)
    assert [f["code"] for f in fel] == ["bedomningssignal"]
    assert "täcka stegen [0, 1, 2]" in fel[0]["message"]
    # …och med ettpoängssteget ifyllt tiger vakten.
    exam["uppgifter"][2]["elevlosningar"].insert(1, {
        "etikett": "1 p",
        "partier": [{"rader": ["ansats"], "poang": [1, 0, 0], "dom": "d"}]})
    doc, schemafel = exam_spec.validate_exam_json(exam)
    assert doc is not None and schemafel == []
    assert exam_gen.bedomningssignaler(exam) == []


def test_bedomningssignal_tal_ett_gammalt_pappers_fullpottslosning():
    """Papper som redan ligger i basen har full pott som ÖVERSTA lösning —
    formen före 2026-08-23. De ska inte börja varna för det: en extra lösning
    på taket passerar, ett hoppat steg gör det inte."""
    exam = _exam()
    exam["uppgifter"][2]["elevlosningar"] = [
        {"etikett": "Elevlösning 1",
         "partier": [{"rader": ["fel"], "poang": [0, 0, 0], "dom": "d"}]},
        {"etikett": "Elevlösning 2",
         "partier": [{"rader": ["ansats"], "poang": [1, 0, 0], "dom": "d"}]},
        {"etikett": "Elevlösning 3",
         "partier": [{"rader": ["halvt"], "poang": [1, 1, 0], "dom": "d"}]},
        {"etikett": "Elevlösning 4",
         "partier": [{"rader": ["helt"], "poang": [1, 1, 1], "dom": "d"}]},
    ]
    assert exam_gen.bedomningssignaler(exam) == []


def test_bedomningssignalen_kostar_aldrig_en_runda():
    """Samma regel som tal- och nivåsignalerna: en varning om formen får
    aldrig i sig själv kosta läraren en omskrivning."""
    trasigt = _exam()
    trasigt["uppgifter"][0]["bedomning"] = "+3 E för båda nollställena."
    # Tre anrop: generering + de två blinda domarna (som inte fäller något).
    # Därtill bedömningspassets ETT anrop per uppgift — det skriver, det
    # reparerar inte, och kostar därför ingen RUNDA. Stubbens «{}» går inte att
    # tolka som ett bedömningssvar, så passet lämnar uppgifterna orörda
    # (fail-open) och varningen står kvar.
    llm, calls = _stub_llm([json.dumps(trasigt), "{}", "{}"])
    res = exam_gen.generate_exam("Ma2b", "SA23", [], model="m", llm=llm)
    assert res["rounds"] == 1
    assert len(calls) == 3 + len(trasigt["uppgifter"])
    assert sum("bedömningsskrivare" in c["prompt"] for c in calls) == 7
    assert [e["code"] for e in res["errors"]] == ["bedomningssignal"]


def test_bedomningen_pa_pappret_ar_en_trappa():
    """PDF:en (bedomning.tex.j2) sätter kriteriet till vänster och nivån i
    högermarginalen, en rad per poäng — nationella provets egen form."""
    doc, _fel = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_bedomning(doc)
    assert tex.count(r"\bedsteg{") == exam_spec.poangsummor(doc)["total"]
    assert r"\bedsteg{anger det ena nollstället}{+1 E}" in tex


def test_facitets_typografi_ar_fragan_storre_och_svaret_mindre():
    """Lärarens dom 2026-08-23: uppgiftstexten kursiv och något större,
    lösningen mindre i rak stil. Skärmen (losning.css) och pappret ska säga
    samma sak — PDF:en är skärmtrogen."""
    doc, _fel = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_bedomning(doc)
    assert r"{\itshape Ange nollställena" in tex
    assert r"{\small\itshape Ange nollställena" not in tex
    # Lösningen ligger i bedömningstabellens vänsterspalt och sätts i \small.
    assert r"{\small \(x = 1\) och \(x = -3\).}" in tex
    css = (Path(__file__).resolve().parent.parent / "app" / "web" / "ui"
           / "losning.css").read_text(encoding="utf-8")
    assert '[data-form="lo-b"] .prtext' in css and "font-style:italic" in css


def test_bedomningens_sidhuvud_bar_riktiga_tecken():
    """Jinjas lexer tolkar strängliteraler som Python: '\\textemdash{}' i ett
    ((* set *)) blir TAB + «extemdash{}». Det stod på lärarens skarpa papper —
    «Matematik 1c extemdash Potenser extperiodcentered Bedömningsanvisning»."""
    doc, _fel = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_bedomning(doc)
    assert "extemdash" not in tex.replace(r"\textemdash", "")
    assert "extperiodcentered" not in tex.replace(r"\textperiodcentered", "")
    assert r"\textperiodcentered{} Bedömningsanvisning" in tex


def test_elevraderna_bar_steg_poang_och_skal_i_pdfen():
    """Lärarens beställning 2026-08-23: en rad per lägre poängsteg, med de
    trappsteg lösningen FICK i högerspalten och det korta skälet under dem.
    Nollpoängsraden säger «Inga poäng» och sedan varför."""
    exam = _exam()
    exam["uppgifter"][2]["elevlosningar"] = [
        {"etikett": "0 p",
         "partier": [{"rader": ["fel"], "poang": [0, 0, 0],
                      "dom": "ingen ansats"}]},
        {"etikett": "1 p",
         "partier": [{"rader": ["ansats"], "poang": [1, 0, 0],
                      "dom": "tecknar men löser inte"}]},
    ]
    doc, _fel = exam_spec.validate_exam_json(exam)
    tex = exam_latex.render_bedomning(doc)
    assert r"\bedrad{0 p}" in tex and r"\bedrad{1 p}" in tex
    assert r"{\small\bfseries Inga poäng}" in tex
    # Nollradens kommentar versaliseras: den fortsatte förut efter «Inga
    # poäng.», och det ledet ströks (exam_latex._utan_rubriken).
    assert "Ingen ansats" in tex and "tecknar men löser inte" in tex
    # Ettpoängsraden fick uppgiftens FÖRSTA E-rad — det räknas ur trappan
    # (exam_latex._fickrader), aldrig av modellen en gång till. E-raden står
    # alltså två gånger på uppgiften: hel i facitraden, och en gång till i
    # 1 p-radens högerspalt. C- och A-raderna bara en gång, i facit.
    assert tex.count(r"\bedsteg{ansats}{+1 E}") == 2
    assert tex.count(r"\bedsteg{korrekt kvadratkomplettering}{+1 C}") == 1
    assert tex.count(r"\bedsteg{generell metod}{+1 A}") == 1


# ══════════════════════════════════════════════════════════════════════
# BEDÖMNINGSPASSET (lärarens beställning 2026-08-23)
#
# Ett anrop per uppgift, körda parallellt, fail-open per uppgift, och det som
# skrivs prövas mot samma deterministiska mått som vakten. Det är fyra löften,
# och vart och ett har sitt test här nedanför.
# ══════════════════════════════════════════════════════════════════════

def _bedsvar(rader_per_enhet, steg):
    """Ett svar som passets schema tillåter: trappan per enhet, och en
    elevlösning per poängsteg."""
    return json.dumps({
        "bedomning": [{"enhet": n, "rader": r}
                      for n, r in rader_per_enhet.items()],
        "elevlosningar": [
            {"poang": list(p), "rader": [f"rad för {sum(p)} p"],
             "kommentar": f"kommentar för {sum(p)} p"} for p in steg],
    }, ensure_ascii=False)


def test_bedomningspasset_skriver_ett_papper_per_poangsteg():
    """Uppgiften är värd 3 poäng — då står facit överst och tre elevrader
    under: 0 p, 1 p och 2 p. Full pott skrivs aldrig som elevlösning."""
    exam = {"uppgifter": [{"poang": [1, 1, 1], "text": "t", "losning": "l",
                           "bedomning": "+1 E a\n+1 C b\n+1 A c"}]}
    svar = _bedsvar({"": ["+1 E tecknar sambandet",
                          "+1 C räknar ut värdet",
                          "+1 A motiverar svaret"]},
                    [(0, 0, 0), (1, 0, 0), (1, 1, 0)])
    llm, calls = _stub_llm([svar])
    assert exam_gen.bedomningspass(exam, model="m", llm=llm) == 1
    assert len(calls) == 1
    u = exam["uppgifter"][0]
    assert u["bedomning"] == ("+1 E tecknar sambandet\n+1 C räknar ut värdet\n"
                              "+1 A motiverar svaret")
    assert [e["etikett"] for e in u["elevlosningar"]] == ["0 p", "1 p", "2 p"]
    assert u["elevlosningar"][1]["partier"][0]["poang"] == [1, 0, 0]
    assert u["elevlosningar"][1]["partier"][0]["dom"] == "kommentar för 1 p"
    # …och dokumentet ska gå igenom schemat och vakten som det står.
    assert exam_gen.bedomningssignaler(exam) == []


def test_bedomningspasset_slanger_en_trappa_som_tappar_ett_poangsteg():
    """Passet SKRIVER i dokumentet, så det som skrivs mäts med vaktens eget
    mått: en rad per poäng, och nivåerna uppgiftens egna. En «enklare» trappa
    som blivit en rad kortare är ingen förbättring."""
    exam = {"uppgifter": [{"poang": [0, 2, 0], "text": "t", "losning": "l",
                           "bedomning": "+1 C först\n+1 C sedan"}]}
    llm, _c = _stub_llm([_bedsvar({"": ["+2 C hela lösningen"]},
                                  [(0, 0, 0), (0, 1, 0)])])
    exam_gen.bedomningspass(exam, model="m", llm=llm)
    # Trappan står kvar…
    assert exam["uppgifter"][0]["bedomning"] == "+1 C först\n+1 C sedan"
    # …men elevlösningarna dög och skrevs ändå. De två prövas var för sig.
    assert [e["etikett"] for e in exam["uppgifter"][0]["elevlosningar"]] == \
        ["0 p", "1 p"]


def test_bedomningspasset_ar_fail_open_per_uppgift():
    """Faller ett anrop lämnas DEN uppgiften utan exempel och provet levereras.
    Grannuppgifterna får aldrig veta om det."""
    exam = {"uppgifter": [
        {"poang": [1, 0, 0], "text": "a", "losning": "l", "bedomning": "+1 E a"},
        {"poang": [1, 0, 0], "text": "b", "losning": "l", "bedomning": "+1 E b"},
    ]}
    ok = _bedsvar({"": ["+1 E rätt svar"]}, [(0, 0, 0)])

    def llm(model, prompt, **kw):
        if '"uppgift": "a"' in prompt:
            raise RuntimeError("kvoten slut")
        return ok

    assert exam_gen.bedomningspass(exam, model="m", llm=llm) == 1
    assert "elevlosningar" not in exam["uppgifter"][0]
    assert exam["uppgifter"][0]["bedomning"] == "+1 E a"
    assert exam["uppgifter"][1]["elevlosningar"][0]["etikett"] == "0 p"


def test_bedomningspasset_kor_anropen_parallellt():
    """Sex uppgifter, sex trådar: väggtiden ska vara ETT anrop lång, inte sex.
    Utan parallellitet lade passet minuter till ett prov som redan tar 7–10."""
    import threading
    exam = {"uppgifter": [{"poang": [1, 0, 0], "text": f"u{i}", "losning": "l",
                           "bedomning": "+1 E a"} for i in range(6)]}
    samtidiga, mest, las = 0, 0, threading.Lock()
    grind = threading.Barrier(6, timeout=10)

    def llm(model, prompt, **kw):
        nonlocal samtidiga, mest
        with las:
            samtidiga += 1
            mest = max(mest, samtidiga)
        # Barriären är beviset: släpper den igenom stod alla sex anropen inne
        # samtidigt. Körs de i rad slår timeouten till och testet faller.
        grind.wait()
        with las:
            samtidiga -= 1
        return _bedsvar({"": ["+1 E rätt svar"]}, [(0, 0, 0)])

    assert exam_gen.bedomningspass(exam, model="m", llm=llm) == 6
    assert mest == 6


def test_avbryt_stoppar_bedomningspasset():
    """Loggraden är livstecknet strömmen avbryter vid (app/web/sse.py). Kastar
    den ska passet sluta — inte köra klart tolv anrop åt en lärare som gått."""
    class Borta(Exception):
        pass

    exam = {"uppgifter": [{"poang": [1, 0, 0], "text": f"u{i}", "losning": "l",
                           "bedomning": "+1 E a"} for i in range(8)]}
    llm, calls = _stub_llm([_bedsvar({"": ["+1 E rätt svar"]}, [(0, 0, 0)])])
    rader = []

    def logg(m):
        rader.append(m)
        if len(rader) >= 2:
            raise Borta

    with pytest.raises(Borta):
        exam_gen.bedomningspass(exam, model="m", llm=llm, log_cb=logg)
    # Trådtaket är sex, så högst sex anrop kan ha startat innan den andra
    # loggraden — aldrig alla åtta.
    assert len(calls) <= exam_gen.BEDOMNING_TRADAR
    # Det som HANN bli skrivet ligger kvar: raden kommer efter skrivningen.
    assert any("elevlosningar" in u for u in exam["uppgifter"])


def test_bedomningspassets_loggrad_bar_siffrorna_matarens_regex_laser():
    """fraga.js flyttar mätaren på «uppgift n av N» i loggraden (f353cbd).
    Raden räknar FÄRDIGA anrop: de går parallellt och blir klara i den ordning
    modellen råkar svara, så uppgiftsnumret hade hoppat fram och tillbaka."""
    exam = {"uppgifter": [{"poang": [1, 0, 0], "text": f"u{i}", "losning": "l",
                           "bedomning": "+1 E a"} for i in range(3)]}
    llm, _c = _stub_llm([_bedsvar({"": ["+1 E rätt svar"]}, [(0, 0, 0)])])
    rader = []
    exam_gen.bedomningspass(exam, model="m", llm=llm, log_cb=rader.append)
    assert all(r.startswith("Skriver elevexempel (uppgift ") for r in rader)
    siffror = [re.search(r"uppgift (\d+) av (\d+)", r).groups() for r in rader]
    assert siffror[0] == ("1", "3") and siffror[-1] == ("3", "3")


def test_bedomningspasset_skriver_trappan_per_deluppgift():
    """Elevlösningarna sitter på UPPGIFTEN medan trappan sitter på varje
    poängbärande enhet — ett anrop ser därför hela uppgiften och skriver
    tillbaka en trappa per deluppgift."""
    exam = {"uppgifter": [{"poang": [0, 0, 0], "text": "stam", "losning": "",
                           "bedomning": "", "deluppgifter": [
                               {"poang": [1, 0, 0], "text": "a", "losning": "l",
                                "bedomning": "+1 E gammalt a"},
                               {"poang": [0, 1, 0], "text": "b", "losning": "l",
                                "bedomning": "+1 C gammalt b"}]}]}
    llm, _c = _stub_llm([_bedsvar({"a": ["+1 E nytt a"], "b": ["+1 C nytt b"]},
                                  [(0, 0, 0), (1, 0, 0)])])
    exam_gen.bedomningspass(exam, model="m", llm=llm)
    delar = exam["uppgifter"][0]["deluppgifter"]
    assert delar[0]["bedomning"] == "+1 E nytt a"
    assert delar[1]["bedomning"] == "+1 C nytt b"
    assert [e["etikett"] for e in exam["uppgifter"][0]["elevlosningar"]] == \
        ["0 p", "1 p"]


def test_andrade_uppgifter_ser_bara_det_bedomningen_bryr_sig_om():
    """Omskrivningen ska bara betala för det som ändrades. En bild som bytts
    ändrar ingen bedömning; en poäng, en text, ett facit eller en trappa gör
    det."""
    fore = _exam()
    assert exam_gen.andrade_uppgifter(fore, _exam()) == []
    efter = _exam()
    efter["uppgifter"][3]["losning"] = "något annat"
    assert exam_gen.andrade_uppgifter(fore, efter) == [4]
    orort = _exam()
    orort["uppgifter"][1]["bild"] = 2
    assert exam_gen.andrade_uppgifter(fore, orort) == []


def test_elevlosningar_far_vara_en_men_aldrig_noll():
    """En enpoängsuppgift har exakt ETT lägre poängsteg. Kravet på två gjorde
    varje flervalsfråga ogiltig; noll är däremot inget fält alls."""
    exam = _exam()
    exam["uppgifter"][1]["elevlosningar"] = [
        {"etikett": "0 p", "partier": [{"rader": ["fel"], "poang": [0, 0, 0],
                                        "dom": "d"}]}]
    doc, fel = exam_spec.validate_exam_json(exam)
    # Uppgift 2 är värd två poäng, så vakten VILL ha 0 p och 1 p — men schemat
    # släpper igenom en enda lösning, och vakten är bara en varning.
    assert doc is not None and fel == []
    exam["uppgifter"][1]["elevlosningar"] = []
    doc, fel = exam_spec.validate_exam_json(exam)
    assert doc is None and "minst" in fel[0]["message"]


def test_elevlosningar_ryms_till_atta_steg():
    """Taket var fyra när lösningarna var illustrationer. Nu är de en rad var i
    en tabell, och en uppgift värd sex poäng har sex lägre steg."""
    exam = _exam()
    exam["uppgifter"][2]["elevlosningar"] = [
        {"etikett": f"{i} p",
         "partier": [{"rader": ["x"], "poang": [min(i, 1), max(i - 1, 0), 0],
                      "dom": "d"}]}
        for i in range(3)]
    doc, fel = exam_spec.validate_exam_json(exam)
    assert doc is not None and fel == []
    assert exam_spec.ExamItem.model_fields["elevlosningar"].metadata[0].max_length == 8


def test_ts1_tecknen_satts_alltid_magert_och_uppratt():
    """TS1 har en fontfil per grad OCH snitt, och den buntade Tectonic-cachen
    bär bara den magra upprätta. Ett gradtecken i en kursiv uppgiftstext fällde
    hela bedömningsanvisningen på «Font TS1/lmr/m/it/12 not loadable» —
    lärarens prov fick sin PDF, hennes anvisning ingen.

    Vakten sitter i escapningen och inte i preamblen: ett försök att linda om
    \\textdegree med \\let + \\renewcommand gick i loop (LaTeX-symboler i en
    annan kodning anropar sig själva en gång till efter \\UseTextSymbol) och
    sprängde TeX:s save stack mitt i seedningen."""
    exam = _exam()
    exam["uppgifter"][0]["text"] = "Kaffet håller 50 °C ± 2 °C. Bestäm tiden."
    doc, fel = exam_spec.validate_exam_json(exam)
    assert doc is not None and fel == []
    tex = exam_latex.render_bedomning(doc)
    # Uppgiftstexten sätts KURSIVT i anvisningen — gradtecknet ska ändå be om
    # ts1-lmr och inte ts1-lmri.
    assert r"\itshape Kaffet håller 50 {\normalfont\textdegree}C" in tex
    # Modellens och lärarens egna tecken går ALLTID genom escapningen, och
    # där sitter vakten — oavsett var på pappret texten sedan hamnar.
    for tecken, kommando in (("°", r"\textdegree"), ("±", r"\textpm"),
                             ("×", r"\texttimes"), ("µ", r"\textmu"),
                             ("·", r"\textperiodcentered"), ("€", r"\texteuro")):
        assert exam_latex.escape_mixed(f"x {tecken} y") == \
            "x {\\normalfont" + kommando + "} y"
    # MALLENS EGNA tecken står i känd kontext och behöver ingen vakt: två
    # \textperiodcentered står i sidhuvudet och i rubriken, båda i mager
    # upprätt stil. Bedömningstabellens etikett är däremot FET och bär vakten
    # själv — den fällde ts1-lmbx10 första gången.
    assert tex.count(r"\textperiodcentered") == 2 + tex.count(
        r"{\normalfont\textperiodcentered} full pott")


def test_nollraden_upprepar_inte_rubriken_i_pdfen():
    """«Inga poäng» stod två gånger på lärarens papper: en gång som rubrik i
    högerspalten och en gång till som kommentarens första två ord, för det är
    så modellen skriver en hel mening. Rubriken bär den, kommentaren säger
    varför."""
    exam = _exam()
    exam["uppgifter"][2]["elevlosningar"] = [
        {"etikett": "0 p",
         "partier": [{"rader": ["fel"], "poang": [0, 0, 0],
                      "dom": "Inga poäng. Svaret är rätt av fel skäl."}]},
        {"etikett": "1 p",
         "partier": [{"rader": ["halvt"], "poang": [1, 0, 0],
                      "dom": "Får +1 E, men stannar där."}]},
    ]
    doc, _fel = exam_spec.validate_exam_json(exam)
    tex = exam_latex.render_bedomning(doc)
    assert tex.count("Inga poäng") == 1
    assert "Svaret är rätt av fel skäl." in tex
    # Bara nollraden strippas — en poängsatt rad rörs inte.
    assert "Får +1 E, men stannar där." in tex


def test_nollraden_utan_egen_kommentar_far_ingen_tom_rad():
    """Skrev modellen bara «Inga poäng» är hela kommentaren rubriken, och då
    ska ingenting stå under den."""
    exam = _exam()
    exam["uppgifter"][2]["elevlosningar"] = [
        {"etikett": "0 p",
         "partier": [{"rader": ["fel"], "poang": [0, 0, 0],
                      "dom": "Inga poäng."}]}]
    doc, _fel = exam_spec.validate_exam_json(exam)
    tex = exam_latex.render_bedomning(doc)
    assert tex.count("Inga poäng") == 1
    assert r"{\small\bfseries Inga poäng}\par " in tex


def test_trappstegets_niva_star_forst_pa_fast_position():
    """Nivåmärket låg förut sist på raden via \\hfill — nationella provets egen
    sättning, som fungerar när kriteriet har hela sidbredden. I
    bedömningstabellens högerspalt (41 % av satsytan) bröts ett långt kriterium
    över fyra rader och «+1 E» hamnade mitt inne i textflödet på den sista.

    Nu står nivån FÖRST i en egen smal spalt med hängande indrag, precis som på
    skärmen (losning.css .lotrappa är en grid med nivån i första spalten)."""
    preamble = (Path(__file__).resolve().parent.parent / "app" / "templates"
                / "_preamble.tex.j2").read_text(encoding="utf-8")
    bit = preamble[preamble.index(r"\newcommand{\bedsteg}"):]
    bit = bit[:bit.index("\n\n")]
    assert r"\makebox[\bednivabredd]" in bit and r"\hangindent" in bit
    assert r"\hfill" not in bit, "nivån flyter fortfarande med texten"
    # Argumentordningen är oförändrad: \bedsteg{kriterium}{nivå}.
    doc, _fel = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_bedomning(doc)
    assert r"\bedsteg{anger det ena nollstället}{+1 E}" in tex
    # En rad per poäng även när kriterierna är långa — raderna är egna stycken
    # och bryts som löptext inne i sin spalt.
    assert tex.count(r"\bedsteg{") == exam_spec.poangsummor(doc)["total"]
