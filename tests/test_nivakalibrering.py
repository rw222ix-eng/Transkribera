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
    # Varje prov som är MÄTT ska också stå som källa (och tvärtom vaktar
    # test_exam.test_np_fordelningen_ar_intern_konsistent). Läraren har fyra
    # kurser, och alla fyra ska ha minst ett läst prov — annars gäller rubriken
    # bevisligen inte den klass hon skriver provet till.
    kallor = " ".join(niva_rubrik.ANALYSERADE_PROV)
    for kurs in ("1a", "1c", "2a", "2c"):
        assert f"NpMa{kurs}" in kallor, kurs


def test_ingen_np_uppgift_aterges_i_koden():
    """Regeln som gör materialet lagligt att använda: ankaren är EGENSKRIVNA
    parafraser, aldrig provens egna uppgifter. Regeln kan inte kontrolleras
    maskinellt utan att proven läggs i repot (vilket vore samma brott), så det
    som vaktas här är att regeln STÅR — den som stryker meningen ska behöva
    stryka det här testet också, och då syns beslutet i diffen."""
    doc = niva_rubrik.__doc__ or ""
    assert "EGENSKRIVNA parafraser" in doc
    assert "Ingen NP-uppgift återges" in doc


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
        assert set(a) == {"kurs", "typ", "niva", "text", "varfor"}
        assert a["kurs"] in {"1", "2"}
        assert a["typ"] in typer and a["niva"] in niva_rubrik.NIVAER
        assert a["text"].strip() and a["varfor"].strip()
    for niva in niva_rubrik.NIVAER:
        assert [a for a in niva_rubrik.ANKARE if a["niva"] == niva], niva
    # Varje typ ska ha minst ett par som visar en gräns — ett ensamt ankare
    # säger inget om vad som skiljer nivåerna åt.
    for typ in typer:
        nivaer = {a["niva"] for a in niva_rubrik.ANKARE if a["typ"] == typ}
        assert len(nivaer) >= 2, typ
    # Båda kursstegen ska täcka alla tre nivåerna. Ett 1a-papper som bara har
    # kurs-2-ankare för A får logaritmer och diskriminanter till förebild.
    for steg in ("1", "2"):
        egna = {a["niva"] for a in niva_rubrik.ANKARE if a["kurs"] == steg}
        assert egna == set(niva_rubrik.NIVAER), steg


def test_ankarurvalet_foljer_typerna_och_faller_tillbaka():
    valda = niva_rubrik.ankare(["resonemang"], per_niva=1)
    assert valda and all(a["typ"] == "resonemang" for a in valda)
    # En typ som inte finns ska ge ankare ändå — fel typ styr bättre än inget.
    assert niva_rubrik.ankare(["finns-inte"])


def test_ankarurvalet_valjer_kursens_egna_forst():
    """Kursbreddningen: ett 1a-papper ska inte få kurs 2:s logaritmer till
    förebild, och ett 2c-papper ska inte få kurs 1:s vardagsprocent."""
    ettan = niva_rubrik.ankare(per_niva=1, kurs="Matematik, nivå 1a")
    assert ettan and all(a["kurs"] == "1" for a in ettan)
    tvaan = niva_rubrik.ankare(per_niva=1, kurs="Matematik, nivå 2c")
    assert tvaan and all(a["kurs"] == "2" for a in tvaan)
    # Utan kurs står ordningen i listan kvar — ingen tyst omsortering.
    assert niva_rubrik.ankare(per_niva=1) == niva_rubrik.ankare(
        per_niva=1, kurs="Matematik – fortsättning, nivå 1c")


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
    # Utan kurs sägs ingenting om kursen — det är ärligare än att gissa 2a.
    assert niva_rubrik.RUBRIK_KURSNIVA not in block


# ─────────────────────────────────────────────── kursbreddningen (D3) ─────
# Fyndet som ska överleva nästa omskrivning: mätningen sa att E, C och A
# betyder SAMMA sak i 1a, 1c, 2a och 2c — tolv uppgifter som förekommer i både
# 1a- och 1c-provet vt 2022 har samma poängsättning i båda. Det som skiljer är
# hur mycket av varje nivå provet innehåller. Testerna nedan håller den
# skillnaden på plats åt båda hållen: rubriken får inte delas per kurs, och
# mixen får inte slås ihop.

