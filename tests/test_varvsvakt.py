"""Omskrivningen vaktar sitt eget varv (exam_gen._varvsvakt).

Sju av sju prov 23–24/9 behövde ett andra «Laga fynden» på just det första
varvet skrev om (veckoanalysen 2026-09-27, förslag 1; Rickard godkände samma
dag). Sviten låser kontraktet: ett rent varv kostar inget anrop, ett varv som
inför ett fynd lagas i EN runda låst till fyndets uppgift, gamla fynd rörs
inte, och det som står kvar blir varningar utan att varvet kastas.

Inga skarpa anrop: modellen är en stubbe som svarar efter promptens sort."""
import copy
import json

from app import exam_gen
from tests.test_exam import _exam

TIPS = " Tips: använd pq-formeln."
REPARATION = "Problem att åtgärda"


def _llm(varv: dict, lagning: dict | None = None):
    """Omskrivningen får `varv`, reparationen `lagning`, allt annat
    (bedömningspassets elevexempel) ett tomt svar, som passet tål."""
    calls: list[str] = []

    def llm(model, prompt, system=None, options=None, response_format=None,
            max_tokens=None, token_cb=None):
        calls.append(prompt)
        if REPARATION in prompt:
            return json.dumps(lagning if lagning is not None else varv)
        if "önskemål" in prompt:
            return json.dumps(varv)
        return "{}"

    return llm, calls


def _reparationer(calls: list[str]) -> list[str]:
    return [p for p in calls if REPARATION in p]


def _med_tips(exam: dict, nr: int) -> dict:
    exam["uppgifter"][nr - 1]["text"] += TIPS
    return exam


def test_rent_varv_kostar_inget_anrop_och_samma_prompter(monkeypatch):
    """Kassettregeln: vakterna är gratis, och ett varv utan nya fynd går exakt
    de anrop och de prompter det gick innan vakten fanns."""
    varv = _exam()
    varv["uppgifter"][1]["text"] = "Lös ekvationen $x^2 - 5x + 6 = 0$."
    llm, calls = _llm(varv)
    res = exam_gen.refine_exam(_exam(), "byt talen", nummer=2, model="m",
                               llm=llm)
    assert _reparationer(calls) == []
    assert res["exam"]["uppgifter"][1]["text"] == varv["uppgifter"][1]["text"]

    monkeypatch.setattr(exam_gen, "_varvsvakt", lambda _f, res, **_k: res)
    llm2, calls2 = _llm(varv)
    exam_gen.refine_exam(_exam(), "byt talen", nummer=2, model="m", llm=llm2)
    assert calls == calls2


def test_varv_som_infor_ett_tips_lagas_i_en_last_runda():
    """Prov 88, 19/9: ett tips som lagats kom tillbaka efter ett varv på samma
    uppgift. Nu lagas det i samma varv, och lagningen får bara röra uppgiften
    fyndet sitter på, hur mycket modellen än skriver om."""
    varv = _med_tips(_exam(), 2)
    lagning = _exam()
    lagning["uppgifter"][1]["text"] = "Lös ekvationen $x^2 - 5x + 6 = 0$."
    for i in (0, 2, 3, 4):              # modellen «råkar» skriva om resten
        lagning["uppgifter"][i]["text"] = f"På pizzerian säljs {i} pizzor."
    llm, calls = _llm(varv, lagning)
    fore = _exam()
    res = exam_gen.refine_exam(fore, "skriv om den", nummer=2, model="m",
                               llm=llm)
    rep = _reparationer(calls)
    assert len(rep) == 1
    assert "tips" in rep[0].lower() and "uppgift 2" in rep[0]
    efter = res["exam"]
    assert efter["uppgifter"][1]["text"] == "Lös ekvationen $x^2 - 5x + 6 = 0$."
    for i, u in enumerate(fore["uppgifter"]):
        if i != 1:
            assert efter["uppgifter"][i]["text"] == u["text"], \
                f"uppgift {i + 1} rördes"
    assert not [e for e in res["errors"] if e.get("code") == "anivavakt"]


