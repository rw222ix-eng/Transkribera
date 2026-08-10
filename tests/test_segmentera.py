"""Ordtider till undertextrader: transcriber.segmentera_ord.

Molnet ger tid per ord; det som avgör om undertexter, källmarkörer och
20-sekunderslyssningen hamnar rätt är att segmenten byggs på meningsgräns,
kapas till undertextstorlek, och att tiderna aldrig går bakåt. Egenskapen
ärvs från den rivna alignmentens testsvit — kravet överlevde metoden.
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app import transcriber

MS = 0.0011          # toleransfönster: en millisekund plus avrundningen


def _ord(text, start, slut):
    return {"text": text, "start": start, "end": slut}


def test_punkt_bryter_segmentet():
    seg = transcriber.segmentera_ord([
        _ord("Hej", 0.0, 0.4), _ord("där.", 0.5, 1.0),
        _ord("Nästa", 2.0, 2.5), _ord("mening.", 2.6, 3.0)])
    assert [s["text"] for s in seg] == ["Hej där.", "Nästa mening."]
    assert seg[0]["start"] == 0.0 and seg[0]["end"] == 1.0
    assert seg[1]["start"] == 2.0 and seg[1]["end"] == 3.0


def test_orden_bar_sina_egna_tider():
    # Det är ordens tider 20-sekunderslyssningen hoppar till.
    seg = transcriber.segmentera_ord([_ord("a", 1.0, 1.5), _ord("b.", 1.6, 2.0)])
    assert seg[0]["words"] == [{"text": "a", "start": 1.0, "end": 1.5},
                               {"text": "b.", "start": 1.6, "end": 2.0}]


def test_for_lang_rad_bryts_pa_ordgrans():
    # Ingen punkt på en halv minut — utan tak blev det ETT segment.
    ord_ = [_ord(f"ord{i:02d}", i * 1.0, i * 1.0 + 0.8) for i in range(40)]
    seg = transcriber.segmentera_ord(ord_)
    assert len(seg) > 1
    for s in seg:
        assert len(s["text"]) <= transcriber.MAX_CAPTION_CHARS + 10
    # Inget ord tappas och ordningen står sig.
    ihop = [o["text"] for s in seg for o in s["words"]]
    assert ihop == [o["text"] for o in ord_]


def test_for_langt_tidsspann_bryts():
    ord_ = [_ord("a", 0.0, 1.0), _ord("b", 40.0, 41.0), _ord("c.", 42.0, 43.0)]
    seg = transcriber.segmentera_ord(ord_)
    assert len(seg) == 2                     # 40 s utan paus spränger MAX_CAPTION_SEC
    assert seg[0]["text"] == "a"


def test_tom_lista_ger_tomt_resultat():
    assert transcriber.segmentera_ord([]) == []


# ── Egenskapen som räknas: tiderna går aldrig bakåt ─────────────────────

ordlangder = st.lists(
    st.tuples(st.floats(min_value=0.05, max_value=3.0,
                        allow_nan=False, allow_infinity=False),
              st.floats(min_value=0.0, max_value=2.0,
                        allow_nan=False, allow_infinity=False),
              st.booleans()),
    min_size=1, max_size=200)


@given(ordlangder)
@settings(max_examples=100, deadline=None)
def test_segmenten_ar_monotona_och_tappar_inga_ord(delar):
    """Varje segment börjar efter det föregående och slutar efter sin egen
    början — annars hoppar undertexten bakåt mitt i lektionen. Och varje ord
    molnet gav ska ut igen, i samma ordning."""
    ord_, t = [], 0.0
    for i, (langd, gap, punkt) in enumerate(delar):
        t += gap
        ord_.append(_ord(f"w{i}" + ("." if punkt else ""), round(t, 3),
                         round(t + langd, 3)))
        t += langd
    seg = transcriber.segmentera_ord(ord_)
    assert [o["text"] for s in seg for o in s["words"]] == [o["text"] for o in ord_]
    for s in seg:
        assert s["end"] >= s["start"]
        for o in s["words"]:
            assert s["start"] - MS <= o["start"] <= o["end"] <= s["end"] + MS
    for forra, nasta in zip(seg, seg[1:]):
        assert nasta["start"] >= forra["start"] - MS
