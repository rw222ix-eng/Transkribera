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
             delar=True, memory="", teman="", referens="", bilder="",
             profil="prov",
             llm=None, max_rounds=exam_gen.MAX_ROUNDS, log_cb=None):
        calls.append({"kurs": kurs, "punkter": punkter, "memory": memory,
                      "teman": teman, "antal": antal,
                      "referens": referens, "bilder": bilder, "profil": profil})
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
    assert result["summor"]["e"] == 9
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


def test_approve_bedomning_failure_surfaces_and_keeps_prov(client, monkeypatch):
    """Bedömningsanvisningens returvärde kastades bort: föll den kom varken
    logg eller errors-post, och kvittot stod kvar på 'PDF skapad'. Läraren
    upptäckte det först vid rättningen. Felet ska SYNAS — men ett fungerande
    prov får inte kastas bort bara för att det sekundära dokumentet föll."""
    result, _ = _make_exam(client, monkeypatch)
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)

    sedda_loggar = []

    def fake_compile(tex, out_dir, jobname, **kw):
        if jobname.endswith("bedomning"):
            return None, ('Could not locate a virtual/physical font for '
                          'TFM "ntxsy7".')
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{jobname}.pdf"
        p.write_bytes(b"%PDF-1.5 fejk")
        return p, ""
    monkeypatch.setattr(exam_pdf, "compile_pdf", fake_compile)

    def fake_fix(exam, log, **kw):
        sedda_loggar.append(log)
        return {"exam": exam, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "fix_latex", fake_fix)

    r = client.post(f"/api/exams/{result['id']}/approve", json={})
    evs = _events(r)
    res = _done(r)

    bed_loggar = [e["msg"] for e in evs
                  if e["type"] == "log" and "edömningsanvisningen" in e.get("msg", "")]
    assert bed_loggar, "felet nämndes aldrig i strömmen"
    bed = [e for e in res["errors"] if e["code"] == "bedomning"]
    assert bed, f"ingen bedömningspost i errors: {res['errors']}"
    assert "ntxsy7" in bed[0]["message"]
    # Loggraden i strömmen är transient (den försvinner när körningen är
    # klar, se exRunning-gaten i app.js) — det som PERSISTERAS är message,
    # och gränssnittet läser aldrig code. Utan svensk prefix framför den
    # råa LaTeX-loggen ser läraren bara en engelsk fontrad bredvid ett
    # kvitto som säger att PDF:en skapades, med inget som säger VILKET
    # dokument som saknas.
    assert bed[0]["message"].startswith(
        "Bedömningsanvisningen gick inte att kompilera:\n")
    assert res["pdf"], "det fungerande provet ska INTE kastas bort"
    assert res["status"] == "godkänt"
    # fix_latex måste få BEDÖMNINGENS logg — provets är tom, och en tom logg
    # ger modellen ingenting att korrigera.
    assert sedda_loggar and all("ntxsy7" in lg for lg in sedda_loggar)
    # Sista rundan ger upp (MAX_LATEX_ROUNDS nått) — då får loggraden inte
    # längre lova en korrigering som aldrig sker. Tidigare rundor FÅR lova
    # det, eftersom de faktiskt följs av ett fix_latex-anrop.
    assert bed_loggar[-1] == "Bedömningsanvisningen gick inte att kompilera."


