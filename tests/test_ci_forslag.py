"""CI-förvalet: punkterna väljs ur det läraren utgår från (2026-09-06).

Lärarens beställning: «AI-modellen ska analysera det man utgår ifrån, scanna
innehållet och korskorrelera det med det centrala innehållet så att punkterna
kan väljas automatiskt. Tydligt kopplat, inte långsökt.»

Tre saker prövas, och de tre är hela modulen: att FRÅGAN bär nivåns punkter och
lärarens material, att SVARET filtreras mot nivån och aldrig fäller begäran, och
att KÄLLTEXTEN bara innehåller det som faktiskt finns (aldrig en oläst sida).
"""
from __future__ import annotations

import json

from app import ci_forslag, db


def _events(resp) -> list[dict]:
    return [json.loads(line[len("data:"):])
            for line in resp.text.splitlines() if line.startswith("data:")]


def _done(resp) -> dict:
    evs = [e for e in _events(resp) if e["type"] == "done"]
    assert evs, _events(resp)
    return evs[0]["result"]


def _punkter():
    return ci_forslag.nivans_punkter("mate/2a")


def _svar(data: dict):
    """En llm som svarar med `data` som JSON — samma väg som en riktig modell:
    texten går genom regex- och JSON-läsningen, inte förbi den."""
    return lambda model, prompt, **kw: json.dumps(data, ensure_ascii=False)


# ── nivån ────────────────────────────────────────────────────────────────────

def test_nivaid_ger_nivans_alla_punkter():
    punkter = _punkter()
    koder = [p["kod"] for p in punkter]
    assert "G25-M2A-ALG-8" in koder and "G25-M2A-GEO-1" in koder
    # Bara nivåns egna: 2c:s koder får aldrig komma med i 2a:s lista.
    assert not [k for k in koder if not k.startswith("G25-M2A-")]


def test_okand_niva_ger_tom_lista():
    assert ci_forslag.nivans_punkter("mate/9z") == []
    assert ci_forslag.nivans_punkter("") == []


# ── prompten ─────────────────────────────────────────────────────────────────

def test_prompten_bar_markoren_alla_koder_och_kalltexten():
    punkter = _punkter()
    p = ci_forslag.build_ci_prompt(punkter, "UR BOKEN: pq-formeln på s. 55.",
                                   "2.3 Andragradsekvationer")
    # Markören är fejk-CLI:ts nyckel (tests/fejk.py _auto) — utan den spelas
    # fel band upp, och kassetten mäter något annat än den ska.
    assert ci_forslag.MARKOR in p
    for punkt in punkter:
        assert punkt["kod"] in p, punkt["kod"]
        assert punkt["kort"] in p
    assert "pq-formeln på s. 55" in p
    assert "2.3 Andragradsekvationer" in p


def test_prompten_ber_aldrig_om_tackning_eller_gissningar():
    """Täckningsdomaren på tavlan letar luckor med flit. Det här är motsatsen:
    en punkt som kryssas i «för säkerhets skull» är en punkt läraren måste
    klicka bort, och då är förvalet värre än inget förval."""
    p = ci_forslag.build_ci_prompt(_punkter(), "material", "")
    lag = p.lower()
    assert "gissa" not in lag
    assert "täck" not in lag
    assert "tomma" in lag          # tomt svar ska stå som ett giltigt svar


def test_markoren_star_bara_i_den_har_prompten():
    """Auto-läget väljer band på frasen. Står den i två prompter väljs fel band
    i den ena, och det syns först som ett obegripligt testfel någon annanstans."""
    from pathlib import Path

    rot = Path(__file__).resolve().parent.parent / "app"
    traff = [f for f in rot.rglob("*.py")
             if ci_forslag.MARKOR in f.read_text(encoding="utf-8")]
    assert [f.name for f in traff] == ["ci_forslag.py"]


# ── svaret ───────────────────────────────────────────────────────────────────

def test_foresla_tar_punkterna_och_skalen():
    res = ci_forslag.foresla(
        _punkter(), "UR BOKEN: pq-formeln.", "Andragradsekvationer",
        llm=_svar({"punkter": [{"kod": "G25-M2A-ALG-8", "skal": "s. 55 pq-formeln"}],
                   "osakra": [{"kod": "G25-M2A-ALG-7", "skal": "nämns kort"}]}))
    assert res["punkter"] == [{"kod": "G25-M2A-ALG-8", "skal": "s. 55 pq-formeln"}]
    assert res["osakra"] == [{"kod": "G25-M2A-ALG-7", "skal": "nämns kort"}]
    assert res["tomt_skal"] == ""


