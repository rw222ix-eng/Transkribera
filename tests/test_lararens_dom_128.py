"""Lärarens dom 2026-09-23 kväll över exam 128 (BA26B, Ma 1a, «MATTETEST 1 –
Tal, procent och enheter», 7/10) och exam 129 (TE26A, Ma 1c, 14/10), som
kod. Uppgiftstexterna nedan står ordagrant som modellen skrev dem.

  A  NP-typerna: yrkespunkterna gav noll kategorier och exam 128 skrevs utan
     en enda förebild, tyst.
  B  Texten: direkt uppmaning, ett formbyte per E-poäng, inga villkors- eller
     ordförklaringsmeningar, verkliga föremål, bara kapitlet och kursen, en
     mening per rad.
  C  Tiden: 20 poäng på 60 minuter i takt 3 «räknades till 70».
  +  Situationen: 129 fick tändstickorna ur 126, en annan klass prov i samma
     kurs.
"""
import copy

from app import db, elevlasare, exam_gen, exam_spec, kursdomare, niva_rubrik
from app import np_vakter

KURS_1A = "Matematik, nivå 1a"
KODER_128 = ["G25-M1A-YRK-1", "G25-M1A-YRK-2", "G25-M1A-YRK-4",
             "G25-M1A-PRO-2"]


def _u(text, poang, typ="rutin", del_="B", delar=None, losning="x"):
    u = {"del": del_, "formaga": "B", "typ": typ, "poang": poang,
         "text": text, "losning": losning,
         "bedomning": "\n".join(["+1 E rätt"] * sum(poang))}
    if delar:
        u["poang"] = [0, 0, 0]
        u["deluppgifter"] = delar
    return u


def _d(text, poang, losning="x"):
    return {"poang": poang, "text": text, "losning": losning,
            "bedomning": "\n".join(["+1 E rätt"] * sum(poang))}


def _prov(*uppgifter, kurs="Matematik 1a"):
    return {"titel": "Tal och andelar", "kurs": kurs, "hjalpmedel": "-",
            "uppgifter": [copy.deepcopy(u) for u in uppgifter]}


UPPG1 = _u("Skriv storheterna i den enhet som står i uppgiften. Svara i "
           "grundpotensform.", [0, 0, 0], delar=[
               _d("Sträckan $307$ km, skriven i meter.", [1, 0, 0]),
               _d("Massan $6$ mg, skriven i gram.", [1, 0, 0]),
               _d("Längden $5 \\cdot 10^{2}$ nm, skriven i meter.",
                  [1, 0, 0])])
UPPG3 = _u("En elektriker lägger till $25$ % moms på sitt timpris. Moms är en "
           "skatt. Timpriset kan vara vilket belopp som helst. En kund får "
           "rabatt på priset med moms. Då betalar kunden lika mycket som "
           "timpriset utan moms. Beräkna hur många procent rabatt kunden "
           "får.", [0, 0, 1])
UPPG4 = _u("Ekvationen nedan har lösningen $x = 0{,}02$.\n"
           "$\\dfrac{x}{0{,}05} + kx = 0{,}2$\nBestäm konstanten $k$.",
           [0, 2, 0], typ="redovisning")
UPPG5 = _u("Påståendena nedan handlar om tal i bråkform.", [0, 0, 0], delar=[
    _d("Sara påstår att det finns ett bråk med nämnaren $12$ mellan "
       "$\\dfrac{2}{3}$ och $\\dfrac{3}{4}$. Täljaren ska vara ett heltal. "
       "Avgör om Sara har rätt.", [0, 1, 0])])
UPPG6 = _u("Ali ska lägga kvadratiska plattor på ett golv. Golvet är "
           "$3{,}9$ m långt och $2{,}1$ m brett.", [0, 0, 0], delar=[
               _d("Ingen platta får kapas. Plattans sida är ett helt antal "
                  "centimeter och minst $10$ cm. Bestäm alla sidlängder som "
                  "plattan kan ha.", [0, 0, 2])])


def _koder(fel):
    return [f["code"] for f in fel]


# ── A. NP-TYPERNA ────────────────────────────────────────────────────────

