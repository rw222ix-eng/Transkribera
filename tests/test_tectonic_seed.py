"""Seedningsskriptet för Tectonic-cachen (PR 1)."""
from pathlib import Path

from app import exam_latex
from tools import seed_tectonic_cache


def test_probe_drar_in_alla_paket():
    """Sondens källa måste nämna varje paket cachen ska innehålla."""
    for paket in ("newtxtext", "newtxmath", "xcolor", "tikz",
                  "pgfplots", "graphicx", "amsmath", "amssymb",
                  "fontenc", "geometry", "fancyhdr", "lastpage",
                  "tabularx", "enumitem", "swedish"):
        assert paket in seed_tectonic_cache.PROBE_TEX, f"{paket} saknas i sonden"


def test_probe_laddar_amssymb_fore_newtxmath():
    """Ordningen är inte kosmetisk: amssymb efter newtxmath ger
    'Command \\openbox already defined'."""
    assert (seed_tectonic_cache.PROBE_TEX.index("amssymb")
            < seed_tectonic_cache.PROBE_TEX.index("newtxmath"))


def test_seed_tar_bort_markoren_innan_kompilering(tmp_path, monkeypatch):
    """En halvfärdig cache låser --only-cached för alltid — markören måste
    bort INNAN kompileringen, inte efter."""
    cache = tmp_path / "cache"
    cache.mkdir()
    markor = cache / ".seeded"
    markor.write_text("", encoding="utf-8")
    monkeypatch.setattr(seed_tectonic_cache.exam_pdf, "engine_dir",
                        lambda: tmp_path)

    sedd_vid_kompilering = {}

    def fejk_compile(tex, out_dir, jobname, **kw):
        sedd_vid_kompilering["fanns"] = markor.exists()
        return Path(out_dir) / f"{jobname}.pdf", ""

    ok, _ = seed_tectonic_cache.seed(tmp_path / "ut", compile_fn=fejk_compile)
    assert ok is True
    assert sedd_vid_kompilering["fanns"] is False
    assert markor.exists(), "markören ska skrivas tillbaka vid lyckad seed"


def test_seed_skriver_inte_markor_vid_misslyckande(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / ".seeded").write_text("", encoding="utf-8")
    monkeypatch.setattr(seed_tectonic_cache.exam_pdf, "engine_dir",
                        lambda: tmp_path)

    ok, meddelande = seed_tectonic_cache.seed(
        tmp_path / "ut",
        compile_fn=lambda *a, **kw: (None, "! LaTeX Error: File `newtxtext.sty' not found."))

    assert ok is False
    assert "newtxtext" in meddelande
    assert not (cache / ".seeded").exists(), \
        "markören får ALDRIG finnas kvar efter en misslyckad seed"


def test_seed_skapar_markor_fran_borjan(tmp_path, monkeypatch):
    """Cachen börjar utan markör — seed måste skapa den efter lyckad kompilering."""
    cache = tmp_path / "cache"
    cache.mkdir()
    # Markören existerar INTE från början (detta är det vanliga läget)
    markor = cache / ".seeded"
    assert not markor.exists()
    monkeypatch.setattr(seed_tectonic_cache.exam_pdf, "engine_dir",
                        lambda: tmp_path)

    def fejk_compile(tex, out_dir, jobname, **kw):
        return Path(out_dir) / f"{jobname}.pdf", ""

    ok, _ = seed_tectonic_cache.seed(tmp_path / "ut", compile_fn=fejk_compile)
    assert ok is True
    assert markor.exists(), "markören ska skapas efter lyckad seed"


def test_sonden_satter_glyfer_i_alla_mattestorlekar():
    """ntxsy7/ntxsy5/ntxmi5 hämtas ner först när en glyf FAKTISKT sätts i
    script- respektive scriptscript-storlek. Enbart en \\frac räcker inte:
    bråkstrecket är en linje, inte en glyf, och TeX nöjer sig då med .tfm-
    metriken — xdvipdfmx faller senare på 'Could not locate a virtual/
    physical font'. Därför måste både en symbol (\\cdot, \\sqrt) och en
    bokstav finnas på varje nivå.

    escape_mixed gör om $…$ till \\(…\\), så matte-kroppen matchas utan
    delimitrar."""
    tex = exam_latex.render_bedomning(
        seed_tectonic_cache._representative_doc())
    assert r"x^{a \cdot \sqrt{b}}" in tex, \
        "symbolglyf i script-storlek (ntxsy7) seedas aldrig"
    assert r"y^{\frac{c \cdot d}{e}}" in tex, \
        "glyfer i scriptscript-storlek (ntxmi5/ntxsy5) seedas aldrig"
    # Sonden speglar stegen (belt and braces, som \pic-figuren) så att den
    # står kvar även om det representativa dokumentet skrivs om.
    assert r"x^{a \cdot \sqrt{b}}" in seed_tectonic_cache.PROBE_TEX
    assert r"y^{\frac{c \cdot d}{e}}" in seed_tectonic_cache.PROBE_TEX
