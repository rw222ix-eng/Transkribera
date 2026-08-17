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
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


@pytest.fixture
def conn_v20(tmp_path):
    """En bas som den såg ut FÖRE v21: lektionsinnehall utan hjalpmedel-kolumn,
    med en rad redan i sig. Byggd genom att köra migrationerna, släppa kolumnen
    och stämpla tillbaka versionen — samma väg lärarens riktiga bas kommer att
    gå när den öppnas första gången efter uppdateringen."""
    fil = tmp_path / "gammal.db"
    c = db.connect(fil)
    db.replace_lektionsinnehall(c, [
        {"datum": "2026-08-17", "tid": "08:15–09:00", "klass": "NA26F",
         "kurs": "Matematik 1c", "fran": 2, "till": 6}])
    # SQLite kan släppa kolumner sedan 3.35; misslyckas det finns ingen v20 att
    # migrera FRÅN och testet har inget att säga.
    c.execute("ALTER TABLE lektionsinnehall DROP COLUMN hjalpmedel")
    c.execute("PRAGMA user_version=20")
    c.commit()
    c.close()
    db._initialized.discard(str(fil))     # tvinga migrationerna att köra igen
    c = db.connect(fil)
    yield c
    c.close()


@pytest.fixture
def conn_v21(tmp_path):
    """Samma sak en version senare: en bas FÖRE v22, alltså kalenderposter utan
    ci-kolumnerna och med ett prov redan i sig."""
    fil = tmp_path / "gammal21.db"
    c = db.connect(fil)
    db.replace_kalenderposter(c, [
        {"datum": "2026-10-01", "tid": "09:05–10:20", "titel": "PROV 1",
         "klass": "NA25", "slag": "prov"}])
    c.execute("ALTER TABLE kalenderposter DROP COLUMN ci")
    c.execute("ALTER TABLE kalenderposter DROP COLUMN ci_okant")
    c.execute("PRAGMA user_version=21")
    c.commit()
    c.close()
    db._initialized.discard(str(fil))
    c = db.connect(fil)
    yield c
    c.close()


# Tomma fran/till = gäller tills vidare, formen ett handskrivet schema har.
SCHEMA_RADER = [
    {"dag": 1, "tid": "08:15–09:00", "kurs": "Matematik 3c", "klass": "9A",
     "sal": "A214", "fran": "", "till": "", "undantag": []},
    {"dag": 1, "tid": "10:15–11:00", "kurs": "Matematik 4", "klass": "9B",
     "sal": "B103", "fran": "", "till": "", "undantag": []},
    {"dag": 3, "tid": "08:15–09:00", "kurs": "Matematik 3c", "klass": "9A",
     "sal": "A214", "fran": "", "till": "", "undantag": []},
]


# ------------------------------------------------------------------ schemat --

def test_schema_ror_sig_genom_databasen_med_frontendens_faltnamn(conn):
    ut = db.replace_schema(conn, SCHEMA_RADER)
    assert ut == SCHEMA_RADER                      # samma form in som ut
    assert db.list_schema(conn) == SCHEMA_RADER


def test_schemaradens_giltighet_overlever_databasen(conn):
    """Utan datumen i DB:t vore synkens arbete bortkastat vid nästa omladdning
    — veckovyn läser giltigheten härifrån, inte ur svaret."""
    ut = db.replace_schema(conn, [dict(SCHEMA_RADER[0], fran="2026-08-19",
                                       till="2026-12-16",
                                       undantag=["2026-09-03", "2026-10-09"])])
    assert (ut[0]["fran"], ut[0]["till"]) == ("2026-08-19", "2026-12-16")
    assert ut[0]["undantag"] == ["2026-09-03", "2026-10-09"]
    assert db.list_schema(conn) == ut


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


# ------------------------------------------------- lektionens eget innehåll --
# Sidorna gäller per LEKTIONSTILLFÄLLE. Veckoschemat är en rad per serie och
# kan inte bära dem — den här listan är dagens, och den har därför datum.

INNEHALL = [
    {"datum": "2026-08-17", "tid": "08:15–09:00", "klass": "NA26F",
     "kurs": "Matematik 1c", "fran": 2, "till": 6, "uppg": "1101–1103, 1105–1119"},
    {"datum": "2026-08-19", "tid": "10:15–11:00", "klass": "NA26F",
     "kurs": "Matematik 1c", "fran": 7, "till": 7},
]


def test_innehallet_ror_sig_genom_databasen_med_frontendens_faltnamn(conn):
    assert db.replace_lektionsinnehall(conn, INNEHALL) == INNEHALL
    assert db.list_lektionsinnehall(conn) == INNEHALL


def test_samma_lektion_last_tva_ganger_ar_en_rad(conn):
    """Synken är idempotent: UNIQUE på tillfället, inte på raden."""
    db.replace_lektionsinnehall(conn, INNEHALL + [dict(INNEHALL[0], fran=3, till=9)])
    ut = db.list_lektionsinnehall(conn)
    assert len(ut) == 2
    assert (ut[0]["fran"], ut[0]["till"]) == (3, 9)     # den sist lästa gäller


