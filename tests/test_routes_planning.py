"""Planering-routern (Fas 0/1): PNG-export, generering, reparation,
iteration och godkännande — allt stubbat och säkert under base_dir."""
import base64
import copy
import json

import pytest

from app import lesson_board
from app.web import server


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


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    class HW:
        gpu_name = "Test GPU"; vram_mb = 24000; has_cuda = True
        ram_mb = 64000; cpu_cores = 16; free_disk_mb = 500000
        cpu_name = "Test CPU"; vram_free_mb = 20000; ram_free_mb = 40000
        total_disk_mb = 1000000; cuda_version = "12.1"
        compute_capability = "8.9"; gpu_arch = "Ada Lovelace"; disks = []

    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    monkeypatch.setattr(server.llm_manager, "is_installed", lambda *a, **k: False)
    monkeypatch.setattr(server.whisper_manager, "is_installed", lambda *a, **k: False)
    c = TestClient(server.create_app(base_dir=tmp_path))
    c.base_dir = tmp_path
    return c


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

@pytest.fixture
def llm_ready(client, monkeypatch):
    """Arbitern svarar som om LLM:en är installerad och startad."""
    monkeypatch.setattr(client.app.state.arbiter, "ensure_llm",
                        lambda: "http://127.0.0.1:8170")
    return client


def _stub_generate(monkeypatch, result):
    calls = []

    def fake(course, group, moment, *, model, memory="", underlag="", llm=None,
             max_rounds=lesson_board.MAX_ROUNDS, log_cb=None, token_cb=None):
        calls.append({"course": course, "group": group, "moment": moment,
                      "model": model, "memory": memory, "underlag": underlag})
        if log_cb:
            log_cb("Genererar lektionstavlan …")
        return result
    monkeypatch.setattr(lesson_board, "generate_board", fake)
    return calls


def test_generate_requires_moment(llm_ready):
    r = llm_ready.post("/api/planning/generate", json={"moment": "  "})
    assert r.status_code == 400


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


def test_generate_409_when_gpu_busy(llm_ready, monkeypatch):
    monkeypatch.setattr(llm_ready.app.state.arbiter, "try_acquire_gpu",
                        lambda: False)
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

    def fake_refine(board, instruction, *, model, llm=None,
                    max_rounds=lesson_board.MAX_ROUNDS, log_cb=None,
                    token_cb=None):
        captured["instruction"] = instruction
        return {"board": updated, "errors": [], "rounds": 1}
    monkeypatch.setattr(lesson_board, "refine_board", fake_refine)

    r = llm_ready.post(f"/api/planning/{pid}/refine",
                       json={"message": "byt exempel 2"})
    result = _done(r)
    assert result["board"]["title"] == "Uppdaterad"
    assert captured["instruction"] == "byt exempel 2"


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
                        lambda spec: "http://127.0.0.1:8170")
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
    monkeypatch.setattr(client.app.state.arbiter, "ensure_model", lambda spec: None)
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
    källa — utan innehållsordsträff svarar arkivfrågan 404."""
    from app import db as appdb
    conn = appdb.connect(client.base_dir / "transkribera.db")
    appdb.create_planned_lesson(conn, titel="Utflykt",
                                moment="var på berget och jag såg en älg")
    conn.close()
    r = client.post("/api/planning/ask",
                    json={"q": "Var förklarar jag täljare och nämnare?"})
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
    monkeypatch.setattr(client.app.state.arbiter, "try_acquire_gpu", lambda: True)
    monkeypatch.setattr(client.app.state.arbiter, "release_gpu", lambda: None)
    monkeypatch.setattr(client.app.state.arbiter, "ensure_llm",
                        lambda: "http://127.0.0.1:8170")
    monkeypatch.setattr(rp.llm_client, "generate",
                        lambda *a, **k: "Det står på tavlan Bråk")
    monkeypatch.setattr(server.llm_manager, "is_installed", lambda *a, **k: True)

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
