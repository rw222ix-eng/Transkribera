"""Nivåkalibreringen (Del C): rubriken, domaren, signalerna och bokens skala.

Ingen modell körs här. Det som prövas är allt runt anropet — och de tre ställen
där nivåarbetet kan gå sönder tyst:

* rubriken är DATA, och data ruttnar. En typ som saknar en nivåbeskrivning gör
  promptblocket tystare utan att något går sönder, så det mäts här.
* domaren får aldrig kunna underkänna ett prov som är rätt. Ett obegripligt
  svar, ett svar om uppgifter som inte finns, ett «oklart» — allt ska passera.
* signalerna är RÄKNADE i nationella prov (app/niva_rubrik.ANALYSERADE_PROV).
  En signal som fäller en riktig NP-uppgift är värdelös, och två sådana ströks
  redan under arbetet; testerna nedan håller de kvarvarande ärliga.
"""
from __future__ import annotations

import json

import pytest

from app import bok, bok_ocr, db, exam_gen, exam_spec, niva_rubrik


# ─────────────────────────────────────────────────────── rubriken (C1) ────

def test_rubriken_sager_vad_den_vilar_pa():
    """En rubrik utan källor är en åsikt. Fältet är tomt tills proven lästs,
    och det här testet är skälet att det inte går att glömma."""
    assert niva_rubrik.ANALYSERADE_PROV, \
        "rubriken saknar underlag — fyll ANALYSERADE_PROV eller märk den som hypotes"


def test_alla_nivaer_beskrivs_generellt():
    for niva in niva_rubrik.NIVAER:
        text = niva_rubrik.RUBRIK_GENERELL[niva]
        assert text.strip() and text.startswith(niva)


def test_varje_uppgiftstyp_har_alla_tre_nivaerna():
    """Skelettet låser typen per uppgift. Saknas en nivå för den typen faller
    promptblocket tillbaka på det generella — tystare, utan att något syns."""
    typer = set(exam_spec.Uppgiftstyp.__args__)
    assert set(niva_rubrik.RUBRIK_PER_TYP) == typer
    for typ, krav in niva_rubrik.RUBRIK_PER_TYP.items():
        assert set(krav) == set(niva_rubrik.NIVAER), typ
        assert all(v.strip() for v in krav.values()), typ


def test_varje_formaga_har_en_stege_och_K_saknar_E():
    """K:s lucka är inte ett hål utan en mätning: kommunikationspoäng
    förekommer noll gånger på E-nivå i alla fyra proven. Skulle någon fylla i
    raden «för fullständighetens skull» ska det här testet stoppa det."""
    assert set(niva_rubrik.RUBRIK_PER_FORMAGA) == set(exam_spec.FORMAGA_NAMN)
    for f, krav in niva_rubrik.RUBRIK_PER_FORMAGA.items():
        vantade = {"C", "A"} if f == "K" else set(niva_rubrik.NIVAER)
        assert set(krav) == vantade, f
        assert all(v.strip() for v in krav.values()), f


def test_ankarna_ar_hela_och_taecker_varje_niva():
    typer = set(exam_spec.Uppgiftstyp.__args__)
    for a in niva_rubrik.ANKARE:
        assert set(a) == {"typ", "niva", "text", "varfor"}
        assert a["typ"] in typer and a["niva"] in niva_rubrik.NIVAER
        assert a["text"].strip() and a["varfor"].strip()
    for niva in niva_rubrik.NIVAER:
        assert [a for a in niva_rubrik.ANKARE if a["niva"] == niva], niva
    # Varje typ ska ha minst ett par som visar en gräns — ett ensamt ankare
    # säger inget om vad som skiljer nivåerna åt.
    for typ in typer:
        nivaer = {a["niva"] for a in niva_rubrik.ANKARE if a["typ"] == typ}
        assert len(nivaer) >= 2, typ


def test_ankarurvalet_foljer_typerna_och_faller_tillbaka():
    valda = niva_rubrik.ankare(["resonemang"], per_niva=1)
    assert valda and all(a["typ"] == "resonemang" for a in valda)
    # En typ som inte finns ska ge ankare ändå — fel typ styr bättre än inget.
    assert niva_rubrik.ankare(["finns-inte"])


