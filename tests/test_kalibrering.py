"""Svårighetskalibreringen (Etapp 4): vad eleverna säger om nivåetiketten.

Matrisen nedan är SYNTETISK och byggd så att varje flagga har exakt en orsak.
Det är med flit: ett riktigt prov har alla effekterna blandade, och då går det
inte att säga vilket mått som tände. Här ska ett rött test peka på en rad kod.
"""
from __future__ import annotations

import json
from pathlib import Path

from app import db, kalibrering

# Tolv elever, fyra uppgifter. Raderna är byggda mot etiketten:
#
# * 1 (E, 2 p): nästan alla tar den. Ska INTE flaggas.
# * 2 (C, 3 p): mitten, och den skiljer starka från svaga. Ska INTE flaggas.
# * 3 (A, 2 p): men elva av tolv tar full pott. FÖR LÄTT för sin etikett.
# * 4 (E, 2 p): alla tar full pott. Ligger rätt för sin etikett men SKILJER
#   ingen elev från någon annan, och det är den andra sortens flagga.
ELEVER = 12
MATRIS = {
    #        u1      u2      u3      u4
    1:  {"1": 2, "2": 3, "3": 2, "4": 2},
    2:  {"1": 2, "2": 3, "3": 2, "4": 2},
    3:  {"1": 2, "2": 3, "3": 2, "4": 2},
    4:  {"1": 2, "2": 2, "3": 2, "4": 2},
    5:  {"1": 2, "2": 2, "3": 2, "4": 2},
    6:  {"1": 2, "2": 2, "3": 2, "4": 2},
    7:  {"1": 2, "2": 1, "3": 2, "4": 2},
    8:  {"1": 2, "2": 1, "3": 2, "4": 2},
    9:  {"1": 1, "2": 1, "3": 2, "4": 2},
    10: {"1": 1, "2": 0, "3": 2, "4": 2},
    11: {"1": 1, "2": 0, "3": 2, "4": 2},
    12: {"1": 0, "2": 0, "3": 0, "4": 2},
}
RADER = [
    {"nyckel": "1", "kod": "1", "text": "Lätt ingång", "p": 2,
     "peca": [2, 0, 0], "formaga": "P", "ci": []},
    {"nyckel": "2", "kod": "2", "text": "Mitten", "p": 3,
     "peca": [1, 2, 0], "formaga": "PL", "ci": []},
    {"nyckel": "3", "kod": "3", "text": "Påstådd A-uppgift", "p": 2,
     "peca": [0, 0, 2], "formaga": "R", "ci": []},
    {"nyckel": "4", "kod": "4", "text": "Full pott till alla", "p": 2,
     "peca": [2, 0, 0], "formaga": "B", "ci": []},
]


def _tripel(varde: int, peca: list[int]) -> list:
    """Elevens poäng utlagd i den nivå raden bär, samma form som
    elevresultat-tabellen (varde_e, varde_c, varde_a)."""
    ut = [None, None, None]
    for i, tak in enumerate(peca):
        if tak:
            ut[i] = min(varde, tak)
            varde -= ut[i]
    return ut


def _resultat() -> dict:
    peca = {r["nyckel"]: r["peca"] for r in RADER}
    return {elev: {nyckel: _tripel(v, peca[nyckel])
                   for nyckel, v in rad.items()}
            for elev, rad in MATRIS.items()}


# ── Måtten ────────────────────────────────────────────────────────────────

def test_nivan_ar_den_hogsta_som_ger_poang():
    assert kalibrering.niva_ur_peca([2, 0, 0]) == "E"
    assert kalibrering.niva_ur_peca([1, 2, 0]) == "C"
    assert kalibrering.niva_ur_peca([0, 1, 1]) == "A"
    assert kalibrering.niva_ur_peca([0, 0, 0]) is None


def test_p_vardet_ar_andelen_av_maxpoangen():
    matten = {m["nyckel"]: m for m in
              kalibrering.matt(RADER, _resultat())}
    # Uppgift 1: 2·8 + 1·3 + 0 = 19 av 24.
    assert matten["1"]["p"] == round(19 / 24, 4)
    # Uppgift 4: alla tar full pott.
    assert matten["4"]["p"] == 1.0
    assert matten["4"]["elever"] == ELEVER


