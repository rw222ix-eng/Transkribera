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


def _dom(niva, motivering="skäl"):
    return {"niva": niva, "motivering": motivering, "kryss": [],
            "resonemang": ""}


def test_dubbeldomen_slapper_igenom_bara_nar_bada_ar_eniga_med_poangen():
    """Enighetsregeln (2026-09-07). Läraren: «jag ska vara tvärsäker på att en
    C-uppgift är C.» Då räcker det inte att EN domare håller med."""
    enheter = exam_gen.domarenheter(_exam([_uppg(1, (0, 2, 0))]))
    enig = {"1": _dom("C")}
    assert exam_gen.avvikelser(enheter, enig, enig) == []


def test_dubbeldomen_faller_nar_domarna_ar_oense():
    enheter = exam_gen.domarenheter(_exam([_uppg(1, (0, 2, 0))]))
    avv = exam_gen.avvikelser(enheter, {"1": _dom("C")}, {"1": _dom("E")})
    assert [a["path"] for a in avv] == ["uppgift 1"]
    assert "poängsatt C men bedöms som E" in avv[0]["message"]
    # Att de är OENSE ska stå i klartext: uppgiften är otydlig, inte bara
    # felplacerad, och reparationen ska veta skillnaden.
    assert "Den andra bedömaren sa C" in avv[0]["message"]
    assert avv[0]["pastadd"] == "C" and avv[0]["domd"] == "E"


def test_dubbeldomen_faller_nar_bada_sager_samma_fel_niva():
    enheter = exam_gen.domarenheter(_exam([_uppg(1, (0, 2, 0))]))
    bada = {"1": _dom("E", "ren rutin")}
    avv = exam_gen.avvikelser(enheter, bada, bada)
    assert [a["path"] for a in avv] == ["uppgift 1"]
    assert "Den andra bedömaren" not in avv[0]["message"]
    # Åtgärden ska stå i felet, inte bara konstaterandet.
    assert niva_rubrik.STEGET_UPP["E→C"] in avv[0]["message"]


def test_oklart_ar_ett_fynd_och_inte_langre_toleransen():
    """«Oklart» var toleransen och passerade. En uppgift vars nivå inte går att
    avgöra är inte en uppgift läraren kan vara tvärsäker på."""
    enheter = exam_gen.domarenheter(_exam([_uppg(1, (0, 2, 0))]))
    avv = exam_gen.avvikelser(enheter, {"1": _dom("OKLART", "gränsfall")},
                              {"1": _dom("C")})
    assert [a["path"] for a in avv] == ["uppgift 1"]
    assert "kunde inte avgöra nivån" in avv[0]["message"]
    assert avv[0]["domd"] == "oklart"


def test_tystnad_efter_omfragan_ar_ett_fynd():
    """Tystnad var den tolerans som INTE syntes: en domare som hoppade över
    halva pappret «godkände» det. Omfrågan sker i _fraga_domare; når den hit är
    enheten obesvarad två gånger."""
    enheter = exam_gen.domarenheter(_exam([_uppg(1, (0, 2, 0))]))
    avv = exam_gen.avvikelser(enheter, {}, {"1": _dom("C")})
    assert [a["path"] for a in avv] == ["uppgift 1"]
    assert "nämnde den inte" in avv[0]["message"]


def test_domaren_fragar_en_gang_till_om_de_overhoppade():
    """Och omfrågan sker BARA på de enheter som saknas — inte hela pappret en
    gång till."""
    prompter = []

    def llm(model, prompt, **kw):
        prompter.append(prompt)
        # Första svaret från varje domare hoppar över uppgift 2; omfrågan får
        # den. Domaren känns igen på att prompten bär uppgift 1.
        if "Uppgift 1." in prompt:
            return json.dumps({"domar": [{"nr": "1", "niva": "E"}]})
        return json.dumps({"domar": [{"nr": "2", "niva": "E"}]})

    exam = _exam([_uppg(1, (1, 0, 0)), _uppg(2, (1, 0, 0))])
    fynd, kordes = exam_gen.niva_fynd(exam, model="m", llm=llm)
    assert kordes and fynd == []
    # blind, omfrågan, kriteriedom, omfrågan — och omfrågorna bär BARA den
    # uppgift som saknades.
    assert len(prompter) == 4
    assert "Uppgift 2." in prompter[1] and "Uppgift 1." not in prompter[1]


