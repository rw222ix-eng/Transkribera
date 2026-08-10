"""Hybridtolkningen av kalendern (Etapp 0.1b).

Reglerna klassar det de klarar och markerar resten som osäker; bara resten går
till Claude. Det som måste hålla är att modellen aldrig kan göra kalendern
SÄMRE än reglerna:

* ett beslut om en nyckel vi inte skickade in kastas — den kan inte uppfinna
  en lektion ur ingenting,
* en lektion måste ha både klass och kurs och komma ur en återkommande TID,
* faller anropet står reglernas placering kvar,
* samma serie frågas en gång, inte per instans och inte per synk.
"""
import json

import pytest

from app import calendar_google, db, kalender_ai
from app.web import server


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def _tid(datum, fran, till, **extra):
    return dict({"summary": extra.pop("summary", "Lektion"),
                 "start": {"dateTime": f"{datum}T{fran}:00"},
                 "end": {"dateTime": f"{datum}T{till}:00"}}, **extra)


def _heldag(namn, fran, till):
    return {"summary": namn, "start": {"date": fran}, "end": {"date": till}}


# --------------------------------------------------- vad som blir osäkert --

def test_reglerna_markerar_det_de_inte_kan_avgora():
    ut = calendar_google.tolka_handelser([
        # Säkert: känd kurs + klass, återkommande.
        _tid("2026-08-17", "09:05", "10:20", summary="Matematik, nivå 2c NA25",
             recurringEventId="r1"),
        # Osäkert: återkommande med klass men ingen igenkänd kurs.
        _tid("2026-08-17", "08:25", "08:55", summary="Mentorstid NA25",
             recurringEventId="r2"),
        # Osäkert: heldag utan lovord.
        _heldag("APL-vecka åk 2", "2026-09-14", "2026-09-19"),
        # Säkert: enstaka möte.
        _tid("2026-08-20", "13:00", "14:30", summary="Ämneslagsmöte"),
    ], klasser=["NA25"], kurser=["Matematik, nivå 2c"])

    assert len(ut["schema"]) == 1
    varfor = {o["titel"]: o["varfor"] for o in ut["osakra"]}
    assert set(varfor) == {"Mentorstid NA25", "APL-vecka åk 2"}
    # Det osäkra ligger ändå placerat — inget försvinner om ingen frågar vidare.
    assert any(p["titel"] == "Mentorstid NA25" for p in ut["poster"])


def test_en_serie_frags_en_gang_inte_per_instans():
    handelser = [_tid(d, "08:25", "08:55", summary="Mentorstid NA25",
                      recurringEventId="r2")
                 for d in ("2026-08-17", "2026-08-24", "2026-08-31")]
    ut = calendar_google.tolka_handelser(handelser, klasser=["NA25"],
                                         kurser=["Matematik, nivå 2c"])
    assert len(ut["osakra"]) == 1


def test_serienyckeln_skiljer_pa_slag_men_inte_pa_datum():
    a = _tid("2026-08-17", "08:25", "08:55", summary="Mentorstid", recurringEventId="r")
    b = _tid("2026-09-21", "08:25", "08:55", summary="MENTORSTID  ", recurringEventId="r")
    c = _heldag("Mentorstid", "2026-08-17", "2026-08-18")
    assert calendar_google.serienyckel(a) == calendar_google.serienyckel(b)
    assert calendar_google.serienyckel(a) != calendar_google.serienyckel(c)


# ------------------------------------------------------------ beslutet gäller --

def test_beslut_gor_en_post_till_en_lektion():
    handelser = [_tid("2026-08-18", "10:15", "11:00", summary="Ma2c NA25 halvklass A",
                      location="P807", recurringEventId="r5")]
    kanda = ["Matematik, nivå 2c"]          # «Ma2c» är kalenderns egen kortform
    ut = calendar_google.tolka_handelser(handelser, klasser=["NA25"], kurser=kanda)
    nyckel = ut["osakra"][0]["nyckel"]
    med = calendar_google.tolka_handelser(
        handelser, klasser=["NA25"], kurser=kanda,
        beslut={nyckel: {"slag": "lektion", "klass": "NA25",
                         "kurs": "Matematik, nivå 2c"}})
    assert med["schema"] == [{"dag": 2, "tid": "10:15–11:00",
                              "kurs": "Matematik, nivå 2c", "klass": "NA25",
                              "sal": "P807",
                              # Serien sågs bara en gång: den dagen är både
                              # första och sista instansen.
                              "fran": "2026-08-18", "till": "2026-08-18",
                              "undantag": []}]
    assert med["poster"] == []


def test_beslut_gor_en_heldag_till_uppehall():
    handelser = [_heldag("Friluftsdag", "2026-09-11", "2026-09-12")]
    nyckel = calendar_google.serienyckel(handelser[0])
    ut = calendar_google.tolka_handelser(
        handelser, beslut={nyckel: {"slag": "uppehall", "namn": "Friluftsdag"}})
    assert ut["lov"] == [{"fran": "2026-09-11", "till": "2026-09-11",
                          "namn": "Friluftsdag", "typ": "uppehall"}]


