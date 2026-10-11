"""Punktens delbegrepp och grafisk ekvationslösning i GeoGebra (exam_gen
ci_delbegrepp, grafisk_digitalvakt; Rickard 2026-10-11 över prov 156)."""
from app import exam_gen
from app.web import routes_exam

TRI1 = "G25-M1C-TRI-1"
ALG2 = "G25-M1C-ALG-2"
ALG3 = "G25-M1C-ALG-3"
TRI2 = "G25-M1C-TRI-2"


def _u(text, losning, poang, del_="C", kod=TRI1, **extra):
    return {"del": del_, "text": text, "losning": losning, "poang": poang,
            "innehall": [kod], **extra}


def _prov(*uppg, hjalpmedel="Del B utan räknare. Del C med räknare."):
    return {"hjalpmedel": hjalpmedel, "uppgifter": list(uppg)}


def _koder(fel):
    return [f["code"] for f in fel]


def test_cosinus_saknas_som_i_prov_156():
    prov = _prov(
        _u("Rampen lutar 6°.", r"$\sin 6^{\circ} = \frac{0{,}62}{x}$", [1, 0, 0]),
        _u("Bestäm bredden.", r"$\frac{2{,}10}{\tan 40^{\circ}}$", [0, 2, 0]),
        _u("Bestäm vinkeln.", r"$v = \sin^{-1}(0{,}09)$", [1, 0, 0]))
    fel = exam_gen.ci_delbegrepp(prov, [TRI1])
    assert len(fel) == 1 and "cosinus" in fel[0]["message"]


def test_alla_tre_och_arcus_ger_tystnad():
    prov = _prov(
        _u("a", r"$\sin v$", [1, 0, 0]), _u("b", r"$\cos v$", [1, 0, 0]),
        _u("c", r"$\tan^{-1} 2$", [0, 1, 0]))
    assert exam_gen.ci_delbegrepp(prov, [TRI1]) == []


def test_begrepp_bara_pa_a_fälls_men_inte_metod():
    prov = _prov(
        _u("Ange definitionsmängden.", "", [0, 0, 1], kod=ALG2),
        _u("Ange värdemängden.", "", [1, 0, 0], kod=ALG2),
        _u(r"$\vec{u} + \vec{v}$ och $\vec{u} - \vec{v}$, $|\vec{u}|$ och "
           r"$2\vec{u}$", "", [0, 0, 2], kod=TRI2))
    fel = exam_gen.ci_delbegrepp(prov, [ALG2, TRI2])
    assert len(fel) == 1 and "definitionsmängd" in fel[0]["message"]


def test_utan_taggar_tyst():
    prov = {"uppgifter": [{"del": "C", "text": "x", "poang": [1, 0, 0]}]}
    assert exam_gen.ci_delbegrepp(prov, [TRI1]) == []


def test_grafisk_kraver_digital_del():
    prov = _prov(_u("Lös ekvationen med hjälp av grafen.", "", [1, 0, 0],
                    del_="B", kod=ALG3, figur={"typ": "graf"}))
    fel = exam_gen.grafisk_digitalvakt(prov, [ALG3])
    assert _koder(fel) == ["geogebra"] and fel[0]["path"] == "hjalpmedel"


def test_grafisk_i_geogebra_tyst():
    prov = _prov(
        _u("Lös ekvationen $400 \\cdot 0{,}85^{t} = 100$ grafiskt i GeoGebra.",
           "", [1, 0, 0], kod=ALG3),
        hjalpmedel=("Del B utan räknare. Del C med digitala verktyg "
                    "(GeoGebra på datorn) och formelblad."))
    assert exam_gen.digitala_delar(prov) == {"C"}
    assert exam_gen.grafisk_digitalvakt(prov, [ALG3]) == []


def test_grafiskt_utan_graf_i_del_b_fälls():
    prov = _prov(
        _u("Lös ekvationen grafiskt.", "", [1, 0, 0], del_="B", kod=ALG3),
        _u("Lös ekvationen i GeoGebra.", "", [1, 0, 0], kod=ALG3),
        hjalpmedel="Del B utan räknare. Del C med digitala verktyg och formelblad.")
    fel = exam_gen.grafisk_digitalvakt(prov, [ALG3])
    assert [f["path"] for f in fel] == ["uppgift 1"]


def test_tyst_utan_punkten():
    prov = _prov(_u("Lös grafiskt.", "", [1, 0, 0], del_="B"))
    assert exam_gen.grafisk_digitalvakt(prov, [TRI1]) == []


def test_promptblocket_bara_med_utlosande_punkt():
    assert exam_gen.build_delbegrepp(["G25-M1C-ALG-1"], "prov") == ""
    block = exam_gen.build_delbegrepp([TRI1, ALG3], "prov")
    assert "cosinus" in block and "GeoGebra" in block
    assert exam_gen.build_delbegrepp([TRI1, ALG3], "arbetsblad") == ""


def test_efterkontrollen_visar_fyndet():
    prov = _prov(_u("Rampen.", r"$\sin 6^{\circ}$", [1, 0, 0]))
    fynd = routes_exam._delbegreppsfynd(prov, "prov")
    assert any(f["kod"] == "delbegrepp" for f in fynd)
    assert routes_exam._delbegreppsfynd(prov, "arbetsblad") == []