def test_approve_prov_fran_tidigare_runda_overlever_senare_kompileringsfel(
        client, monkeypatch):
    """Fynd 2 (granskning): koden satte om pdf_path till DENNA rundas
    kompileringsresultat varje varv. Om provet kompilerar i runda 0 men
    bedömningen faller, går slingan vidare till fix_latex — som kan skriva om
    HELA provet till JSON där en senare runda inte längre går att kompilera.
    Då blev pdf_path None trots att runda 0:s fungerande prov-PDF fortfarande
    låg kvar i utkatalogen, och ett fullt användbart prov blev oåtkomligt
    för läraren bara för att en SENARE, av bedömningen utlöst, runda gick
    illa."""
    result, _ = _make_exam(client, monkeypatch)
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)

    antal_provkompileringar = {"n": 0}

    def fake_compile(tex, out_dir, jobname, **kw):
        if jobname.endswith("bedomning"):
            return None, "! Undefined control sequence i bedömningen."
        antal_provkompileringar["n"] += 1
        if antal_provkompileringar["n"] == 1:
            out_dir.mkdir(parents=True, exist_ok=True)
            p = out_dir / f"{jobname}.pdf"
            p.write_bytes(b"%PDF-1.5 fejk")
            return p, ""
        return None, "! Missing $ inserted."
    monkeypatch.setattr(exam_pdf, "compile_pdf", fake_compile)
    monkeypatch.setattr(exam_gen, "fix_latex",
                        lambda exam, log, **kw: {"exam": exam, "errors": [],
                                                 "rounds": 1})

    r = client.post(f"/api/exams/{result['id']}/approve", json={})
    res = _done(r)

    from pathlib import Path
    assert res["pdf"], "runda 0:s fungerande prov ska inte försvinna"
    assert Path(res["pdf"]).exists()
    assert any(e["code"] == "bedomning" for e in res["errors"]), res["errors"]
    assert not any(e["code"] == "kompilering" for e in res["errors"])


def test_approve_bedomning_failure_without_llm_still_gets_bedomning_code(
        client, monkeypatch):
    """Grenen för "ingen omkörning möjlig" (modellen kan inte startas) hade
    kvar den gamla hårdkodade 'kompilering'-koden efter att rundgrenen fick
    'bedomning'. Provet hade då redan kompilerat och bara anvisningen
    saknades, men klienten fick samma kod som vid ett fullständigt
    misslyckande — och skulle kunna kasta bort ett fullt användbart prov."""
    result, _ = _make_exam(client, monkeypatch)
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)
    monkeypatch.setattr(client.app.state.arbiter, "ensure_llm", lambda: None)

    def fake_compile(tex, out_dir, jobname, **kw):
        if jobname.endswith("bedomning"):
            return None, "! Undefined control sequence."
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{jobname}.pdf"
        p.write_bytes(b"%PDF-1.5 fejk")
        return p, ""
    monkeypatch.setattr(exam_pdf, "compile_pdf", fake_compile)

    r = client.post(f"/api/exams/{result['id']}/approve", json={})
    evs = _events(r)
    res = _done(r)

    bed = [e for e in res["errors"] if e["code"] == "bedomning"]
    assert bed, f"koden ska vara 'bedomning', inte 'kompilering': {res['errors']}"
    assert bed[0]["message"].startswith(
        "Bedömningsanvisningen gick inte att kompilera:\n")
    assert res["pdf"], "provet kompilerade och ska behållas trots att " \
                        "modellen inte kunde startas"
    # ensure_llm() är None redan vid FÖRSTA rundan här, så det blir aldrig
    # något omförsök. Loggraden får då inte påstå "försöker korrigera" —
    # det vore precis den sortens tomt löfte den här rutten ska bort med.
    bed_loggar = [e["msg"] for e in evs
                  if e["type"] == "log" and "edömningsanvisningen" in e.get("msg", "")]
    assert bed_loggar == ["Bedömningsanvisningen gick inte att kompilera."]


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


# ------------------------------------------------------ Fas 4: bildunderlag --

_PNG_1PX_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
                "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def _upload_underlag(client, monkeypatch, beskrivning="Graf över en andragradsfunktion."):
    from app.web import routes_planning as rp
    monkeypatch.setattr(client.app.state.arbiter, "ensure_model",
                        lambda spec: "http://127.0.0.1:8170")
    monkeypatch.setattr(rp.llm_client, "chat", lambda *a, **k: beskrivning)
    r = client.post("/api/planning/underlag", json={
        "filer": [{"namn": "figur.png",
                   "data": "data:image/png;base64," + _PNG_1PX_B64}]})
    assert r.status_code == 200
    return _done(r)