def test_en_heldag_kan_bli_en_post_och_tappas_inte():
    """«Öppet hus» stänger inte skolan men står i kalendern. Grenen saknades
    och heldagsposter försvann tyst — funnet vid en skarp körning."""
    handelser = [_heldag("Öppet hus", "2026-10-08", "2026-10-09")]
    nyckel = calendar_google.serienyckel(handelser[0])
    ut = calendar_google.tolka_handelser(handelser, beslut={nyckel: {"slag": "post"}})
    assert ut["poster"] == [{"datum": "2026-10-08", "tid": "",
                             "titel": "Öppet hus", "klass": ""}]
    assert ut["lov"] == []


def test_ignorera_tar_bort_posten_helt():
    handelser = [_tid("2026-08-20", "18:00", "19:00", summary="Träning")]
    nyckel = calendar_google.serienyckel(handelser[0])
    ut = calendar_google.tolka_handelser(handelser, beslut={nyckel: {"slag": "ignorera"}})
    assert ut["poster"] == [] and ut["lov"] == [] and ut["schema"] == []


# -------------------------------------------------------------- valideringen --

def _osakra():
    return [{"nyckel": "mentorstid na25|tid|serie", "titel": "Mentorstid NA25",
             "heldag": False, "aterkommande": True, "varfor": "…"},
            {"nyckel": "apl-vecka|heldag|enstaka", "titel": "APL-vecka",
             "heldag": True, "aterkommande": False, "varfor": "…"}]


def test_beslut_om_en_okand_nyckel_kastas():
    """Modellen kan omklassificera det den fick se — aldrig uppfinna."""
    ut = kalender_ai.validera(
        {"beslut": [{"nyckel": "hittepå|tid|serie", "slag": "lektion",
                     "klass": "NA25", "kurs": "Matematik, nivå 2c"}]}, _osakra())
    assert ut == {}


def test_lektion_utan_klass_eller_kurs_kastas():
    ut = kalender_ai.validera(
        {"beslut": [{"nyckel": "mentorstid na25|tid|serie", "slag": "lektion",
                     "klass": "NA25"}]}, _osakra())
    assert ut == {}


def test_lektion_ur_en_heldag_kastas():
    """En lektion utan tid finns inte."""
    ut = kalender_ai.validera(
        {"beslut": [{"nyckel": "apl-vecka|heldag|enstaka", "slag": "lektion",
                     "klass": "NA25", "kurs": "Matematik, nivå 2c"}]}, _osakra())
    assert ut == {}


def test_lov_ur_en_tidsatt_handelse_kastas():
    """Skolan stängs inte av en timme i kalendern."""
    ut = kalender_ai.validera(
        {"beslut": [{"nyckel": "mentorstid na25|tid|serie", "slag": "lov"}]},
        _osakra())
    assert ut == {}


def test_okant_slag_kastas():
    ut = kalender_ai.validera(
        {"beslut": [{"nyckel": "apl-vecka|heldag|enstaka", "slag": "kanske"}]},
        _osakra())
    assert ut == {}


def test_giltiga_beslut_slapps_igenom():
    ut = kalender_ai.validera({"beslut": [
        {"nyckel": "mentorstid na25|tid|serie", "slag": "post"},
        {"nyckel": "apl-vecka|heldag|enstaka", "slag": "uppehall", "namn": "APL"},
    ]}, _osakra())
    assert ut["mentorstid na25|tid|serie"]["slag"] == "post"
    assert ut["apl-vecka|heldag|enstaka"] == {"slag": "uppehall", "namn": "APL"}


def test_skrap_fran_modellen_ger_tom_bedomning():
    for data in (None, [], {"beslut": "nej"}, {"annat": 1}):
        assert kalender_ai.validera(data, _osakra()) == {}


# ------------------------------------------------------------------ anropet --

def test_bedom_skickar_bara_de_osakra_och_validerar_svaret():
    sedda = {}

    def llm(model, prompt, **kw):
        sedda["prompt"] = prompt
        sedda["schema"] = kw.get("response_format")
        return json.dumps({"beslut": [
            {"nyckel": "mentorstid na25|tid|serie", "slag": "post"}]})

    ut = kalender_ai.bedom(_osakra(), ["NA25"], ["Matematik, nivå 2c"], llm=llm)
    assert ut == {"mentorstid na25|tid|serie": {"slag": "post",
                                                "namn": "Mentorstid NA25"}}
    assert "Mentorstid NA25" in sedda["prompt"]
    assert "NA25" in sedda["prompt"] and "Matematik, nivå 2c" in sedda["prompt"]
    assert sedda["schema"]["type"] == "json_schema"


def test_bedom_utan_osakra_anropar_inte_modellen():
    def llm(*a, **k):
        raise AssertionError("modellen ska inte anropas")
    assert kalender_ai.bedom([], llm=llm) == {}


