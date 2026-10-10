"""Lärarens dom 2026-10-02 över tre blad till BA26B (exam 153–155).

1. Delfrågorna a), b), c) stod i uppgiftens text, och svarsraderna hamnade
   samlade längst ner (155:6). Varje delfråga ska vara en deluppgift med en
   svarslinje direkt under sig. Normaliseringen i exam_gen
   (delfragor_till_deluppgifter, i _validate och ovningspappret_stadat) gör
   om dem; poäng som inte går att dela blir ett fynd i reparationsrundan.
2. Språket på 154:1 gick inte att förstå för elever med svag svenska.
   Regeln står i arbetsbladets prompt (build_sprak_blad), fackorden utan
   exempel räknas (facktermsvakt) och elevläsaren läser bladet som en elev
   med svag svenska.

Texterna nedan är de verkliga ur transkribera.db (exam_versions 726 och 728).
"""
import copy

from app import elevlasare, exam_gen, exam_spec
from app.web import routes_exam

# 155:6, version 728.
NEG_6 = {
    "typ": "rutin", "formaga": "P", "poang": [3, 0, 0], "drillar": 1,
    "text": "Utan räknare. a) Beräkna $-7 - 5$.\nb) Beräkna $4 - (-12)$.\n"
            "c) Beräkna $-3 - (-9)$.",
    "svarsfalt": ["a)", "b)", "c)"],
    "losning": "a) $-12$\nStarta på $-7$ och gå 5 steg åt vänster\n"
               "$-7 - 5 = -12$ ← längre ner under noll\nb) $16$\n"
               "$4 - (-12) = 4 + 12 = 16$ ← minus minus blir plus\nc) $6$\n"
               "$-3 - (-9) = -3 + 9 = 6$ ← minus minus blir plus",
    "bedomning": "+1 E korrekt svar på a) ($-12$)\n"
                 "+1 E korrekt svar på b) ($16$)\n"
                 "+1 E korrekt svar på c) ($6$)",
    "innehall": ["negativa tal", "subtraktion"]}

# 155:1: tabellen på stammen, första bedömningsraden nämner ingen del.
NEG_1 = {
    "typ": "rutin", "formaga": "B", "poang": [2, 0, 0], "drillar": 1,
    "text": "Utan räknare. Tabellen nedan visar temperaturen på ett bygge fyra "
            "morgnar i januari.\na) Skriv temperaturerna i ordning från den "
            "lägsta till den högsta.\nb) Beräkna hur många grader temperaturen "
            "steg från måndag till tisdag.",
    "tabell": {"rubriker": ["Morgon", "Måndag", "Tisdag", "Onsdag", "Torsdag"],
               "rader": [["Temperatur (°C)", "$-4$", "$2$", "$-1$", "$-6$"]]},
    "svarsfalt": ["a)", "b)"],
    "losning": "a) $-6,\\ -4,\\ -1,\\ 2$\nb) 6 grader\n$2 - (-4) = 2 + 4 = 6$",
    "bedomning": "+1 E korrekt ordning: $-6,\\ -4,\\ -1,\\ 2$\n"
                 "+1 E korrekt svar på b): 6 grader",
    "innehall": ["negativa tal", "tallinjen", "skillnad mellan tal"]}

# 155:7: en problemuppgift, b) över två rader.
NEG_7 = {
    "typ": "problem", "formaga": "PL", "poang": [2, 0, 0], "drillar": 1,
    "text": "Utan räknare. Höjderna mäts från markytan.\nEn stödmur går från "
            "$-0{,}4$ m till $0{,}9$ m.\na) Hur hög är muren?\nb) Ett rör "
            "ligger $0{,}3$ m under murens fot.\nVilken höjd har röret?",
    "svarsfalt": ["a)", "b)"],
    "notis": "Tips: Rita en lodrät tallinje med markytan vid 0.",
    "losning": "a) $1{,}3$ m\n$0{,}9 - (-0{,}4) = 0{,}9 + 0{,}4 = 1{,}3$ ← "
               "minus minus blir plus\nb) $-0{,}7$ m\n$-0{,}4 - 0{,}3 = "
               "-0{,}7$ ← under betyder längre ner",
    "bedomning": "+1 E korrekt svar på a) (1,3 m)\n"
                 "+1 E korrekt svar på b) ($-0{,}7$ m)",
    "innehall": ["negativa tal", "decimaltal", "skillnad mellan tal"]}

