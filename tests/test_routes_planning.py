"""Planering-routern (Fas 0/1): PNG-export, generering, reparation,
iteration och godkännande — allt stubbat och säkert under base_dir."""
import base64
import copy
import json

import pytest

from app import lesson_board


def _events(resp) -> list[dict]:
    """Plocka ut SSE-events ur ett StreamingResponse-svar."""
    return [json.loads(line[len("data:"):])
            for line in resp.text.splitlines() if line.startswith("data:")]


def _done(resp) -> dict:
    evs = [e for e in _events(resp) if e["type"] == "done"]
    assert evs, _events(resp)
    return evs[0]["result"]


def _valid_board() -> dict:
    return copy.deepcopy(lesson_board.FEW_SHOTS[0][1])

# Minsta giltiga PNG (1×1 px) — räcker för att testa magisk signatur + skrivning.
_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
_DATA_URL = "data:image/png;base64," + base64.b64encode(_PNG_1PX).decode()


def test_export_writes_png_under_planering(client):
    r = client.post("/api/planning/export",
                    json={"title": "Pythagoras sats", "png": _DATA_URL})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    from pathlib import Path
    saved = Path(data["path"])
    assert saved.exists()
    assert saved.read_bytes() == _PNG_1PX
    # Hamnar i Transkriberingar/<lektion>/planering/ under base_dir.
    rel = saved.relative_to(client.base_dir)
    assert rel.parts[0] == "Transkriberingar"
    assert rel.parts[1] == "Pythagoras sats"
    assert rel.parts[2] == "planering"
    assert saved.suffix == ".png"


def test_export_sanitizes_traversal_title(client):
    r = client.post("/api/planning/export",
                    json={"title": "../../..\\utanför", "png": _DATA_URL})
    assert r.status_code == 200
    from pathlib import Path
    saved = Path(r.json()["path"]).resolve()
    base = client.base_dir.resolve()
    # Sökvägstecknen strippas — filen ligger kvar under base_dir och
    # kvarvarande punkter kan inte klättra uppåt.
    assert base in saved.parents
    assert "Transkriberingar" in saved.parts


def test_export_empty_title_falls_back(client):
    r = client.post("/api/planning/export", json={"title": "///", "png": _DATA_URL})
    assert r.status_code == 200
    from pathlib import Path
    assert "Planering" in Path(r.json()["path"]).parts


def test_export_rejects_non_png(client):
    jpg = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0jpg").decode()
    r = client.post("/api/planning/export", json={"title": "x", "png": jpg})
    assert r.status_code == 400

    fake = "data:image/png;base64," + base64.b64encode(b"inte en png").decode()
    r = client.post("/api/planning/export", json={"title": "x", "png": fake})
    assert r.status_code == 400

    r = client.post("/api/planning/export", json={"title": "x", "png": ""})
    assert r.status_code == 400


def test_export_rejects_broken_base64(client):
    r = client.post("/api/planning/export",
                    json={"title": "x", "png": "data:image/png;base64,%%%inte-base64"})
    assert r.status_code == 400


def test_export_rejects_oversized(client):
    huge = "data:image/png;base64," + "A" * (41 * 1024 * 1024)
    r = client.post("/api/planning/export", json={"title": "x", "png": huge})
    assert r.status_code == 413


# ------------------------------------------------------- Fas 1: generate --

def _stub_generate(monkeypatch, result):
    calls = []

    def fake(course, group, moment, *, model, memory="", underlag="",
             utfall="", bok="", llm=None,
             max_rounds=lesson_board.MAX_ROUNDS, log_cb=None, token_cb=None,
             **_kw):
        calls.append({"course": course, "group": group, "moment": moment,
                      "model": model, "memory": memory, "underlag": underlag,
                      "utfall": utfall})
        if log_cb:
            log_cb("Genererar lektionstavlan …")
        return result
    monkeypatch.setattr(lesson_board, "generate_board", fake)
    return calls


def test_generate_requires_moment(llm_ready):
    r = llm_ready.post("/api/planning/generate", json={"moment": "  "})
    assert r.status_code == 400


