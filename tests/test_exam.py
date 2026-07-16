"""Provgeneratorn (Fas 4): schema/balans/kravgränser, LaTeX-rendering,
PDF-modul med stubbat kompilatoranrop samt genereringslooparna."""
import copy
import json
import subprocess

import pytest

from app import exam_gen, exam_latex, exam_pdf, exam_spec


def _exam() -> dict:
    """Balanserat exempelprov: 20 p totalt (10/6/4), förmågorna inom målen."""
    return {
        "titel": "Prov — Andragradsfunktioner",
        "kurs": "Ma2b", "klass": "SA23", "datum": "2026-10-05",
        "tid_min": 120,
        "hjalpmedel": "Del B utan räknare. Del C med räknare och formelblad.",
        "uppgifter": [
            {"del": "B", "formaga": "B", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Ange nollställena till $f(x) = (x-1)(x+3)$.",
             "innehall": ["nollställen"],
             "losning": "$x = 1$ och $x = -3$.",
             "bedomning": "+2 E för båda nollställena."},
            {"del": "B", "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Lös ekvationen $x^2 - 4x + 3 = 0$.",
             "innehall": ["pq-formeln"],
             "losning": "$x = 1$ eller $x = 3$.",
             "bedomning": "+1 E per korrekt rot."},
            {"del": "C", "formaga": "P", "typ": "redovisning", "poang": [2, 1, 0],
             "text": "Lös ekvationen $x^2 + 6x - 7 = 0$ med kvadratkomplettering.",
             "innehall": ["kvadratkomplettering"],
             "losning": "$(x+3)^2 = 16$ ger $x = 1$ eller $x = -7$.",
             "bedomning": "+1 E ansats, +1 E svar, +1 C fullständig metod."},
            {"del": "C", "formaga": "PL", "typ": "problem", "poang": [1, 2, 1],
             "text": "En rektangulär hage har omkretsen 60 m. Bestäm de mått "
                     "som maximerar arean.",
             "innehall": ["optimering", "andragradsfunktioner"],
             "losning": "Kvadrat $15 \\times 15$ m ger max.",
             "bedomning": "+1 E modell, +2 C lösning, +1 A motivering av max."},
            {"del": "C", "formaga": "R", "typ": "resonemang", "poang": [1, 1, 2],
             "text": "Avgör om påståendet stämmer: en andragradsfunktion med "
                     "$a < 0$ saknar minsta värde. Motivera.",
             "innehall": ["andragradsfunktioner"],
             "losning": "Sant — grafen är en nedåtriktad parabel.",
             "bedomning": "+1 E ställningstagande, +1 C motivering, +2 A stringens."},
            {"del": "C", "formaga": "K", "typ": "redovisning", "poang": [2, 2, 1],
             "text": "Förklara med graf och ord hur symmetrilinjen bestäms "
                     "för $f(x) = x^2 - 6x + 5$.",
             "innehall": ["symmetrilinje"],
             "losning": "$x = 3$ via $-b/(2a)$ eller nollställenas mittpunkt.",
             "bedomning": "+2 E korrekt linje, +2 C tydlig förklaring, +1 A flera representationer."},
        ],
    }


# ------------------------------------------------------------------ schema --

def test_valid_exam_passes():
    doc, errors = exam_spec.validate_exam_json(_exam())
    assert doc is not None
    assert errors == []


def test_schema_rejects_unknown_fields_and_values():
    bad = _exam()
    bad["uppgifter"][0]["formaga"] = "X"
    doc, errors = exam_spec.validate_exam_json(bad)
    assert doc is None and any(e["code"] == "schema" for e in errors)

    bad2 = _exam()
    bad2["uppgifter"][0]["hitta_pa"] = 1
    assert exam_spec.validate_exam_json(bad2)[0] is None


def test_response_format_shape():
    rf = exam_spec.to_response_format()
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "matteprov"
    assert "uppgifter" in rf["json_schema"]["schema"]["properties"]


# ------------------------------------------------------------------ balans --

def test_all_e_points_flagged():
    bad = _exam()
    for u in bad["uppgifter"]:
        u["poang"] = [3, 0, 0]
    doc, errors = exam_spec.validate_exam_json(bad)
    assert any(e["code"] == "nivabalans" for e in errors)


def test_zero_point_item_flagged():
    bad = _exam()
    bad["uppgifter"][0]["poang"] = [0, 0, 0]
    doc, errors = exam_spec.validate_exam_json(bad)
    assert any(e["code"] == "poang" for e in errors)