def test_domarsvar_som_inte_gar_att_tolka_faller_ingenting():
    """En trasig kontroll får aldrig underkänna ett prov som är rätt. Ett svar
    utan en enda tolkbar dom är inte tystnad om enskilda uppgifter utan en
    kontroll som inte kördes — och då fälls ingenting, men läraren får veta
    det (se test_fail_open_markeras_i_nivafel)."""
    assert exam_gen._parse_domar("inte json alls") == {}
    assert exam_gen._parse_domar('{"domar": "fel form"}') == {}
    fynd, kordes = exam_gen.niva_fynd(_exam([_uppg(1, (0, 2, 0))]), model="m",
                                      llm=lambda *a, **k: "trasigt")
    assert fynd == [] and kordes is False


def test_domaren_kapar_langa_fellistor():
    n = exam_gen.MAX_DOMAR_PROBLEM + 3
    enheter = exam_gen.domarenheter(
        _exam([_uppg(i, (0, 0, 1)) for i in range(1, n + 1)]))
    domar = {str(i): {"niva": "E", "motivering": ""} for i in range(1, n + 1)}
    assert len(exam_gen.avvikelser(enheter, domar)) == exam_gen.MAX_DOMAR_PROBLEM


def test_doma_nivaer_kor_tva_anrop_och_bada_far_skalan_med_sig():
    """Två domar per papper, och BÅDA mot den skala dokumentet skrevs mot. Får
    de olika skalor är de inte två domar om samma sak."""
    anrop = []

    def llm(model, prompt, **kw):
        anrop.append(prompt)
        return json.dumps({"domar": [{"nr": "1", "niva": "E",
                                      "motivering": "ren rutin"}]})

    avv = exam_gen.doma_nivaer(_exam([_uppg(1, (0, 0, 2))]), model="m", llm=llm,
                               skala="SKALAN SOM GÄLLDE")
    assert len(anrop) == 2 and all("SKALAN SOM GÄLLDE" in p for p in anrop)
    # Prompterna är OLIKA — annars är den andra domen bara en upprepning.
    assert exam_gen.KRITERIEDOMARE in anrop[1] \
        and exam_gen.KRITERIEDOMARE not in anrop[0]
    assert len(avv) == 1 and avv[0]["code"] == "niva"


def test_kriteriedomaren_kryssar_innan_den_domer():
    """Checklistan står FÖRE nivån i schemat, och grammatiken skriver fälten i
    schemats ordning: modellen kan inte välja nivå först och fylla i kryssen så
    att de passar."""
    falt = list(exam_gen.DOMAR_KRIT_SCHEMA["properties"]["domar"]["items"]
                ["properties"])
    for kriterium, _fraga, _niva in exam_gen.KRITERIER:
        assert falt.index(kriterium) < falt.index("niva"), kriterium
    # Kriterierna är rubrikens egna, inte påhittade: varje ja pekar på en nivå
    # rubriken beskriver.
    assert {n for _f, _q, n in exam_gen.KRITERIER} <= set(niva_rubrik.NIVAER)


def test_domaren_kors_inte_pa_ett_dokument_utan_poang():
    anrop = []
    exam_gen.doma_nivaer(_exam([]), model="m",
                         llm=lambda *a, **k: anrop.append(1) or "{}")
    assert anrop == []


# ─────────────────────────────────────────── nivåpasset i genereringen ────

