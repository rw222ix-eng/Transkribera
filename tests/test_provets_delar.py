"""Provets delar, enheter och bildstöd — lärarens sex anmärkningar 2026-08-22.

Hon körde ett skarpt prov på nio uppgifter efter dagens bygge och läste igenom
det. Sex saker föll ut, och varje test här nere är ett av dem. De hör ihop
därför att de alla handlar om SAMMA papper sett på två ställen: förhandsvisningen
i canvas och PDF:en. Fyra av de sex var att skärmen och pappret sa olika saker.

  1. Enheten «cm$^2$» trycktes med dollartecken och allt på skärmens svarsrad.
  2. OBS-rutan upprepade försättsbladets regler överst på varje del.
  3. «Fortsätter på nästa sida» i stället för papprets kursiva «Vänd →».
  4. Del A blev uppgift 1, 2 och 7 — delarna låg om varandra.
  5. Del A fick 3 uppgifter och Del B 6. NP har det tvärtom.
  6. En enda bild på hela provet.

Punkt 7 (provets takt) och 8 («Föreslå antal») bor i tests/test_tidsmodell.py,
där NP-kalibreringen redan står.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from app import exam_gen, exam_latex, exam_spec, platar


UI = Path(__file__).resolve().parent.parent / "app" / "web" / "ui"


# ══════════════════════════════════════════════════════════════════════
# Canvasens byggare körd på riktigt
#
# blad-bygg.js är REN: den bygger HTML-strängar och rör aldrig DOM:en (till
# skillnad från blad.js, som mäter och paginerar). Den går därför att köra i
# node med ett tomt `window` — och då prövas det som faktiskt hamnar på
# skärmen, inte en regex mot källkoden. Saknas node hoppas testet över; de
# textbaserade proven nedanför gäller ändå.
# ══════════════════════════════════════════════════════════════════════

def _kor_bladbygg(anrop: str) -> str:
    """Kör blad-bygg.js i node och returnera vad `anrop` gav (en HTML-sträng)."""
    if not shutil.which("node"):
        pytest.skip("node saknas — canvasbygget körs inte")
    skript = (
        "const fs = require('fs');\n"
        "global.window = {};\n"
        f"eval(fs.readFileSync({json.dumps(str(UI / 'blad-bygg.js'))}, 'utf8'));\n"
        "const bb = global.window.BladBygg;\n"
        f"process.stdout.write(String({anrop}));\n"
    )
    with tempfile.TemporaryDirectory() as d:
        fil = Path(d) / "kor.js"
        fil.write_text(skript, encoding="utf-8")
        r = subprocess.run(["node", str(fil)], capture_output=True, text=True,
                           encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout


def _canvasprov(uppgifter: list[dict], **doc) -> str:
    v = {"typ": "Prov", "moment": "derivata", "kurs": "Matematik 3c",
         "klass": "NA25", "titel": "Prov — derivata", **doc}
    return _kor_bladbygg(
        f"bb.provblad({json.dumps(v, ensure_ascii=False)}, "
        f"{json.dumps(uppgifter, ensure_ascii=False)}, 'B')")


def _uppg(**extra) -> dict:
    return {"nr": 1, "p": 2, "t": "Bestäm arean.", "ut": "kort",
            "niva": "E", **extra}


# ── 1. ENHETEN ─────────────────────────────────────────────────────────

def test_enheten_ar_matematik_och_renderas_som_matematik():
    """«cm$^2$» ska bli cm² på svarsraden, inte texten «cm$^2$».

    Fältet bär TeX inom dollartecken (exam_spec.enhet — samma sträng som
    LaTeX-mallen sätter i matteläge), och canvas escapade den som ren text.
    Läraren fick dollartecknen tryckta i förhandsvisningen medan PDF:en satte
    cm²: två papper, samma prov, olika svarsrad."""
    html = _canvasprov([_uppg(enhet="cm$^2$")])
    assert "cm$^2$" not in html, "enheten trycktes ordagrant"
    # mat() delar på $ och lägger matten i .mat med data-tex — det är den
    # KaTeX sedan renderar (samma väg som all annan matte på bladet).
    assert 'class="prenhet">cm<span class="mat" data-tex="^2"' in html


def test_enheten_som_ar_ett_led_renderas_ocksa():
    """Ledet «$f'(x) =$» är samma fält och samma väg — hela strängen är matte
    där, och en oescapad apostrof i ett HTML-attribut får inte bryta ut."""
    html = _canvasprov([_uppg(enhet="$f'(x) =$")])
    assert "data-tex=\"f'(x) =\"" in html
    assert "$f'(x)" not in html


def test_facitets_enhet_renderas_med():
    """Samma fält, samma regel, andra pappret: lösningsförslagets svarsrad."""
    html = _kor_bladbygg(
        "bb.losning({typ:'Prov'}, "
        + json.dumps([_uppg(f="$12$", enhet="cm$^2$")], ensure_ascii=False)
        + ", 1).join('')")
    assert "cm$^2$" not in html
    assert '<span class="mat" data-tex="^2"' in html


def test_latexmallen_satter_enheten_i_matteläge():
    """Andra änden av samma kedja: i TeX ska «cm$^2$» bli «cm\\(^2\\)» —
    matteläge — och inte escapade dollartecken."""
    tex = exam_latex.escape_mixed("cm$^2$")
    assert tex == r"cm\(^2\)"
    assert r"\$" not in tex


# ── 2. OBS-RUTAN ───────────────────────────────────────────────────────

def test_obs_rutan_ar_borta_ur_canvas():
    """«Det framgår redan på försättsbladet vad som är tillåtet» (läraren).

    Rutan upprepade hjälpmedelsregeln, redovisningsregeln och lösbladsregeln
    överst på varje dels första ark. PDF:en har aldrig haft den."""
    html = _canvasprov([_uppg()], hjalpmedel="Räknare är inte tillåtna.")
    assert "probs" not in html
    assert "OBS!" not in html
    assert "rutat lösblad" not in html
    # Delnamnet i huvudet står kvar: det är vilket papper man håller i.
    assert "Del A" in html


def test_obs_rutan_finns_inte_i_latexmallen_heller():
    mall = (Path(__file__).resolve().parent.parent / "app" / "templates"
            / "prov.tex.j2").read_text(encoding="utf-8")
    assert "OBS!" not in mall


def test_inlamningsraden_ar_lararens_provrutin():
    """Eleverna får båda delarna samtidigt; räknaren hämtas först när Del A är
    inlämnad. Raden sa förut «innan du hämtar Del B», vilket beskrev en
    utdelning som inte sker."""
    from tests.test_exam import _exam
    doc, _ = exam_spec.validate_exam_json(_exam())
    tex = exam_latex.render_prov(doc)
    assert "innan du tar fram digitala verktyg" in tex
    assert "innan du hämtar" not in tex


# ── 3. VÄNDMÄRKET ──────────────────────────────────────────────────────

def test_vandmarket_pa_skarmen_ar_samma_ord_som_i_pdf():
    """PDF:en sätter {\\small\\itshape Vänd\\,} + pil i sidfotens högra fält.
    Skärmen skrev «Fortsätter på nästa sida» centrerat och stort."""
    js = (UI / "blad.js").read_text(encoding="utf-8")
    assert "const VAND = 'Vänd';" in js
    assert "Fortsätter på nästa sida" not in js
    css = (UI / "prov.css").read_text(encoding="utf-8")
    rad = [r for r in css.splitlines() if r.startswith(".prslut[data-vand]{")]
    assert rad, "vändmärkets regel hittades inte"
    # Nedre HÖGRA hörnet, kursivt och litet — inte en centrerad versalrad.
    assert "justify-content:flex-end" in rad[0]
    assert "font-style:italic" in rad[0]
    assert "font-size:13px" in rad[0]
    # Slutraden («Slut på del A …») är fortfarande sidans egen signal.
    assert ".prslut[data-slut]{text-align:center" in css


def test_vandmarket_star_inte_pa_delens_sista_ark():
    """Regeln är oförändrad och står kvar i koden: `slice(0, -1)` — alla ark
    utom det sista i sin del. Där lämnar eleven in."""
    js = (UI / "blad.js").read_text(encoding="utf-8")
    assert js.count("slice(0, -1).forEach(a => rad(a, 'data-vand', VAND))") == 2


# ── 4. DELARNA OCH NUMREringen ─────────────────────────────────────────

def _slots_till_exam(slots: list[dict]) -> dict:
    """Ett minimalt prov-JSON ur ett skelett — nog för att pröva ordningen."""
    return {"titel": "Prov", "kurs": "Matematik 3c", "klass": "NA25",
            "hjalpmedel": "Linjal.",
            "uppgifter": [{"del": s["del"], "formaga": s["formaga"],
                           "typ": s["typ"], "poang": list(s["poang"]),
                           "text": f"Uppgift {i}.", "losning": "svar",
                           "bedomning": "1 p för svaret"}
                          for i, s in enumerate(slots, 1)]}


def test_delarna_ligger_sammanhangande_i_skelettet():
    """Skelettet ska ge B…B C…C, aldrig B C B. Numreringen följer listan på
    skärmen och delgrupperingen i PDF:en; ligger de om varandra säger de två
    pappren olika saker om samma prov."""
    for antal in range(3, 21):
        slots = exam_spec.balanced_skeleton(antal, "prov", delar=True)
        delar = [s["del"] for s in slots]
        assert delar == sorted(delar, key=lambda d: exam_spec.DEL_ORDNING.index(d)), \
            f"{antal} uppgifter: delarna ligger om varandra — {delar}"
        assert set(delar) == {"B", "C"}, antal


def test_ordna_delar_rattar_ett_prov_med_delarna_om_varandra():
    """Grammatiken låser delen per index vid genereringen, men `refine_exam`
    skriver om hela dokumentet utan skelett. Sorteringen är räddningen — och
    den är STABIL: ordningen inom en del bär den stigande svårigheten."""
    exam = {"uppgifter": [{"del": "B", "text": "1"}, {"del": "B", "text": "2"},
                          {"del": "C", "text": "3"}, {"del": "C", "text": "4"},
                          {"del": "B", "text": "5"}, {"del": "C", "text": "6"}]}
    assert exam_spec.ordna_delar(exam) is True
    assert [u["del"] for u in exam["uppgifter"]] == list("BBBCCC")
    # Stabil: 1, 2, 5 i den ordningen — inte omkastade.
    assert [u["text"] for u in exam["uppgifter"]] == ["1", "2", "5", "3", "4", "6"]
    # Redan i ordning → ingen ändring och inget påstående om motsatsen.
    assert exam_spec.ordna_delar(exam) is False


def test_valideringen_lagger_delarna_i_ordning():
    """Vägen dit: allt som passerar exam_gen._validate — generering,
    reparation, riktad omgenerering, LaTeX-fix — ska komma ut sorterat."""
    slots = exam_spec.balanced_skeleton(9, "prov", delar=True)
    exam = _slots_till_exam(slots)
    # Kasta om dem som lärarens prov låg: Del A på plats 1, 2 och 7.
    upp = exam["uppgifter"]
    exam["uppgifter"] = [upp[0], upp[1], upp[6], upp[2], upp[3], upp[4],
                         upp[5], upp[7], upp[8]]
    exam_gen._validate(exam, "prov")
    delar = [u["del"] for u in exam["uppgifter"]]
    assert delar == sorted(delar, key=lambda d: exam_spec.DEL_ORDNING.index(d))


def test_numreringen_loper_och_ingen_uppgift_ligger_utanfor_sin_del():
    """PDF:ens vy: numren 1…n i följd, varje del ett sammanhängande spann."""
    doc, fel = exam_spec.validate_exam_json(
        _slots_till_exam(exam_spec.balanced_skeleton(9, "prov", delar=True)),
        "prov")
    assert doc is not None, fel
    vy = exam_latex._build_view(doc)
    nummer = [u["nummer"] for d in vy["delar"] for u in d["uppgifter"]]
    assert nummer == list(range(1, 10))
    for d in vy["delar"]:
        egna = [u["nummer"] for u in d["uppgifter"]]
        assert egna == list(range(egna[0], egna[-1] + 1)), d["rubrik"]


def test_skarmen_delar_pa_delen_och_inte_pa_nivan():
    """Buggens rot: `arE` la alla E-uppgifter i Del A. Delen handlar om
    HJÄLPMEDEL, nivån om svårighet — två olika frågor, och provet 2026-08-22
    hade en E-uppgift i räknardelen. `avd` är dokumentets del, buren hela vägen
    från exam_spec via plan.js franProv."""
    plan = (UI / "plan.js").read_text(encoding="utf-8")
    assert "avd: u.del || null," in plan, "delen når aldrig arket"
    blad = (UI / "blad.js").read_text(encoding="utf-8")
    assert "const iDelA = (u, avdelat) => (avdelat ? u.avd === 'B' : arE(u));" in blad
    # Nivåfallbacken finns kvar för prototypens papper, men bara när INGEN
    # uppgift bär `avd` — ett halvt taggat prov ska inte bli halvt nivådelat.
    assert "const harAvd = lista => (lista || []).some(u => u && u.avd);" in blad
    # Och ingen av provets delningar räknar på nivån längre.
    for rad in blad.splitlines():
        if "filter(arE)" in rad:
            assert "pool" in rad or "valj" in rad, \
                f"provets delning räknar fortfarande på nivån: {rad.strip()}"


# ── 5. BALANSEN MELLAN DELARNA ─────────────────────────────────────────
#
# NP:s egna tal (NpMa2a, uppgiftshäftena):
#
#   prov   utan verktyg (B+C)        med verktyg (D)          andel utan
#   vt17   15 uppg / 28 p / 120 min   9 uppg / 27 p / 120 min  62,5 % / 51 %
#   vt22   17 uppg / 34 p / 120 min  11 uppg / 21 p / 120 min  60,7 % / 62 %
#
# FLER uppgifter i den räknarfria delen, ungefär LIKA poäng. Lärarens prov blev
# tvärtom: 3 uppgifter i Del A och 6 i Del B.

NP_DELPROV = [
    {"namn": "NpMa2a vt17", "utan_uppg": 15, "utan_p": 28,
     "med_uppg": 9, "med_p": 27},
    {"namn": "NpMa2a vt22", "utan_uppg": 17, "utan_p": 34,
     "med_uppg": 11, "med_p": 21},
]


def test_np_ligger_dar_vi_pastar_att_det_ligger():
    """Facit över uppräkningen ovan: NP lägger 60–63 % av uppgifterna och
    51–62 % av poängen i den räknarfria delen. Ändras talen ska det synas."""
    for p in NP_DELPROV:
        andel_uppg = p["utan_uppg"] / (p["utan_uppg"] + p["med_uppg"])
        andel_poang = p["utan_p"] / (p["utan_p"] + p["med_p"])
        assert 0.58 <= andel_uppg <= 0.65, p["namn"]
        assert 0.45 <= andel_poang <= 0.65, p["namn"]
    assert exam_spec.DEL_B_ANDEL == 0.60


def _delsummor(antal: int) -> tuple[int, int, int, int]:
    """(uppgifter i Del A, poäng i Del A, uppgifter i Del B, poäng i Del B)."""
    slots = exam_spec.balanced_skeleton(antal, "prov", delar=True)

    def poang(s):
        d = s.get("deluppgifter")
        return sum(sum(x["poang"]) for x in d) if d else sum(s["poang"])
    a = [s for s in slots if s["del"] == "B"]
    b = [s for s in slots if s["del"] == "C"]
    return len(a), sum(poang(s) for s in a), len(b), sum(poang(s) for s in b)


def test_nio_uppgifter_ger_lararens_form():
    """Det prov hon faktiskt skrev: nio uppgifter. Del A ≥ 5, Del B ≤ 4, och
    poängen i Del A mellan 45 och 65 procent — NP:s spann."""
    na, pa, nb, pb = _delsummor(9)
    assert na >= 5, f"Del A fick bara {na} uppgifter"
    assert nb <= 4, f"Del B fick {nb} uppgifter"
    assert na + nb == 9
    assert 0.45 <= pa / (pa + pb) <= 0.65, f"Del A bär {pa} av {pa + pb} poäng"


@pytest.mark.parametrize("antal", range(5, 21))
def test_delfordelningen_ar_np_trogen_for_varje_antal(antal):
    """Andelen räknas på HELA provet och fördelas ut med största rest — förut
    avrundades den per karaktärsgrupp, och tre nedåtavrundningar i rad gav 50
    procent i stället för 60."""
    na, pa, nb, pb = _delsummor(antal)
    andel = na / (na + nb)
    assert 0.53 <= andel <= 0.68, \
        f"{antal} uppgifter: Del A fick {na} av {na + nb} ({andel:.0%})"
    assert na > nb, f"{antal} uppgifter: fler i Del B än i Del A"
    assert 0.45 <= pa / (pa + pb) <= 0.68, \
        f"{antal} uppgifter: Del A bär {pa} av {pa + pb} poäng"


# ── 6. BILDERNA ────────────────────────────────────────────────────────

def test_prompten_ber_om_flera_bilder_spridda_over_bada_delarna():
    """«Skulle kunna ha flera bilder bara för att det ska bli mer estetiskt
    snyggt — det behöver inte hjälpa» (läraren). Regeln bad förut om «högst
    ungefär var tredje uppgift» och gav EN bild på nio."""
    r = exam_gen.SCEN_REGEL
    assert "minst två eller tre" in r
    assert "BÅDA delarna" in r
    assert "var tredje uppgift" not in r
    # Gränsen som står kvar: en uppgift utan situation har inget att måla.
    assert "ALDRIG scen" in r and "utan situation" in r.lower()


def test_samma_plat_valjs_inte_tva_ganger_i_samma_prov():
    """Två identiska bilder på ett prov läser som ett tryckfel. Andra träffen
    ska ta näst bästa plåt — eller ingen alls, och då står SCENE-stycket
    framme."""
    exam = {"uppgifter": [
        {"text": "En inhägnad vid floden.",
         "scen": {"begrepp": "optimering inhägnad", "scene": "x", "filnamn": "a"}},
        {"text": "En annan inhägnad vid floden.",
         "scen": {"begrepp": "optimering inhägnad", "scene": "y", "filnamn": "b"}},
    ]}
    platar.matcha_exam(exam)
    valda = [u["scen"].get("plat") for u in exam["uppgifter"]]
    assert valda[0], "första uppgiften fick ingen plåt alls — testet mäter inget"
    assert valda[0] != valda[1], f"samma plåt två gånger: {valda}"


def test_lararens_egna_val_raknas_som_tagna():
    """Har hon själv lagt a-19 på uppgift 2 ska uppgift 1 inte få samma plåt
    matchad — hennes val är senare än vårt och rörs aldrig."""
    exam = {"uppgifter": [
        {"text": "En inhägnad vid floden.",
         "scen": {"begrepp": "optimering inhägnad", "scene": "x", "filnamn": "a"}},
        {"text": "En annan.", "scen": {"begrepp": "kast", "scene": "y",
                                       "filnamn": "b", "plat": "a-19-hage-flod"}},
    ]}
    platar.matcha_exam(exam)
    assert exam["uppgifter"][1]["scen"]["plat"] == "a-19-hage-flod"
    assert exam["uppgifter"][0]["scen"].get("plat") != "a-19-hage-flod"


def test_bilden_drar_med_sig_plats_pa_sidan():
    """Layouten: en uppgift med bild begär utrymme INNAN den börjar, så att
    rubriken och frågan inte blir sista raderna på en sida med bilden ensam
    överst på nästa. Egen makro, inte paketet needspace — det ligger inte i
    den seedade Tectonic-bunten."""
    preamble = (Path(__file__).resolve().parent.parent / "app" / "templates"
                / "_preamble.tex.j2").read_text(encoding="utf-8")
    assert r"\newcommand{\pfbehov}[1]" in preamble
    assert r"\usepackage{needspace}" not in preamble
    mall = (Path(__file__).resolve().parent.parent / "app" / "templates"
            / "prov.tex.j2").read_text(encoding="utf-8")
    assert r"\pfbehov{92mm}" in mall
    assert "((* if u.har_bild *))" in mall


def test_har_bild_raknas_i_python_och_inte_i_mallen():
    """Frågan «bär uppgiften någon bild?» kan inte ställas i Jinja: en tom
    selectattr-kedja är Undefined, och StrictUndefined fäller renderingen i
    stället för att svara nej. Både uppgiftens egen bild och deluppgifternas
    räknas."""
    from tests.test_exam import _exam
    exam = _exam()
    exam["uppgifter"][0]["bild"] = 1
    doc, fel = exam_spec.validate_exam_json(exam)
    assert doc is not None, fel
    vy = exam_latex._build_view(doc, bilder={1: "sida-1.png"})
    alla = [u for d in vy["delar"] for u in d["uppgifter"]]
    assert all("har_bild" in u for u in alla)
    assert alla[0]["har_bild"] is True
    assert any(u["har_bild"] is False for u in alla[1:])


# ── 7. SVARSRADEN HÖR TILL KRAVET ──────────────────────────────────────
#
# LÄRARENS DOM 2026-08-22, om uppgift 7 på hennes nya prov («Undersök vilka tal
# $a$ … Ange villkoret på $a$ och förklara varför övriga fall måste uteslutas»,
# 2 p, Fullständig lösning krävs): «Fullständig lösning krävs ⇒ eleven skriver
# på lösblad ⇒ INGEN svarsrad på provpappret. Svar: ____ finns BARA på
# uppgifter/deluppgifter med Endast svar krävs.»
#
# Canvas satte raden på VARJE uppgift som inte redan hade en annan svarsplats
# — villkoret frågade efter alternativ, deluppgifter och kryssrutor, aldrig
# efter kravet. En tom linje under en fråga säger «skriv svaret här», alltså
# raka motsatsen till kravraden två rader ovanför.
#
# Papprets ände mäts i tests/test_forlaga_matt.py
# (test_ingen_svarsrad_pa_redovisningsuppgift).

def test_svarsraden_star_bara_pa_kortsvaren():
    html = _canvasprov([
        _uppg(nr=1, ut="kort", enhet="kr"),
        _uppg(nr=2, ut="rakna", t="Undersök vilka tal $a$ som kan ges "
                                  "potensen $a^{0} = 1$. Ange villkoret."),
    ])
    assert html.count("prsvarnamn") == 1, "fel antal svarsrader i arket"
    # Raden hör till uppgift 1 — den som säger «Endast svar krävs».
    ett, tva = html.split('<span class="prnr">2.')
    assert "prsvarnamn" in ett
    assert "prsvar" not in tva
    # Kravraden står kvar på båda och säger vilken som är vilken.
    assert "Endast svar krävs." in ett
    assert "Fullständig lösning krävs." in tva


def test_svarsraden_uteblir_aven_nar_uppgiften_bar_en_enhet():
    """Enheten är svarets FORM, inte ett löfte om en svarsplats. En
    redovisningsuppgift med «kr» fick förut en linje med enheten efter."""
    html = _canvasprov([_uppg(ut="rakna", enhet="kr")])
    assert "prsvar" not in html
    assert "prenhet" not in html


def test_deluppgifternas_svarsrader_foljer_samma_krav():
    # `del` är ett nyckelord i Python och går inte att skicka som kwarg —
    # nyckeln sätts därför efteråt.
    kort = _uppg(ut="kort")
    kort["del"] = ["Beräkna $2^5$.", "Beräkna $3^2$."]
    lang = _uppg(ut="rakna")
    lang["del"] = ["Visa att …", "Motivera varför …"]
    assert _canvasprov([kort]).count("prsvarnamn") == 2
    assert "prsvar" not in _canvasprov([lang])


def test_kryssrutorna_ar_kvar_som_egen_svarsplats():
    """Kryssrutorna ÄR svarsplatsen (exam_spec.Svarsrutor) och sätts av mallen
    oavsett krav — regeln ovan gäller den tomma linjen, inte rutorna."""
    html = _canvasprov([_uppg(ut="rakna", rutor={"etikett": "Sats",
                                                 "val": ["Randvinkeln",
                                                         "Kordasatsen"]})])
    assert html.count("guruta") == 2
    assert "prlinje" not in html


def test_latexvyn_slapper_svarsfaltet_pa_en_redovisningsuppgift():
    """Andra änden av samma dom: `svarsfalt_rad` är provmallens svarsplats och
    får bara finnas på kortsvaren. Listan `svarsfalt` står kvar — arbetsbladet,
    gruppuppgiften och diagnosen bygger sin form på den."""
    vy_kort = exam_latex._enhet_vy(
        poang=(1, 0, 0), typ="rutin", formaga="P", text="t", losning="l",
        bedomning="b", alternativ=None, ratt_alternativ=None, notis=None,
        bild_fil=None, svarsfalt=["Villkor"])
    vy_lang = exam_latex._enhet_vy(
        poang=(0, 0, 2), typ="redovisning", formaga="R", text="t", losning="l",
        bedomning="b", alternativ=None, ratt_alternativ=None, notis=None,
        bild_fil=None, svarsfalt=["Villkor"])
    assert vy_kort["svarsfalt_rad"] == ["Villkor:"]
    assert vy_lang["svarsfalt_rad"] is None
    assert vy_lang["svarsfalt"] == ["Villkor"]
    assert vy_lang["endast_svar"] is False
