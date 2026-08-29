"""Jobben som överlever fliken (Etapp 2).

Tre påståenden prövas här, och de är de tre som semantikbytet vilar på:

1. **En stängd flik dödar inte längre jobbet.** Provet, tavlan, arbetsbladet
   och anteckningarna tar minuter och är betalda i det ögonblick de startar.
   Förr kastades hela körningen när strömmen dog (`sse.sse_response`, som står
   kvar oförändrad för transkriberingen och boken) — nu kör tråden klart och
   skriver sitt papper.
2. **Lärarens Avbryt gör det strömmen slutade göra.** Flaggan sätts av
   POST /api/jobb/{id}/avbryt och tråden ser den vid nästa `emit`.
3. **Historiken går att spela upp igen.** Varje event ligger i `jobb_events`
   med sitt `seq`, och GET /api/jobb/{id}/strom?fran=N ger resten.

Testerna kör strömmen direkt där de kan (samma metod som tests/test_sse.py:
nedkopplingen syns bara på ASGI:s receive-kanal, och den kan ingen testklient
härma) och över HTTP där rutten är det som prövas.
"""
from __future__ import annotations

import json
import threading
import time

import anyio
import pytest

from app import db as appdb
from app.web import sse


class Forfragan:
    """Starlettes Request, så långt strömmen bryr sig om den."""

    def __init__(self) -> None:
        self.nere = False

    async def is_disconnected(self) -> bool:
        return self.nere


def _las(resp, *, efter_forsta=None, tak=400) -> list[dict]:
    async def kor():
        ut = []
        async for bit in resp.body_iterator:
            ut.append(json.loads(bit[len("data: "):]))
            if len(ut) == 1 and efter_forsta is not None:
                efter_forsta()
            if len(ut) >= tak:
                break
        return ut
    return anyio.run(kor)


def _vanta(villkor, sekunder: float = 5.0) -> bool:
    slut = time.monotonic() + sekunder
    while time.monotonic() < slut:
        if villkor():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def db_file(tmp_path):
    return tmp_path / "transkribera.db"


def _jobben(db_file) -> list[dict]:
    conn = appdb.connect(db_file)
    try:
        return appdb.aktiva_jobb(conn)
    finally:
        conn.close()


# ── 1. Migrationen ──────────────────────────────────────────────────────────

def test_migrationen_lagger_de_tva_tabellerna(db_file):
    conn = appdb.connect(db_file)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == \
            appdb.SCHEMA_VERSION >= 27
        namn = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert {"jobb", "jobb_events"} <= namn
    finally:
        conn.close()


def test_anslutningen_bar_de_tre_pragman(db_file):
    """Sätts de inte om per anslutning gäller de inte: alla tre är
    per-connection i sqlite, precis som foreign_keys."""
    conn = appdb.connect(db_file)
    try:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1   # NORMAL
        assert conn.execute("PRAGMA temp_store").fetchone()[0] == 2    # MEMORY
        # Och de gamla står kvar.
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_skrivsessionen_committar_och_rullar_tillbaka(db_file):
    conn = appdb.connect(db_file)
    try:
        with appdb.skriv(conn):
            conn.execute("INSERT INTO courses(namn) VALUES ('Kvar')")
        with pytest.raises(RuntimeError):
            with appdb.skriv(conn):
                conn.execute("INSERT INTO courses(namn) VALUES ('Borta')")
                raise RuntimeError("något small")
        namn = {r["namn"] for r in
                conn.execute("SELECT namn FROM courses").fetchall()}
        assert "Kvar" in namn and "Borta" not in namn
    finally:
        conn.close()


def test_skrivsessionen_talar_en_oppen_transaktion(db_file):
    """`_get_or_create` committar bara när den skapade något — en uppslagning
    som inte gjorde det lämnar sqlite3:s implicita transaktion öppen. Ett rakt
    BEGIN IMMEDIATE hade då fällt hela anropet."""
    conn = appdb.connect(db_file)
    try:
        conn.execute("INSERT INTO courses(namn) VALUES ('Redan')")
        assert conn.in_transaction
        with appdb.skriv(conn):
            conn.execute("INSERT INTO groups(namn) VALUES ('NA25')")
        assert not conn.in_transaction          # committad, inte kvarlämnad
    finally:
        conn.close()


# ── 2. Jobbet lever vidare ──────────────────────────────────────────────────