def test_planeringarna_ar_takade(llm_ready, monkeypatch):
    """Soaknatten 2026-08-08: `plannings` fick en post per genererad tavla och
    tappade aldrig någon. Hela tavlans JSON blev kvar för processens livstid —
    0,3 MB per soakvarv, utan platå. Appen startas i augusti och stängs i juni.

    Taket får inte ta den tavla läraren arbetar med; den nyaste ska leva.
    """
    _stub_generate(monkeypatch, {"board": _valid_board(), "errors": [], "rounds": 1})
    ider = []
    for i in range(55):
        r = llm_ready.post("/api/planning/generate", json={"moment": f"moment {i}"})
        ider.append(_done(r)["id"])

    assert llm_ready.post(f"/api/planning/{ider[-1]}/render-report",
                          json={"warnings": []}).status_code == 200
    assert llm_ready.post(f"/api/planning/{ider[0]}/render-report",
                          json={"warnings": []}).status_code == 404
    # Femtio kvar, inte femtiofem — och det är de femtio senaste.
    assert llm_ready.post(f"/api/planning/{ider[-50]}/render-report",
                          json={"warnings": []}).status_code == 200
    assert llm_ready.post(f"/api/planning/{ider[-51]}/render-report",
                          json={"warnings": []}).status_code == 404


def test_generate_streams_board_and_stores_planning(llm_ready, monkeypatch):
    board = _valid_board()
    calls = _stub_generate(monkeypatch,
                           {"board": board, "errors": [], "rounds": 1})
    r = llm_ready.post("/api/planning/generate",
                       json={"moment": "Pythagoras sats"})
    assert r.status_code == 200
    result = _done(r)
    assert result["board"]["title"] == "Pythagoras sats"
    assert result["errors"] == [] and result["rounds"] == 1
    assert calls[0]["moment"] == "Pythagoras sats"
    # loggen streamas som SSE-events
    assert any(e["type"] == "log" for e in _events(r))
    # planeringen finns i minnet → approve fungerar
    r2 = llm_ready.post(f"/api/planning/{result['id']}/approve", json={})
    assert r2.status_code == 200


def test_generate_tar_klass_och_kurs_som_namn(llm_ready, monkeypatch):
    """Frontenden känner klass och kurs vid NAMN — schemat är namn hela vägen
    (app/web/ui/kalender.js). Namnen ska räcka: de slås upp, skapas om de
    saknas, och når prompten som klass och kurs."""
    calls = _stub_generate(monkeypatch,
                           {"board": _valid_board(), "errors": [], "rounds": 1})
    r = llm_ready.post("/api/planning/generate",
                       json={"moment": "Derivatans definition",
                             "klass": "NA25", "kurs": "Matematik, nivå 2c"})
    assert r.status_code == 200
    _done(r)
    assert calls[0]["group"] == "NA25"
    assert calls[0]["course"] == "Matematik, nivå 2c"
    assert "NA25" in [g["namn"] for g in llm_ready.get("/api/groups").json()]


def test_id_vinner_over_namn(llm_ready, monkeypatch):
    gid = llm_ready.post("/api/groups", json={"namn": "TE25prk"}).json()["id"]
    calls = _stub_generate(monkeypatch,
                           {"board": _valid_board(), "errors": [], "rounds": 1})
    r = llm_ready.post("/api/planning/generate",
                       json={"moment": "Enhetscirkeln", "group_id": gid,
                             "klass": "struntnamn"})
    _done(r)
    assert calls[0]["group"] == "TE25prk"


def test_generate_utan_klass_och_kurs_gar_anda(llm_ready, monkeypatch):
    """Man ska kunna skriva en tavla utan att ha valt lektion i veckan."""
    calls = _stub_generate(monkeypatch,
                           {"board": _valid_board(), "errors": [], "rounds": 1})
    _done(llm_ready.post("/api/planning/generate", json={"moment": "Integraler"}))
    assert calls[0]["group"] == "klassen" and calls[0]["course"] == "matematik"


def test_generate_409_when_gpu_busy(llm_ready, monkeypatch):
    monkeypatch.setattr(llm_ready.app.state.arbiter, "try_acquire_gpu",
                        lambda: None)
    r = llm_ready.post("/api/planning/generate", json={"moment": "x"})
    assert r.status_code == 409


