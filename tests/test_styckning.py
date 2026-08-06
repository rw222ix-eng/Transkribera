"""Styckningen och kontextbryggan som EGENSKAPER (Etapp 2).

`dela_upp` är den enda rena funktionen i hela molnvägen: in kommer en längd och
ffmpegs tystnadsintervall, ut kommer bitgränserna. Allt annat hänger på den —
kostnaden räknas per bit, alignmenten får sin tidsram per bit, och en skarv på
fel ställe hörs mitt i en mening.

Exempeltester räcker inte för den sortens funktion: felen ligger i kanterna
(en tystnad exakt vid fönstrets slut, ett ljud på exakt 300 s, en paus var
tionde sekund) och de kanterna hittar Hypothesis snabbare än vi kommer på dem.

Egenskaperna nedan är kontraktet:
  1. Bitarna täcker HELA ljudet, i ordning, utan glapp och utan överlapp.
  2. Ingen bit är längre än max — annars växer begäran och alignmentens
     trellis utan tak.
  3. Ingen bit utom den sista är kortare än min — annars styckas en lektion
     med talpauser till konfetti.
  4. Samma indata ger samma gränser (kostnaden får inte variera mellan två
     körningar av samma fil).
"""
from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app import openai_asr

MAX = openai_asr.MAX_BIT_SEK
MIN = openai_asr.MIN_BIT_SEK

# Tystnader som ffmpeg kan rapportera dem: par (start, slut) med slut > start.
tystnad = st.builds(
    lambda a, d: (a, a + d),
    st.floats(min_value=0, max_value=4000, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.05, max_value=5, allow_nan=False, allow_infinity=False),
)
langder = st.floats(min_value=0.1, max_value=5000, allow_nan=False,
                    allow_infinity=False)


@given(langd=langder, tyst=st.lists(tystnad, max_size=40))
@settings(max_examples=300, deadline=None)
def test_bitarna_tacker_hela_ljudet(langd, tyst):
    granser = openai_asr.dela_upp(langd, tyst)
    assert granser, "ett ljud med längd måste ge minst en bit"
    assert granser[0][0] == 0.0
    assert granser[-1][1] == pytest.approx(langd)
    for (a1, b1), (a2, b2) in zip(granser, granser[1:]):
        assert b1 == a2, "glapp eller överlapp mellan bitarna"
    for a, b in granser:
        assert b > a, "en bit får aldrig vara tom eller bakvänd"


@given(langd=langder, tyst=st.lists(tystnad, max_size=40))
@settings(max_examples=300, deadline=None)
def test_ingen_bit_ar_langre_an_taket(langd, tyst):
    for a, b in openai_asr.dela_upp(langd, tyst):
        assert b - a <= MAX + 1e-6


@given(langd=langder, tyst=st.lists(tystnad, max_size=40))
@settings(max_examples=300, deadline=None)
def test_bara_sista_biten_far_vara_kort(langd, tyst):
    granser = openai_asr.dela_upp(langd, tyst)
    for a, b in granser[:-1]:
        assert b - a >= MIN - 1e-6, "en talpaus får inte stycka ljudet i konfetti"


@given(langd=langder, tyst=st.lists(tystnad, max_size=20))
@settings(max_examples=100, deadline=None)
def test_samma_indata_ger_samma_granser(langd, tyst):
    assert openai_asr.dela_upp(langd, tyst) == openai_asr.dela_upp(langd, tyst)


@given(langd=langder, tyst=st.lists(tystnad, max_size=20))
@settings(max_examples=100, deadline=None)
def test_ordningen_pa_tystnaderna_spelar_ingen_roll(langd, tyst):
    """ffmpeg rapporterar i tidsordning, men koden sorterar själv — och ska
    göra det, för en omsorterad lista är samma ljud."""
    assert openai_asr.dela_upp(langd, tyst) == openai_asr.dela_upp(langd, list(reversed(tyst)))


# ── Kanterna, uttryckta som exempel ──────────────────────────────────────

def test_ljud_utan_langd_ger_inga_bitar():
    assert openai_asr.dela_upp(0.0, []) == []
    assert openai_asr.dela_upp(-5.0, [(1, 2)]) == []


