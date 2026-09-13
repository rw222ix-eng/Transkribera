"""tools/dokument_reparera_markor.py — reparationen av «Fortsätt ändra»-skadan.

Verktyget skriver i lärarens riktiga bas. Testerna handlar därför mest om vad
det INTE gör: ett papper vars markör står kvar där den ska, en kopia som bär
egna bilder, en exams-rad utan pdf på disk. Varje falsk träff är ett papper
läraren tappar.
"""
import json

import pytest

from app import db
from tools import dokument_reparera_markor as rep


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def papper(bilder=None, uppgifter=None, **extra):
    return dict({
        "typ": "Prov", "moment": "Kapitel 1", "klass": "TE26A",
        "kurs": "Matematik 1c", "datum": "2026-09-16", "tid": "08:15–09:45",
        "provId": 44, "bilder": bilder or {},
        "uppgifter": uppgifter or [{"nr": 1, "t": "Beräkna √49", "p": 2}],
    }, **extra)


def _dok(conn, versioner, status="godkant", markor=None):
    """Ett papper med flera versioner, markören där anroparen vill ha den."""
    d = db.create_dokument(conn, dokument=versioner[0], status=status)
    for v in versioner[1:]:
        db.add_dokument_version(conn, d["id"], dokument=v)
    if markor is not None:
        db.update_dokument(conn, d["id"], markor=markor)
    return d["id"]


# ── markören ────────────────────────────────────────────────────────────────

def test_markoren_flyttas_till_sista_versionen_nar_bilderna_ligger_dar(conn):
    """Prov 44 i skarpt läge: v0 utan bilder, sista versionen med fem."""
    bilder = {k: "data:image/png;base64,AA" for k in
              ("forsatt", "uppg3", "uppg6", "uppg8", "uppg11")}
    did = _dok(conn, [papper(), papper(bilder=bilder)], markor=0)
    fynd = rep.samla(conn)
    assert [f["id"] for f in fynd["markor"]] == [did]
    assert fynd["markor"][0]["sista"] == 1
    assert fynd["markor"][0]["saknade_bilder"] == sorted(bilder)
    rep.reparera(conn, fynd)
    vy = db.get_dokument(conn, did)
    assert vy["markor"] == 1
    assert sorted(vy["dokument"]["bilder"]) == sorted(bilder)


def test_markoren_flyttas_inte_nar_markorens_version_redan_bar_bilderna(conn):
    """Tolv papper i basen har markör 0 och en senare version — men samma
    bildnycklar i båda. Att flytta dem hade bytt innehåll utan att laga något."""
    b = {"uppg3": "data:image/png;base64,AA"}
    _dok(conn, [papper(bilder=b), papper(bilder=b, moment="omskrivet")], markor=0)
    assert rep.samla(conn)["markor"] == []


def test_utkast_och_markor_langst_bak_rors_inte(conn):
    b = {"uppg3": "data:image/png;base64,AA"}
    _dok(conn, [papper(), papper(bilder=b)], status="utkast", markor=0)
    _dok(conn, [papper(), papper(bilder=b)])          # markör står redan sist
    assert rep.samla(conn)["markor"] == []


# ── dubbletten ──────────────────────────────────────────────────────────────

def test_tom_dubblett_hittas_och_raderas_bara_med_verkstall(conn):
    b = {"forsatt": "data:image/png;base64,AA"}
    original = _dok(conn, [papper(), papper(bilder=b)])
    kopia = _dok(conn, [papper()])
    fynd = rep.samla(conn)
    assert [f["id"] for f in fynd["dubbletter"]] == [kopia]
    assert fynd["dubbletter"][0]["original"] == original
    # samla() är ren läsning: dry-run får aldrig ha rört något.
    assert db.get_dokument(conn, kopia) is not None
    rep.reparera(conn, fynd)
    assert db.get_dokument(conn, kopia) is None
    assert db.get_dokument(conn, original) is not None


def test_kopia_med_egna_bilder_rors_inte(conn):
    _dok(conn, [papper(), papper(moment="varv 2")])
    _dok(conn, [papper(bilder={"uppg3": "data:image/png;base64,AA"})])
    assert rep.samla(conn)["dubbletter"] == []


def test_kopia_med_andra_uppgifter_rors_inte(conn):
    _dok(conn, [papper(), papper(moment="varv 2")])
    _dok(conn, [papper(uppgifter=[{"nr": 1, "t": "Ett annat prov", "p": 3}])])
    assert rep.samla(conn)["dubbletter"] == []


def test_ensamt_papper_ar_ingen_dubblett(conn):
    _dok(conn, [papper()])
    assert rep.samla(conn)["dubbletter"] == []


# ── vakten: lösningsbladet ──────────────────────────────────────────────────

def test_losningsblad_raderas_aldrig_som_dubblett(conn):
    """Skarpt fall 2026-09-13: dokument 130 var prov 44:s lösningsblad och
    uppfyllde ALLA fyra dubblettvillkoren — en version, tomma bilder, samma
    provId, identiska uppgifter. `losningsblad` är den enda skillnaden."""
    b = {"forsatt": "data:image/png;base64,AA"}
    original = _dok(conn, [papper(), papper(bilder=b)])
    blad = _dok(conn, [papper(losningsblad=True)])
    fynd = rep.samla(conn)
    assert fynd["dubbletter"] == []
    assert [f["id"] for f in fynd["fredade"]] == [blad]
    assert fynd["fredade"][0]["original"] == original
    rep.reparera(conn, fynd)
    assert db.get_dokument(conn, blad) is not None