def test_generate_releases_gpu_on_error(llm_ready, monkeypatch):
    # LLM ej installerad → error-event, men GPU-låset släpps (nästa anrop
    # blockeras inte).
    monkeypatch.setattr(llm_ready.app.state.arbiter, "ensure_llm", lambda: None)
    r = llm_ready.post("/api/planning/generate", json={"moment": "x"})
    assert any(e["type"] == "error" and "inte installerad" in e["message"]
               for e in _events(r))
    monkeypatch.setattr(llm_ready.app.state.arbiter, "ensure_llm",
                        lambda: "http://x")
    _stub_generate(monkeypatch,
                   {"board": _valid_board(), "errors": [], "rounds": 1})
    r2 = llm_ready.post("/api/planning/generate", json={"moment": "x"})
    assert r2.status_code == 200          # inte 409 — låset släpptes


# -------------------------------------------------- Fas 1: render-report --

def _make_planning(llm_ready, monkeypatch, rounds=1) -> str:
    _stub_generate(monkeypatch,
                   {"board": _valid_board(), "errors": [], "rounds": rounds})
    r = llm_ready.post("/api/planning/generate", json={"moment": "x"})
    return _done(r)["id"]


def test_render_report_unknown_id(llm_ready):
    r = llm_ready.post("/api/planning/finns-ej/render-report",
                       json={"warnings": ["[WB] x"]})
    assert r.status_code == 404


def test_render_report_no_warnings_is_noop(llm_ready, monkeypatch):
    pid = _make_planning(llm_ready, monkeypatch)
    r = llm_ready.post(f"/api/planning/{pid}/render-report",
                       json={"warnings": []})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "repaired": False}


def test_render_report_triggers_repair(llm_ready, monkeypatch):
    pid = _make_planning(llm_ready, monkeypatch, rounds=1)
    repaired = _valid_board()
    repaired["title"] = "Reparerad"
    captured = {}

    def fake_repair(board, warnings, *, model, llm=None, rounds_used=1,
                    max_rounds=lesson_board.MAX_ROUNDS, log_cb=None,
                    token_cb=None):
        captured["warnings"] = warnings
        captured["rounds_used"] = rounds_used
        return {"board": repaired, "errors": [], "rounds": rounds_used + 1}
    monkeypatch.setattr(lesson_board, "repair_board", fake_repair)

    r = llm_ready.post(f"/api/planning/{pid}/render-report",
                       json={"warnings": ["[WB] hoger: 1 element-överlapp"]})
    result = _done(r)
    assert result["repaired"] is True
    assert result["board"]["title"] == "Reparerad"
    assert captured["warnings"] == ["[WB] hoger: 1 element-överlapp"]
    assert captured["rounds_used"] == 1


def test_render_report_exhausted_budget_skips_llm(llm_ready, monkeypatch):
    pid = _make_planning(llm_ready, monkeypatch,
                         rounds=lesson_board.MAX_ROUNDS)
    r = llm_ready.post(f"/api/planning/{pid}/render-report",
                       json={"warnings": ["[WB] x"]})
    assert r.status_code == 200
    assert r.json()["exhausted"] is True


# --------------------------------------------------------- Fas 1: refine --

def test_refine_requires_message(llm_ready, monkeypatch):
    pid = _make_planning(llm_ready, monkeypatch)
    r = llm_ready.post(f"/api/planning/{pid}/refine", json={"message": " "})
    assert r.status_code == 400


def test_refine_updates_board(llm_ready, monkeypatch):
    pid = _make_planning(llm_ready, monkeypatch)
    updated = _valid_board()
    updated["title"] = "Uppdaterad"
    captured = {}

    def fake_refine(board, instruction, *, model, mal=None, llm=None,
                    max_rounds=lesson_board.MAX_ROUNDS, log_cb=None,
                    token_cb=None):
        captured["instruction"] = instruction
        captured["mal"] = mal
        return {"board": updated, "errors": [], "rounds": 1}
    monkeypatch.setattr(lesson_board, "refine_board", fake_refine)

    r = llm_ready.post(f"/api/planning/{pid}/refine",
                       json={"message": "byt exempel 2"})
    result = _done(r)
    assert result["board"]["title"] == "Uppdaterad"
    assert captured["instruction"] == "byt exempel 2"
    assert captured["mal"] is None          # inget klick → hela tavlan, som förut

    # Pekade läraren på en ruta i granskningen ska den följa hela vägen ner.
    r2 = llm_ready.post(f"/api/planning/{pid}/refine",
                        json={"message": "gör den kortare",
                              "mal": {"namn": "Formel 3", "innehall": "a^2+b^2=c^2"}})
    _done(r2)
    assert captured["mal"] == {"namn": "Formel 3", "innehall": "a^2+b^2=c^2"}


