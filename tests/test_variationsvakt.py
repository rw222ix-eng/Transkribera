"""Variationsvakten (Etapp 4): samma uppgift med nya siffror.

Det som prövas hårdast här är inte vakten utan VILLKORET. Blocket får läggas
till prompten bara när underlaget är icke-tomt, därför att kassetterna
(tests/kassetter) är inspelade mot en bestämd prompt och ett mål är en
byte-identisk payload. Testernas databas är tom, alltså blir underlaget tomt,
alltså ska prompten vara byte för byte som före etappen, och det är det
påståendet `test_tom_lista_ger_byte_identisk_prompt` mäter, inte påstår.
"""
from __future__ import annotations

import json

import pytest

from app import db, exam_gen
from tests import fejk

GAMLA = [
    "Lös ekvationen $3x + 6 = 21$. Endast svar krävs.",
    "I en damm växer alger. Arean beskrivs av $A(t) = 12 + 0{,}5t^2$.",
]


# ── Fingeravtrycket ───────────────────────────────────────────────────────

def test_talen_forsvinner_men_formen_star_kvar():
    a = exam_gen.fingeravtryck("Lös ekvationen $3x + 6 = 21$.")
    b = exam_gen.fingeravtryck("Lös  ekvationen $5x + 2 = 17$.")
    assert a == b == "lös ekvationen $#x + # = #$."


def test_decimaltal_ar_ett_tal():
    assert exam_gen.fingeravtryck("Svara $12,5$") == \
        exam_gen.fingeravtryck("Svara $7,25$")


def test_olika_uppgifter_far_olika_avtryck():
    assert exam_gen.fingeravtryck("Lös ekvationen $3x = 6$.") != \
        exam_gen.fingeravtryck("Derivera $f(x) = 3x$.")


def test_for_kort_avtryck_raknas_inte():
    """«Beräkna $#$» är inte en uppgift som går igen. Det är en formulering
    alla uppgifter delar, och en flagga på den vore brus i varje generering."""
    assert exam_gen.build_variation(["Beräkna $12$"]) == ""


# ── Villkoret: kassetteregeln ─────────────────────────────────────────────

def test_tom_lista_ger_tomt_block():
    assert exam_gen.build_variation([]) == ""
    assert exam_gen.build_variation(None) == ""


@pytest.mark.parametrize("profil", ["prov", "arbetsblad", "gruppuppgift",
                                    "diagnos"])
def test_tom_lista_ger_byte_identisk_prompt(profil):
    """Byte för byte, inte «i stort sett». Ett enda blanksteg till i prompten
    är en ny prompt, och då är kassetterna inspelade mot något annat än det
    appen skickar."""
    argument = dict(antal=6, tid_min=120, profil=profil,
                    memory="minne", teman="teman")
    fore = exam_gen.build_prompt("Matematik 3c", "NA25", ["Derivata"],
                                 **argument)
    efter = exam_gen.build_prompt("Matematik 3c", "NA25", ["Derivata"],
                                  variation=exam_gen.build_variation([]),
                                  **argument)
    assert fore.encode("utf-8") == efter.encode("utf-8")


def test_icke_tom_lista_syns_i_prompten():
    prompt = exam_gen.build_prompt(
        "Matematik 3c", "NA25", ["Derivata"],
        variation=exam_gen.build_variation(GAMLA))
    assert "lös ekvationen $#x + # = #$." in prompt
    # Talen ska INTE stå där: listan säger vilka uppgifter som är förbrukade,
    # inte vilka siffror.
    assert "3x + 6 = 21" not in prompt


def test_listan_har_ett_tak():
    # Olika UPPGIFTER och inte samma uppgift med olika tal. Det senare är
    # precis vad vakten drar ihop till en rad, som testet ovanför visar.
    manga = [f"Undersök vad som händer med {'ord ' * (i % 40 + 4)}i fallet."
             for i in range(200)]
    rader = exam_gen.build_variation(manga).splitlines()
    assert len([r for r in rader if r.startswith("- ")]) == exam_gen.MAX_AVTRYCK


