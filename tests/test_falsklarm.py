"""Vakternas falsklarm ur granskningen av de kommande proven 2026-10-11."""
from app import ci_utanfor, exam_gen, np_vakter


def test_vektornamn_och_storheter_ar_inga_konstanter():
    k = np_vakter.konstanter
    assert k(r"Beräkna $\vec{u} + \vec{v}$.") == set()
    assert k(r"Ställ upp en formel för kostnaden $K$ kr när släpvagnen "
             r"hyrs i $t$ timmar.") == set()
    assert k(r"Linjen $L$ har ekvationen $y = 2x + 3$ och linjen $M$ har "
             r"ekvationen $2x - y - 1 = 0$.") == set()
    assert k(r"Vektorn $\vec{a} = (k,\ 2)$ är parallell med $\vec{u}$. "
             r"Bestäm talet $k$.") == set()


def test_riktiga_konstanter_raknas_fortfarande():
    assert np_vakter.konstanter(r"Lös $ax + b = 7$ för $x$.") == {"a", "b"}


def test_kvadrat_av_tal_i_ekvation_ar_ingen_kvadreringsregel():
    s = ci_utanfor._Kvadreringsregler().search
    assert s(r"$(4 + t)^2 + 6^2 = 100$") is None
    assert s(r"$(x + 3)^2 = x^2 + 6x + 9$") is not None
    assert s(r"Förenkla $(a + b)^2 - (a - b)^2$") is not None


def test_rubrikens_extra_meningar_ar_inga_delmoment():
    rader = [
        {"datum": "2026-09-01", "fran": 85, "till": 88,
         "rubrik": "Mönster och generella samband. Räkna ifatt"},
        {"datum": "2026-09-02", "fran": 151, "till": 151,
         "rubrik": "Testa dig själv 2"},
        {"datum": "2026-09-03", "fran": 152, "till": 155,
         "rubrik": "blandade övningar"},
    ]
    dm = exam_gen.delmoment_ur_lektioner(rader, fran=1, till=200,
                                         provdatum="2026-10-01")
    assert [d["delmoment"] for d in dm] == ["Mönster och generella samband"]