# ------------------------------------------------------------ klockslaget --

def _tid(board: dict) -> str:
    return board["boards"][0]["sections"][0].get("text", "")


def _planering_med_tid(llm_ready, monkeypatch, tid="09:10") -> str:
    _stub_generate(monkeypatch,
                   {"board": _valid_board(), "errors": [], "rounds": 1})
    r = llm_ready.post("/api/planning/generate",
                       json={"moment": "Randvinkelsatsen", "starttid": tid})
    return _done(r)["id"]


def test_starttiden_hamnar_forst_pa_vanstertavlan(llm_ready, monkeypatch):
    """`starttid` fanns i begäran och i planeringens state men nådde aldrig
    tavlan. Läraren vill ha klockslaget uppe till vänster — det sätts av
    systemet, inte av modellen."""
    _stub_generate(monkeypatch,
                   {"board": _valid_board(), "errors": [], "rounds": 1})
    r = llm_ready.post("/api/planning/generate",
                       json={"moment": "Randvinkelsatsen", "starttid": "09:10"})
    board = _done(r)["board"]
    assert _tid(board) == "09:10"
    assert board["boards"][0]["sections"][1]["kind"] == "heading"


def test_utan_starttid_ingen_tid_pa_tavlan(llm_ready, monkeypatch):
    _stub_generate(monkeypatch,
                   {"board": _valid_board(), "errors": [], "rounds": 1})
    r = llm_ready.post("/api/planning/generate", json={"moment": "x"})
    assert _done(r)["board"]["boards"][0]["sections"][0]["kind"] == "heading"


def test_sluttiden_hamtas_ur_veckoschemat(llm_ready, monkeypatch):
    """Frontenden skickar bara starten (plan.js delar schemats "09:05–10:20" på
    bindestrecket) — men läraren vill ha hela passet på tavlan, och sluttiden
    står på samma schemarad."""
    llm_ready.put("/api/schema", json={"schema": [
        {"dag": 2, "tid": "09:10–10:20", "klass": "NA25",
         "kurs": "Matematik, nivå 2b", "sal": "P807"},
        {"dag": 3, "tid": "09:10–09:55", "klass": "TE24", "kurs": "Ma1c"},
    ]})
    _stub_generate(monkeypatch,
                   {"board": _valid_board(), "errors": [], "rounds": 1})
    r = llm_ready.post("/api/planning/generate",
                       json={"moment": "Lutning", "klass": "NA25",
                             "datum": "2026-09-01", "starttid": "09:10"})
    assert _tid(_done(r)["board"]) == "09:10–10:20"


def test_okant_klockslag_ger_bara_starttiden(llm_ready, monkeypatch):
    """Ingen schemarad matchar → tavlan får starten och inget gissat slut."""
    _stub_generate(monkeypatch,
                   {"board": _valid_board(), "errors": [], "rounds": 1})
    r = llm_ready.post("/api/planning/generate",
                       json={"moment": "Lutning", "starttid": "07:45"})
    assert _tid(_done(r)["board"]) == "07:45"


def test_sluttid_i_begaran_vinner(llm_ready, monkeypatch):
    """Skickar frontenden en sluttid ska den gälla — schemat är fallbacken."""
    _stub_generate(monkeypatch,
                   {"board": _valid_board(), "errors": [], "rounds": 1})
    r = llm_ready.post("/api/planning/generate",
                       json={"moment": "x", "starttid": "13:00",
                             "sluttid": "14:30"})
    assert _tid(_done(r)["board"]) == "13:00–14:30"