def test_rader_utan_sidor_hoppas_over(conn):
    """Utan sidor finns ingenting att bära — och ingen gissning görs här."""
    db.replace_lektionsinnehall(conn, [
        {"datum": "2026-08-17", "klass": "NA26F", "kurs": "Matematik 1c"},
        {"datum": "", "klass": "NA26F", "kurs": "Matematik 1c", "fran": 2, "till": 6},
    ])
    assert db.list_lektionsinnehall(conn) == []


def test_hjalpmedlet_skiljer_pa_tomt_och_osynkat(conn):
    """Provets upplägg («En del» / «Del A + Del B») förvalas ur hjälpmedlen som
    står på lektionerna. Då måste två svar hållas isär, och det är hela skälet
    till att kolumnen får vara NULL:

      ''    — synken HAR läst raden och inget verktyg nämndes.
      NULL  — raden skrevs innan kolumnen fanns (v21), ingen har tittat.

    Utan skillnaden hade appen sagt «inga digitala verktyg i planeringen» om en
    termin som aldrig lästs med hjälpmedelsögon. NULL utelämnas därför ur
    svaret, tom sträng följer med."""
    db.replace_lektionsinnehall(conn, [
        dict(INNEHALL[0], hjalpmedel="dator"),
        dict(INNEHALL[1], hjalpmedel=""),
        {"datum": "2026-08-21", "tid": "13:00–14:00", "klass": "NA26F",
         "kurs": "Matematik 1c", "fran": 8, "till": 9},      # nyckeln saknas
    ])
    ut = db.list_lektionsinnehall(conn)
    assert ut[0]["hjalpmedel"] == "dator"
    assert ut[1]["hjalpmedel"] == ""
    assert "hjalpmedel" not in ut[2]


def test_migrationen_till_v21_lamnar_gamla_rader_osynkade(conn_v20):
    """Kolumnen läggs till på en bas som redan har lektioner i sig, och de
    raderna ska komma ut UTAN nyckeln — inte med tom sträng. En migration som
    fyller i '' hade förvandlat hela terminen till «inga verktyg»."""
    ut = db.list_lektionsinnehall(conn_v20)
    assert len(ut) == 1
    assert "hjalpmedel" not in ut[0]
    assert ut[0]["fran"] == 2


def test_provets_innehall_ror_sig_genom_databasen_som_en_lista(conn):
    """Koderna lagras kommaseparerade (en kolumn, ingen tabell — det är fyra
    strängar per prov) men kommer ut som en LISTA, för det är formen
    window.Kalender bär dem i."""
    db.replace_kalenderposter(conn, [
        {"datum": "2026-10-01", "tid": "09:05–10:20", "titel": "PROV 1",
         "klass": "NA25", "slag": "prov",
         "ci": ["G25-M2C-ALG-2", "G25-M2C-ALG-6"], "ci_okant": 2},
        {"datum": "2026-10-02", "tid": "", "titel": "PROV 2", "klass": "NA25",
         "slag": "prov", "ci": []},
        {"datum": "2026-10-03", "tid": "", "titel": "Ämneslagsmöte", "klass": ""},
    ])
    ut = db.list_kalenderposter(conn)
    assert ut[0]["ci"] == ["G25-M2C-ALG-2", "G25-M2C-ALG-6"]
    assert ut[0]["ci_okant"] == 2
    # Läst utan träff: tom lista, och ingen okänd-räkning att visa.
    assert ut[1]["ci"] == []
    assert "ci_okant" not in ut[1]
    # Aldrig läst med Gy25-ögon: nyckeln finns inte alls.
    assert "ci" not in ut[2]


def test_lararens_egen_kalenderpost_far_inget_pastaende_om_innehall(conn):
    """Posten läraren godkänner i appen (Kalender.lagg) är ingen
    kalenderhändelse med en beskrivning att läsa — den ska komma ut UTAN
    ci-nyckeln, inte med en tom lista."""
    p = db.add_kalenderpost(conn, datum="2026-10-01", titel="Prov · NA25",
                            klass="NA25", slag="prov")
    assert "ci" not in p


def test_migrationen_till_v22_lamnar_gamla_poster_osynkade(conn_v21):
    """Kolumnerna läggs till på en bas som redan har prov i sig, och de posterna
    ska komma ut UTAN nyckeln — inte med en tom lista. En migration som fyller i
    '' hade påstått att varje gammalt prov är läst och saknar centralt
    innehåll."""
    ut = db.list_kalenderposter(conn_v21)
    assert len(ut) == 1
    assert "ci" not in ut[0]
    assert ut[0]["titel"] == "PROV 1"


def test_synk_utanfor_fonstret_raderar_inte_innehallet(conn):
    """Samma fönsterregel som loven och posterna: en synk i augusti får inte
    stryka sidorna som står på vårterminens lektioner."""
    db.replace_lektionsinnehall(conn, INNEHALL + [
        {"datum": "2027-03-02", "tid": "08:15–09:00", "klass": "NA26F",
         "kurs": "Matematik 1c", "fran": 210, "till": 216}])
    kvar = db.replace_lektionsinnehall(conn, [], fran="2026-08-01", till="2026-12-20")
    assert [p["datum"] for p in kvar] == ["2027-03-02"]


# ---------------------------------------------------------------- rutterna --

def test_api_schema_ger_de_tre_listorna(client):
    r = client.get("/api/schema")
    assert r.status_code == 200
    d = r.json()
    # …och sidorna på de enskilda lektionerna, som hämtas i samma svar: förvalen
    # sätts när veckan ritas, och ett andra anrop hade hunnit komma efter.
    assert set(d) == {"schema", "lov", "poster", "innehall"}
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


