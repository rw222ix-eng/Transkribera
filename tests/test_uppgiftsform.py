"""NP:s uppgiftsform (lärarens dom 2026-10-03): måtten ur NP-profilen,
skelettet som bygger formen och efterkontrollen som pekar ut prov utanför
den. Se niva_rubrik.NP_UPPGIFTSFORM och exam_spec._np_uppgiftsform."""
from __future__ import annotations

import collections
import json
from pathlib import Path

import pytest

from app import exam_spec, niva_rubrik

FIL = Path(__file__).resolve().parents[1] / "app" / "data" / "np_uppgiftsprofil.json"
KURS_1C = "Matematik, nivå 1c"


# ── Måtten ────────────────────────────────────────────────────────────────

def _rakna_ur_profilen(kurs: str, termin: str, profil: dict) -> dict:
    """Samma räkning som står i kommentaren ovanför NP_UPPGIFTSFORM."""
    k = profil["kurser"][kurs]
    raknare = {(p["termin"], d["namn"]): d["hjalpmedel_raknare"]
               for p in k["prov"] for d in p["delprov"]}
    upp: dict[int, list[dict]] = collections.OrderedDict()
    for r in k["uppgifter"]:
        if r["termin"] == termin:
            upp.setdefault(r["nr"], []).append(r)
    ups = list(upp.values())
    summa = [sum(sum(e["poang"]) for e in v) for v in ups]
    utan = [raknare.get((termin, v[0]["delprov"])) is False for v in ups]
    ett = [i for i, p in enumerate(summa) if p == 1]
    return {
        "uppgifter": len(ups), "poang": sum(summa),
        "enheter": sum(len(v) for v in ups), "enpoangare": len(ett),
        "med_deluppgifter": sum(len(v) > 1 for v in ups),
        "max_deluppgifter": max(len(v) for v in ups),
        "fristaende_stora": sum(len(v) == 1 and p >= 3
                                for v, p in zip(ups, summa)),
        "storlekar": tuple(sum(min(p, 4) == s for p in summa)
                           for s in (1, 2, 3, 4)),
        "enpoangare_niva": tuple(sum(ups[i][0]["niva"] == n for i in ett)
                                 for n in niva_rubrik.NIVAER),
        "utan_raknare": sum(utan),
        "enpoangare_utan_raknare": sum(utan[i] for i in ett),
        "kortsvar_utan_raknare": sum(
            u and all(e["kortsvar"] for e in v) for v, u in zip(ups, utan)),
    }


@pytest.mark.skipif(not FIL.exists(), reason="NP-profilen saknas")
def test_tabellen_ar_profilen_omraknad():
    profil = json.loads(FIL.read_text(encoding="utf-8"))
    for namn, matt in niva_rubrik.NP_UPPGIFTSFORM.items():
        kurs = namn.split()[0].removeprefix("NpMa")
        termin = "vt" + namn.split()[-1][2:]
        assert _rakna_ur_profilen(kurs, termin, profil) == matt, namn


def test_tabellen_stammer_mot_nivamatningen():
    """Uppgiftsantal och poäng ska vara NP_MATNING:s, prov för prov."""
    for namn, matt in niva_rubrik.NP_UPPGIFTSFORM.items():
        nm = niva_rubrik.NP_MATNING[namn]
        assert matt["uppgifter"] == nm["uppgifter"], namn
        assert matt["poang"] == sum(nm["poang"]), namn
        assert sum(matt["storlekar"]) == matt["uppgifter"], namn


def test_lararens_siffror_for_1c_vt22():
    """Domens egna tal: 32 uppgifter på 70 p, 13 enpoängare, 8 med
    deluppgifter (högst 3), 2,2 p per uppgift, 1,7 per bedömd enhet."""
    m = niva_rubrik.NP_UPPGIFTSFORM["NpMa1c vt 2022"]
    assert (m["uppgifter"], m["poang"], m["enpoangare"],
            m["med_deluppgifter"], m["max_deluppgifter"]) == (32, 70, 13, 8, 3)
    assert round(m["poang"] / m["uppgifter"], 1) == 2.2
    assert round(m["poang"] / m["enheter"], 1) == 1.7
    # Alla enpoängare i den räknarfria delen.
    assert m["enpoangare_utan_raknare"] == m["enpoangare"]


def test_banden_per_kurs():
    f = niva_rubrik.uppgiftsform(KURS_1C)
    assert f["kurs"] == "1c" and f["prov"] == 2
    assert f["enpoangare"] == (0.296, 0.406)
    assert f["fristaende_stora"] == (0.125, 0.259)
    assert f["max_deluppgifter"] == 3
    # Kurs 1 bär fler enpoängare än kurs 2.
    assert (niva_rubrik.uppgiftsform("1a")["enpoangare"][0]
            > niva_rubrik.uppgiftsform("2a")["enpoangare"][0])
    # Omätt kurs: ingen form, inte en gissning.
    assert niva_rubrik.uppgiftsform("Matematik 3c") is None
    assert niva_rubrik.uppgiftsform("Matematik, nivå 1b") is None