def test_tiden_overlever_en_iteration(llm_ready, monkeypatch):
    """refine skriver om HELA tavlan och kan tappa tidssektionen — den läggs
    på igen efteråt i stället för att bevakas."""
    pid = _planering_med_tid(llm_ready, monkeypatch)
    monkeypatch.setattr(lesson_board, "refine_board",
                        lambda board, instruction, **kw: {
                            "board": _valid_board(), "errors": [], "rounds": 1})
    r = llm_ready.post(f"/api/planning/{pid}/refine",
                       json={"message": "byt exempel 2"})
    assert _tid(_done(r)["board"]) == "09:10"


def test_tiden_overlever_en_reparation(llm_ready, monkeypatch):
    pid = _planering_med_tid(llm_ready, monkeypatch)
    monkeypatch.setattr(lesson_board, "repair_board",
                        lambda board, warnings, **kw: {
                            "board": _valid_board(), "errors": [], "rounds": 2})
    r = llm_ready.post(f"/api/planning/{pid}/render-report",
                       json={"warnings": ["[WB] vanster: element-överlapp"]})
    assert _tid(_done(r)["board"]) == "09:10"


# -------------------------------------------------------- Fas 1: approve --

def test_approve_writes_board_json_under_base(llm_ready, monkeypatch):
    pid = _make_planning(llm_ready, monkeypatch)
    r = llm_ready.post(f"/api/planning/{pid}/approve", json={})
    assert r.status_code == 200
    from pathlib import Path
    saved = Path(r.json()["path"])
    assert saved.exists() and saved.suffix == ".json"
    rel = saved.relative_to(llm_ready.base_dir)
    assert rel.parts[0] == "Transkriberingar"
    assert rel.parts[2] == "planering"
    payload = json.loads(saved.read_text(encoding="utf-8"))
    assert payload["version"] == "wb-json-v1"
    assert payload["board"]["title"] == "Pythagoras sats"


def test_export_lagger_bilden_bredvid_wb_jsonen(llm_ready, monkeypatch):
    """Tavlan är två saker i arkivet: JSON:en den skrevs som och bilden den
    såg ut som. Med `pid` tas lektionsnamnet ur planeringen själv, så de två
    hamnar i samma mapp även när klienten skickar en annan titel."""
    pid = _make_planning(llm_ready, monkeypatch)
    godkand = llm_ready.post(f"/api/planning/{pid}/approve", json={}).json()
    r = llm_ready.post("/api/planning/export",
                       json={"pid": pid, "title": "något helt annat",
                             "png": _DATA_URL})
    assert r.status_code == 200
    from pathlib import Path
    bild = Path(r.json()["path"])
    assert bild.parent == Path(godkand["path"]).parent
    assert bild.suffix == ".png" and bild.read_bytes() == _PNG_1PX


def test_export_utan_kand_pid_faller_tillbaka_pa_titeln(llm_ready):
    """En tavla som aldrig gick genom servern (prototypens form) har inget
    pid — då gäller titeln klienten skickar."""
    r = llm_ready.post("/api/planning/export",
                       json={"pid": "finns-ej", "title": "Pythagoras sats",
                             "png": _DATA_URL})
    assert r.status_code == 200
    from pathlib import Path
    assert "Pythagoras sats" in Path(r.json()["path"]).parts


def test_approve_unknown_id(llm_ready):
    r = llm_ready.post("/api/planning/finns-ej/approve", json={})
    assert r.status_code == 404


# ------------------------------------------- Fas 3: DB, kalender, PATCH --

def _make_planning_with_datum(llm_ready, monkeypatch) -> dict:
    _stub_generate(monkeypatch,
                   {"board": _valid_board(), "errors": [], "rounds": 1})
    r = llm_ready.post("/api/planning/generate",
                       json={"moment": "Pythagoras sats",
                             "datum": "2026-09-01", "starttid": "09:10"})
    result = _done(r)
    ra = llm_ready.post(f"/api/planning/{result['id']}/approve", json={})
    assert ra.status_code == 200
    return ra.json()


def test_approve_persists_to_db(llm_ready, monkeypatch):
    approved = _make_planning_with_datum(llm_ready, monkeypatch)
    planned_id = approved["planned_id"]
    r = llm_ready.get(f"/api/planning/{planned_id}")
    assert r.status_code == 200
    planned = r.json()
    assert planned["status"] == "planerad"
    assert planned["datum"] == "2026-09-01"
    assert planned["starttid"] == "09:10"
    assert planned["board"]["title"] == "Pythagoras sats"