# 154:1, version 726: lärarens exempel på språket eleverna inte förstår.
BRAK_1 = {
    "formaga": "B", "typ": "rutin", "poang": [2, 0, 0], "drillar": 2,
    "text": "Utan räknare. Skriv längderna som bråk med nämnaren 4.\nSkriv "
            "hela längden som ett enda bråk utan heltal framför.\nTill "
            "exempel kan $1\\tfrac{1}{3}$ skrivas $\\tfrac{4}{3}$.\n"
            "a) $\\tfrac{1}{2}$ m\nb) $1\\tfrac{1}{2}$ m",
    "svarsfalt": ["a)", "b)"], "enhet": "m",
    "innehall": ["bråk i blandad form"],
    "losning": "a) $\\tfrac{2}{4}$\n$\\tfrac{1}{2} = \\tfrac{2}{4}$ ← gånger "
               "2 uppe och nere\nb) $\\tfrac{6}{4}$\n$1 = \\tfrac{4}{4}$ ← en "
               "hel är fyra fjärdedelar\n$\\tfrac{4}{4} + \\tfrac{2}{4} = "
               "\\tfrac{6}{4}$",
    "bedomning": "+1 E korrekt svar $\\tfrac{2}{4}$ m i a)\n"
                 "+1 E korrekt svar $\\tfrac{6}{4}$ m i b)"}

# 154:2: «blandad form» utan exempel.
BRAK_2 = {
    "formaga": "P", "typ": "rutin", "poang": [1, 0, 0], "drillar": 2,
    "text": "Utan räknare. Beräkna $2 - \\tfrac{3}{4}$.\nSvara i blandad form.",
    "innehall": ["bråk i blandad form"],
    "losning": "$1\\tfrac{1}{4}$", "bedomning": "+1 E korrekt svar $1\\tfrac{1}{4}$"}


def _blad(*uppgifter, typ="arbetsblad"):
    return {"titel": "Negativa tal", "kurs": "Matematik, nivå 1a",
            "klass": "BA26B", "hjalpmedel": "Utan räknare.",
            "uppgifter": [copy.deepcopy(u) for u in uppgifter]}


def _gor_om(*uppgifter, typ="arbetsblad"):
    exam = _blad(*uppgifter)
    fel = exam_gen.delfragor_till_deluppgifter(exam, typ)
    return exam, fel


# ── 1. DELFRÅGORNA ────────────────────────────────────────────────────────

def test_155_6_blir_tre_deluppgifter_med_var_sin_poang_och_facit():
    exam, fel = _gor_om(NEG_6)
    assert fel == []
    u = exam["uppgifter"][0]
    assert u["poang"] == [0, 0, 0]
    # Samma uppmaning på alla tre lyfts till stammen, som 155:8 efter
    # lärarens omskrivning: «Beräkna.» och uttrycken under.
    assert u["text"] == "Utan räknare. Beräkna."
    assert "svarsfalt" not in u
    delar = u["deluppgifter"]
    assert [d["text"] for d in delar] == ["$-7 - 5$", "$4 - (-12)$",
                                          "$-3 - (-9)$"]
    assert [d["poang"] for d in delar] == [[1, 0, 0]] * 3
    assert delar[0]["losning"].startswith("$-12$\nStarta på $-7$")
    assert delar[2]["losning"] == "$6$\n$-3 - (-9) = -3 + 9 = 6$ ← minus minus blir plus"
    assert [d["bedomning"] for d in delar] == [
        "+1 E korrekt svar ($-12$)", "+1 E korrekt svar ($16$)",
        "+1 E korrekt svar ($6$)"]


def test_155_6_validerar_med_deluppgifterna():
    exam, _ = _gor_om(NEG_6)
    doc, fel = exam_spec.validate_exam_json(exam, "arbetsblad")
    assert doc is not None, fel
    assert not [f for f in fel if f["code"] == "stam"]