def test_koder_som_inte_finns_i_nivan_slapps_aldrig_igenom():
    """Koden är identiteten (course_data). En kod ur en annan kurs, eller en
    påhittad, skulle bli en bricka läraren inte kan tolka."""
    res = ci_forslag.foresla(
        _punkter(), "material",
        llm=_svar({"punkter": [{"kod": "G25-M2C-ALG-1", "skal": "fel kurs"},
                               {"kod": "PÅHITTAD", "skal": "finns inte"},
                               {"kod": "G25-M2A-ALG-8", "skal": "riktig"}],
                   "osakra": []}))
    assert [p["kod"] for p in res["punkter"]] == ["G25-M2A-ALG-8"]


def test_samma_kod_star_i_hogst_en_lista():
    """En redan förkryssad punkt får inte dyka upp som osäkert förslag också —
    läraren hade sett samma punkt två gånger, en gång i och en gång att kryssa."""
    res = ci_forslag.foresla(
        _punkter(), "material",
        llm=_svar({"punkter": [{"kod": "G25-M2A-ALG-8", "skal": "a"},
                               {"kod": "G25-M2A-ALG-8", "skal": "dubblett"}],
                   "osakra": [{"kod": "G25-M2A-ALG-8", "skal": "samma igen"}]}))
    assert [p["kod"] for p in res["punkter"]] == ["G25-M2A-ALG-8"]
    assert res["osakra"] == []


def test_taken_och_skallangden_halls():
    punkter = _punkter()
    res = ci_forslag.foresla(
        punkter, "material",
        llm=_svar({"punkter": [{"kod": p["kod"], "skal": "x" * 400}
                               for p in punkter],
                   "osakra": []}))
    assert len(res["punkter"]) == ci_forslag.MAX_PUNKTER
    assert all(len(p["skal"]) <= ci_forslag.MAX_SKAL for p in res["punkter"])


def test_osakra_taket_ar_lagre():
    punkter = _punkter()
    res = ci_forslag.foresla(
        punkter, "material",
        llm=_svar({"punkter": [],
                   "osakra": [{"kod": p["kod"], "skal": "kanske"}
                              for p in punkter]}))
    assert len(res["osakra"]) == ci_forslag.MAX_OSAKRA


def test_trasigt_json_ger_tomt_svar_och_ett_skal():
    res = ci_forslag.foresla(_punkter(), "material",
                             llm=lambda model, prompt, **kw: "inte json alls")
    assert res["punkter"] == [] and res["osakra"] == []
    assert "otydligt" in res["tomt_skal"]


def test_json_i_prosa_raddas_anda():
    """Modellen ramar ibland in svaret i en mening. Att fälla ett helt förval
    på en inledningsrad vore dyrt — samma räddning som doma_tackning gör."""
    res = ci_forslag.foresla(
        _punkter(), "material",
        llm=lambda model, prompt, **kw:
            'Här är resultatet: {"punkter": [{"kod": "G25-M2A-ALG-8", '
            '"skal": "s. 55"}], "osakra": []} Hoppas det hjälper!')
    assert [p["kod"] for p in res["punkter"]] == ["G25-M2A-ALG-8"]


def test_ett_undantag_faller_aldrig_forvalet():
    """FAIL-OPEN. Läraren bad aldrig om förvalet — hon skrev in ett bokspann.
    Ett nätfel får kosta förslaget, aldrig begäran."""
    def dor(model, prompt, **kw):
        raise RuntimeError("nätet är nere")

    res = ci_forslag.foresla(_punkter(), "material", llm=dor)
    assert res["punkter"] == [] and res["osakra"] == []
    assert res["tomt_skal"]


def test_tom_kalltext_fragar_aldrig_modellen():
    def aldrig(model, prompt, **kw):
        raise AssertionError("modellen anropades utan material")

    res = ci_forslag.foresla(_punkter(), "   ", llm=aldrig)
    assert "lästa" in res["tomt_skal"]