def test_get_planned_404(llm_ready):
    assert llm_ready.get("/api/planning/99999").status_code == 404


def test_calendar_returns_month_entries(llm_ready, monkeypatch):
    approved = _make_planning_with_datum(llm_ready, monkeypatch)
    r = llm_ready.get("/api/planning/calendar", params={"year": 2026, "month": 9})
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert [e["typ"] for e in entries] == ["planering"]
    assert entries[0]["id"] == approved["planned_id"]
    assert entries[0]["status"] == "planerad"
    # tom månad + ogiltig månad
    assert llm_ready.get("/api/planning/calendar",
                         params={"year": 2026, "month": 10}).json()["entries"] == []
    assert llm_ready.get("/api/planning/calendar",
                         params={"year": 2026, "month": 13}).status_code == 400


def test_patch_planned_status_and_link(llm_ready, monkeypatch):
    from app import db as appdb
    approved = _make_planning_with_datum(llm_ready, monkeypatch)
    planned_id = approved["planned_id"]

    r = llm_ready.patch(f"/api/planning/{planned_id}", json={"status": "inställd"})
    assert r.status_code == 200 and r.json()["status"] == "inställd"

    # manuell länkning till en lektion + av-länkning
    conn = appdb.connect(llm_ready.base_dir / "transkribera.db")
    les = appdb.create_lesson(conn, history_id="hx",
                              ts="2026-09-01T09:00:00", name="lektion")
    conn.close()
    r = llm_ready.patch(f"/api/planning/{planned_id}",
                        json={"lesson_id": les["id"], "status": "hållen"})
    assert r.json()["lesson_id"] == les["id"]
    r = llm_ready.patch(f"/api/planning/{planned_id}",
                        json={"lesson_id": None, "status": "planerad"})
    assert r.json()["lesson_id"] is None

    assert llm_ready.patch(f"/api/planning/{planned_id}",
                           json={"status": "ogiltig"}).status_code == 400
    assert llm_ready.patch(f"/api/planning/{planned_id}",
                           json={}).status_code == 400
    assert llm_ready.patch("/api/planning/99999",
                           json={"status": "hållen"}).status_code == 404


def test_org_patch_autolinks_lesson(llm_ready, monkeypatch):
    """Org-flödet: när lektionen får klass/kurs/datum länkas den mot en
    matchande planering som blir 'hållen'."""
    from app import db as appdb
    conn = appdb.connect(llm_ready.base_dir / "transkribera.db")
    gid = appdb.get_or_create_group(conn, "NA23")
    cid = appdb.get_or_create_course(conn, "Ma3c")
    p = appdb.create_planned_lesson(conn, titel="Derivata", datum="2026-09-02",
                                    starttid="09:10", group_id=gid, course_id=cid)
    les = appdb.create_lesson(conn, history_id="hy",
                              ts="2026-09-02T09:12:00", name="lektion")
    conn.close()

    r = llm_ready.patch(f"/api/lessons/{les['id']}",
                        json={"group_id": gid, "course_id": cid,
                              "datum": "2026-09-02", "starttid": "09:12"})
    assert r.status_code == 200
    assert r.json()["planned_lesson_id"] == p["id"]
    planned = llm_ready.get(f"/api/planning/{p['id']}").json()
    assert planned["status"] == "hållen"
    assert planned["lesson_id"] == les["id"]


# ---------------------------------------------------------- Fas: underlag --

def _underlag_fixture(client, monkeypatch, beskrivning="Sida om andragradsfunktioner."):
    """Stubbar visionsmodellen och laddar upp en 1×1-PNG som underlag."""
    from app.web import routes_planning as rp
    monkeypatch.setattr(client.app.state.arbiter, "ensure_model",
                        lambda spec=None: "claude-code")
    monkeypatch.setattr(rp.llm_client, "chat",
                        lambda *a, **k: beskrivning)
    r = client.post("/api/planning/underlag",
                    json={"filer": [{"namn": "kap3.png", "data": _DATA_URL}]})
    assert r.status_code == 200
    return _done(r)


