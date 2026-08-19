"""Felinjektion: godkännandet, disken och GPU-låset (Etapp 4.4).

Molnets felmoder är redan prövade (`tests/test_molnkorningen.py`) och nätet
som dör mitt i en körning likaså (`e2e/moln.spec.mjs`). Kvar står de tre som
kostar mest när de händer på riktigt, och som ingen upptäcker förrän de gör
det:

* **Godkännandet måste vara allt-eller-inget.** Läraren trycker Godkänn en
  gång. Faller skrivningen halvvägs får hon inte en lektion i kalendern utan
  papper, eller två lektioner för att hon tryckte igen.
* **Disken tar slut.** Lektionsinspelningar är hundratals megabyte och
  lärardatorer är fulla. Varje skrivväg ska svara med ett svenskt besked, inte
  med ett fel som når läraren som «Okänt fel».
* **GPU-låset.** Ett tungt jobb i taget. Den som får 409 får inte råka SLÄPPA
  någon annans lås — låset har ingen ägarkontroll, så ett `finally` på fel
  ställe stjäl det utan att något syns förrän två jobb kör samtidigt.
"""
from __future__ import annotations

import copy
import errno
import json
from pathlib import Path

import pytest

from app import db, exam_pdf, gpu_arbiter, lesson_board


def _events(resp) -> list[dict]:
    return [json.loads(rad[len("data:"):])
            for rad in resp.text.splitlines() if rad.startswith("data:")]


def _done(resp) -> dict:
    ev = [e for e in _events(resp) if e["type"] == "done"]
    assert ev, _events(resp)
    return ev[0]["result"]


def _fel(resp) -> str:
    """Felmeddelandet läraren får — ur SSE-strömmens error-event."""
    ev = [e for e in _events(resp) if e["type"] == "error"]
    assert ev, _events(resp)
    return ev[0].get("message") or ev[0].get("error") or ""


def _tavla(llm_ready, monkeypatch, moment="Derivatans definition") -> str:
    """En färdig planering i serverns minne — det godkännandet arbetar på."""
    board = copy.deepcopy(lesson_board.FEW_SHOTS[0][1])
    board["title"] = moment
    monkeypatch.setattr(lesson_board, "generate_board",
                        lambda *a, **k: {"board": board, "errors": [], "rounds": 1})
    r = llm_ready.post("/api/planning/generate", json={"moment": moment,
                                                       "klass": "NA25",
                                                       "kurs": "Matematik, nivå 2c"})
    assert r.status_code == 200
    return _done(r)["id"]