def test_yrkespunkterna_leder_till_np_kategorier_genom_exempelorden():
    """Exam 128:s beställning gav [] och noll typer. Exempelorden i punkternas
    text («procent och andelar», «överslagsräkning», «enhetsbyten») bär
    innehållet, rubrikerna gör det inte."""
    kat = niva_rubrik.np_kategorier(KODER_128)
    for k in ("procent", "aritmetik", "proportionalitet", "potenser",
              "geometri"):
        assert k in kat, kat
    assert "funktioner" not in kat       # «trigonometriska funktioner» är inte det
    typer = niva_rubrik.np_typer(KURS_1A, KODER_128)
    assert len(typer) >= 20
    assert {t["kategori"] for t in typer} >= {"procent", "aritmetik"}


def test_2a_yrkespunkter_utan_exempelord_far_hela_kursens_np():
    """«Yrkesnära fördjupning» och «Hjälpmedel och verktyg» saknar exempelord.
    Ensamma hade de gett noll typer; hellre hela kursens NP än ingen."""
    assert niva_rubrik.np_typer("Matematik, nivå 2a",
                                ["G25-M2A-YRK-1", "G25-M2A-YRK-2"])


def test_varje_innehallspunkt_i_en_matt_kurs_nar_np_typer():
    """Vakten som gör att det aldrig blir tyst igen, också för 2c:s
    sammansatta kategorier («statistik/normalfördelning»). Problemlösningen
    och de digitala punkterna är sätt att arbeta och har ingen egen kategori."""
    from app import course_data
    texter = course_data.kodtexter()
    for kurs, pref in (("Matematik, nivå 1a", "G25-M1A"),
                       ("Matematik, nivå 1c", "G25-M1C"),
                       ("Matematik, nivå 2a", "G25-M2A"),
                       ("Matematik, nivå 2c", "G25-M2C")):
        for kod in sorted(texter):
            if not kod.startswith(pref) or "-PRO-" in kod or "-DIG-" in kod:
                continue
            assert niva_rubrik.np_typer(kurs, [kod]), (kurs, kod)


def test_noll_np_typer_i_en_matt_kurs_sags_hogt():
    text = niva_rubrik.np_typer_saknas(KURS_1A, ["G25-M1A-PRO-2"])
    assert "Inga av nationella provets uppgiftstyper" in text
    assert "G25-M1A-PRO-2" in text
    # Typer finns: tyst. Omätt kurs: tyst, där finns inget att följa.
    assert niva_rubrik.np_typer_saknas(KURS_1A, KODER_128) == ""
    assert niva_rubrik.np_typer_saknas("Matematik, nivå 3c",
                                       ["G25-M1A-PRO-2"]) == ""


def test_efterkontrollen_sager_till_om_noll_np_typer():
    from app.web import routes_exam
    exam = _prov(_u("Beräkna $3 + 4$.", [1, 0, 0]))
    exam["kurs"] = KURS_1A
    exam["uppgifter"][0]["innehall"] = ["G25-M1A-PRO-2"]
    doc, fel = exam_spec.validate_exam_json(copy.deepcopy(exam))
    assert doc is not None, fel
    fynd = routes_exam._nptypfynd(doc, "prov")
    assert [f["kod"] for f in fynd] == ["nptyper"]
    # Det lagas inte av en omskrivning: ingen knapp för det ensamt.
    assert routes_exam.efterkontroll_instruktion(fynd) == ""
    exam["uppgifter"][0]["innehall"] = ["G25-M1A-YRK-2"]
    doc, _ = exam_spec.validate_exam_json(copy.deepcopy(exam))
    assert routes_exam._nptypfynd(doc, "prov") == []


# ── B. TEXTEN ────────────────────────────────────────────────────────────

