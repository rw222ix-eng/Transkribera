"""«Inför provet» (2026-09-19): arbetsbladet som övar provets uppgiftstyper.

Lärarens beställning: proven blir klara minst en vecka före provdagen, och
veckan innan tränar klassen på ett ARBETSBLAD som bygger på provets
uppgiftstyper, aldrig på provets uppgifter.

Sviten prövar de fyra delarna var för sig, alla utan skarpa modellanrop:
promptblocket (och att prompten är BYTE-IDENTISK utan det), de två
läs-endpointsen, kopieringsvakten i efterkontrollen och drilltäckningen.
"""
import copy
import json

import pytest

from app import db as appdb
from app import exam_gen, exam_spec
from app.web import routes_exam

from tests.test_exam import _exam
from tests.test_routes_exam import (_course_id, _done, _godkant_prov,
                                    _stub_generate)


@pytest.fixture
def client(llm_ready):
    """Generering kräver att arbitern svarar. Basfixturen bor i conftest.py."""
    return llm_ready


# ───────────────────────── promptblocket ──────────────────────────


def test_blocket_bar_formen_aldrig_texterna():
    """Provets uppgiftstexter får ALDRIG gå in i prompten. Ett blad skrivet ur
    dem hade delat ut provet till hela klassen en vecka i förväg."""
    prov = _exam()
    block = exam_gen.build_infor_prov(exam_gen.provslots(prov), [], 6)
    assert block
    for u in prov["uppgifter"]:
        stam = u["text"][:40]
        assert stam not in block, stam
    # Formen står däremot där, plats för plats.
    assert "provets uppgift 1:" in block and "provets uppgift 7:" in block
    assert "rutin" in block and "poäng (E/C/A)" in block


def test_tomt_underlag_ger_tom_strang():
    """Kassetteregeln: utan valt prov ska blocket vara tomt, och prompten
    därmed byte för byte den som gick i väg förut."""
    assert exam_gen.build_infor_prov([], [], 6) == ""
    assert exam_gen.build_infor_prov(None, None, 6) == ""
    # Ett urval som inte finns på pappret faller bort tyst (ett gammalt val i
    # klienten ska inte stoppa ett blad).
    assert exam_gen.build_infor_prov(exam_gen.provslots(_exam()), [99], 6) == ""


def test_en_sak_och_blandat_ger_olika_order():
    """Läraren väljer «en sak» eller «blandat», och valet ska nå modellen som
    två olika order, inte som ett stycke den får tolka."""
    slots = exam_gen.provslots(_exam())
    blandat = exam_gen.build_infor_prov(slots, [], 6)
    en_sak = exam_gen.build_infor_prov(slots, [3], 6)
    assert "FÖRDELA BLADETS 6 uppgifter JÄMNT" in blandat
    assert "STIGA I SVÅRIGHET" in en_sak
    assert "FÖRDELA" not in en_sak
    # «En sak» listar bara sin egen uppgift.
    assert "provets uppgift 3:" in en_sak and "provets uppgift 1:" not in en_sak


def test_blocket_tillater_ett_forberedande_steg():
    """Den enda regeln som säger emot omprovet, och hela skillnaden mellan att
    pröva och att öva."""
    block = exam_gen.build_infor_prov(exam_gen.provslots(_exam()), [], 6)
    assert "DU FÅR GÖRA INGÅNGEN LÄTTARE" in block
    assert "aldrig bytas mot en enklare" in block


def _blad(**k):
    return exam_gen.build_prompt("Matematik, nivå 2c", "NA25", ["Derivator"],
                                 antal=6, profil="arbetsblad", **k)


