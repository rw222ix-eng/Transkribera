"""Förbannade uppladdningar (Etapp 2) — appen ska fela snyggt, aldrig hänga.

Källorna är fem: en lokal fil, drag-och-släpp, en URL, en inspelning i delar
(som ska gå att rädda efter en krasch) och exempelfilen. Det som kommer in den
vägen är sällan det man tänkt sig: en trunkerad MP3 från en telefon som dog,
en .wav som egentligen är en .m4a, en video utan ljudspår, noll byte, och
filnamn med å ä ö, `& % #` och tecken Windows vägrar skriva.

Kravet är litet och hårt: varje sådan fil ska ge ett svenskt besked som säger
vad läraren kan göra — inte ett 500-svar, inte en tom sträng, och framför allt
inte en bar som står still. En lektion går inte att spela in igen.
"""
from __future__ import annotations

import pytest

from app import paths
from app.web import server


# ── Namnen ────────────────────────────────────────────────────────────────
# `Path(name).name` tog bort mappdelarna men inte tecknen Windows vägrar
# skriva. «fråga?.mp3» blev OSError inne i write_bytes — 500 utan besked.

FORBANNADE_NAMN = [
    ("lektion.mp3", "lektion.mp3"),                       # det vanliga
    ("Åk 3 – prov & repetition #2.m4a",                   # åäö, &, #, tankstreck
     "Åk 3 – prov & repetition #2.m4a"),
    ("100 % klart.wav", "100 % klart.wav"),
    ("fråga?.mp3", "fråga.mp3"),                          # Windows vägrar ?
    ("a*b.mp3", "ab.mp3"),
    ("v45|v46.mp3", "v45v46.mp3"),
    ("..\\..\\Windows\\system32\\evil.mp3", "evil.mp3"),  # ingen klättring
    ("../../etc/passwd", "passwd"),
    ("", "inspelning.webm"),                              # tomt namn
    (".", "inspelning.webm"),
    ("..", "inspelning.webm"),
    ("   .mp3", "inspelning.webm"),                       # bara blanksteg
]


@pytest.mark.parametrize("namn,vantat", FORBANNADE_NAMN)
def test_uppladdningens_filnamn_gar_alltid_att_skriva(client, namn, vantat):
    r = client.post("/api/upload", params={"name": namn}, content=b"ljud")
    assert r.status_code == 200, r.text
    sparad = client.base_dir / "downloads" / vantat
    assert sparad.is_file(), f"{namn!r} skrevs inte som {vantat!r}"
    assert sparad.read_bytes() == b"ljud"
    # Aldrig utanför downloads/ — hur namnet än ser ut.
    assert sparad.resolve().parent == (client.base_dir / "downloads").resolve()


def test_kolon_skapar_ingen_dold_dataström(client):
    """`x:y.mp3` är inte ett filnamn på NTFS utan en dataström på filen `x`:
    uppladdningen «lyckas» och filen finns ändå inte när ffmpeg ska läsa den."""
    r = client.post("/api/upload", params={"name": "x:y.mp3"}, content=b"ljud")
    assert r.status_code == 200
    downloads = client.base_dir / "downloads"
    filer = [p.name for p in downloads.iterdir()]
    assert filer == ["y.mp3"]
    assert (downloads / "y.mp3").read_bytes() == b"ljud"


def test_noll_byte_avvisas_med_besked(client):
    r = client.post("/api/upload", content=b"")
    assert r.status_code == 400
    assert "tom" in r.json()["error"].lower()


def test_for_stor_uppladdning_avvisas_pa_headern(client):
    """Taket är 2 GB. Avvisandet sker på Content-Length — annars buffras
    två gigabyte i RAM innan servern hinner säga nej."""
    r = client.post("/api/upload", content=b"x",
                    headers={"content-length": str(server.MAX_UPLOAD_BYTES + 1)})
    assert r.status_code == 413
    assert "stor" in r.json()["error"].lower()


def test_samma_namn_tva_ganger_skriver_inte_over(client):
    client.post("/api/upload", params={"name": "lektion.mp3"}, content=b"ett")
    client.post("/api/upload", params={"name": "lektion.mp3"}, content=b"tva")
    filer = sorted(p.read_bytes() for p in (client.base_dir / "downloads").iterdir())
    assert filer == [b"ett", b"tva"], "en inspelning skrevs över av nästa"