def test_tva_formbyten_pa_en_e_poang_falls():
    """Uppgift 1: «307 km, skriven i meter» + «Svara i grundpotensform» är två
    byten för 1 E-poäng. «Skriv 307 km i grundpotensform.» är ett."""
    fel = np_vakter.formbytesvakt(_prov(UPPG1))
    assert [f["path"] for f in fel] == ["uppgift 1a", "uppgift 1b",
                                        "uppgift 1c"]
    assert "km → m och grundpotensform" in fel[0]["message"]
    assert "nm → m" in fel[2]["message"]
    rak = _prov(_u("Skriv $307$ km i grundpotensform.", [1, 0, 0]))
    assert np_vakter.formbytesvakt(rak) == []
    # Två byten på två poäng är NP:s egen form (nederbörd i mm till liter).
    tva = _prov(_u("Skriv $307$ km i meter och i grundpotensform.",
                   [2, 0, 0]))
    assert np_vakter.formbytesvakt(tva) == []
    # Area ur längder är en beräkning, inget byte.
    area = _prov(_u("Golvet är $3{,}9$ m långt. Svara i m$^2$.", [1, 0, 0]))
    assert np_vakter.formbytesvakt(area) == []


def test_lasreglerna_faller_exam_128_uppgift_for_uppgift():
    fel = np_vakter.lasregelvakt(_prov(UPPG1, UPPG3, UPPG5, UPPG6))
    text = " | ".join(f["message"] for f in fel)
    assert "«storheterna» är ord om uppgiften" in text            # 1
    assert "«Moms är en skatt.» förklarar ett ord" in text         # 3
    assert "vilket belopp som helst.» säger bara" in text          # 3
    assert "«Täljaren ska vara ett heltal.» är en villkorsmening" in text
    assert "«kvadratiska plattor» beskriver formen" in text        # 6
    assert "«Ingen platta får kapas.» är en villkorsmening" in text
    # Rätt skrivet enligt hennes egna former: tyst.
    ratt = _prov(
        _u("Skriv $307$ km i grundpotensform.", [1, 0, 0]),
        _u("En elektriker tar $400$ kr i timmen.\nMed $25$ % moms blir det "
           "$500$ kr.\nEn kund får rabatt och betalar $400$ kr.", [0, 0, 0],
           delar=[_d("Hur många procent rabatt får kunden?", [0, 1, 0]),
                  _d("Blir det samma procent om timpriset är $600$ kr? "
                     "Förklara varför.", [0, 0, 1])]),
        _u("Finns det ett bråk med nämnaren $12$ som ligger mellan "
           "$\\dfrac{2}{3}$ och $\\dfrac{3}{4}$?", [0, 1, 0]),
        _u("Ali ska lägga kvadratiska klinkerplattor på ett golv.",
           [1, 0, 0]))
    assert np_vakter.lasregelvakt(ratt) == []


def test_anvand_formeln_och_ar_en_metodforeskrift():
    """Exam 129 uppgift 10: formeln stod på raden ovanför."""
    fel = np_vakter.lasregelvakt(_prov(_u(
        "Bromssträckan $s$ m ges av formeln\n$s = 0{,}039v^{2}$\n"
        "Använd formeln och bestäm den högsta fart som ger högst 45 m "
        "bromssträcka.", [0, 3, 0], typ="problem", del_="C")))
    assert any("«Använd formeln och»" in f["message"] for f in fel)
    assert "«använd formeln»" not in exam_gen.INSTRUCTION.split(
        "Tillåtet är bara")[1][:120]


def test_kursgransen_faller_konstanten_och_delbarheten_i_1a():
    fel = np_vakter.kursvakt(_prov(UPPG4), kurs=KURS_1A)
    assert _koder(fel) == ["kursvakt"]
    assert "okänd konstant" in fel[0]["message"]
    # 1c har formen (parameter på A): tyst där.
    assert np_vakter.kursvakt(_prov(UPPG4), kurs="Matematik, nivå 1c") == []
    delare = _prov(_u("Bestäm den största gemensamma delaren till 390 och "
                      "210.", [0, 1, 0]))
    assert _koder(np_vakter.kursvakt(delare, kurs=KURS_1A)) == ["kursvakt"]
    # Kursdomaren får samma gräns i ord, också förklädd som plattsättning.
    prompt = kursdomare.build_kurs_prompt([], kursdomare.kursgrans(KURS_1A))
    assert "Bestäm konstanten" in prompt
    assert "ingen platta får kapas" in prompt
    assert "också när den är klädd som problemlösning" in prompt


