"""Prov-routern (Fas 4): generering/refine/approve/artefakter med stubbar."""
import copy
import json

import pytest

from app import db as appdb
from app import exam_gen, exam_pdf
from app.web import server, routes_exam


def _events(resp):
    return [json.loads(line[len("data:"):])
            for line in resp.text.splitlines() if line.startswith("data:")]


def _done(resp):
    evs = [e for e in _events(resp) if e["type"] == "done"]
    assert evs, _events(resp)
    return evs[0]["result"]


def _exam_doc():
    from tests.test_exam import _exam
    return _exam()


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
    c = TestClient(server.create_app(base_dir=tmp_path))
    monkeypatch.setattr(c.app.state.arbiter, "ensure_llm", lambda: "http://x")
    c.base_dir = tmp_path
    return c


def _stub_generate(monkeypatch, result=None):
    calls = []

    def fake(kurs, klass, punkter, *, model, antal=10, tid_min=120,
             delar=True, memory="", teman="", referens="", profil="prov",
             llm=None, max_rounds=exam_gen.MAX_ROUNDS, log_cb=None):
        calls.append({"kurs": kurs, "punkter": punkter, "memory": memory,
                      "teman": teman, "antal": antal,
                      "referens": referens, "profil": profil})
        if log_cb:
            log_cb("Skriver provet …")
        return result or {"exam": _exam_doc(), "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "generate_exam", fake)
    return calls


def _course_id(client, namn="Matematik, nivå 2b"):
    for c in client.get("/api/courses").json():
        if c["namn"] == namn:
            return c["id"]
    raise AssertionError("kursen saknas (seedningen?)")


def _make_exam(client, monkeypatch, **extra):
    calls = _stub_generate(monkeypatch)
    body = {"course_id": _course_id(client), "antal": 6, **extra}
    r = client.post("/api/exams/generate", json=body)
    assert r.status_code == 200
    return _done(r), calls


def test_generate_requires_course(client):
    assert client.post("/api/exams/generate", json={}).status_code == 400


def test_generate_creates_exam_with_balance_info(client, monkeypatch):
    result, calls = _make_exam(client, monkeypatch, datum="2026-10-05")
    assert result["errors"] == []
    assert result["exam"]["titel"].startswith("Prov")
    assert result["granser"]["total"] == 20
    assert result["summor"]["e"] == 10
    assert calls[0]["kurs"] == "Matematik, nivå 2b"
    # provet finns i DB:n
    r = client.get(f"/api/exams/{result['id']}")
    assert r.status_code == 200
    assert r.json()["status"] == "utkast"


def test_generate_passes_selected_content_and_tags_exam(client, monkeypatch):
    cid = _course_id(client)
    conn = appdb.connect(client.base_dir / "transkribera.db")
    punkt = appdb.list_course_content(conn, cid)[0]
    conn.close()
    result, calls = _make_exam(client, monkeypatch, punkter=[punkt["id"]])
    assert any(punkt["rubrik"] in p for p in calls[0]["punkter"])
    conn = appdb.connect(client.base_dir / "transkribera.db")
    tagged = conn.execute("SELECT content_id FROM content_tags WHERE exam_id = ?",
                          (result["id"],)).fetchall()
    conn.close()
    assert [t["content_id"] for t in tagged] == [punkt["id"]]


def test_generate_409_when_busy(client, monkeypatch):
    monkeypatch.setattr(client.app.state.arbiter, "try_acquire_gpu", lambda: False)
    r = client.post("/api/exams/generate", json={"course_id": _course_id(client)})
    assert r.status_code == 409


def test_refine_adds_version(client, monkeypatch):
    result, _ = _make_exam(client, monkeypatch)
    updated = _exam_doc()
    updated["uppgifter"][0]["text"] = "Ny uppgift $x = 2$."
    captured = {}

    def fake_refine(exam, message, *, model, nummer=None, profil="prov",
                    llm=None, max_rounds=exam_gen.MAX_ROUNDS, log_cb=None):
        captured["message"] = message
        captured["nummer"] = nummer
        return {"exam": updated, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)

    r = client.post(f"/api/exams/{result['id']}/refine",
                    json={"message": "byt uppgift 1", "nummer": 1})
    res = _done(r)
    assert captured == {"message": "byt uppgift 1", "nummer": 1}
    assert len(res["versions"]) == 2
    assert res["exam"]["uppgifter"][0]["text"] == "Ny uppgift $x = 2$."


def test_refine_requires_message(client, monkeypatch):
    result, _ = _make_exam(client, monkeypatch)
    assert client.post(f"/api/exams/{result['id']}/refine",
                       json={"message": " "}).status_code == 400
    assert client.post("/api/exams/999/refine",
                       json={"message": "x"}).status_code == 404


def test_approve_without_engine_saves_tex(client, monkeypatch):
    result, _ = _make_exam(client, monkeypatch, datum="2026-10-05")
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    r = client.post(f"/api/exams/{result['id']}/approve", json={})
    res = _done(r)
    assert res["status"] == "godkänt"
    assert res["tex"] and res["pdf"] is None
    from pathlib import Path
    tex = Path(res["tex"])
    assert tex.exists()
    rel = tex.relative_to(client.base_dir)
    assert rel.parts[:2] == ("Transkriberingar", "prov")
    assert "Matematik, nivå 2b" in rel.parts
    # tex serveras, pdf 404
    assert client.get(f"/api/exams/{result['id']}/tex").status_code == 200
    assert client.get(f"/api/exams/{result['id']}/pdf").status_code == 404


def test_approve_with_stubbed_engine_sets_pdf(client, monkeypatch):
    result, _ = _make_exam(client, monkeypatch, datum="2026-10-05")
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)

    def fake_compile(tex, out_dir, jobname, **kw):
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{jobname}.pdf"
        p.write_bytes(b"%PDF-1.5 fejk")
        return p, ""
    monkeypatch.setattr(exam_pdf, "compile_pdf", fake_compile)

    r = client.post(f"/api/exams/{result['id']}/approve", json={})
    res = _done(r)
    assert res["pdf"] and res["errors"] == []
    pr = client.get(f"/api/exams/{result['id']}/pdf")
    assert pr.status_code == 200
    assert pr.content.startswith(b"%PDF")