def test_154_1_far_enheten_pa_varje_del_och_stammen_star_kvar():
    exam, fel = _gor_om(BRAK_1)
    assert fel == []
    u = exam["uppgifter"][0]
    assert u["text"].endswith("skrivas $\\tfrac{4}{3}$.")
    assert "enhet" not in u and "svarsfalt" not in u
    delar = u["deluppgifter"]
    assert [d["text"] for d in delar] == ["$\\tfrac{1}{2}$ m",
                                          "$1\\tfrac{1}{2}$ m"]
    assert [d["enhet"] for d in delar] == ["m", "m"]
    assert delar[1]["bedomning"] == "+1 E korrekt svar $\\tfrac{6}{4}$ m"


def test_155_1_bedomningen_i_ordning_nar_forsta_raden_inte_namner_delen():
    exam, fel = _gor_om(NEG_1)
    assert fel == []
    u = exam["uppgifter"][0]
    assert u["tabell"] == NEG_1["tabell"]          # datat står på stammen
    assert u["text"].startswith("Utan räknare. Tabellen nedan")
    assert [d["bedomning"] for d in u["deluppgifter"]] == [
        "+1 E korrekt ordning: $-6,\\ -4,\\ -1,\\ 2$",
        "+1 E korrekt svar: 6 grader"]


def test_155_7_problemuppgiften_far_en_svarsrad_under_varje_del():
    exam, fel = _gor_om(NEG_7)
    assert fel == []
    u = exam["uppgifter"][0]
    assert u["notis"] == NEG_7["notis"]
    delar = u["deluppgifter"]
    assert delar[1]["text"] == ("Ett rör ligger $0{,}3$ m under murens fot.\n"
                                "Vilken höjd har röret?")
    # Redovisningsuppgift: svarslinjen står under delen, lösbladet en gång.
    assert [d.get("svarsfalt") for d in delar] == [["Svar"], ["Svar"]]


def test_normaliseringen_ar_idempotent():
    exam, _ = _gor_om(NEG_6, NEG_7, BRAK_1)
    en_gang = copy.deepcopy(exam)
    assert exam_gen.delfragor_till_deluppgifter(exam, "arbetsblad") == []
    assert exam == en_gang


def test_odelbar_poang_blir_ett_fynd_och_uppgiften_star_orord():
    """Gruppuppgiften 13:1:s bedömning går inte att dela på delarna."""
    u = dict(NEG_6, bedomning="+1 E minst två korrekta svar\n"
                              "+1 E alla tre korrekta", poang=[2, 0, 0])
    exam, fel = _gor_om(u)
    assert exam["uppgifter"][0] == u
    assert [f["code"] for f in fel] == [exam_gen.DELFRAGEKOD]
    assert fel[0]["path"] == "uppgifter[0].text"
    assert "+1 E korrekt svar i a)" in fel[0]["message"]


def test_facit_utan_bokstaver_blir_ett_fynd():
    """Blad 102:1: lösningen märker inte delarna."""
    u = dict(NEG_7, losning="Muren är $1{,}3$ m. Röret ligger på $-0{,}7$ m.")
    exam, fel = _gor_om(u)
    assert "deluppgifter" not in exam["uppgifter"][0]
    assert "lösningen märker inte" in fel[0]["message"]


def test_poang_som_inte_gar_ihop_blir_ett_fynd():
    exam, fel = _gor_om(dict(NEG_6, poang=[4, 0, 0]))
    assert "deluppgifter" not in exam["uppgifter"][0]
    assert "(4, 0, 0)" in fel[0]["message"]


def test_gruppuppgiften_far_fyndet_i_sin_egen_form():
    u = dict(NEG_6, bedomning="+1 E minst två korrekta\n+1 E alla tre",
             poang=[2, 0, 0])
    _exam, fel = _gor_om(u, typ="gruppuppgift")
    assert "Skriv dem som deluppgifter" in fel[0]["message"]


def test_bokstav_i_matten_eller_mitt_i_meningen_ar_ingen_delfraga():
    for text in ("Bestäm $f(a)$ och $g(b)$ när $a) = 2$.",
                 "Svara på frågan som står i a) och b) i tabellen.",
                 "a) Beräkna $2 + 3$."):
        u = dict(NEG_6, text=text)
        exam, fel = _gor_om(u)
        assert exam["uppgifter"][0] == u and fel == []