def test_kursrubriken_ar_mix_och_form_inte_en_egen_nivadefinition():
    """Rubriken per kurs får INTE definiera om E, C eller A. Skulle någon
    skriva «i 1a räcker det med …» hör det inte hemma här — det motsägs av
    materialet, och det är precis det felet en språkmodell gör spontant."""
    assert set(niva_rubrik.RUBRIK_PER_KURS) == {"1a", "1c", "2a", "2c"}
    for kurs, text in niva_rubrik.RUBRIK_PER_KURS.items():
        assert text.strip() and "Mix:" in text, kurs
    assert "samma poängsättning i båda proven" in niva_rubrik.RUBRIK_KURSNIVA


def test_kursens_band_ar_snavare_an_det_gemensamma():
    """Om alla fyra kurserna får samma band är delningen meningslös. 1c:s
    C-band (42–43 %) och 2a:s (34–37 %) överlappar inte ens."""
    gemensamt = niva_rubrik.NP_FORDELNING["poangandel"]
    for kurs, band in niva_rubrik.NP_FORDELNING_PER_KURS.items():
        assert set(band) == set(niva_rubrik.NIVAER), kurs
        for niva, (lo, hi) in band.items():
            glo, ghi = gemensamt[niva]
            assert glo <= lo and hi <= ghi, (kurs, niva)
    ettc = niva_rubrik.NP_FORDELNING_PER_KURS["1c"]["C"]
    tvaa = niva_rubrik.NP_FORDELNING_PER_KURS["2a"]["C"]
    assert ettc[0] > tvaa[1], "1c ska vara C-tyngre än 2a"


def test_kursen_naar_prompten_och_domaren():
    for kurs, nyckel in (("Matematik, nivå 1a", "1a"),
                         ("Matematik, nivå 2c", "2c")):
        block = niva_rubrik.build_niva_block(["rutin"], ["P"], kurs=kurs)
        assert niva_rubrik.RUBRIK_KURSNIVA in block
        assert niva_rubrik.RUBRIK_PER_KURS[nyckel] in block
        andra = "2c" if nyckel == "1a" else "1a"
        assert niva_rubrik.RUBRIK_PER_KURS[andra] not in block
    # Domaren mäter mot samma text som prompten skrevs mot.
    sk = exam_spec.balanced_skeleton(8, "prov", delar=True)
    assert exam_gen._skala("prov", "", sk, "Matematik, nivå 1c") == \
        niva_rubrik.build_niva_block(
            sorted({s["typ"] for s in sk}), sorted({s["formaga"] for s in sk}),
            kurs="Matematik, nivå 1c")


def test_okand_kurs_ger_det_breda_bandet_och_ingen_kursrubrik():
    """Ma4 och Ma5 är INTE mätta. En rubrik som ändå påstod sig veta hur A ser
    ut där vore hittepå — då står det generella kvar."""
    assert niva_rubrik.kursnyckel("Matematik – fördjupning, nivå 1c") is None
    assert niva_rubrik.kursnyckel("") is None
    block = niva_rubrik.build_niva_block(kurs="Matematik, nivå 4")
    assert niva_rubrik.RUBRIK_KURSNIVA not in block
    assert niva_rubrik.niva_mal_prov(kurs="Matematik, nivå 4") == \
        niva_rubrik.niva_mal_prov()


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
         "losning": "$x = 2$ och $x = -5$.",
         # Trappan: en rad per poäng (exam_gen.bedomningssignaler).
         "bedomning": "+1 E ett nollställe\n+1 E båda nollställena"},
        {"del": None, "formaga": "P", "typ": "redovisning", "poang": [1, 1, 0],
         "text": "Lös ekvationen $x^2 - 9 = 0$.", "losning": "$x = \\pm 3$.",
         "bedomning": "+1 E korrekt ansats\n+1 C fullständig lösning"},
    ])


def test_fixturen_ar_verkligen_giltig():
    doc, fel = exam_spec.validate_exam_json(_giltigt_prov(), "arbetsblad")
    assert doc is not None and fel == []


def test_domarrundan_lagger_sina_fynd_i_reparationsloopen():
    dom = json.dumps({"domar": [{"nr": "2", "niva": "E", "motivering": "rutin"}]})
    battre = json.dumps(_giltigt_prov())
    llm, anrop = _stub([json.dumps(_giltigt_prov()), dom, "{}", battre])
    res = exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m",
                                 antal=2, profil="arbetsblad", llm=llm)
    # generering, nivådom, räknedom, reparation — DOMARNA kostar ett anrop var
    # men ingen runda; bara reparationen är en runda, och den delas av båda.
    assert len(anrop) == 4
    assert "poängsatt C men bedöms som E" in anrop[3]
    assert res["rounds"] == 2 and res["errors"] == []


