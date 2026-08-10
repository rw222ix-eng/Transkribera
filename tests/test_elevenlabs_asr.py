"""Molntranskriberingen hos ElevenLabs: nyckel, kontrakt, ordtider, omtag.

Inget nät: httpx-anropet fejkas. Det som testas är kontraktet mot API:et — att
modellen är förbestämd, att ordtiderna filtreras och fylls, att
audio_duration_secs blir kostnad, och att ett fel blir en mening en lärare
kan läsa.
"""
import json
from pathlib import Path

import pytest

from app import elevenlabs_asr


# ---- Nyckeln --------------------------------------------------------------

def test_miljon_vinner_over_filen(tmp_path, monkeypatch):
    (tmp_path / elevenlabs_asr.NYCKELFIL).write_text("fran-fil", encoding="utf-8")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fran-miljon")
    assert elevenlabs_asr.api_key(tmp_path) == "fran-miljon"


def test_nyckelfilen_lases_nar_miljon_ar_tom(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    elevenlabs_asr.spara_nyckel(tmp_path, "  el-test  ")
    assert elevenlabs_asr.api_key(tmp_path) == "el-test"
    assert elevenlabs_asr.har_nyckel(tmp_path) is True


def test_tom_nyckel_raderar_filen(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    elevenlabs_asr.spara_nyckel(tmp_path, "el-test")
    elevenlabs_asr.spara_nyckel(tmp_path, "")
    assert elevenlabs_asr.har_nyckel(tmp_path) is False


def test_transkribera_utan_nyckel_reser_saknar_nyckel(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(elevenlabs_asr.SaknarNyckel):
        elevenlabs_asr.transkribera(tmp_path / "x.wav", tmp_path, langd=10.0)


# ---- Kostnad --------------------------------------------------------------

def test_kostnad_raknas_pa_debiterade_sekunder():
    # En timme à $0,22 — priset följer audio_duration_secs, inte filens längd.
    assert elevenlabs_asr.kostnad_usd(3600) == 0.22


def test_resultatet_bar_kostnad_och_alias():
    res = elevenlabs_asr.Resultat(text="Hej.", sekunder=1800.0)
    assert res.debiterade_sekunder == 1800.0
    assert res.kostnad == elevenlabs_asr.kostnad_usd(1800.0)


# ---- Anropet --------------------------------------------------------------

SVAR_OK = {
    "language_code": "sv",
    "language_probability": 0.99,
    "text": "Hej världen.",
    "words": [
        {"text": "Hej", "type": "word", "start": 0.1, "end": 0.4},
        {"text": " ", "type": "spacing", "start": 0.4, "end": 0.5},
        {"text": "(skratt)", "type": "audio_event", "start": 0.5, "end": 1.0},
        {"text": "världen.", "type": "word", "start": 1.0, "end": 1.6},
    ],
    "audio_duration_secs": 6,
    "transcription_id": "abc123",
}


class _FejkSvar:
    def __init__(self, kropp, status=200):
        self._kropp = kropp
        self.status_code = status
        self.text = kropp if isinstance(kropp, str) else json.dumps(kropp)

    def json(self):
        if isinstance(self._kropp, str):
            return json.loads(self._kropp)
        return self._kropp


class _FejkKlient:
    senaste: dict = {}

    def __init__(self, kropp, status=200):
        self._kropp, self._status = kropp, status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, data=None, files=None):
        _FejkKlient.senaste = {"url": url, "headers": headers,
                               "data": data, "files": files}
        return _FejkSvar(self._kropp, self._status)


def _fejka(monkeypatch, kropp, status=200):
    monkeypatch.setattr(elevenlabs_asr.httpx, "Client",
                        lambda **k: _FejkKlient(kropp, status))


def test_svaret_blir_text_ord_sekunder_och_sprak(tmp_path, monkeypatch):
    fil = tmp_path / "ljud.ogg"
    fil.write_bytes(b"ogg")
    _fejka(monkeypatch, SVAR_OK)
    text, ord_, sek, sprak = elevenlabs_asr.transkribera_fil(fil, "el-x", sprak="sv")
    assert text == "Hej världen."
    assert (sek, sprak) == (6.0, "sv")
    # spacing och audio_event är inte ord — bara de riktiga orden blir tider.
    assert [o["text"] for o in ord_] == ["Hej", "världen."]
    assert ord_[0]["start"] == 0.1 and ord_[-1]["end"] == 1.6


def test_ord_utan_tid_interpoleras(tmp_path, monkeypatch):
    fil = tmp_path / "ljud.ogg"
    fil.write_bytes(b"ogg")
    kropp = dict(SVAR_OK)
    kropp["words"] = [
        {"text": "Ett", "type": "word", "start": 0.0, "end": 1.0},
        {"text": "2026", "type": "word", "start": None, "end": None},
        {"text": "tre.", "type": "word", "start": 2.0, "end": 3.0},
    ]
    _fejka(monkeypatch, kropp)
    _, ord_, _, _ = elevenlabs_asr.transkribera_fil(fil, "el-x")
    assert ord_[1]["start"] == 1.0 and ord_[1]["end"] == 2.0


def test_modellen_ar_forbestamd_och_ordtider_begarda(tmp_path, monkeypatch):
    fil = tmp_path / "ljud.ogg"
    fil.write_bytes(b"ogg")
    _fejka(monkeypatch, SVAR_OK)
    elevenlabs_asr.transkribera_fil(fil, "el-x", sprak="sv")
    skickat = _FejkKlient.senaste["data"]
    assert skickat["model_id"] == "scribe_v2"
    assert skickat["timestamps_granularity"] == "word"
    assert skickat["diarize"] == "false"
    assert skickat["tag_audio_events"] == "false"
    assert skickat["language_code"] == "sv"
    assert _FejkKlient.senaste["headers"]["xi-api-key"] == "el-x"


def test_sprak_utelamnas_nar_det_ar_tomt(tmp_path, monkeypatch):
    fil = tmp_path / "ljud.ogg"
    fil.write_bytes(b"ogg")
    _fejka(monkeypatch, SVAR_OK)
    elevenlabs_asr.transkribera_fil(fil, "el-x")
    assert "language_code" not in _FejkKlient.senaste["data"]


def test_avvisad_nyckel_blir_en_lasbar_mening(tmp_path, monkeypatch):
    fil = tmp_path / "ljud.ogg"
    fil.write_bytes(b"ogg")
    _fejka(monkeypatch, {"detail": {"status": "invalid_api_key",
                                    "message": "Invalid API key."}}, status=401)
    with pytest.raises(elevenlabs_asr.MolnFel) as fel:
        elevenlabs_asr.transkribera_fil(fil, "el-fel")
    assert "nyckeln" in str(fel.value).lower()
    assert "401" in str(fel.value)


def test_detail_som_strang_hanteras():
    assert "Försök igen" in elevenlabs_asr._felmeddelande(503, '{"detail": "overloaded"}')
    assert "overloaded" in elevenlabs_asr._felmeddelande(503, '{"detail": "overloaded"}')


def test_trasigt_svar_blir_molnfel(tmp_path, monkeypatch):
    fil = tmp_path / "ljud.ogg"
    fil.write_bytes(b"ogg")
    _fejka(monkeypatch, "<html>inte json</html>")
    with pytest.raises(elevenlabs_asr.MolnFel) as fel:
        elevenlabs_asr.transkribera_fil(fil, "el-x")
    assert "JSON" in str(fel.value)


# ---- Omtag ----------------------------------------------------------------

def test_429_tas_om_och_gar_igenom(monkeypatch):
    monkeypatch.setattr(elevenlabs_asr, "BACKOFF", (0.0, 0.0, 0.0))
    forsok = {"n": 0}

    def gor():
        forsok["n"] += 1
        if forsok["n"] < 3:
            raise elevenlabs_asr.MolnFel(429, "lugn")
        return "klart"

    assert elevenlabs_asr.med_omtag(gor) == "klart"
    assert forsok["n"] == 3


def test_401_tas_aldrig_om():
    forsok = {"n": 0}

    def gor():
        forsok["n"] += 1
        raise elevenlabs_asr.MolnFel(401, "avvisad")

    with pytest.raises(elevenlabs_asr.MolnFel):
        elevenlabs_asr.med_omtag(gor)
    assert forsok["n"] == 1


def test_avbryt_biter_under_backoff(monkeypatch):
    monkeypatch.setattr(elevenlabs_asr, "BACKOFF", (5.0,))

    def gor():
        raise elevenlabs_asr.MolnFel(500, "fel")

    with pytest.raises(RuntimeError, match="avbröts"):
        elevenlabs_asr.med_omtag(gor, avbruten=lambda: True)


# ---- Hela vägen (utan ffmpeg och nät) -------------------------------------

def _fejka_omkodning(monkeypatch):
    monkeypatch.setattr(elevenlabs_asr, "_koda_om",
                        lambda audio, dest: (dest.write_bytes(b"ogg"), dest)[1])


def test_transkribera_ger_resultat_och_ett_enda_delta(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-x")
    _fejka_omkodning(monkeypatch)
    _fejka(monkeypatch, SVAR_OK)
    deltan, pct = [], []
    res = elevenlabs_asr.transkribera(
        tmp_path / "in.wav", tmp_path, langd=6.0, sprak="sv",
        delta_cb=deltan.append, progress_cb=pct.append)
    assert res.text == "Hej världen."
    assert res.sprak == "sv" and res.sekunder == 6.0
    assert [o["text"] for o in res.ord] == ["Hej", "världen."]
    assert deltan == ["Hej världen."]      # ETT delta — hela texten på en gång
    assert pct == [10, 100] and pct == sorted(pct)


def test_tempkatalogen_stadas_aven_vid_fel(tmp_path, monkeypatch):
    import tempfile as tf
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-x")
    _fejka_omkodning(monkeypatch)
    _fejka(monkeypatch, {"detail": {"message": "nej"}}, status=400)
    fore = set(Path(tf.gettempdir()).glob("transkribera-moln-*"))
    with pytest.raises(elevenlabs_asr.MolnFel):
        elevenlabs_asr.transkribera(tmp_path / "in.wav", tmp_path, langd=6.0)
    assert set(Path(tf.gettempdir()).glob("transkribera-moln-*")) == fore
