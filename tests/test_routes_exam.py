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
def client(llm_ready):
    """Allt i den här sviten genererar — arbitern måste svara.
    Basfixturen bor i conftest.py."""
    return llm_ready


def _stub_generate(monkeypatch, result=None):
    calls = []

    def fake(kurs, klass, punkter, *, model, antal=10, tid_min=120,
             delar=True, memory="", teman="", referens="", bilder="",
             utfall="", bok="", profil="prov", grupp=None,
             llm=None, max_rounds=exam_gen.MAX_ROUNDS, log_cb=None, **_kw):
        calls.append({"kurs": kurs, "punkter": punkter, "memory": memory,
                      "teman": teman, "antal": antal, "utfall": utfall,
                      "referens": referens, "bilder": bilder, "profil": profil,
                      # nivåvalet (v25): rutten ska bygga skelettet och skicka
                      # banden — eller inget av dem, när väljaren står i default
                      "skeleton": _kw.get("skeleton"),
                      "niva_mal": _kw.get("niva_mal")})
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
    result, calls = _make_exam(client, monkeypatch, punkter=[punkt["kod"]])
    assert any(punkt["rubrik"] in p for p in calls[0]["punkter"])
    conn = appdb.connect(client.base_dir / "transkribera.db")
    tagged = conn.execute("SELECT content_id FROM content_tags WHERE exam_id = ?",
                          (result["id"],)).fetchall()
    conn.close()
    assert [t["content_id"] for t in tagged] == [punkt["id"]]


def test_generate_409_when_busy(client, monkeypatch):
    monkeypatch.setattr(client.app.state.arbiter, "try_acquire_llm", lambda: None)
    r = client.post("/api/exams/generate", json={"course_id": _course_id(client)})
    assert r.status_code == 409


def test_refine_adds_version(client, monkeypatch):
    result, _ = _make_exam(client, monkeypatch)
    updated = _exam_doc()
    updated["uppgifter"][0]["text"] = "Ny uppgift $x = 2$."
    captured = {}

    def fake_refine(exam, message, *, model, nummer=None, profil="prov",
                    mal=None, bok="", historik=None, llm=None,
                    max_rounds=exam_gen.MAX_ROUNDS, log_cb=None, **_kw):
        captured["message"] = message
        captured["nummer"] = nummer
        captured["mal"] = mal
        return {"exam": updated, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)

    r = client.post(f"/api/exams/{result['id']}/refine",
                    json={"message": "byt uppgift 1", "nummer": 1})
    res = _done(r)
    assert captured == {"message": "byt uppgift 1", "nummer": 1, "mal": None}
    assert len(res["versions"]) == 2
    assert res["exam"]["uppgifter"][0]["text"] == "Ny uppgift $x = 2$."

    # Elementet läraren pekade på — sidhuvudet har inget uppgiftsnummer.
    _done(client.post(f"/api/exams/{result['id']}/refine",
                      json={"message": "skriv om den",
                            "mal": {"namn": "Sidhuvudet", "innehall": "Ma 1c · NA26F"}}))
    assert captured["nummer"] is None
    assert captured["mal"] == {"namn": "Sidhuvudet", "innehall": "Ma 1c · NA26F"}


def test_refine_svaret_bar_vad_som_faktiskt_andrades(client, monkeypatch):
    """Markeringen ska inte längre gissas ur lärarens mening. Servern har båda
    versionerna och säger vilka element som skiljer sig — här: bara uppgift 1,
    fast meningen nämner både «svårare» och «uppgift 3» (som regexpen i plan.js
    hade målat röda)."""
    result, _ = _make_exam(client, monkeypatch)
    updated = _exam_doc()
    updated["uppgifter"][0]["text"] = "Ny uppgift $x = 2$."
    monkeypatch.setattr(exam_gen, "refine_exam",
                        lambda *a, **k: {"exam": updated, "errors": [], "rounds": 1})
    res = _done(client.post(f"/api/exams/{result['id']}/refine",
                            json={"message": "gör uppgift 3 svårare"}))
    assert res["andrade"] == ["uppg1"]


def test_refine_som_inte_andrade_nagot_marker_ingenting(client, monkeypatch):
    """En tom lista är ett svar, inte ett saknat fält: ingenting på pappret ska
    målas rött för syns skull."""
    result, doc = _make_exam(client, monkeypatch)
    monkeypatch.setattr(exam_gen, "refine_exam",
                        lambda exam, *a, **k: {"exam": exam, "errors": [], "rounds": 1})
    res = _done(client.post(f"/api/exams/{result['id']}/refine",
                            json={"message": "gör den svårare"}))
    assert res["andrade"] == []


def test_riktad_omskrivning_slapper_bara_igenom_malet(client, monkeypatch):
    """Hela vägen genom rutten, med den RIKTIGA sammanfogningen: modellen
    skriver om alla uppgifter, servern släpper igenom en. Då blir `andrade`
    ärlig av sig själv — den diffas mot det som faktiskt sparades."""
    result, _ = _make_exam(client, monkeypatch)
    allt_omskrivet = _exam_doc()
    for i, u in enumerate(allt_omskrivet["uppgifter"], start=1):
        u["text"] = f"På pizzerian säljs {i} pizzor. Beräkna intäkten."
        u["losning"] = f"Svaret är {i}."
    allt_omskrivet["titel"] = "Prov — Pizzor"
    monkeypatch.setattr(exam_gen, "_llm_round",
                        lambda *a, **k: copy.deepcopy(allt_omskrivet))

    res = _done(client.post(f"/api/exams/{result['id']}/refine",
                            json={"message": "ta bort deluppgift b)",
                                  "nummer": 4,
                                  "mal": {"el": "uppg4", "namn": "Uppgift 4"}}))
    assert res["andrade"] == ["uppg4"]
    assert res["exam"]["uppgifter"][3]["text"].startswith("På pizzerian")
    assert res["exam"]["titel"] == _exam_doc()["titel"]
    for i, u in enumerate(_exam_doc()["uppgifter"]):
        if i != 3:
            assert res["exam"]["uppgifter"][i] == u


def test_refine_tar_emot_flera_mal_och_en_nummerlista(client, monkeypatch):
    """Flervalet: läraren markerade två uppgifter och skrev EN mening. Rutten
    bär listan och målen vidare — och ett ensamt mål går exakt som förut."""
    result, _ = _make_exam(client, monkeypatch)
    fangat = {}

    def fake_refine(exam, message, *, model, nummer=None, mal=None, malen=None,
                    **_kw):
        fangat["nummer"] = nummer
        fangat["malen"] = malen
        fangat["mal"] = mal
        return {"exam": exam, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)

    malen = [{"el": "uppg3", "namn": "Uppgift 3", "innehall": "Beräkna arean."},
             {"el": "uppg5", "namn": "Uppgift 5", "innehall": "Lös den."}]
    _done(client.post(f"/api/exams/{result['id']}/refine",
                      json={"message": "gör dem kortare", "nummer": [3, 5],
                            "mal": malen[0], "malen": malen}))
    assert fangat["nummer"] == [3, 5]
    assert [m["el"] for m in fangat["malen"]] == ["uppg3", "uppg5"]

    # ETT mål: dagens payload, dagens värden — int och inget `malen`.
    _done(client.post(f"/api/exams/{result['id']}/refine",
                      json={"message": "gör den kortare", "nummer": 3,
                            "mal": malen[0]}))
    assert fangat["nummer"] == 3 and fangat["malen"] is None
    # En lista med ett enda mål är inte heller flerval.
    _done(client.post(f"/api/exams/{result['id']}/refine",
                      json={"message": "gör den kortare", "nummer": [3],
                            "malen": [malen[0]]}))
    assert fangat["nummer"] == 3 and fangat["malen"] is None