def test_tomt_block_ger_byte_identisk_prompt():
    """KASSETTKRAVET (mönstret i test_lararord). Skickar klienten inget prov
    ska arbetsbladets prompt vara EXAKT den som gick i väg innan läget fanns,
    och bandnyckeln ARBETSBLAD ska stå kvar i båda."""
    forut = _blad()
    assert _blad(infor="") == forut
    assert _blad(infor=exam_gen.build_infor_prov([], [], 6)) == forut
    assert "INFÖR ETT PROV" not in forut
    assert "ARBETSBLAD" in forut
    med = _blad(infor=exam_gen.build_infor_prov(
        exam_gen.provslots(_exam()), [], 6))
    assert "ARBETSBLAD" in med and med != forut
    # BANDVALET (tests/fejk._auto väljer på nyckelord, i den här ordningen):
    # blocket får inte dra in ett ord som tar ett annat band.
    for tjuvnyckel in ("GRUPPUPPGIFT", "lektionstavla", "matteprov",
                       "Skriv lärarens stödanteckningar", "Läs transkriptet"):
        assert tjuvnyckel not in med[:med.index("Uppdrag:")] or \
            tjuvnyckel in forut[:forut.index("Uppdrag:")], tjuvnyckel
    # Blocket står FÖRE uppdraget: det är en plan över pappret som ska
    # skrivas, och den ska läsas med uppdraget i sikte.
    assert med.rindex("Uppdrag:") > med.rindex("INFÖR ETT PROV")


# ─────────────────────── fältet och grammatiken ───────────────────


def test_drillar_star_i_grammatiken_bara_nar_prompten_ber_om_det():
    """Samma regel som delmomentets: fältet finns exakt när det som skickas
    nämner det, och en regel som läser prompten kan inte glömmas."""
    block = exam_gen.build_infor_prov(exam_gen.provslots(_exam()), [], 6)
    assert exam_gen._drillar_i_grammatiken(block)
    assert not exam_gen._drillar_i_grammatiken(_blad())
    # Ett blad som ska skrivas om bär fältet som JSON och behåller det därför.
    assert exam_gen._drillar_i_grammatiken('{"drillar": 3}')


def _schema(profil, antal, **kw):
    """Schemat som text. Skelettvägen bakar in ExamItem per uppgift och städar
    bort definitionen, så fältet går inte att slå upp, bara att läsa av."""
    sk = exam_spec.balanced_skeleton(antal, profil, delar=(profil == "prov"))
    return json.dumps(exam_spec.to_response_format(skeleton=sk, **kw),
                      ensure_ascii=False)


def test_grammatiken_ar_oforandrad_utan_blocket():
    """Utan «Inför provet» ska schemat vara byte för byte det som gick i väg
    innan fältet fanns, på BÅDA profilerna."""
    for profil in ("prov", "arbetsblad"):
        assert "drillar" not in _schema(profil, 12)
    assert "drillar" in _schema("arbetsblad", 12, drillar=True)
    # PROVET får det aldrig, hur anroparen än frågar: schemat ligger på
    # 29 844 av 30 000 tecken vid tjugo uppgifter, och taket i
    # to_response_format offrar fältet i stället för grammatiktvånget.
    assert "drillar" not in _schema("prov", 20, drillar=True)


# ──────────────────────── drilltäckningen ─────────────────────────


def _blad_doc(drillar):
    doc = copy.deepcopy(_exam())
    for u, d in zip(doc["uppgifter"], drillar):
        u["drillar"] = d
    return doc


def test_drilltackningen_faller_det_valda_numret_som_saknas():
    fel = exam_gen.drilltackning(_blad_doc([1, 1, 3, 3, 3, 1, 1]), [1, 3, 5])
    assert [f["code"] for f in fel] == ["drilltackning"]
    assert "uppgift 5" in fel[0]["message"]
    # Allt täckt: noll fynd, noll rundor.
    assert exam_gen.drilltackning(_blad_doc([1, 1, 3, 3, 3, 1, 1]),
                                  [1, 3]) == []


def test_fler_sorter_an_uppgifter_ar_inget_fel():
    """Sju uppgifter kan inte öva tolv sorter. Skarpt (prov 88, 2026-09-19)
    fällde kontrollen sex av tolv på ett blad som var precis som beställt och
    kostade en reparationsrunda. Kravet är «lika många sorter som bladet har
    uppgifter»; ett fel först när en sort övas dubbelt medan en annan står
    utan."""
    valda = list(range(1, 13))
    # Sju olika sorter på sju uppgifter: rent, fast fem valda saknas.
    assert exam_gen.drilltackning(_blad_doc([1, 2, 3, 4, 5, 6, 7]), valda) == []
    # En dubblett (1, 1) medan sorterna 8–12 står utan: ETT fynd som pekar
    # ut dubbletten, inte fem fynd om varje lucka.
    fel = exam_gen.drilltackning(_blad_doc([1, 1, 3, 4, 5, 6, 7]), valda)
    assert [f["code"] for f in fel] == ["drilltackning"]
    assert "drillar=[1]" in fel[0]["message"]
    assert "uppgift 2, 8, 9, 10, 11, 12" in fel[0]["message"]


