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


# ── Provets PDF: lagret ritat i bilden (app/bildlager_rita.py) ─────────────
# Rickard 2026-10-08, prov 163. Provet sätts i LaTeX och ser inte skärmens
# lager, så godkännandet ritar in det i en kopia av bilden.

GRA = (128, 128, 128)


def _gra(bredd=800, hojd=450):
    from PIL import Image
    return Image.new("RGB", (bredd, hojd), GRA)


def _andrat(fore, efter):
    from PIL import ImageChops
    return ImageChops.difference(fore.convert("RGB"), efter.convert("RGB")).getbbox()


def test_pilen_andrar_bilden_dar_den_gar_och_ingen_annanstans():
    from app import bildlager_rita as br
    bild = _gra()
    ut = br.rita(bild, [{"typ": "pil", "fran": [0.2, 0.5], "till": [0.8, 0.5]}])
    assert ut.convert("RGB").getpixel((400, 225)) != GRA
    x0, y0, x1, y1 = _andrat(bild, ut)
    # Pilen går från x 160 till 640 på höjden 225. Strecket, spetsen och den
    # mjuka skuggan får breda ut sig några tiotal pixlar, inte mer.
    assert 120 < x0 < 160 and 640 < x1 < 680, (x0, x1)
    assert 180 < y0 < 225 < y1 < 270, (y0, y1)
    # Originalet rörs inte: kopian är den som ritas på.
    assert bild.getpixel((400, 225)) == GRA


def test_tomt_eller_trasigt_lager_lamnar_bilden_orord():
    from app import bildlager_rita as br
    bild = _gra()
    for lager in (None, [], "pil", [{"typ": "pilen", "fran": [0, 0], "till": [1, 1]}],
                  [{"typ": "pil", "fran": [0, 0]}], [7, None],
                  [{"typ": "ring", "mitt": [0.5, 0.5], "r": True}]):
        assert br.rita(bild, lager) is bild, lager


def test_vinkelbagen_ligger_mellan_stralarna():
    """Hörnet i (200, 400) på en 800 × 450-bild, strålarna åt höger och
    snett uppåt höger (45°). Bågen med radien 0,1 · 800 = 80 px ska gå
    genom bisektrisen och inte på andra sidan hörnet."""
    import math
    from app import bildlager_rita as br
    bild = _gra()
    ut = br.rita(bild, [{"typ": "vinkel", "mitt": [0.25, 400 / 450],
                         "fran": [0.75, 400 / 450], "till": [0.5, 150 / 450],
                         "r": 0.1}]).convert("RGB")
    v = math.radians(22.5)
    pa_bagen = (round(200 + 80 * math.cos(v)), round(400 - 80 * math.sin(v)))
    assert ut.getpixel(pa_bagen) != GRA
    x0, y0, x1, y1 = _andrat(bild, ut)
    assert x0 > 180, "bågen gick åt vänster om hörnet, den stora vinkeln"
    assert y1 < 420


def test_texten_ritas_och_matematiken_blir_tecken():
    from app import bildlager_rita as br
    assert br.klartext("$\\tfrac{1}{4}$ m") == "1/4 m"
    assert br.klartext("$32^\\circ$") == "32°"
    assert br.klartext("$0{,}30$ m") == "0,30 m"
    assert br.klartext("vinkeln $v$") == "vinkeln v"
    bild = _gra()
    ut = br.rita(bild, [{"typ": "etikett", "plats": [0.5, 0.5], "text": "höga kanten"}])
    x0, y0, x1, y1 = _andrat(bild, ut)
    assert x0 < 400 < x1 and y0 < 225 < y1


def test_alla_bladets_typer_ritas():
    from app import bildlager_rita as br
    bild = _gra()
    ut = br.rita(bild, TUNNEL + [{"typ": "vinkel", "mitt": [0.3, 0.7],
                                   "fran": [0.6, 0.7], "till": [0.5, 0.5],
                                   "text": "$v$"}])
    assert _andrat(bild, ut) is not None


def test_vinkeln_ar_en_giltig_typ():
    vinkel = {"typ": "vinkel", "mitt": [0.3, 0.7], "fran": [0.6, 0.7],
              "till": [0.5, 0.5], "text": "$v$"}
    assert bl.validera([vinkel]) == []
    assert bl.validera([dict(vinkel, r=0.1)]) == []
    assert any("r ska vara" in f for f in bl.validera([dict(vinkel, r=0.9)]))
    assert any("hörnet" in f for f in bl.validera([dict(vinkel, fran=[0.3, 0.705])]))
    assert any("saknar mitt" in f for f in bl.validera(
        [{k: v for k, v in vinkel.items() if k != "mitt"}]))


def test_lagerfilerna_ersatts_och_stadas(tmp_path):
    """tryck.rita_bildlager skriver kopian med provets id i namnet, byter den
    mot originalet i bildindexet och tar bort förra godkännandets kopior.
    Omtrycket (lagerfiler) hittar bara provets egna."""
    from app import tryck
    _gra().save(tmp_path / "egen-163-06.png")
    _gra().save(tmp_path / "plat-a-19-hage.jpg")
    (tmp_path / "lager-163-04.png").write_bytes(b"gammal")
    (tmp_path / "lager-99-06.png").write_bytes(b"annat prov")
    pil = [{"typ": "pil", "fran": [0.1, 0.5], "till": [0.9, 0.5]}]
    karta = tryck.rita_bildlager(
        {6: "egen-163-06.png", 7: "plat-a-19-hage.jpg", 8: "egen-163-08.png"},
        tryck.bildlager({"uppg6": pil, "uppg7": pil, "uppg8": pil, "rubrik": pil}),
        tmp_path, 163)
    # Plåten är en JPEG och kopian också. Uppgift 8:s fil saknas på disk och
    # trycks som förut i stället för att fälla godkännandet.
    assert karta == {6: "lager-163-06.png", 7: "lager-163-07.jpg",
                     8: "egen-163-08.png"}
    assert not (tmp_path / "lager-163-04.png").exists()
    assert (tmp_path / "lager-99-06.png").read_bytes() == b"annat prov"
    assert tryck.lagerfiler(tmp_path, 163) == {6: "lager-163-06.png",
                                                7: "lager-163-07.jpg"}