def test_safe_name_ar_ren_och_behaller_andelsen():
    assert paths.safe_name("a" * 300 + ".mp3").endswith(".mp3")
    assert len(paths.safe_name("a" * 300 + ".mp3")) <= 120
    assert paths.safe_name("", "reserv.webm") == "reserv.webm"


# ── Inspelningen i delar ──────────────────────────────────────────────────
# En lektion går inte att spela in igen: varje bit flushas till <session>.part
# så en krasch lämnar en fil som går att rädda.

def test_delad_inspelning_overlever_en_krasch(client):
    for bit in (b"del1", b"del2", b"del3"):
        assert client.post("/api/recording/append", params={"session": "abc"},
                           content=bit).status_code == 200
    # «Kraschen»: ingen finish. Det halvfärdiga ska synas och gå att rädda.
    kvar = client.get("/api/recordings/incomplete").json()
    assert len(kvar) == 1 and kvar[0]["bytes"] == 12
    r = client.post("/api/recording/finish",
                    params={"session": "abc", "name": "räddad?.webm"})
    assert r.status_code == 200
    assert (client.base_dir / "downloads" / "räddad.webm").read_bytes() == b"del1del2del3"


def test_delad_inspelning_med_otillaten_session_avvisas(client):
    for session in ("../hemligt", "a/b", "x" * 100, ""):
        r = client.post("/api/recording/append", params={"session": session},
                        content=b"x")
        assert r.status_code == 400, session


# ── Filerna som inte går att läsa ────────────────────────────────────────
# Det som skiljer «trasig fil» från «ffmpeg saknas» är vad läraren ska GÖRA,
# och därför måste beskeden skilja sig åt. Båda vägarna ska sluta med ett
# felkort — aldrig med en körning som står still.

class _Arbiter:
    def try_acquire_gpu(self): return True
    def release_gpu(self): pass
    def stop_llm(self): return False
    def ensure_llm(self): return None
    def ensure_model(self, spec=None): return None
    def prewarm_async(self): pass
    def llm_installed(self): return False


FORBANNADE_FILER = [
    ("trunkerad.mp3", b"\xff\xfb\x90d" + b"\x00" * 40),   # halv MP3-ram
    ("noll.wav", b""),                                     # 0 byte
    ("fel-andelse.wav", b"\x00\x00\x00\x20ftypM4A "),      # m4a som heter wav
    ("korrupt-header.mp4", b"NOTAHEADER" * 4),
    ("bara-video.mkv", b"\x1aE\xdf\xa3" + b"\x00" * 32),   # inget ljudspår
]


@pytest.mark.parametrize("namn,innehall", FORBANNADE_FILER)
@pytest.mark.ffmpeg
def test_en_fil_som_inte_gar_att_lasa_blir_ett_besked(tmp_path, monkeypatch,
                                                      namn, innehall):
    """Med RIKTIG ffprobe: ingen av de här filerna har en speltid, och då ska
    körningen stanna direkt med ett besked om filen — inte skicka noll bitar
    till molnet och skylla på ljudet efteråt."""
    from fastapi.testclient import TestClient
    from tests.conftest import HW

    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    monkeypatch.setattr(server.openai_asr, "har_nyckel", lambda *a, **k: True)
    # Molnet får ALDRIG nås med en fil vi inte kunnat läsa en längd ur.
    monkeypatch.setattr(server.openai_asr, "transkribera",
                        lambda *a, **k: pytest.fail("molnet anropades på en trasig fil"))
    c = TestClient(server.create_app(base_dir=tmp_path, arbiter=_Arbiter()))
    fil = tmp_path / namn
    fil.write_bytes(innehall)

    r = c.post("/api/transcribe", json={"source": str(fil), "language": "sv",
                                        "formats": ["srt"]})
    assert r.status_code == 200
    assert "error" in r.text
    assert namn in r.text or "speltid" in r.text
    assert "gav inget resultat" not in r.text


def test_fil_som_inte_finns_sags_rakt_ut(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from tests.conftest import HW

    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    monkeypatch.setattr(server.openai_asr, "har_nyckel", lambda *a, **k: True)
    c = TestClient(server.create_app(base_dir=tmp_path, arbiter=_Arbiter()))
    r = c.post("/api/transcribe", json={"source": str(tmp_path / "borta.mp3"),
                                        "language": "sv", "formats": ["srt"]})
    assert "Filen finns inte" in r.text