def test_avbruten_skickas_bara_nar_den_ges():
    """Kassettregeln: ett mål är en byte-identisk payload. Ett extra nyckelord
    i anropet när ingen avbrytare finns hade ändrat varenda befintlig fejk."""
    sedda = []

    def llm(model, prompt, **kw):
        sedda.append(kw)
        return json.dumps({"punkter": [], "osakra": []})

    ci_forslag.foresla(_punkter(), "material", llm=llm)
    assert "avbruten" not in sedda[-1]

    stopp = lambda: False
    ci_forslag.foresla(_punkter(), "material", llm=llm, avbruten=stopp)
    assert sedda[-1]["avbruten"] is stopp


def test_tomma_listor_ar_ett_giltigt_svar():
    res = ci_forslag.foresla(_punkter(), "material",
                             llm=_svar({"punkter": [], "osakra": []}))
    assert res["punkter"] == [] and res["osakra"] == []
    assert "ingen punkt" in res["tomt_skal"]


# ── källtexten ───────────────────────────────────────────────────────────────

def _bok_i_db(base):
    """En bok med register för s. 40–65, men bara TVÅ lästa sidor. Det är det
    vanliga läget: läraren slår upp ett spann långt innan sidorna är avlästa."""
    db_file = base / "transkribera.db"
    conn = db.connect(db_file)
    try:
        b = db.create_bok(conn, namn="Origo 2a", kurs="Ma2a", sidor=300)
        db.set_bok_register(conn, b["id"], [
            {"nr": "2.1", "titel": "Kvadreringsreglerna", "fran": 40, "till": 50},
            {"nr": "2.3", "titel": "Andragradsekvationer", "fran": 51, "till": 65},
            {"nr": "3.1", "titel": "Statistik", "fran": 66, "till": 80},
        ])
        db.save_bok_sida(conn, b["id"], 44, avsnitt="2.1",
                         rubrik="Kvadreringsreglerna",
                         text="Kvadreringsreglerna motiveras geometriskt.")
        db.save_bok_sida(conn, b["id"], 55, avsnitt="2.3",
                         rubrik="pq-formeln",
                         text="pq-formeln härleds ur kvadratkomplettering.")
        # Läst i faktapasset men utan text — sidan är alltså INTE avläst.
        db.save_bok_sida(conn, b["id"], 56, avsnitt="2.3", rubrik="Rötter")
    finally:
        conn.close()
    return db_file, b["id"]


def test_kalltexten_bar_avsnitten_och_de_lasta_sidorna(tmp_path):
    db_file, bid = _bok_i_db(tmp_path)
    text, kalla = ci_forslag.kalltext(
        tmp_path, db_file,
        {"bok": {"id": bid, "fran": 40, "till": 65},
         "moment": "2.3 Andragradsekvationer"})
    # Avsnittsregistret finns även för olästa sidor — det är det som bär
    # momentet när ingen sida är avläst än.
    assert "2.1 Kvadreringsreglerna" in text
    assert "2.3 Andragradsekvationer" in text
    # Och bara avsnitt som ÖVERLAPPAR spannet.
    assert "Statistik" not in text
    assert "pq-formeln härleds" in text
    assert kalla.startswith("Origo 2a s. 40–65")
    assert "2.3 Andragradsekvationer" in kalla


def test_olasta_sidor_namns_inte_med_ett_ord(tmp_path):
    """Samma regel som bok.uppslag_text: en rad om att sidan saknas hade blivit
    en inbjudan till modellen att fylla luckan själv."""
    db_file, bid = _bok_i_db(tmp_path)
    text, _kalla = ci_forslag.kalltext(
        tmp_path, db_file, {"bok": {"id": bid, "fran": 40, "till": 65}})
    assert "Sida 56" not in text and "Rötter" not in text
    for ord_ in ("oläst", "saknas", "inte läst"):
        assert ord_ not in text.lower()


def test_kalltexten_laser_aldrig_in_en_sida(tmp_path, monkeypatch):
    """96 sekunder per sida hör hemma där läraren tryckt Skriv och väntar på ett
    papper — inte i ett förval som ska komma tyst medan hon skriver."""
    from app import bok

    def aldrig(*a, **kw):
        raise AssertionError("förvalet läste in en sida")

    monkeypatch.setattr(bok, "las_spann", aldrig)
    db_file, bid = _bok_i_db(tmp_path)
    text, _ = ci_forslag.kalltext(
        tmp_path, db_file, {"bok": {"id": bid, "fran": 40, "till": 65}})
    assert text