def test_utan_avvikelser_kostar_domaren_ingen_reparation():
    dom = json.dumps({"domar": [{"nr": "1", "niva": "E", "motivering": ""},
                                {"nr": "2", "niva": "C", "motivering": ""}]})
    llm, anrop = _stub([json.dumps(_giltigt_prov()), dom, "{}"])
    res = exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m",
                                 antal=2, profil="arbetsblad", llm=llm)
    # Två domaranrop, noll rundor: en domare som inte fäller får aldrig kosta
    # läraren en omskrivning.
    assert len(anrop) == 3 and res["rounds"] == 1 and res["errors"] == []


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


# ──────────────────────────────── talvakterna och räknedomaren (2026-08-23) ──
# Talen var det sista som skilde ett genererat prov från ett riktigt: nivån var
# kalibrerad, men uppgifterna bar avrundade procentsatser och ingångstal
# konstruerade baklänges. Vakterna nedan är RÄKNADE i samma tio nationella prov
# som nivårubriken (exam_gen.TALREGLER), och samma lärdom gäller: en vakt som
# fäller riktiga NP-uppgifter är värdelös — därför står frikänningstestet sist.

def _b(**kw):
    """En uppgift i den räknarfria delen."""
    u = _uppg(1, (1, 0, 0), **{k: v for k, v in kw.items() if k != "delen"})
    u["del"] = kw.get("delen", "B")
    return u


def test_talsignal_facit_utan_raknare_far_inte_vara_ett_narmevarde():
    exam = _exam([_b(losning="$x \\approx 5{,}8480$")])
    fel = exam_gen.talsignaler(exam)
    assert [f["code"] for f in fel] == ["talsignal"]
    assert "svaret ska vara exakt" in fel[0]["message"]


def test_talsignal_exakt_facit_utan_raknare_passerar():
    """Ett förkortat bråk ÄR svaret i nationella provets räknarfria del."""
    assert exam_gen.talsignaler(_exam([_b(losning="$x = 10/7$")])) == []


def test_talsignal_forandringsfaktorn_passerar_i_raknarfri_del():
    """1,04 har två decimaler och är ändå rätt: den står som GIVET tal i kurs
    1:s räknarfria del. Vakten fäller 3,75, inte förändringsfaktorn."""
    ok = _exam([_b(text="Värdet ges av $y = 500 \\cdot 1{,}04^x$.")])
    assert exam_gen.talsignaler(ok) == []
    fel = exam_gen.talsignaler(_exam([_b(text="Beräkna $3{,}75 \\cdot 12{,}5$.")]))
    assert any("EXAKT en decimal" in f["message"] for f in fel)


def test_talsignal_blocktal_passerar_men_lost_stort_tal_falls():
    """$4444^2 - 4443^2$ är en riktig NP-uppgift: talet är stort men en regel
    gör aritmetiken onödig, och det syns på att talet återkommer i facit."""
    block = _exam([_b(text="Beräkna $4444^2 - 4443^2$.",
                      losning="$(4444 + 4443)(4444 - 4443) = 8887$")])
    assert exam_gen.talsignaler(block) == []
    fel = exam_gen.talsignaler(_exam([_b(text="Dividera $12\\,166$ med $79$.",
                                         losning="$154$")]))
    assert any("stora tal" in f["message"] for f in fel)


def test_talsignal_avrunda_till_tva_decimaler_falls():
    """Frasen finns inte i nationella provet — noll gånger i tio prov."""
    fel = exam_gen.talsignaler(_exam([_b(text="Avrunda till två decimaler.")]))
    assert any("finns inte i" in f["message"] for f in fel)


def test_talsignal_procentsvar_med_tva_decimaler_falls():
    """Det skarpa fyndet: «94,93 %» i räknardelen. Talet har fyra
    värdesiffror och två decimaler och klarar därför slutsvarsvakten — men NP
    anger procent med högst EN decimal, och toleransen står i facit."""
    exam = _exam([_b(delen="C", text="Hur stor är andelen?",
                     losning="Andelen blir $94{,}93$ %")])
    fel = exam_gen.talsignaler(exam)
    assert [f["code"] for f in fel] == ["talsignal"]
    assert "högst en decimal" in fel[0]["message"]