def test_promptblocket_bar_rubrik_steg_och_ankare():
    block = niva_rubrik.build_niva_block(["rutin"], ["P"])
    assert "NIVÅKRAV" in block
    for niva in niva_rubrik.NIVAER:
        assert niva_rubrik.RUBRIK_GENERELL[niva] in block
    assert niva_rubrik.STEGET_UPP["E→C"] in block
    assert niva_rubrik.RUBRIK_PER_TYP["rutin"]["C"] in block
    assert niva_rubrik.RUBRIK_PER_FORMAGA["P"]["C"] in block
    # Bara den begärda typen och förmågan — blocket ska inte svälla.
    assert niva_rubrik.RUBRIK_PER_TYP["resonemang"]["C"] not in block
    assert niva_rubrik.RUBRIK_PER_FORMAGA["M"]["C"] not in block


# ────────────────────────────────────────────────────── domaren (C4) ──────

def _uppg(nr: int, poang, **kw):
    return {"del": "C", "formaga": kw.get("formaga", "P"),
            "typ": kw.get("typ", "redovisning"), "poang": list(poang),
            "text": kw.get("text", f"Uppgift {nr}."),
            "losning": kw.get("losning", "Lösning."),
            "bedomning": kw.get("bedomning", f"+1 E för uppgift {nr}.")}


def _exam(uppgifter):
    return {"titel": "Prov", "kurs": "Ma2c", "hjalpmedel": "Formelblad",
            "uppgifter": uppgifter}


def test_domarenheterna_numreras_som_uppgiftsplanen():
    exam = _exam([
        _uppg(1, (1, 0, 0)),
        {"del": "C", "formaga": "PL", "typ": "problem", "poang": [0, 0, 0],
         "text": "Stam.", "losning": "", "bedomning": "",
         "deluppgifter": [
             {"poang": [1, 0, 0], "text": "a-frågan.", "losning": "L",
              "bedomning": "B"},
             {"poang": [0, 1, 1], "text": "b-frågan.", "losning": "L",
              "bedomning": "B", "typ": "resonemang"}]},
    ])
    enheter = exam_gen.domarenheter(exam)
    assert [e["nr"] for e in enheter] == ["1", "2a", "2b"]
    assert [e["niva"] for e in enheter] == ["E", "E", "A"]
    # Deluppgiften ärver förälderns förmåga men har egen typ.
    assert enheter[2]["formaga"] == "PL" and enheter[2]["typ"] == "resonemang"
    # Föräldern med [0,0,0] är ingen egen enhet — poängen ligger på barnen.
    assert "2" not in [e["nr"] for e in enheter]


def test_domaren_ser_aldrig_facit():
    """Bedömningsanvisningen säger «+1 C fullständig lösning». Kommer den med
    är domen inte blind utan en avskrift."""
    exam = _exam([_uppg(1, (0, 2, 0), bedomning="+1 C fullständig lösning")])
    enheter = exam_gen.domarenheter(exam)
    prompt = exam_gen.build_domar_prompt(enheter)
    assert "poang" not in prompt and "+1 C" not in prompt
    assert "bedomning" not in prompt
    assert "Uppgift 1." in prompt


def test_avvikelse_bara_vid_riktig_oenighet():
    enheter = exam_gen.domarenheter(_exam([
        _uppg(1, (0, 2, 0)), _uppg(2, (0, 2, 0)),
        _uppg(3, (0, 2, 0)), _uppg(4, (0, 2, 0))]))
    domar = {
        "1": {"niva": "C", "motivering": "stämmer"},        # enig
        "2": {"niva": "OKLART", "motivering": "gränsfall"},  # toleransen
        "3": {"niva": "E", "motivering": "rutin"},           # fäller
        # uppgift 4 nämns inte alls → tystnad tolkas aldrig
    }
    avv = exam_gen.avvikelser(enheter, domar)
    assert [a["path"] for a in avv] == ["uppgift 3"]
    assert "poängsatt C men bedöms som E" in avv[0]["message"]
    # Åtgärden ska stå i felet, inte bara konstaterandet.
    assert niva_rubrik.STEGET_UPP["E→C"] in avv[0]["message"]


def test_domarsvar_som_inte_gar_att_tolka_faller_ingenting():
    """En trasig kontroll får aldrig underkänna ett prov som är rätt."""
    assert exam_gen._parse_domar("inte json alls") == {}
    assert exam_gen._parse_domar('{"domar": "fel form"}') == {}
    enheter = exam_gen.domarenheter(_exam([_uppg(1, (0, 2, 0))]))
    assert exam_gen.avvikelser(enheter, exam_gen._parse_domar("trasigt")) == []