def test_synken_laser_hela_lasaret_framat(client, monkeypatch):
    """Skarpt fall (2026-08-10): med 210 dagars fönster slutade läsningen i
    mars, och de nationella proven i maj fanns inte för appen."""
    sett = {}
    monkeypatch.setattr(server.calendar_google, "read_schema",
                        lambda *a, **k: sett.update(k) or {"schema": [], "lov": [],
                                                           "poster": []})
    client.post("/api/schema/synk")
    assert sett["dagar"] >= 330


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


def test_synk_skriver_in_lektionernas_sidor(client, monkeypatch):
    """Sidorna ska ligga kvar efter synken — förvalen läser dem ur /api/schema,
    inte ur synksvaret."""
    monkeypatch.setattr(server.calendar_google, "read_schema", lambda *a, **k: {
        "schema": SCHEMA_RADER, "lov": [], "poster": [], "innehall": INNEHALL})
    d = client.post("/api/schema/synk").json()
    assert d["innehall"] == INNEHALL
    assert client.get("/api/schema").json()["innehall"] == INNEHALL


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
                             "klass": "9A", "sal": "A214",
                             # Giltigheten är seriens egna instanser: veckan får
                             # inte ritas före den första eller efter den sista.
                             "fran": "2026-08-17", "till": "2026-08-24",
                             "undantag": []}]


# ------------------------------------- sidorna som står på lektionen --

# Beskrivningen som den ser ut i lärarens kalender: innehållet överst, sedan
# avdelaren, och under den anteckningar om ENSKILDA ELEVER.
BESKRIVNING = """s. 2–6 · uppg. 1101–1103, 1105–1119
OBS! ta med miniräknare
———
MATE1C00X. HT-schema (period 35).
👤 Elev som behöver extra tid, se s. 400 i pärmen"""


def test_sidorna_och_uppgifterna_lases_ur_beskrivningen():
    assert calendar_google.sidor_ur_beskrivning(BESKRIVNING) == {
        "fran": 2, "till": 6, "uppg": "1101–1103, 1105–1119"}


def test_texten_under_avdelaren_lases_aldrig():
    """Integritetskravet, och villkoret för att beskrivningen läses alls:
    elevanteckningarna under ——— får varken tolkas eller komma ut. Sidan 400
    där nere finns inte för appen — sidorna är de som står ÖVER avdelaren."""
    assert calendar_google.sidor_ur_beskrivning(BESKRIVNING)["till"] == 6
    # Och en beskrivning som BARA är anteckningar ger ingenting alls.
    assert calendar_google.sidor_ur_beskrivning(
        "———\n👤 Eleven läser s. 88–92 enligt sitt åtgärdsprogram") == {}


def test_tva_avsnitt_pa_samma_lektion_ger_hela_strackan():
    """Lektionen som avslutar ett avsnitt och börjar nästa skrivs som två
    rader i kalendern — sidorna är hela sträckan, uppgifterna båda listorna."""
    assert calendar_google.sidor_ur_beskrivning(
        "Kubikrötter: s. 5–6 · uppg. 1116–1119\n"
        "Potenser: s. 7–9 · uppg. 1201–1203, 1205–1212\n"
        "OBS! ta med miniräknare") == {
        "fran": 5, "till": 9, "uppg": "1116–1119, 1201–1203, 1205–1212"}


@pytest.mark.parametrize("text, vantat", [
    ("s. 7", {"fran": 7, "till": 7}),                      # en ensam sida
    ("s. 2-6", {"fran": 2, "till": 6}),                    # vanligt bindestreck
    ("sid. 40–48", {"fran": 40, "till": 48}),
    ("Sidorna 12–14 · uppg 3101-3110",
     {"fran": 12, "till": 14, "uppg": "3101–3110"}),       # en form på spannen
    ("s. 5 · uppg. 1101, 1103,1109",
     {"fran": 5, "till": 5, "uppg": "1101, 1103, 1109"}),
    ("Genomgång av kvadratrötter", {}),                    # inga sidor → inget
    ("uppg. 1101–1103", {}),                               # uppgifter utan sidor
    ("", {}),
    (None, {}),
])
def test_sidformerna_som_star_i_kalendern(text, vantat):
    assert calendar_google.sidor_ur_beskrivning(text) == vantat


@pytest.mark.parametrize("text, titel, vantat", [
    ("OBS! ta med miniräknare", "", "raknare"),
    ("s. 2–6, räknaren behövs", "", "raknare"),
    ("Ta med räknare", "", "raknare"),
    ("Vi kör GeoGebra hela passet", "", "dator"),
    ("ta med datorn", "", "dator"),
    ("Alla datorer laddade!", "", "dator"),
    # Rubriken räknas också: läraren skriver ofta verktyget där.
    ("s. 12–14", "Ma1c NA26F · GeoGebra", "dator"),
    ("s. 12–14", "NA26F miniräknarpass", "raknare"),
    # Datorn väger tyngst när båda nämns — den öppnar hela verktygslådan.
    ("Räknare och dator", "", "dator"),
    # Inget verktyg är ett SVAR, inte ett tomrum: tom sträng, inte None.
    ("Genomgång av kvadratrötter", "", ""),
    ("", "", ""),
    (None, None, ""),
    # Ordgränsen: en kalkylator är inte en dator.
    ("Kalkylatorn på tavlan", "", ""),
])
def test_hjalpmedlen_lases_ur_lektionens_ord(text, titel, vantat):
    assert calendar_google.hjalpmedel_ur_text(text, titel) == vantat


