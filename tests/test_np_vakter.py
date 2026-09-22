"""NP-vakterna (app/np_vakter.py) mot lärarens dom över prov 88.

Prov 88 («Algebra och ekvationer», Ma 2a, tolv uppgifter) ligger i
tests/data/exam88.json som appen skrev det: inget ur nationella proven, bara
appens egna uppgifter. Läraren gick igenom det uppgift för uppgift 2026-09-22
och det hon fällde ska vakterna fälla, det hon godkände ska passera. Hennes
egna förtydligande fraser («Avgör om Elin har hittat alla lösningar», «Visa
hur du har räknat med hjälp av miniräknare») är medvetna och får inte kosta
ett fynd.

Allt här är räknat, inga modellanrop, inga kassetter.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app import exam_gen, exam_spec, np_vakter
from app.web import routes_exam

FIXTUR = Path(__file__).resolve().parent / "data" / "exam88.json"


@pytest.fixture(scope="module")
def exam88() -> dict:
    return json.loads(FIXTUR.read_text(encoding="utf-8"))


def _koder(fel: list[dict], kod: str) -> set[str]:
    """Uppgiftsnumren («7», «12b») vaktens fynd pekar på."""
    return {f["path"].split(" ", 1)[1] for f in fel if f["code"] == kod}


# ── underlag för egna prov ───────────────────────────────────────────────

def _u(text="Beräkna $\\sqrt{49}$.", poang=(1, 0, 0), **extra) -> dict:
    rad = {"del": "B", "typ": "redovisning", "formaga": "P",
           "poang": list(poang), "text": text, "losning": "7.",
           "bedomning": "+1 E för 7"}
    rad.update(extra)
    return rad


def _prov(uppgifter: list[dict], kurs="Matematik 2a") -> dict:
    return {"titel": "Prov", "kurs": kurs, "uppgifter": uppgifter}


# ── 1. stegvakten ────────────────────────────────────────────────────────

def test_uppgift_9_tre_steg_for_en_poang_falls(exam88):
    """Lärarens dom: «tre steg (ekvation, rot, differens) för 1 p. NP ger
    2–3 p.» Uppgift 4 (två poäng, insättning + pq) ska passera."""
    fel = np_vakter.stegvakt(exam88)
    assert _koder(fel, "stegvakt") == {"9"}
    assert "Höj poängen till 2" in fel[0]["message"]


def test_stegraknaren_ar_kalibrerad_pa_prov_88(exam88):
    """Heuristiken (rakna_steg) ska räkna som läraren räknade: nio har tre
    steg, fyra har fyra på två poäng, sju (utveckla två parenteser, förenkla)
    har två. Skriv inte om heuristiken utan att dessa tre står kvar."""
    steg = {e["nr"]: np_vakter.rakna_steg(e["kort"]["losning"])
            for e in exam_gen.domarenheter(exam88)}
    assert steg["9"] == 3
    assert steg["4"] == 4
    assert steg["7"] == 2


def test_stegvakten_mater_inte_kortsvar():
    """Ett A-kortsvar ger 1 p för 3 steg i kurs 2 (2a A_kortsvar: median 3,0)
    och är NP:s svåraste poäng per ord, med flit."""
    u = _u(typ="rutin", poang=(0, 0, 1),
           losning="$2^x = 8$ ger $x = 3$, så $y = 3 \\cdot 3 = 9$ och "
                   "$y - 1 = 8$.")
    assert np_vakter.stegvakt(_prov([u])) == []
    u["typ"] = "redovisning"
    assert _koder(np_vakter.stegvakt(_prov([u])), "stegvakt") == {"1"}


def test_svaret_forst_raknas_inte_som_ett_steg():
    """Prompten ber om svaret först. «Svaret är $x = 5$.» är inget räknesteg."""
    assert np_vakter.rakna_steg("Svaret är $x = 5$. $2x = 10$ ger $x = 5$.") == 2
    assert np_vakter.rakna_steg("$x = 5$.") == 0
    # «och» binder (samma operation två gånger), «alltså» binder (samma steg
    # omskrivet), «ger» skiljer (nytt steg).
    assert np_vakter.rakna_steg(
        "Nej. Regeln ger $(x+1)^2 = x^2 + 2x + 1$ och $x(x+2) = x^2 + 2x$.") == 1
    assert np_vakter.rakna_steg(
        "Nej. $3x = 12$, alltså $x = 4$.") == 1


# ── 2. poängformen ───────────────────────────────────────────────────────

def test_uppgift_7_kommunikation_pa_en_poang_falls(exam88):
    """Lärarens dom: «Kommunikation för en enpoängare stämmer inte med NP
    (K-poäng ges för redovisning i flerpoängare)». Uppgift 10 (0/3/0, K)
    är NP:s form och passerar."""
    fel = np_vakter.poangformvakt(exam88, exam88["kurs"])
    traffar = _koder(fel, "poangform")
    assert "7" in traffar and "10" not in traffar
    sju = next(f for f in fel if f["path"] == "uppgift 7")
    assert "Kommunikation" in sju["message"] and "minst 3 p" in sju["message"]


def test_a_losning_pa_en_poang_falls_men_a_kortsvar_passerar():
    """2a: alla elva A-enheter på 1 p är kortsvar, alla A-lösningar ger
    minst 2 p."""
    los = _u(poang=(0, 0, 1))
    kort = _u(poang=(0, 0, 1), typ="rutin")
    assert _koder(np_vakter.poangformvakt(_prov([los])), "poangform") == {"1"}
    assert np_vakter.poangformvakt(_prov([kort])) == []
    # 2c har EN A-lösning på 1 p i mätningen (bedöm modellens begränsning),
    # så där är gränsen 1 och raden passerar.
    assert np_vakter.poangformvakt(_prov([los], kurs="Ma2c")) == []


def test_e_enhet_over_tva_och_enhet_over_fyra_falls():
    tre_e = _u(poang=(3, 0, 0))
    fem = _u(poang=(0, 2, 3))
    fel = np_vakter.poangformvakt(_prov([tre_e, fem]))
    assert _koder(fel, "poangform") == {"1", "2"}
    assert "E-enhet" in fel[0]["message"]
    assert "aldrig mer än 4 p" in fel[1]["message"]


def test_k_reglerna_galler_bara_kurs_2():
    """1a har K på E-nivå (4 E-poäng) och på tvåpoängare (×5); regeln är
    mätt på kurs 2 och stannar där."""
    k2 = _u(poang=(0, 2, 0), formaga="K")
    ek = _u(poang=(1, 0, 0), formaga="K")
    assert _koder(np_vakter.poangformvakt(_prov([k2, ek], kurs="Matematik 2a")),
                  "poangform") == {"1", "2"}
    assert np_vakter.poangformvakt(_prov([k2, ek], kurs="Matematik 1a")) == []
    assert np_vakter.poangformvakt(_prov([k2, ek], kurs="")) == []


# ── 3. metodvakten ───────────────────────────────────────────────────────

def test_uppgift_1b_2a_2b_foreskriver_metod(exam88):
    """Lärarens dom: «med pq-formeln», «med kvadreringsregeln», «med
    konjugatregeln». NP föreskriver aldrig metod i den räknarfria delen."""
    fel = np_vakter.metodvakt(exam88)
    assert _koder(fel, "metodvakt") == {"1b", "2a", "2b"}


def test_tillatna_foreskrifter_passerar():
    """Det som FINNS i NP: «med algebraisk metod», «använd formeln», «bryt
    ut», «med hjälp av grafen». Verbet «Faktorisera» är en uppgift, inte en
    föreskrift. Och Del C (med räknare) mäts inte."""
    for text in ("Lös ekvationen $x^2 - 4 = 0$ med algebraisk metod.",
                 "Använd formeln och beräkna $y$.",
                 "Bryt ut största möjliga faktor ur $6x + 9$.",
                 "Lös $f(x) = 2$ med hjälp av grafen.",
                 "Faktorisera $x^2 - 9$."):
        assert np_vakter.metodvakt(_prov([_u(text=text)])) == [], text
    c = _u(text="Lös $x^2 - 6x - 16 = 0$ med pq-formeln.", **{"del": "C"})
    assert np_vakter.metodvakt(_prov([c])) == []


# ── 4. parametervakten ───────────────────────────────────────────────────

def test_prov_88_uppgift_4_6b_och_12_passerar(exam88):
    """4 (C, konstanten c), 6b (A, bredden b) och 12 (c, som får talet 25 i
    a) ligger alla inom 2a:s tak. Uppgift 3, 8, 9 och 11 har formler med
    definierade storheter (R, n, K, t, m), inte parametrar."""
    assert np_vakter.parametervakt(exam88, exam88["kurs"]) == []


def test_konstanter_raknar_med_profilens_definition():
    k = np_vakter.konstanter
    assert k("Resultatet ges av $R = 45n - 12\\,000$ där $n$ är antalet.") == set()
    assert k("Ekvationen $x^2 - 8x + c = 0$ har roten $x = 3$.") == {"c"}
    assert k("Låt $c = 25$. Skriv $x^2 + 10x + c$ som en kvadrat.") == set()
    assert k("Utveckla $(4a + 3)(4a - 3)$.") == set()      # a är den okända
    assert k("Skriv arean som ett uttryck i $x$ och $b$.") == {"b"}
    assert k("Bestäm $f(2)$ när $f(x) = 3x + a$.") == {"a"}
    assert k("$\\sqrt{205} \\approx 14{,}3$") == set()


def test_parametertaket_ar_kursens_och_nivans():
    """E 0, C 1, A 2 i 2a; 1a:s A-kortsvar lever på bokstäver (median 2)."""
    tva = _u(text="Förenkla $ax + bx$.", poang=(1, 0, 0))
    assert _koder(np_vakter.parametervakt(_prov([tva], "Matematik 2a")),
                  "parametervakt") == {"1"}
    assert np_vakter.parametervakt(_prov([tva], "Matematik 1a")) == []
    assert np_vakter.parametervakt(_prov([tva], "Matematik, nivå 4")) == []
    a = _u(text="Förenkla $ax + bx$.", poang=(0, 0, 2))
    assert np_vakter.parametervakt(_prov([a], "Matematik 2a")) == []


# ── 5. kursvakten ────────────────────────────────────────────────────────

def test_uppgift_12b_for_varje_x_ar_2c_form(exam88):
    """Lärarens dom: «alla värden på c som gör uttrycket positivt för varje
    x» är 2c-NP:s A, inte 2a:s. I 2a står formen bara på A-enheter med
    minst 2 p och resonemangspoäng."""
    fel = np_vakter.kursvakt(exam88, exam88["kurs"])
    assert _koder(fel, "kursvakt") == {"12b"}
    assert "2c:s form" in fel[0]["message"]


def test_generaliseringen_tillats_pa_A_med_tva_poang_och_resonemang():
    text = "Undersök om $x^2 + 2x + 3$ är positivt för alla $x$."
    ok = _u(text=text, poang=(0, 0, 2), formaga="R")
    assert np_vakter.kursvakt(_prov([ok]), "Matematik 2a") == []
    fel_niva = _u(text=text, poang=(0, 2, 0), formaga="R")
    assert _koder(np_vakter.kursvakt(_prov([fel_niva]), "Matematik 2a"),
                  "kursvakt") == {"1"}
    # I 2c är formen fri, i kurs 1 finns den inte alls (0 av 71, 0 av 77).
    assert np_vakter.kursvakt(_prov([fel_niva]), "Ma2c") == []
    assert _koder(np_vakter.kursvakt(_prov([ok]), "Matematik 1c"),
                  "kursvakt") == {"1"}
    # Utan kurs, varken i anropet eller på pappret, prövas ingenting.
    assert np_vakter.kursvakt(_prov([fel_niva], kurs=""), "") == []


def test_grannkursens_innehall_falls_med_kursens_lista():
    """2c-tvärsnittets R1 för 2a, 1c-tvärsnittets regel 1 för 1a; 1c och 2c
    har ingen tyngre granne och prövas inte."""
    lik = _u(text="Trianglarna är likformiga. Bestäm $x$.")
    assert _koder(np_vakter.kursvakt(_prov([lik]), "Matematik 2a"),
                  "kursvakt") == {"1"}
    assert np_vakter.kursvakt(_prov([lik]), "Ma2c") == []
    trig = _u(text="Beräkna $\\sin v$ i triangeln.")
    assert _koder(np_vakter.kursvakt(_prov([trig]), "Matematik 1a"),
                  "kursvakt") == {"1"}
    assert np_vakter.kursvakt(_prov([trig]), "Matematik 1c") == []


# ── 6. familjvakten ──────────────────────────────────────────────────────

def test_uppgift_3_8_och_11_ar_samma_modellfamilj(exam88):
    """Lärarens dom: «två gånger fast avgift + rörlig kostnad, sätt in. NP
    har en per prov.» ETT fynd som nämner alla tre."""
    fel = np_vakter.familjvakt(exam88)
    assert len(fel) == 1
    assert "Uppgift 3, 8 och 11" in fel[0]["message"]
    assert fel[0]["path"] == "uppgift 11"


def test_familjen_kans_igen_pa_formeln_scenen_eller_forebilden():
    a = _u(text="Priset ges av $P = 120 + 15t$ där $t$ är antalet timmar.")
    b = _u(text="Kostnaden är $K = 40n + 300$ där $n$ är antalet.")
    c = _u(text="Beräkna $2^5$.")
    assert len(np_vakter.familjvakt(_prov([a, c, b]))) == 1
    assert np_vakter.familjvakt(_prov([a, c])) == []
    d = _u(scen={"begrepp": "Kafé budget"})
    e = _u(scen={"begrepp": "kafé  budget"})
    assert len(np_vakter.familjvakt(_prov([d, c, e]))) == 1
    f = _u(forebild={"nr": 1, "sort": "samma sorts areaproblem"})
    g = _u(forebild={"nr": 2, "sort": "samma sorts areaproblem"})
    assert len(np_vakter.familjvakt(_prov([f, g]))) == 1


# ── 7. dolt-krav-vakten ──────────────────────────────────────────────────

def test_uppgift_11_antagandet_utskrivet_ar_ett_dolt_krav(exam88):
    """Lärarens dom: A-poängen hänger på «antagandet utskrivet», ett krav
    uppgiften inte ställer."""
    fel = np_vakter.doltkravvakt(exam88)
    assert _koder(fel, "doltkrav") == {"11"}
    assert "antagande" in fel[0]["message"]


def test_kravet_som_texten_staller_ar_inget_fynd():
    ok = _u(text="Avgör om Ali har rätt. Motivera ditt svar.",
            bedomning="+1 E svarar nej och förklarar felet")
    assert np_vakter.doltkravvakt(_prov([ok])) == []
    dolt = _u(text="Beräkna priset.",
              bedomning="+1 E rätt pris\n+1 E motiverar valet av metod",
              poang=(2, 0, 0))
    assert _koder(np_vakter.doltkravvakt(_prov([dolt])), "doltkrav") == {"1"}
    # Enheten syns på pappret när uppgiften bär fältet `enhet`.
    enhet = _u(text="Beräkna längden.", bedomning="+1 E rätt svar med enhet")
    assert _koder(np_vakter.doltkravvakt(_prov([enhet])), "doltkrav") == {"1"}
    enhet["enhet"] = "m"
    assert np_vakter.doltkravvakt(_prov([enhet])) == []
    # Redovisningskravet prövas bara på kortsvar: lösningsuppgiften har
    # kravraden «Fullständig lösning krävs» tryckt på pappret.
    red = _u(text="Beräkna $2^5$.", bedomning="+1 E redovisad lösning")
    assert np_vakter.doltkravvakt(_prov([red])) == []
    red["typ"] = "rutin"
    assert _koder(np_vakter.doltkravvakt(_prov([red])), "doltkrav") == {"1"}


# ── ordval och textlängd fäller aldrig ───────────────────────────────────

def test_lararens_fortydliganden_kostar_inget(exam88):
    """5a («Avgör om Elin har hittat alla lösningar») och 10 («Visa hur du
    har räknat med hjälp av miniräknare») är lärarens egna och passerar
    alla sju. Och en uppgift som är dubbelt så lång är fortfarande fri."""
    fel = np_vakter.np_vakter(exam88, exam88["kurs"])
    traffade = {f["path"] for f in fel}
    assert "uppgift 5a" not in traffade and "uppgift 10" not in traffade
    lang = _u(text="Elin ska lösa ekvationen $2x + 3 = 11$. Hon börjar med "
                   "att dra bort tre från båda leden, det vill säga hon "
                   "skriver $2x = 8$. Avgör om Elin gör rätt så långt, och "
                   "bestäm sedan $x$.")
    assert np_vakter.np_vakter(_prov([lang]), "Matematik 2a") == []


def test_hela_domen_over_prov_88(exam88):
    """Uppgift för uppgift, som läraren skrev tabellen: 1b/2a/2b metod, 3+8+11
    familj, 7 poängform, 9 steg, 11 dolt krav, 12b kursgräns. Det hon
    godkände (4, 5a, 8:s text, 10) står utan fynd."""
    fel = np_vakter.np_vakter(exam88, exam88["kurs"])
    per_kod = {}
    for f in fel:
        per_kod.setdefault(f["code"], set()).add(f["path"].split(" ", 1)[1])
    assert per_kod["metodvakt"] == {"1b", "2a", "2b"}
    assert per_kod["stegvakt"] == {"9"}
    assert "7" in per_kod["poangform"]
    assert per_kod["kursvakt"] == {"12b"}
    assert per_kod["familjvakt"] == {"11"}
    assert per_kod["doltkrav"] == {"11"}
    assert "parametervakt" not in per_kod
    for nr in ("4", "5a", "5b", "10"):
        assert f"uppgift {nr}" not in {f["path"] for f in fel}, nr


# ── kedjan: fixrundan, slutgrinden, canvasen ────────────────────────────

def test_fynden_gar_i_samma_reparationsrunda_som_de_gamla(exam88):
    """_raknade_fynd bär de sju på profilen prov och inte på arbetsbladet."""
    fel = exam_gen._raknade_fynd(exam88, avsnitt=None, antal=12,
                                 delmoment=None, profil="prov",
                                 kurs=exam88["kurs"])
    koder = {f["code"] for f in fel}
    assert {"stegvakt", "poangform", "metodvakt", "kursvakt", "familjvakt",
            "doltkrav"} <= koder
    blad = exam_gen._raknade_fynd(exam88, avsnitt=None, antal=12,
                                  delmoment=None, profil="arbetsblad",
                                  kurs=exam88["kurs"])
    assert not set(np_vakter.KODER) & {f["code"] for f in blad}
    for kod in np_vakter.KODER:
        assert exam_gen._raknas_om({"code": kod, "path": "uppgift 3"}), kod


def test_efterkontrollen_visar_fynden_med_nummer_och_atgard(exam88):
    """Canvasen får en rad per fynd med uppgiftens nummer (så rutan kan
    markeras) och Laga-knappen en åtgärd per kod."""
    fynd = routes_exam._npfynd(exam88, "prov")
    assert fynd and all(f["kod"] in np_vakter.KODER for f in fynd)
    assert {f["nr"] for f in fynd} >= {9, 7, 1, 2, 12, 11}
    assert routes_exam._npfynd(exam88, "arbetsblad") == []
    for kod in np_vakter.KODER:
        assert kod in routes_exam._ATGARD, kod
    text = routes_exam.efterkontroll_instruktion(fynd)
    assert "Uppgift 9 ger 1 p" in text
    assert "De gäller uppgift 1, 2, 6, 7, 9, 11 och 12." in text


# ── skelettet: poängformen låses innan modellen skriver ─────────────────

def _brott(sk: list[dict], kurs: str) -> list[tuple[str, dict]]:
    form = exam_spec.np_form("prov", kurs, len(sk))
    ut = []
    for s in sk:
        kar = exam_spec._karaktar(s["poang"])
        if s["typ"] != "rutin" and kar == "A" \
                and s["poang"][2] < exam_spec.NP_A_LOSNING_MIN_POANG:
            ut.append(("A-lösning under 2 p", s))
        if s["typ"] != "rutin" and kar == "E" \
                and s["poang"][0] > exam_spec.NP_E_ENHET_MAX_POANG:
            ut.append(("E-lösning över 2 p", s))
        if form["k3"] and s["formaga"] == "K" and not (
                sum(s["poang"]) == exam_spec.NP_K_ENHET_POANG
                and sum(1 for v in s["poang"] if v) == 1):
            ut.append(("K-rad utan 3 p på en nivå", s))
        for d in s.get("delar") or []:
            if d[2] == 1 and sum(d) == 1 and s["typ"] != "rutin":
                ut.append(("deluppgift som är en A-lösning om 1 p", s))
    return ut


@pytest.mark.parametrize("antal", [3, 6, 8, 10, 12, 16, 20])
@pytest.mark.parametrize("kurs", ["", "Matematik 2a", "Ma2c", "Matematik 1c",
                                  "Ma1a"])
def test_skelettet_haller_poangformen(antal, kurs):
    """Prov 88:s uppgift 7 var skelettets beslut: (0, 0, 1) på en
    redovisningsrad märkt K. Ingen A-lösning under 2 p, ingen E-lösning
    över 2, och i kurs 2 varje K-rad 3 p på en nivå — och skelettet ska
    ändå validera rent."""
    sk = exam_spec.balanced_skeleton(antal, "prov", delar=True, kurs=kurs)
    assert _brott(sk, kurs) == []
    doc = exam_spec._skeleton_doc(sk)
    assert exam_spec.validate_balance(doc, profil="prov") == []
    assert exam_spec.validate_ordning(doc) == []


def test_lararens_bestallning_tolv_uppgifter_23_poang_i_2a():
    """Exakt exam 88:s beställning: 12 uppgifter, 70 minuter i takt 3 = 23 p.
    Poängformen och balansen ska båda hålla, och en K-rad räcker."""
    tak = exam_spec.poang_tak_for(70, 3)
    assert tak == 23
    sk = exam_spec.balanced_skeleton(12, "prov", delar=True,
                                     kurs="Matematik 2a", poang_tak=tak)
    assert sum(sum(s["poang"]) for s in sk) <= tak
    assert _brott(sk, "Matematik 2a") == []
    doc = exam_spec._skeleton_doc(sk)
    assert exam_spec.validate_balance(doc, profil="prov") == []
    assert exam_spec.validate_ordning(doc) == []
    k = [s for s in sk if s["formaga"] == "K"]
    assert len(k) == 1 and sorted(k[0]["poang"]) == [0, 0, 3]
    # Mot samma prov med de sju vakterna: skelettet ger dem ingenting.
    exam = {"kurs": "Matematik 2a", "uppgifter": [
        {"del": s["del"], "typ": s["typ"], "formaga": s["formaga"],
         "poang": s["poang"], "text": "Beräkna $2^5$.", "losning": "32.",
         "bedomning": "+1 E 32"} for s in sk if not s.get("delar")]}
    assert np_vakter.poangformvakt(exam, "Matematik 2a") == []


def test_tio_uppgifter_i_1c_balanserar_utan_k_regeln():
    """1c har K på E och på tvåpoängare; bara A- och E-reglerna gäller."""
    sk = exam_spec.balanced_skeleton(10, "prov", delar=True,
                                     kurs="Matematik 1c")
    assert _brott(sk, "Matematik 1c") == []
    doc = exam_spec._skeleton_doc(sk)
    assert exam_spec.validate_balance(doc, profil="prov") == []
    assert exam_spec.validate_ordning(doc) == []
    assert exam_spec.np_form("prov", "Matematik 1c", 10)["k3"] is False


def test_a_kortsvaret_ar_np_form_fran_atta_uppgifter():
    """(0, 0, 1) på en A-rad blir «Endast svar krävs» (2a: alla elva
    1-poängs A-enheter är kortsvar), i kortsvarsblocket först i Del B. På
    ett litet prov höjs raden till 2 p i stället, för blocket skulle annars
    väga ner Del B:s första halva."""
    sk = exam_spec.balanced_skeleton(12, "prov", delar=True,
                                     kurs="Matematik 2a")
    a_kort = [s for s in sk if s["typ"] == "rutin" and s["poang"][2]]
    assert a_kort and all(s["del"] == "B" for s in a_kort)
    typer = [s["typ"] == "rutin" for s in sk if s["del"] == "B"]
    assert typer == sorted(typer, reverse=True), "kortsvaren först"
    litet = exam_spec.balanced_skeleton(6, "prov", delar=True,
                                        kurs="Matematik 2a")
    assert not [s for s in litet if s["typ"] == "rutin" and s["poang"][2]]


@pytest.mark.parametrize("profil,antal", [("arbetsblad", 8),
                                          ("arbetsblad", 20),
                                          ("gruppuppgift", 4)])
def test_arbetsblad_och_gruppuppgift_ar_ororda(monkeypatch, profil, antal):
    """Kassettregeln: bara provets skelett ändras. Utan form är rotationen,
    tripplarna, bantningen och varvningen byte för byte som förut, och det
    prövas genom att bygga samma papper med poängformen avstängd."""
    assert exam_spec.np_form(profil, "Matematik 2a", antal) is None
    med = exam_spec.balanced_skeleton(antal, profil, delar=False,
                                      kurs="Matematik 2a", poang_tak=antal * 2)
    monkeypatch.setattr(exam_spec, "np_form", lambda *a, **k: None)
    utan = exam_spec.balanced_skeleton(antal, profil, delar=False,
                                       kurs="Matematik 2a", poang_tak=antal * 2)
    assert med == utan


def test_bantningen_gor_a_losningen_till_kortsvar_inte_till_noll():
    """Under taket byts (0, 0, 2) mot (0, 0, 1), och då blir raden ett
    kortsvar i stället för en A-lösning om 1 p."""
    slots = [{"del": None, "formaga": "PL", "karaktar": "A", "typ": "problem",
              "poang": [0, 0, 2]},
             {"del": None, "formaga": "B", "karaktar": "E", "typ": "rutin",
              "poang": [1, 0, 0]}]
    form = exam_spec.np_form("prov", "Matematik 2a", 12)
    exam_spec._banta_skelett(slots, 2, None, form)
    assert slots[0]["poang"] == [0, 0, 1] and slots[0]["typ"] == "rutin"
    # K-raden i kurs 2 bantas aldrig under 3.
    k = [{"del": None, "formaga": "K", "karaktar": "C", "typ": "redovisning",
          "poang": [0, 3, 0]}]
    exam_spec._banta_skelett(k, 1, None, form)
    assert k[0]["poang"] == [0, 3, 0]