def test_forbudsvakten_faller_ekvationen_pa_kapitel_1_testet():
    """Ekvationer är kapitel 2 för BA26B (lektionen 15/10, provet 7/10)."""
    delmoment = [{"delmoment": "Enhetsbyten", "sidor": "27–30"},
                 {"delmoment": "Tiopotenser", "sidor": "31–33"}]
    forbjudna = [{"metod": "Algebraiska uttryck", "sidor": "88–91"},
                 {"metod": "Linjära ekvationer", "sidor": "94–97"}]
    fel = exam_gen.forbudsvakt(_prov(UPPG1, UPPG4), delmoment, forbjudna)
    assert [f["path"] for f in fel] == ["uppgift 2"]
    assert "Linjära ekvationer (s. 94–97)" in fel[0]["message"]
    # Har klassen haft ekvationer är ordet inget förbud.
    haft = delmoment + [{"delmoment": "Linjära ekvationer", "sidor": "94–97"}]
    assert exam_gen.forbudsvakt(_prov(UPPG4), haft, forbjudna) == []
    # Ingen förbudslista, inget fynd (kassetteregeln).
    assert exam_gen.forbudsvakt(_prov(UPPG4), delmoment, []) == []
    # Utan kalender: provets eget kapitel är ändå haft. Ett 2a-prov över
    # «1.1 Uttryck, ekvationer och formler» får skriva «Lös ekvationen».
    kapitel = [{"avsnitt": "1.1",
                "etikett": "1.1 Uttryck, ekvationer och formler"}]
    senare = [{"metod": "Andragradsekvationer", "sidor": "60–80"}]
    assert exam_gen.forbudsvakt(_prov(UPPG4), [], senare, kapitel) == []
    assert exam_gen.forbudsvakt(_prov(UPPG4), [], senare) != []


def test_inga_bokstaver_nar_algebran_kommer_senare():
    """Generalrepetitionen samma natt skrev «En fisk väger $m$ kg … Svara med
    ett förenklat uttryck i $m$ och $k$» och två lönformler $L = 160t$ på
    kapitel 1-testet. Läraren: A-formen «UTAN bokstäver, eftersom klassen
    inte läst algebra än»."""
    delmoment = [{"delmoment": "Enhetsbyten", "sidor": "27–30"}]
    kapitel = [{"avsnitt": "1.3", "etikett": "1.3 Andelar och förhållanden"}]
    forbjudna = [{"metod": "Algebraiska uttryck", "sidor": "88–91"}]
    fisk = _u("En fisk väger $m$ kg.\nFisken innehåller $k$ mg kvicksilver.\n"
              "Hur många procent av fiskens vikt är kvicksilver?", [0, 0, 1])
    tal = _u("En fisk väger $2{,}5$ kg.\nHur många gram är det?", [1, 0, 0])
    fel = exam_gen.forbudsvakt(_prov(tal, fisk), delmoment, forbjudna, kapitel)
    assert [f["path"] for f in fel] == ["uppgift 2"]
    assert "räknar med bokstäver ($k$, $m$)" in fel[0]["message"]
    # Prompten säger det också, men bara när det klassen haft är känt.
    block = exam_gen.build_forbjudet(forbjudna, delmoment, kapitel)
    assert "Klassen har INTE räknat med bokstäver" in block
    assert "bokstäver" not in exam_gen.build_forbjudet(forbjudna)
    # Har klassen haft uttrycken är bokstäverna fria.
    haft = delmoment + [{"delmoment": "Algebraiska uttryck", "sidor": "88"}]
    assert exam_gen.forbudsvakt(_prov(fisk), haft, forbjudna) == []
    assert "bokstäver" not in exam_gen.build_forbjudet(forbjudna, haft)