def test_hjalpmedlen_lases_aldrig_under_avdelaren():
    """Samma integritetsregel som sidorna: allt under ——— är anteckningar om
    ENSKILDA ELEVER. En elev som har rätt till dator på prov får inte göra hela
    klassens prov tvådelat — och framför allt får texten aldrig läsas."""
    assert calendar_google.hjalpmedel_ur_text(
        "s. 2–6\n———\n👤 Eleven skriver på dator enligt sitt åtgärdsprogram") == ""


# ------------------------------- provets centrala innehåll ur beskrivningen --
# Läraren har skrivit in vilket centralt innehåll varje PROV berör, i provets
# egen kalenderhändelse. Punkterna är Gy25:s och hör till en NIVÅ — därför är
# gruppens kurser en del av frågan, inte en detalj: «Programmering» finns i både
# 1c och 2c, och ett prov i 2c får aldrig förvälja en punkt ur 1c.
#
# Testerna nedan låser KALIBRERINGEN, inte bara funktionen: vad som ska matcha,
# och lika viktigt vad som medvetet INTE ska göra det.

TVAC = ["Matematik, nivå 2c"]


@pytest.mark.parametrize("text, vantat", [
    # 1. Koden själv — identitet, ingen tolkning.
    ("G25-M2C-ALG-2", ["G25-M2C-ALG-2"]),
    ("g25-m2c-alg-2 och g25-m2c-sta-3", ["G25-M2C-ALG-2", "G25-M2C-STA-3"]),
    # 2. Etiketten läraren ser i väljaren, som en hel ordföljd.
    ("Andragradsekvationer", ["G25-M2C-ALG-6"]),
    ("- Logaritmer\n- Rotekvationer", ["G25-M2C-ALG-2", "G25-M2C-ALG-7"]),
    ("Provet handlar om kvadreringsregler.", ["G25-M2C-ALG-4"]),
    # Åt andra hållet också: raden är kortare än etiketten men står i den.
    ("Normalfördelning", ["G25-M2C-STA-2"]),
    # 3. Skolverkets ordagranna text, för den som klistrar in ämnesplanen.
    ("Metoder för att lösa andragradsekvationer och rotekvationer samt "
     "bestämning av polynomfunktioners nollställen.",
     ["G25-M2C-ALG-6", "G25-M2C-ALG-7"]),
    # Ordgränsen: ekvationSSYSTEM är en annan punkt än ekvationer.
    ("Linjära ekvationssystem", ["G25-M2C-ALG-1"]),
    # Det som inte är innehåll säger ingenting: sidor, uppgifter, kapitel, sal.
    ("s. 2–48 · uppg. 1101–1230", []),
    ("Kap 1 och 2", []),
    ("Sal E107", []),
    ("", []),
    (None, []),
])
def test_punkterna_som_kanns_igen_i_provets_beskrivning(text, vantat):
    assert calendar_google.centralt_innehall_ur_text(text, "", TVAC)[0] == vantat


def test_punkterna_hor_till_gruppens_egen_niva():
    """Kalibreringens viktigaste gräns. «Logaritmer» finns i 2c, inte i 1c — och
    en grupp som bara läser 1c ska inte få 2c:s punkt förvald bara för att ordet
    står i kalendern. Utan kurser alls matchas ingenting: appen gissar hellre
    ingen nivå än fel."""
    assert calendar_google.centralt_innehall_ur_text(
        "Logaritmer", "", ["Matematik, nivå 1c"]) == ([], 0)
    assert calendar_google.centralt_innehall_ur_text("Logaritmer", "", []) == ([], 0)
    # Kursen står i lärarens schema i flera former — alla ska duga.
    for form in ("Ma2c", "Matematik 2c", "MATE2C00X", "Matematik, nivå 2c"):
        assert calendar_google.centralt_innehall_ur_text(
            "Logaritmer", "", [form])[0] == ["G25-M2C-ALG-2"]


BADA = ["Matematik, nivå 1c", "Matematik, nivå 2c"]


def test_tvetydig_rad_hoppas_over_och_raknas_som_okand():
    """«Programmering» är en punkt i BÅDE 1c och 2c, och lärarens klasser läser
    faktiskt båda samma läsår (NA26F och TE26A i den riktiga basen). Står raden
    ensam går det inte att avgöra vilken nivå hon menar, och då är tystnad rätt
    svar: hellre för få förvalda punkter än fel. Raden räknas i stället som
    okänd, så att förvalet kan säga att den fanns."""
    assert calendar_google.centralt_innehall_ur_text(
        "Programmering", "", BADA) == ([], 0)
    # Pekar beskrivningens övriga rader åt VAR SITT håll är den fortfarande
    # oavgjord — då vet vi bara att provet spänner över två nivåer.
    koder, okanda = calendar_google.centralt_innehall_ur_text(
        "Logaritmer\nFunktionsbegreppet\nProgrammering", "", BADA)
    assert koder == ["G25-M2C-ALG-2", "G25-M1C-ALG-2"]
    assert okanda == 1