def test_tabellens_rader_pa_gruppuppgiften_rors_inte():
    """Gruppuppgiftens ingång (FORLAGA_GRUPP): uttrycken i en tabell med
    raderna a) och b) och svarsfälten «Svar a)», «Svar b)»."""
    u = {"formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
         "text": "Beräkna de två uttrycken i tabellen utan räknare.",
         "tabell": {"rubriker": ["Uppgift", "Uttryck"],
                    "rader": [["a)", "$9 + 3 \\cdot 4^2$"], ["b)", "$6$"]]},
         "svarsfalt": ["Svar a)", "Svar b)"],
         "losning": "a) $57$. b) $6$.",
         "bedomning": "+1 E rätt svar i a)\n+1 E rätt svar i b)"}
    exam, fel = _gor_om(u, typ="gruppuppgift")
    assert exam["uppgifter"][0] == u and fel == []


def test_provet_rors_inte():
    exam = _blad(NEG_6)
    assert exam_gen.delfragor_till_deluppgifter(exam, "prov") == []
    assert exam["uppgifter"][0] == NEG_6


def test_validate_gor_om_bladet_och_lagger_fyndet_bland_felen():
    odelbar = dict(NEG_7, bedomning="+2 E båda svaren korrekta")
    exam = _blad(NEG_6, odelbar)
    _doc, fel = exam_gen._validate(exam, "arbetsblad")
    assert exam["uppgifter"][0]["deluppgifter"]
    assert [f["path"] for f in fel if f["code"] == exam_gen.DELFRAGEKOD] == [
        "uppgifter[1].text"]


def test_validate_lamnar_provet_orort():
    exam = _blad(NEG_6)
    exam_gen._validate(exam, "prov")
    assert "deluppgifter" not in exam["uppgifter"][0]


def test_ovningspappret_stadat_gor_om_och_satter_raknarmarket_i_stammen():
    exam = _blad(NEG_6)
    exam["uppgifter"][0]["text"] = exam["uppgifter"][0]["text"].removeprefix(
        "Utan räknare. ")
    exam_gen.ovningspappret_stadat(exam, "arbetsblad")
    u = exam["uppgifter"][0]
    assert u["text"] == "Utan räknare. Beräkna."
    assert len(u["deluppgifter"]) == 3


def test_efterkontrollen_pekar_ut_de_gamla_bladens_uppgifter():
    exam = _blad(BRAK_2, NEG_6, NEG_7)
    sparat = copy.deepcopy(exam)
    fynd = routes_exam._delfragefynd(exam, "arbetsblad")
    assert [(f["kod"], f["nr"]) for f in fynd] == [
        (exam_gen.DELFRAGEKOD, 2), (exam_gen.DELFRAGEKOD, 3)]
    assert exam == sparat                       # räknat på en kopia
    assert routes_exam._delfragefynd(exam, "prov") == []


def test_reglerna_star_i_bladets_och_gruppuppgiftens_prompt_men_inte_provets():
    blad = exam_gen.build_prompt("Matematik 1a", "BA26B", ["Bråk"],
                                 antal=6, profil="arbetsblad")
    grupp = exam_gen.build_prompt("Matematik 1a", "BA26B", ["Bråk"],
                                  antal=4, profil="gruppuppgift")
    prov = exam_gen.build_prompt("Matematik 1a", "BA26B", ["Bråk"],
                                 antal=6, profil="prov")
    assert exam_gen.DELFRAGOR_BLAD in blad
    assert exam_gen.DELFRAGOR_GRUPP in grupp
    assert exam_gen.DELFRAGOR_BLAD not in grupp
    for text in (exam_gen.DELFRAGOR_BLAD, exam_gen.DELFRAGOR_GRUPP,
                 "SPRÅKET (lärarens dom 2026-10-02"):
        assert text not in prov


# ── 2. SPRÅKET ────────────────────────────────────────────────────────────

def test_sprakregeln_ar_starkast_med_inriktning():
    utan = exam_gen.build_sprak_blad("")
    med = exam_gen.build_sprak_blad("Bygg och anläggning")
    assert "Skriv längderna som bråk med nämnaren 4." in utan
    assert "\\tfrac{?}{4}" in utan
    assert "Klassen går Bygg och anläggning" in med
    assert med.startswith(utan.split("Ett förtydligande")[0])
    blad = exam_gen.build_prompt("Matematik 1a", "BA26B", ["Bråk"], antal=6,
                                 profil="arbetsblad",
                                 inriktning="Bygg och anläggning")
    assert med in blad


