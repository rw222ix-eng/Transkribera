"""Kort text på bladet inför provet (Rickard 2026-09-26).

«Proven har oftast lite text och är i stället uppdelade i deluppgifter,
vilket gör informationen lättare att ta in.» Domen blev en regel i prompten
(INFOR_TEXT), en vakt (textmangdvakt, i ovningsvakter och efterkontrollen)
och de här testerna.
"""
from app import exam_gen, exam_spec
from app.web import routes_exam


def _uppg(text, poang=(1, 0, 0), **k):
    return dict({"del": None, "formaga": "P", "typ": "problem",
                 "poang": list(poang), "text": text, "losning": "5",
                 "bedomning": "+1 E korrekt svar", "drillar": 1}, **k)


def _del(text, poang=(1, 0, 0)):
    return {"text": text, "poang": list(poang), "losning": "5",
            "bedomning": "+1 E korrekt svar", "typ": "problem"}


def _blad(*uppgifter):
    exam = {"titel": "Inför provet", "kurs": "Matematik, nivå 1c",
            "klass": "NA26F", "hjalpmedel": "", "uppgifter": list(uppgifter)}
    doc, fel = exam_spec.validate_exam_json(exam, "arbetsblad")
    assert doc is not None, fel
    return exam


def _fynd(exam):
    return [(f["path"], f["message"]) for f in exam_gen.textmangdvakt(exam)]


# Blad 137:4 som det såg ut 25/9 och som det skrevs om 26/9.
DIKE_FORE = ("Ett dike längs ett hus ska fyllas med makadam, alltså krossad "
             "sten.\nDiket är $12$ m långt, $40$ cm brett och $50$ cm djupt.\n"
             "De översta $10$ cm fylls med jord och resten med makadam.\nMan "
             "köper $20$ % mer makadam än volymen, eftersom makadamen packas "
             "ihop.\nMakadam säljs bara i hela kubikmeter.\n\nHur många "
             "kubikmeter makadam ska köpas?")
DIKE_EFTER = ("Ett dike ska fyllas med makadam, alltså krossad sten.\nDiket är "
              "$12$ m långt, $40$ cm brett och $50$ cm djupt.\nDe översta $10$ "
              "cm fylls med jord.\nMan köper $20$ % extra makadam.\n\nHur många "
              "hela kubikmeter makadam ska köpas?")


def test_c_problemet_far_provets_tak_och_delas_inte():
    fore = _fynd(_blad(_uppg(DIKE_FORE, (0, 2, 0))))
    assert [p for p, _ in fore] == ["uppgift 1"]
    assert "ledda steg" in fore[0][1] and "C-nivå" in fore[0][1]
    assert _fynd(_blad(_uppg(DIKE_EFTER, (0, 2, 0)))) == []


def test_e_uppgiften_har_bladets_lagre_tak():
    """Samma text som går igenom på C fälls på E: E-uppgiften får delas."""
    fynd = _fynd(_blad(_uppg(DIKE_EFTER, (1, 0, 0))))
    assert fynd and "Dela den i a) och b)" in fynd[0][1]


def test_stammen_ger_sammanhanget_och_deluppgiften_sitt_faktum():
    lang = _uppg("Jorden på en tomt innehåller olja.\nJorden får innehålla högst "
                 "$0{,}5$ % olja.\nVarje kilogram innehåller $2\\,000$ mg olja.",
                 (0, 0, 0), losning="", bedomning="",
                 deluppgifter=[_del("Hur många gram olja får ett kilogram "
                                    "jord innehålla?"),
                               _del("Hur många procent av jorden är olja?")])
    assert [p for p, _ in _fynd(_blad(lang))] == ["uppgift 1"]
    kort = _uppg("Jorden på en tomt innehåller olja.", (0, 0, 0), losning="",
                 bedomning="",
                 deluppgifter=[_del("Jorden får innehålla högst $0{,}5$ % olja."
                                    "\n\nHur många gram olja får ett kilogram "
                                    "jord innehålla?"),
                               _del("Varje kilogram innehåller $2\\,000$ mg "
                                    "olja.\n\nHur många procent av jorden är "
                                    "olja?")])
    assert _fynd(_blad(kort)) == []


def test_deluppgiften_far_en_mening_fakta():
    u = _uppg("Ali gjuter en platta.", (0, 0, 0), losning="", bedomning="",
              deluppgifter=[_del("Plattan är $3$ m lång.\nDen är $2$ m bred."
                                 "\n\nHur stor är arean?")])
    fynd = _fynd(_blad(u))
    assert [p for p, _ in fynd] == ["uppgift 1a"]


def test_raknarmarket_och_svara_i_raknas_inte():
    """Räknarmärket sätter appen själv, och «Svara i …» efter frågan är en del
    av frågan, inte ett faktum före den."""
    u = _uppg("Utan räknare. Ali gjuter en platta.", (0, 0, 0), losning="",
              bedomning="",
              deluppgifter=[_del("Till $6$ m$^{3}$ går det åt $12\\,000$ kg "
                                 "torrbetong.\n\nHur mycket går åt till $1$ "
                                 "m$^{3}$?\nSvara i grundpotensform.")])
    assert _fynd(_blad(u)) == []


def test_decimaltalet_ar_ett_ord():
    """«0{,}3» blir «0 , 3» i _rentext. Bladets tak mäter texten, inte talen:
    nio decimaltal i en mening är fortfarande en kort mening."""
    tal = " och ".join(f"${k}{{,}}5$" for k in range(1, 10))
    u = _uppg(f"Ali mäter sidorna {tal}.\n\nBeräkna summan.")
    assert g_ord(u["text"]) > exam_gen.BLAD_ORD_FORE_FRAGAN
    assert _fynd(_blad(u)) == []


def g_ord(text):
    return exam_gen._ord_fore_fragan(text)


def test_vakten_star_i_bladets_kontroller():
    lang = _blad(_uppg(DIKE_FORE, (1, 0, 0)))
    assert "textmangd" in exam_gen.OVNINGSKODER
    assert "textmangd" in {f["code"] for f in exam_gen.ovningsvakter(lang)}
    assert "textmangd" in routes_exam._ATGARD
    prov = {"uppgifter": [{"del": "C", "typ": "problem", "poang": [1, 0, 0],
                           "text": "Beräkna.", "formaga": "P"}]}
    koder = {f["kod"] for f in routes_exam._ovningsfynd(lang, prov, "arbetsblad")}
    assert "textmangd" in koder
    # Tyst på andra papper och utan provet.
    assert not routes_exam._ovningsfynd(lang, None, "arbetsblad")
    assert not routes_exam._ovningsfynd(lang, prov, "prov")


def test_prompten_bar_regeln_med_vaktens_tal():
    prov = {"uppgifter": [{"del": "B", "typ": "problem", "poang": [1, 0, 0],
                           "text": "Beräkna $2 + 3$.", "formaga": "P",
                           "losning": "5"}]}
    block = exam_gen.build_infor_prov(exam_gen.provslots(prov), [], 6)
    assert "KORT TEXT, SOM PROVET" in block
    assert f"Högst {exam_gen.BLAD_ORD_FORE_FRAGAN} ord före frågan" in block
    assert "delas inte i ledda steg" in block
    assert "som en egen deluppgift" in block
    # Kassettregeln: utan prov är blocket tomt.
    assert exam_gen.build_infor_prov([], [], 6) == ""