def test_beskrivningen_sjalv_avgor_den_tvetydiga_raden():
    """Har de entydiga raderna pekat ut EN nivå är provets nivå avgjord av
    texten själv, och då läses den delade punkten där. Utan det här hade fem
    punkter — programmering, problemlösning, digitala verktyg, matematiska
    modeller, matematikens historia — aldrig kunnat förväljas för de två klasser
    som läser både 1c och 2c."""
    assert calendar_google.centralt_innehall_ur_text(
        "Logaritmer\nProgrammering", "", BADA) == (
        ["G25-M2C-ALG-2", "G25-M2C-DIG-2"], 0)
    # Koden i rubriken duger lika bra som avgörare — den bär sin nivå i sig.
    assert calendar_google.centralt_innehall_ur_text(
        "Programmering", "PROV 1 · G25-M1C-ALG-2", BADA) == (
        ["G25-M1C-ALG-2", "G25-M1C-DIG-3"], 0)


def test_okanda_rader_raknas_bara_nar_nagot_kandes_igen():
    """En beskrivning där INGENTING matchar handlar om något annat än centralt
    innehåll — att anmäla den som «tre rader kändes inte igen» vore att klaga på
    en text som aldrig lovade något. Räkningen börjar först när minst en punkt
    är funnen."""
    assert calendar_google.centralt_innehall_ur_text(
        "Vi ses i E107\nTa med legitimation\nProvet börjar 08:15", "", TVAC) == ([], 0)
    koder, okanda = calendar_google.centralt_innehall_ur_text(
        "Logaritmer\nAllt vi hann med i höstas\nOch lite till", "", TVAC)
    assert koder == ["G25-M2C-ALG-2"]
    assert okanda == 2
    # Hjälpmedelsraden är inte en obegriplig innehållsrad: den frågan besvarar
    # synken på annat håll (hjalpmedel_ur_text).
    assert calendar_google.centralt_innehall_ur_text(
        "Logaritmer\nTa med räknare", "", TVAC) == (["G25-M2C-ALG-2"], 0)


def test_rubriken_bidrar_med_koder_men_aldrig_med_okanda_rader():
    """Rubriken är en rubrik («NA26F: PROV 1 (kap 1 och 2)»), inte ett påstående
    om innehåll — den får ge en kod men aldrig anmäla sig som obegriplig."""
    assert calendar_google.centralt_innehall_ur_text(
        "Logaritmer", "PROV 1 · G25-M2C-STA-2", TVAC) == (
        ["G25-M2C-STA-2", "G25-M2C-ALG-2"], 0)
    assert calendar_google.centralt_innehall_ur_text(
        "Logaritmer", "NA26F: PROV 1 (kap 1 och 2)", TVAC) == (
        ["G25-M2C-ALG-2"], 0)


def test_innehallet_lases_aldrig_under_avdelaren():
    """Samma integritetsregel som sidorna och hjälpmedlen: allt under ——— är
    anteckningar om ENSKILDA ELEVER och får varken tolkas eller komma ut. Att en
    elev kämpar med normalfördelningen är inte provets centrala innehåll."""
    assert calendar_google.centralt_innehall_ur_text(
        "Logaritmer\n———\n👤 Eleven klarar inte normalfördelning", "", TVAC) == (
        ["G25-M2C-ALG-2"], 0)


def test_provets_innehall_faller_ut_ur_synken():
    """Hela vägen: två lektioner ger klassens kurs, provhändelsen ger
    beskrivningen, och posten kommer ut med sina koder. `ci` sätts på VARJE prov
    — tom lista är svaret «läst, ingenting nämnt» — men aldrig på något annat i
    kalendern."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-09-07", "09:05", "10:20", summary="Matematik, nivå 2c NA25",
             location="E107", recurringEventId="r1"),
        _tid("2026-09-14", "09:05", "10:20", summary="Matematik, nivå 2c NA25",
             location="E107", recurringEventId="r1"),
        _tid("2026-10-01", "09:05", "10:20", summary="NA25: PROV 1 (kap 1 och 2)",
             description="Logaritmer\nAndragradsekvationer\nTa med räknare"),
        _tid("2026-10-02", "13:00", "14:30", summary="Ämneslagsmöte"),
    ], klasser=["NA25"], kurser=["Matematik, nivå 2c"], idag="2026-09-07")
    prov = [p for p in ut["poster"] if p.get("slag") == "prov"]
    assert len(prov) == 1
    assert prov[0]["ci"] == ["G25-M2C-ALG-2", "G25-M2C-ALG-6"]
    assert "ci_okant" not in prov[0]
    # Mötet är inget prov och läses aldrig med Gy25-ögon.
    assert all("ci" not in p for p in ut["poster"] if p.get("slag") != "prov")


def test_provet_utan_igenkant_innehall_far_tom_lista_inte_ingen():
    """Skillnaden mellan «läst utan träff» och «aldrig läst» måste bära hela
    vägen ut — det är den som avgör om förvalet får säga något alls."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-09-07", "09:05", "10:20", summary="Matematik, nivå 2c NA25",
             recurringEventId="r1"),
        _tid("2026-10-01", "09:05", "10:20", summary="NA25: PROV 1",
             description="Vi ses i E107"),
    ], klasser=["NA25"], kurser=["Matematik, nivå 2c"], idag="2026-09-07")
    prov = [p for p in ut["poster"] if p.get("slag") == "prov"][0]
    assert prov["ci"] == []


