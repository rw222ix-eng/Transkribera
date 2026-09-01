"""Användarspåret (app/spar.py, migration v28, middlewaren i server.py).

Spåret är underlag för att förbättra appen efter hur den faktiskt används —
och det får ALDRIG kosta läraren något: en trasig loggning ska svälja sig
själv, inte fälla varvet den satt fast i.
"""
from __future__ import annotations

import json

from app import db, spar
from tools import spar as spar_rapport


def test_normalisera_byter_idn_men_inte_ord():
    assert spar.normalisera("/api/exams/17/refine") == "/api/exams/{id}/refine"
    # planeringens pid är 12 hex-tecken (uuid4().hex[:12])
    assert (spar.normalisera("/api/planning/0a1b2c3d4e5f/refine")
            == "/api/planning/{id}/refine")
    # ord som råkar innehålla siffror är inte id:n
    assert spar.normalisera("/api/bocker") == "/api/bocker"


def test_logga_skriver_rad_och_rapporten_laser_den(tmp_path):
    db_file = tmp_path / "t.db"
    spar.logga(db_file, "onske", doktyp="prov", dok_id=7,
               detalj={"message": "byt uppgift 2", "mal": "Uppgift 2"})
    spar.logga(db_file, "utfall", doktyp="prov", dok_id=7,
               detalj={"andrade": ["uppgift-2"], "fel": 0})
    conn = db.connect(db_file)
    try:
        rader = conn.execute("SELECT art, doktyp, dok_id, detalj FROM spar "
                             "ORDER BY id").fetchall()
    finally:
        conn.close()
    assert [r[0] for r in rader] == ["onske", "utfall"]
    assert json.loads(rader[0][3])["message"] == "byt uppgift 2"
    text = spar_rapport.rapport(db_file, dagar=1)
    assert "byt uppgift 2" in text
    assert "[Uppgift 2]" in text  # målet läraren pekade på står med


def test_logga_svaljer_sina_fel(tmp_path):
    # katalog som databas → sqlite kastar; logga får inte göra det
    trasig = tmp_path / "mapp"
    trasig.mkdir()
    spar.logga(trasig, "api", vag="POST /api/x")  # ska inte kasta


def test_middleware_loggar_mutationer_men_inte_getar(client):
    client.get("/api/dokument")
    client.post("/api/klassprofil")  # metod finns inte → 405, men den loggas:
    # även ett misslyckat anrop är en handling läraren gjorde
    client.put("/api/klassprofil", json={})
    conn = db.connect(client.base_dir / "transkribera.db")
    try:
        rader = [r[0] for r in conn.execute(
            "SELECT vag FROM spar WHERE art='api' ORDER BY id").fetchall()]
    finally:
        conn.close()
    assert "PUT /api/klassprofil" in rader
    assert not any(r.startswith("GET ") for r in rader)