def test_momentet_racker_som_kalla(tmp_path):
    db_file, _bid = _bok_i_db(tmp_path)
    text, kalla = ci_forslag.kalltext(
        tmp_path, db_file, {"moment": "Pythagoras sats"})
    assert "Pythagoras sats" in text
    assert kalla == "Pythagoras sats"


def test_kalltexten_ar_takad(tmp_path):
    db_file, bid = _bok_i_db(tmp_path)
    conn = db.connect(db_file)
    try:
        for sida in range(41, 54):
            db.save_bok_sida(conn, bid, sida, text="x" * 4000)
    finally:
        conn.close()
    text, _ = ci_forslag.kalltext(
        tmp_path, db_file, {"bok": {"id": bid, "fran": 40, "till": 65}})
    assert len(text) <= ci_forslag.MAX_KALLTECKEN + 2000


def test_har_kalla_kraver_mer_an_nivan():
    assert not ci_forslag.har_kalla({"niva": "mate/2a"})
    assert not ci_forslag.har_kalla({"niva": "mate/2a", "moment": "   "})
    assert ci_forslag.har_kalla({"moment": "Andragradsekvationer"})
    assert ci_forslag.har_kalla({"bok": {"id": 1, "fran": 40, "till": 65}})
    assert ci_forslag.har_kalla({"forlaga": {"id": 7}})
    assert ci_forslag.har_kalla({"underlag": "abc123abc123"})


# ── rutten ───────────────────────────────────────────────────────────────────

def test_rutten_kraver_en_kalla(llm_ready):
    r = llm_ready.post("/api/planning/ci-forslag", json={"niva": "mate/2a"})
    assert r.status_code == 400
    assert "källa" in r.json()["error"]


def test_rutten_kraver_en_kand_niva(llm_ready):
    r = llm_ready.post("/api/planning/ci-forslag",
                       json={"niva": "", "moment": "Derivata"})
    assert r.status_code == 400
    r = llm_ready.post("/api/planning/ci-forslag",
                       json={"niva": "mate/9z", "moment": "Derivata"})
    assert r.status_code == 400


def test_rutten_tar_ingen_molnplats_ifran_lararen(llm_ready, monkeypatch,
                                                  fejk_claude):
    """Mätt 2026-09-06: tre bakgrundsförslag åt alla tre molnplatserna och
    lärarens egen tavla fick 409. Förslaget har nu en egen plats, så ett fullt
    molntak syns inte alls här."""
    fejk_claude("auto")
    arb = llm_ready.app.state.arbiter
    monkeypatch.setattr(arb, "try_acquire_llm", lambda: None)   # molnet fullt
    r = llm_ready.post("/api/planning/ci-forslag",
                       json={"niva": "mate/2a",
                             "moment": "2.3 Andragradsekvationer och pq-formeln"})
    assert r.status_code == 200
    assert _done(r)["punkter"]


def test_ett_nyare_forslag_tar_over(llm_ready, monkeypatch):
    """Läraren ändrade källorna medan förslaget väntade på platsen. Då ska det
    gamla lämna walkover i kontraktets form, inte köa och inte falla."""
    arb = llm_ready.app.state.arbiter
    monkeypatch.setattr(arb, "acquire_forslag",
                        lambda n, **kw: None)       # biljetten blev gammal
    monkeypatch.setattr(ci_forslag, "foresla", _aldrig)
    r = llm_ready.post("/api/planning/ci-forslag",
                       json={"niva": "mate/2a", "moment": "Andragradsekvationer"})
    assert r.status_code == 200
    res = _done(r)
    assert set(res) == {"punkter", "osakra", "kalla", "tomt_skal"}
    assert res["punkter"] == [] and res["osakra"] == []
    assert "nyare" in res["tomt_skal"]


def _aldrig(*a, **kw):
    raise AssertionError("modellen frågades trots att förslaget var överspelat")


def test_rutten_spelar_upp_kassetten_och_ger_kontraktets_form(llm_ready,
                                                              fejk_claude):
    """Hela vägen genom appens egen söm: fejkat `claude` → ström → JSON →
    filtrering mot nivån. Bandet väljs på markörfrasen i auto-läget, precis som
    i e2e."""
    fejk_claude("auto")
    r = llm_ready.post("/api/planning/ci-forslag",
                       json={"niva": "mate/2a",
                             "moment": "2.3 Andragradsekvationer och pq-formeln"})
    assert r.status_code == 200
    res = _done(r)
    assert set(res) == {"punkter", "osakra", "kalla", "tomt_skal"}
    koder = [p["kod"] for p in res["punkter"]]
    assert "G25-M2A-ALG-8" in koder
    assert all(k.startswith("G25-M2A-") for k in koder)
    assert all(p["skal"] for p in res["punkter"])
    assert res["osakra"] and res["tomt_skal"] == ""
    assert res["kalla"] == "2.3 Andragradsekvationer och pq-formeln"
    # Förloppet ska synas medan modellen tänker.
    assert any(e["type"] == "progress" for e in _events(r))