def _stub(svar: list[str], *, dom: str = "{}", krit: str | None = None,
          rakne: str = "{}"):
    """En stubbad modell som svarar efter vad prompten FRÅGAR om.

    `svar` är svaren på DOKUMENTprompterna i tur och ordning (den sista
    upprepas, som förut). `dom` går till nivådomarna — samma svar till båda,
    för enighet är normalläget — och `krit` när kriteriedomaren ska säga något
    annat än den blinda. Räknedomaren får `rakne`.

    Dispatchen finns för att nivådomen är TVÅ anrop sedan 2026-09-07 och
    grinden kan ställa dem flera gånger till. En lista i tur och ordning hade
    behövt räknas om vid varje ändring i kedjan — och listans sista svar, ett
    helt prov, hade gått till en domare som svarade med det.

    `dom="{}"` betyder «domaren svarade inget tolkbart» och är alltså
    fail-open: den kontrollen räknas som icke körd och fäller ingenting."""
    anrop, dokument = [], []

    def llm(model, prompt, **kw):
        anrop.append(prompt)
        # HELA frasen, inte bara ordet: nivåfynden i en reparationsprompt SÄGER
        # «kriteriedomaren», och dispatchen hade då gett domarsvaret till en
        # fråga om ett helt prov. Samma skäl som i tests/fejk.py.
        if f"Du är {exam_gen.KRITERIEDOMARE}" in prompt:
            return dom if krit is None else krit
        if "vilken nivå den faktiskt ligger på" in prompt:
            return dom
        if "räknedomare" in prompt:
            return rakne
        dokument.append(prompt)
        return svar[min(len(dokument) - 1, len(svar) - 1)]

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
    """Fyndet ska laga sig själv i den delade rundan — och när det gjort det
    ska grinden se att det är borta, inte betala en extrarunda till.

    Domsvaret nedan gäller bara uppgift 2 och håller med om uppgift 1: efter
    reparationen dömer grinden om just uppgift 2, får samma svar, och då står
    fyndet kvar. Det är därför pappret till slut bär `nivafel` fast
    reparationen «lyckades» — bandet är en stubbe som inte ändrar sig."""
    dom = json.dumps({"domar": [{"nr": "1", "niva": "E", "motivering": ""},
                                {"nr": "2", "niva": "E", "motivering": "rutin"}]})
    battre = json.dumps(_giltigt_prov())
    llm, anrop = _stub([json.dumps(_giltigt_prov()), battre], dom=dom)
    res = exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m",
                                 antal=2, profil="arbetsblad", llm=llm)
    dokument = [p for p in anrop if "Skriv ett matteprov" in p
                or "Skriv ett ARBETSBLAD" in p]
    assert "poängsatt C men bedöms som E" in dokument[1]
    assert [(f["nr"], f["domd"]) for f in res["nivafel"]] == [("2", "E")]


def test_utan_avvikelser_kostar_domaren_ingen_reparation():
    dom = json.dumps({"domar": [{"nr": "1", "niva": "E", "motivering": ""},
                                {"nr": "2", "niva": "C", "motivering": ""}]})
    llm, anrop = _stub([json.dumps(_giltigt_prov())], dom=dom)
    res = exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m",
                                 antal=2, profil="arbetsblad", llm=llm)
    # Generering + två nivådomare + räknedomaren = fyra anrop, noll rundor och
    # noll extrarundor: domare som inte fäller får aldrig kosta läraren en
    # omskrivning, och grinden ska inte döma om ett papper som är rent.
    assert len(anrop) == 4 and res["rounds"] == 1 and res["errors"] == []
    assert res["nivafel"] == []


def test_doma_false_stanger_av_hela_passet():
    llm, anrop = _stub([json.dumps(_giltigt_prov())])
    exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m", antal=2,
                           profil="arbetsblad", llm=llm, doma=False)
    assert len(anrop) == 1


def test_en_nivareparation_som_forstor_dokumentet_kastas():
    """Var provet rent före domaren och trasigt efter är omskrivningen en
    försämring. Då behålls det gamla och nivåfyndet visas som en varning."""
    dom = json.dumps({"domar": [{"nr": "1", "niva": "E", "motivering": ""},
                                {"nr": "2", "niva": "E", "motivering": "rutin"}]})
    trasigt = json.dumps(_exam([
        {"del": None, "formaga": "P", "typ": "rutin", "poang": [0, 0, 0],
         "text": "Tom.", "losning": "L", "bedomning": "B"}]))
    llm, _anrop = _stub([json.dumps(_giltigt_prov()), trasigt], dom=dom)
    res = exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m",
                                 antal=2, profil="arbetsblad", llm=llm)
    assert res["exam"] == _giltigt_prov()
    assert [e["code"] for e in res["errors"]] == ["niva"]
    # …och grinden ger upp på samma sätt: den lagning som river dokumentet är
    # ingen lagning, och då är nivån osäkrad och SÄGS vara det.
    assert [f["nr"] for f in res["nivafel"]] == ["2"]


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


