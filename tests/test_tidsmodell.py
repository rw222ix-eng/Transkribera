"""Tidsmodellen mot riktiga nationella prov.

Konstanterna i exam_spec.MIN_PER_POANG var gissade ur «praxis och
lärarerfarenhet» tills de mättes mot NpMa2a vt 2017 och vt 2022. Det är lätt
gjort att skruva ett sådant tal igen — någon tycker att ett prov blev för långt
och drar ned E-vikten en tiondel — och då är mätningen borta utan att något går
sönder. Den här sviten är spärren: fakta ur de fyra delproven ligger hårdkodade
nedan, och modellen måste fortsätta träffa deras provtider.

Bara siffrorna står här. Provtexterna är Skolverkets och hör inte hemma i
repot; det som finns kvar av dem är antal uppgifter, poängtripplarnas summor
och den tryckta provtiden.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import exam_spec


PLAN_JS = Path(__file__).resolve().parent.parent / "app" / "web" / "ui" / "plan.js"

# ── Underlaget: fyra delprov, uppräknade ur uppgiftshäftena ────────────────
# (namn, huvuduppgifter, deluppgifter, E, C, A, provtid)
#
# Deluppgifterna räknas som de står i häftet — uppgift 1 a) b) är två. De
# används inte av modellen (den räknar huvuduppgifter, precis som våra papper
# räknar sina) men står med för att en framtida modell ska kunna prövas mot dem
# utan att någon måste läsa proven igen.
#
# Kortsvarspoängen (delprov B i sin helhet plus de enskilda uppgifter som är
# märkta «Endast svar krävs» — vt17:10b, vt22:19, 20 och 21) står i sista
# fältet. De används bara av test_kortsvarsrabatten_saknar_stod, som håller
# fast vid att rabatten förkastades av DATAT och inte av lathet.
DELPROV: list[dict] = [
    {"namn": "NpMa2a vt17 delprov B+C", "uppgifter": 15, "deluppgifter": 22,
     "e": 12, "c": 9, "a": 7, "provtid": 120, "kortsvar": (7, 7, 2)},
    {"namn": "NpMa2a vt17 delprov D", "uppgifter": 9, "deluppgifter": 13,
     "e": 11, "c": 10, "a": 6, "provtid": 120, "kortsvar": (0, 0, 0)},
    {"namn": "NpMa2a vt22 delprov B+C", "uppgifter": 17, "deluppgifter": 28,
     "e": 15, "c": 13, "a": 6, "provtid": 120, "kortsvar": (11, 6, 4)},
    {"namn": "NpMa2a vt22 delprov D", "uppgifter": 11, "deluppgifter": 12,
     "e": 8, "c": 7, "a": 6, "provtid": 120, "kortsvar": (4, 0, 0)},
]

# Provens egen totalsumma, tryckt på första sidan i varje häfte. Ett facit över
# uppräkningen ovan: går delproven inte ihop till den här summan har någon läst
# fel, och då är kalibreringen värdelös oavsett vad modellen svarar.
PROV = [
    {"namn": "NpMa2a vt 2017", "delprov": (0, 1),
     "poang": 55, "e": 23, "c": 19, "a": 13, "provtid": 240},
    {"namn": "NpMa2a vt 2022", "delprov": (2, 3),
     "poang": 55, "e": 23, "c": 20, "a": 12, "provtid": 240},
]

# NP:s provtid är ARBETSTID. Skolverket delar inte ut häften i den, och
# MIN_START_OCH_SLUT är lärarens overhead runt sin egen lektion — den ska
# därför inte finnas med i jämförelsen. Modellens arbetstidsdel räknas här och
# inte via tidsatgang(), som både lägger på åttan och avrundar till fem.
def _arbetstid(rad: dict) -> float:
    """Poäng- och uppgiftstermerna, utan start/slut och utan avrundning."""
    return (rad["e"] * exam_spec.MIN_PER_POANG["e"]
            + rad["c"] * exam_spec.MIN_PER_POANG["c"]
            + rad["a"] * exam_spec.MIN_PER_POANG["a"]
            + rad["uppgifter"] * exam_spec.MIN_PER_UPPGIFT)


def _fel(rad: dict) -> float:
    """Relativt fel mot provtiden, i procent. Positivt = modellen tror att
    delprovet tar längre tid än det får ta."""
    return (_arbetstid(rad) / rad["provtid"] - 1) * 100


# ── uppräkningen ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("prov", PROV, ids=lambda p: p["namn"])
def test_uppraekningen_gar_ihop_med_provets_egen_summa(prov):
    delar = [DELPROV[i] for i in prov["delprov"]]
    for niva in ("e", "c", "a"):
        assert sum(d[niva] for d in delar) == prov[niva], niva
    assert sum(d["e"] + d["c"] + d["a"] for d in delar) == prov["poang"]
    assert sum(d["provtid"] for d in delar) == prov["provtid"]


def test_deluppgifterna_ar_minst_lika_manga_som_uppgifterna():
    for d in DELPROV:
        assert d["deluppgifter"] >= d["uppgifter"], d["namn"]
        assert sum(d["kortsvar"]) <= d["e"] + d["c"] + d["a"], d["namn"]


# ── passningen ────────────────────────────────────────────────────────────

# Delprovstoleransen är vald, inte önskad. NP:s egen tidstäthet spretar från
# 3,53 till 5,71 minuter per poäng mellan de fyra delproven, och ingen rak
# modell i poäng + antal uppgifter kan träffa alla fyra tätare än ±19 % med
# nivåvikter som går att försvara. 25 % lämnar plats för den spretningen och
# fäller ändå de gamla gissningarna med marginal (de låg 25–51 % fel).
TOLERANS_DELPROV = 25.0
# Hela provet är den siffra modellen faktiskt är byggd för att träffa: 55 poäng
# på 240 minuter, båda åren. Där finns ingen spretning att gömma sig bakom.
TOLERANS_PROV = 5.0


@pytest.mark.parametrize("rad", DELPROV, ids=lambda d: d["namn"])
def test_modellen_traeffar_delprovets_provtid(rad):
    fel = _fel(rad)
    assert abs(fel) <= TOLERANS_DELPROV, (
        f"{rad['namn']}: modellen säger {_arbetstid(rad):.0f} min, "
        f"provet ger {rad['provtid']} min ({fel:+.1f} %)")


@pytest.mark.parametrize("prov", PROV, ids=lambda p: p["namn"])
def test_modellen_traeffar_hela_provets_tid(prov):
    delar = [DELPROV[i] for i in prov["delprov"]]
    minuter = sum(_arbetstid(d) for d in delar)
    fel = (minuter / prov["provtid"] - 1) * 100
    assert abs(fel) <= TOLERANS_PROV, (
        f"{prov['namn']}: modellen säger {minuter:.0f} min, "
        f"provet ger {prov['provtid']} min ({fel:+.1f} %)")


def test_modellen_lutar_inte_at_ett_hall():
    """Fyra delprov som alla ligger 20 % fel åt samma håll är en modell som är
    fel skalad, även om varje enskilt fel ryms i toleransen."""
    medel = sum(_fel(d) for d in DELPROV) / len(DELPROV)
    assert abs(medel) <= 5.0, f"systematiskt fel {medel:+.1f} %"


def test_gamla_gissningarna_skulle_ha_fallit():
    """Spärren måste bita. 1,6/2,2/3,1 var husets tal före mätningen — de ska
    inte kunna smyga tillbaka."""
    gamla = {"e": 1.6, "c": 2.2, "a": 3.1}
    varst = max(
        abs((sum(d[n] * gamla[n] for n in gamla)
             + d["uppgifter"] * exam_spec.MIN_PER_UPPGIFT)
            / d["provtid"] - 1) * 100
        for d in DELPROV)
    assert varst > TOLERANS_DELPROV, \
        "toleransen är så vid att den gamla gissningen ryms — den mäter inget"


def test_kortsvarsrabatten_saknar_stod():
    """Prövad och förkastad, och det ska gå att se varför utan att räkna om
    det för hand.

    Rabattens mekanism är att poäng där «Endast svar krävs» kostar mindre tid.
    Håller den ska modellen överskatta ett delprov ju större dess
    kortsvarsandel är. Det gör den inte: vt22 delprov D har 19 % kortsvarspoäng
    och underskattas MEST av alla fyra, medan vt17 delprov D utan en enda
    kortsvarspoäng ligger närmare. Rangordningen är alltså bruten, och det som
    ser ut som en rabatt är i själva verket skillnaden mellan delprov B/C och
    delprov D."""
    andel = {d["namn"]: sum(d["kortsvar"]) / (d["e"] + d["c"] + d["a"])
             for d in DELPROV}
    fel = {d["namn"]: _fel(d) for d in DELPROV}
    d17 = "NpMa2a vt17 delprov D"
    d22 = "NpMa2a vt22 delprov D"
    assert andel[d17] == 0 and andel[d22] > 0.15
    assert fel[d22] < fel[d17], \
        "kortsvarsandelen förklarar felen — pröva rabatten igen"


# ── de två implementationerna ─────────────────────────────────────────────

def test_frontenden_raknar_med_samma_tal():
    """Modellen är dubblerad: exam_spec.tidsatgang och plan.js uppskatta().
    Ett tal som räknas på två ställen blir förr eller senare två tal, så
    plan.js läses här som text och jämförs siffra för siffra."""
    js = PLAN_JS.read_text(encoding="utf-8")
    m = re.search(r"const PER_NIVA = \{\s*E:\s*([\d.]+),\s*C:\s*([\d.]+),"
                  r"\s*A:\s*([\d.]+)\s*\}", js)
    assert m, "PER_NIVA hittades inte i plan.js"
    assert [float(x) for x in m.groups()] == [
        exam_spec.MIN_PER_POANG["e"],
        exam_spec.MIN_PER_POANG["c"],
        exam_spec.MIN_PER_POANG["a"]], "plan.js PER_NIVA har glidit"

    u = re.search(r"antal \* ([\d.]+) \+ (\d+)\) / 5", js)
    assert u, "uppskatta() ser inte ut som den brukar"
    assert float(u.group(1)) == exam_spec.MIN_PER_UPPGIFT
    assert float(u.group(2)) == exam_spec.MIN_START_OCH_SLUT

    # TAKTEN ÄR DUBBLERAD PÅ SAMMA SÄTT och måste läsas med. Faktorn ligger på
    # poängtermen i båda implementationerna; glider den isär får skärmen och
    # servern olika provtid för samma papper.
    for namn, varde in (("NP_TAKT", exam_spec.NP_MIN_PER_POANG),
                        ("PROV_TAKT", exam_spec.PROV_MIN_PER_POANG)):
        t = re.search(r"const %s = ([\d.]+);" % namn, js)
        assert t, f"{namn} hittades inte i plan.js"
        assert float(t.group(1)) == varde, f"plan.js {namn} har glidit"
    # Faktorn räknas likadant: takt / NP, spärrad till [1, 2·NP].
    assert "Math.min(Math.max(v, 1), 2 * NP_TAKT) / NP_TAKT" in js
    # … och den ligger på POÄNGTERMEN, inte på uppgiftstermen eller overheaden.
    assert "* taktfaktor(taktFor(v));" in js


# ── takten: lärarens val, inte husets ─────────────────────────────────────

def test_takten_ar_ett_mellanting_mellan_np_och_lararens_forlaga():
    """Tre mätpunkter, alla 2026-08-22 (se exam_spec vid NP_MIN_PER_POANG):
    NP 4,4 min/poäng (55 p på 240 min), lärarens egen förlaga 2,4 (Ma2c
    kapitel 2, 37 p på 90 min) och hennes val 3,5 däremellan. «NP:s 4,4 är för
    mycket, det hinner jag inte under en lektion. En bra avvägning att prova är
    3,5.»"""
    assert exam_spec.NP_MIN_PER_POANG == 4.4
    assert exam_spec.FORLAGA_MIN_PER_POANG == 2.4
    assert exam_spec.PROV_MIN_PER_POANG == 3.5
    assert (exam_spec.FORLAGA_MIN_PER_POANG
            < exam_spec.PROV_MIN_PER_POANG
            < exam_spec.NP_MIN_PER_POANG)
    # NP-talet är verkligen provens: 55 poäng på 240 minuter.
    assert abs(240 / 55 - exam_spec.NP_MIN_PER_POANG) < 0.1
    # Förlagans likaså: 37 poäng på 90 minuter.
    assert abs(90 / 37 - exam_spec.FORLAGA_MIN_PER_POANG) < 0.1
    # Faktorn på poängtermen: 3,5/4,4 ≈ 0,80.
    assert abs(exam_spec.taktfaktor(exam_spec.PROV_MIN_PER_POANG) - 0.80) < 0.01


def test_np_kalibreringen_ar_ororrd_utan_takt():
    """Takten är ett PÅSLAG, inte en ändring av mätningen: utan `takt` räknar
    modellen exakt som före väljaren, och det är det som håller NP-testerna
    ovan giltiga."""
    rad = DELPROV[0]
    summor = {"e": rad["e"], "c": rad["c"], "a": rad["a"]}
    vantat = round((_arbetstid(rad) + exam_spec.MIN_START_OCH_SLUT) / 5) * 5
    assert exam_spec.tidsatgang(summor, rad["uppgifter"]) == vantat
    assert exam_spec.tidsatgang(summor, rad["uppgifter"],
                                takt=exam_spec.NP_MIN_PER_POANG) == vantat
    assert exam_spec.taktfaktor(None) == 1.0
    # Skräp i fältet får aldrig ge ett prov utan tid.
    for skrap in ("", "abc", 0, -3, None):
        assert exam_spec.taktfaktor(skrap) == 1.0
    # Spärren: under en minut per poäng och över dubbla NP är skrivfel.
    assert exam_spec.taktfaktor(0.2) == exam_spec.taktfaktor(1.0)
    assert exam_spec.taktfaktor(99) == exam_spec.taktfaktor(2 * 4.4)


def test_takten_ger_ett_tatare_prov_an_np():
    """Utfallet läraren ville se: 80 minuter ska bära ~20 poäng med 3,5-takten,
    inte 16–18 som NP-modellen gav. Räknat på det skelett som skulle byggas."""
    np = exam_spec.foreslag_antal(80, "prov", takt=exam_spec.NP_MIN_PER_POANG)
    hennes = exam_spec.foreslag_antal(80, "prov")
    assert hennes["takt"] == exam_spec.PROV_MIN_PER_POANG
    assert hennes["poang"] > np["poang"], (np, hennes)
    assert 19 <= hennes["poang"] <= 25, hennes
    assert hennes["antal"] > np["antal"]


def test_diagnosen_behaller_np_takten():
    """Diagnosen räknar UPPGIFTER ur en given lektion. Att pressa takten där
    vore att fylla lektionen i stället för att mäta den."""
    assert exam_spec.takt_for("diagnos") == exam_spec.NP_MIN_PER_POANG
    assert exam_spec.takt_for("prov") == exam_spec.PROV_MIN_PER_POANG
    assert exam_spec.takt_for("arbetsblad") == exam_spec.PROV_MIN_PER_POANG
    js = PLAN_JS.read_text(encoding="utf-8")
    assert "v.typ === 'Diagnos' ? NP_TAKT" in js


def test_takten_reser_med_dokumentet():
    """Valet är lärarens och ska gå att läsa av ett halvår senare — därför i
    upplägget (inst.Prov.takt), som klonas in i dokumentet (nyVersion)."""
    js = PLAN_JS.read_text(encoding="utf-8")
    assert "formelblad: true, takt: 3.5 }" in js
    assert 'class="taktfalt"' in js, "takten syns inte i panelen"
    assert "Takt <input" in js


# ── «Föreslå antal»: provtiden in, antalet uppgifter ut ───────────────────

def test_foreslag_antal_landar_inom_fem_minuter_fran_provtiden():
    """«Föreslå antal» följt av «Uppskatta tiden» ska landa på ingångstiden.

    Det är hela poängen med att räkna på SKELETTET i stället för på en
    snittkostnad per uppgift: poängsumman hoppar två och tre steg mellan
    intilliggande antal, och snittet slog fel med upp till en kvart på små
    papper."""
    for tid in range(40, 125, 5):
        r = exam_spec.foreslag_antal(tid, "prov")
        assert abs(r["tid"] - tid) <= 5, (tid, r)
        assert r["antal"] >= 1


def test_foreslag_antal_raknar_samma_tid_som_uppskattningen():
    """Talen får inte komma ur två modeller. Förslagets `tid` ska vara exakt
    det tidsatgang() säger om samma skelett."""
    for tid in (60, 80, 90, 120):
        r = exam_spec.foreslag_antal(tid, "prov")
        slots = exam_spec.balanced_skeleton(r["antal"], "prov", delar=True)
        summor = exam_spec.poangsummor(exam_spec._skeleton_doc(slots))
        assert summor["total"] == r["poang"]
        assert exam_spec.tidsatgang(summor, len(slots),
                                    takt=r["takt"]) == r["tid"]


def test_lararens_exempel():
    """Talen ur kommentaren, så att de inte kan glida: med 3,5-takten ger 80
    minuter 9 uppgifter och 20 poäng, 90 ger 10 och 21, 100 ger 11 och 24 —
    och 9 uppgifter på 20 poäng kostar ~80 minuter tillbaka."""
    assert exam_spec.foreslag_antal(80, "prov")["antal"] == 9
    assert exam_spec.foreslag_antal(80, "prov")["poang"] == 20
    assert exam_spec.foreslag_antal(90, "prov")["antal"] == 10
    assert exam_spec.foreslag_antal(100, "prov")["antal"] == 11
    slots = exam_spec.balanced_skeleton(9, "prov", delar=True)
    summor = exam_spec.poangsummor(exam_spec._skeleton_doc(slots))
    assert exam_spec.tidsatgang(
        summor, 9, takt=exam_spec.PROV_MIN_PER_POANG) == 80


def test_knappen_finns_och_fragar_servern():
    """Räkningen bor på ETT ställe (exam_spec.foreslag_antal) därför att den
    behöver skelettet — skärmen har inget. Knappen frågar alltså rutten."""
    js = PLAN_JS.read_text(encoding="utf-8")
    assert "data-foreslag" in js
    assert "/api/exams/foreslag-antal?tid=" in js
    assert "foreslag: true," in js


def test_tidsatgang_ar_arbetstiden_plus_overhead():
    """Det tidsatgang() lägger till utöver arbetstiden är exakt overheaden —
    inget annat har smugit sig in i formeln."""
    rad = DELPROV[0]
    summor = {"total": rad["e"] + rad["c"] + rad["a"],
              "e": rad["e"], "c": rad["c"], "a": rad["a"]}
    vantat = round((_arbetstid(rad) + exam_spec.MIN_START_OCH_SLUT) / 5) * 5
    assert exam_spec.tidsatgang(summor, rad["uppgifter"]) == vantat


# ── EN SANNING FÖRE SKRIVNINGEN ───────────────────────────────────────────
#
# LÄRAREN 2026-08-22: «Föreslå antal» gav tio uppgifter och 24 poäng, och
# «Uppskatta tiden» svarade sedan 16/8/0 E/C/A. Noll A-poäng på ett balanserat
# prov — omöjligt, och ändå var båda talen «rätt» i sin egen modell. Förslaget
# räknade på skelettet (balanced_skeleton med NP_TRIPPLAR), skärmen gissade
# fördelningen ur poängen per uppgift (plan.js ecaDel, som ger A först vid fem
# poäng på EN uppgift). Testerna nedan låser att det bara finns en modell kvar.

def test_skelettet_bar_a_poang_pa_ett_balanserat_prov():
    """Regressionen läraren såg: tio uppgifter, Balanserat, noll A-poäng."""
    r = exam_spec.skelettsummor(10, "prov")
    assert r["summor"]["a"] > 0, r
    assert r["summor"]["e"] > 0 and r["summor"]["c"] > 0, r
    assert sum(r["summor"].values()) == r["poang"]


@pytest.mark.parametrize("antal", range(1, 21))
def test_skelettsummor_ar_samma_skelett_som_byggs(antal):
    """Summorna får inte komma ur en egen räkning vid sidan av skelettet."""
    r = exam_spec.skelettsummor(antal, "prov")
    slots = exam_spec.balanced_skeleton(antal, "prov", delar=True)
    summor = exam_spec.poangsummor(exam_spec._skeleton_doc(slots))
    assert r["antal"] == len(slots)
    assert r["poang"] == summor["total"]
    assert r["summor"] == {n: summor[n] for n in ("e", "c", "a")}
    assert r["tid"] == exam_spec.tidsatgang(
        summor, len(slots), takt=exam_spec.PROV_MIN_PER_POANG)


@pytest.mark.parametrize("tid", range(40, 125, 5))
def test_de_tva_knapparna_sager_samma_sak(tid):
    """«Föreslå antal» och «Uppskatta tiden» ska ge SAMMA poäng, samma E/C/A
    och samma tid för samma antal, mix och takt — det är hela buggen."""
    forslag = exam_spec.foreslag_antal(tid, "prov")
    uppskattning = exam_spec.skelettsummor(forslag["antal"], "prov",
                                           takt=forslag["takt"])
    assert uppskattning["poang"] == forslag["poang"]
    assert uppskattning["summor"] == forslag["summor"]
    assert uppskattning["tid"] == forslag["tid"]


@pytest.mark.parametrize("mix", ["Bara E", "E-tyngd", "C/A-tyngd"])
def test_nivamixen_foljer_med_till_skelettet(mix):
    """Väljaren ska synas i fördelningen. Gör den inte det svarar knappen på
    ett annat prov än det som står i panelen."""
    val = exam_spec.nivaval("prov", mix)
    egen = exam_spec.skelettsummor(10, "prov", mix=val["mix"],
                                   niva_mal=val["mal"])["summor"]
    balanserat = exam_spec.skelettsummor(10, "prov")["summor"]
    assert egen != balanserat, (mix, egen)
    if mix == "Bara E":
        assert egen["a"] == 0 and egen["e"] > balanserat["e"]
    if mix == "C/A-tyngd":
        assert egen["e"] < balanserat["e"]


def test_takten_andrar_tiden_men_inte_poangen():
    """Takten sitter på poängtermen. Ett tätare prov är inte ett annat prov."""
    np = exam_spec.skelettsummor(10, "prov", takt=exam_spec.NP_MIN_PER_POANG)
    hennes = exam_spec.skelettsummor(10, "prov",
                                     takt=exam_spec.FORLAGA_MIN_PER_POANG)
    assert np["summor"] == hennes["summor"]
    assert np["poang"] == hennes["poang"]
    assert hennes["tid"] < np["tid"]


def test_uppskattningen_gissar_inte_pa_oskrivna_prov():
    """Skärmen ska fråga rutten så länge pappret är oskrivet, och ecaDel bara
    finnas kvar som nödutgång när servern inte svarar."""
    js = PLAN_JS.read_text(encoding="utf-8")
    assert "/api/exams/skelett?antal=" in js
    # Mixen och takten måste med i frågan — annars svarar rutten på ett annat
    # prov än det som står i panelen.
    assert "&nivamix=${encodeURIComponent(i.nivamix" in js
    assert "&takt=${taktFor(v)}" in js
    # ecaDel får anropas på exakt ETT ställe: inuti uppskatta(), som numera är
    # fallbacken. Dyker den upp någon annanstans har gissningen krupit tillbaka.
    assert js.count("ecaDel(") == 2, "ecaDel ska definieras och anropas en gång"
    # Fallbacken ska synas för läraren.
    assert "(uppskattad fördelning)" in js
    # Skrivna prov räknar på dokumentets egna tripplar.
    assert "barPeca(u) ? (skrivna++, u.peca) : ecaDel(u.p, mix)" in js
    assert "if (!lokalt.gissat) { visaUppskattning(v, lokalt); return; }" in js


def test_foreslag_antal_far_lararens_takt_med_sig():
    """Takten stod i toasten men inte i frågan — 2,4 min/p gav ett antal
    räknat på 3,5 med «takt 2,4 min/p» tryckt bredvid."""
    js = PLAN_JS.read_text(encoding="utf-8")
    assert "/api/exams/foreslag-antal?tid=" in js
    assert "+ `&takt=${takt}`" in js


def test_rutten_svarar_med_summor(client):
    """Skelettrutten och förslagsrutten ska bära E/C/A, och samma E/C/A."""
    r = client.get("/api/exams/skelett?antal=10&typ=prov&takt=3.5")
    assert r.status_code == 200, r.text
    kropp = r.json()
    assert kropp["antal"] == 10
    assert kropp["summor"]["a"] > 0, kropp
    f = client.get("/api/exams/foreslag-antal?tid=%d&typ=prov&takt=3.5"
                   % kropp["tid"]).json()
    assert f["antal"] == 10
    assert f["summor"] == kropp["summor"]
    assert f["poang"] == kropp["poang"]
    # Nivåmixen når fram hela vägen genom rutten.
    bara_e = client.get(
        "/api/exams/skelett?antal=10&typ=prov&nivamix=Bara%20E").json()
    assert bara_e["summor"]["a"] == 0, bara_e