def test_dry_run_sager_varfor_losningsbladet_fredas(conn, tmp_path, capsys):
    b = {"forsatt": "data:image/png;base64,AA"}
    _dok(conn, [papper(), papper(bilder=b)])
    blad = _dok(conn, [papper(losningsblad=True)])
    conn.close()
    rep.main(["--db", str(tmp_path / "t.db")])
    ut = capsys.readouterr().out
    assert f"FREDAT: dokument {blad}" in ut and "losningsblad: true" in ut


def test_fredat_blad_raknas_inte_som_atgard(conn):
    """En fredad rad är en förklaring, inte en ändring — annars säger verktyget
    att det har jobb kvar att göra efter att allt är lagat."""
    b = {"forsatt": "data:image/png;base64,AA"}
    _dok(conn, [papper(), papper(bilder=b)])
    _dok(conn, [papper(losningsblad=True)])
    assert rep.antal_atgarder(rep.samla(conn)) == 0


# ── exams-statusen ──────────────────────────────────────────────────────────

def _exam(conn, pdf=None):
    ex = db.create_exam(conn, exam={"titel": "Kapitel 1", "uppgifter": []},
                        titel="Kapitel 1", datum="2026-09-16")
    vid = conn.execute("SELECT id FROM exam_versions WHERE exam_id = ?",
                       (ex["id"],)).fetchone()["id"]
    if pdf is not None:
        db.set_exam_artifacts(conn, ex["id"], version_id=vid,
                              pdf_path=str(pdf), approve=False)
    return ex["id"], vid


def test_examsstatus_stamplas_om_nar_pdf_finns(conn, tmp_path):
    pdf = tmp_path / "Kapitel 1.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    exam_id, _ = _exam(conn, pdf)
    _dok(conn, [papper(provId=exam_id)])
    fynd = rep.samla(conn)
    assert [f["provid"] for f in fynd["exams"]] == [exam_id]
    rep.reparera(conn, fynd)
    assert db.get_exam(conn, exam_id)["status"] == rep.EXAM_GODKANT


def test_examsstatus_rors_inte_utan_pdf_pa_disk(conn, tmp_path):
    """Sökvägen finns i basen men filen är borta — en godkänd rad utan fil är
    precis det routes_exam vägrar skriva."""
    exam_id, _ = _exam(conn, tmp_path / "borta.pdf")
    _dok(conn, [papper(provId=exam_id)])
    assert rep.samla(conn)["exams"] == []


def test_examsstatus_rors_inte_nar_dokumentet_ar_utkast(conn, tmp_path):
    pdf = tmp_path / "Kapitel 1.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    exam_id, _ = _exam(conn, pdf)
    _dok(conn, [papper(provId=exam_id)], status="utkast")
    assert rep.samla(conn)["exams"] == []


# ── säkerhetskopian och kommandoraden ───────────────────────────────────────

def test_sakerhetskopian_ar_en_lasbar_bas(conn, tmp_path):
    did = _dok(conn, [papper()])
    kopia = rep.sakerhetskopiera(tmp_path / "t.db")
    assert kopia.parent == tmp_path / "Transkriberingar" / "backup"
    assert kopia.exists() and kopia.stat().st_size > 0
    c2 = db.connect(kopia)
    try:
        assert db.get_dokument(c2, did)["dokument"]["provId"] == 44
    finally:
        c2.close()


def test_dry_run_skriver_ingenting(conn, tmp_path, capsys):
    b = {"forsatt": "data:image/png;base64,AA"}
    did = _dok(conn, [papper(), papper(bilder=b)], markor=0)
    kopia = _dok(conn, [papper()])
    conn.close()
    assert rep.main(["--db", str(tmp_path / "t.db")]) == 0
    ut = capsys.readouterr().out
    assert "DRY-RUN" in ut and f"dokument {did}" in ut and f"dokument {kopia}" in ut
    c2 = db.connect(tmp_path / "t.db")
    try:
        assert c2.execute("SELECT markor FROM dokument WHERE id = ?",
                          (did,)).fetchone()["markor"] == 0
        assert db.get_dokument(c2, kopia) is not None
    finally:
        c2.close()
    assert not (tmp_path / "Transkriberingar").exists()


def test_verkstall_lagar_allt_och_lamnar_inget_kvar(conn, tmp_path):
    pdf = tmp_path / "Kapitel 1.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    exam_id, _ = _exam(conn, pdf)
    b = {"forsatt": "data:image/png;base64,AA"}
    did = _dok(conn, [papper(provId=exam_id), papper(provId=exam_id, bilder=b)],
               markor=0)
    kopia = _dok(conn, [papper(provId=exam_id)])
    conn.close()
    assert rep.main(["--db", str(tmp_path / "t.db"), "--verkstall"]) == 0
    c2 = db.connect(tmp_path / "t.db")
    try:
        vy = db.get_dokument(c2, did)
        assert vy["markor"] == 1 and list(vy["dokument"]["bilder"]) == ["forsatt"]
        assert db.get_dokument(c2, kopia) is None
        assert db.get_exam(c2, exam_id)["status"] == rep.EXAM_GODKANT
        assert rep.antal_atgarder(rep.samla(c2)) == 0
    finally:
        c2.close()
    assert list((tmp_path / "Transkriberingar" / "backup").glob("*.db"))


def test_json_each_klarar_papper_utan_bilderfalt(conn):
    """Ett gammalt papper saknar `bilder` helt. Verktyget får inte krascha på
    det — och får inte heller tro att det saknar bilder som någon annan bär."""
    utan = papper()
    utan.pop("bilder")
    _dok(conn, [utan, json.loads(json.dumps(utan))], markor=0)
    assert rep.samla(conn)["markor"] == []