def test_refine_tal_skrap_i_nummer_och_malen(client, monkeypatch):
    """Ett rått int() på klientens värde blev en 500. Silen släpper igenom det
    som är nummer och mål, och struntar i resten."""
    result, _ = _make_exam(client, monkeypatch)
    fangat = {}

    def fake_refine(exam, message, *, model, nummer=None, malen=None, **_kw):
        fangat["nummer"] = nummer
        fangat["malen"] = malen
        return {"exam": exam, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)

    _done(client.post(f"/api/exams/{result['id']}/refine",
                      json={"message": "x", "nummer": "abc",
                            "malen": "inte en lista"}))
    assert fangat["nummer"] is None and fangat["malen"] is None
    _done(client.post(f"/api/exams/{result['id']}/refine",
                      json={"message": "x", "nummer": [4, "5", 0, 4],
                            "malen": [{"el": f"uppg{i}"} for i in range(1, 9)]}))
    assert fangat["nummer"] == [4, 5]
    assert len(fangat["malen"]) == 6           # taket, se llm_client.MAX_MALEN


def test_flervalet_slapper_igenom_bada_uppgifterna_genom_rutten(client,
                                                                monkeypatch):
    """Hela vägen med den RIKTIGA sammanfogningen: modellen skriver om allt,
    servern släpper igenom de två uppgifterna läraren pekade på."""
    result, _ = _make_exam(client, monkeypatch)
    allt_omskrivet = _exam_doc()
    for i, u in enumerate(allt_omskrivet["uppgifter"], start=1):
        u["text"] = f"På pizzerian säljs {i} pizzor. Beräkna intäkten."
        u["losning"] = f"Svaret är {i}."
    allt_omskrivet["uppgifter"][5]["text"] = "Ett tåg kör i 80 km/h i 45 min."
    allt_omskrivet["uppgifter"][5]["losning"] = "60 km."
    allt_omskrivet["titel"] = "Prov — Pizzor"
    monkeypatch.setattr(exam_gen, "_llm_round",
                        lambda *a, **k: copy.deepcopy(allt_omskrivet))

    res = _done(client.post(
        f"/api/exams/{result['id']}/refine",
        json={"message": "byt sammanhang i båda", "nummer": [4, 6],
              "malen": [{"el": "uppg4", "namn": "Uppgift 4"},
                        {"el": "uppg6", "namn": "Uppgift 6"}]}))
    assert res["andrade"] == ["uppg4", "uppg6"]
    assert res["exam"]["titel"] == _exam_doc()["titel"]
    for i, u in enumerate(_exam_doc()["uppgifter"]):
        if i not in (3, 5):
            assert res["exam"]["uppgifter"][i] == u


def test_refine_requires_message(client, monkeypatch):
    result, _ = _make_exam(client, monkeypatch)
    assert client.post(f"/api/exams/{result['id']}/refine",
                       json={"message": " "}).status_code == 400
    assert client.post("/api/exams/999/refine",
                       json={"message": "x"}).status_code == 404


def test_pappret_bar_lararens_datum_inte_modellens(client, monkeypatch):
    """Modellen fyller i `datum` — fältet står i INSTRUCTION:s lista utan
    källa — och skrev den dag den råkade köra. Lärarens dag ligger i
    exams.datum, ur planeringens väljare. Skärmen läste kolumnen och PDF:en
    läste JSON:en, så en gruppuppgift till den 20:e trycktes med den 19:e i
    huvudet. Kolumnen vinner, i dokumentet och därmed på pappret."""
    modellens = _exam_doc() | {"datum": "2026-08-19"}
    monkeypatch.setattr(exam_gen, "generate_exam",
                        lambda *a, **kw: {"exam": copy.deepcopy(modellens),
                                          "errors": [], "rounds": 1})
    r = client.post("/api/exams/generate",
                    json={"course_id": _course_id(client), "antal": 6,
                          "datum": "2026-08-20"})
    result = _done(r)
    assert result["exam"]["datum"] == "2026-08-20"

    # Och pappret: den lagrade JSON:en kan bära modellens dag sedan tidigare
    # (alla dokument i basen gör det), så renderingen stämplar om den också.
    conn = appdb.connect(client.base_dir / "transkribera.db")
    appdb.add_exam_version(conn, result["id"], copy.deepcopy(modellens))
    conn.close()
    sedda = {}

    def fake_compile(tex, out_dir, jobname, **kw):
        sedda.setdefault(jobname, tex)
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{jobname}.pdf"
        p.write_bytes(b"%PDF-1.5 fejk")
        return p, ""
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)
    monkeypatch.setattr(exam_pdf, "compile_pdf", fake_compile)
    _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    prov = next(t for n, t in sedda.items() if "bedomning" not in n)
    assert "2026-08-20" in prov and "2026-08-19" not in prov


def test_pappret_bar_lararens_provtid_aven_nar_modellen_teg(client, monkeypatch):
    """`tid_min` är VALFRITT i schemat (exam_spec.ExamDoc), och rutten satte
    lärarens minuter bara om modellen råkat fylla i fältet. Teg modellen föll
    minuterna bort: prov.tex.j2 utelämnar Provtid-raden på försättsbladet
    medan skärmen (blad.js) stod och sa «90 minuter, kl. …». Samma regel som
    lärarens datum — kolumnen vinner, ovillkorligt."""
    tyst = {k: v for k, v in _exam_doc().items() if k != "tid_min"}
    monkeypatch.setattr(exam_gen, "generate_exam",
                        lambda *a, **kw: {"exam": copy.deepcopy(tyst),
                                          "errors": [], "rounds": 1})
    result = _done(client.post("/api/exams/generate",
                               json={"course_id": _course_id(client),
                                     "antal": 6, "tid_min": 90}))
    assert result["exam"]["tid_min"] == 90

    # Och lärarens tal vinner även när modellen skrev ett eget.
    monkeypatch.setattr(exam_gen, "generate_exam",
                        lambda *a, **kw: {"exam": _exam_doc() | {"tid_min": 45},
                                          "errors": [], "rounds": 1})
    andra = _done(client.post("/api/exams/generate",
                              json={"course_id": _course_id(client),
                                    "antal": 6, "tid_min": 90}))
    assert andra["exam"]["tid_min"] == 90

    # Hela vägen ut på pappret: Provtid-raden ska stå där.
    sedda = {}

    def fake_compile(tex, out_dir, jobname, **kw):
        sedda.setdefault(jobname, tex)
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{jobname}.pdf"
        p.write_bytes(b"%PDF-1.5 fejk")
        return p, ""
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)
    monkeypatch.setattr(exam_pdf, "compile_pdf", fake_compile)
    _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    prov = next(t for n, t in sedda.items() if "bedomning" not in n)
    assert "Provtid" in prov and "90 minuter" in prov


