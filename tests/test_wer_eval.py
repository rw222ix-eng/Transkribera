"""Tester för WER-utvärderingen (tests/wer_eval.py). Ren stdlib."""
from tests.wer_eval import normalisera, wer, cer


def test_normalisera_tar_bort_skiljetecken_och_versaler():
    assert normalisera("Hej, Världen! Åäö — test.") == "hej världen åäö test"


def test_normalisera_hanterar_siffror_och_extra_blank():
    assert normalisera("  Det   är  3 st. ") == "det är 3 st"


def test_wer_identiska_texter_ar_noll():
    assert wer("hej på dig", "hej på dig") == 0.0


def test_wer_raknar_substitution_insattning_strykning():
    # ref 4 ord; 1 substitution + 1 strykning = 2/4
    assert wer("en katt satt här", "en hund satt") == 0.5


def test_wer_okanslig_for_interpunktion_och_versaler():
    assert wer("Hej, på dig!", "hej på dig") == 0.0


def test_wer_tom_hypotes_ar_hundra_procent():
    assert wer("tre ord här", "") == 1.0


def test_cer_teckenniva():
    # ref "abc" vs hyp "abd": 1 substitution av 3 tecken
    assert abs(cer("abc", "abd") - 1 / 3) < 1e-9