def test_talsignal_slutsvaret_med_raknare_men_inte_mellanleden():
    """Mellanled får ha fler siffror (TALREGLER säger det) — bara slutsvaret
    mäts. En vakt som läste hela facit hade fällt varje korrekt uträkning."""
    ok = _exam([_b(delen="C", text="Beräkna volymen.",
                   losning="Mellanledet $\\approx 12{,}16643$. Svar: $12$ dm")])
    assert exam_gen.talsignaler(ok) == []
    fel = exam_gen.talsignaler(_exam([_b(delen="C", text="Beräkna volymen.",
                                         losning="Svaret är $12{,}166$ dm")]))
    assert any("för många siffror" in f["message"] for f in fel)


def test_talsignal_fraserna_hor_till_var_sin_del():
    med = _exam([_b(delen="C", text="Lös ekvationen. Svara exakt.")])
    assert any("räknarfria delen" in f["message"]
               for f in exam_gen.talsignaler(med))
    utan = _exam([_b(text="Lös ekvationen. Svara med minst en decimal.")])
    assert any("aldrig ett närmevärde" in f["message"]
               for f in exam_gen.talsignaler(utan))


def test_talsignal_provovergripande_andel_avrundningsinstruktioner():
    """En enstaka instruktion om svarets form är normal; ett papper där var
    femte uppgift bär en har bytt genre. Flaggan sitter på PROVET."""
    manga = _exam([_uppg(i, (1, 0, 0),
                         text=f"Beräkna {i}. Avrunda till en decimal.")
                   for i in range(1, 5)])
    fel = [f for f in exam_gen.talsignaler(manga) if f["path"] == "prov"]
    assert len(fel) == 1 and "av 4 uppgifter" in fel[0]["message"]


@pytest.mark.parametrize("delen,text,losning", [
    # Alla fem är skrivna som riktiga NP-uppgifter på sin sida av
    # räknargränsen. Fäller någon vakt här har den blivit för ivrig.
    ("B", "Lös ekvationen $x^2 - 4x + 3 = 0$.", "$x = 1$ och $x = 3$."),
    ("B", "Förenkla $\\frac{2}{3} + \\frac{1}{6}$.", "$5/6$."),
    ("B", "En vara kostar $1\\,200$ kr. Priset höjs 15 %.", "$1\\,380$ kr."),
    ("C", "Värdet sjunker från $230\\,000$ kr till $157\\,000$ kr på 6 år.",
     "Förändringsfaktorn $\\approx 0{,}9385$. Svar: $6{,}2$ % per år."),
    ("C", "År 2020 fanns $1411$ tigrar och 2022 fanns $2967$.",
     "Ökningen är $110$ %."),
])
def test_talvakterna_faller_inte_riktiga_np_uppgifter(delen, text, losning):
    assert exam_gen.talsignaler(
        _exam([_b(delen=delen, text=text, losning=losning)])) == []


def test_raknedomaren_far_facit_men_aldrig_poang():
    """Räknedomaren MÅSTE se facit — den ska jämföra mot det. Poängen och
    bedömningsanvisningen är en annan sak: de säger vilken nivå uppgiften
    påstås ligga på, och det ska inte färga räkningen."""
    exam = _exam([_uppg(1, (0, 2, 0), losning="$x = 6$",
                        bedomning="+1 C fullständig lösning")])
    prompt = exam_gen.build_rakne_prompt(exam_gen.domarenheter(exam))
    assert "räknedomare" in prompt          # kassettroutingens nyckelfras
    assert "$x = 6$" in prompt
    assert "poang" not in prompt and "+1 C" not in prompt


def test_raknedomaren_ser_om_uppgiften_har_raknare():
    enheter = exam_gen.domarenheter(_exam([
        _uppg(1, (1, 0, 0)), _uppg(2, (1, 0, 0))]))
    enheter[0]["del"] = "B"
    prompt = exam_gen.build_rakne_prompt(enheter)
    assert "utan digitala verktyg" in prompt and "med digitala verktyg" in prompt


