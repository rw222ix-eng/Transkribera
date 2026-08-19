"""Hela molnkörningen med beordringsbara fel (Etapp 2).

Skillnaden mot tests/test_transcribe_progress.py: där är
`elevenlabs_asr.transkribera` utbytt mot en attrapp, här körs den PÅ RIKTIGT.
Bara ffmpeg (omkodningen) är stubbad, så anropet, omtagen, kostnaden ur
audio_duration_secs och ordtidernas väg till segment exekverar som de gör på
lärarens maskin — mot ett moln vi kan be bete sig hur illa som helst
(tests/fejk.py).

Det som prövas är löftena i vägen ut till skärmen:
  * kostnaden kommer ur det API:et debiterar, aldrig ur filens längd,
  * ett tillfälligt fel kostar en paus och inte lektionen,
  * ett fel som inte går över blir ett svenskt besked med en väg vidare,
  * framsteget går bara framåt,
  * inget halvfärdigt hamnar i historiken.
"""
from __future__ import annotations

import json

import pytest

from app import elevenlabs_asr
from app.web import server
from tests.conftest import HW
from tests.fejk import Moln


class _Arbiter:
    def __init__(self):
        self.slappt = 0
    def try_acquire_gpu(self): return "nyckel"
    def try_acquire_llm(self): return "nyckel"
    def release_gpu(self, nyckel=None): self.slappt += 1
    def release_llm(self, nyckel=None): self.slappt += 1
    def stop_llm(self): return False
    def ensure_llm(self): return None
    def ensure_model(self, spec=None): return None
    def prewarm_async(self): pass
    def llm_installed(self): return False