def test_nationella_provet_far_inget_forval():
    """NP är inte lärarens att skriva — det ligger i kalendern som en tid att
    hålla, inte som en uppgift att göra (samma skäl som klass.js `egetProv`)."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-09-07", "09:05", "10:20", summary="Matematik, nivå 2c NA25",
             recurringEventId="r1"),
        _tid("2026-11-10", "09:00", "12:00", summary="NP MAT nivå 2c NA25",
             description="Logaritmer"),
    ], klasser=["NA25"], kurser=["Matematik, nivå 2c"], idag="2026-09-07")
    np = [p for p in ut["poster"] if p.get("slag") == "np"][0]
    assert "ci" not in np


def test_rutan_i_schemat_racker_som_kurskalla_for_provet():
    """Gruppens kurs behöver inte stå i en lektionshändelse den här veckan —
    schemat appen redan har (schema_lektioner) vet vad NA26F läser, och det är
    det som gör provets punkter avgörbara även när kalendern bara bär provet."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-10-01", "10:00", "11:30", summary="NA26F: PROV 1",
             description="Funktionsbegreppet"),
    ], klasser=["NA26F"], idag="2026-09-07", schema_nu=SCHEMAT)
    prov = [p for p in ut["poster"] if p.get("slag") == "prov"][0]
    assert prov["ci"] == ["G25-M1C-ALG-2"]


def test_innehallet_hanger_pa_lektionstillfallet_inte_pa_serien():
    """Samma serie, två veckor, olika sidor. Schemaraden är EN — innehållet
    är två, ett per datum."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-08-17", "08:15", "09:00", summary="Matematik 3c 9A",
             location="A214", recurringEventId="r1", description=BESKRIVNING),
        _tid("2026-08-24", "08:15", "09:00", summary="Matematik 3c 9A",
             location="A214", recurringEventId="r1", description="s. 7–11"),
    ], idag="2026-08-17")
    assert len(ut["schema"]) == 1
    # `hjalpmedel` sätts på VARJE rad, också när ingenting nämns: tom sträng
    # betyder «läst, inget hittat» och är ett annat svar än NULL i basen (raden
    # skrevs innan kolumnen fanns). Provets upplägg skiljer på dem.
    assert ut["innehall"] == [
        {"datum": "2026-08-17", "tid": "08:15–09:00", "klass": "9A",
         "kurs": "Matematik 3c", "fran": 2, "till": 6,
         "hjalpmedel": "raknare", "uppg": "1101–1103, 1105–1119"},
        {"datum": "2026-08-24", "tid": "08:15–09:00", "klass": "9A",
         "kurs": "Matematik 3c", "fran": 7, "till": 11, "hjalpmedel": ""},
    ]


SCHEMAT = [{"dag": 1, "tid": "10:00–11:30", "klass": "NA26F",
            "kurs": "Matematik, nivå 1c", "sal": "E107"},
           {"dag": 1, "tid": "13:00–14:00", "klass": "NA26F", "kurs": "", "sal": ""}]


def test_rubriken_som_sager_amnet_kanns_igen_pa_rutan_i_schemat():
    """«NA26F: Kvadratrötter och kubikrötter» — läraren skriver ämnet, aldrig
    kursnamnet. Utan schemat blir varje sådan lektion en osäker SERIE (rubriken
    byts varje vecka, så inget beslut går att cacha) och sidorna når aldrig
    fram. Ligger den i en ruta appen redan har, och bär beskrivningen sidor, är
    saken avgjord utan att någon behöver frågas."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-08-24", "10:00", "11:30",
             summary="NA26F: Kvadratrötter och kubikrötter", location="E107",
             recurringEventId="r1", description=BESKRIVNING),
    ], klasser=["NA26F"], kurser=["Matematik, nivå 1c"],
        idag="2026-08-24", schema_nu=SCHEMAT)
    assert ut["osakra"] == []
    assert ut["poster"] == []
    assert ut["schema"][0]["kurs"] == "Matematik, nivå 1c"
    assert ut["innehall"] == [
        {"datum": "2026-08-24", "tid": "10:00–11:30", "klass": "NA26F",
         "kurs": "Matematik, nivå 1c", "fran": 2, "till": 6,
         "hjalpmedel": "raknare", "uppg": "1101–1103, 1105–1119"}]


@pytest.mark.parametrize("summary, tid, beskrivning, schema", [
    # Mentorstiden ligger också i en ruta — men den har inga sidor.
    ("Mentorstid NA26F", "10:00", "Vi går igenom frånvaron", SCHEMAT),
    # Sidor, men ingen ruta på den tiden: appen hittar inte på en lektion.
    ("NA26F: Potenser", "15:00", BESKRIVNING, SCHEMAT),
    # Rutan finns men står utan kurs — då säger den ingenting.
    ("NA26F: Potenser", "13:00", BESKRIVNING, SCHEMAT),
    ("NA26F: Potenser", "10:00", BESKRIVNING, []),
])
def test_rutan_avgor_bara_nar_bagge_villkoren_haller(summary, tid, beskrivning, schema):
    ut = calendar_google.tolka_handelser([
        _tid("2026-08-24", tid, "16:00", summary=summary,
             recurringEventId="r1", description=beskrivning),
    ], klasser=["NA26F"], kurser=["Matematik, nivå 1c"],
        idag="2026-08-24", schema_nu=schema)
    assert ut["schema"] == [] and ut["innehall"] == []
    assert len(ut["osakra"]) == 1           # ligger kvar som en fråga till Claude