def test_id_ar_forsta_eventet_och_allt_hamnar_i_historiken(db_file):
    def job(emit):
        emit({"type": "log", "msg": "Skriver …"})
        return {"id": 7}

    ev = _las(sse.jobb_response(job, Forfragan(), typ="prov", db_file=db_file))
    assert ev[0]["type"] == "jobb" and isinstance(ev[0]["id"], int)
    assert [e["type"] for e in ev] == ["jobb", "log", "done"]
    # Varje event bär sitt nummer, och numren är historikens ordning.
    assert [e["seq"] for e in ev[1:]] == [1, 2]

    jobb_id = ev[0]["id"]
    conn = appdb.connect(db_file)
    try:
        assert _vanta(lambda: appdb.hamta_jobb(conn, jobb_id)["status"] == "done")
        rad = appdb.hamta_jobb(conn, jobb_id)
        assert rad["typ"] == "prov"
        # Resultatets id sparas så att en återupptagen klient hittar pappret.
        assert rad["resultat_ref"] == "7"
        historik = appdb.jobb_events(conn, jobb_id)
        assert [e["type"] for e in historik] == ["log", "done"]
    finally:
        conn.close()


def test_stangd_flik_dodar_inte_jobbet(db_file):
    """SEMANTIKBYTET. Motsatsen till test_sse.test_klienten_som_gar_avbryter
    _jobbet, som fortfarande gäller för de jobb som HÖR ihop med sin flik."""
    forfragan = Forfragan()
    varv, slutforde = [], []
    startat = threading.Event()

    def job(emit):
        emit({"type": "log", "msg": "Skriver …"})
        startat.set()
        for i in range(40):
            varv.append(i)
            emit({"type": "token", "text": "x"})
            time.sleep(0.001)
        slutforde.append(True)
        return {"id": 1}

    # Fliken stängs redan på handskakningen — värsta fallet: läraren hann inte
    # se en enda rad. Jobbet ska ändå gå hela vägen.
    ev = _las(sse.jobb_response(job, forfragan, typ="prov", db_file=db_file),
              efter_forsta=lambda: forfragan.__setattr__("nere", True))
    jobb_id = ev[0]["id"]

    assert startat.wait(5), "jobbet hann aldrig börja — testet mäter fel sak"
    assert _vanta(lambda: bool(slutforde)), "jobbet dog med fliken"
    assert len(varv) == 40
    conn = appdb.connect(db_file)
    try:
        assert _vanta(lambda: appdb.hamta_jobb(conn, jobb_id)["status"] == "done")
        # …och historiken är komplett trots att ingen läste den live.
        assert len(appdb.jobb_events(conn, jobb_id)) == 42   # log + 40 + done
    finally:
        conn.close()


def test_avbryt_stoppar_vid_nasta_livstecken(db_file):
    """Lärarens knapp gör det frånkopplingen slutade göra."""
    varv, slutforde = [], []
    startat = threading.Event()
    fangat = {"id": None}

    def job(emit):
        emit({"type": "log", "msg": "Skriver …"})
        startat.set()
        for i in range(2000):
            varv.append(i)
            emit({"type": "token", "text": "x"})
            time.sleep(0.002)
        slutforde.append(True)                 # ska ALDRIG hända
        return {"id": 1}

    # Läs några event, släpp strömmen och tryck sedan Avbryt — precis som
    # läraren gör det från en annan flik: knappen känner bara jobbets id.
    ev = _las(sse.jobb_response(job, Forfragan(), typ="tavla", db_file=db_file),
              tak=5)
    fangat["id"] = ev[0]["id"]
    assert startat.wait(5)
    assert sse.begar_avbrott(fangat["id"]) is True

    conn = appdb.connect(db_file)
    try:
        assert _vanta(lambda: appdb.hamta_jobb(
            conn, fangat["id"])["status"] == "avbrutet")
    finally:
        conn.close()
    assert not slutforde, "jobbet körde klart trots Avbryt"
    assert len(varv) < 2000


def test_felet_blir_status_och_besked(db_file):
    def job(emit):
        raise OSError(28, "No space left on device")

    ev = _las(sse.jobb_response(job, Forfragan(), typ="prov", db_file=db_file))
    assert ev[-1]["type"] == "error" and "utrymme" in ev[-1]["message"]
    conn = appdb.connect(db_file)
    try:
        rad = appdb.hamta_jobb(conn, ev[0]["id"])
        assert _vanta(lambda: appdb.hamta_jobb(
            conn, ev[0]["id"])["status"] == "error")
        assert "utrymme" in appdb.hamta_jobb(conn, ev[0]["id"])["fel"]
        assert rad is not None
    finally:
        conn.close()


# ── 3. Uppspelningen ────────────────────────────────────────────────────────

def test_uppspelning_fran_seq(db_file):
    conn = appdb.connect(db_file)
    try:
        jobb_id = appdb.skapa_jobb(conn, typ="prov")
        for n, msg in enumerate(["ett", "två", "tre", "fyra"], 1):
            appdb.lagg_jobb_event(conn, jobb_id, n, {"type": "log", "msg": msg})
        appdb.satt_jobb_status(conn, jobb_id, "done")
    finally:
        conn.close()

    ev = _las(sse.uppspelning(jobb_id, Forfragan(), db_file=db_file, fran=3))
    assert [e["msg"] for e in ev] == ["tre", "fyra"]
    # Och från noll: hela historiken.
    assert len(_las(sse.uppspelning(jobb_id, Forfragan(), db_file=db_file))) == 4