def test_utan_valt_datum_bar_pappret_inget(client, monkeypatch):
    """Ingen dag vald → ingen dag på pappret. Ett hittepådatum i huvudet är
    värre än inget: det är det eleverna skriver av."""
    monkeypatch.setattr(
        exam_gen, "generate_exam",
        lambda *a, **kw: {"exam": _exam_doc() | {"datum": "2026-08-19"},
                          "errors": [], "rounds": 1})
    result = _done(client.post("/api/exams/generate",
                               json={"course_id": _course_id(client), "antal": 6}))
    assert result["exam"]["datum"] is None


# ── Det som trycks är det läraren SER ──────────────────────────────────────
#
# Utkastets ångra-markör (dokument.markor) och provets versionspekare
# (exams.current_version) var två historier utan koppling. Läraren ångrade ett
# dåligt omskrivningsvarv: skärmen backade till byggställningarna, medan
# pekaren stod kvar på det förkastade pizzavarvet. Godkännandet läser pekaren —
# PDF:en trycktes ur varvet hon just kastat, och pekaren fick rättas för hand.

def _varv(client, monkeypatch, exam_id, text):
    """Ett omskrivningsvarv. Returnerar exam-versionen varvet gav."""
    ny = _exam_doc()
    ny["uppgifter"][0]["text"] = text
    monkeypatch.setattr(exam_gen, "refine_exam",
                        lambda *a, **k: {"exam": ny, "errors": [], "rounds": 1})
    res = _done(client.post(f"/api/exams/{exam_id}/refine",
                            json={"message": text}))
    return res["current_version"]


def _fangar_tex(monkeypatch):
    sedda = {}

    def fake_compile(tex, out_dir, jobname, **kw):
        sedda.setdefault(jobname, tex)
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{jobname}.pdf"
        p.write_bytes(b"%PDF-1.5 fejk")
        return p, ""
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)
    monkeypatch.setattr(exam_pdf, "compile_pdf", fake_compile)
    return sedda


def test_godkannandet_trycker_varvet_lararen_ser(client, monkeypatch):
    """Två varv, ångra, godkänn: PDF:en byggs ur FÖRSTA varvet."""
    result, _ = _make_exam(client, monkeypatch)
    forsta = _varv(client, monkeypatch, result["id"], "Byggställningens höjd.")
    andra = _varv(client, monkeypatch, result["id"], "Pizzerians intäkt.")
    assert forsta != andra

    sedda = _fangar_tex(monkeypatch)
    # Ångra: klienten visar första varvet igen och säger vilken version det var.
    _done(client.post(f"/api/exams/{result['id']}/approve",
                      json={"version": forsta}))
    prov = next(t for n, t in sedda.items() if "bedomning" not in n)
    assert "Byggställningens" in prov
    assert "Pizzerians" not in prov


def test_omskrivningen_bygger_vidare_pa_varvet_lararen_ser(client, monkeypatch):
    """Samma hål på andra sidan: ett önskemål EFTER en ångring byggde vidare på
    det varv läraren kastade."""
    result, _ = _make_exam(client, monkeypatch)
    forsta = _varv(client, monkeypatch, result["id"], "Byggställningens höjd.")
    _varv(client, monkeypatch, result["id"], "Pizzerians intäkt.")

    sett = {}

    def fake_refine(exam, message, *a, **k):
        sett["text"] = exam["uppgifter"][0]["text"]
        return {"exam": exam, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)
    _done(client.post(f"/api/exams/{result['id']}/refine",
                      json={"message": "gör den kortare", "version": forsta}))
    assert sett["text"] == "Byggställningens höjd."


def test_utan_version_star_pekaren_kvar(client, monkeypatch):
    """Äldre utkast bär ingen version — då gäller senaste varvet som förut."""
    result, _ = _make_exam(client, monkeypatch)
    _varv(client, monkeypatch, result["id"], "Byggställningens höjd.")
    _varv(client, monkeypatch, result["id"], "Pizzerians intäkt.")
    sedda = _fangar_tex(monkeypatch)
    _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    prov = next(t for n, t in sedda.items() if "bedomning" not in n)
    assert "Pizzerians" in prov


def test_ett_annat_provs_version_flyttar_ingenting(client, monkeypatch):
    """Versionsnumret kommer från klienten. Ett prov ska inte gå att peka på
    ett annat provs text."""
    ett, _ = _make_exam(client, monkeypatch)
    tva, _ = _make_exam(client, monkeypatch)
    frammande = _varv(client, monkeypatch, tva["id"], "Ett annat provs text.")
    egen = _varv(client, monkeypatch, ett["id"], "Byggställningens höjd.")

    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        assert appdb.set_current_exam_version(conn, ett["id"], frammande) is None
        vy = appdb.get_exam(conn, ett["id"])
        assert vy["current_version"] == egen
    finally:
        conn.close()


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


def test_approve_svaret_bar_falten_plan_js_laser(client, monkeypatch):
    """Kontraktet mellan rutten och klienten, läst ur BÅDA ändarna.

    Rutten lägger sökvägarna i `pdf` och `tex`; plan.js läste `pdf_path` —
    DB-kolumnens namn, som aldrig finns i svaret. Det syntes ingenstans:
    `godkant.pdf` blev alltid null, dokumentet i Sparat fick aldrig sin
    PDF-sökväg, och toasten sa «PDF:en gick inte att bygga» om varje prov som
    kompilerat felfritt. Rutt-testerna såg det inte (de läser svaret, inte
    klienten) och e2e-testerna inte heller (mockarna hittade på svaret).

    Därför läses fältnamnen HÄR ur plan.js och krävs finnas i det svar rutten
    faktiskt skickar. Byter någon ände namn faller det här testet."""
    import re
    from pathlib import Path

    result, _ = _make_exam(client, monkeypatch, datum="2026-10-05")
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)

    def fake_compile(tex, out_dir, jobname, **kw):
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{jobname}.pdf"
        p.write_bytes(b"%PDF-1.5 fejk")
        return p, ""
    monkeypatch.setattr(exam_pdf, "compile_pdf", fake_compile)

    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    assert res["pdf"] and res["tex"]

    js = (Path(routes_exam.__file__).parent / "ui" / "plan.js"
          ).read_text(encoding="utf-8")
    start = js.index("/api/exams/${godkant.provId}/approve")
    # Blocket är .then-hanteraren; .catch efter den läser felet, inte svaret.
    block = js[start:js.index(".catch(", start)]
    kod = re.sub(r"/\*.*?\*/", "", block, flags=re.S)   # kommentarer ljuger inte
    lasta = set(re.findall(r"\br\.(\w+)", kod))
    assert "pdf" in lasta, kod
    saknas = sorted(lasta - set(res))
    assert not saknas, f"plan.js läser fält som approve-svaret inte har: {saknas}"


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