def test_rutten_ar_fail_open_nar_modellen_svarar_skrap(llm_ready, fejk_claude):
    """Ett otydligt svar är inte ett fel. Läraren ska få sina kryss orörda och
    en not om varför, aldrig ett felmeddelande hon inte bad om."""
    fejk_claude("trasig-json")
    r = llm_ready.post("/api/planning/ci-forslag",
                       json={"niva": "mate/2a", "moment": "Andragradsekvationer"})
    assert r.status_code == 200
    res = _done(r)
    assert res["punkter"] == [] and res["osakra"] == []
    assert res["tomt_skal"]
    assert not [e for e in _events(r) if e["type"] == "error"]


# ── Sidtexten sprids över spannets avsnitt ───────────────────────────────
# Skarpt 2026-09-06: s. 4–58 i Origo 2a (kap 1.1–1.3). Kapitel 1.1:s lästa
# sidor åt hela budgeten, 1.2 och 1.3 nådde modellen bara som rubriker och
# blev «osäkra» fast läraren pekat rakt på dem.

_RAD = {"avsnitt": [
    {"nr": "1.1", "titel": "Uttryck", "kap": "Kapitel 1 · Algebra",
     "vag": "Algebraiska uttryck och Ekvationer", "fran": 8, "till": 26},
    {"nr": "1.2", "titel": "Andragradsuttryck", "kap": "Kapitel 1 · Algebra",
     "vag": "Uttryck av andra graden och Kvadreringsreglerna", "fran": 27, "till": 38},
    {"nr": "1.3", "titel": "Andragradsekvationer", "fran": 39, "till": 69},
    {"nr": "2.1", "titel": "Koordinatsystem", "fran": 70, "till": 76}]}


def test_avsnittsraderna_bar_kapitel_och_delavsnitt():
    rader = ci_forslag._avsnittsrader(_RAD, 4, 58)
    assert len(rader) == 3                       # 2.1 ligger utanför spannet
    assert rader[1].startswith("- 1.2 Andragradsuttryck (s. 27–38, Kapitel 1 · Algebra)")
    assert "delavsnitt: Uttryck av andra graden och Kvadreringsreglerna" in rader[1]
    assert "delavsnitt" not in rader[2]          # 1.3 saknar väg: ingen tom rad


def test_sidtexten_sprids_over_avsnitten_och_klipps_per_sida():
    sidor = [{"sida": s, "avsnitt": None, "rubrik": None, "text": f"S{s} " + "x" * 5000}
             for s in range(8, 31)]              # 1.1 hela, 1.2 fyra sidor, som Origo 2a
    text = ci_forslag._sidtext_spridd(sidor, _RAD, 4, 58, budget=4 * 2400)
    ordning = [int(m) for m in __import__("re").findall(r"— Sida (\d+)", text)]
    # Varv för varv: första sidan ur 1.1, första ur 1.2, andra ur 1.1, andra ur 1.2.
    assert ordning == [8, 27, 9, 28]
    assert all(len(bit) <= ci_forslag.MAX_PER_SIDA + 60 for bit in text.split("\n\n"))
    # Olästa sidor nämns aldrig.
    assert "Sida 31" not in ci_forslag._sidtext_spridd(
        sidor + [{"sida": 31, "text": ""}], _RAD, 4, 58, budget=10 ** 6)


def test_prompten_kalibrerar_och_gor_avsnitten_till_bevis():
    prompt = ci_forslag.build_ci_prompt(
        [{"kod": "G25-M2A-ALG-5", "kort": "Andragradsekvationer", "text": "…"}],
        "AVSNITT I SPANNET:\n- 1.3 Andragradsekvationer", "1.3 Andragradsekvationer")
    assert "AVSNITTEN i spannet är starka bevis" in prompt
    assert "delavsnitt" in prompt
    assert "2–5 punkter" in prompt
