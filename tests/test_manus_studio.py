"""manus_studio.py — servern bakom inspelningsfönstret.

Mikrofonen och molnet är inte med här: det som testas är rutterna, jobbtråden
och att en inspelning blir en fullständig mapp. Själva arbetet är manus.kor(),
som har egna tester.
"""
import json
import threading
import urllib.request
from base64 import b64encode
from http.server import ThreadingHTTPServer

import pytest

import manus
import manus_studio


@pytest.fixture
def server():
    """En riktig server på en slumpad port — rutterna ska prövas över HTTP, inte
    genom att anropa metoderna direkt."""
    srv = ThreadingHTTPServer(("127.0.0.1", 0), manus_studio.Studio)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _hamta(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=5) as svar:
            return svar.status, svar.read()
    except urllib.error.HTTPError as fel:
        return fel.code, fel.read()


def test_startsidan_ar_html(server):
    kod, kropp = _hamta(server + "/")
    assert kod == 200
    assert b"Manusstudio" in kropp


def test_cachebrytare_i_url_ger_fortfarande_sidan(server):
    # Regressionen: sökvägen matchades tecken för tecken, så «/?cb=2» blev 404.
    assert _hamta(server + "/?cb=2")[0] == 200


def test_okand_vag_ar_404(server):
    assert _hamta(server + "/nagot")[0] == 404


def test_lage_ar_json_med_de_falt_fonstret_laser(server):
    kod, kropp = _hamta(server + "/lage")
    assert kod == 200
    assert set(json.loads(kropp)) >= {"lage", "logg", "pct", "filer", "fel", "mapp"}


def test_inspelningen_blir_en_mapp_med_ljud_manus_och_undertexter(monkeypatch, tmp_path):
    """Hela jobbtråden, med molnet och ffmpeg bortkopplade."""
    monkeypatch.setattr(manus_studio, "UT", tmp_path)
    monkeypatch.setattr(manus_studio, "_remuxa", lambda ra, mal: (mal.write_bytes(b"ogg"), mal)[1])
    korda = {}

    def kor(media, manusfil, format, sprak, ut_mapp, **kw):
        korda.update(media=media, manusfil=manusfil, format=format)
        kw["logg"]("kör")
        kw["pct"]("Tider", 100)
        return [media.with_suffix(".srt")]

    monkeypatch.setattr(manus, "kor", kor)
    manus_studio._arbeta("Derivatan, del 1", "Manuset står här.", b"ljud", ".webm")

    mapp = tmp_path / "Derivatan, del 1"
    assert (mapp / "Derivatan, del 1.ogg").exists()
    # Manuset sparas bredvid ljudet: om ett halvår är det enda källan till vad
    # som SKULLE sägas — undertexten bär bara vad som sades.
    assert (mapp / "Derivatan, del 1.txt").read_text(encoding="utf-8") == "Manuset står här.\n"
    assert korda["manusfil"] == mapp / "Derivatan, del 1.txt"
    assert korda["format"] == ["srt", "vtt", "json"]
    assert manus_studio._jobb["lage"] == "klar"
    assert manus_studio._jobb["pct"] == 100


def test_tomt_namn_blir_ett_datum_och_otillatna_tecken_stryks(monkeypatch, tmp_path):
    monkeypatch.setattr(manus_studio, "UT", tmp_path)
    monkeypatch.setattr(manus_studio, "_remuxa", lambda ra, mal: (mal.write_bytes(b"ogg"), mal)[1])
    monkeypatch.setattr(manus, "kor", lambda *a, **kw: [])
    manus_studio._arbeta("Kap 3: derivata?", "", b"ljud", ".webm")
    # Kolon och frågetecken går inte att skriva i ett filnamn på Windows — och
    # ett kolon hade dessutom skapat en NTFS-dataström i stället för en mapp.
    assert (tmp_path / "Kap 3 derivata").is_dir()

    manus_studio._arbeta("", "", b"ljud", ".webm")
    assert [d.name for d in tmp_path.iterdir() if d.name.startswith("Manus ")]


def test_fel_i_jobbet_blir_en_mening_i_fonstret(monkeypatch, tmp_path):
    monkeypatch.setattr(manus_studio, "UT", tmp_path)
    monkeypatch.setattr(manus_studio, "_remuxa", lambda ra, mal: (_ for _ in ()).throw(
        RuntimeError("Kunde inte läsa inspelningen")))
    manus_studio._arbeta("Prov", "", b"ljud", ".webm")
    assert manus_studio._jobb["lage"] == "fel"
    assert "Kunde inte läsa inspelningen" in manus_studio._jobb["fel"]


def test_molnets_delta_byggs_till_EN_rad_i_loggen(monkeypatch):
    manus_studio._satt(logg=[])
    manus_studio._logg("Skickar 1 del ...")
    for bit in ("Mamma ", "denna ", "låt."):
        manus_studio._strom(bit)
    # Hundra deltan får inte bli hundra rader — det är en mening som växer.
    assert manus_studio._jobb["logg"] == ["Skickar 1 del ...", "…Mamma denna låt."]


def test_posta_medan_ett_jobb_kors_startar_inte_ett_till(server, monkeypatch):
    monkeypatch.setitem(manus_studio._jobb, "lage", "arbetar")
    kropp = json.dumps({"namn": "x", "manus": "", "ljud": b64encode(b"a").decode(),
                        "andelse": ".webm"}).encode()
    with urllib.request.urlopen(urllib.request.Request(
            server + "/spela", data=kropp,
            headers={"Content-Type": "application/json"}), timeout=5) as svar:
        assert "fel" in json.loads(svar.read())