def test_drilltackningen_ar_fail_open():
    """Två tystnader, båda med flit: utan valda nummer finns ingen fråga, och
    bär ingen uppgift fältet kördes kontrollen aldrig."""
    assert exam_gen.drilltackning(_blad_doc([1, 1, 1, 1, 1, 1, 1]), []) == []
    assert exam_gen.drilltackning(_exam(), [1, 3]) == []


def test_drillnummer_ar_samma_lista_som_blocket_raknar():
    slots = exam_gen.provslots(_exam())
    assert exam_gen.drillnummer(slots, []) == [1, 2, 3, 4, 5, 6, 7]
    assert exam_gen.drillnummer(slots, [3, 99, 1]) == [1, 3]


def test_passet_kor_en_runda_och_slapper_igenom():
    """Högst EN reparationsrunda, och ett fynd som inte gick att laga blir en
    varning i stället för ett stopp."""
    rundor = []

    def llm(*a, **k):
        rundor.append(1)
        return None                         # modellen svarar inte

    res = exam_gen._infor_pass(_blad_doc([1] * 7), [], model="", llm=llm,
                               profil="arbetsblad", antal=7, skeleton=None,
                               nummer=[1, 3], rounds_used=1, max_rounds=3)
    assert len(rundor) == 1
    assert [e["code"] for e in res["errors"]] == ["drilltackning"]
    assert res["exam"]["uppgifter"][0]["drillar"] == 1


def test_passet_kostar_ingenting_nar_bladet_ar_rent():
    rundor = []
    res = exam_gen._infor_pass(_blad_doc([1, 3, 1, 3, 1, 3, 1]), [], model="",
                               llm=lambda *a, **k: rundor.append(1),
                               profil="arbetsblad", antal=7, skeleton=None,
                               nummer=[1, 3], rounds_used=1, max_rounds=3)
    assert rundor == [] and res["errors"] == []


# ───────────────────────── kopieringsvakten ───────────────────────


def test_kopiefynd_faller_provets_uppgift_med_nya_tal():
    prov = _exam()
    blad = copy.deepcopy(prov)
    # Uppgift 2 är provets egen med utbytta siffror, resten är nyskrivna.
    blad["uppgifter"][1]["text"] = "Lös ekvationen $x^2 - 8x + 15 = 0$."
    for i, u in enumerate(blad["uppgifter"]):
        if i != 1:
            u["text"] = f"En helt nyskriven övningsuppgift nummer {i} om tal."
    fynd = routes_exam._kopiefynd(blad, prov)
    assert [f["kod"] for f in fynd] == ["kopia"]
    assert fynd[0]["nr"] == 2 and fynd[0]["el"] == "uppg2"
    # LAGBART: «Laga fynden» ska kunna skicka det vidare som en instruktion.
    assert routes_exam.efterkontroll_nummer(fynd) == [2]
    assert "kopia" in routes_exam._ATGARD
    assert "Byt ut uppgiften" in routes_exam.efterkontroll_instruktion(fynd)


def test_kopiefynd_ar_fail_open_utan_prov():
    """Ett senare GET på samma blad kommer utan id, och då räknas ingenting."""
    assert routes_exam._kopiefynd(_exam(), None) == []
    assert routes_exam._kopiefynd(_exam(), {"uppgifter": []}) == []


def test_ett_kopiefynd_per_uppgift():
    """6a och 6b är samma kopia, och två rader om samma uppgift säger inte mer
    än en (samma regel som tipsvakten)."""
    prov = copy.deepcopy(_exam())
    prov["uppgifter"][0]["deluppgifter"] = None
    blad = copy.deepcopy(prov)
    fynd = routes_exam._kopiefynd(blad, prov)
    assert len(fynd) == len({f["nr"] for f in fynd})