# ─────────────────── E-signalerna: rena E-papper (2026-09-07) ─────────────
# Exam 51 («Bara E») fick tre C-uppgifter poängsatta E. De tre nedan är just de
# formerna, och de fälls utan att någon modell körs.

_REN_E = {"e": (1.0, 1.0), "c": (0, 0), "a": (0, 0)}


def _e_fynd(text, *, losning="Lösning.", formaga="P", poang=(1, 0, 0),
            niva_mal=_REN_E):
    enheter = exam_gen.domarenheter(
        _exam([_uppg(1, poang, text=text, losning=losning, formaga=formaga)]))
    return exam_gen.e_nivasignaler(enheter, niva_mal)


@pytest.mark.parametrize("text,ord_i_fyndet", [
    # Uppgift 7 på exam 51, ordagrant i formen.
    ("Teckna $(x+2)^2 - x^2$ och förenkla uttrycket.", "kvadreringsregeln"),
    ("Förenkla $(a+b)(a-b)$.", "kvadreringsregeln"),
    # Uppgift 12: «visa att det alltid gäller» är C i rubriken.
    ("Visa att $(x+4)^2 - (x-4)^2 = 16x$ för alla $x$.", "kvadreringsregeln"),
    ("Stämmer det att summan alltid är jämn?", "generellt"),
])
def test_e_signalen_faller_c_innehall_pa_ett_rent_e_papper(text, ord_i_fyndet):
    fynd = _e_fynd(text)
    assert [f["code"] for f in fynd] == ["niva"], text
    assert ord_i_fyndet in fynd[0]["message"]
    assert fynd[0]["pastadd"] == "E" and fynd[0]["domd"] == "C"


def test_e_signalen_faller_ett_motexempel_som_ar_losningen():
    """Uppgift 9 på exam 51: «är √a < a för alla positiva a?» — motexemplet
    kräver ett tal mellan 0 och 1, och det är A i nationella provet."""
    fynd = _e_fynd("Gäller olikheten för varje positivt tal?", formaga="R",
                   losning="Nej. Ett motexempel är $a = 0{,}25$.")
    assert len(fynd) == 1 and fynd[0]["domd"] == "C"
    # …och när formuleringen INTE är generell är det motexemplet som fäller,
    # med A som dömd nivå.
    ensamt = _e_fynd("Stämmer Almas påstående?", formaga="R",
                     losning="Nej, ett motexempel är $a = 0{,}25$.")
    assert len(ensamt) == 1 and ensamt[0]["domd"] == "A"


@pytest.mark.parametrize("text,losning", [
    # Rena rutinuppgifter på E-nivå. Fäller någon signal här är vakten för ivrig
    # igen — samma lärdom som nivåsignalerna en gång kostade.
    ("Lös ekvationen $3x + 5 = 20$.", "$x = 5$."),
    ("Beräkna $(3+4)^2$.", "$49$."),
    ("Förenkla $(x+2)(x+5)$.", "$x^2 + 7x + 10$."),
    ("Hur stor är arean av rektangeln?", "$12$ cm$^2$."),
])
def test_e_signalen_faller_inte_en_ren_rutinuppgift(text, losning):
    assert _e_fynd(text, losning=losning) == []


def test_e_signalerna_galler_bara_rena_e_papper():
    """På ett blandat papper är kvadreringsregeln inte fel — där är det
    dubbeldomen som avgör var uppgiften hör hemma."""
    text = "Teckna $(x+2)^2 - x^2$ och förenkla uttrycket."
    assert _e_fynd(text, niva_mal=None) == []
    assert _e_fynd(text, niva_mal={"e": (0.5, 0.6), "c": (0.2, 0.3),
                                   "a": (0.1, 0.2)}) == []
    # …och inte heller på en uppgift som faktiskt ÄR poängsatt C.
    assert _e_fynd(text, poang=(0, 1, 0)) == []


# ─────────────────────────────── grinden (2026-09-07) ─────────────────────

def _ren_e_blad():
    """Ett arbetsblad som klarar E-bandet — och där uppgift 2 är den sortens
    kvadreringsuppgift exam 51 var full av."""
    return _exam([
        {"del": None, "formaga": "B", "typ": "rutin", "poang": [2, 0, 0],
         "text": "Lös ekvationen $3x + 5 = 20$.", "losning": "$x = 5$.",
         "bedomning": "+1 E ansats\n+1 E rätt svar"},
        {"del": None, "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
         "text": "Teckna $(x+2)^2 - x^2$ och förenkla uttrycket.",
         "losning": "$4x + 4$.",
         "bedomning": "+1 E utvecklar\n+1 E förenklar"},
    ])