def test_approve_ger_upp_efter_tva_fixrundor(client, monkeypatch):
    """Reparationsloopens tak. En modell som skriver trasig LaTeX om och om
    igen får inte hålla läraren kvar i en väntan utan slut — och varje runda
    är ett betalt anrop. Taket är MAX_LATEX_ROUNDS, och när det är nått ska
    felet SÄGAS, med .tex-filen kvar att öppna."""
    result, _ = _make_exam(client, monkeypatch)
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)
    monkeypatch.setattr(exam_pdf, "compile_pdf",
                        lambda *a, **k: (None, "! Missing $ inserted."))

    rundor = {"n": 0}

    def rakna(exam, log, **kw):
        rundor["n"] += 1
        # Modellen «rättar» men skriver lika trasig LaTeX varje gång.
        return {"exam": exam, "errors": [], "rounds": rundor["n"]}
    monkeypatch.setattr(exam_gen, "fix_latex", rakna)

    r = client.post(f"/api/exams/{result['id']}/approve", json={})
    res = _done(r)
    assert rundor["n"] == exam_gen.MAX_LATEX_ROUNDS,         f"{rundor['n']} fixrundor — taket är {exam_gen.MAX_LATEX_ROUNDS}"
    assert any(e["code"] == "kompilering" for e in res["errors"])
    assert res["pdf"] is None
    assert res["tex"], "källan ska ligga kvar att öppna"


def test_approve_slutar_fixa_nar_provet_kompilerar(client, monkeypatch):
    """Andra sidan av taket: går det igenom i andra rundan ska det inte bli
    en tredje."""
    result, _ = _make_exam(client, monkeypatch)
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)
    forsok = {"n": 0}

    def fake_compile(tex, out_dir, jobname, **kw):
        forsok["n"] += 1
        if forsok["n"] == 1:
            return None, "! Missing $ inserted."
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{jobname}.pdf"
        p.write_bytes(b"%PDF-1.5 fejk")
        return p, ""
    monkeypatch.setattr(exam_pdf, "compile_pdf", fake_compile)

    rundor = {"n": 0}

    def rakna(exam, log, **kw):
        rundor["n"] += 1
        return {"exam": exam, "errors": [], "rounds": rundor["n"]}
    monkeypatch.setattr(exam_gen, "fix_latex", rakna)

    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    assert rundor["n"] == 1
    assert res["pdf"] and res["errors"] == []


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
    # Fynd 5 (granskning): bed_loggar har tre poster (två omförsök + den
    # sista, uppgivna) — bara [-1] pinnades tidigare. En implementation som
    # ALLTID skickade den uppgivna varianten hade ändå passerat oupptäckt.
    # Pinna även att en icke-sista runda faktiskt lovar ett omförsök.
    assert bed_loggar[:-1] == ["Bedömningsanvisningen gick inte att "
                               "kompilera — försöker korrigera …"] * 2


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


# ------------------------------------- Etapp 2: lösningsbladets egen fil --
# Lösningsbladet i dokumenthögen är en KLON av sitt original och bär samma id.
# «Ladda ner PDF» på det gav därför provet självt: knappen kunde inte skilja
# dem åt, för det fanns ingen annan fil att peka på. Bedömningsanvisningen
# kompilerades redan bredvid provet men hade ingen rutt; arbetsbladets facit
# fanns bara som sista sida i bladet.

def _bygger_varje_dokument(monkeypatch):
    """Motorn stubbad så att VARJE jobname lämnar en fil — annars uppstår
    systerdokumenten aldrig och testet mäter stubben, inte rutten."""
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)

    def fake_compile(tex, out_dir, jobname, **kw):
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{jobname}.pdf"
        p.write_bytes(b"%PDF-1.5 " + jobname.encode("utf-8"))
        return p, ""
    monkeypatch.setattr(exam_pdf, "compile_pdf", fake_compile)


def _arbetsblad(client, monkeypatch, **extra):
    _stub_generate(monkeypatch)
    return _done(client.post("/api/exams/generate", json={
        "course_id": _course_id(client), "typ": "arbetsblad",
        "datum": "2026-10-05", **extra}))


def test_provets_losningsforslag_har_en_egen_rutt(client, monkeypatch):
    result, _ = _make_exam(client, monkeypatch, datum="2026-10-05")
    _bygger_varje_dokument(monkeypatch)
    _done(client.post(f"/api/exams/{result['id']}/approve", json={}))

    r = client.get(f"/api/exams/{result['id']}/bedomning")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert b"bedomning" in r.content
    assert "bedomning" in r.headers.get("content-disposition", "")
    # Och provets egen rutt ger fortfarande PROVET — det var buggen.
    assert b"bedomning" not in client.get(f"/api/exams/{result['id']}/pdf").content
    # «Lösningar» är en EGEN rutt sedan skärmversionen kom. Här finns ingen
    # avritning (godkännandet skickade inga blad), så den ger anvisningen —
    # reserven, och samma papper som förut.
    los = client.get(f"/api/exams/{result['id']}/losningar")
    assert los.status_code == 200 and b"bedomning" in los.content


def test_bedomning_utan_byggd_pdf_ger_provets_besked(client, monkeypatch):
    result, _ = _make_exam(client, monkeypatch, datum="2026-10-05")
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    r = client.get(f"/api/exams/{result['id']}/bedomning")
    assert r.status_code == 404 and "godkänn provet" in r.json()["error"]
    assert client.get("/api/exams/99999/bedomning").status_code == 404
    assert client.get("/api/exams/99999/facit").status_code == 404


def test_bedomning_som_saknas_bredvid_provet_sags_pa_svenska(client, monkeypatch):
    """Provet kompilerade, anvisningen inte. Beskedet ska säga just det —
    inte «okänt prov» och inte serverns engelska LaTeX-logg.

    Och lösningsrutten faller på samma sak: dess reserv ÄR anvisningen (se
    tryck.losningar_bredvid), så utan avritning och utan anvisning finns
    ingenting att ge."""
    from pathlib import Path
    result, _ = _make_exam(client, monkeypatch, datum="2026-10-05")
    _bygger_varje_dokument(monkeypatch)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    pdf = Path(res["pdf"])
    pdf.with_name(f"{pdf.stem} - bedomning{pdf.suffix}").unlink()
    r = client.get(f"/api/exams/{result['id']}/bedomning")
    assert r.status_code == 404
    assert r.json()["error"].startswith("Bedömningsanvisningen är inte byggd")
    los = client.get(f"/api/exams/{result['id']}/losningar")
    assert los.status_code == 404
    assert los.json()["error"].startswith("Lösningsförslaget är inte byggt")


def test_arbetsbladets_separata_facit_byggs_och_serveras(client, monkeypatch):
    from pathlib import Path
    result = _arbetsblad(client, monkeypatch)
    _bygger_varje_dokument(monkeypatch)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    ut = Path(res["pdf"]).parent
    assert list(ut.glob("* - facit.pdf")), sorted(p.name for p in ut.iterdir())
    # Källan ligger bredvid som provets — ett papper ska gå att sätta för hand.
    assert list(ut.glob("* - facit.tex"))
    r = client.get(f"/api/exams/{result['id']}/facit")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert b"facit" in r.content