def test_underlag_upload_saves_and_describes(client, monkeypatch):
    result = _underlag_fixture(client, monkeypatch)
    assert result["id"] and len(result["filer"]) == 1
    assert result["filer"][0]["namn"] == "kap3.png"
    assert "andragradsfunktioner" in result["filer"][0]["beskrivning"]
    d = client.base_dir / "Transkriberingar" / "underlag" / result["id"]
    assert (d / "sida-01.png").exists()
    assert (d / "underlag.json").exists()


def test_underlag_rejects_bad_format_and_empty(client):
    r = client.post("/api/planning/underlag", json={"filer": []})
    assert r.status_code == 400
    r = client.post("/api/planning/underlag", json={
        "filer": [{"namn": "x.txt", "data": "data:text/plain;base64,aGVq"}]})
    assert r.status_code == 400


def test_underlag_without_vision_model_degrades(client, monkeypatch):
    monkeypatch.setattr(client.app.state.arbiter, "ensure_model", lambda spec=None: None)
    r = client.post("/api/planning/underlag",
                    json={"filer": [{"namn": "kap3.png", "data": _DATA_URL}]})
    result = _done(r)
    assert result["filer"][0]["beskrivning"] == ""
    # loggen berättar att bildtolkningen saknas
    assert any("bildtolkning" in (e.get("msg") or "") for e in _events(r))


def test_generate_passes_underlag_to_prompt(client, monkeypatch):
    result = _underlag_fixture(client, monkeypatch)
    monkeypatch.setattr(client.app.state.arbiter, "ensure_llm",
                        lambda: "http://127.0.0.1:8170")
    calls = _stub_generate(monkeypatch,
                           {"board": _valid_board(), "errors": [], "rounds": 1})
    r = client.post("/api/planning/generate",
                    json={"moment": "Andragradsfunktioner",
                          "underlag": result["id"]})
    assert r.status_code == 200
    assert "andragradsfunktioner" in calls[0]["underlag"].lower()
    assert "kap3.png" in calls[0]["underlag"]


def test_generate_ignores_invalid_underlag_id(client, monkeypatch):
    monkeypatch.setattr(client.app.state.arbiter, "ensure_llm",
                        lambda: "http://127.0.0.1:8170")
    calls = _stub_generate(monkeypatch,
                           {"board": _valid_board(), "errors": [], "rounds": 1})
    r = client.post("/api/planning/generate",
                    json={"moment": "Bråk", "underlag": "../../etc"})
    assert r.status_code == 200
    assert calls[0]["underlag"] == ""


# ---- Arkivsökets äkta relevans + live-events (spec 2026-07-18) --------------

def test_archive_ask_ignores_stopword_matches(client):
    """En tavla som bara matchar frågans småord ("var/jag/och") får inte bli
    källa — genomsökningen spelas ändå upp och ett ärligt 0-träffar-svar
    strömmas utan att LLM:en behövs."""
    from app import db as appdb
    conn = appdb.connect(client.base_dir / "transkribera.db")
    appdb.create_planned_lesson(conn, titel="Utflykt",
                                moment="var på berget och jag såg en älg")
    conn.close()
    r = client.post("/api/planning/ask",
                    json={"q": "Var förklarar jag täljare och nämnare?"})
    assert r.status_code == 200
    events = _events(r)
    assert [e["hits"] for e in events if e["type"] == "scan_result"] == [0]
    done = next(e for e in events if e["type"] == "done")
    assert done["result"]["sources"] == []
    assert "verkar inte nämna" in done["result"]["text"]


def test_archive_ask_empty_archive_404(client):
    r = client.post("/api/planning/ask", json={"q": "derivata"})
    assert r.status_code == 404