# ── Flaggan efter genereringen ────────────────────────────────────────────

def test_samma_uppgift_med_nya_tal_flaggas():
    exam = {"uppgifter": [
        {"text": "Lös ekvationen $9x + 1 = 19$. Endast svar krävs."},
        {"text": "Bestäm derivatan av $f(x) = x^3 - 3x^2$ och tolka den."}]}
    flaggor = exam_gen.variationsflaggor(exam, GAMLA)
    assert [f["nr"] for f in flaggor] == ["1"]
    assert flaggor[0]["avtryck"] == "lös ekvationen $#x + # = #$. endast svar krävs."


def test_deluppgifter_flaggas_med_sitt_eget_nummer():
    exam = {"uppgifter": [{"text": "Stam.", "deluppgifter": [
        {"text": "Något helt annat att räkna ut här."},
        {"text": "Lös ekvationen $2x + 8 = 30$. Endast svar krävs."}]}]}
    assert [f["nr"] for f in exam_gen.variationsflaggor(exam, GAMLA)] == ["1b"]


def test_tomt_underlag_flaggar_ingenting():
    exam = {"uppgifter": [{"text": "Lös ekvationen $3x + 6 = 21$."}]}
    assert exam_gen.variationsflaggor(exam, []) == []


def test_flaggan_star_i_svaret_fran_generate(fejk_claude):
    """Fältet följer med hela vägen ut ur generate_exam, och är en LISTA även
    när ingenting flaggades, så klienten slipper skilja «inga flaggor» från
    «ingen vakt körde»."""
    fejk_claude("auto")
    res = exam_gen.generate_exam("Matematik 3c", "NA25", ["Derivata"],
                                 model="", antal=6)
    assert res["likheter"] == []


def test_flaggan_tander_pa_provbandets_egna_uppgifter(fejk_claude):
    """Underlaget är bandets EGNA uppgifter, så då ska varenda en flaggas. Det
    är vaktens skarpa prov: den ska hitta en upprepning när det finns en."""
    fejk_claude("auto")
    exam = exam_gen._parse_exam(json.loads(
        fejk.las_kassett("prov")["rader"][-1])["result"])
    texter = [u["text"] for u in exam["uppgifter"] if u.get("text")]
    res = exam_gen.generate_exam("Matematik 3c", "NA25", ["Derivata"],
                                 model="", antal=6, tidigare=texter)
    assert res["likheter"], "vakten hittade ingen upprepning i sitt eget band"


# ── Underlaget ur databasen ───────────────────────────────────────────────

def test_tom_databas_ger_tomt_underlag(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    try:
        assert db.tidigare_uppgiftstexter(conn, 1) == []
    finally:
        conn.close()


def test_underlaget_laser_bade_generatorns_papper_och_hogen(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    try:
        cid = db.get_or_create_course(conn, "Matematik 3c")
        db.create_exam(conn, exam={
            "titel": "Prov", "kurs": "Matematik 3c", "hjalpmedel": "-",
            "uppgifter": [{"text": "Ur generatorns bokföring.", "formaga": "P",
                           "typ": "rutin", "poang": [1, 0, 0],
                           "losning": "x", "bedomning": "y"}]},
            typ="prov", course_id=cid)
        db.create_dokument(conn, dokument={
            "typ": "Arbetsblad", "kurs": "Matematik 3c",
            "uppgifter": [{"t": "Ur högen läraren ser.",
                           "del": ["En deluppgift ur högen."]}]})
        texter = db.tidigare_uppgiftstexter(conn, cid)
        assert "Ur generatorns bokföring." in texter
        assert "Ur högen läraren ser." in texter
        assert "En deluppgift ur högen." in texter
    finally:
        conn.close()