@pytest.fixture
def rigg(tmp_path, monkeypatch):
    """Servern med RIKTIG elevenlabs_asr, fejkat moln och stubbad ffmpeg."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test")
    monkeypatch.setattr(elevenlabs_asr, "_koda_om",
                        lambda audio, dest: (dest.write_bytes(b"ogg"), dest)[1])
    monkeypatch.setattr(server.transcriber, "write_outputs",
                        lambda segs, base, fmts: [tmp_path / "ut.srt"])
    monkeypatch.setattr(server.output_store, "assemble_output",
                        lambda *a, **k: {"files": [], "video": None,
                                         "folder": str(tmp_path)})

    arb = _Arbiter()
    media = tmp_path / "lektion.mp3"
    media.write_bytes(b"ljud")

    def kor(*, langd=700.0, lagen="ok"):
        """En körning. `lagen` är ett läge per HTTP-anrop (fejk.Moln) —
        omtagen är de enda som ger fler än ett."""
        moln = Moln(lagen).installera(monkeypatch)
        monkeypatch.setattr(server.media_mod, "probe_duration", lambda *_: langd)
        c = TestClient(server.create_app(base_dir=tmp_path, arbiter=arb))
        r = c.post("/api/transcribe", json={
            "source": str(media), "language": "sv", "formats": ["srt"]})
        return c, r, moln

    kor.arb = arb
    kor.tmp = tmp_path
    return kor


def _events(text):
    return [json.loads(rad[len("data:"):])
            for rad in text.splitlines() if rad.startswith("data:")]


def _typ(text, typ):
    return [e for e in _events(text) if e["type"] == typ]


# ── Kostnaden ────────────────────────────────────────────────────────────

def test_kostnaden_kommer_ur_svaret_inte_ur_filens_langd(rigg):
    """700 s ljud, men fejken debiterar 6 s — kostnaden ska vara 6 s × priset,
    inte 700 s. En fil kan innehålla tystnad, och läraren ska aldrig debiteras
    för mer än det API:et fakturerade."""
    c, r, moln = rigg(langd=700.0)
    assert len(moln.anrop) == 1                    # hela filen i ETT anrop
    kostnad = _typ(r.text, "kostnad")
    assert len(kostnad) == 1
    assert kostnad[0]["usd"] == pytest.approx(elevenlabs_asr.kostnad_usd(6.0))
    assert kostnad[0]["minuter"] == pytest.approx(0.1, abs=0.05)


def test_hela_texten_kommer_som_ett_delta(rigg):
    c, r, moln = rigg(langd=100.0)
    delta = _typ(r.text, "delta")
    assert [d["text"] for d in delta] == ["Hej världen."]


def test_ordtiderna_ur_svaret_blir_segment(rigg):
    """Molnets ordtider ska bära hela vägen till historiken — ingen lokal
    tidsättning finns kvar att rädda dem."""
    c, r, moln = rigg(langd=100.0)
    assert _typ(r.text, "error") == []
    post = c.get("/api/history").json()[0]
    assert post["words"] == 2                      # «Hej världen.»


# ── Felmoderna ───────────────────────────────────────────────────────────

def test_429_kostar_en_paus_inte_lektionen(rigg):
    c, r, moln = rigg(langd=700.0, lagen=["429", "ok"])
    assert len(moln.anrop) == 2                    # ett omtag
    assert _typ(r.text, "error") == []
    assert len(c.get("/api/history").json()) == 1


def test_ett_429_som_inte_gar_over_blir_ett_besked(rigg):
    c, r, moln = rigg(langd=100.0, lagen="429")
    fel = _typ(r.text, "error")
    assert fel and "429" in fel[0]["message"]
    assert "kvot" in fel[0]["message"] or "många" in fel[0]["message"]
    assert c.get("/api/history").json() == []      # inget halvfärdigt sparas
    assert rigg.arb.slappt == 1                    # GPU:n släpps ändå


def test_avvisad_nyckel_pekar_pa_installningarna(rigg):
    c, r, moln = rigg(langd=100.0, lagen="401")
    fel = _typ(r.text, "error")
    assert fel and "401" in fel[0]["message"]
    assert "nyckeln" in fel[0]["message"].lower()
    assert len(moln.anrop) == 1                    # 401 tas aldrig om


def test_natet_som_dor_under_uppladdningen_tas_om(rigg):
    """Uppladdningen dör på vägen: omtaget skickar om hela filen, och texten
    som till slut kommer är hel."""
    c, r, moln = rigg(langd=100.0, lagen=["dor", "ok"])
    assert len(moln.anrop) == 2
    assert _typ(r.text, "error") == []
    post = c.get("/api/history").json()[0]
    assert post["words"] >= 2


def test_en_timeout_mot_molnet_tas_ocksa_om(rigg):
    c, r, moln = rigg(langd=100.0, lagen=["timeout", "ok"])
    assert len(moln.anrop) == 2 and _typ(r.text, "error") == []


def test_ett_tomt_svar_blir_ett_besked_inte_en_tom_fil(rigg):
    """Molnet svarade, men utan text. Att skriva en tom SRT vore att låtsas."""
    c, r, moln = rigg(langd=100.0, lagen="tomt")
    fel = _typ(r.text, "error")
    assert fel and "resultat" in fel[0]["message"]
    assert c.get("/api/history").json() == []


def test_trasig_json_i_svaret_blir_ett_besked(rigg):
    """Ett 200 som inte är JSON är ett fel med namn — inte en tyst tom fil."""
    c, r, moln = rigg(langd=100.0, lagen="trasig")
    fel = _typ(r.text, "error")
    assert fel and "JSON" in fel[0]["message"]


def test_disken_som_tar_slut_blir_507_och_inte_ett_tyst_tapp(rigg, monkeypatch):
    """Inspelningen flushas till <session>.part medan lektionen pågår. Tar
    disken slut ska klienten få veta det NU — inte upptäcka det efter 70
    minuter."""
    c, _, _ = rigg(langd=100.0)

    import builtins
    riktiga = builtins.open

    def full(fil, lage="r", *a, **k):
        if str(fil).endswith(".part") and "a" in lage:
            raise OSError(28, "No space left on device")
        return riktiga(fil, lage, *a, **k)
    monkeypatch.setattr(builtins, "open", full)

    r = c.post("/api/recording/append", params={"session": "abc"}, content=b"x")
    assert r.status_code == 507
    assert "utrymme" in r.json()["error"]


# ── Framsteget ───────────────────────────────────────────────────────────

def _pcts(text):
    return [e["pct"] for e in _typ(text, "progress")]


def test_framsteget_gar_bara_framat(rigg):
    c, r, moln = rigg(langd=700.0)
    pct = _pcts(r.text)
    assert pct == sorted(pct), pct
    assert pct[0] >= 0 and pct[-1] <= 100
    # Molnets band är 0–60: omkodningen klar och svaret mottaget ska båda synas.
    molnband = [p for p in pct if p <= 60]
    assert len(molnband) >= 2
