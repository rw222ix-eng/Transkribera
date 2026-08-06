"""Datagrunden (Etapp 0.1): veckoschemat, loven och kalenderposterna.

Kontraktet är FRONTENDENS. app/web/ui/kalender.js håller tre listor och läser
dem med bestämda fältnamn — testerna här låser exakt de namnen, för det är den
enda kopplingen mellan servern och veckovyn, terminsvyn, arkivets lovband och
köns schematräff. Byter ett fältnamn ska ett test falla, inte en tom vecka
ritas.
"""
import pytest

from app import calendar_google, db, lasar_data
from app.web import server


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
    return TestClient(server.create_app(base_dir=tmp_path))


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


SCHEMA_RADER = [
    {"dag": 1, "tid": "08:15–09:00", "kurs": "Matematik 3c", "klass": "9A", "sal": "A214"},
    {"dag": 1, "tid": "10:15–11:00", "kurs": "Matematik 4", "klass": "9B", "sal": "B103"},
    {"dag": 3, "tid": "08:15–09:00", "kurs": "Matematik 3c", "klass": "9A", "sal": "A214"},
]


# ------------------------------------------------------------------ schemat --

def test_schema_ror_sig_genom_databasen_med_frontendens_faltnamn(conn):
    ut = db.replace_schema(conn, SCHEMA_RADER)
    assert ut == SCHEMA_RADER                      # samma form in som ut
    assert db.list_schema(conn) == SCHEMA_RADER


def test_schema_sorteras_pa_dag_och_klockslag(conn):
    db.replace_schema(conn, list(reversed(SCHEMA_RADER)))
    ut = db.list_schema(conn)
    assert [(r["dag"], r["tid"]) for r in ut] == [(1, "08:15–09:00"), (1, "10:15–11:00"),
                                                  (3, "08:15–09:00")]


def test_schema_byts_ut_helt_inte_lagt_till(conn):
    db.replace_schema(conn, SCHEMA_RADER)
    db.replace_schema(conn, SCHEMA_RADER[:1])
    assert len(db.list_schema(conn)) == 1


def test_rader_utan_dag_eller_tid_hoppas_over(conn):
    """En rad som inte går att placera i veckan får inte bli en halv lektion."""
    ut = db.replace_schema(conn, [
        {"dag": 0, "tid": "08:15–09:00", "klass": "9A"},
        {"dag": 1, "tid": "", "klass": "9A"},
        {"dag": "tisdag", "tid": "09:00–10:00", "klass": "9A"},
        SCHEMA_RADER[0],
    ])
    assert ut == [SCHEMA_RADER[0]]


def test_klasser_och_kurser_skapas_en_gang(conn):
    db.replace_schema(conn, SCHEMA_RADER)
    db.replace_schema(conn, SCHEMA_RADER)
    assert [g["namn"] for g in db.list_groups(conn)] == ["9A", "9B"]


def test_tomt_schema_ar_ett_giltigt_svar(conn):
    """Appen hittar inte på lektioner för att fylla ut veckan."""
    db.replace_schema(conn, SCHEMA_RADER)
    assert db.replace_schema(conn, []) == []


# --------------------------------------------------------------------- lov --

LOV = [{"fran": "2026-10-26", "till": "2026-10-30", "namn": "Höstlov", "typ": "lov"}]


def test_seed_lov_ar_idempotent(conn):
    assert db.seed_lov(conn, LOV) == 1
    assert db.seed_lov(conn, LOV) == 0
    assert db.list_lov(conn) == LOV


def test_bundlad_lasarsdata_har_de_tre_typerna(conn):
    poster = lasar_data.load_lov()
    assert poster, "app/data/lasar/*.json måste finnas — annars ritas lovveckor som arbetsveckor"
    assert {p["typ"] for p in poster} <= {"lov", "dag", "uppehall"}
    assert all(p["fran"] <= p["till"] for p in poster)


def test_synk_ersatter_loven_men_seedning_skriver_aldrig_over(conn):
    db.seed_lov(conn, LOV)
    db.replace_lov(conn, [{"fran": "2027-02-22", "till": "2027-02-26",
                           "namn": "Sportlov", "typ": "lov"}])
    assert [p["namn"] for p in db.list_lov(conn)] == ["Sportlov"]
    db.seed_lov(conn, LOV)                          # appstart efter synken
    assert [p["namn"] for p in db.list_lov(conn)] == ["Höstlov", "Sportlov"]


# --------------------------------------------------------- kalenderposterna --