def test_approve_compile_failure_reports_honestly(client, monkeypatch):
    result, _ = _make_exam(client, monkeypatch)
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)
    monkeypatch.setattr(exam_pdf, "compile_pdf",
                        lambda *a, **k: (None, "! Missing $ inserted."))
    monkeypatch.setattr(exam_gen, "fix_latex",
                        lambda exam, log, **kw: {"exam": exam, "errors": [],
                                                 "rounds": 1})
    r = client.post(f"/api/exams/{result['id']}/approve", json={})
    res = _done(r)
    assert res["status"] == "godkänt"                 # .tex finns — ärligt fel
    assert any(e["code"] == "kompilering" for e in res["errors"])
    assert res["pdf"] is None


# ------------------------------------------------------ Fas 5: arbetsblad --

def test_generate_arbetsblad_sets_typ_and_profile(client, monkeypatch):
    calls = _stub_generate(monkeypatch)
    r = client.post("/api/exams/generate",
                    json={"course_id": _course_id(client), "typ": "arbetsblad"})
    result = _done(r)
    assert result["typ"] == "arbetsblad"
    assert calls[0]["profil"] == "arbetsblad"
    assert client.get(f"/api/exams/{result['id']}").json()["typ"] == "arbetsblad"


def test_approve_arbetsblad_renders_facit_without_bedomning(client, monkeypatch):
    calls = _stub_generate(monkeypatch)
    r = client.post("/api/exams/generate",
                    json={"course_id": _course_id(client), "typ": "arbetsblad",
                          "datum": "2026-10-05"})
    result = _done(r)
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    ra = client.post(f"/api/exams/{result['id']}/approve", json={})
    res = _done(ra)
    from pathlib import Path
    tex = Path(res["tex"]).read_text(encoding="utf-8")
    assert "Facit" in tex and "Arbetsblad" in tex
    assert "Kravgränser" not in tex
    # ingen separat bedömningsanvisning för arbetsblad
    assert not list(Path(res["tex"]).parent.glob("* - bedomning.tex"))


def test_generate_with_referens_builds_reference_prompt(client, monkeypatch):
    # skapa + godkänn ett referensprov först
    result, _ = _make_exam(client, monkeypatch, datum="2026-09-01")
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    _done(client.post(f"/api/exams/{result['id']}/approve", json={}))

    calls = _stub_generate(monkeypatch)
    r = client.post("/api/exams/generate",
                    json={"course_id": _course_id(client),
                          "referens_exam_id": result["id"]})
    _done(r)
    assert "HÖJ" in calls[0]["referens"]
    assert "kvadratkomplettering" in calls[0]["referens"]
    assert calls[0]["teman"] == ""        # referensläget ersätter undvik-listan


def test_generate_flags_duplicates_against_previous_exam(client, monkeypatch):
    # godkänt prov med samma uppgiftstexter → nya provet flaggas
    result, _ = _make_exam(client, monkeypatch, datum="2026-09-01")
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    _done(client.post(f"/api/exams/{result['id']}/approve", json={}))

    _stub_generate(monkeypatch)           # returnerar identiskt prov
    r = client.post("/api/exams/generate",
                    json={"course_id": _course_id(client)})
    res = _done(r)
    assert len(res["dubbletter"]) >= 4
    d = res["dubbletter"][0]
    assert d["likhet"] >= 0.55 and d["mot_exam_id"] == result["id"]


def test_content_status_provad_flag(client, monkeypatch):
    cid = _course_id(client)
    conn = appdb.connect(client.base_dir / "transkribera.db")
    punkt = appdb.list_course_content(conn, cid)[0]
    conn.close()
    result, _ = _make_exam(client, monkeypatch, punkter=[punkt["id"]])
    # otestat tills provet är godkänt
    r = client.get("/api/exams/content-status", params={"course_id": cid})
    assert {p["id"]: p["provad"] for p in r.json()["punkter"]}[punkt["id"]] is False
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    r = client.get("/api/exams/content-status", params={"course_id": cid})
    assert {p["id"]: p["provad"] for p in r.json()["punkter"]}[punkt["id"]] is True


def test_content_status_marks_behandlat(client, monkeypatch):
    cid = _course_id(client)
    conn = appdb.connect(client.base_dir / "transkribera.db")
    punkt = appdb.list_course_content(conn, cid)[0]
    les = appdb.create_lesson(conn, history_id="h1",
                              ts="2026-09-01T09:00:00", name="lektion")
    gid = appdb.get_or_create_group(conn, "SA23")
    appdb.update_lesson(conn, les["id"], group_id=gid, course_id=cid)
    appdb.tag_content(conn, punkt["id"], lesson_id=les["id"])
    conn.close()

    r = client.get("/api/exams/content-status",
                   params={"course_id": cid, "group_id": gid})
    punkter = r.json()["punkter"]
    by_id = {p["id"]: p for p in punkter}
    assert by_id[punkt["id"]]["behandlad"] is True
    others = [p for p in punkter if p["id"] != punkt["id"]]
    assert all(p["behandlad"] is False for p in others)