def test_facktermsvakten_faller_154_1_och_154_2():
    fynd = exam_gen.facktermsvakt(_blad(BRAK_1, BRAK_2))
    assert [f["path"] for f in fynd] == ["uppgift 1", "uppgift 2"]
    assert "«nämnare»" in fynd[0]["message"]
    assert "«blandad form»" in fynd[1]["message"]
    assert all(f["code"] == "begriplighet"
               and exam_gen.SPRAKVAKTENS_MARKE in f["message"] for f in fynd)
    # Slutgrinden räknar om det som ett språkfynd.
    assert exam_gen._raknas_om(fynd[0])


def test_facktermen_med_exempel_i_samma_mening_star():
    ok = dict(BRAK_2, text="Utan räknare. Beräkna $2 - \\tfrac{3}{4}$.\n"
                           "Svara i blandad form, som $1\\tfrac{1}{2}$.")
    visad = dict(BRAK_1, text="I $\\tfrac{3}{4}$ är nämnaren 4.\n"
                              "a) $\\tfrac{1}{2}$ m $= \\tfrac{?}{4}$ m\n"
                              "b) $1\\tfrac{1}{2}$ m $= \\tfrac{?}{4}$ m")
    assert exam_gen.facktermsvakt(_blad(ok, visad)) == []


def test_facktermsvakten_ser_in_i_deluppgifterna():
    exam, _ = _gor_om(BRAK_1)
    exam["uppgifter"][0]["text"] = "Utan räknare."
    exam["uppgifter"][0]["deluppgifter"][1]["text"] = "Skriv som bråk med nämnaren 2."
    fynd = exam_gen.facktermsvakt(exam)
    assert [f["path"] for f in fynd] == ["uppgift 1"]


def test_bladets_vakter_bar_facktermsvakten():
    exam = _blad(BRAK_2)
    kod = [f for f in exam_gen.ovningsvakter(exam) if "«blandad form»" in
           f["message"]]
    assert kod
    assert [f for f in exam_gen.varvsvakter(exam, "arbetsblad")
            if "«blandad form»" in f["message"]]
    assert not [f for f in exam_gen.varvsvakter(exam, "gruppuppgift")
                if "«blandad form»" in f["message"]]


def test_efterkontrollen_visar_fackorden_pa_bladet():
    fynd = routes_exam._facktermfynd(_blad(BRAK_1, BRAK_2), "arbetsblad")
    assert [(f["kod"], f["nr"]) for f in fynd] == [("sprak", 1), ("sprak", 2)]
    assert "nämnare" in fynd[0]["text"]
    assert routes_exam._facktermfynd(_blad(BRAK_1), "gruppuppgift") == []


def _enheter():
    return exam_gen.domarenheter(_blad(BRAK_1))


def test_elevlasaren_laser_bladet_med_svag_svenska():
    p = elevlasare.build_elevlasare_prompt(_enheter(), "Bygg och anläggning",
                                           "arbetsblad")
    assert "SVAG SVENSKA" in p
    assert "Skriv hela längden som ett enda bråk utan heltal framför." in p
    assert "Klassen går Bygg och anläggning" in p
    # Ordvalet fäller fortfarande aldrig i sig.
    assert "aldrig \"nej\" att ordvalet skiljer sig" in p
    assert p.endswith("Svara med enbart JSON.")


def test_elevlasarens_provprompt_ar_byte_for_byte_densamma():
    e = _enheter()
    assert (elevlasare.build_elevlasare_prompt(e, "Bygg", "prov")
            == elevlasare.build_elevlasare_prompt(e, "Bygg"))
    # Varje prov läses med svag svenska sedan Rickards dom 2026-10-10 (BA26B
    # prov 2), oavsett klass.
    for inr in ("", "Bygg"):
        p = elevlasare.build_elevlasare_prompt(e, inr)
        assert "SVAG SVENSKA" in p and "Det här är ett prov," in p