def test_kalenderpost_overlever_och_dubbleras_inte(conn):
    post = dict(datum="2026-08-19", tid="11:15–12:00",
                titel="Prov Matematik 4 — komplexa tal", klass="9B", slag="prov")
    assert db.add_kalenderpost(conn, **post)["klass"] == "9B"
    db.add_kalenderpost(conn, **post)               # godkänt två gånger
    assert len(db.list_kalenderposter(conn)) == 1
    assert db.list_kalenderposter(conn)[0]["slag"] == "prov"


def test_kalenderpost_kraver_datum_och_titel(conn):
    assert db.add_kalenderpost(conn, datum="", titel="Möte") is None
    assert db.add_kalenderpost(conn, datum="2026-08-19", titel="  ") is None


def test_synk_ror_bara_schemats_poster_inte_lararens(conn):
    """Frontendens två ursprung: 'schema' ägs av Google, 'appen' av läraren."""
    db.add_kalenderpost(conn, datum="2026-08-19", titel="Prov Ma4", klass="9B")
    db.replace_kalenderposter(conn, [{"datum": "2026-08-20", "tid": "13:00–14:30",
                                      "titel": "Ämneslagsmöte"}], kalla="schema")
    db.replace_kalenderposter(conn, [{"datum": "2026-08-21", "titel": "Utvecklingssamtal"}],
                              kalla="schema")
    titlar = sorted(p["titel"] for p in db.list_kalenderposter(conn))
    assert titlar == ["Prov Ma4", "Utvecklingssamtal"]


# ---------------------------------------------------------------- rutterna --

def test_api_schema_ger_de_tre_listorna(client):
    r = client.get("/api/schema")
    assert r.status_code == 200
    d = r.json()
    assert set(d) == {"schema", "lov", "poster"}
    # Loven seedas vid appstart — en färsk installation utan Google-konto ska
    # ändå veta när skolan är stängd.
    assert d["lov"], "loven seedas ur app/data/lasar vid create_app"
    # …och exempelschemat, så att planeringen går att prova innan Google är
    # kopplad. Skrivs över i sin helhet vid första synken.
    assert d["schema"], "exempelschemat seedas vid create_app"


def test_put_schema_och_las_tillbaka(client):
    r = client.put("/api/schema", json={"schema": SCHEMA_RADER})
    assert r.status_code == 200
    assert r.json()["schema"] == SCHEMA_RADER
    assert client.get("/api/schema").json()["schema"] == SCHEMA_RADER


def test_put_schema_tar_ocksa_en_naken_lista(client):
    assert client.put("/api/schema", json=SCHEMA_RADER).json()["schema"] == SCHEMA_RADER


def test_put_schema_avvisar_annat_an_lista(client):
    assert client.put("/api/schema", json={"schema": "måndag"}).status_code == 400


def test_post_kalenderpost(client):
    r = client.post("/api/kalenderposter",
                    json={"datum": "2026-09-03", "tid": "08:15–09:00",
                          "titel": "Prov Matematik 3c — integraler", "klass": "9A",
                          "slag": "prov"})
    assert r.status_code == 200
    assert r.json()["titel"] == "Prov Matematik 3c — integraler"
    # Posterna listas i datumordning bland exempelschemats mentorstider.
    egen = [p for p in client.get("/api/schema").json()["poster"]
            if p["titel"].startswith("Prov Matematik 3c")]
    assert egen and egen[0]["klass"] == "9A"


def test_post_kalenderpost_utan_titel_ar_400(client):
    assert client.post("/api/kalenderposter", json={"datum": "2026-09-03"}).status_code == 400


def test_synk_utan_google_lamnar_datan_ororda(client, monkeypatch):
    client.put("/api/schema", json={"schema": SCHEMA_RADER})
    monkeypatch.setattr(server.calendar_google, "read_schema",
                        lambda *a, **k: {"error": "Inte ansluten till Google Kalender"})
    r = client.post("/api/schema/synk")
    assert r.status_code == 409
    assert "Google" in r.json()["error"]
    assert client.get("/api/schema").json()["schema"] == SCHEMA_RADER


def test_synk_skriver_in_det_google_svarar(client, monkeypatch):
    monkeypatch.setattr(server.calendar_google, "read_schema", lambda *a, **k: {
        "schema": SCHEMA_RADER,
        "lov": [{"fran": "2026-10-26", "till": "2026-10-30", "namn": "Höstlov", "typ": "lov"}],
        "poster": [{"datum": "2026-08-20", "tid": "13:00–14:30", "titel": "Ämneslagsmöte"}],
    })
    d = client.post("/api/schema/synk").json()
    assert d["schema"] == SCHEMA_RADER
    assert [p["namn"] for p in d["lov"]] == ["Höstlov"]
    assert d["poster"][0]["titel"] == "Ämneslagsmöte"
    assert d["synkad"]


