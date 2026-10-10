"""Rickards granskning av prov 163 (TE26A kap 6), 2026-10-08.

Vektorer har namn med pil, intervall hör inte till ett vektorprov, en
deluppgift är kort, och «vågrät», «sluttar» och «i förhållande till» står i
språkvaktens lista. Uppgifterna nedan är de han fällde, ordagrant."""
from app import exam_gen as g


def _prov(*uppgifter, delmoment="Vektorer i koordinatform"):
    ut = []
    for u in uppgifter:
        u = dict(u)
        u.setdefault("delmoment", delmoment)
        u.setdefault("poang", [1, 0, 0])
        ut.append(u)
    return {"kurs": "Matematik, nivå 1c", "uppgifter": ut}


def _koder(fynd):
    return [f["path"] for f in fynd]


def test_vektorer_utan_namn_falls():
    prov = _prov({"text": "Beräkna $(-5,\\ 7) - (8,\\ -3)$."},
                 {"text": "Vektorn $(6,\\ -8)$ är given."},
                 {"text": "Bestäm $k$ så att $(6,\\ -8) + k(-1,\\ 3) = (2,\\ 4)$."})
    assert _koder(g.vektornamnvakt(prov)) == ["uppgift 1", "uppgift 2", "uppgift 3"]


def test_vektorer_med_namn_passerar():
    prov = _prov({"text": "Vektorerna är $\\vec{v} = (-5,\\ 7)$ och $\\vec{u} = (8,\\ -3)$.\n\n"
                          "Beräkna $\\vec{v} - \\vec{u}$."},
                 {"text": "Bestäm talet $k$ så att $\\vec{u} + k\\vec{w} = (2,\\ 4)$."},
                 {"text": "Punkten $P(2,\\ -7)$ ligger i koordinatsystemet."})
    assert g.vektornamnvakt(prov) == []


def test_intervall_utanfor_provets_kapitel():
    prov = _prov({"text": "Bestäm alla $t$ så att $|\\vec{p} + \\vec{q}|$ är högst 10.\nSvara med ett intervall."})
    assert _koder(g.intervallvakt(prov)) == ["uppgift 1"]
    olikheter = _prov({"text": "Svara med ett intervall."}, delmoment="Olikheter och intervall")
    assert g.intervallvakt(olikheter) == []


def test_intervallvakten_tiger_utan_ram():
    blad = {"uppgifter": [{"text": "Svara med ett intervall.", "poang": [1, 0, 0]}]}
    assert g.intervallvakt(blad) == []
    assert _koder(g.intervallvakt(blad, _prov({"text": "x"}))) == ["uppgift 1"]


def test_lang_deluppgift_falls_kort_passerar():
    lang = ("Nu vill Hugo komma i land precis mittemot startplatsen.\nHan riktar kajaken snett åt "
            "vänster, mot strömmen.\nDå pekar den resulterande vektorn rakt mot andra stranden.\n\n"
            "Rita en figur med Hugos hastighet, strömmens hastighet och den resulterande vektorn.\n"
            "Bestäm vinkeln mellan stranden och den riktning Hugo styr kajaken.")
    kort = ("Hugo vill nu komma i land precis mittemot startplatsen.\n\nBestäm vinkeln mellan "
            "stranden och den riktning han ska styra.\nRita en figur med vektorerna.")
    prov = _prov({"text": "Hugo paddlar kajak över en älv.", "poang": [0, 0, 0],
                  "deluppgifter": [{"text": lang, "poang": [0, 1, 1]}, {"text": kort, "poang": [0, 1, 1]}]})
    assert _koder(g.deluppgiftsvakt(prov)) == ["uppgift 1a"]


def test_svara_ord_ur_granskningen():
    prov = _prov({"text": "Taket på en friggebod sluttar åt ett håll.\nI vågrät led är taket 2,4 m."},
                 {"text": "Beräkna kajakens fart i förhållande till stranden."})
    meddelanden = " ".join(f["message"] for f in g.sprakvakt(prov))
    for ord_ in ("«sluttar»", "«vågrät»", "«i förhållande till»"):
        assert ord_ in meddelanden


def test_citatet_slutar_meningen():
    """A-bladet inför BA26B prov 2 (exam 180 v853), uppgift 5 ordagrant."""
    prov = _prov({"text": "Ella påstår: «Per timme har jag alltid mer kvar efter skatt än Noah.» "
                          "Avgör om Ella har rätt och förklara varför."})
    assert g.sprakvakt(prov) == []


def test_reglerna_star_i_prompten():
    for rad in ("VEKTORER HAR ALLTID ETT NAMN MED PIL", "DET CENTRALA INNEHÅLLET STYR",
                "ORD SOM ELEVEN HAR", "BESKRIVS FRÅN PUNKT TILL PUNKT",
                "En deluppgift är kort"):
        assert rad in g.INSTRUCTION


def test_strack_och_tid_i_vektoruppgift():
    ballong = _prov({"text": "En luftballong stiger med 3 m/s. Samtidigt för vinden den åt höger. "
                             "Hur högt har den stigit när den flyttats 200 m längs marken?",
                     "losning": "Vindens fart: 4 m/s\nTid: $200 / 4 = 50$ s\nHöjd: 150"})
    kajak = _prov({"text": "Hugo paddlar över en älv. Vattnet strömmar åt höger.",
                   "deluppgifter": [{"text": "Beräkna storleken av den resulterande vektorn.",
                                     "losning": r"$\sqrt{0{,}5^2 + 1{,}2^2} = 1{,}3$", "poang": [0, 1, 0]}]})
    assert _koder(g.tidsvektorvakt(ballong)) == ["uppgift 1"]
    assert g.tidsvektorvakt(kajak) == []


def test_a_bladets_batuppgift_8_oktober():
    """A-bladet inför prov 163, uppgift 9 (exam 169 version 762), ordagrant."""
    prov = _prov({"text": "Liam ska köra en motorbåt rakt över en å.",
                  "deluppgifter": [{"text": "Beräkna båtens fart rakt över ån.\nSvara i hela m/min.",
                                    "poang": [0, 0, 1]}]})
    ny = _prov({"text": "Liam styr så att den resulterande vektorn $\vec{b} + \vec{s}$ pekar rakt mot andra stranden."})
    assert "«fart rakt över»" in " ".join(f["message"] for f in g.sprakvakt(prov))
    assert not any("fart rakt över" in f["message"] for f in g.sprakvakt(ny))
    for rad in ("A-NIVÅN ÄR EN INSIKT", "BARA VERKTYG KLASSEN HAR", "SÄG VILKEN VEKTOR SOM MENAS"):
        assert rad in g.INSTRUCTION