def test_generate_with_bilder_builds_block_and_sanitizes(client, monkeypatch):
    und = _upload_underlag(client, monkeypatch)
    exam = _exam_doc()
    exam["uppgifter"][0]["bild"] = 1        # giltigt index
    exam["uppgifter"][1]["bild"] = 7        # utanför underlaget → saneras
    calls = _stub_generate(monkeypatch,
                           result={"exam": exam, "errors": [], "rounds": 1})
    r = client.post("/api/exams/generate",
                    json={"course_id": _course_id(client), "underlag": und["id"]})
    result = _done(r)
    assert "andragradsfunktion" in calls[0]["bilder"]
    assert '"bild"' in calls[0]["bilder"]
    uppg = result["exam"]["uppgifter"]
    assert uppg[0]["bild"] == 1 and uppg[1]["bild"] is None
    assert result["underlag"] == und["id"]
    # exam_items speglar bildens sökväg
    conn = appdb.connect(client.base_dir / "transkribera.db")
    row = conn.execute("SELECT bild_path FROM exam_items WHERE nummer='1'").fetchone()
    conn.close()
    assert row["bild_path"].endswith("sida-01.png")


def test_generate_ignores_unknown_underlag(client, monkeypatch):
    calls = _stub_generate(monkeypatch)
    r = client.post("/api/exams/generate",
                    json={"course_id": _course_id(client), "underlag": "feedfeedfeed"})
    result = _done(r)
    assert calls[0]["bilder"] == ""
    assert result["underlag"] is None


# --------------------------------------------------------------- radering --


def _set_tex_path(client, exam_id, path):
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        row = conn.execute("SELECT current_version FROM exams WHERE id = ?",
                           (exam_id,)).fetchone()
        conn.execute("UPDATE exam_versions SET tex_path = ? WHERE id = ?",
                     (str(path), row["current_version"]))
        conn.commit()
    finally:
        conn.close()


def test_delete_exam_removes_rows_and_files(client, monkeypatch):
    result, _ = _make_exam(client, monkeypatch)
    exam_id = result["id"]
    out = client.base_dir / "Transkriberingar" / "prov" / "kurs" / "2026-01-01"
    out.mkdir(parents=True)
    tex = out / "Prov.tex"
    tex.write_text("x", encoding="utf-8")
    bed = out / "Prov - bedomning.tex"
    bed.write_text("x", encoding="utf-8")
    _set_tex_path(client, exam_id, tex)

    r = client.delete(f"/api/exams/{exam_id}")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert not tex.exists() and not bed.exists()
    assert client.get(f"/api/exams/{exam_id}").status_code == 404
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        for tabell in ("exam_versions", "exam_items"):
            n = conn.execute(f"SELECT COUNT(*) FROM {tabell} "
                             "WHERE exam_id = ?", (exam_id,)).fetchone()[0]
            assert n == 0, tabell
        n = conn.execute("SELECT COUNT(*) FROM content_tags WHERE exam_id = ?",
                         (exam_id,)).fetchone()[0]
        assert n == 0
    finally:
        conn.close()


def test_delete_exam_unknown_404(client):
    assert client.delete("/api/exams/99999").status_code == 404


def test_delete_exam_never_touches_files_outside_transkriberingar(client, monkeypatch):
    result, _ = _make_exam(client, monkeypatch)
    exam_id = result["id"]
    utanfor = client.base_dir / "viktig.tex"
    utanfor.write_text("x", encoding="utf-8")
    _set_tex_path(client, exam_id, utanfor)

    r = client.delete(f"/api/exams/{exam_id}")
    assert r.status_code == 200
    assert utanfor.exists()


def test_approve_copies_bilder_and_includes_graphics(client, monkeypatch):
    und = _upload_underlag(client, monkeypatch)
    exam = _exam_doc()
    exam["uppgifter"][0]["bild"] = 1
    _stub_generate(monkeypatch, result={"exam": exam, "errors": [], "rounds": 1})
    r = client.post("/api/exams/generate",
                    json={"course_id": _course_id(client), "underlag": und["id"]})
    exam_id = _done(r)["id"]
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    r2 = client.post(f"/api/exams/{exam_id}/approve", json={})
    result = _done(r2)
    from pathlib import Path
    tex = Path(result["tex"]).read_text(encoding="utf-8")
    assert "\includegraphics" in tex and "bild-01.png" in tex
    assert (Path(result["tex"]).parent / "bild-01.png").exists()