def test_domaren_kapar_langa_fellistor():
    n = exam_gen.MAX_DOMAR_PROBLEM + 3
    enheter = exam_gen.domarenheter(
        _exam([_uppg(i, (0, 0, 1)) for i in range(1, n + 1)]))
    domar = {str(i): {"niva": "E", "motivering": ""} for i in range(1, n + 1)}
    assert len(exam_gen.avvikelser(enheter, domar)) == exam_gen.MAX_DOMAR_PROBLEM


def test_doma_nivaer_kor_ett_anrop_och_far_skalan_med_sig():
    anrop = []

    def llm(model, prompt, **kw):
        anrop.append(prompt)
        return json.dumps({"domar": [{"nr": "1", "niva": "E",
                                      "motivering": "ren rutin"}]})

    avv = exam_gen.doma_nivaer(_exam([_uppg(1, (0, 0, 2))]), model="m", llm=llm,
                               skala="SKALAN SOM GÄLLDE")
    assert len(anrop) == 1 and "SKALAN SOM GÄLLDE" in anrop[0]
    assert len(avv) == 1 and avv[0]["code"] == "niva"


def test_domaren_kors_inte_pa_ett_dokument_utan_poang():
    anrop = []
    exam_gen.doma_nivaer(_exam([]), model="m",
                         llm=lambda *a, **k: anrop.append(1) or "{}")
    assert anrop == []


# ─────────────────────────────────────────── nivåpasset i genereringen ────

def _stub(svar: list[str]):
    anrop = []

    def llm(model, prompt, **kw):
        anrop.append(prompt)
        return svar[min(len(anrop) - 1, len(svar) - 1)]

    return llm, anrop


def _giltigt_prov():
    """Ett litet arbetsblad som klarar profilens balansregler — kollat av
    test_fixturen_ar_verkligen_giltig nedan, så att ett fel i FIXTUREN inte
    kan se ut som ett fel i domaren."""
    return _exam([
        {"del": None, "formaga": "B", "typ": "rutin", "poang": [2, 0, 0],
         "text": "Ange nollställena till $y = (x - 2)(x + 5)$.",
         "losning": "$x = 2$ och $x = -5$.", "bedomning": "+2 E."},
        {"del": None, "formaga": "P", "typ": "redovisning", "poang": [1, 1, 0],
         "text": "Lös ekvationen $x^2 - 9 = 0$.", "losning": "$x = \\pm 3$.",
         "bedomning": "+1 E, +1 C."},
    ])


def test_fixturen_ar_verkligen_giltig():
    doc, fel = exam_spec.validate_exam_json(_giltigt_prov(), "arbetsblad")
    assert doc is not None and fel == []


def test_domarrundan_lagger_sina_fynd_i_reparationsloopen():
    dom = json.dumps({"domar": [{"nr": "2", "niva": "E", "motivering": "rutin"}]})
    battre = json.dumps(_giltigt_prov())
    llm, anrop = _stub([json.dumps(_giltigt_prov()), dom, battre])
    res = exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m",
                                 antal=2, profil="arbetsblad", llm=llm)
    # generering, dom, reparation — domen kostar inte en runda, reparationen gör det
    assert len(anrop) == 3
    assert "poängsatt C men bedöms som E" in anrop[2]
    assert res["rounds"] == 2 and res["errors"] == []


def test_utan_avvikelser_kostar_domaren_ingen_reparation():
    dom = json.dumps({"domar": [{"nr": "1", "niva": "E", "motivering": ""},
                                {"nr": "2", "niva": "C", "motivering": ""}]})
    llm, anrop = _stub([json.dumps(_giltigt_prov()), dom])
    res = exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m",
                                 antal=2, profil="arbetsblad", llm=llm)
    assert len(anrop) == 2 and res["rounds"] == 1 and res["errors"] == []


def test_doma_false_stanger_av_hela_passet():
    llm, anrop = _stub([json.dumps(_giltigt_prov())])
    exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m", antal=2,
                           profil="arbetsblad", llm=llm, doma=False)
    assert len(anrop) == 1


def test_en_nivareparation_som_forstor_dokumentet_kastas():
    """Var provet rent före domaren och trasigt efter är omskrivningen en
    försämring. Då behålls det gamla och nivåfyndet visas som en varning."""
    dom = json.dumps({"domar": [{"nr": "2", "niva": "E", "motivering": "rutin"}]})
    trasigt = json.dumps(_exam([
        {"del": None, "formaga": "P", "typ": "rutin", "poang": [0, 0, 0],
         "text": "Tom.", "losning": "L", "bedomning": "B"}]))
    llm, _anrop = _stub([json.dumps(_giltigt_prov()), dom, trasigt])
    res = exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m",
                                 antal=2, profil="arbetsblad", llm=llm)
    assert res["exam"] == _giltigt_prov()
    assert [e["code"] for e in res["errors"]] == ["niva"]