def test_grinden_kor_extrarundorna_och_sager_ifran_nar_de_inte_racker():
    """Hårda grinden: ett papper får inte levereras som klart med kvarstående
    nivåfynd. Här svarar stubben med SAMMA papper varje gång, så fyndet står
    kvar — och då ska pappret bära `nivafel` i stället för att tiga.

    Bladet är ett RENT E-blad och får därför EXTRA_NIVARUNDOR_RENT rundor:
    varje uppgift påstår samma nivå, och domen måste hålla varje gång."""
    enig = json.dumps({"domar": [{"nr": "1", "niva": "E"},
                                 {"nr": "2", "niva": "E"}]})
    llm, anrop = _stub([json.dumps(_ren_e_blad())], dom=enig)
    res = exam_gen.generate_exam("Ma1a", "NA25", ["algebra"], model="m",
                                 antal=2, profil="arbetsblad", llm=llm,
                                 niva_mal=_REN_E)
    # De extra riktade rundorna utöver domarpassets egen.
    rundor = [p for p in anrop if "Problem att åtgärda" in p]
    assert len(rundor) == 1 + exam_gen.EXTRA_NIVARUNDOR_RENT
    # Extrarundorna bär BARA nivåfyndet — inte talsignaler, inte balansfel.
    assert "kvadreringsregeln eller konjugatregeln" in rundor[-1]
    assert [(f["nr"], f["pastadd"], f["domd"]) for f in res["nivafel"]] \
        == [("2", "E", "C")]
    # Fyndet står kvar i fellistan också: den är klientens `provFel`.
    assert [e["code"] for e in res["errors"]] == ["niva"]


def test_grinden_ar_tyst_nar_omskrivningen_lagade_nivan():
    """Och när extrarundan FUNGERAR ska pappret levereras utan `nivafel` — och
    utan en andra extrarunda."""
    enig = json.dumps({"domar": [{"nr": "1", "niva": "E"},
                                 {"nr": "2", "niva": "E"}]})
    lagat = _ren_e_blad()
    lagat["uppgifter"][1]["text"] = "Förenkla uttrycket $4x + 4 - x$."
    llm, anrop = _stub([json.dumps(_ren_e_blad()), json.dumps(lagat)], dom=enig)
    res = exam_gen.generate_exam("Ma1a", "NA25", ["algebra"], model="m",
                                 antal=2, profil="arbetsblad", llm=llm,
                                 niva_mal=_REN_E)
    assert res["nivafel"] == [] and res["errors"] == []
    assert len([p for p in anrop if "Problem att åtgärda" in p]) == 1
    assert res["exam"]["uppgifter"][1]["text"] == lagat["uppgifter"][1]["text"]


def _tre_e_uppgifter():
    """Tre rena E-uppgifter utan en enda deterministisk signal — det som fäller
    här ska vara domen och ingenting annat."""
    return _exam([
        _uppg(1, (2, 0, 0), formaga="B", typ="rutin",
              text="Lös ekvationen $3x + 5 = 20$.", losning="$x = 5$."),
        _uppg(2, (2, 0, 0), formaga="P", typ="rutin",
              text="Beräkna $12 + 8$.", losning="$20$."),
        _uppg(3, (2, 0, 0), formaga="M", typ="rutin",
              text="Skriv $0{,}25$ i procentform.", losning="$25$ %."),
    ])


def _domarkort(prompt: str) -> set[str]:
    """Uppgiftsnumren en domarprompt faktiskt frågar om."""
    import re
    return set(re.findall(r'"nr": "([^"]+)"', prompt))