def test_exakt_pa_taket_ar_en_enda_bit():
    """300,0 s är EN begäran; 300,1 s är två. Gränsen ligger där den står."""
    assert openai_asr.dela_upp(MAX, []) == [(0.0, MAX)]
    assert len(openai_asr.dela_upp(MAX + 0.1, [])) == 2


def test_tystnad_exakt_vid_fonstrets_kant_anvands():
    """En tystnad vars mitt ligger PRECIS på max_sek ska användas — den är
    fortfarande inom fönstret, och att missa den ger en skarv mitt i tal."""
    granser = openai_asr.dela_upp(600.0, [(MAX - 0.5, MAX + 0.5)])
    assert granser[0] == (0.0, MAX)


def test_tystnad_precis_innanfor_golvet_anvands():
    granser = openai_asr.dela_upp(600.0, [(MIN - 0.5, MIN + 0.5)], max_sek=MAX,
                                 min_sek=MIN)
    assert granser[0] == (0.0, MIN)


def test_sista_tystnaden_i_fonstret_vinner():
    """Klipp så sent som möjligt: varje bit ska bära så mycket sammanhang den
    får plats med."""
    granser = openai_asr.dela_upp(600.0, [(99, 101), (199, 201), (279, 281)])
    assert granser[0] == (0.0, 280.0)


# ── Kontextbryggan ──────────────────────────────────────────────────────
# Varje bit får föregående bits svans som ledtext, så modellen fortsätter i
# samma stavning över skarven. Svansen är de sista 120 orden, och prompten
# kapas till 2000 tecken innan den skickas.

@given(ord_=st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyzåäö ",
                             min_size=1, max_size=30),
                     min_size=1, max_size=400))
@settings(max_examples=200, deadline=None)
def test_ledtexten_ar_alltid_hogst_tvatusen_tecken(ord_, tmp_path_factory):
    # Fixturen byggs inuti testet: en function-scoped monkeypatch återställs
    # inte mellan Hypothesis omgångar (och Hypothesis säger ifrån om man ändå
    # ber om den).
    from _pytest.monkeypatch import MonkeyPatch

    from tests.fejk import Moln
    mp = MonkeyPatch()
    try:
        moln = Moln("ok").installera(mp)
        fil = tmp_path_factory.mktemp("bit") / "bit.ogg"
        fil.write_bytes(b"ogg")
        ledtext = " ".join(ord_)
        openai_asr.transkribera_bit(fil, "sk-x", ledtext=ledtext)
    finally:
        mp.undo()
    skickad = moln.anrop[-1]["data"].get("prompt", "")
    assert len(skickad) <= 2000
    if ledtext.strip():
        # Det är SVANSEN som ska följa med över skarven, inte början.
        assert ledtext.endswith(skickad)


def test_tom_ledtext_skickas_inte_alls(tmp_path, monkeypatch):
    from tests.fejk import Moln
    moln = Moln("ok").installera(monkeypatch)
    fil = tmp_path / "bit.ogg"
    fil.write_bytes(b"ogg")
    openai_asr.transkribera_bit(fil, "sk-x", ledtext="")
    assert "prompt" not in moln.anrop[-1]["data"]


def test_svansen_ar_de_sista_hundratjugo_orden(tmp_path, monkeypatch):
    """Bryggan ska bära slutet av förra biten — det är där nästa fortsätter."""
    from tests.fejk import Moln
    moln = Moln(["ok", "ok"]).installera(monkeypatch)
    monkeypatch.setattr(openai_asr, "tystnader", lambda *a, **k: [])
    monkeypatch.setattr(openai_asr, "_klipp_ut",
                        lambda audio, start, end, dest: (dest.write_bytes(b"ogg"), dest)[1])
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    # Två bitar: den andra ska bära den första bitens text som ledtext.
    openai_asr.transkribera(tmp_path / "a.wav", tmp_path, langd=MAX + 10)
    andra = moln.anrop[1]["data"].get("prompt", "")
    assert "Hej världen." in andra