# ──────────────────────────────────── deterministiska signaler (C4) ───────

def test_signal_kommunikationspoang_pa_e_niva():
    exam = _exam([_uppg(1, (1, 1, 0), formaga="K")])
    fel = exam_gen.nivasignaler(exam)
    assert [f["code"] for f in fel] == ["nivasignal"]
    assert "kommunikation" in fel[0]["message"]


def test_signal_visa_att_med_a_poang():
    exam = _exam([_uppg(1, (0, 0, 2), text="Visa att summan alltid är jämn.")])
    assert any("visa ett påstående" in f["message"]
               for f in exam_gen.nivasignaler(exam))


def test_signal_oppen_formulering_med_bara_e_poang():
    exam = _exam([_uppg(1, (2, 0, 0), text="Undersök om påståendet stämmer.")])
    assert any("utredning" in f["message"] for f in exam_gen.nivasignaler(exam))


@pytest.mark.parametrize("text,poang", [
    # Alla fyra är formulerade som riktiga NP-uppgifter på sin nivå. Fäller
    # någon signal här har den blivit för ivrig igen.
    ("Lös ekvationen $(2024 - x)^2 = 7(2024 - x)$.", (0, 0, 1)),
    ("Teckna funktionen $V$ som ger värdet efter $t$ år.", (0, 0, 1)),
    ("Visa att sambandet gäller för alla sådana tal.", (0, 2, 0)),
    ("Utred vilka värden riktningskoefficienten kan anta.", (0, 0, 2)),
])
def test_signalerna_faller_inte_riktiga_np_uppgifter(text, poang):
    assert exam_gen.nivasignaler(_exam([_uppg(1, poang, text=text)])) == []


# ─────────────────────────────────────────────── bokens nivåskala (C2) ────

def test_uppgiftsraderna_bar_bokens_egen_markering():
    ut = bok_ocr._uppgifter([
        {"nr": 1215, "niva": 1, "nivamarke": "a"},
        {"nr": "1216", "nivå": "3", "nivåmärke": "★★★"},
        {"nr": 1217},                       # omarkerad uppgift
        1218,                               # bara ett tal
    ])
    assert ut == [
        {"nr": 1215, "niva": 1, "nivamarke": "a"},
        {"nr": 1216, "niva": 3, "nivamarke": "★★★"},
        {"nr": 1217, "niva": None, "nivamarke": None},
        {"nr": 1218, "niva": None, "nivamarke": None},
    ]


def test_nivasystemet_rostas_fram_ur_sidorna():
    sidor = [{"nivasystem": "a, b, c där c är svårast"},
             {"nivasystem": "a, b, c där c är svårast"},
             {"nivasystem": "tre färgade rutor"},
             {"nivasystem": None}]
    assert bok.nivasystem(sidor) == "a, b, c där c är svårast"
    # Sidor lästa före Del C saknar fältet — tystnad är normalt, inte ett fel.
    assert bok.nivasystem([{"nivasystem": None}]) == ""
    assert bok.nivasystem([]) == ""


def _uppslag():
    return [{"nr": 1201, "niva": 1, "nivamarke": "a"},
            {"nr": 1202, "niva": 1, "nivamarke": "a"},
            {"nr": 1203, "niva": 1, "nivamarke": "a"},
            {"nr": 1210, "niva": 2, "nivamarke": "b"},
            {"nr": 1221, "niva": 3, "nivamarke": "c"}]


def test_bokblocket_ger_spann_och_exempel_for_arbetsbladet():
    block = bok.build_niva_block(
        {"namn": "Matematik 5000+ 2c"}, 184, 185,
        [{"nivasystem": "a, b, c där c är svårast"}], _uppslag(),
        profil="arbetsblad")
    assert "Matematik 5000+ 2c, s. 184–185" in block
    assert "a, b, c där c är svårast" in block
    assert "bokens beteckning: a" in block
    assert "spänna bokens nivåer 1–3" in block
    # Två exempel per nivå, inte alla fem uppgifterna.
    assert "1201, 1202" in block and "1203" not in block