def test_missing_rutin_flagged():
    bad = _exam()
    for u in bad["uppgifter"]:
        u["typ"] = "redovisning"
    doc, errors = exam_spec.validate_exam_json(bad)
    assert any(e["code"] == "blandning" for e in errors)


def test_formaga_concentration_flagged():
    bad = _exam()
    for u in bad["uppgifter"]:
        u["formaga"] = "P"
    doc, errors = exam_spec.validate_exam_json(bad)
    assert any(e["code"] == "formagabalans" for e in errors)


# ------------------------------------------------------------- kravgränser --

def test_kravgranser_np_model():
    doc, _ = exam_spec.validate_exam_json(_exam())
    g = exam_spec.kravgranser(doc)
    assert g["total"] == 20
    assert g["E"]["minst"] == 5            # ceil(20 * 0.25)
    assert g["C"]["minst"] == 9            # ceil(20 * 0.45)
    assert g["C"]["varav_ca"] == 3         # ceil(10 * 0.30)
    assert g["A"]["minst"] == 13           # ceil(20 * 0.65)
    assert g["A"]["varav_a"] == 2          # ceil(4 * 0.40)
    assert "reproducerbar" not in g["regel"]   # regeln är själva texten
    assert "25" in g["regel"] and "65" in g["regel"]


def test_kravgranser_configurable():
    doc, _ = exam_spec.validate_exam_json(_exam())
    g = exam_spec.kravgranser(doc, {"e_andel": 0.5})
    assert g["E"]["minst"] == 10


# ---------------------------------------------------------------- escaping --

def test_escape_latex_specials():
    assert exam_latex.escape_latex("50% & #1_a {b}") == \
        r"50\% \& \#1\_a \{b\}"
    assert "textbackslash" in exam_latex.escape_latex("a\\b")


def test_escape_mixed_preserves_math():
    out = exam_latex.escape_mixed("Andelen är 50% eftersom $x^2 \\ge 0$ gäller.")
    assert r"50\%" in out
    assert r"\(x^2 \ge 0\)" in out
    # kontrolltecken strippas (o-escapad backslash i JSON)
    assert "\x0c" not in exam_latex.escape_mixed("a\x0cb")


# --------------------------------------------------------------- rendering --

def test_render_prov_golden_markers():
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_prov(doc)
    # fast preamble — modellen styr aldrig den
    assert tex.lstrip().startswith("\\documentclass[11pt,a4paper]{article}")
    assert "\\usepackage[swedish]{babel}" in tex
    # försättsblad med kravgränser och poäng
    assert "Kravgränser" in tex
    assert "minst 5 poäng" in tex and "minst 13 poäng" in tex
    # regelns %-tecken är escapade (annars kommenterar de bort resten av raden)
    assert r"25\?" not in tex
    assert r"25\% av totalpoängen" in tex
    assert "20 poäng (10/6/4)" in tex
    # delar + numrerade uppgifter med poängrutor
    assert "Del B" in tex and "Del C" in tex
    assert "Uppgift 1" in tex and "Uppgift 6" in tex
    # poängrutor via \poang-makrot (renderas som "(E/C/A)" i PDF:en)
    assert r"\poang{2/1/0}" in tex and r"\poang{1/2/1}" in tex
    # matte bevarad, rutinuppgift får svarsrad
    assert r"\(x^2 - 4x + 3 = 0\)" in tex
    assert "\\svarsrad" in tex
    # lösningar hör INTE hemma i provet
    assert "lösningsförslag" not in tex.lower()


def test_render_bedomning_contains_solutions():
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_bedomning(doc)
    assert "Bedömningsanvisning" in tex
    assert "Lösningsförslag" in tex
    assert "Problemlösning" in tex          # förmågenamn
    assert r"\(x = 1\)" in tex or "x = 1" in tex


def test_render_escapes_model_text():
    e = _exam()
    e["uppgifter"][0]["text"] = "Rabatten är 25% & gäller {alla}."
    doc, _ = exam_spec.validate_exam_json(e)
    tex = exam_latex.render_prov(doc)
    assert r"25\% \& g" in tex
    assert "{alla}" not in tex


# ------------------------------------------------------------- exam_pdf ----

def test_compile_pdf_success_with_stub(tmp_path, monkeypatch):
    monkeypatch.setattr(exam_pdf, "engine_path", lambda: tmp_path / "tectonic.exe")

    def fake_runner(cmd, **kw):
        out = tmp_path / "ut"
        (out / "prov.pdf").write_bytes(b"%PDF-1.5 fejk")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    pdf, log = exam_pdf.compile_pdf("\\documentclass{article}", tmp_path / "ut",
                                    "prov", runner=fake_runner)
    assert pdf is not None and pdf.exists()
    assert log == ""
    assert (tmp_path / "ut" / "prov.tex").exists()     # källan lämnas kvar


