"""Bildlagret (tools/bildlager.py, blad-bygg.js bildlager): formen på datan och
vägen genom appens API.

Lärarens dom 2026-10-02: pilar och mått ovanpå arbetsbladets målade bilder.
Datan bor i dokumentet (`v.bildlager`), och servern lagrar dokumentet utan att
tolka det, så samma rundtur fungerar mot en server med gammal Python i minnet.
"""
import base64
import json

import pytest

from tools import bildlager as bl

TUNNEL = [
    {"typ": "linje", "fran": [0, 0.22], "till": [1, 0.22], "streckad": True,
     "text": "markytan $0$ m"},
    {"typ": "pil", "fran": [0.12, 0.5], "till": [0.38, 0.42], "text": "taket $-1$ m"},
    {"typ": "pil", "fran": [0.12, 0.92], "till": [0.38, 0.86], "text": "golvet $-4$ m"},
    {"typ": "matt", "fran": [0.6, 0.42], "till": [0.6, 0.86], "text": "? m"},
    {"typ": "etikett", "plats": [0.8, 0.1], "text": "Saga: 5 m"},
    {"typ": "ring", "mitt": [0.5, 0.6], "r": 0.1, "sida": "ner"},
]


def test_tunnellagret_duger():
    assert bl.validera(TUNNEL) == []


@pytest.mark.parametrize("lager, del_av_fel", [
    ("pil", "lista"),
    ([], "tomt"),
    ([{"typ": "pilen", "fran": [0, 0], "till": [1, 1]}], "okänd typ"),
    ([{"typ": "pil", "fran": [0, 0]}], "saknar till"),
    ([{"typ": "pil", "form": [0, 0], "fran": [0, 0], "till": [1, 1]}], "okänt fält form"),
    ([{"typ": "pil", "fran": [0, 1.2], "till": [1, 1]}], "mellan 0 och 1"),
    ([{"typ": "pil", "fran": [0, True], "till": [1, 1]}], "mellan 0 och 1"),
    ([{"typ": "matt", "fran": [0.5, 0.5], "till": [0.5, 0.505], "text": "1 m"}], "samma punkt"),
    ([{"typ": "matt", "fran": [0, 0], "till": [0, 1]}], "saknar text"),
    ([{"typ": "etikett", "plats": [0.5, 0.5], "text": "$-4 m"}], "udda antal $"),
    ([{"typ": "etikett", "plats": [0.5, 0.5], "text": "x" * 41}], "högst 40"),
    ([{"typ": "etikett", "plats": [0.5, 0.5], "text": "a", "sida": "norr"}], "sida"),
    ([{"typ": "pil", "fran": [0, 0], "till": [1, 1], "textvid": "mitt"}], "svans eller spets"),
    ([{"typ": "linje", "fran": [0, 0], "till": [1, 1], "streckad": "ja"}], "true eller false"),
    ([{"typ": "ring", "mitt": [0.5, 0.5], "r": 0.9}], "r ska vara"),
    ([{"typ": "etikett", "plats": [0.5, 0.5], "text": "a"}] * 13, "högst 12"),
])
def test_felen_sags_med_namn(lager, del_av_fel):
    fel = bl.validera(lager)
    assert any(del_av_fel in f for f in fel), fel


def test_nyckeln():
    assert bl.nyckel_for("5") == "uppg5"
    assert bl.nyckel_for("uppg12") == "uppg12"
    assert bl.nyckel_for("forsatt") == "forsatt"
    with pytest.raises(bl.Fel):
        bl.nyckel_for("../x")


def test_scennyckeln_ar_blad_js_scenNyckel():
    """Samma märke som plan.js sätter när läraren släpper en bild, annars ritar
    blad.js bilden som inaktuell (bilden-foljer-scenen.spec.mjs)."""
    assert bl.scen_nyckel({"t": "x", "scen": {"filnamn": "a-03-slang", "begrepp": "b"}}) == "a-03-slang"
    assert bl.scen_nyckel({"t": "Lös  ekvationen\n nu"}) == "Lös ekvationen nu"
    assert bl.scen_nyckel(None) == ""


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def _papper():
    return {
        "typ": "Arbetsblad", "moment": "Negativa tal", "klass": "BA26B",
        "kurs": "Matematik, nivå 1a", "datum": "2026-10-05", "tid": "",
        "bilder": {}, "andrat": [], "uppgifter": [
            {"nr": 5, "p": 2, "t": "Taket i en gångtunnel ligger på $-1$ m.",
             "scen": {"filnamn": "a-40-gangtunnel", "begrepp": "negativa tal"}}],
    }


@pytest.fixture
def via_klienten(client, monkeypatch):
    """Verktygets HTTP-anrop går till testklienten i stället för en riktig port."""
    def anrop(server, metod, vag, kropp=None, raw=False):
        r = client.request(metod, vag, json=kropp)
        if r.status_code >= 400:
            raise bl.Fel(f"{metod} {vag}: {r.status_code}")
        return r.content if raw else r.json()
    monkeypatch.setattr(bl, "_anrop", anrop)
    return client


def test_rundturen_genom_api(via_klienten, tmp_path):
    c = via_klienten
    dok = c.post("/api/dokument", json={"dokument": _papper(), "status": "godkant"}).json()
    fil = tmp_path / "tunnel.png"
    fil.write_bytes(PNG)

    bl.lagg_bild("x", dok["id"], "5", fil)
    bl.satt_lager("x", dok["id"], "5", TUNNEL)
    rad = c.get("/api/dokument").json()["sparade"][0]
    v = rad["dokument"]
    assert v["bildlager"] == {"uppg5": TUNNEL}
    assert v["bildscen"] == {"uppg5": "a-40-gangtunnel"}
    assert rad["markor"] == 2
    # Bilden kommer tillbaka som bytes, hur listan än serverar den.
    assert c.get(f"/api/dokument/{dok['id']}/bild/uppg5").content == PNG

    ut = tmp_path / "ut.png"
    assert bl.hamta_bild("x", dok["id"], "uppg5", ut) == "lärarens bild"
    assert ut.read_bytes() == PNG

    bl.ta_bort_lager("x", dok["id"], "uppg5")
    v = c.get("/api/dokument").json()["sparade"][0]["dokument"]
    assert v["bildlager"] == {}
    # Bilden står kvar genom alla tre skrivningarna (server.py _ater_bilder).
    assert c.get(f"/api/dokument/{dok['id']}/bild/uppg5").content == PNG


def test_ett_trasigt_lager_skrivs_aldrig(via_klienten):
    c = via_klienten
    dok = c.post("/api/dokument", json={"dokument": _papper(), "status": "godkant"}).json()
    with pytest.raises(bl.Fel, match="duger inte"):
        bl.satt_lager("x", dok["id"], "5", [{"typ": "pil", "fran": [0, 0]}])
    assert c.get("/api/dokument").json()["sparade"][0]["markor"] == 0


def test_kommandoraden_validerar(tmp_path, capsys):
    f = tmp_path / "l.json"
    f.write_text(json.dumps(TUNNEL), encoding="utf-8")
    assert bl.main(["validera", str(f)]) == 0
    f.write_text(json.dumps([{"typ": "pil"}]), encoding="utf-8")
    assert bl.main(["validera", str(f)]) == 1
    assert "saknar fran" in capsys.readouterr().out