def test_raknedomen_faller_bara_pa_ett_uttryckligt_nej():
    enheter = exam_gen.domarenheter(_exam([
        _uppg(1, (1, 0, 0)), _uppg(2, (1, 0, 0)),
        _uppg(3, (1, 0, 0)), _uppg(4, (1, 0, 0))]))
    domar = exam_gen._parse_rakning(json.dumps({"domar": [
        {"nr": "1", "berakning": "2+2", "stammer": "ja"},
        {"nr": "2", "berakning": "figuren saknas", "stammer": "oklart"},
        {"nr": "3", "berakning": "$x = 4$", "stammer": "nej",
         "ratt_svar": "$x = 4$", "skal": "facit räknar med fel koefficient"},
        # uppgift 4 nämns inte alls → tystnad tolkas aldrig
    ]}))
    fel = exam_gen.raknefel(enheter, domar)
    assert [f["path"] for f in fel] == ["uppgift 3"]
    assert fel[0]["code"] == "rakning"
    # Åtgärden ska säga att BÅDA ändras — ett facit som skrivs om ensamt
    # räknar på andra tal än uppgiften.
    assert "ändras TILLSAMMANS" in fel[0]["message"]
    assert "fel koefficient" in fel[0]["message"]


def test_raknedomen_tar_emot_boolean_och_kapar_langa_listor():
    """Schemat ber om en sträng, men en modell som svarar `true`/`false` ska
    läsas rätt ändå — och taket delas med nivåfynden."""
    n = exam_gen.MAX_DOMAR_PROBLEM + 3
    enheter = exam_gen.domarenheter(
        _exam([_uppg(i, (1, 0, 0)) for i in range(1, n + 1)]))
    domar = exam_gen._parse_rakning(json.dumps({"domar": [
        {"nr": str(i), "berakning": "…", "stammer": False, "ratt_svar": "7"}
        for i in range(1, n + 1)]}))
    assert all(d["stammer"] == "nej" for d in domar.values())
    assert len(exam_gen.raknefel(enheter, domar)) == exam_gen.MAX_DOMAR_PROBLEM


def test_raknedomarsvar_som_inte_gar_att_tolka_faller_ingenting():
    """En trasig kontroll får aldrig underkänna ett papper som är rätt."""
    assert exam_gen._parse_rakning("inte json alls") == {}
    assert exam_gen._parse_rakning('{"domar": "fel form"}') == {}
    enheter = exam_gen.domarenheter(_exam([_uppg(1, (1, 0, 0))]))
    assert exam_gen.raknefel(enheter, exam_gen._parse_rakning("trasigt")) == []


def test_raknedomaren_ar_fail_open():
    """Faller anropet — modellen borta, kvoten slut — levereras pappret ändå."""
    def llm(*a, **kw):
        raise RuntimeError("kvoten är slut")

    rader = []
    assert exam_gen.doma_rakning(_exam([_uppg(1, (1, 0, 0))]), model="m",
                                 llm=llm, log_cb=rader.append) == []
    assert any("levereras ändå" in r for r in rader)


def test_raknedomaren_kors_i_samma_pass_och_delar_reparationsrundan():
    """Båda domarna i ETT pass och EN reparationsrunda — och talsignalerna
    åker med in i den prompten fastän de aldrig fäller själva."""
    nivadom = json.dumps({"domar": [{"nr": "2", "niva": "E",
                                     "motivering": "rutin"}]})
    raknedom = json.dumps({"domar": [{"nr": "1", "berakning": "$x = 2$",
                                      "stammer": "nej", "ratt_svar": "$x = 2$",
                                      "skal": "facit tappar en rot"}]})
    prov = _giltigt_prov()
    # En avrundningsfras som talvakten fäller — men som inte får kosta en runda
    # på egen hand (se testet efter det här).
    prov["uppgifter"][0]["text"] += " Avrunda till två decimaler."
    llm, anrop = _stub([json.dumps(prov), nivadom, raknedom, json.dumps(prov)])
    res = exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m",
                                 antal=2, profil="arbetsblad", llm=llm)
    assert len(anrop) == 4 and res["rounds"] == 2
    # EN reparationsprompt, alla tre sorters fynd i den.
    assert "poängsatt C men bedöms som E" in anrop[3]
    assert "ändras TILLSAMMANS" in anrop[3]
    assert "finns inte i nationella provet" in anrop[3]
    # Domarnas fynd gick IN i reparationen och prövas aldrig om (passet körs en
    # gång) — de står alltså inte kvar. Talsignalerna räknas däremot om på
    # resultatet, och eftersom uppspelningen gav tillbaka samma papper står de
    # kvar som varningar läraren ser.
    assert {e["code"] for e in res["errors"]} == {"talsignal"}