def test_compile_pdf_failure_writes_log(tmp_path, monkeypatch):
    monkeypatch.setattr(exam_pdf, "engine_path", lambda: tmp_path / "tectonic.exe")

    def fail_runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout="",
                                           stderr="! Undefined control sequence.")

    pdf, log = exam_pdf.compile_pdf("x", tmp_path / "ut", "prov",
                                    runner=fail_runner)
    assert pdf is None
    assert "Undefined control sequence" in log
    assert (tmp_path / "ut" / "prov.log.txt").exists()


def test_compile_pdf_engine_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(exam_pdf, "engine_path", lambda: None)
    pdf, log = exam_pdf.compile_pdf("x", tmp_path / "ut", "prov")
    assert pdf is None and "Tectonic" in log


def test_compile_pdf_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(exam_pdf, "engine_path", lambda: tmp_path / "tectonic.exe")

    def slow_runner(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)

    pdf, log = exam_pdf.compile_pdf("x", tmp_path / "ut", "prov",
                                    timeout=1, runner=slow_runner)
    assert pdf is None and "avbröts" in log


# ------------------------------------------------------------- exam_gen ----

def _stub_llm(responses: list[str]):
    calls: list[dict] = []

    def llm(model, prompt, system=None, options=None, response_format=None,
            max_tokens=None, token_cb=None):
        calls.append({"prompt": prompt, "system": system,
                      "response_format": response_format})
        return responses[min(len(calls) - 1, len(responses) - 1)]

    return llm, calls


def test_generate_exam_valid_first_try():
    llm, calls = _stub_llm([json.dumps(_exam())])
    res = exam_gen.generate_exam("Ma2b", "SA23", ["pq-formeln"], model="m", llm=llm)
    assert res["errors"] == [] and res["rounds"] == 1
    assert res["exam"]["titel"].startswith("Prov")
    assert calls[0]["response_format"]["json_schema"]["name"] == "matteprov"
    assert "pq-formeln" in calls[0]["prompt"]


def test_generate_exam_repairs_imbalance():
    bad = _exam()
    for u in bad["uppgifter"]:
        u["poang"] = [3, 0, 0]
    llm, calls = _stub_llm([json.dumps(bad), json.dumps(_exam())])
    res = exam_gen.generate_exam("Ma2b", "SA23", [], model="m", llm=llm)
    assert res["rounds"] == 2 and res["errors"] == []
    assert "nivabalans" in calls[1]["prompt"] or "E-poängen" in calls[1]["prompt"]


def test_generate_exam_gives_up_after_budget():
    bad = _exam()
    for u in bad["uppgifter"]:
        u["poang"] = [3, 0, 0]
    llm, calls = _stub_llm([json.dumps(bad)])
    res = exam_gen.generate_exam("Ma2b", "SA23", [], model="m", llm=llm)
    assert res["rounds"] == exam_gen.MAX_ROUNDS
    assert res["errors"] and res["exam"] is not None


def test_refine_exam_targets_item():
    updated = _exam()
    updated["uppgifter"][3]["text"] = "Ny optimeringsuppgift med decimaltal."
    llm, calls = _stub_llm([json.dumps(updated)])
    res = exam_gen.refine_exam(_exam(), "byt mot ett med decimaltal",
                               nummer=4, model="m", llm=llm)
    assert res["errors"] == []
    assert "uppgift 4" in calls[0]["prompt"]


def test_fix_latex_rounds_cap():
    llm, calls = _stub_llm([json.dumps(_exam())])
    res = exam_gen.fix_latex(_exam(), "! Missing $ inserted.", model="m", llm=llm)
    assert res["rounds"] == 1 and res["errors"] == []
    assert "Missing $" in calls[0]["prompt"]
    # budgeten slut → inget LLM-anrop
    res2 = exam_gen.fix_latex(_exam(), "fel", model="m", llm=llm,
                              rounds_used=exam_gen.MAX_LATEX_ROUNDS)
    assert res2["rounds"] == exam_gen.MAX_LATEX_ROUNDS
    assert any(e["code"] == "kompilering" for e in res2["errors"])
    assert len(calls) == 1


# ------------------------------------------------------ Fas 5: arbetsblad --