def test_stadningen_gor_spoken_till_avbrutna(db_file):
    """Trådarna dog med processen. Utan städningen hade en ny flik visat dem
    som pågående för alltid."""
    conn = appdb.connect(db_file)
    try:
        jobb_id = appdb.skapa_jobb(conn, typ="tavla")
        appdb.satt_jobb_status(conn, jobb_id, "running")
        assert appdb.stada_jobb(conn) == 1
        rad = appdb.hamta_jobb(conn, jobb_id)
        assert rad["status"] == "avbrutet" and "startade om" in rad["fel"]
    finally:
        conn.close()


def test_ett_avslutat_jobb_flyttas_inte_igen(db_file):
    """En tråd som hinner skriva sitt `done` efter Avbryt får inte skriva över
    avbrottet — då hade listan sagt att pappret blev skrivet."""
    conn = appdb.connect(db_file)
    try:
        jobb_id = appdb.skapa_jobb(conn, typ="prov")
        appdb.satt_jobb_status(conn, jobb_id, "avbrutet")
        appdb.satt_jobb_status(conn, jobb_id, "done", resultat_ref="9")
        assert appdb.hamta_jobb(conn, jobb_id)["status"] == "avbrutet"
    finally:
        conn.close()


# ── 4. Rutterna ─────────────────────────────────────────────────────────────

def test_aktiva_listar_kor_och_nyligen_klara(client):
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        kor = appdb.skapa_jobb(conn, typ="prov", dokument_id="12")
        appdb.satt_jobb_status(conn, kor, "running")
        appdb.lagg_jobb_event(conn, kor, 1, {"type": "log", "msg": "Skriver …"})
        klart = appdb.skapa_jobb(conn, typ="tavla")
        appdb.satt_jobb_status(conn, klart, "done")
    finally:
        conn.close()

    svar = client.get("/api/jobb/aktiva").json()
    assert [j["id"] for j in svar["kor"]] == [kor]
    assert {j["id"] for j in svar["jobb"]} == {kor, klart}
    # Raden går att rita utan att spela upp historiken.
    assert svar["kor"][0]["senaste"] == "Skriver …"
    assert svar["kor"][0]["dokument_id"] == "12"
    # …och den går att smalna av till ETT dokument.
    smalt = client.get("/api/jobb/aktiva?dokument_id=12").json()
    assert [j["id"] for j in smalt["jobb"]] == [kor]


def test_avbryt_rutten(client):
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        jobb_id = appdb.skapa_jobb(conn, typ="prov")
        appdb.satt_jobb_status(conn, jobb_id, "running")
    finally:
        conn.close()

    r = client.post(f"/api/jobb/{jobb_id}/avbryt")
    assert r.status_code == 200 and r.json() == {"ok": True, "status": "avbrutet"}
    # En andra tryckning är ingen olycka — beskedet är vad som redan hänt.
    assert client.post(f"/api/jobb/{jobb_id}/avbryt").json() == \
        {"ok": False, "status": "avbrutet"}
    assert client.post("/api/jobb/999999/avbryt").status_code == 404


def test_stromrutten_spelar_upp_over_http(client):
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        jobb_id = appdb.skapa_jobb(conn, typ="anteckningar")
        appdb.lagg_jobb_event(conn, jobb_id, 1, {"type": "log", "msg": "ett"})
        appdb.lagg_jobb_event(conn, jobb_id, 2,
                              {"type": "progress", "steg": 2, "av": 3,
                               "text": "Skriver anteckningarna"})
        appdb.lagg_jobb_event(conn, jobb_id, 3, {"type": "done", "result": {"id": 4}})
        appdb.satt_jobb_status(conn, jobb_id, "done", resultat_ref="4")
    finally:
        conn.close()

    r = client.get(f"/api/jobb/{jobb_id}/strom?fran=2")
    assert r.status_code == 200
    ev = [json.loads(rad[len("data:"):])
          for rad in r.text.splitlines() if rad.startswith("data:")]
    assert [e["type"] for e in ev] == ["progress", "done"]
    assert ev[0]["steg"] == 2 and ev[0]["av"] == 3
    assert client.get("/api/jobb/999999/strom").status_code == 404


def test_ett_jobb_som_uppslag(client):
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        jobb_id = appdb.skapa_jobb(conn, typ="prov", dokument_id="3")
    finally:
        conn.close()
    assert client.get(f"/api/jobb/{jobb_id}").json()["typ"] == "prov"
    assert client.get("/api/jobb/999999").status_code == 404