def test_talsignaler_ensamma_kostar_aldrig_en_runda():
    """Talens smak är en varning, inte en dom. Fäller ingen domare får läraren
    signalen att läsa — men inte en omskrivning hon inte bett om."""
    prov = _giltigt_prov()
    prov["uppgifter"][0]["text"] += " Avrunda till två decimaler."
    llm, anrop = _stub([json.dumps(prov), "{}", "{}"])
    res = exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m",
                                 antal=2, profil="arbetsblad", llm=llm)
    assert len(anrop) == 3 and res["rounds"] == 1
    # Två signaler: frasen på uppgiften, och pappret som helhet (en av två
    # uppgifter är över andelstaket).
    assert [e["code"] for e in res["errors"]] == ["talsignal", "talsignal"]
    assert [e["path"] for e in res["errors"]] == ["uppgift 1", "prov"]


def test_doma_false_stanger_av_bada_domarna():
    llm, anrop = _stub([json.dumps(_giltigt_prov())])
    exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m", antal=2,
                           profil="arbetsblad", llm=llm, doma=False)
    assert len(anrop) == 1


def test_talreglerna_star_i_prompten_for_alla_fyra_profilerna():
    for profil in ("prov", "arbetsblad", "gruppuppgift", "diagnos"):
        p = exam_gen.build_prompt("Matematik, nivå 2c", "NA25", [], antal=6,
                                  profil=profil,
                                  skeleton=exam_spec.balanced_skeleton(
                                      6, profil if profil != "diagnos"
                                      else "arbetsblad", delar=False))
        assert exam_gen.TALREGLER in p, profil


def test_np_frasen_om_tva_decimaler_ar_borta_ur_instruktionen():
    """Den stod som FAST FRAS att använda, och kom ut på skarpa prov. Den som
    sätter tillbaka den ska behöva stryka det här testet."""
    assert "Avrunda till två decimaler.' där" not in exam_gen.INSTRUCTION
    for fras in ("Svara exakt.", "Svara med minst en decimal.",
                 "Avrunda svaret till ett heltal."):
        assert fras in exam_gen.INSTRUCTION, fras


# ─────────────────────────────────────────────── bokens nivåskala (C2) ────

def test_uppgiftsraderna_bar_bokens_egen_markering():
    ut = bok_ocr._uppgifter([
        {"nr": 1215, "niva": 1, "nivamarke": "a"},
        {"nr": "1216", "nivå": "3", "nivåmärke": "★★★"},
        {"nr": 1217},                       # omarkerad uppgift
        1218,                               # bara ett tal
    ])
    # `exempel` är None när modellen inte sa något om saken (konsekvensregeln i
    # test_bok.py) — okänt, och det läses som en vanlig uppgift.
    assert ut == [
        {"nr": 1215, "niva": 1, "nivamarke": "a", "exempel": None},
        {"nr": 1216, "niva": 3, "nivamarke": "★★★", "exempel": None},
        {"nr": 1217, "niva": None, "nivamarke": None, "exempel": None},
        {"nr": 1218, "niva": None, "nivamarke": None, "exempel": None},
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


def test_bokblocket_ar_golv_tak_och_ordning_for_gruppuppgiften():
    """Golvet och taket stod rätt från början; ORDNINGEN var fel. Blocket sa
    «inte en trappa — uppgifterna behöver inte bli svårare nedåt», och lärarens
    skarpa lektion sa emot: stegringen var det som fungerade (Del F, dom 1)."""
    block = bok.build_niva_block({"namn": "Boken"}, 10, 11, [], _uppslag(),
                                 profil="gruppuppgift")
    assert "FÖRSTA" in block and "SISTA" in block
    assert "nivå 1" in block and "nivå 3" in block
    assert "svårare nedåt" in block
    # Fortfarande golv och tak, inte provets jämna spann över alla nivåer.
    assert "spänna" not in block


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
    fel sak. Sedan kursbreddningen bär skalan också KURSEN, så den ska följa
    med hit — annars döms ett 1a-papper mot 2c:s ankarexempel."""
    skeleton = exam_spec.balanced_skeleton(8, kurs="Ma2c")
    prompt = exam_gen.build_prompt("Ma2c", "NA25", [], antal=8,
                                   skeleton=skeleton)
    skala = exam_gen._skala("prov", "", skeleton, "Ma2c")
    assert skala and skala in prompt
    # Utan kursen är det en annan text — det är just det felet raden hindrar.
    assert exam_gen._skala("prov", "", skeleton) not in prompt


def test_bokens_skala_ar_ocksa_domarens(monkeypatch):
    skala = exam_gen._skala("arbetsblad", "BOKENS NIVÅSKALA — hittepå", None)
    assert skala == "BOKENS NIVÅSKALA — hittepå"