def test_ett_trasigt_anrop_lamnar_reglerna_ororda():
    def llm(*a, **k):
        raise RuntimeError("Claude Code svarar inte")
    assert kalender_ai.bedom(_osakra(), llm=llm) == {}


# -------------------------------------------------------------------- cachen --

def test_synken_fragar_en_gang_och_kommer_ihag(tmp_path, monkeypatch):
    """Hela vägen: reglerna placerar, Claude får resten, beslutet cachas — och
    nästa synk frågar inte om samma sak igen."""
    from fastapi.testclient import TestClient

    class HW:
        gpu_name = "T"; vram_mb = 1; has_cuda = False; ram_mb = 1; cpu_cores = 1
        free_disk_mb = 1; cpu_name = "T"; vram_free_mb = 1; ram_free_mb = 1
        total_disk_mb = 1; cuda_version = ""; compute_capability = ""
        gpu_arch = ""; disks = []

    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    client = TestClient(server.create_app(base_dir=tmp_path))
    monkeypatch.setattr(client.app.state.arbiter, "ensure_llm", lambda: "http://x")

    handelser = [
        _tid("2026-08-17", "09:05", "10:20", summary="Matematik, nivå 2c NA25",
             location="P807", recurringEventId="r1"),
        _tid("2026-08-17", "08:25", "08:55", summary="Mentorstid NA25",
             recurringEventId="r2"),
        _heldag("Friluftsdag", "2026-09-11", "2026-09-12"),
    ]
    monkeypatch.setattr(calendar_google, "_load_creds", lambda *a, **k: object())
    monkeypatch.setattr(calendar_google, "list_events", lambda *a, **k: handelser)

    anrop = []

    def llm(model, prompt, **kw):
        anrop.append(prompt)
        return json.dumps({"beslut": [
            {"nyckel": "mentorstid na25|tid|serie", "slag": "post"},
            {"nyckel": "friluftsdag|heldag|enstaka", "slag": "uppehall",
             "namn": "Friluftsdag"},
        ]})
    # Bind originalet FÖRE patchen — annars kallar lambdan sig själv.
    riktig_bedom = kalender_ai.bedom
    monkeypatch.setattr(server.kalender_ai, "bedom",
                        lambda o, k=None, ku=None, **kw: riktig_bedom(o, k, ku, llm=llm))

    d = client.post("/api/schema/synk").json()
    assert len(anrop) == 1
    assert d["bedomda"] == 2
    assert [r["klass"] for r in d["schema"]] == ["NA25"]
    assert any(p["namn"] == "Friluftsdag" and p["typ"] == "uppehall" for p in d["lov"])
    assert any(p["titel"] == "Mentorstid NA25" for p in d["poster"])

    d2 = client.post("/api/schema/synk").json()
    assert len(anrop) == 1, "cachen ska göra andra synken gratis"
    assert d2["schema"] == d["schema"] and d2["bedomda"] == 2


def test_synken_gar_igenom_utan_claude(tmp_path, monkeypatch):
    """Är Claude utloggad står reglernas placering — det är alltid bättre än
    ingen vecka alls."""
    from fastapi.testclient import TestClient

    class HW:
        gpu_name = "T"; vram_mb = 1; has_cuda = False; ram_mb = 1; cpu_cores = 1
        free_disk_mb = 1; cpu_name = "T"; vram_free_mb = 1; ram_free_mb = 1
        total_disk_mb = 1; cuda_version = ""; compute_capability = ""
        gpu_arch = ""; disks = []

    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    client = TestClient(server.create_app(base_dir=tmp_path))
    monkeypatch.setattr(client.app.state.arbiter, "ensure_llm", lambda: None)
    monkeypatch.setattr(calendar_google, "_load_creds", lambda *a, **k: object())
    monkeypatch.setattr(calendar_google, "list_events", lambda *a, **k: [
        _tid("2026-08-17", "09:05", "10:20", summary="Matematik, nivå 2c NA25",
             recurringEventId="r1"),
        _heldag("Friluftsdag", "2026-09-11", "2026-09-12"),
    ])
    d = client.post("/api/schema/synk").json()
    assert d["bedomda"] == 0 and d["osakra"] == 1
    assert len(d["schema"]) == 1


def test_beslut_cachas_per_serie(conn):
    assert db.get_kalenderbeslut(conn) == {}
    db.save_kalenderbeslut(conn, {
        "mentorstid na25|tid|serie": {"slag": "post", "namn": "Mentorstid NA25"},
        "ma2c halvklass|tid|serie": {"slag": "lektion", "klass": "NA25",
                                     "kurs": "Matematik, nivå 2c"},
    })
    cache = db.get_kalenderbeslut(conn)
    assert cache["ma2c halvklass|tid|serie"]["kurs"] == "Matematik, nivå 2c"
    # Ett omtag skriver över i stället för att dubblera.
    db.save_kalenderbeslut(conn, {"mentorstid na25|tid|serie": {"slag": "ignorera"}})
    assert db.get_kalenderbeslut(conn)["mentorstid na25|tid|serie"]["slag"] == "ignorera"
    assert len(db.get_kalenderbeslut(conn)) == 2
