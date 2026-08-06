"""Tidsättningen som helhet (Etapp 2): bitarnas tider blir lektionens.

gpt-transcribe svarar utan en enda tidsstämpel. Tiderna sätts lokalt med
forced alignment per BIT, och bitens tider ligger i sin egen lilla tidslinje
(0 → bitens längd). Det som avgör om undertexter, källmarkörer och
20-sekunderslyssningen hamnar rätt är därför inte Viterbi-sökningen — den är
torchaudios — utan att förskjutningen läggs på, att tiderna aldrig går bakåt,
och att en bit som inte går att aligna ändå levererar sin text.

Ingen modell laddas: `_modell`, `_ljud` och `_ordtider` är sömmarna.
Jämförelserna är toleranta (±1 ms) — tiderna avrundas till millisekunder, och
exakt likhet på flyttal är ett test som faller på en annan maskin.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app import alignment
from app.openai_asr import Bit

MS = 0.0011          # toleransfönster: en millisekund plus avrundningen


@pytest.fixture
def rigg(monkeypatch):
    """Alignmenten utan modell: orden kommer ur en tabell i stället för ljudet."""
    monkeypatch.setattr(alignment, "_modell", lambda *a, **k: (None, None, "cpu"))
    monkeypatch.setattr(alignment, "_ljud", lambda *a, **k: None)

    def satt(ordtider):
        monkeypatch.setattr(alignment, "_ordtider", ordtider)
    return satt


def _ord(text, start, slut):
    return {"text": text, "start": start, "end": slut}


def test_forskjutningen_laggs_pa_bitens_tider(rigg, tmp_path):
    """Bitens ord ligger i bitens egen tidslinje. Utan förskjutningen hamnar
    varje undertext efter den första på fel ställe i lektionen."""
    rigg(lambda text, *a, **k: [_ord("hej", 0.0, 0.5), _ord("där.", 0.6, 1.0)])
    segment = alignment.tidsatt(tmp_path / "a.wav",
                                [Bit(0.0, 10.0, "hej där.", 10.0),
                                 Bit(10.0, 20.0, "hej där.", 10.0)],
                                tmp_path)
    assert segment[0]["start"] == pytest.approx(0.0, abs=MS)
    assert segment[1]["start"] == pytest.approx(10.0, abs=MS)
    assert segment[1]["end"] == pytest.approx(11.0, abs=MS)
    # Orden bär sina egna tider — det är dem 20-sekunderslyssningen hoppar till.
    assert segment[1]["words"][0]["start"] == pytest.approx(10.0, abs=MS)


def test_en_bit_som_inte_gar_att_aligna_behaller_sin_text(rigg, tmp_path):
    """Ett transkript utan finkorniga tider är fortfarande ett transkript.
    Ett tomt resultat vore ett tapp — lektionen går inte att spela in igen."""
    def kastar(*a, **k):
        raise RuntimeError("CTC-sökningen gav upp")
    rigg(kastar)
    segment = alignment.tidsatt(tmp_path / "a.wav",
                                [Bit(30.0, 45.0, "det som sades", 15.0)],
                                tmp_path)
    assert len(segment) == 1
    assert segment[0]["text"] == "det som sades"
    assert segment[0]["start"] == pytest.approx(30.0, abs=MS)
    assert segment[0]["end"] == pytest.approx(45.0, abs=MS)
    assert segment[0]["words"] == []          # inga ordtider utlovas


def test_tom_bit_hoppas_over_utan_att_falla(rigg, tmp_path):
    rigg(lambda text, *a, **k: [_ord("x", 0.0, 1.0)])
    segment = alignment.tidsatt(tmp_path / "a.wav",
                                [Bit(0.0, 5.0, "   ", 5.0),
                                 Bit(5.0, 10.0, "x", 5.0)],
                                tmp_path)
    assert len(segment) == 1 and segment[0]["start"] == pytest.approx(5.0, abs=MS)


def test_avbrott_mellan_bitarna_biter(rigg, tmp_path):
    rigg(lambda text, *a, **k: [_ord("x", 0.0, 1.0)])
    with pytest.raises(RuntimeError, match="avbröts"):
        alignment.tidsatt(tmp_path / "a.wav",
                          [Bit(0.0, 5.0, "x", 5.0)], tmp_path,
                          avbruten=lambda: True)


def test_framsteget_gar_till_hundra(rigg, tmp_path):
    rigg(lambda text, *a, **k: [_ord("x", 0.0, 1.0)])
    pct = []
    alignment.tidsatt(tmp_path / "a.wav",
                      [Bit(0.0, 5.0, "x", 5.0), Bit(5.0, 10.0, "x", 5.0)],
                      tmp_path, progress_cb=pct.append)
    assert pct == sorted(pct) and pct[-1] == 100


# ── Egenskapen som räknas: tiderna går aldrig bakåt ─────────────────────

bitar = st.lists(
    st.floats(min_value=0.5, max_value=300, allow_nan=False, allow_infinity=False),
    min_size=1, max_size=12)


@given(langder=bitar)
@settings(max_examples=100, deadline=None)
def test_segmenten_ar_monotona_over_hela_lektionen(langder, tmp_path_factory):
    """Varje segment börjar efter det föregående och slutar efter sin egen
    början — annars hoppar undertexten bakåt mitt i lektionen."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    try:
        mp.setattr(alignment, "_modell", lambda *a, **k: (None, None, "cpu"))
        mp.setattr(alignment, "_ljud", lambda *a, **k: None)
        # Orden ligger jämnt inom bitens egen längd (det alignmenten ger).
        mp.setattr(alignment, "_ordtider",
                   lambda text, vag, *a, **k: [_ord("a", 0.0, 0.4),
                                               _ord("b.", 0.4, 0.8)])
        b, t = [], 0.0
        for langd in langder:
            b.append(Bit(t, t + langd, "a b.", langd))
            t += langd
        segment = alignment.tidsatt(Path("x.wav"), b,
                                    tmp_path_factory.mktemp("m"))
    finally:
        mp.undo()
    assert len(segment) == len(langder)
    for s in segment:
        assert s["end"] >= s["start"]
        for o in s["words"]:
            assert s["start"] - MS <= o["start"] <= o["end"] <= s["end"] + MS
    for forra, nasta in zip(segment, segment[1:]):
        assert nasta["start"] >= forra["start"] - MS