def test_facitfilen_ar_facit_ensamt_inte_hela_bladet(client, monkeypatch):
    """Kontraktet mot mallen: filen bär facitbandet och lösningarna men inte
    uppgifterna. Ett «separat facit» som ändå har elevernas ark i sig är inte
    ett facit, det är ett andra exemplar av bladet."""
    from pathlib import Path
    result = _arbetsblad(client, monkeypatch)
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    # Bara kroppen jämförs: preamblen DEFINIERAR \svarsrad i båda filerna,
    # och det är användningen som skiljer dem åt.
    kropp = lambda t: t.split(r"\begin{document}", 1)[1]
    blad = kropp(Path(res["tex"]).read_text(encoding="utf-8"))
    facit = kropp(next(Path(res["tex"]).parent.glob("* - facit.tex")
                       ).read_text(encoding="utf-8"))
    assert r"\delprovband{Facit}" in facit
    assert r"{\large Facit" in facit and r"{\large Arbetsblad" in blad
    # Elevernas del är släckt: instruktionsraden, sidbrytningen och
    # svarsutrymmet hör till bladet, inte till lärarens lösningar.
    assert "Öva i egen takt" in blad and "Öva i egen takt" not in facit
    assert r"\newpage" in blad and r"\newpage" not in facit
    assert r"\svarsrad" in blad and r"\svarsrad" not in facit
    # …men lösningarna är kvar, ordagrant desamma som på bladets sista sida.
    from app import exam_latex
    for u in _exam_doc()["uppgifter"]:
        satt = exam_latex.escape_mixed(u["losning"])
        assert satt in blad and satt in facit, satt


def test_separat_facit_slacker_bandet_i_elevbladet(client, monkeypatch):
    """«Separat facit» valt i planeringen: elevbladet ska INTE bära facit på
    sista sidan — annars får eleverna lösningarna dubbelt (i bladet OCH i
    facit-PDF:en bredvid). Valet bor i webbläsarens dokument och reser med
    approve-anropet som `separat_facit`."""
    from pathlib import Path
    from app import exam_latex
    result = _arbetsblad(client, monkeypatch)
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)
    res = _done(client.post(f"/api/exams/{result['id']}/approve",
                            json={"separat_facit": True}))
    kropp = lambda t: t.split(r"\begin{document}", 1)[1]
    blad = kropp(Path(res["tex"]).read_text(encoding="utf-8"))
    assert r"\delprovband{Facit}" not in blad
    # Instruktionsraden lovar inte längre något som inte finns i bladet.
    assert "sista sidan" not in blad and "delas ut separat" in blad
    for u in _exam_doc()["uppgifter"]:
        assert exam_latex.escape_mixed(u["losning"]) not in blad
    # …och lösningarna finns kvar — men BARA i det separata facit-bladet.
    facit = kropp(next(Path(res["tex"]).parent.glob("* - facit.tex")
                       ).read_text(encoding="utf-8"))
    assert r"\delprovband{Facit}" in facit
    for u in _exam_doc()["uppgifter"]:
        assert exam_latex.escape_mixed(u["losning"]) in facit


def test_plan_js_skickar_separat_facit_med_approve():
    """Flaggan finns bara om frontenden skickar den: valet bor i webbläsarens
    dokument (inst.facit) och står inte i provets JSON. Utan den här raden i
    plan.js är serverflaggan död kod och bladet bär facit igen.

    Kontraktet är negativt: bandet trycks BARA för «Facit i bladet». Både
    «Separat facit» och «Inget facit» reser flaggan — annars fick ett blad
    läraren bad ha inget facit ändå lösningarna, fast bara i LaTeX-reserven."""
    import re
    from pathlib import Path
    js = (Path(routes_exam.__file__).parent / "ui" / "plan.js"
          ).read_text(encoding="utf-8")
    start = js.index("/api/exams/${godkant.provId}/approve")
    kod = re.sub(r"/\*.*?\*/", "", js[start:js.index(".then(", start)], flags=re.S)
    assert "separat_facit" in kod, kod
    assert "!== 'Facit i bladet'" in kod, kod


def test_provet_far_inget_separat_facit(client, monkeypatch):
    """Provet har sin bedömningsanvisning. Ett facit bredvid vore ett tredje
    papper som säger samma sak, och läraren skulle få välja mellan dem."""
    from pathlib import Path
    result, _ = _make_exam(client, monkeypatch, datum="2026-10-05")
    _bygger_varje_dokument(monkeypatch)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    assert not list(Path(res["pdf"]).parent.glob("* - facit.pdf"))
    assert client.get(f"/api/exams/{result['id']}/facit").status_code == 404


def test_ett_blad_som_kompilerat_falls_inte_av_sitt_eget_facit(client, monkeypatch):
    """Facit gatear INTE godkännandet, till skillnad från bedömningen: dess
    innehåll är exakt det som just kompilerat på bladets sista sida, så ett
    fel där kan inte vara ett fel i uppgifterna."""
    result = _arbetsblad(client, monkeypatch)
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)

    def fake_compile(tex, out_dir, jobname, **kw):
        if jobname.endswith(" - facit"):
            return None, "! Undefined control sequence."
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{jobname}.pdf"
        p.write_bytes(b"%PDF-1.5 fejk")
        return p, ""
    monkeypatch.setattr(exam_pdf, "compile_pdf", fake_compile)

    r = client.post(f"/api/exams/{result['id']}/approve", json={})
    res = _done(r)
    assert res["status"] == "godkänt" and res["pdf"] and res["errors"] == []
    # Men det SÄGS — ett papper som tyst inte blev byggt är just det som
    # upptäcks framför kopiatorn.
    assert any("separata facit" in e.get("msg", "")
               for e in _events(r) if e["type"] == "log")
    assert client.get(f"/api/exams/{result['id']}/facit").status_code == 404


@pytest.mark.tectonic
def test_arbetsbladets_facit_kompilerar_och_bar_bara_losningarna(client, monkeypatch):
    """Skarp körning: riktig Tectonic, riktig cache, samma väg som lärarens
    maskin — och sedan läses PDF:en. Strängtesterna ovan kan inte se det som
    faktiskt avgör: att pappret läraren delar ut bär lösningarna och INTE
    uppgifterna. En mall cachen aldrig sett kraschar dessutom tyst första
    gången ett papper av den sorten godkänns, och det syns bara här."""
    from pathlib import Path

    from tests.test_pdf_kontrakt import text_ur

    result = _arbetsblad(client, monkeypatch)
    res = _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    assert res["pdf"], res["errors"]
    blad = Path(res["pdf"])
    facit = blad.with_name(f"{blad.stem} - facit{blad.suffix}")
    assert facit.is_file()

    r = client.get(f"/api/exams/{result['id']}/facit")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")

    text = text_ur(facit)
    assert "Facit" in text
    for u in _exam_doc()["uppgifter"]:
        stam = u["text"].split("$")[0].strip()
        if len(stam) > 12:                    # en stam som går att söka efter
            assert stam not in text, stam
    # Lösningarna är kvar — det är hela pappret.
    assert "Kravgränser" not in text


