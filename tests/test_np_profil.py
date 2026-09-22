"""NP-profilen (app/data/np_uppgiftsprofil.json) — låser att datat är det som
lästes och att mallens mått är de som tools/np_profil.py räknar fram.

Antalen är enheter per kurs så som agenterna räknade dem 2026-09-22; ändras
korpusen ska raden här ändras MED FLIT, inte tyst."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import niva_rubrik

FIL = Path(__file__).resolve().parents[1] / "app" / "data" / "np_uppgiftsprofil.json"


@pytest.fixture(scope="module")
def profil() -> dict:
    return json.loads(FIL.read_text(encoding="utf-8"))


def test_fyra_kurser_med_ratt_antal_enheter(profil):
    antal = {k: d["mall"]["enheter"] for k, d in profil["kurser"].items()}
    assert antal == {"1a": 71, "1c": 77, "2a": 112, "2c": 74}


def test_poangsummorna_stammer_mot_nivarubrikens_matning(profil):
    """NP_MATNING räknades 2026-08 ur samma prov; profilen ska ge samma
    trippel per termin (2a vt17/18/22, 2c vt18/22)."""
    for kurs in ("2a", "2c"):
        for prov in profil["kurser"][kurs]["prov"]:
            nyckel = f"NpMa{kurs} vt 20{prov['termin'][2:]}"
            vantat = niva_rubrik.NP_MATNING[nyckel]["poang"]
            rader = [r for r in profil["kurser"][kurs]["uppgifter"]
                     if r.get("termin") == prov["termin"] and r.get("poang")]
            summa = tuple(sum(r["poang"][i] for r in rader) for i in range(3))
            assert summa == tuple(vantat), (kurs, prov["termin"], summa)


def test_ingen_provtext_bara_parafraser(profil):
    for kurs, d in profil["kurser"].items():
        for r in d["uppgifter"]:
            for falt in ("form_parafras", "avgorande_steg"):
                text = str(r.get(falt) or "")
                assert len(text.split()) <= 30, (kurs, r.get("termin"), r.get("nr"), falt)


def test_mallen_har_alla_sex_grupper_per_kurs(profil):
    for kurs, d in profil["kurser"].items():
        assert set(d["mall"]["matt"]) == {
            "E_kortsvar", "E_losning", "C_kortsvar", "C_losning",
            "A_kortsvar", "A_losning"}, kurs
        for post in d["mall"]["matt"].values():
            assert post["n"] >= 5
            assert post["steg"]["median"] is not None


def test_stegen_vaxer_med_nivan_i_alla_kurser(profil):
    """Det stabila fyndet: steg-medianen växer E → C → A för lösningsuppgifter
    i alla fyra kurserna, medan ordmängden inte gör det."""
    for kurs, d in profil["kurser"].items():
        m = d["mall"]["matt"]
        e, c, a = (m[f"{n}_losning"]["steg"]["median"] for n in "ECA")
        assert e <= c <= a, (kurs, e, c, a)
        assert a > e, kurs


def test_kursgransen_delade_uppgifter_har_samma_poang(profil):
    """2c mot 2a och 1c mot 1a: nästan alla delade uppgifter har identisk
    poängtrippel. Kursen sitter i innehållet, inte i svårigheten."""
    for kurs in ("2c", "1c"):
        g = profil["kurser"][kurs]["mall"]["grannkurs"]
        assert g and g["delade"] >= 30
        assert g["samma_poang"] >= g["delade"] - 3, g


def test_tvarsnitten_finns(profil):
    for kurs, d in profil["kurser"].items():
        assert d["tvarsnitt"] and "E" in d["tvarsnitt"], kurs