def test_bokblocket_ar_golv_och_tak_for_gruppuppgiften():
    block = bok.build_niva_block({"namn": "Boken"}, 10, 11, [], _uppslag(),
                                 profil="gruppuppgift")
    assert "INGÅNG" in block and "FÖRDJUPNINGEN" in block
    assert "nivå 1" in block and "nivå 3" in block
    assert "spänna" not in block          # ingen trappa


def test_ett_uppslag_utan_nivaer_ger_inget_block():
    """En skala med en enda nivå säger inte vad svårare betyder. Tomt block →
    anroparen faller tillbaka på NP-rubriken."""
    assert bok.build_niva_block({"namn": "B"}, 1, 2, [], [], profil="arbetsblad") == ""
    bara_en = [{"nr": 1, "niva": 1, "nivamarke": "a"}]
    assert bok.build_niva_block({"namn": "B"}, 1, 2, [], bara_en,
                                profil="arbetsblad") == ""
    omarkerade = [{"nr": 1, "niva": None}, {"nr": 2, "niva": None}]
    assert bok.build_niva_block({"namn": "B"}, 1, 2, [], omarkerade,
                                profil="arbetsblad") == ""


def test_nivataggarna_overlever_databasen(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    try:
        b = db.create_bok(conn, namn="Boken", sidor=300)
        db.save_bok_sida(conn, b["id"], 184, nivasystem="a, b, c")
        db.save_bok_uppgifter(conn, b["id"], [
            {"nr": 1201, "sida": 184, "niva": 1, "nivamarke": "a"}])
        assert db.bok_sidor(conn, b["id"], 184, 184)[0]["nivasystem"] == "a, b, c"
        rad = db.bok_uppgifter(conn, b["id"], 184, 184)[0]
        assert rad["niva"] == 1 and rad["nivamarke"] == "a"
        # Textpasset skriver bara text — det får inte radera nivåsystemet.
        db.save_bok_sida(conn, b["id"], 184, text="sidans text")
        sida = db.bok_sidor(conn, b["id"], 184, 184)[0]
        assert sida["nivasystem"] == "a, b, c" and sida["text"] == "sidans text"
    finally:
        conn.close()


# ────────────────────────────────────────────── skalan in i prompten ──────

@pytest.mark.parametrize("profil", ["arbetsblad", "gruppuppgift"])
def test_utan_bokdorr_far_bladet_np_rubriken(profil):
    """Blocket utelämnas aldrig tyst. «Stigande svårighet» utan skala var
    precis det planen skrevs för."""
    p = exam_gen.build_prompt("Ma1a", "NA25", [], antal=4, profil=profil,
                              grupp={"elever": 3, "langd_min": 45,
                                     "redovisning": "muntligt"})
    assert "Ingen lärobok är vald" in p
    assert "NIVÅKRAV" in p
    # Uppdragsraden sa förut «rutin- och procedursuppgifter med stigande
    # svårighet» — svårare ÄN VAD? Den förankringslösa frasen är borta;
    # skalan står i stället i klartext.
    assert "med stigande svårighet" not in p


def test_med_bokdorr_vinner_bokens_skala():
    p = exam_gen.build_prompt("Ma1a", "NA25", [], antal=4, profil="arbetsblad",
                              boknivaer="BOKENS NIVÅSKALA — hittepå")
    assert "BOKENS NIVÅSKALA — hittepå" in p
    assert "Ingen lärobok är vald" not in p


def test_provet_far_np_rubriken_intill_uppgiftsplanen():
    """Poängen står i planen, kravet står i rubriken — de ska stå bredvid
    varandra, annars är siffran ett löfte utan innehåll."""
    p = exam_gen.build_prompt("Ma2c", "NA25", [], antal=8)
    assert "Uppgiftsplan" in p and "NIVÅKRAV" in p
    assert p.index("Uppgiftsplan") < p.index("NIVÅKRAV")


def test_provet_domas_mot_samma_skala_som_det_skrevs_mot():
    """Bedöms dokumentet mot en annan skala än den skrevs mot mäter domaren
    fel sak."""
    skeleton = exam_spec.balanced_skeleton(8)
    prompt = exam_gen.build_prompt("Ma2c", "NA25", [], antal=8,
                                   skeleton=skeleton)
    skala = exam_gen._skala("prov", "", skeleton)
    assert skala and skala in prompt


def test_bokens_skala_ar_ocksa_domarens(monkeypatch):
    skala = exam_gen._skala("arbetsblad", "BOKENS NIVÅSKALA — hittepå", None)
    assert skala == "BOKENS NIVÅSKALA — hittepå"