def test_lektion_utan_sidor_ger_inget_innehall():
    """Ingen gissning: står det inga sidor i kalendern gäller klassprofilens
    förval, precis som innan."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-08-17", "08:15", "09:00", summary="Matematik 3c 9A",
             recurringEventId="r1"),
        _tid("2026-08-24", "08:15", "09:00", summary="Matematik 3c 9A",
             recurringEventId="r1", description="Vi fortsätter där vi slutade"),
    ], idag="2026-08-17")
    assert ut["innehall"] == []


def test_bara_lektioner_bar_innehall():
    """Mötet på tisdag är ingen lektion, och «s. 3–4» i dess beskrivning är
    dagordningen — den ska inte bli ett sidspann i planeringen."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-08-18", "13:00", "14:30", summary="Ämneslagsmöte",
             recurringEventId="r9", description="s. 3–4 i handlingarna"),
        _tid("2026-08-18", "15:00", "16:00", summary="Utvecklingssamtal",
             description="s. 12"),
    ], idag="2026-08-18")
    assert ut["innehall"] == []


def test_proven_markeras_som_prov():
    """Ett prov är en tid att hålla, inte ett möte — appen erbjuder att planera
    det och terminsvyn räknar det. Skolans NP heter «NP MAT nivå 1c» och
    innehåller varken «prov» eller «nationell», så titelgissningen missade dem
    helt (2026-08-10)."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-12-15", "09:00", "14:20", summary="NP MAT nivå 1c (NA26) – berör NA26F"),
        _tid("2026-11-05", "08:10", "09:40", summary="Prov kapitel 3 – TE26A"),
        _tid("2026-09-08", "13:00", "14:30", summary="Ämneslagsmöte"),
    ], klasser=["NA26F", "TE26A"])
    slag = {p["titel"]: p.get("slag") for p in ut["poster"]}
    assert slag == {"NP MAT nivå 1c (NA26) – berör NA26F": "np",
                    "Prov kapitel 3 – TE26A": "prov",
                    "Ämneslagsmöte": None}


@pytest.mark.parametrize("titel, vantat", [
    ("NP MAT nivå 1c (NA26)", "np"),
    ("Nationellt prov MA 2c", "np"),
    ("Prov kapitel 3", "prov"),
    ("Omprov bråk", "prov"),
    ("Provet flyttat till fredag", "prov"),
    # Ordgränserna är hela poängen: en föreläsning om provteori är ingen
    # provtid, och en prövning är något helt annat.
    ("4UVÄ18 Föreläsning 4: Provteori (Zoom)", None),
    ("Prövning bokad: Malmö – Försvarsmakten", None),
    ("Ämneslagsmöte", None),
    # Diagnosen skrivs ihop: skolan skriver «Matematikdiagnos åk 1», och
    # ordgränser hade missat den. Den är också det precisa ordet när båda står.
    ("Matematikdiagnos åk 1 genomförs under veckan", "diagnos"),
    ("Diagnos 2 – bråk och procent", "diagnos"),
    ("Diagnostiskt prov MA 1c", "diagnos"),
])
def test_provslag_pa_ordet_inte_pa_bokstaverna(titel, vantat):
    assert calendar_google.provslag(titel) == vantat


def test_annat_programs_loggrad_blir_ingen_post():
    """Skarpt fall (2026-08-10): lärarens automatiska synk mellan skol- och
    privatkalendern skriver «Synk: 7 nytt – se beskrivning» som en
    femminuterspunkt markerad ledig. Ingen lektion, inget möte, inget prov."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-09-07", "07:30", "07:35", summary="Synk: 7 nytt – se beskrivning.",
             transparency="transparent"),
        _tid("2026-09-07", "13:00", "14:30", summary="Ämneslagsmöte"),
    ])
    assert [p["titel"] for p in ut["poster"]] == ["Ämneslagsmöte"]
    assert ut["notiser"] == 1


def test_kort_handelse_som_bokar_tid_ar_ingen_notis():
    """Det är LEDIGmarkeringen som gör en punkt till en notis. En kort
    händelse som faktiskt tar tid i anspråk är en post som alla andra."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-09-07", "07:30", "07:35", summary="Ring rektorn"),
        _tid("2026-09-08", "08:00", "08:05", summary="Hämta nycklar",
             transparency="transparent", location="Expeditionen"),
    ])
    assert [p["titel"] for p in ut["poster"]] == ["Ring rektorn", "Hämta nycklar"]
    assert ut["notiser"] == 0


def test_lang_ledigmarkerad_handelse_ar_ingen_notis():
    """Gymnasiemässan och friluftsdagen står som «ledig» men är hela dagar som
    påverkar undervisningen — de ska inte försvinna."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-10-09", "08:00", "16:00", summary="Gymnasiemässa",
             transparency="transparent"),
    ])
    assert [p["titel"] for p in ut["poster"]] == ["Gymnasiemässa"]
    assert ut["notiser"] == 0