def test_elevlasarens_fynd_pa_bladet_far_byta_beskrivningen_mot_visad_form():
    e = _enheter()
    dom = {e[0]["nr"]: {"omskrivning": "Jag vet inte vad nämnaren är.",
                        "forstar": "nej", "avvikelse": "",
                        "fortydligande": "Skriv «$\\tfrac{1}{2}$ m = ?/4 m».",
                        "sammanhang": "tydligt", "ny_situation": ""}}
    blad = elevlasare.elevlasarfynd(e, dom, "arbetsblad")
    prov = elevlasare.elevlasarfynd(e, dom)
    assert "samma sak visad" in blad[0]["message"]
    assert "Lägg till, stryk inte" in prov[0]["message"]


def test_infor_passet_skickar_bladets_profil_till_elevlasaren(monkeypatch):
    sett = {}

    def fejk(exam, **k):
        sett.update(k)
        return []
    monkeypatch.setattr(elevlasare, "doma_elevlasare", fejk)
    exam = _blad(BRAK_2)
    exam_gen._infor_pass(exam, [], model="m", llm=None, profil="arbetsblad",
                         antal=1, skeleton=None, nummer=None, rounds_used=0,
                         max_rounds=0, prov=_blad(NEG_6), doma=True,
                         inriktning="Bygg och anläggning")
    assert sett.get("profil") == "arbetsblad"


# ── 3. DELUPPGIFTENS EGEN BOKSTAV (NA26F prov 2, exam 156) ───────────────
# Deluppgifterna började med «a) », «b) » …, och pappret skrev «a) a) Lös
# ekvationen …» på uppgift 1, 2, 3, 11 och 12.

def _prov156():
    delar = [{"poang": [1, 0, 0], "text": "a) Lös ekvationen $2x + 3 = 11$.",
              "losning": "$x = 4$", "bedomning": "+1 E korrekt svar"},
             {"poang": [1, 0, 0], "text": "b)  Lös ekvationen $5x = 2x + 9$.",
              "losning": "$x = 3$", "bedomning": "+1 E korrekt svar"},
             {"poang": [1, 0, 0], "text": "a) står kvar, den är inte min.",
              "losning": "$1$", "bedomning": "+1 E korrekt svar"}]
    return {"titel": "Prov 2", "kurs": "Matematik, nivå 1c", "klass": "NA26F",
            "hjalpmedel": "", "uppgifter": [
                {"del": "B", "formaga": "P", "typ": "rutin",
                 "poang": [0, 0, 0], "text": "Lös ekvationerna.",
                 "losning": "", "bedomning": "", "deluppgifter": delar}]}


def test_valideringen_stryker_deluppgiftens_egen_bokstav_pa_provet():
    exam = _prov156()
    exam_gen._validate(exam, "prov")
    assert [d["text"] for d in exam["uppgifter"][0]["deluppgifter"]] == [
        "Lös ekvationen $2x + 3 = 11$.", "Lös ekvationen $5x = 2x + 9$.",
        "a) står kvar, den är inte min."]


def test_valideringen_stryker_den_pa_bladet_ocksa():
    exam = _prov156()
    exam["uppgifter"][0]["del"] = None
    exam_gen._validate(exam, "arbetsblad")
    assert exam["uppgifter"][0]["deluppgifter"][0]["text"].startswith("Lös")


def test_latex_visar_aldrig_dubbel_bokstav_pa_ett_gammalt_papper():
    from app import exam_latex
    doc, fel = exam_spec.validate_exam_json(_prov156(), "prov")
    assert doc is not None, fel
    tex = exam_latex.render_prov(doc)
    assert "a) Lös" not in tex and "b)  Lös" not in tex
    assert "Lös ekvationen" in tex
    assert exam_spec.utan_egen_bokstav("c) Lös", 2) == "Lös"
    assert exam_spec.utan_egen_bokstav("c) Lös", 0) == "c) Lös"


def test_skarmen_stryker_bokstaven_i_franprov():
    import pathlib
    js = (pathlib.Path(__file__).parents[1] / "app" / "web" / "ui"
          / "plan.js").read_text(encoding="utf-8")
    assert "'abcdefghijkl'.charAt(k) + '\\\\)\\\\s*'" in js
