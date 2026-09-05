"""Centralt innehåll som andrahandskälla för lektionstavlan.

Lärarens dom 2026-09-05 (kväll): «behandlar det verkligen de sidorna i boken
man ska göra? ÅTERANVÄND INTE UPPGIFTER, GÖR EGNA! I andra hand luta sig på
det centrala innehållet.» Utan uppslagen bok fanns inget kontrakt alls:
tavlan skrevs fritt och täckningsdomaren hade ingenting att döma mot.
"""
from app import course_data as cd


def test_punkterna_ar_kursens_egna_och_momentets():
    punkter = cd.centralt_innehall_punkter(
        "Matematik, nivå 2a", "Andragradsuttryck: multiplicera binom")
    assert punkter, "momentet ska matcha minst en punkt"
    assert all(p["kod"].startswith("G25-M2A-") for p in punkter), punkter
    # Stammen är det som matchar: «andragradsuttryck» och
    # «andragradsfunktioner» delar «andragrads», och det är sakens namn.
    assert any("Andragrads" in p["kort"] for p in punkter), punkter
    assert len(punkter) <= 5


def test_kursen_slas_upp_pa_alla_sina_namn():
    """Appens kursnamn, kurskortnamnet och den gamla beteckningen ska ge
    samma punkter: kursregistret bär alla tre."""
    moment = "Andragradsfunktioner: symmetrilinje och vändpunkt"
    a = cd.centralt_innehall_punkter("Matematik, nivå 2a", moment)
    assert a
    assert cd.centralt_innehall_punkter("Ma2a", moment) == a
    assert cd.centralt_innehall_punkter("Matematik 2a", moment) == a


def test_okand_kurs_och_okant_moment_ger_ingenting():
    """Ingen träff = inget andrahandskontrakt. Då döms tavlan bara på formen,
    precis som förut — hellre det än fem punkter som inte hör hit."""
    assert cd.centralt_innehall_punkter("Historia 1b", "källkritik") == []
    assert cd.centralt_innehall_punkter("Matematik, nivå 2a", "") == []
    assert cd.centralt_innehall_block("Historia 1b", "källkritik") == ""


def test_blocket_sager_sjalvt_vad_det_ar():
    """Blocket går in på BOKENS plats i prompten (routes_planning generate),
    så det måste bära sin egen instruktion — precis som bok.build_bok_block."""
    b = cd.centralt_innehall_block(
        "Matematik, nivå 2a", "Andragradsuttryck: multiplicera binom")
    assert b.startswith(cd.CI_MARKOR)
    assert "kursens punkter för momentet" in b
    assert "skriv HELT EGNA" in b.replace("Skriv HELT EGNA", "skriv HELT EGNA")
    # En rad per punkt, med etiketten och Skolverkets text.
    rader = [r for r in b.splitlines() if r.startswith("- ")]
    assert rader and all(": " in r for r in rader)
    assert len(rader) <= 5