# ──────────────────────────── endpointsen ─────────────────────────


def test_nasta_ger_klassens_kommande_godkanda_prov(client):
    """`_omprovskandidat` vänd framåt: datum ≥ idag, stigande, närmast först.
    `idag` skickas ALLTID i tester (testdatum-rötan)."""
    senare, gid, cid = _godkant_prov(
        client, titel="Prov 2 · kapitel 2", datum="2026-11-02",
        klass="TE27A", kurs="Matematik, nivå 2b")
    narmast, _, _ = _godkant_prov(
        client, titel="Prov 1 · kapitel 1", datum="2026-10-20",
        klass="TE27A", kurs="Matematik, nivå 2b")
    r = client.get("/api/exams/nasta",
                   params={"group_id": gid, "course_id": cid,
                           "idag": "2026-10-01"})
    assert r.status_code == 200
    svar = r.json()
    assert svar["prov"]["id"] == narmast
    assert [p["id"] for p in svar["kommande"]] == [narmast, senare]
    rad = svar["prov"]
    assert rad["titel"] == "Prov 1 · kapitel 1"
    assert rad["datum"] == "2026-10-20"
    assert rad["antal_uppgifter"] == len(_exam()["uppgifter"])
    assert rad["course_id"] == cid and rad["group_id"] == gid
    # Efter provdagen finns inget kommande kvar.
    svar = client.get("/api/exams/nasta",
                      params={"group_id": gid, "course_id": cid,
                              "idag": "2026-11-03"}).json()
    assert svar == {"prov": None, "kommande": []}


def test_nasta_tar_bara_godkanda_prov_i_ratt_klass(client):
    utkast, gid, cid = _godkant_prov(
        client, titel="Prov 1", datum="2026-10-20",
        klass="TE27B", kurs="Matematik, nivå 1b")
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        appdb.set_exam_status(conn, utkast, "utkast")
        # Ett godkänt blad i samma klass ska inte heller med: bara prov.
        blad = appdb.create_exam(conn, exam=_exam(), group_id=gid,
                                 course_id=cid, datum="2026-10-21",
                                 typ="arbetsblad")
        appdb.set_exam_status(conn, blad["id"], "godkänt")
    finally:
        conn.close()
    svar = client.get("/api/exams/nasta",
                      params={"group_id": gid, "course_id": cid,
                              "idag": "2026-10-01"}).json()
    assert svar == {"prov": None, "kommande": []}
    # Utan klass finns ingen fråga.
    assert client.get("/api/exams/nasta",
                      params={"idag": "2026-10-01"}).json() == {
        "prov": None, "kommande": []}


def test_uppgiftstyper_grupperar_pa_delmoment_forst(client):
    prov_id, _, _ = _godkant_prov(
        client, titel="Prov 1", datum="2026-10-20",
        klass="TE27C", kurs="Matematik, nivå 2c")
    r = client.get(f"/api/exams/{prov_id}/uppgiftstyper")
    assert r.status_code == 200
    svar = r.json()
    assert [t["nummer"] for t in svar["typer"]] == list(
        range(1, len(_exam()["uppgifter"]) + 1))
    # _godkant_prov sätter delmomentet på uppgift 1, och delmomentet vinner
    # över avsnittet och över typ + förmåga.
    assert svar["typer"][0]["etikett"] == "Kapitel 1, avsnitt 1.2 (s. 7–11)"
    assert svar["typer"][0]["delmoment"] == "Kapitel 1, avsnitt 1.2 (s. 7–11)"
    # Reserven är typ + förmåga med kursplanens egna namn.
    assert svar["typer"][1]["etikett"] == "Rutin, Procedur"
    # Grupperna bär unionen av sina nummer, i provets ordning.
    for g in svar["grupper"]:
        assert g["nummer"] == sorted(g["nummer"])
    alla = [n for g in svar["grupper"] for n in g["nummer"]]
    assert sorted(alla) == [t["nummer"] for t in svar["typer"]]
    assert len({g["etikett"] for g in svar["grupper"]}) == len(svar["grupper"])
    assert client.get("/api/exams/99999/uppgiftstyper").status_code == 404