# ── Skelettet ─────────────────────────────────────────────────────────────

def _form(skelett: list[dict]) -> dict:
    return {"antal": len(skelett),
            "poang": sum(sum(s["poang"]) for s in skelett),
            "ett": sum(sum(s["poang"]) == 1 for s in skelett),
            "delar": sum(bool(s.get("delar")) for s in skelett),
            "fri": sum(not s.get("delar") and sum(s["poang"]) >= 3
                       for s in skelett)}


def test_1c_tolv_uppgifter_pa_100_minuter_far_npform():
    """Prov 156:s beställning: 1c, tolv uppgifter, 100 minuter, takt 3. Förut
    12 uppgifter, 33 p, 0 enpoängare, 5 med deluppgifter, 5 fristående 3+.
    Nu fler och kortare uppgifter på SAMMA poäng, och balansen håller."""
    tak = exam_spec.poang_tak_for(100, 3)
    sk = exam_spec.balanced_skeleton(12, "prov", kurs=KURS_1C, poang_tak=tak)
    f = _form(sk)
    assert f["poang"] == tak == 33
    assert 13 <= f["antal"] <= 15, "en eller två byten, högst tre lyft"
    assert f["ett"] >= 4
    assert f["fri"] <= 4 and f["delar"] <= 4
    doc = exam_spec._skeleton_doc(sk)
    assert exam_spec.validate_balance(doc, profil="prov") == []
    assert exam_spec.validate_ordning(doc) == []
    # Enpoängarna är kortsvar i den räknarfria delen, som i NP.
    ett = [s for s in sk if sum(s["poang"]) == 1]
    assert sum(s["del"] == "B" for s in ett) >= 4


def test_formen_i_alla_fyra_kurserna_pa_100_minuter():
    tak = exam_spec.poang_tak_for(100, 3)
    for kurs in ("1a", "1c", "2a", "2c"):
        sk = exam_spec.balanced_skeleton(12, "prov", kurs=f"Matematik, nivå "
                                         f"{kurs}", poang_tak=tak)
        mal = exam_spec.uppgiftsform_mal(niva_rubrik.uppgiftsform(kurs),
                                         len(sk))
        f = _form(sk)
        assert f["poang"] <= tak, kurs
        assert f["ett"] >= mal["enpoangare"], (kurs, f)
        assert f["fri"] <= mal["fristaende_stora"], (kurs, f)
        assert f["delar"] <= mal["med_deluppgifter"] + 1, (kurs, f)


def test_ett_prov_som_redan_har_formen_far_inga_nya_uppgifter():
    """70 minuter i takt 3: tolv uppgifter på 23 p hade redan fyra
    enpoängare och en fristående trepoängare. Inget lyft."""
    sk = exam_spec.balanced_skeleton(12, "prov", kurs=KURS_1C,
                                     poang_tak=exam_spec.poang_tak_for(70, 3))
    assert len(sk) == 12


def test_formen_ror_inte_kassetternas_skelett_eller_ovningspapper():
    """Omätt kurs, prov under tio uppgifter, arbetsblad och gruppuppgift:
    antalet står kvar, och np_form bär ingen uppgiftsform."""
    tak = exam_spec.poang_tak_for(100, 3)
    assert len(exam_spec.balanced_skeleton(12, "prov", kurs="Matematik 3c",
                                           poang_tak=tak)) == 12
    assert len(exam_spec.balanced_skeleton(9, "prov", kurs=KURS_1C,
                                           poang_tak=tak)) == 9
    assert len(exam_spec.balanced_skeleton(6, "prov",
                                           kurs="Matematik, nivå 2c")) == 6
    for profil in ("arbetsblad", "gruppuppgift"):
        assert exam_spec.np_form(profil, KURS_1C, 12) is None
        assert len(exam_spec.balanced_skeleton(12, profil, kurs=KURS_1C)) == 12
    assert exam_spec.np_form("prov", "Matematik 3c", 12)["uppgiftsform"] is None


def test_aldrig_over_panelens_tak():
    """Tjugo är panelens tak och det grammatikbudgeten är mätt på."""
    tak = exam_spec.poang_tak_for(120, 3)
    for antal in (18, 20):
        sk = exam_spec.balanced_skeleton(antal, "prov", kurs=KURS_1C,
                                         poang_tak=tak)
        assert len(sk) <= exam_spec.MAX_FORESLAGET_ANTAL