# ------------------------------------------------- tolkningen av Google-data --

def _tid(datum, fran, till, **extra):
    return dict({"summary": extra.pop("summary", "Lektion"),
                 "start": {"dateTime": f"{datum}T{fran}:00"},
                 "end": {"dateTime": f"{datum}T{till}:00"}}, **extra)


def test_aterkommande_handelse_med_klass_blir_veckoschema():
    ut = calendar_google.tolka_handelser([
        _tid("2026-08-17", "08:15", "09:00", summary="Matematik 3c 9A",
             location="A214", recurringEventId="r1"),
        _tid("2026-08-24", "08:15", "09:00", summary="Matematik 3c 9A",
             location="A214", recurringEventId="r1"),
    ])
    assert ut["schema"] == [{"dag": 1, "tid": "08:15–09:00", "kurs": "Matematik 3c",
                             "klass": "9A", "sal": "A214"}]


def test_kanda_namn_ur_databasen_vinner_over_monstret():
    ut = calendar_google.tolka_handelser(
        [_tid("2026-08-18", "09:15", "10:00", summary="Matematik, nivå 2 · NA22",
              recurringEventId="r2")],
        klasser=["NA22"], kurser=["Matematik, nivå 2"])
    assert ut["schema"][0]["klass"] == "NA22"
    assert ut["schema"][0]["kurs"] == "Matematik, nivå 2"


def test_aterkommande_utan_kant_kurs_blir_post_inte_lektion():
    """Mentorstiden och utvecklingssamtalen återkommer varje vecka och bär
    klassens namn — men de är inga lektioner att planera. Känner appen till
    sina kurser är det KURSEN som avgör."""
    ut = calendar_google.tolka_handelser(
        [_tid("2026-08-17", "08:25", "08:55", summary="Mentorstid NA25",
              recurringEventId="r9"),
         _tid("2026-08-17", "09:05", "10:20", summary="Matematik, nivå 2c NA25",
              location="P807", recurringEventId="r8")],
        klasser=["NA25"], kurser=["Matematik, nivå 2c"])
    assert [r["kurs"] for r in ut["schema"]] == ["Matematik, nivå 2c"]
    assert [p["titel"] for p in ut["poster"]] == ["Mentorstid NA25"]


def test_synk_utanfor_fonstret_raderar_inte_loven(conn):
    """En synk i augusti läser inte påsklovet nästa vår — och får därför inte
    radera det heller."""
    db.seed_lov(conn, [
        {"fran": "2026-10-26", "till": "2026-10-30", "namn": "Höstlov", "typ": "lov"},
        {"fran": "2027-03-29", "till": "2027-04-02", "namn": "Påsklov", "typ": "lov"},
    ])
    db.replace_lov(conn, [{"fran": "2026-10-26", "till": "2026-10-31",
                           "namn": "Höstlov", "typ": "lov"}],
                   fran="2026-08-01", till="2026-12-31")
    namn = [(p["namn"], p["till"]) for p in db.list_lov(conn)]
    assert namn == [("Höstlov", "2026-10-31"), ("Påsklov", "2027-04-02")]


def test_synk_utanfor_fonstret_raderar_inte_posterna(conn):
    db.replace_kalenderposter(conn, [
        {"datum": "2026-09-01", "titel": "Konferens"},
        {"datum": "2027-05-03", "titel": "Konferens"}], kalla="schema")
    db.replace_kalenderposter(conn, [{"datum": "2026-09-08", "titel": "Konferens"}],
                              kalla="schema", fran="2026-08-01", till="2026-12-31")
    assert [p["datum"] for p in db.list_kalenderposter(conn)] == ["2026-09-08", "2027-05-03"]


def test_engangshandelse_blir_post_inte_lektion():
    ut = calendar_google.tolka_handelser([_tid("2026-08-20", "13:00", "14:30",
                                               summary="Ämneslagsmöte")])
    assert ut["schema"] == []
    assert ut["poster"] == [{"datum": "2026-08-20", "tid": "13:00–14:30",
                             "titel": "Ämneslagsmöte", "klass": ""}]


def test_aterkommande_utan_klass_blir_post():
    """Hellre en post för mycket i kalendern än en påhittad lektion i schemat."""
    ut = calendar_google.tolka_handelser([_tid("2026-08-19", "15:00", "16:00",
                                               summary="Arbetslagsmöte",
                                               recurringEventId="r3")])
    assert ut["schema"] == [] and len(ut["poster"]) == 1