# ──────────────────────────── routen ──────────────────────────────


def test_falten_nar_generatorn_bara_for_arbetsblad(client, monkeypatch):
    calls = _stub_generate(monkeypatch)
    prov_id, gid, cid = _godkant_prov(
        client, titel="Prov 1", datum="2026-10-20",
        klass="TE27D", kurs="Matematik, nivå 2b")
    r = client.post("/api/exams/generate", json={
        "course_id": cid, "group_id": gid, "antal": 6, "typ": "arbetsblad",
        "infor_prov_id": prov_id, "infor_nummer": [3, 1]})
    assert r.status_code == 200
    _done(r)
    assert calls[-1]["inforprov"]["titel"] == "Prov 1"
    assert calls[-1]["infor_nummer"] == [3, 1]
    # PROVET som prov: fälten tystas, för ett prov övar inte inför ett prov.
    client.post("/api/exams/generate", json={
        "course_id": cid, "group_id": gid, "antal": 6, "typ": "prov",
        "infor_prov_id": prov_id, "infor_nummer": [3]})
    assert calls[-1]["inforprov"] is None and calls[-1]["infor_nummer"] == []


def test_provets_texter_gar_in_i_undvik_listan(client, monkeypatch):
    """Kopiorna ska fällas gratis av variationsvakten. Vägen via förlagan var
    inte farbar: den nollar undvik-listan och stänger av vakten."""
    calls = _stub_generate(monkeypatch)
    prov_id, gid, cid = _godkant_prov(
        client, titel="Prov 1", datum="2026-10-20",
        klass="TE27E", kurs="Matematik, nivå 1c")
    client.post("/api/exams/generate", json={
        "course_id": cid, "group_id": gid, "antal": 6, "typ": "arbetsblad",
        "infor_prov_id": prov_id})
    tidigare = calls[-1]["tidigare"]
    assert _exam()["uppgifter"][0]["text"] in tidigare


def test_ogodkant_prov_avvisas_med_svensk_mening(client, monkeypatch):
    _stub_generate(monkeypatch)
    prov_id, gid, cid = _godkant_prov(
        client, titel="Prov 1", datum="2026-10-20",
        klass="TE27F", kurs="Matematik, nivå 2a")
    conn = appdb.connect(client.base_dir / "transkribera.db")
    try:
        appdb.set_exam_status(conn, prov_id, "utkast")
    finally:
        conn.close()
    r = client.post("/api/exams/generate", json={
        "course_id": cid, "group_id": gid, "antal": 6, "typ": "arbetsblad",
        "infor_prov_id": prov_id})
    assert r.status_code == 400
    assert "godkänt" in r.json()["error"]
    # Ett id som inte finns säger det rakt ut i stället för att tiga.
    r = client.post("/api/exams/generate", json={
        "course_id": cid, "group_id": gid, "antal": 6, "typ": "arbetsblad",
        "infor_prov_id": 99999})
    assert r.status_code == 400 and "finns inte" in r.json()["error"]


def test_kopiefynden_foljer_med_genereringens_svar(client, monkeypatch):
    """Provets id når `_exam_result` bara i genereringen; ett senare GET på
    samma blad ger inga kopiefynd (fail-open)."""
    prov_id, gid, cid = _godkant_prov(
        client, titel="Prov 1", datum="2026-10-20",
        klass="TE27G", kurs="Matematik, nivå 3c")
    _stub_generate(monkeypatch)             # bladet BLIR provets uppgifter
    svar = _done(client.post("/api/exams/generate", json={
        "course_id": cid, "group_id": gid, "antal": 6, "typ": "arbetsblad",
        "infor_prov_id": prov_id}))
    koder = [f["kod"] for f in svar["efterkontroll"]]
    assert "kopia" in koder
    kvar = client.get(f"/api/exams/{svar['id']}").json()
    assert "kopia" not in [f["kod"] for f in kvar["efterkontroll"]]