def test_schemaraden_bar_seriens_forsta_och_sista_dag():
    """Skarpt fall (2026-08-10): appen ritade höstens lektioner på
    uppstartsveckan i augusti — läraren hade möten, inte lektioner. Ett
    veckoschema utan giltighet gäller varenda vecka som finns."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-08-19", "08:10", "09:40", summary="Matematik, nivå 1c TE26A",
             location="B204", recurringEventId="ht"),
        _tid("2026-12-16", "08:10", "09:40", summary="Matematik, nivå 1c TE26A",
             location="B204", recurringEventId="ht"),
    ], klasser=["TE26A"], kurser=["Matematik, nivå 1c"], idag="2026-08-10",
        fonster_till="2027-03-08")
    assert ut["schema"][0]["fran"] == "2026-08-19"
    assert ut["schema"][0]["till"] == "2026-12-16"


def test_installd_lektion_blir_ett_undantag():
    """Skarpt fall (2026-08-10): Kaggdagen och gymnasiemässan strök tre
    lektioner ur kalendern, men mönstret ritade dem ändå. Kalendern visste —
    instansen fanns inte — och nu skrivs den kunskapen ner."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-09-07", "08:10", "09:40", summary="Matematik, nivå 1c TE26A",
             location="B204", recurringEventId="r"),
        # 14/9 saknas: lektionen är inställd.
        _tid("2026-09-21", "08:10", "09:40", summary="Matematik, nivå 1c TE26A",
             location="B204", recurringEventId="r"),
    ], klasser=["TE26A"], kurser=["Matematik, nivå 1c"], idag="2026-08-10")
    assert ut["schema"][0]["undantag"] == ["2026-09-14"]


def test_lovveckor_raknas_inte_som_undantag():
    """Loven ritas redan som stängda. Att lista varenda lovdag som ett undantag
    hade gjort raderna oläsliga utan att ändra en enda vecka."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-10-19", "08:10", "09:40", summary="Matematik, nivå 1c TE26A",
             location="B204", recurringEventId="r"),
        {"summary": "Höstlov", "start": {"date": "2026-10-26"},
         "end": {"date": "2026-10-31"}},
        _tid("2026-11-02", "08:10", "09:40", summary="Matematik, nivå 1c TE26A",
             location="B204", recurringEventId="r"),
    ], klasser=["TE26A"], kurser=["Matematik, nivå 1c"], idag="2026-08-10")
    assert ut["schema"][0]["undantag"] == []


def test_serie_som_nar_fonstrets_kant_far_oppet_slut():
    """Sista instansen ligger vid kanten av det synken hann läsa — då är slutet
    okänt. Ett satt `till` hade tömt veckovyn sju månader fram."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-08-19", "08:10", "09:40", summary="Matematik, nivå 1c TE26A",
             location="B204", recurringEventId="ht"),
        _tid("2027-03-03", "08:10", "09:40", summary="Matematik, nivå 1c TE26A",
             location="B204", recurringEventId="ht"),
    ], klasser=["TE26A"], kurser=["Matematik, nivå 1c"], idag="2026-08-10",
        fonster_till="2027-03-08")
    assert ut["schema"][0]["fran"] == "2026-08-19"
    assert ut["schema"][0]["till"] == ""


def test_serie_som_tagit_slut_ligger_inte_kvar_i_veckan():
    """Läsfönstret går 240 dagar BAKÅT för lovens och arkivets skull — men
    vårterminens serier ska inte dyka upp i höstens vecka. Skarpt fall
    (2026-08-10): tre lektioner ur april låg kvar bredvid höstens schema."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-04-20", "14:40", "15:25", summary="Matematik, nivå 2a IN24prk",
             location="P807", recurringEventId="vt"),
        _tid("2026-08-17", "08:10", "09:40", summary="Matematik, nivå 1c TE26A",
             location="B204", recurringEventId="ht"),
    ], klasser=["IN24prk", "TE26A"],
        kurser=["Matematik, nivå 2a", "Matematik, nivå 1c"], idag="2026-08-10")
    assert [r["klass"] for r in ut["schema"]] == ["TE26A"]


def test_serie_som_fortfarande_gar_behalls_fast_den_borjade_i_varas():
    """Det är sista instansen som avgör, inte den första — en kurs som löper
    över läsårsskiftet är samma serie hela vägen."""
    ut = calendar_google.tolka_handelser([
        _tid("2026-04-20", "14:40", "15:25", summary="Matematik, nivå 2a IN24prk",
             location="P807", recurringEventId="r"),
        _tid("2026-09-07", "14:40", "15:25", summary="Matematik, nivå 2a IN24prk",
             location="P807", recurringEventId="r"),
    ], klasser=["IN24prk"], kurser=["Matematik, nivå 2a"], idag="2026-08-10")
    assert [r["klass"] for r in ut["schema"]] == ["IN24prk"]


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
    # Attrappen expanderar inte serierna, så varje rad ses en enda gång och
    # giltigheten blir den dagen. Testet handlar om att lektionerna kommer
    # tillbaka som samma vecka — inte om datumen.
    utan = lambda rader: [{k: v for k, v in r.items() if k not in ("fran", "till", "undantag")}
                          for r in rader]
    assert utan(ut["schema"]) == utan(SCHEMA_RADER)


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