def test_systerdokumenten_lyder_provets_sokvagssparr(client, monkeypatch):
    """Sökvägen ärvs ur pdf_path och prövas där. En pdf_path utanför basen
    får inte gå att nå via en systerrutt heller — den vore annars en väg runt
    spärren snarare än en väg till ett papper."""
    result, _ = _make_exam(client, monkeypatch)
    utanfor = client.base_dir.parent / "utanfor.pdf"
    utanfor.write_bytes(b"%PDF-1.5 utanfor basen")
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        row = conn.execute("SELECT current_version FROM exams WHERE id = ?",
                           (result["id"],)).fetchone()
        conn.execute("UPDATE exam_versions SET pdf_path = ? WHERE id = ?",
                     (str(utanfor), row["current_version"]))
        conn.commit()
    finally:
        conn.close()
    for vag in ("pdf", "bedomning", "facit"):
        assert client.get(f"/api/exams/{result['id']}/{vag}").status_code == 403, vag


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
    assert "HELT NYA" in calls[0]["referens"]
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
    result, _ = _make_exam(client, monkeypatch, punkter=[punkt["kod"]])
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
                        lambda spec=None: "claude-code")
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
    # Arbetsbladets separata facit ligger bredvid med samma regel — lämnas det
    # kvar blir det en föräldralös fil i en katalog läraren själv öppnar.
    facit = out / "Prov - facit.tex"
    facit.write_text("x", encoding="utf-8")
    _set_tex_path(client, exam_id, tex)

    r = client.delete(f"/api/exams/{exam_id}")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert not tex.exists() and not bed.exists() and not facit.exists()
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
    assert r"\includegraphics" in tex and "bild-01.png" in tex
    assert (Path(result["tex"]).parent / "bild-01.png").exists()


def test_provet_gar_att_andra_efter_en_omstart(client, monkeypatch):
    """Provet har bott i databasen sedan v5 och ska därför tåla en omstart —
    samma sak som tavlan fick i v20. Läraren som skriver halvt på kvällen ska
    kunna ändra vidare på morgonen."""
    from fastapi.testclient import TestClient
    result, _ = _make_exam(client, monkeypatch)
    ny = TestClient(server.create_app(base_dir=client.base_dir))
    monkeypatch.setattr(ny.app.state.arbiter, "ensure_llm",
                        lambda: "http://127.0.0.1:8170")

    uppdaterad = _exam_doc()
    uppdaterad["uppgifter"][0]["text"] = "Efter omstarten."
    sett = {}

    def fake_refine(exam, message, *, model, nummer=None, profil="prov",
                    mal=None, bok="", historik=None, llm=None,
                    max_rounds=exam_gen.MAX_ROUNDS, log_cb=None, **_kw):
        sett["uppgifter"] = len(exam.get("uppgifter") or [])
        return {"exam": uppdaterad, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)

    r = ny.post(f"/api/exams/{result['id']}/refine",
                json={"message": "skriv om den", "nummer": 1})
    assert r.status_code == 200
    assert _done(r)["exam"]["uppgifter"][0]["text"] == "Efter omstarten."
    # Och provet som skickades in var det som låg i databasen, inte ett tomt.
    assert sett["uppgifter"] == len(_exam_doc()["uppgifter"])


def test_refine_far_varvhistoriken_och_skarmtexten(client, monkeypatch):
    """Samma sammanhang som tavlan får: vad läraren redan bett om, och hur
    rutan ser ut på skärmen (KaTeX skriver sin källa en gång till)."""
    result, _ = _make_exam(client, monkeypatch)
    sett = {}

    def fake_refine(exam, message, *, model, nummer=None, profil="prov",
                    mal=None, bok="", historik=None, **kw):
        sett["historik"] = historik
        sett["mal"] = mal
        return {"exam": _exam_doc(), "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)

    _done(client.post(f"/api/exams/{result['id']}/refine", json={
        "message": "ännu kortare",
        "historik": ["Gör uppgift 1 kortare"],
        "mal": {"namn": "Uppgift 1", "innehall": "$x=2$",
                "renderat": "x=2 x=2"}}))
    assert sett["historik"] == ["Gör uppgift 1 kortare"]
    assert sett["mal"]["renderat"] == "x=2 x=2"


# ══════════ NÄR TVÅ SAKER SKER SAMTIDIGT ══════════
#
# Rutterna prövades förr en i taget, i tur och ordning — och det är inte så en
# lärare använder appen. Hon godkänner ett prov och skickar en sista ändring i
# samma andetag; hon har appen öppen i två flikar; hon stänger locket mitt i ett
# varv. Testerna nedan är de lägena.


def _kompilerar(monkeypatch, *, innan_kompilering=None):
    """PDF-motorn, fejkad. `innan_kompilering` körs FÖRE varje kompilering —
    där ställer sig ett varv från en annan flik i vägen."""
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: True)

    def fake_compile(tex, out_dir, jobname, **kw):
        if innan_kompilering:
            innan_kompilering()
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{jobname}.pdf"
        p.write_bytes(b"%PDF-1.5 fejk")
        return p, ""
    monkeypatch.setattr(exam_pdf, "compile_pdf", fake_compile)


def _versioner(client, exam_id):
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        return [dict(r) for r in conn.execute(
            "SELECT id, version, tex_path, pdf_path FROM exam_versions "
            "WHERE exam_id = ? ORDER BY version", (exam_id,)).fetchall()]
    finally:
        conn.close()


def test_refine_pa_godkant_papper_ger_409(client, monkeypatch):
    """Ett refine-svar som landade EFTER godkännandet la en ny version, flyttade
    pekaren dit — och den versionen har ingen PDF. «Ladda ner PDF» sa då «ingen
    pdf ännu, godkänn provet» om ett prov som låg utskrivet på skärmen. Godkänt
    är låst, och nejet säger vägen tillbaka."""
    result, _ = _make_exam(client, monkeypatch)
    _kompilerar(monkeypatch)
    _done(client.post(f"/api/exams/{result['id']}/approve", json={}))

    monkeypatch.setattr(exam_gen, "refine_exam",
                        lambda exam, *a, **k: {"exam": _exam_doc(),
                                               "errors": [], "rounds": 1})
    r = client.post(f"/api/exams/{result['id']}/refine",
                    json={"message": "gör den kortare"})
    assert r.status_code == 409
    assert "låst" in r.json()["error"] and "Fortsätt ändra" in r.json()["error"]
    # Och ingen ny version smög in: pekaren står kvar på det som trycktes.
    assert len(_versioner(client, result["id"])) == 1
    assert client.get(f"/api/exams/{result['id']}/pdf").status_code == 200


