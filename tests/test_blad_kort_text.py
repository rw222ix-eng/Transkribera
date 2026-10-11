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


def test_raden_efter_fragan_namns_i_fyndet():
    """Blad 183:6 (2026-10-10): «Svara med minst en decimal.» och «Förklara
    kort …» efter frågan gjorde frågan till bakgrund, och två omskrivningar
    strök fakta utan att komma under taket. Fyndet pekar ut raden."""
    text = ("En fotboll rymmer $5{,}6$ liter luft.\nBollens volym i cm$^3$ ges "
            "av formeln: $V = \\dfrac{4\\pi r^3}{3}$, där $r$ är radien i cm.\n"
            "Bestäm den minsta kantlängd som en kubformad kartong för bollen "
            "kan ha.\nSvara med minst en decimal.\nFörklara kort vad du gör i "
            "varje steg.")
    fynd = _fynd(_blad(_uppg(text, (0, 3, 0))))
    assert fynd and "«Svara med minst en decimal.» står efter den" in fynd[0][1]
    # Utan rader efter frågan säger fyndet inget om dem.
    assert "står efter den" not in _fynd(_blad(_uppg(DIKE_FORE, (0, 2, 0))))[0][1]


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


def test_pastaendet_ar_fragans_foremal():
    """Provets form (131:5a): ett faktum, påståendet, frågan."""
    u = _uppg("Ett släp klarar högst $500$ kg.", (0, 0, 0), losning="",
              bedomning="",
              deluppgifter=[_del("Hassan lastar $18$ balkar som väger $19$ kg "
                                 "styck.\nHan påstår att släpet klarar lasten."
                                 "\n\nAvgör om Hassan har rätt.")])
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


def test_bladet_far_provets_form():
    """Provgranskningens domar 2026-09-26 på bladet: avgör-frågan säger vad
    eleven ska visa, uttrycksformen står i frågan, figurerna visar uttrycket
    och räknarmeningen står aldrig i uppgiften."""
    fel = _blad(
        _uppg("Leo påstår att $x = 3$ löser $x^2 = 9$.\n\nAvgör om Leo har rätt."),
        _uppg("Beräkna $B$.\nSvara med ett uttryck i $A$."),
        _uppg("Tabellen visar figurerna.\n\nTeckna ett uttryck för figur $n$ "
              "och motivera det."),
        _uppg("Beräkna volymen.\nRedovisa kort på pappret hur du har använt "
              "din räknare."))
    fynd = exam_gen.bladets_formvakt(fel)
    assert [f["path"] for f in fynd] == [f"uppgift {n}" for n in (1, 2, 3, 4)]
    assert {f["code"] for f in fynd} == {"provform"}
    ratt = _blad(
        _uppg("Leo påstår att $x = 3$ löser $x^2 = 9$.\n\nAvgör om Leo har rätt "
              "och förklara varför."),
        _uppg("Lea löser $2x = 8$ och får $x = 3$.\n\nAvgör med en beräkning om "
              "Lea har räknat rätt."),
        _uppg("Bestäm $B$ som ett uttryck i $A$."),
        _uppg("Tabellen visar figurerna.\n\nTeckna ett uttryck för figur $n$. "
              "Visa med hjälp av figurerna hur du kom fram till uttrycket."))
    assert exam_gen.bladets_formvakt(ratt) == []
    assert "provform" in exam_gen.OVNINGSKODER
    assert "provform" in routes_exam._ATGARD
    assert "provform" in {f["code"] for f in exam_gen.ovningsvakter(fel)}


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


def test_uppmaningen_ar_inget_namn():
    """Prov 126:3: formeln sist på raden utan punkt, «Bestäm» på nästa."""
    prov = {"uppgifter": [{"text": "Talet $n$ är ett heltal.\n$a^{2n} = a^{k}$\n"
                                   "Bestäm $k$ som ett uttryck i $n$.",
                           "poang": [0, 0, 1], "typ": "rutin"},
                          {"text": "Noah köper golvlister.", "poang": [1, 0, 0],
                           "typ": "rutin"}]}
    namn = exam_gen.provets_namn_och_sammanhang(prov)["namn"]
    assert "Bestäm" not in namn and "Noah" in namn


def test_bladets_ordtak_ar_textmangdvakten():
    """Blad 221:9 (IndA inför prov 215): ett ekvationssystem med decimaler.
    Ordvakten räknar «$1{,}2x$» som tre ord, textmängdvakten som ett. Bladets
    efterkontroll mäter som skrivningen, med textmängdvakten."""
    u = _uppg("Räknare tillåten. Linjerna (1) och (2) skär varandra.\n"
              "(1) $1{,}2x + 0{,}5y = 4{,}6$\n(2) $0{,}8x - 0{,}5y = 1{,}4$",
              poang=(0, 0, 0), deluppgifter=[_del(
                  "Hugo adderar ekvationerna och får $2x = 3{,}2$.\n"
                  "Avgör om Hugo har räknat rätt och förklara varför.")])
    exam = _blad(u)
    assert exam_gen.ordvakt(exam)
    marke = exam_gen.ORDVAKTENS_MARKE
    assert any(marke in f["text"] for f in routes_exam._sprakfynd(exam, "prov"))
    assert not any(marke in f["text"]
                   for f in routes_exam._sprakfynd(exam, "prov", blad=True))
    assert exam_gen.textmangdvakt(exam) == []