@pytest.mark.parametrize("niva_mal,vantade", [
    (_REN_E, {"1", "2", "3"}),          # rent papper: hela pappret döms om
    (None, {"2"}),                      # blandat: bara den rörda uppgiften
])
def test_omdomen_efter_en_omskrivning_mater_hela_det_rena_pappret(niva_mal,
                                                                 vantade):
    """Grindens andra hål: den dömde bara om de uppgifter den senast fällde, så
    `nivafel` beskrev en delmängd och inte pappret läraren fick. På ett rent
    nivåpapper påstår VARJE uppgift samma nivå — en dom utanför servern på ett
    levererat A-blad (2026-09-08) fällde fem andra uppgifter än de grinden
    tittat på — så där mäts hela pappret om. På ett blandat papper är
    delmängden fortfarande rätt: en omskrivning av uppgift 2 säger ingenting om
    uppgift 3."""
    exam = _tre_e_uppgifter()
    dom = json.dumps({"domar": [{"nr": "1", "niva": "E"},
                                {"nr": "2", "niva": "C"},
                                {"nr": "3", "niva": "E"}]})
    llm, anrop = _stub([json.dumps(exam)], dom=dom)
    fynd = exam_gen.avvikelser(exam_gen.domarenheter(exam),
                               exam_gen._parse_domar(dom))
    assert [f["nr"] for f in fynd] == ["2"]
    # `nivamatt=False`: domarpasset skrev om pappret efter att fynden mättes,
    # och det är precis då omdomen ska köras.
    exam_gen._niva_grind({"exam": exam, "errors": [], "rounds": 1,
                          "nivafynd": fynd, "nivakoll": True,
                          "nivamatt": False},
                         model="m", llm=llm, profil="arbetsblad", skala="",
                         antal=3, skeleton=None, koder=None,
                         niva_mal=niva_mal)
    domar = [p for p in anrop if "vilken nivå den faktiskt ligger på" in p]
    assert domar, "ingen omdom kördes"
    assert _domarkort(domar[0]) == vantade


def test_ett_rent_papper_doms_om_aven_utan_kvarstaende_fynd():
    """Rundan kan ha kommit ur räknedomaren i stället: då är nivåfynden tomma
    OCH pappret omskrivet, och «inga fynd» gällde ett dokument som inte längre
    finns. Ett rent papper får aldrig levereras som säkrat på en dom om en
    tidigare version — ett blandat får det, som förut."""
    exam = _tre_e_uppgifter()
    dom = json.dumps({"domar": [{"nr": "1", "niva": "E"},
                                {"nr": "2", "niva": "E"},
                                {"nr": "3", "niva": "E"}]})
    for niva_mal, vantat in ((_REN_E, 2), (None, 0)):
        llm, anrop = _stub([json.dumps(exam)], dom=dom)
        res = exam_gen._niva_grind({"exam": exam, "errors": [], "rounds": 1,
                                    "nivafynd": [], "nivakoll": True,
                                    "nivamatt": False},
                                   model="m", llm=llm, profil="arbetsblad",
                                   skala="", antal=3, skeleton=None,
                                   koder=None, niva_mal=niva_mal)
        # Dubbeldomen är två anrop; det blandade pappret kör inget alls.
        assert len(anrop) == vantat, niva_mal
        assert res["nivafel"] == []


def test_fail_open_markeras_i_nivafel():
    """Faller domaranropet levereras pappret ändå — men tystnaden får inte se
    ut som ett godkännande."""
    def llm(model, prompt, **kw):
        if "vilken nivå den faktiskt ligger på" in prompt:
            raise RuntimeError("kvoten slut")
        return json.dumps(_giltigt_prov())

    loggat = []
    res = exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m",
                                 antal=2, profil="arbetsblad", llm=llm,
                                 log_cb=loggat.append)
    assert res["nivafel"] == exam_gen.NIVAKOLL_FOLL
    assert res["exam"] is not None, "pappret ska levereras ändå"
    assert loggat[-1] == ("Nivån gick inte att kontrollera: nivåkontrollen "
                          "kunde inte köras.")