def _disken_full(monkeypatch, *, bara: str | None = None):
    """Nästa skrivning på disk misslyckas som när disken är full.

    `bara` begränsar felet till filnamn som innehåller strängen — annars
    faller ALLA skrivningar, också de som hör till testriggen."""
    riktig_text = Path.write_text
    riktig_bytes = Path.write_bytes

    def slut(self, *a, **k):
        if bara is None or bara in self.name:
            raise OSError(errno.ENOSPC, "No space left on device")
        return riktig_text(self, *a, **k)

    def slut_b(self, *a, **k):
        if bara is None or bara in self.name:
            raise OSError(errno.ENOSPC, "No space left on device")
        return riktig_bytes(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", slut)
    monkeypatch.setattr(Path, "write_bytes", slut_b)


# ══════════════════════════════ godkännandet ════════════════════════════════

def test_godkannandet_lamnar_ingen_lektion_utan_sitt_papper(llm_ready, monkeypatch):
    """Servern dör mellan raden och filen — det får inte gå att hamna där.

    Godkännandet skriver TVÅ saker: en rad i planned_lessons (lektionsminnet
    som nästa tavla bygger vidare på) och tavlan som fil under
    Transkriberingar/<lektion>/planering/. Faller filskrivningen ska raden
    inte bli kvar: läraren ser då en planerad lektion i veckan vars papper
    inte finns, trycker Godkänn igen, och får två."""
    pid = _tavla(llm_ready, monkeypatch)
    _disken_full(monkeypatch, bara="tavla ")

    r = llm_ready.post(f"/api/planning/{pid}/approve", json={})
    assert r.status_code == 507, r.text
    assert "disk" in r.json()["error"].lower()

    conn = db.connect(llm_ready.base_dir / "transkribera.db")
    try:
        rader = conn.execute("SELECT COUNT(*) AS n FROM planned_lessons").fetchone()
    finally:
        conn.close()
    assert rader["n"] == 0, "en planerad lektion utan papper blev kvar"


def test_ett_andra_forsok_efter_ett_misslyckat_ger_en_lektion_inte_tva(
        llm_ready, monkeypatch):
    """…och när disken städats fungerar samma knapp igen — en gång."""
    pid = _tavla(llm_ready, monkeypatch)
    # Disken fylls i en EGEN monkeypatch-omgivning. `monkeypatch.undo()` stod
    # här förr med kommentaren «stubbarna kvar» — men `llm_ready` får samma
    # monkeypatch-instans som testet, så undo tog bort dess stubbar också.
    # Därefter föll `is_running` tillbaka på den riktiga kontrollen: sann på en
    # maskin med Claude Code installerat, falsk i CI. Testet var grönt här och
    # rött där, och det var maskinen som avgjorde, inte koden.
    with pytest.MonkeyPatch.context() as disken:
        _disken_full(disken, bara="tavla ")
        assert llm_ready.post(f"/api/planning/{pid}/approve",
                              json={}).status_code == 507

    pid2 = _tavla(llm_ready, monkeypatch)
    r = llm_ready.post(f"/api/planning/{pid2}/approve", json={})
    assert r.status_code == 200
    assert Path(r.json()["path"]).is_file()

    conn = db.connect(llm_ready.base_dir / "transkribera.db")
    try:
        n = conn.execute("SELECT COUNT(*) AS n FROM planned_lessons").fetchone()["n"]
    finally:
        conn.close()
    assert n == 1


def _prov(llm_ready, fejk_claude) -> int:
    """Ett riktigt prov i basen — skrivet ur den skarpa kassetten, genom
    appens egen generator (schema, balans, städning av toppnycklar)."""
    fejk_claude(kassett="prov")
    gid = llm_ready.post("/api/groups", json={"namn": "NA25"}).json()["id"]
    cid = llm_ready.post("/api/courses",
                         json={"namn": "Matematik, nivå 2c"}).json()["id"]
    r = llm_ready.post("/api/exams/generate",
                       json={"group_id": gid, "course_id": cid, "antal": 6})
    res = _done(r)
    assert res["id"], res
    return res["id"]


def test_provets_godkannande_markerar_inte_godkant_nar_texen_inte_kan_skrivas(
        llm_ready, fejk_claude, monkeypatch):
    """Provet skrivs som .tex, .pdf och en bedömningsanvisning. Går inte ens
    .tex:en att skriva ska provet stå kvar som utkast — ett prov som är märkt
    godkänt men saknar papper är värre än ett som syns misslyckas."""
    exam_id = _prov(llm_ready, fejk_claude)

    _disken_full(monkeypatch, bara=".tex")
    r2 = llm_ready.post(f"/api/exams/{exam_id}/approve", json={})
    besked = _fel(r2)
    assert "disk" in besked.lower(), besked

    view = llm_ready.get(f"/api/exams/{exam_id}").json()
    assert view["status"] != "godkänt", "provet märktes godkänt utan papper"


def test_ett_prov_som_inte_gick_att_rendera_alls_godkanns_inte(
        llm_ready, fejk_claude, monkeypatch):
    """Godkännandet får märka provet godkänt med ENBART .tex — det är ärligt,
    LaTeX:en går att kompilera för hand. Men faller redan valideringen skrivs
    ingen fil alls, och då finns ingenting att godkänna. Förr sattes flaggan
    ändå: provet stod som godkänt i kalendern, utan .tex, utan PDF."""
    exam_id = _prov(llm_ready, fejk_claude)
    from app import exam_spec

    monkeypatch.setattr(exam_spec, "validate_exam_json",
                        lambda *a, **k: (None, [{"path": "uppgifter",
                                                 "code": "schema",
                                                 "message": "trasigt prov"}]))
    r = llm_ready.post(f"/api/exams/{exam_id}/approve", json={})
    res = _done(r)
    assert res["errors"], res
    view = llm_ready.get(f"/api/exams/{exam_id}").json()
    assert view["status"] != "godkänt"


# ═══════════════════════════════ disken full ═══════════════════════════════

def test_sakerhetskopian_sager_ifran_nar_disken_ar_full(client, monkeypatch):
    """Säkerhetskopian har redan en väg för «platsen går inte att skriva
    till». Disken som tar slut MITT I zip-skrivningen är en annan sak, och
    kvittot får inte påstå att kopian finns."""
    import zipfile

    def full(*a, **k):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(zipfile.ZipFile, "write", full)
    r = client.post("/api/backup", json={})
    assert r.status_code == 507, r.text
    assert "disk" in r.json()["error"].lower()
    # …och den halva zipen ligger inte kvar och ser ut som en kopia.
    kvar = list((client.base_dir / "exports").glob("*.zip"))
    assert kvar == [], kvar


def test_tryckpaketet_sager_ifran_nar_disken_ar_full(client, monkeypatch):
    """Tryckpaketet fogar ihop PDF:erna till en fil. Går den inte att skriva
    ska läraren få veta det innan hon står vid kopiatorn."""
    import base64

    from app import tryck

    monkeypatch.setattr(tryck, "png_till_pdf",
                        lambda *a, **k: client.base_dir / "fejk.pdf")
    monkeypatch.setattr(tryck, "_sidor", lambda *a, **k: 1)

    def full(*a, **k):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(tryck, "foga_ihop", full)
    png = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
    r = client.post("/api/tryck", json={"dokument": [
        {"namn": "Dagens tavla", "typ": "Tavla", "kopior": 1, "png": png}]})
    assert r.status_code == 200
    besked = _fel(r)
    assert "disk" in besked.lower(), besked


def test_alla_stromjobb_oversatter_full_disk_till_svenska():
    """Bokimporten skriver sidbilder, extraktionen skriver ingenting, provet
    skriver .tex — men de delar strömlagret, och det är där översättningen
    bor. Ett OSError med ENOSPC ska aldrig nå läraren som «[Errno 28] No space
    left on device»; allt annat ska däremot gå fram ordagrant, för det är ofta
    en mening någon skrivit åt henne."""
    from app.web import sse

    assert "disk" in sse._besked(OSError(errno.ENOSPC, "No space left")).lower()
    assert sse._besked(RuntimeError("Claude Code är inte inloggat.")) \
        == "Claude Code är inte inloggat."
    # En annan OSError är inte diskfull och får inte döpas om till det.
    assert "disk" not in sse._besked(
        OSError(errno.ENOENT, "No such file")).lower()


# ══════════════════════════ Grindarna (kort & moln) ═══════════════════════════

GENERERANDE = [
    ("/api/planning/generate", {"moment": "Derivator"}),
    ("/api/exams/generate", {"course_id": 1, "antal": 4}),
    ("/api/chat", {"messages": [{"role": "user", "content": "hej"}]}),
]


@pytest.mark.parametrize("vag,kropp", GENERERANDE)
def test_fullt_tak_ger_409_och_stjal_inte_nagon_annans_plats(
        llm_ready, vag, kropp):
    """LLM_TAK jobb samtidigt: den som kommer sedan får 409.

    Grinden har en ägarkontroll sedan buggkandidat 9 — samma nyckeldisciplin som
    GPU-låset, ärvd därifrån: bara en nyckel som togs ut öppnar. Testet står ändå
    kvar — det som prövas är att 409-vägen inte ens FÖRSÖKER släppa, och att ett
    `finally` på fel sida om return-raden numera skulle vara ofarligt i stället
    för att rycka undan platsen för jobbet som pågår."""
    arb = llm_ready.app.state.arbiter
    nycklar = [arb.try_acquire_llm() for _ in range(gpu_arbiter.LLM_TAK)]
    assert all(nycklar), "taket var redan nått innan testet började"
    try:
        r = llm_ready.post(vag, json=kropp)
        assert r.status_code == 409, (vag, r.status_code)
        assert r.json()["error"] == gpu_arbiter.LLM_UPPTAGET
        # …och platserna är kvar hos den som höll dem.
        assert not arb.try_acquire_llm(), \
            f"{vag} släppte en plats den aldrig tog"
    finally:
        for n in nycklar:
            assert arb.release_llm(n), f"{vag} släppte vår plats"


def test_gpu_laset_stanger_inte_langre_molnjobben(llm_ready):
    """Arvet som skulle bort: förr räckte en pågående transkribering för att
    läraren skulle mötas av «GPU:n är upptagen» när hon bad om en tavla. Kortet
    och molnet är två skilda grindar nu."""
    arb = llm_ready.app.state.arbiter
    nyckel = arb.try_acquire_gpu()
    assert nyckel, "låset var upptaget innan testet började"
    try:
        r = llm_ready.post("/api/planning/generate", json={"moment": "Derivator"})
        assert r.status_code == 200, r.status_code
    finally:
        assert arb.release_gpu(nyckel), "planeringen släppte vårt GPU-lås"


def test_godkannandet_vantar_inte_pa_grinden(llm_ready, fejk_claude, monkeypatch):
    """PDF-bygget är CPU-arbete (Tectonic) och ska inte köa bakom någon grind.

    Förr tog godkännandet låset och höll det genom hela kompileringen: läraren
    som skrev nästa dokument direkt efter ett godkänt prov fick «upptagen» —
    samtidigt som gränssnittet sa att PDF:en byggdes i bakgrunden. Grinden tas
    nu bara runt en eventuell LaTeX-fixrunda, som är ett LLM-anrop."""
    exam_id = _prov(llm_ready, fejk_claude)
    monkeypatch.setattr(exam_pdf, "engine_available", lambda: False)

    arb = llm_ready.app.state.arbiter
    nycklar = [arb.try_acquire_llm() for _ in range(gpu_arbiter.LLM_TAK)]
    assert all(nycklar), "taket var redan nått innan testet började"
    try:
        r = llm_ready.post(f"/api/exams/{exam_id}/approve", json={})
        assert r.status_code == 200, r.text
        res = _done(r)
        assert res["tex"], "ingen .tex skrevs — godkännandet kom aldrig fram"
    finally:
        for n in nycklar:
            assert arb.release_llm(n), "godkännandet släppte vår plats"
    # …och taket är fritt igen.
    arb.release_llm(arb.try_acquire_llm())


def test_ett_jobb_som_kastar_slapper_platsen(llm_ready, monkeypatch):
    """Ett jobb som dör mitt i får inte lämna sin plats tagen — läcker alla tre
    är appen slut för dagen och läraren måste starta om den."""
    def sprangs(*a, **k):
        raise RuntimeError("kortet försvann mitt i")

    monkeypatch.setattr(lesson_board, "generate_board", sprangs)
    r = llm_ready.post("/api/planning/generate", json={"moment": "Derivator"})
    assert "kortet försvann" in _fel(r)

    arb = llm_ready.app.state.arbiter
    nycklar = [arb.try_acquire_llm() for _ in range(gpu_arbiter.LLM_TAK)]
    assert all(nycklar), "en plats låstes fast av ett jobb som dog"
    for n in nycklar:
        arb.release_llm(n)


def test_grinden_ar_fri_igen_efter_en_hel_generering(llm_ready, monkeypatch):
    board = copy.deepcopy(lesson_board.FEW_SHOTS[0][1])
    monkeypatch.setattr(lesson_board, "generate_board",
                        lambda *a, **k: {"board": board, "errors": [], "rounds": 1})
    assert llm_ready.post("/api/planning/generate",
                          json={"moment": "Derivator"}).status_code == 200
    arb = llm_ready.app.state.arbiter
    nycklar = [arb.try_acquire_llm() for _ in range(gpu_arbiter.LLM_TAK)]
    assert all(nycklar)
    for n in nycklar:
        arb.release_llm(n)