def test_heldagshandelse_med_lovord_blir_lov_med_inklusivt_slutdatum():
    ut = calendar_google.tolka_handelser([{
        "summary": "Höstlov",
        "start": {"date": "2026-10-26"},
        "end": {"date": "2026-10-31"},          # Google räknar slutet exklusivt
    }])
    assert ut["lov"] == [{"fran": "2026-10-26", "till": "2026-10-30",
                          "namn": "Höstlov", "typ": "lov"}]


def test_studiedag_blir_uppehall_och_endagslov_blir_dag():
    ut = calendar_google.tolka_handelser([
        {"summary": "Studiedag", "start": {"date": "2026-05-22"}, "end": {"date": "2026-05-23"}},
        {"summary": "Röd dag", "start": {"date": "2026-05-14"}, "end": {"date": "2026-05-15"}},
    ])
    assert {p["namn"]: p["typ"] for p in ut["lov"]} == {"Studiedag": "uppehall",
                                                        "Röd dag": "dag"}


# ------------------------------------------------------------ exempelschemat --

def test_exempelschemat_ar_en_hel_lararvecka():
    """Avritad ur ett publicerat gymnasieschema: fem dagar, fyra grupper, bara
    matematik (fysiken är utbytt), och kursnamn som finns i kursregistret så
    att det centrala innehållet går att välja."""
    d = lasar_data.load_exempelschema()
    rader = d["schema"]
    assert {r["dag"] for r in rader} == {1, 2, 3, 4, 5}
    assert len({r["klass"] for r in rader}) == 4
    assert all(r["sal"] and r["kurs"].startswith("Matematik") for r in rader)
    assert {r["kurs"] for r in rader} <= set(db.GY25_NIVAER), \
        "kursnamnen måste vara nivånamn — annars finns inget centralt innehåll"
    # Ingen grupp har två lektioner på samma tid samma dag.
    nycklar = [(r["dag"], r["tid"], r["klass"]) for r in rader]
    assert len(nycklar) == len(set(nycklar))


def test_aterkommande_poster_expanderas_over_lasaret_utan_lovdagar():
    lov = [{"fran": "2026-10-26", "till": "2026-10-30", "namn": "Höstlov", "typ": "lov"}]
    poster = lasar_data.expandera_poster(
        [{"dag": 1, "tid": "08:25–08:55", "titel": "Mentorstid", "klass": "NA25"}],
        "2026-10-19", "2026-11-09", lov)
    assert [p["datum"] for p in poster] == ["2026-10-19", "2026-11-02", "2026-11-09"]
    assert poster[0]["titel"] == "Mentorstid" and poster[0]["klass"] == "NA25"


def test_expandering_utan_giltigt_spann_ger_inget():
    assert lasar_data.expandera_poster([{"dag": 1, "titel": "X"}], "", "") == []


def test_exempelschemat_seedas_en_gang(client, tmp_path):
    """Läraren ska kunna prova planeringen direkt — men exempelveckan får inte
    komma tillbaka efter att hon synkat sin riktiga kalender."""
    d = client.get("/api/schema").json()
    assert len(d["schema"]) == len(lasar_data.load_exempelschema()["schema"])
    assert d["poster"], "mentorstid och konferenser skrivs ut vecka för vecka"
    assert all(not any(l["fran"] <= p["datum"] <= l["till"] for l in d["lov"])
               for p in d["poster"]), "inga poster på lovdagar"

    client.put("/api/schema", json={"schema": []})     # synk mot en tom kalender
    from app.web import server as srv
    srv.create_app(base_dir=tmp_path)                  # appen startas om
    assert client.get("/api/schema").json()["schema"] == []


# ------------------------------------------------- skriva ut till Google --

class FejkTjanst:
    """Minsta möjliga stand-in för googleapiclient — samlar det som skulle
    skickats så att kroppen går att granska utan ett Google-konto."""

    def __init__(self):
        self.skapade = []

    def events(self):
        return self

    def insert(self, calendarId=None, body=None):
        self.skapade.append(body)
        return self

    def execute(self):
        return {"id": "e" + str(len(self.skapade))}


@pytest.fixture
def google(monkeypatch):
    tjanst = FejkTjanst()
    monkeypatch.setattr(calendar_google, "_load_creds", lambda *a, **k: object())
    import sys, types
    modul = types.ModuleType("googleapiclient.discovery")
    modul.build = lambda *a, **k: tjanst
    paket = types.ModuleType("googleapiclient")
    paket.discovery = modul
    monkeypatch.setitem(sys.modules, "googleapiclient", paket)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", modul)
    return tjanst