def test_en_mening_per_rad_och_varje_mening_ryms():
    """Exam 129 uppgift 10: «Använd formeln och bestäm den högsta fart som
    ger högst 45 m / bromssträcka.» bröts mitt i."""
    text = ("Ekvationen nedan har lösningen $x = 0{,}02$. Bestäm $k$. Leo kör "
            "4,5 km. kl. 13 går han.")
    assert exam_gen.dela_meningar(text) == (
        "Ekvationen nedan har lösningen $x = 0{,}02$.\nBestäm $k$.\n"
        "Leo kör 4,5 km. kl. 13 går han.")
    lang = _prov(_u("Använd formeln och bestäm den högsta fart som ger "
                    "högst 45 m bromssträcka.", [0, 1, 0]))
    fel = exam_gen.radvakt(lang)
    assert _koder(fel) == ["radlangd"]
    assert "Dela meningen i två" in fel[0]["message"]
    kort = _prov(_u("Bestäm den högsta farten.\nBromssträckan är högst "
                    "$45$ m.", [0, 1, 0]))
    assert exam_gen.radvakt(kort) == []
    # Matten räknas som den syns: ett bråk är så brett som sin längsta del.
    assert exam_gen._synlig_matte("\\dfrac{x}{0{,}05}") == 5
    # Det nya pappret får en mening per rad, facit står orört.
    exam = _prov(_u("Leo kör lastbil. Han ska köra $342$ km.", [1, 0, 0],
                    losning="Svar: 5 h. Det tar 5 h."))
    exam_gen.mening_per_rad(exam)
    assert exam["uppgifter"][0]["text"] == ("Leo kör lastbil.\nHan ska köra "
                                            "$342$ km.")
    assert exam["uppgifter"][0]["losning"] == "Svar: 5 h. Det tar 5 h."


def test_instruktionen_bar_textens_form():
    i = exam_gen.INSTRUCTION
    assert "TEXTENS FORM" in i
    assert "«Skriv 307 km i grundpotensform.»" in i
    assert f"högst {exam_gen.MENING_RAD_TAK} tecken" in i
    assert "ETT FORMBYTE PER E-POÄNG" in i
    assert "«Täljaren ska vara ett heltal.»" in i
    assert "Blir det samma procent om timpriset är 600 kr?" in i
    assert "«kvadratiska klinkerplattor»" in i
    # Det gamla exemplet på en förtydligande mening var just den sortens
    # godtycklighetsmening hon fällde.
    assert "Talet x kan vara vilket tal som helst" not in i
    assert "Talet x kan vara vilket tal som helst" not in \
        elevlasare.build_elevlasare_prompt([])
    assert "FRÅGAN omskriven med villkoret inbyggt" in \
        elevlasare.build_elevlasare_prompt([])


# ── C. TIDEN ─────────────────────────────────────────────────────────────

def test_papperet_pa_taket_mats_med_hennes_rakning():
    """20 poäng på 60 minuter i takt 3 är hennes tak. Efterkontrollen sa
    «räknas till 70», tidsmodellens uppgiftsterm och overhead ovanpå."""
    summor = {"total": 20, "e": 8, "c": 7, "a": 5}
    assert exam_spec.poang_tak_for(60, 3) == 20
    assert exam_spec.papperstid(summor, 10, 3) == 60
    assert exam_spec.tidsatgang(summor, 10, takt=3) == 70     # den gamla
    # Utan takt på pappret: tidsmodellen med husets takt, som förut.
    assert exam_spec.papperstid(summor, 10, None) == exam_spec.tidsatgang(
        summor, 10, takt=exam_spec.takt_for("prov"))
    # Tidsvakten vid beställningen tiger när taket håller.
    assert exam_spec.tidsvakt(10, 60, "prov", takt=3, kurs="Ma1a") == []


def test_efterkontrollens_tidsfynd_foljer_taket():
    from app.web import routes_exam

    class Doc:
        tid_min, takt, uppgifter = 60, 3.0, [None] * 10

    assert routes_exam._tidfynd(Doc, {"total": 20}, "prov") == []
    fynd = routes_exam._tidfynd(Doc, {"total": 21}, "prov")
    assert [f["kod"] for f in fynd] == ["tid"]
    assert "rymmer det 20 poäng" in fynd[0]["text"]
    assert "21 poäng, alltså 63 minuter" in fynd[0]["text"]


