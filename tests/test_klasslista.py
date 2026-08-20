"""Klasslistan ur inklistringen — städningen och efternamnsordningen.

Formaten är de läraren faktiskt klistrar in: Excel med personnummer i egen
kolumn, numrerade PDF-listor, «Efternamn, Förnamn» ur skolsystemet. Ordningen
är svensk — å, ä, ö efter z — utan att luta sig mot maskinens locale.
"""
from app import klasslista


def test_sorterar_pa_efternamn():
    assert klasslista.ordna(["Cesar Berg", "Anna Ceder", "Bo Alm"]) == [
        "Bo Alm", "Cesar Berg", "Anna Ceder"]


def test_fornamnet_skiljer_lika_efternamn():
    assert klasslista.ordna(["Vera Alm", "Bo Alm"]) == ["Bo Alm", "Vera Alm"]


def test_komma_ar_efternamnet_forst():
    assert klasslista.ordna(["Ceder, Anna", "Alm, Bo"]) == [
        "Bo Alm", "Anna Ceder"]


def test_komma_fore_klasskod_ar_inte_ett_efternamn():
    # «Anna Ceder, NA25» är ett namn med klasskod — inte efternamnet
    # «Anna Ceder». Icke-namnsdelar filtreras före komma-tolkningen.
    assert klasslista.ordna(["Anna Ceder, NA25", "Bo Alm, 9A"]) == [
        "Bo Alm", "Anna Ceder"]


def test_csvrad_laser_efternamn_fornamn_och_slapper_resten():
    assert klasslista.ordna(["Ceder,Anna,20080101-1234", "Alm,Bo,20081231-5678"]) == [
        "Bo Alm", "Anna Ceder"]


def test_numrering_och_punkter_stads():
    assert klasslista.ordna(["1. Anna Ceder", "2) Bo Alm", "- Vera Berg"]) == [
        "Bo Alm", "Vera Berg", "Anna Ceder"]


def test_excelkolumner_med_personnummer_och_klasskod():
    rader = ["Anna Ceder\t20080101-1234\tNA25", "Bo Alm\t20081231-5678\tNA25"]
    assert klasslista.ordna(rader) == ["Bo Alm", "Anna Ceder"]


def test_tva_namnkolumner_blir_ett_namn():
    # «Anna<TAB>Ceder» går inte att skilja från «Ceder<TAB>Anna» — utan komma
    # vinner ordningen orden står i, och sista ordet är efternamnet.
    assert klasslista.ordna(["Anna\tCeder", "Bo\tAlm"]) == [
        "Bo Alm", "Anna Ceder"]


def test_svensk_ordning_efter_z():
    namn = ["Ulla Öman", "Per Ålund", "Siv Ängström", "Zara Zetter"]
    assert klasslista.ordna(namn) == [
        "Zara Zetter", "Per Ålund", "Siv Ängström", "Ulla Öman"]


def test_partikeln_hor_till_efternamnet():
    # von Sydow sorterar på v — så står hon i betygskatalogen.
    assert klasslista.ordna(["Sara von Sydow", "Bo Alm", "Vera Tell"]) == [
        "Bo Alm", "Vera Tell", "Sara von Sydow"]


def test_helversaler_versaliseras():
    assert klasslista.ordna(["ANNA-KARIN CEDER", "BO ALM"]) == [
        "Bo Alm", "Anna-Karin Ceder"]


def test_tomma_rader_och_skrap_forsvinner():
    assert klasslista.ordna(["", "   ", "3.", "Bo Alm"]) == ["Bo Alm"]


def test_ensamt_namn_ar_sitt_eget_efternamn():
    assert klasslista.ordna(["Madonna", "Bo Alm"]) == ["Bo Alm", "Madonna"]