def _arbetsblad() -> dict:
    """E-tungt övningsblad utan redovisningsuppgifter — ok som arbetsblad,
    obalanserat som prov."""
    return {
        "titel": "Arbetsblad — pq-formeln", "kurs": "Ma2b",
        "hjalpmedel": "Räknare",
        "uppgifter": [
            {"del": None, "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Lös $x^2 - 5x + 6 = 0$.", "innehall": ["pq-formeln"],
             "losning": "$x = 2$ eller $x = 3$.", "bedomning": "+2 E."},
            {"del": None, "formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
             "text": "Lös $x^2 + 2x - 8 = 0$.", "innehall": ["pq-formeln"],
             "losning": "$x = 2$ eller $x = -4$.", "bedomning": "+2 E."},
            {"del": None, "formaga": "B", "typ": "rutin", "poang": [1, 1, 0],
             "text": "Vad kallas talet under rottecknet i pq-formeln?",
             "innehall": ["pq-formeln"], "losning": "Diskriminantuttrycket.",
             "bedomning": "+1 E, +1 C."},
            {"del": None, "formaga": "PL", "typ": "rutin", "poang": [1, 1, 1],
             "text": "Hitta två tal med summan 7 och produkten 12.",
             "innehall": ["ekvationer"], "losning": "3 och 4.",
             "bedomning": "+1 E, +1 C, +1 A."},
        ],
    }


def test_arbetsblad_profile_accepts_worksheet_balance():
    doc, errors = exam_spec.validate_exam_json(_arbetsblad(), "arbetsblad")
    assert doc is not None and errors == []
    # samma dokument faller som PROV (saknar redovisning, för E-tungt)
    _doc2, prov_errors = exam_spec.validate_exam_json(_arbetsblad(), "prov")
    assert any(e["code"] == "blandning" for e in prov_errors)


def test_render_arbetsblad_has_facit_no_kravgranser():
    doc, _ = exam_spec.validate_exam_json(_arbetsblad(), "arbetsblad")
    tex = exam_latex.render_arbetsblad(doc)
    assert "Arbetsblad" in tex
    assert "Facit" in tex
    assert "Kravgränser" not in tex
    assert r"\(x = 2\)" in tex                    # facit = lösningarna
    assert r"\poang{" not in tex                  # poäng dolda som standard
    tex_p = exam_latex.render_arbetsblad(doc, visa_poang=True)
    assert r"\poang{2/0/0}" in tex_p


def test_build_referens_numbers_and_instructs():
    ref = exam_gen.build_referens(["Lös $x^2 = 4$.", "Optimera hagen."])
    assert "1. Lös" in ref and "2. Optimera" in ref
    assert "HÖJ" in ref and "ALDRIG" in ref


def test_build_prompt_arbetsblad_profile():
    p = exam_gen.build_prompt("Ma2b", "SA23", [], profil="arbetsblad")
    assert "ARBETSBLAD" in p
    assert "del: null" in p


def test_generate_exam_respects_profile():
    llm, _ = _stub_llm([json.dumps(_arbetsblad())])
    res = exam_gen.generate_exam("Ma2b", "SA23", [], model="m", llm=llm,
                                 profil="arbetsblad")
    assert res["errors"] == [] and res["rounds"] == 1


def test_find_similar_exam_items(tmp_path):
    from app import db as appdb
    conn = appdb.connect(tmp_path / "t.db")
    cid = appdb.get_or_create_course(conn, "Ma2b")
    gammalt = appdb.create_exam(conn, exam=_exam(), course_id=cid,
                                datum="2026-09-01")
    # bara godkända prov räknas
    assert appdb.find_similar_exam_items(
        conn, cid, ["Lös ekvationen $x^2 - 4x + 3 = 0$."]) == []
    appdb.set_exam_artifacts(conn, gammalt["id"], approve=True)

    flaggor = appdb.find_similar_exam_items(
        conn, cid, ["Lös ekvationen $x^2 - 4x + 3 = 0$.",
                    "Beräkna integralen av $\\sin x$ mellan 0 och pi."])
    assert len(flaggor) == 1
    assert flaggor[0]["index"] == 0
    assert flaggor[0]["mot_exam_id"] == gammalt["id"]
    assert flaggor[0]["likhet"] >= 0.9
    # exkludering av det egna provet
    assert appdb.find_similar_exam_items(
        conn, cid, ["Lös ekvationen $x^2 - 4x + 3 = 0$."],
        exclude_exam_id=gammalt["id"]) == []


def test_prompt_includes_memory_and_themes():
    p = exam_gen.build_prompt("Ma2b", "SA23", ["pq-formeln"],
                              memory="Klassen har arbetat med kvadrering.",
                              teman="2026-09-01 — Prov 1: lös ekvationen …")
    assert "kvadrering" in p
    assert "UNDVIK" in p
    assert "egenformulerade" in exam_gen.SYSTEM