def test_diskrimineringen_ar_mot_restpoangen():
    """Restpoängen och inte totalen: en uppgift som ingår i sin egen
    jämförelse korrelerar med sig själv."""
    matten = {m["nyckel"]: m for m in kalibrering.matt(RADER, _resultat())}
    assert matten["2"]["diskriminering"] > 0.5      # skiljer starka från svaga
    # Alla tog samma poäng på uppgift 4. Den skiljer BEVISLIGEN ingen, och det
    # är en nolla och inte ett tomt fält.
    assert matten["4"]["diskriminering"] == 0.0


def test_konstant_serie_ar_ingen_korrelation():
    assert kalibrering.korrelation([1, 1, 1], [1, 2, 3]) is None
    assert kalibrering.korrelation([1, 2, 3], [2, 4, 6]) == 1.0


def test_for_fa_elever_ger_inget_matt():
    litet = {1: {"1": [2, None, None]}, 2: {"1": [1, None, None]}}
    matten = kalibrering.matt(RADER, litet)
    assert all(m["p"] is None for m in matten)


def test_orattad_rad_ar_inte_noll_poang():
    """Skillnaden mellan «noll poäng» och «inte rättad» är skillnaden mellan en
    svår uppgift och en uppgift läraren hann till hälften."""
    resultat = _resultat()
    for elev in (10, 11, 12):
        resultat[elev]["1"] = [None, None, None]
    matten = {m["nyckel"]: m for m in kalibrering.matt(RADER, resultat)}
    assert matten["1"]["elever"] == 9
    assert matten["1"]["p"] == round(17 / 18, 4)


# ── Flaggorna ─────────────────────────────────────────────────────────────

def test_en_a_uppgift_som_nastan_alla_klarar_flaggas():
    flaggor = kalibrering.flaggor(kalibrering.matt(RADER, _resultat()))
    for_latt = [f for f in flaggor if f["flagga"] == "for_latt"]
    assert [f["nyckel"] for f in for_latt] == ["3"]
    assert "A-uppgift" in for_latt[0]["varfor"]


def test_en_uppgift_som_inte_skiljer_flaggas():
    flaggor = kalibrering.flaggor(kalibrering.matt(RADER, _resultat()))
    trubbiga = [f for f in flaggor if f["flagga"] == "skiljer_inte"]
    assert [f["nyckel"] for f in trubbiga] == ["4"]


def test_en_uppgift_som_ligger_ratt_flaggas_inte():
    flaggor = kalibrering.flaggor(kalibrering.matt(RADER, _resultat()))
    assert "2" not in {f["nyckel"] for f in flaggor}


def test_en_e_uppgift_som_ingen_klarar_flaggas():
    """Bara p-flaggan tänder här, och det är rätt: pappret har EN uppgift, så
    det finns ingen restpoäng att korrelera mot och alltså inget att säga om
    hur den skiljer elever åt."""
    resultat = {e: {"1": [0, None, None]} for e in range(1, 13)}
    flaggor = kalibrering.flaggor(kalibrering.matt(RADER[:1], resultat))
    assert [f["flagga"] for f in flaggor] == ["for_svar"]
    assert "börjar vid 55 %" in flaggor[0]["varfor"]


def test_sammandraget_per_niva():
    per = kalibrering.per_niva(kalibrering.matt(RADER, _resultat()))
    assert per["E"]["uppgifter"] == 2 and per["C"]["uppgifter"] == 1
    assert per["A"]["uppgifter"] == 1
    assert per["A"]["p_medel"] > per["C"]["p_medel"]   # etiketten stämmer inte
    assert per["A"]["band"] == list(kalibrering.BAND["A"])


# ── Hela vägen: databas → mått ────────────────────────────────────────────