def test_lyftet_flyttar_ingen_poang_mellan_nivaer_eller_formagor():
    """Lyftet är en omfördelning: nivåsummor och förmågesummor före
    poängsökningen är exakt desamma efter."""
    form = exam_spec.np_form("prov", KURS_1C, 12)
    slots = [
        {"del": None, "formaga": "P", "karaktar": "C", "typ": "redovisning",
         "poang": [0, 3, 0]},
        {"del": None, "formaga": "PL", "karaktar": "C", "typ": "problem",
         "poang": [0, 4, 0]},
        {"del": None, "formaga": "B", "karaktar": "E", "typ": "rutin",
         "poang": [2, 0, 0]},
    ] * 4
    slots = [dict(s, poang=list(s["poang"])) for s in slots]

    def summor(sl):
        niva = [sum(s["poang"][i] for s in sl) for i in range(3)]
        fm = collections.Counter()
        for s in sl:
            fm[s["formaga"]] += sum(s["poang"])
        return niva, fm

    fore = summor(slots)
    tillagda = exam_spec._np_uppgiftsform(slots, form, 12)
    assert tillagda == len(slots) - 12 > 0
    assert summor(slots) == fore
    assert all(s["formaga"] != "K" for s in slots)


# ── Efterkontrollen ───────────────────────────────────────────────────────

def _doc(skelett: list[dict], kurs: str = KURS_1C) -> exam_spec.ExamDoc:
    upp = []
    for s in skelett:
        bas = dict(del_=s["del"], formaga=s["formaga"], typ=s["typ"],
                   text="_", losning="_", bedomning="_")
        if s.get("delar"):
            upp.append(exam_spec.ExamItem(
                poang=(0, 0, 0), **bas,
                deluppgifter=[exam_spec.SubItem(text="_", poang=tuple(d),
                                                losning="_", bedomning="_")
                              for d in s["delar"]]))
        else:
            upp.append(exam_spec.ExamItem(poang=tuple(s["poang"]), **bas))
    return exam_spec.ExamDoc(titel="_", kurs=kurs, hjalpmedel="_",
                             uppgifter=upp)


# Prov 156 version 1 (NA26F, 2026-10-03): 12 uppgifter, 33 p, 0 enpoängare,
# 5 med deluppgifter, 5 fristående 3+. Skelettet så som det byggdes då.
PROV_156 = [
    {"del": "B", "formaga": "B", "typ": "rutin", "poang": [2, 0, 0],
     "delar": [[1, 0, 0], [1, 0, 0]]},
    {"del": "B", "formaga": "P", "typ": "rutin", "poang": [3, 0, 0],
     "delar": [[1, 0, 0], [1, 0, 0], [1, 0, 0]]},
    {"del": "B", "formaga": "PL", "typ": "rutin", "poang": [0, 0, 2],
     "delar": [[0, 0, 1], [0, 0, 1]]},
    {"del": "B", "formaga": "M", "typ": "problem", "poang": [2, 0, 0]},
    {"del": "B", "formaga": "P", "typ": "redovisning", "poang": [0, 3, 0]},
    {"del": "B", "formaga": "R", "typ": "resonemang", "poang": [0, 4, 0]},
    {"del": "B", "formaga": "K", "typ": "redovisning", "poang": [0, 0, 3]},
    {"del": "C", "formaga": "R", "typ": "resonemang", "poang": [2, 0, 0]},
    {"del": "C", "formaga": "PL", "typ": "problem", "poang": [0, 3, 0]},
    {"del": "C", "formaga": "K", "typ": "redovisning", "poang": [0, 3, 0]},
    {"del": "C", "formaga": "M", "typ": "problem", "poang": [0, 1, 2],
     "delar": [[0, 1, 0], [0, 0, 2]]},
    {"del": "C", "formaga": "B", "typ": "redovisning", "poang": [1, 0, 2],
     "delar": [[1, 0, 0], [0, 0, 2]]},
]


def test_efterkontrollen_pekar_ut_prov_156():
    fel = exam_spec.validate_uppgiftsform(_doc(PROV_156))
    assert [f["code"] for f in fel] == ["uppgiftsform"]
    text = fel[0]["message"]
    assert "0 enpoängare" in text and "fristående" in text
    assert "—" not in text


def test_efterkontrollen_tiger_om_ett_nytt_prov():
    tak = exam_spec.poang_tak_for(100, 3)
    sk = exam_spec.balanced_skeleton(12, "prov", kurs=KURS_1C, poang_tak=tak)
    assert exam_spec.validate_uppgiftsform(_doc(sk)) == []
    # …och om omätta kurser.
    assert exam_spec.validate_uppgiftsform(_doc(PROV_156, "Matematik 3c")) == []


def test_fyndet_star_i_efterkontrollen_och_lagas_inte():
    from app.web import routes_exam
    doc = _doc(PROV_156)
    fynd = routes_exam.efterkontroll({"typ": "prov", "exam": {}}, doc, None)
    assert "uppgiftsform" in [f["kod"] for f in fynd]
    assert "uppgiftsform" in routes_exam._OLAGBARA
    # Arbetsbladet har ingen uppgiftsform att följa.
    blad = routes_exam.efterkontroll({"typ": "arbetsblad", "exam": {}}, doc,
                                     None)
    assert "uppgiftsform" not in [f["kod"] for f in blad]