def test_stegvakten_hojer_inte_poangen_pa_taket():
    """Lagningen gav uppgift 9 en fjärde C-poäng och pappret 21 p på ett
    20-poängspass."""
    u = _u("Beräkna.", [0, 1, 0], typ="problem", del_="C",
           losning="$a = 1$ ger $b = 2$ ger $c = 3$ ger $d = 4$.")
    exam = _prov(u)
    utan = np_vakter.stegvakt(exam)
    assert "Höj poängen" in utan[0]["message"]
    pa = np_vakter.stegvakt(exam, poang_tak=1)
    assert "höj INTE poängen" in pa[0]["message"]


# ── SITUATIONEN (exam 129 mot exam 126) ─────────────────────────────────

TANDSTICKOR_126 = ("Figurerna nedan är byggda av tändstickor. Tabellen visar "
                   "antalet tändstickor i de tre första figurerna. Teckna ett "
                   "uttryck för antalet tändstickor i figur $n$.")


def test_samma_situation_fran_en_annan_klass_falls():
    """«Den här har ju nästan identisk uppgift med provet som min naturklass
    ska ha.»"""
    u7 = _u("Figurerna nedan är byggda av tändstickor. Tabellen visar antalet "
            "tändstickor i de tre första figurerna.\nTeckna ett uttryck för "
            "antalet tändstickor i figur $n$.", [0, 0, 2], typ="problem")
    u7["tabell"] = {"rubriker": ["Figur", "1", "2", "3"],
                    "rader": [["Antal tändstickor", "4", "12", "24"]]}
    tidigare = [TANDSTICKOR_126, "Beräkna $3 + 4$.",
                "Ett hårstrå är ungefär 80 $\\mu$m tjockt.",
                "Mönstret har 4, 12 och 24 prickar i de tre första figurerna."]
    fel = exam_gen.situationsvakt(_prov(_u("Beräkna $5 + 6$.", [1, 0, 0]), u7),
                                  tidigare)
    assert [f["path"] for f in fel] == ["uppgift 2"]
    assert "samma situation («tändstick…»)" in fel[0]["message"]
    assert "Byt situationen, inte bara talen" in fel[0]["message"]
    # Samma figurmönster med ny sak: talserien räcker.
    klossar = copy.deepcopy(u7)
    klossar["text"] = "Figurerna nedan är torn av träklossar."
    klossar["tabell"]["rader"] = [["Antal klossar", "4", "12", "24"]]
    fel = exam_gen.situationsvakt(_prov(klossar), tidigare)
    assert "samma tal i samma ordning" in fel[0]["message"]
    # Ny sak och nya tal: tyst. Ingen historik: tyst (kassetteregeln).
    klossar["tabell"]["rader"] = [["Antal klossar", "1", "3", "6"]]
    assert exam_gen.situationsvakt(_prov(klossar), tidigare) == []
    assert exam_gen.situationsvakt(_prov(u7), []) == []


def test_undvik_listan_namnger_sakerna_kursen_redan_haft():
    text = exam_gen.build_variation([TANDSTICKOR_126])
    assert "SAKER som kursens papper redan har handlat om" in text
    assert "tändstickor" in text
    assert exam_gen.build_variation([]) == ""


def test_underlaget_laser_hela_kursen_i_alla_klasser(tmp_path):
    """126 (NA26F) var taggad med andra punkter än 129:s beställning (TE26A),
    och koderna smalnade förut av till de taggade pappren."""
    conn = db.connect(tmp_path / "t.db")
    try:
        cid = db.get_or_create_course(conn, "Matematik, nivå 1c")

        def prov(text):
            return {"titel": "Prov", "kurs": "Matematik, nivå 1c",
                    "hjalpmedel": "-",
                    "uppgifter": [{"text": text, "formaga": "P",
                                   "typ": "rutin", "poang": [1, 0, 0],
                                   "losning": "x", "bedomning": "y"}]}

        db.create_exam(conn, exam=prov(TANDSTICKOR_126), typ="prov",
                       course_id=cid)
        db.create_exam(conn, exam=prov("Lös olikheten $2x + 1 < 9$."),
                       typ="prov", course_id=cid)
        texter = db.tidigare_uppgiftstexter(conn, cid,
                                            koder=["G25-M1C-ALG-6"])
        assert TANDSTICKOR_126 in texter
        assert "Lös olikheten $2x + 1 < 9$." in texter
    finally:
        conn.close()
