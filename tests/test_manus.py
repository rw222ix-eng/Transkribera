"""manus.py — det lilla programmet vid sidan av appen.

Testet rör bara kabeldragningen: att manuset går in som ledtext, att ordtiderna
skrivs FÖRE undertextgrupperingen (som tappar dem), och att felen kommer som
begripliga meningar i stället för tracebacks. Molnet och tidsättningen är
fejkade — de har egna tester.
"""
import json

import pytest

import manus
from app import openai_asr


@pytest.fixture
def fejkat_moln(monkeypatch):
    """Sömmarna beordrade: probe, nyckel, moln, tidsättning. Returnerar en dict
    där testet kan läsa vad molnet FICK (ledtexten är hela poängen)."""
    sett: dict = {}

    def transkribera(audio, base, *, langd, sprak="", ledtext="", log_cb=None,
                     progress_cb=None, delta_cb=None, avbruten=None):
        sett.update(ledtext=ledtext, sprak=sprak, langd=langd)
        if delta_cb:
            delta_cb("Derivatan mäter förändring.")
        r = openai_asr.Resultat()
        r.bitar.append(openai_asr.Bit(0.0, 12.0, "Derivatan mäter förändring.", 12.0))
        return r

    def tidsatt(audio, bitar, models_root, **kw):
        return [{"start": 0.0, "end": 2.5, "text": "Derivatan mäter förändring.",
                 "words": [{"text": "Derivatan", "start": 0.0, "end": 1.0},
                           {"text": "mäter", "start": 1.0, "end": 1.7},
                           {"text": "förändring.", "start": 1.7, "end": 2.5}]}]

    monkeypatch.setattr(manus.media_mod, "probe_duration", lambda p: 12.0)
    monkeypatch.setattr(manus.openai_asr, "har_nyckel", lambda base: True)
    monkeypatch.setattr(manus.openai_asr, "transkribera", transkribera)
    monkeypatch.setattr(manus.alignment, "ar_installerad", lambda root: True)
    monkeypatch.setattr(manus.alignment, "tidsatt", tidsatt)
    monkeypatch.setattr(manus.alignment, "frigor", lambda: None)
    return sett


@pytest.fixture
def ljud(tmp_path):
    p = tmp_path / "video1.wav"
    p.write_bytes(b"RIFF")
    return p


def test_de_tre_filerna_skrivs_bredvid_ljudet(fejkat_moln, ljud):
    manus.main([str(ljud)])
    assert ljud.with_suffix(".srt").exists()
    assert ljud.with_suffix(".vtt").exists()
    assert ljud.with_suffix(".ord.json").exists()


def test_srt_och_vtt_bar_samma_tid_i_var_sin_notation(fejkat_moln, ljud):
    manus.main([str(ljud), "-f", "srt,vtt"])
    assert "00:00:00,000 --> 00:00:02,500" in ljud.with_suffix(".srt").read_text(encoding="utf-8")
    vtt = ljud.with_suffix(".vtt").read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:02.500" in vtt


def test_ordtiderna_overlever_till_json(fejkat_moln, ljud):
    # Regressionen som lurar: clean_caption_dicts grupperar om segmenten och
    # tappar `words` på vägen. Skrivs JSON efter den blir filen värdelös för
    # animationssynk — som är hela skälet till att den finns.
    manus.main([str(ljud), "-f", "json"])
    data = json.loads(ljud.with_suffix(".ord.json").read_text(encoding="utf-8"))
    assert data["media"] == "video1.wav"
    assert [o["text"] for o in data["segment"][0]["words"]] == \
        ["Derivatan", "mäter", "förändring."]


def test_manuset_gar_in_som_ledtext_utan_radbrytningar(fejkat_moln, ljud, tmp_path):
    (tmp_path / "m.txt").write_text("Derivatan\n\nmäter förändring.\n", encoding="utf-8")
    manus.main([str(ljud), "--manus", str(tmp_path / "m.txt")])
    assert fejkat_moln["ledtext"] == "Derivatan mäter förändring."


def test_utan_manus_skickas_ingen_ledtext(fejkat_moln, ljud):
    manus.main([str(ljud)])
    assert fejkat_moln["ledtext"] == ""


def test_ut_mappen_skapas_och_filerna_hamnar_dar(fejkat_moln, ljud, tmp_path):
    manus.main([str(ljud), "-u", str(tmp_path / "ut"), "-f", "srt"])
    assert (tmp_path / "ut" / "video1.srt").exists()
    assert not ljud.with_suffix(".srt").exists()


def test_saknad_fil_ger_en_mening_inte_en_traceback(fejkat_moln, tmp_path):
    with pytest.raises(SystemExit) as fel:
        manus.main([str(tmp_path / "finns-inte.wav")])
    assert "finns inte" in str(fel.value)


def test_saknad_nyckel_pekar_pa_nyckelfilen(fejkat_moln, ljud, monkeypatch):
    monkeypatch.setattr(manus.openai_asr, "har_nyckel", lambda base: False)
    with pytest.raises(SystemExit) as fel:
        manus.main([str(ljud)])
    assert openai_asr.NYCKELFIL in str(fel.value)


def test_okant_format_stoppas_fore_molnet(fejkat_moln, ljud):
    # Före, inte efter: annars är ljudminuterna betalda när felet kommer.
    with pytest.raises(SystemExit) as fel:
        manus.main([str(ljud), "-f", "srt,doc"])
    assert "doc" in str(fel.value)
    assert "langd" not in fejkat_moln


def test_tidsmodellen_hamtas_nar_den_saknas(fejkat_moln, ljud, monkeypatch):
    hamtat = []
    monkeypatch.setattr(manus.alignment, "ar_installerad", lambda root: False)
    monkeypatch.setattr(manus.alignment, "ladda_ner",
                        lambda root, **kw: hamtat.append(root))
    manus.main([str(ljud), "-f", "srt"])
    assert hamtat, "tidsmodellen ska hämtas automatiskt första gången"
