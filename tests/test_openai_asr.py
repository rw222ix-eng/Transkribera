"""Molntranskriberingen: styckning, nyckel, felmeddelanden och strömtolkning.

Inget nät: httpx-anropet fejkas. Det som testas är kontraktet mot API:et — att
modellen är förbestämd, att strömmens deltan blir text, att usage.seconds blir
kostnad, och att ett fel blir en mening en lärare kan läsa.
"""
import json

import pytest

from app import openai_asr


# ---- Styckning vid tystnad ------------------------------------------------

def test_kort_ljud_blir_en_enda_bit():
    assert openai_asr.dela_upp(120.0, []) == [(0.0, 120.0)]


def test_klipper_i_sista_tystnaden_inom_fonstret():
    # Tystnader vid 100 och 280 s; maxbiten är 300 → klippet ska hamna i den
    # SENASTE möjliga tystnaden (280), inte i den första.
    granser = openai_asr.dela_upp(600.0, [(99.0, 101.0), (279.0, 281.0)])
    assert granser[0] == (0.0, 280.0)
    assert granser[-1][1] == 600.0


def test_hard_klippning_nar_ingen_tystnad_finns():
    granser = openai_asr.dela_upp(700.0, [], max_sek=300.0)
    assert granser == [(0.0, 300.0), (300.0, 600.0), (600.0, 700.0)]


def test_tystnad_for_tidigt_i_fonstret_ignoreras():
    # En paus efter 10 s får inte stycka sönder ljudet i konfetti.
    granser = openai_asr.dela_upp(400.0, [(9.0, 11.0)], max_sek=300.0, min_sek=45.0)
    assert granser[0] == (0.0, 300.0)


def test_bitarna_tacker_hela_ljudet_utan_glapp():
    granser = openai_asr.dela_upp(1000.0, [(x, x + 1) for x in range(60, 1000, 70)])
    assert granser[0][0] == 0.0 and granser[-1][1] == 1000.0
    for forra, nasta in zip(granser, granser[1:]):
        assert forra[1] == nasta[0]


# ---- Nyckeln --------------------------------------------------------------

def test_miljon_vinner_over_filen(tmp_path, monkeypatch):
    (tmp_path / openai_asr.NYCKELFIL).write_text("fran-fil", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "fran-miljon")
    assert openai_asr.api_key(tmp_path) == "fran-miljon"


def test_nyckelfilen_lases_nar_miljon_ar_tom(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    openai_asr.spara_nyckel(tmp_path, "  sk-test  ")
    assert openai_asr.api_key(tmp_path) == "sk-test"
    assert openai_asr.har_nyckel(tmp_path) is True


def test_tom_nyckel_raderar_filen(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    openai_asr.spara_nyckel(tmp_path, "sk-test")
    openai_asr.spara_nyckel(tmp_path, "")
    assert openai_asr.har_nyckel(tmp_path) is False


def test_transkribera_utan_nyckel_reser_saknar_nyckel(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(openai_asr.SaknarNyckel):
        openai_asr.transkribera(tmp_path / "x.wav", tmp_path, langd=10.0)


# ---- Kostnad --------------------------------------------------------------

def test_kostnad_raknas_pa_debiterade_sekunder():
    # 15 minuter à $0,0045 = $0,0675 — priset följer usage, inte filens längd.
    assert openai_asr.kostnad_usd(900) == 0.0675


def test_resultatets_text_och_kostnad_summerar_bitarna():
    res = openai_asr.Resultat(bitar=[openai_asr.Bit(0, 60, "Först.", 60.0),
                                     openai_asr.Bit(60, 120, "Sedan.", 60.0)])
    assert res.text == "Först. Sedan."
    assert res.debiterade_sekunder == 120.0
    assert res.kostnad == openai_asr.kostnad_usd(120.0)


# ---- Anropet och strömmen -------------------------------------------------

class _FejkSvar:
    def __init__(self, rader, status=200):
        self._rader = rader
        self.status_code = status
        self.text = "" if status == 200 else json.dumps(
            {"error": {"message": "nyckeln duger inte"}})

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_lines(self):
        return iter(self._rader)

    def read(self):
        return b""


class _FejkKlient:
    senaste: dict = {}

    def __init__(self, rader, status=200):
        self._rader, self._status = rader, status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def stream(self, metod, url, headers=None, data=None, files=None):
        _FejkKlient.senaste = {"metod": metod, "url": url, "headers": headers,
                               "data": data, "files": files}
        return _FejkSvar(self._rader, self._status)


STROM = [
    'data: {"type":"transcript.text.delta","delta":"Hej "}',
    "",
    'data: {"type":"transcript.text.delta","delta":"världen"}',
    'data: trasig json',
    'data: {"type":"transcript.text.done","text":"Hej världen.",'
    '"usage":{"type":"duration","seconds":6},"languages":[{"code":"sv"}]}',
    "data: [DONE]",
]


def test_strommen_blir_text_sekunder_och_sprak(tmp_path, monkeypatch):
    fil = tmp_path / "bit.ogg"
    fil.write_bytes(b"ogg")
    monkeypatch.setattr(openai_asr.httpx, "Client", lambda **k: _FejkKlient(STROM))
    delar = []
    text, sek, sprak = openai_asr.transkribera_bit(
        fil, "sk-x", sprak="sv", ledtext="Matematik.", delta_cb=delar.append)
    assert text == "Hej världen."          # done-texten vinner över hopsamlade deltan
    assert (sek, sprak) == (6.0, "sv")
    assert delar == ["Hej ", "världen"]    # men deltan strömmas medan de kommer


def test_modellen_ar_forbestamd_och_strommen_pasatt(tmp_path, monkeypatch):
    fil = tmp_path / "bit.ogg"
    fil.write_bytes(b"ogg")
    monkeypatch.setattr(openai_asr.httpx, "Client", lambda **k: _FejkKlient(STROM))
    openai_asr.transkribera_bit(fil, "sk-x", sprak="sv", ledtext="Ledtext.")
    skickat = _FejkKlient.senaste["data"]
    assert skickat["model"] == "gpt-transcribe"
    assert skickat["response_format"] == "json"   # verbose_json stöds inte
    assert skickat["stream"] == "true"
    assert skickat["languages[]"] == "sv"
    assert skickat["prompt"] == "Ledtext."
    assert _FejkKlient.senaste["headers"]["Authorization"] == "Bearer sk-x"


def test_avvisad_nyckel_blir_en_lasbar_mening(tmp_path, monkeypatch):
    fil = tmp_path / "bit.ogg"
    fil.write_bytes(b"ogg")
    monkeypatch.setattr(openai_asr.httpx, "Client",
                        lambda **k: _FejkKlient([], status=401))
    with pytest.raises(RuntimeError) as fel:
        openai_asr.transkribera_bit(fil, "sk-fel")
    assert "nyckeln" in str(fel.value).lower()
    assert "401" in str(fel.value)


def test_femhundrafel_ber_om_nytt_forsok():
    assert "Försök igen" in openai_asr._felmeddelande(503, "{}")