def test_refine_markerar_nivan_men_skriver_inte_om_nagot_annat():
    """En omskrivning kan göra en E-uppgift till en C-uppgift. Grinden i refine
    MÄRKER det men reparerar inte: en extrarunda hade rört en uppgift läraren
    inte pekade på, och det är precis vad mål-låset finns för."""
    fore = _ren_e_blad()
    fore["uppgifter"][1]["text"] = "Förenkla uttrycket $4x + 4 - x$."
    efter = _ren_e_blad()          # modellen gör uppgift 2 till en kvadrering
    anrop = []

    def llm(model, prompt, **kw):
        anrop.append(prompt)
        return json.dumps(efter)

    res = exam_gen.refine_exam(fore, "gör uppgift 2 svårare", model="m",
                               nummer=2, profil="arbetsblad",
                               niva_mal=_REN_E, llm=llm)
    assert len(anrop) == 1, "refine ska inte kosta ett domaranrop"
    assert [f["nr"] for f in res["nivafel"]] == ["2"]


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
    nivadom = json.dumps({"domar": [{"nr": "1", "niva": "E", "motivering": ""},
                                    {"nr": "2", "niva": "E",
                                     "motivering": "rutin"}]})
    raknedom = json.dumps({"domar": [{"nr": "1", "berakning": "$x = 2$",
                                      "stammer": "nej", "ratt_svar": "$x = 2$",
                                      "skal": "facit tappar en rot"}]})
    prov = _giltigt_prov()
    # En avrundningsfras som talvakten fäller — men som inte får kosta en runda
    # på egen hand (se testet efter det här).
    prov["uppgifter"][0]["text"] += " Avrunda till två decimaler."
    llm, anrop = _stub([json.dumps(prov), json.dumps(prov)],
                       dom=nivadom, rakne=raknedom)
    res = exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m",
                                 antal=2, profil="arbetsblad", llm=llm)
    reparation = [p for p in anrop if "Problem att åtgärda" in p][0]
    # EN reparationsprompt DELAD av båda domarna, alla tre sorters fynd i den.
    assert "poängsatt C men bedöms som E" in reparation
    assert "ändras TILLSAMMANS" in reparation
    assert "finns inte i nationella provet" in reparation
    # Talsignalerna räknas om på resultatet, och eftersom uppspelningen gav
    # tillbaka samma papper står de kvar som varningar läraren ser. Nivåfyndet
    # står också kvar — grinden dömde om uppgift 2 och fick samma svar.
    assert {e["code"] for e in res["errors"]} == {"talsignal", "niva"}
    assert [f["nr"] for f in res["nivafel"]] == ["2"]


def test_talsignaler_ensamma_kostar_aldrig_en_runda():
    """Talens smak är en varning, inte en dom. Fäller ingen domare får läraren
    signalen att läsa — men inte en omskrivning hon inte bett om."""
    prov = _giltigt_prov()
    prov["uppgifter"][0]["text"] += " Avrunda till två decimaler."
    enig = json.dumps({"domar": [{"nr": "1", "niva": "E"},
                                 {"nr": "2", "niva": "C"}]})
    llm, anrop = _stub([json.dumps(prov)], dom=enig)
    res = exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m",
                                 antal=2, profil="arbetsblad", llm=llm)
    assert len(anrop) == 4 and res["rounds"] == 1 and res["nivafel"] == []
    # Två signaler: frasen på uppgiften, och pappret som helhet (en av två
    # uppgifter är över andelstaket).
    assert [e["code"] for e in res["errors"]] == ["talsignal", "talsignal"]
    assert [e["path"] for e in res["errors"]] == ["uppgift 1", "prov"]


def test_doma_false_stanger_av_bada_domarna():
    llm, anrop = _stub([json.dumps(_giltigt_prov())])
    exam_gen.generate_exam("Ma1a", "NA25", ["ekvationer"], model="m", antal=2,
                           profil="arbetsblad", llm=llm, doma=False)
    assert len(anrop) == 1


def test_talreglerna_star_i_prompten_for_alla_profilerna():
    for profil in ("prov", "arbetsblad", "gruppuppgift"):
        p = exam_gen.build_prompt("Matematik, nivå 2c", "NA25", [], antal=6,
                                  profil=profil,
                                  skeleton=exam_spec.balanced_skeleton(
                                      6, profil, delar=False))
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