def test_archive_ask_emits_real_scan_events(client, monkeypatch):
    """scan_plan → scan_result×N → deep_read före svaret; träffantalen är
    innehållsordens verkliga förekomster och bara träffarna blir källor."""
    from app import db as appdb
    from app.web import routes_planning as rp
    conn = appdb.connect(client.base_dir / "transkribera.db")
    appdb.create_planned_lesson(conn, titel="Bråk",
                                moment="täljare och nämnare, mer täljare",
                                datum="2026-06-20")
    appdb.create_planned_lesson(conn, titel="Utflykt",
                                moment="var på berget och jag såg en älg",
                                datum="2026-06-21")
    conn.close()
    monkeypatch.setattr(client.app.state.arbiter, "try_acquire_gpu", lambda: "nyckel")
    monkeypatch.setattr(client.app.state.arbiter, "release_gpu", lambda n: True)
    monkeypatch.setattr(client.app.state.arbiter, "ensure_llm",
                        lambda: "http://127.0.0.1:8170")
    monkeypatch.setattr(rp.llm_client, "generate",
                        lambda *a, **k: "Det står på tavlan Bråk")

    r = client.post("/api/planning/ask",
                    json={"q": "Var förklarar jag täljare och nämnare?"})
    assert r.status_code == 200
    events = _events(r)
    types = [e["type"] for e in events]
    assert types.index("scan_plan") < types.index("scan_result") \
        < types.index("deep_read") < types.index("done")

    plan = next(e for e in events if e["type"] == "scan_plan")
    assert plan["total"] == 2
    assert [i["name"] for i in plan["items"]] == ["Utflykt", "Bråk"]

    key_by_name = {i["name"]: i["key"] for i in plan["items"]}
    hits = {e["key"]: e["hits"] for e in events if e["type"] == "scan_result"}
    assert hits[key_by_name["Utflykt"]] == 0
    assert hits[key_by_name["Bråk"]] == 3          # 2×täljare + 1×nämnare

    deep = next(e for e in events if e["type"] == "deep_read")
    assert [s["titel"] for s in deep["sources"]] == ["Bråk"]


def test_refine_far_hela_meddelandet_inklusive_kallviktningen(llm_ready, monkeypatch):
    """Ett klick på en källa i canvas skriver in «Ta mer ur boken …» i FÄLTET.
    Hela meningen är prompten — det finns inget separat viktningsfält, och ska
    inte finnas: viktningen är något läraren skrev."""
    _stub_generate(monkeypatch, {"board": _valid_board(), "errors": [], "rounds": 1})
    pid = _done(llm_ready.post("/api/planning/generate",
                               json={"moment": "Derivator"}))["id"]

    sett = {}

    def fake_refine(board, message, *, model, mal=None, llm=None,
                    max_rounds=lesson_board.MAX_ROUNDS, log_cb=None, token_cb=None):
        sett["message"] = message
        return {"board": _valid_board(), "errors": [], "rounds": 1}
    monkeypatch.setattr(lesson_board, "refine_board", fake_refine)

    meddelande = "Ta mer ur boken och mer ur lektionen — byt exempel 2"
    r = llm_ready.post(f"/api/planning/{pid}/refine", json={"message": meddelande})
    assert r.status_code == 200
    _done(r)
    assert sett["message"] == meddelande


def test_refine_utan_meddelande_ar_400(llm_ready, monkeypatch):
    _stub_generate(monkeypatch, {"board": _valid_board(), "errors": [], "rounds": 1})
    pid = _done(llm_ready.post("/api/planning/generate",
                               json={"moment": "Derivator"}))["id"]
    assert llm_ready.post(f"/api/planning/{pid}/refine",
                          json={"message": "  "}).status_code == 400


def test_refine_pa_okand_planering_ar_404(llm_ready):
    assert llm_ready.post("/api/planning/finnsinte/refine",
                          json={"message": "byt exempel"}).status_code == 404


def test_archive_search_marks_hits_in_snippet(client):
    """Arkivsökets snippet ska markera träffarna med \\x02..\\x03 — samma
    kontrakt som /api/search — så att UI:t kan highlighta sökordet."""
    from app import db as appdb
    conn = appdb.connect(client.base_dir / "transkribera.db")
    appdb.create_planned_lesson(conn, titel="Bråk",
                                moment="idag går vi igenom täljare och nämnare",
                                datum="2026-06-20")
    conn.close()
    r = client.get("/api/planning/archive/search", params={"q": "täljare"})
    assert r.status_code == 200
    hits = r.json()["hits"]
    assert len(hits) == 1
    assert "\x02täljare\x03" in hits[0]["snippet"]