def test_oppna_lagger_tillbaka_pappret_som_utkast(client, monkeypatch):
    """Efter godkännandet fanns ingen väg tillbaka — «Bygg vidare» startade en
    ny körning, alltså ett nytt papper och en ny nota, när det läraren ville var
    att rätta en siffra i uppgift 3."""
    result, _ = _make_exam(client, monkeypatch)
    _kompilerar(monkeypatch)
    _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    assert client.get(f"/api/exams/{result['id']}").json()["status"] == "godkänt"

    r = client.post(f"/api/exams/{result['id']}/oppna")
    assert r.status_code == 200 and r.json()["status"] == "utkast"
    # Artefakterna ligger kvar: en ångrad omöppning ska inte kosta en
    # kompilering till.
    assert _versioner(client, result["id"])[0]["pdf_path"]
    # Och nu går pappret att skriva om igen.
    ny = _exam_doc()
    ny["uppgifter"][0]["text"] = "Rättad uppgift $x = 3$."
    monkeypatch.setattr(exam_gen, "refine_exam",
                        lambda *a, **k: {"exam": ny, "errors": [], "rounds": 1})
    res = _done(client.post(f"/api/exams/{result['id']}/refine",
                            json={"message": "rätta siffran"}))
    assert res["exam"]["uppgifter"][0]["text"] == "Rättad uppgift $x = 3$."
    assert client.post("/api/exams/99999/oppna").status_code == 404


def test_pdf_hittas_aven_nar_pekaren_gatt_vidare(client, monkeypatch):
    """Filen som SENAST byggdes är svaret när pekaren står på ett varv utan
    artefakter — att låta pappret försvinna för att pekaren gått vidare är inte
    försiktighet, det är att tappa bort det."""
    from pathlib import Path

    result, _ = _make_exam(client, monkeypatch)
    _kompilerar(monkeypatch)
    _done(client.post(f"/api/exams/{result['id']}/approve", json={}))
    tryckt = _versioner(client, result["id"])[0]

    # Ett varv som lades till efteråt — pekaren står nu på en version utan
    # pdf_path.
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        appdb.add_exam_version(conn, result["id"],
                               _exam_doc() | {"titel": "Efter"})
    finally:
        conn.close()
    vs = _versioner(client, result["id"])
    assert len(vs) == 2 and not vs[1]["pdf_path"]

    r = client.get(f"/api/exams/{result['id']}/pdf")
    assert r.status_code == 200
    from urllib.parse import quote
    assert quote(Path(tryckt["pdf_path"]).name) \
        in r.headers["content-disposition"]


def test_artefakterna_skrivs_pa_varvet_som_renderades(client, monkeypatch):
    """Godkännandet renderar det dokument handlern läste, men sökvägarna slogs
    upp mot pekaren NÄR kompileringen var klar. Hann ett refine i en annan flik
    flytta pekaren under tiden hamnade .tex/.pdf på ett varv de inte hörde till:
    filen på disk var ett annat papper än det databasen pekade ut."""
    result, _ = _make_exam(client, monkeypatch)
    trycktes = result["current_version"]
    smugit = {}

    def annan_flik():
        if smugit:
            return
        conn = appdb.connect(client.base_dir / "transkribera.db")
        try:
            vy = appdb.add_exam_version(
                conn, result["id"], _exam_doc() | {"titel": "Ett annat varv"})
        finally:
            conn.close()
        smugit["version"] = vy["current_version"]

    _kompilerar(monkeypatch, innan_kompilering=annan_flik)
    _done(client.post(f"/api/exams/{result['id']}/approve", json={}))

    vs = {v["id"]: v for v in _versioner(client, result["id"])}
    assert vs[trycktes]["pdf_path"] and vs[trycktes]["tex_path"]
    assert not vs[smugit["version"]]["pdf_path"]
    # Och läraren kommer ändå åt filen (fallbacken ovan).
    assert client.get(f"/api/exams/{result['id']}/pdf").status_code == 200


def test_tva_varv_pa_samma_papper_ger_409(client, monkeypatch):
    """Två samtidiga omskrivningar läste båda dokumentet innan någon sparat,
    byggde ur samma text, och den som kom sist vann — den förstas ändring fanns
    sedan varken på pappret eller i ångra-historiken."""
    import threading

    result, _ = _make_exam(client, monkeypatch)
    inne, slapp = threading.Event(), threading.Event()
    ny = _exam_doc()
    ny["uppgifter"][0]["text"] = "Det första varvets text."

    def fake_refine(exam, message, *a, **k):
        inne.set()
        assert slapp.wait(20)
        return {"exam": ny, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)

    svar = {}
    t = threading.Thread(target=lambda: svar.update(
        forsta=client.post(f"/api/exams/{result['id']}/refine",
                           json={"message": "gör den kortare"})))
    t.start()
    try:
        assert inne.wait(20), "första varvet kom aldrig fram till modellen"
        andra = client.post(f"/api/exams/{result['id']}/refine",
                            json={"message": "gör den svårare"})
        assert andra.status_code == 409
        assert "skrivs redan om" in andra.json()["error"]
    finally:
        slapp.set()
        t.join(20)
    assert _done(svar["forsta"])["exam"]["uppgifter"][0]["text"] \
        == "Det första varvets text."
    # Låset släpps när varvet landat — nästa ändring går igenom.
    assert client.post(f"/api/exams/{result['id']}/refine",
                       json={"message": "en till"}).status_code == 200


def test_ett_annat_papper_far_skrivas_om_samtidigt(client, monkeypatch):
    """Låset är per dokument, inte per app: två olika papper ska gå att skriva
    om parallellt — det är vad molnsemaforens tak finns till för."""
    import threading

    ett, _ = _make_exam(client, monkeypatch)
    tva, _ = _make_exam(client, monkeypatch)
    inne, slapp = threading.Event(), threading.Event()

    def fake_refine(exam, message, *a, **k):
        if message == "det långa varvet":
            inne.set()
            assert slapp.wait(20)
        return {"exam": exam, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)

    t = threading.Thread(target=lambda: client.post(
        f"/api/exams/{ett['id']}/refine", json={"message": "det långa varvet"}))
    t.start()
    try:
        assert inne.wait(20)
        r = client.post(f"/api/exams/{tva['id']}/refine",
                        json={"message": "ett annat papper"})
        assert r.status_code == 200
    finally:
        slapp.set()
        t.join(20)


def test_varv_som_bygger_pa_en_overkord_version_sparas_inte(client, monkeypatch):
    """Låset gäller den här processen; pekaren kan ha flyttats av något annat
    medan modellen skrev. Att spara då vore last-write-wins — den andres ändring
    försvann även ur ångra-historiken."""
    result, _ = _make_exam(client, monkeypatch)
    mitt = _exam_doc()
    mitt["uppgifter"][0]["text"] = "Mitt varv."
    annans = _exam_doc()
    annans["uppgifter"][0]["text"] = "Någon annans varv."

    def fake_refine(exam, message, *a, **k):
        conn = appdb.connect(client.base_dir / "transkribera.db")
        try:
            appdb.add_exam_version(conn, result["id"], annans)
        finally:
            conn.close()
        return {"exam": mitt, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)

    r = client.post(f"/api/exams/{result['id']}/refine",
                    json={"message": "gör den kortare"})
    fel = [e for e in _events(r) if e["type"] == "error"]
    assert fel and "annat varv" in fel[0]["message"]
    vy = client.get(f"/api/exams/{result['id']}").json()
    assert vy["exam"]["uppgifter"][0]["text"] == "Någon annans varv."
    assert len(vy["versions"]) == 2