def test_med_bokdorr_star_boken_OCH_np_rubriken():
    """Bokens skala VANN förut över NP-rubriken, och det var buggen: bladet och
    dess domare fick «Nivå 1, 2, 3» med uppgiftsnummer och ingen enda mening om
    vad E, C och A kräver — fast domarprompten ber om just E, C eller A «enligt
    beskrivningarna ovan». Nu är boken ett lager TILL."""
    p = exam_gen.build_prompt("Ma1a", "NA25", [], antal=4, profil="arbetsblad",
                              boknivaer="BOKENS NIVÅSKALA — hittepå")
    assert "BOKENS NIVÅSKALA — hittepå" in p
    assert "NIVÅKRAV" in p
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
    """Domaren ska få samma text som pappret skrevs mot — och den texten bär
    numera BÅDA lagren."""
    sk = exam_spec.balanced_skeleton(4, "arbetsblad", delar=False)
    skala = exam_gen._skala("arbetsblad", "BOKENS NIVÅSKALA — hittepå", sk,
                            "Ma1a")
    assert "BOKENS NIVÅSKALA — hittepå" in skala and "NIVÅKRAV" in skala
    # Byte för byte samma text som prompten fick — kursen och uppgiftsplanen
    # ingår i skalan, så domaren måste få båda med sig.
    p = exam_gen.build_prompt("Ma1a", "NA25", [], antal=4, profil="arbetsblad",
                              skeleton=sk,
                              boknivaer="BOKENS NIVÅSKALA — hittepå")
    assert skala in p


def test_rent_nivapapper_far_en_skala_utan_stigning():
    """«Låt de första uppgifterna ligga på E-nivå och de sista på C-nivå» är
    fel order på ett papper där VARJE uppgift ska vara A — och den stod kvar i
    varje skala fram till 2026-09-09, också på de rena A-blad läraren fick.
    Skalan läser uppgiftsplanen och säger nivån rakt ut i stället."""
    nv = exam_spec.NIVAVAL["arbetsblad"]["A-nivå"]
    sk = exam_spec.balanced_skeleton(6, "arbetsblad", delar=False,
                                     mix=nv["mix"], niva_mal=nv["mal"])
    assert exam_gen._rent_skelett(sk) == "A"
    skala = exam_gen._skala("arbetsblad", "", sk, "Ma1c")
    assert "Varenda uppgift på det här bladet ska ligga på A-nivå" in skala
    assert "stigande svårighet" not in skala
    # Ett blandat blad behåller stigningen — undantaget får inte bli regeln.
    blandat = exam_spec.balanced_skeleton(6, "arbetsblad", delar=False)
    assert exam_gen._rent_skelett(blandat) is None
    assert "stigande svårighet" in exam_gen._skala("arbetsblad", "", blandat,
                                                   "Ma1c")


def test_provet_utan_portratt_gar_till_reparation():
    """Fältet är valfritt i schemat, så bara vakten kan kräva det — och bara
    för provet, som är det enda pappret med försättsblad."""
    from app import exam_gen
    assert exam_gen.forsattsignaler({"uppgifter": []}, "arbetsblad") == []
    fel = exam_gen.forsattsignaler({"uppgifter": []}, "prov")
    assert len(fel) == 1 and fel[0]["code"] == "forsatt"
    # Meddelandet ber om alla tre fälten, bildtexten inräknad.
    assert "bildtext" in fel[0]["message"]
    ok = {"forsattsbild": {"person": "Euler", "scene": "SCENE. x",
                           "bildtext": "Euler vid sitt bord. Han byggde upp "
                                       "funktionsläran på 1700-talet. Samma "
                                       "funktioner står på provet."}}
    assert exam_gen.forsattsignaler(ok, "prov") == []


def test_portrattet_utan_bildtext_gar_ocksa_till_reparation():
    """LÄRAREN (2026-09-06): «Det ska ALLTID skapas en passande undertext till
    bilden på försättssidan.» Fältet måste ändå förbli valfritt i schemat
    (kassetterna och proven i basen saknar det), så det är vakten som gör
    «alltid» till ett krav. Ett porträtt utan bildtext ger eleven ett ansikte
    utan förklaring, och det är precis vad hon bad om att slippa."""
    from app import exam_gen
    utan = {"forsattsbild": {"person": "Euler", "scene": "SCENE. x"}}
    fel = exam_gen.forsattsignaler(utan, "prov")
    assert len(fel) == 1 and fel[0]["code"] == "bildtext"
    assert fel[0]["path"] == "forsattsbild.bildtext"
    # Tom sträng är detsamma som inget fält.
    tom = {"forsattsbild": dict(utan["forsattsbild"], bildtext="   ")}
    assert exam_gen.forsattsignaler(tom, "prov")[0]["code"] == "bildtext"
    # … men bara för provet: arbetsbladet har inget försättsblad.
    assert exam_gen.forsattsignaler(utan, "arbetsblad") == []