def test_forklaringen_efter_fragan_raknas_inte():
    """Rickard 2026-10-11: på bladen får förklaringar för svag svenska gå över
    taket. Blad 223:6 fick förklaringen av allmän form efter frågan."""
    fraga = ("Linjen $L$ är parallell med linjen $2{,}4x - 1{,}6y + 4 = 0$.\n"
             "$L$ och linjen $y = -x + 4$ skär $x$-axeln i samma punkt.\n"
             "Bestäm ekvationen för $L$ i allmän form.")
    forkl = ("\nI allmän form står alla termer i vänsterledet och 0 i "
             "högerledet.\nEtt exempel är $5x - 2y + 7 = 0$.")
    assert _fynd(_blad(_uppg(fraga + forkl, (0, 3, 0)))) == []
    # Ett krav efter frågan räknas fortfarande (blad 183:6).
    krav = "\nSvara med minst en decimal.\nFörklara kort vad du gör i varje steg."
    assert exam_gen._utan_forklaring_efter_fragan(fraga + krav) == fraga + krav


def test_vakterna_gar_inte_i_ring_pa_forklaringen():
    """Blad 223:6 (2026-10-11): radlängden delade förklaringen i två meningar,
    språkvakten fällde då «termer», och dolt-krav-raden räknades som ett
    andra uppdrag. Tre omskrivningar gick runt i ringen."""
    text = ("Linjen $L$ är parallell med linjen $2{,}4x - 1{,}6y + 4 = 0$.\n"
            "$L$ och linjen $y = -x + 4$ skär $x$-axeln i samma punkt.\n"
            "Bestäm ekvationen för $L$ i allmän form.\n"
            "I allmän form står alla termer i vänsterledet.\n"
            "Högerledet är 0, som i $5x - 2y + 7 = 0$.\n"
            "Skriv din lösning steg för steg så att någon annan kan följa hur "
            "du räknar.")
    exam = _blad(_uppg(text, (0, 3, 0)))
    assert exam_gen.facktermsvakt(exam) == []
    assert exam_gen.uppdragsvakt(exam) == []
    assert _fynd(exam) == []
    # Utan exemplet fälls ordet som förut.
    utan = _blad(_uppg("Bestäm ekvationen i allmän form.\nI allmän form står "
                       "alla termer i vänsterledet."))
    assert exam_gen.facktermsvakt(utan)
    # Två riktiga uppdrag fälls som förut.
    tva = _blad(_uppg("Linjen går genom $(1,\\ 2)$.\nBestäm $k$.\nRita linjen.",
                      (0, 2, 0)))
    assert exam_gen.uppdragsvakt(tva)


def test_ett_visat_fackord_behover_inget_nytt_exempel():
    """Blad 228:6b (2026-10-11): exemplet med procentenheter stod i meningen
    före frågan, och språkvakten fällde ordet i frågan."""
    text = ("Banken påstår att räntan höjs med 1 %.\nEn ränta som går från 10 % "
            "till 12 % höjs med 2 procentenheter.\nAvgör om banken ska skriva "
            "1 % eller 1 procentenhet och förklara varför.")
    assert exam_gen._fackord_utan_exempel(text) == []
    # Står ordet först utan exempel fälls det som förut.
    assert exam_gen._fackord_utan_exempel(
        "Ange skillnaden i procentenheter.\nRäntan går från 10 % till 12 %.")


def test_raden_om_vad_bokstaven_betyder_ar_inget_faktum():
    """Blad 231:4 (2026-10-11): radlängden delade «…, där $t$ är tiden …» i
    två meningar, och textmängdvakten fällde stammen för tre meningar."""
    u = _uppg("Sara dricker en kopp kaffe.\nKoffeinet i hennes kropp i mg ges "
              "av: $K = 160 \\cdot 0{,}87^{t}$.\nHär är $t$ tiden i timmar efter "
              "att hon drack kaffet.", (0, 0, 0), deluppgifter=[
                  _del("Bestäm hur många procent koffeinet sjunker med per "
                       "minut.", (0, 0, 1))])
    assert _fynd(_blad(u)) == []
    # Tre faktameningar i stammen fälls som förut.
    u2 = _uppg("Sara dricker kaffe.\nHon dricker te.\nHon äter en bulle.",
               (0, 0, 0), deluppgifter=[_del("Beräkna summan.", (0, 0, 1))])
    assert _fynd(_blad(u2))


def test_deluppgiften_lases_med_sin_stam():
    """Blad 228:6 (2026-10-11): stammen visade procentenheter med ett exempel,
    och språkvakten fällde ordet i 6b."""
    u = _uppg("Räntan höjs från $4\\,\\%$ till $5\\,\\%$, alltså med $1$ "
              "procentenhet.", (0, 0, 0), deluppgifter=[
                  _del("Hur många procentenheter höjs räntan nästa gång?",
                       (0, 1, 0))])
    assert exam_gen.facktermsvakt(_blad(u)) == []
    u2 = _uppg("Räntan höjs.", (0, 0, 0), deluppgifter=[
        _del("Hur många procentenheter höjs räntan?", (0, 1, 0))])
    assert exam_gen.facktermsvakt(_blad(u2))