def _skriv_papper(conn) -> int:
    dok = db.create_dokument(conn, dokument={
        "typ": "Prov", "kurs": "Matematik 2c", "klass": "NA25",
        "uppgifter": [{"t": r["text"], "p": r["p"]} for r in RADER]})
    did = dok["id"]
    db.save_rattning(conn, did, elever=ELEVER, andel=0.7, rader=RADER,
                     klass="NA25", kurs="Matematik 2c", datum="2026-05-12")
    gid = db.get_or_create_group(conn, "NA25")
    elever = db.save_elever(conn, gid,
                            [f"Elev {i:02d}" for i in range(1, ELEVER + 1)])
    nummer_till_id = {i: e["id"] for i, e in enumerate(elever, 1)}
    db.save_elevresultat(conn, did, {nummer_till_id[e]: rad
                                     for e, rad in _resultat().items()})
    return did


def test_hela_passet_ur_databasen(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    try:
        did = _skriv_papper(conn)
        ut = kalibrering.kalibrera(conn, kurs="Matematik 2c")
        assert [p["dokument_id"] for p in ut["papper"]] == [did]
        assert ut["uppgifter"] == 4 and ut["omatta"] == 0
        assert {f["flagga"] for f in ut["flaggor"]} == {"for_latt",
                                                        "skiljer_inte"}
        assert ut["grans"]["min_elever"] == kalibrering.MIN_ELEVER
    finally:
        conn.close()


def test_en_tom_databas_ger_ett_tomt_pass(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    try:
        ut = kalibrering.kalibrera(conn)
        assert ut["papper"] == [] and ut["flaggor"] == []
        assert ut["uppgifter"] == 0 and ut["omatta"] == 0
        # Banden följer med även när ingenting mättes: läsaren ska kunna se
        # vad som INTE tände, inte bara att ingenting gjorde det.
        assert ut["per_niva"]["A"]["band"] == list(kalibrering.BAND["A"])
    finally:
        conn.close()


def test_rutten_svarar_med_samma_struktur(client):
    r = client.get("/api/exams/kalibrering")
    assert r.status_code == 200
    ut = r.json()
    assert ut["papper"] == [] and ut["flaggor"] == []
    assert set(ut["grans"]["band"]) == {"E", "C", "A"}


def test_rutten_hittar_det_ratta_pappret(client):
    conn = db.connect(client.base_dir / "transkribera.db")
    try:
        did = _skriv_papper(conn)
    finally:
        conn.close()
    ut = client.get("/api/exams/kalibrering",
                    params={"dokument_id": did}).json()
    assert [p["dokument_id"] for p in ut["papper"]] == [did]
    assert ut["papper"][0]["klass"] == "NA25"
    assert {f["nyckel"] for f in ut["flaggor"]} == {"3", "4"}


def test_cli_skriver_json(tmp_path, capsys):
    fil = tmp_path / "t.db"
    conn = db.connect(fil)
    try:
        _skriv_papper(conn)
    finally:
        conn.close()
    assert kalibrering.main(["--db", str(fil), "--kurs", "Matematik 2c"]) == 0
    ut = capsys.readouterr().out
    assert '"for_latt"' in ut and '"papper"' in ut


def test_cli_utan_databas_sager_det(tmp_path, capsys):
    assert kalibrering.main(["--db", str(tmp_path / "finns_inte.db")]) == 1
    assert "ingen databas" in capsys.readouterr().out


def test_cli_skriver_utf8_i_en_rorledning(tmp_path):
    """Skarpt subprocess-anrop, inte capsys. På Windows är stdout annars den
    lokala kodsidan (cp1252), och flaggtexterna är svenska. Den första körningen
    gav «invalid start byte» när svaret lästes på andra sidan röret. capsys ser
    inte det felet: den fångar strängar, inte byte."""
    import subprocess
    import sys

    fil = tmp_path / "t.db"
    conn = db.connect(fil)
    try:
        _skriv_papper(conn)
    finally:
        conn.close()
    ut = subprocess.run(
        [sys.executable, "-m", "app.kalibrering", "--db", str(fil)],
        capture_output=True, cwd=str(Path(kalibrering.__file__).parent.parent))
    assert ut.returncode == 0, ut.stderr[-500:]
    data = json.loads(ut.stdout.decode("utf-8"))       # byte, inte text
    # «ä» är ETT byte i cp1252 och TVÅ i UTF-8, så raden ovan faller redan om
    # kodningen är fel. Påståendet här är att tecknet faktiskt fanns med.
    assert any("uppgiften mäter" in f["varfor"].lower()
               for f in data["flaggor"]), data["flaggor"]