def test_lektioner_skrivs_som_aterkommande_serier(google, tmp_path):
    """Det är ÅTERKOMMANDET som gör en händelse till en lektion när schemat
    läses tillbaka — skrivs de som enstaka händelser blir de kalenderposter."""
    svar = calendar_google.skriv_schema(
        tmp_path, schema=[SCHEMA_RADER[0]],
        termin={"fran": "2026-08-17", "till": "2026-12-18"}, lov=[])
    assert svar["skapade"] == 1 and svar["fel"] == []
    h = google.skapade[0]
    assert h["summary"] == "Matematik 3c 9A"          # kursen först, klassen sist
    assert h["location"] == "A214"
    assert h["start"]["dateTime"] == "2026-08-17T08:15:00"   # första måndagen
    assert h["end"]["dateTime"] == "2026-08-17T09:00:00"
    assert h["recurrence"][0].endswith("UNTIL=20261218T235959Z")


def test_lovdagar_undantas_ur_serien(google, tmp_path):
    calendar_google.skriv_schema(
        tmp_path, schema=[SCHEMA_RADER[0]],
        termin={"fran": "2026-08-17", "till": "2026-12-18"},
        lov=[{"fran": "2026-10-26", "till": "2026-10-30", "namn": "Höstlov", "typ": "lov"}])
    exdate = [r for r in google.skapade[0]["recurrence"] if r.startswith("EXDATE")]
    assert exdate and "20261026T081500" in exdate[0]


def test_loven_skrivs_som_heldagar_med_exklusivt_slut(google, tmp_path):
    calendar_google.skriv_schema(
        tmp_path, schema=[], termin={"fran": "2026-08-17", "till": "2027-06-11"},
        lov=[{"fran": "2026-10-26", "till": "2026-10-30", "namn": "Höstlov", "typ": "lov"}])
    h = google.skapade[0]
    assert h["start"]["date"] == "2026-10-26" and h["end"]["date"] == "2026-10-31"


def test_det_som_skrivs_ut_lases_tillbaka_som_samma_schema(google, tmp_path):
    """Kedjan hela vägen runt: skriv ut → läs tillbaka → samma vecka."""
    calendar_google.skriv_schema(
        tmp_path, schema=SCHEMA_RADER,
        termin={"fran": "2026-08-17", "till": "2026-12-18"}, lov=[])
    instanser = [dict(h, recurringEventId="r" + str(i))
                 for i, h in enumerate(google.skapade)]
    ut = calendar_google.tolka_handelser(instanser, klasser=["9A", "9B"],
                                         kurser=["Matematik 3c", "Matematik 4"])
    assert ut["schema"] == SCHEMA_RADER


def test_utan_google_kopplig_skrivs_ingenting(tmp_path, monkeypatch):
    monkeypatch.setattr(calendar_google, "_load_creds", lambda *a, **k: None)
    assert "error" in calendar_google.skriv_schema(
        tmp_path, schema=SCHEMA_RADER, termin={"fran": "2026-08-17", "till": "2027-06-11"})


def test_rutten_kraver_ett_schema(client, monkeypatch):
    monkeypatch.setattr(server.calendar_google, "skriv_schema",
                        lambda *a, **k: {"skapade": 17, "fel": []})
    assert client.post("/api/schema/till-google").json()["skapade"] == 17
    client.put("/api/schema", json={"schema": []})
    assert client.post("/api/schema/till-google").status_code == 409


def test_rada_dagar_kanns_igen_pa_sitt_namn():
    """«Långfredag» och «Kristi himmelsfärd» innehåller inte ordet lov — men
    skolan är stängd. Utan namnlistan såg en stängd dag öppen ut."""
    heldag = lambda namn, fran, till: {
        "summary": namn, "start": {"date": fran}, "end": {"date": till}}
    ut = calendar_google.tolka_handelser([
        heldag("Långfredag", "2027-03-26", "2027-03-27"),
        heldag("Kristi himmelsfärd", "2027-05-06", "2027-05-07"),
        heldag("Midsommarafton", "2027-06-25", "2027-06-26"),
    ])
    assert {p["namn"]: p["typ"] for p in ut["lov"]} == {
        "Långfredag": "dag", "Kristi himmelsfärd": "dag", "Midsommarafton": "dag"}


def test_heldagshandelse_utan_lovord_ignoreras():
    """En heldagsanteckning i kalendern stänger inte skolan."""
    ut = calendar_google.tolka_handelser([{
        "summary": "Öppet hus", "start": {"date": "2026-09-10"},
        "end": {"date": "2026-09-11"}}])
    assert ut["lov"] == [] and ut["poster"] == []