def test_fynd_som_fanns_fore_varvet_rors_inte():
    """Refine-kastas-felet (2026-09-18) åt andra hållet: ett tips som redan
    stod på uppgift 5 är inget besked om varvet på uppgift 2. Och ett tips som
    redan stod på uppgift 2 och står kvar i ny text är samma gamla fynd."""
    fore = _med_tips(_exam(), 5)
    varv = copy.deepcopy(fore)
    varv["uppgifter"][1]["text"] = "Lös ekvationen $x^2 - 5x + 6 = 0$."
    llm, calls = _llm(varv)
    res = exam_gen.refine_exam(fore, "byt talen", nummer=2, model="m", llm=llm)
    assert _reparationer(calls) == []
    assert TIPS in res["exam"]["uppgifter"][4]["text"]

    fore = _med_tips(_exam(), 2)
    varv = copy.deepcopy(fore)
    varv["uppgifter"][1]["text"] = ("Lös ekvationen $x^2 - 5x + 6 = 0$. "
                                    "Tips: faktorisera.")
    llm, calls = _llm(varv)
    res = exam_gen.refine_exam(fore, "byt talen", nummer=2, model="m", llm=llm)
    assert _reparationer(calls) == []
    assert res["exam"]["uppgifter"][1]["text"] == varv["uppgifter"][1]["text"]


def test_fri_omskrivning_lagas_bara_pa_fyndets_uppgift():
    """Utan mål får varvet röra allt, men lagningen får bara röra uppgiften
    med det nya fyndet: uppgift 5, som varvet skrev om utan att bryta något,
    står som varvet lämnade den."""
    varv = _med_tips(_exam(), 2)
    varv["uppgifter"][4]["text"] = ("En population beskrivs av "
                                    "$N(t) = 300 \\cdot 1{,}04^t$. Bestäm när "
                                    "populationen har fördubblats.")
    lagning = copy.deepcopy(varv)
    lagning["uppgifter"][1]["text"] = "Lös ekvationen $x^2 - 5x + 6 = 0$."
    lagning["uppgifter"][4]["text"] = "Något helt annat."
    lagning["titel"] = "Prov: Pizzor"
    llm, calls = _llm(varv, lagning)
    res = exam_gen.refine_exam(_exam(), "gör provet lite annorlunda",
                               model="m", llm=llm)
    assert len(_reparationer(calls)) == 1
    efter = res["exam"]
    assert efter["uppgifter"][1]["text"] == "Lös ekvationen $x^2 - 5x + 6 = 0$."
    assert efter["uppgifter"][4]["text"] == varv["uppgifter"][4]["text"]
    assert efter["titel"] == varv["titel"]


def test_fynd_som_star_kvar_blir_varning_och_varvet_star():
    """Lagar rundan inget står varvets papper kvar, önskemålet gick igenom,
    och fyndet syns som varning. Aldrig en andra runda."""
    varv = _med_tips(_exam(), 2)
    llm, calls = _llm(varv, varv)          # lagningen svarar med samma tips
    res = exam_gen.refine_exam(_exam(), "skriv om den", nummer=2, model="m",
                               llm=llm)
    assert len(_reparationer(calls)) == 1
    assert TIPS in res["exam"]["uppgifter"][1]["text"]
    assert [e for e in res["errors"] if e.get("code") == "anivavakt"
            and "uppgift 2" in e.get("path", "")]


def test_budgeten_haller():
    """Är rundorna slut blir fynden varningar direkt, utan anrop."""
    varv = _med_tips(_exam(), 2)
    llm, calls = _llm(varv)
    res = exam_gen.refine_exam(_exam(), "skriv om den", nummer=2, model="m",
                               llm=llm, max_rounds=1)
    assert _reparationer(calls) == []
    assert TIPS in res["exam"]["uppgifter"][1]["text"]
    assert [e for e in res["errors"] if e.get("code") == "anivavakt"]


def test_rorda_uppgifter_ser_notisen_men_inte_platen():
    """Tipset bor ofta i `notis` (prov 88), som andrade_uppgifter inte läser;
    plåten faller ur varje omskriven uppgift utan att modellen valt det."""
    fore = _exam()
    fore["uppgifter"][2]["scen"] = {"begrepp": "hage", "plat": "a-1"}
    efter = copy.deepcopy(fore)
    efter["uppgifter"][1]["notis"] = "Tips: faktorisera."
    efter["uppgifter"][2]["scen"].pop("plat")
    assert exam_gen._rorda_uppgifter(fore, efter) == {2}