def test_avbrutet_varv_committas_inte(client, monkeypatch):
    """Läraren tryckte Avbryt eller stängde fliken: strömmen är död men tråden
    kör vidare, och mellan sista loggraden och skrivningen fanns inget livstecken
    att avbryta VID — versionen sparades ändå, och nästa gång hon öppnade appen
    låg ett varv hon aldrig sett överst i ångra-historiken."""
    from fastapi.responses import JSONResponse as _JSON

    from app.web import sse

    result, _ = _make_exam(client, monkeypatch)
    laget = {"modellen_klar": False, "avbrutet": False}

    def fejkad_strom(job, req):
        """Strömmen som redan tappat sin lyssnare: varje livstecken efter att
        modellen svarat kastar KlientBorta, precis som sse.emit gör."""
        def emit(ev):
            if laget["modellen_klar"]:
                laget["avbrutet"] = True
                raise sse.KlientBorta
        try:
            job(emit)
        except sse.KlientBorta:
            pass
        return _JSON({"avbrutet": laget["avbrutet"]})
    monkeypatch.setattr(routes_exam, "sse_response", fejkad_strom)

    ny = _exam_doc()
    ny["uppgifter"][0]["text"] = "Varvet ingen väntar på."

    def fake_refine(exam, message, *a, **k):
        laget["modellen_klar"] = True
        return {"exam": ny, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)

    r = client.post(f"/api/exams/{result['id']}/refine",
                    json={"message": "gör den kortare"})
    assert r.json()["avbrutet"] is True
    assert len(_versioner(client, result["id"])) == 1
    # Och låset släpptes trots avbrottet — annars vore pappret dött för alltid.
    laget["modellen_klar"] = False
    monkeypatch.setattr(routes_exam, "sse_response", sse.sse_response)
    assert client.post(f"/api/exams/{result['id']}/refine",
                       json={"message": "en till"}).status_code == 200


def test_refine_far_reparerad_json(client, monkeypatch):
    """Modellen skriver "\\times" oescapat, json.loads gör TAB+imes av det, och
    GET-rutten och godkännandet reparerar det. Omskrivningen gjorde det inte —
    den skickade skräpet till modellen som «så här står det», modellen skrev av
    det, och varje varv bar det vidare."""
    result, _ = _make_exam(client, monkeypatch)
    trasig = _exam_doc()
    trasig["uppgifter"][0]["text"] = "Beräkna $2 \times (3 + 4)$."
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        appdb.add_exam_version(conn, result["id"], trasig)
    finally:
        conn.close()

    sett = {}

    def fake_refine(exam, message, *a, **k):
        sett["text"] = exam["uppgifter"][0]["text"]
        return {"exam": exam, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)
    client.post(f"/api/exams/{result['id']}/refine", json={"message": "kortare"})
    assert sett["text"] == "Beräkna $2 \\times (3 + 4)$."
    assert "\t" not in sett["text"]


# ───────────────────────── lärarens nivåval (v25) ─────────────────────────

def test_nivaval_bygger_skelettet_och_persisteras(client, monkeypatch):
    """«Poängnivåer» var en dekoration — värdet nådde aldrig servern. Nu ska
    rutten (1) bygga skelettet ur valets mix (som diagnosen bygger sitt),
    (2) skicka valets band till genereringen och (3) persistera etiketten på
    exams-raden, för refine mäter varje varv mot den."""
    from app import exam_spec
    result, calls = _make_exam(client, monkeypatch, nivamix="Bara E")
    nv = exam_spec.NIVAVAL["prov"]["Bara E"]
    assert calls[0]["niva_mal"] == nv["mal"]
    sk = calls[0]["skeleton"]
    assert sk and len(sk) == 6
    assert all(s["poang"][2] == 0 for s in sk), "Bara E-skelett med A-poäng"
    assert result["nivaval"] == "Bara E"
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        rad = conn.execute("SELECT nivaval FROM exams WHERE id = ?",
                           (result["id"],)).fetchone()
    finally:
        conn.close()
    assert rad["nivaval"] == "Bara E"


def test_nivaval_default_ger_exakt_samma_begaran_som_forut(client, monkeypatch):
    """Kassettregeln: en orörd väljare (inget fält alls) ska ge inget skelett
    och inga band — genereringen bygger då profilens default precis som före
    väljaren. Okänd etikett behandlas likadant: default, inte fel."""
    result, calls = _make_exam(client, monkeypatch)
    assert calls[0]["skeleton"] is None and calls[0]["niva_mal"] is None
    assert result["nivaval"] is None
    _res2, calls2 = _make_exam(client, monkeypatch, nivamix="Balanserat")
    assert calls2[0]["skeleton"] is None and calls2[0]["niva_mal"] is None
    _res3, calls3 = _make_exam(client, monkeypatch, nivamix="påhittat")
    assert calls3[0]["skeleton"] is None and calls3[0]["niva_mal"] is None


def test_nivaval_arbetsbladets_niva_gar_samma_vag(client, monkeypatch):
    """Arbetsbladets väljare heter «Nivå» och skickar `niva` — samma kedja,
    arbetsbladets etiketter."""
    from app import exam_spec
    result, calls = _make_exam(client, monkeypatch, typ="arbetsblad",
                               niva="A-nivå", delar=False)
    nv = exam_spec.NIVAVAL["arbetsblad"]["A-nivå"]
    assert calls[0]["niva_mal"] == nv["mal"]
    assert calls[0]["skeleton"] and all(
        s["del"] is None for s in calls[0]["skeleton"]), "arbetsbladet är platt"
    assert result["nivaval"] == "A-nivå"
    # …men på ett PROV är arbetsbladets etikett inget val alls.
    res2, calls2 = _make_exam(client, monkeypatch, niva="A-nivå")
    assert calls2[0]["niva_mal"] is None and res2["nivaval"] is None


def test_refine_mater_mot_dokumentets_nivaval(client, monkeypatch):
    """REFINE-fällan: valet ska läsas ur exams-raden och nå refine_exam som
    band — klienten valde en gång och ska inte behöva säga om det."""
    from app import exam_spec
    result, _ = _make_exam(client, monkeypatch, nivamix="Bara E")
    sett = {}

    def fake_refine(exam, message, *a, **k):
        sett["niva_mal"] = k.get("niva_mal")
        return {"exam": exam, "errors": [], "rounds": 1}
    monkeypatch.setattr(exam_gen, "refine_exam", fake_refine)
    _done(client.post(f"/api/exams/{result['id']}/refine",
                      json={"message": "kortare"}))
    assert sett["niva_mal"] == exam_spec.NIVAVAL["prov"]["Bara E"]["mal"]

    # Ett papper utan val skickar inga band — profilens default gäller.
    result2, _ = _make_exam(client, monkeypatch)
    sett.clear()
    _done(client.post(f"/api/exams/{result2['id']}/refine",
                      json={"message": "kortare"}))
    assert sett["niva_mal"] is None
