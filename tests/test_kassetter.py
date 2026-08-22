"""Kassetterna: hela kedjan EFTER svaret, körd på riktigt (Etapp 3).

Sviten stubbar annars `llm_client.generate` eller generatorn själv — och hoppar
därmed över precis den del som brukar gå sönder: strömtolkningen i
claude_code, JSON-parsningen, schemat, balansreglerna och reparationsrundorna.

En kassett är ETT svar, sparat rad för rad som CLI:t skrev det. Den spelas upp
genom det fejkade `claude`-programmet, alltså genom appens riktiga söm — inte
genom en monkeypatch en nivå in. Det som prövas är därför: när modellen svarar
såhär, vad gör appen?

`inspelad: false` betyder att bandet är byggt ur appens egna exempel — rätt
form, men ingen modell har skrivit det. Byt ut dem mot riktiga svar med
`python -m tools.spela_in_kassett` (kräver inloggning, kostar några ören).
"""
from __future__ import annotations

import json

import pytest

from app import claude_code, exam_gen, lesson_board, postprocess, whiteboard_spec
from tests import fejk


def test_alla_kassetter_har_den_form_uppspelningen_kraver():
    namn = fejk.alla_kassetter()
    assert namn, "inga kassetter — kedjan efter svaret prövas då aldrig"
    for n in namn:
        band = fejk.las_kassett(n)
        assert band["namn"] == n
        assert band["vad"] and isinstance(band["rader"], list) and band["rader"]
        assert isinstance(band["inspelad"], bool)
        # Sista raden är result-raden: utan den vet appen inte att svaret är slut.
        sista = json.loads(band["rader"][-1])
        assert sista["type"] == "result"


def test_ett_band_gar_genom_bryggan_ord_for_ord(fejk_claude):
    """Uppspelningen ska gå genom claude_code.generate — deltan strömmade,
    texten hopsatt, kostnaden avläst — inte förbi den."""
    fejk_claude(kassett="tavla")
    bitar = []
    svar = claude_code.generate("vad som helst", token_cb=bitar.append)
    assert len(bitar) > 1, "svaret kom inte som en ström"
    assert json.loads(svar)["title"] == "Derivatans definition"
    assert claude_code.SENASTE["kostnad"] > 0


def test_tavlan_ur_kassetten_ar_giltig_wb_json(fejk_claude):
    """Hela vägen: CLI → ström → JSON → whiteboard_spec → färdig tavla."""
    fejk_claude(kassett="tavla")
    res = lesson_board.generate_board(
        "Matematik 3c", "NA25", "Derivatans definition", model="")
    assert res["errors"] == []
    assert res["rounds"] == 1
    board = res["board"]
    assert board["title"] == "Derivatans definition"
    # Samma validator som servern kör innan tavlan får skickas till klienten
    # (den tar den tolkade dicten, inte JSON-texten).
    doc, fel = whiteboard_spec.validate_board_json(board)
    assert doc is not None and fel == []


def test_en_trasig_tavla_repareras_i_nasta_runda(fejk_claude):
    """Första bandet bryter mot schemat, andra är rätt. Reparationsrundan ska
    köra på riktigt — det är den som gör att läraren får en tavla i stället för
    ett felmeddelande."""
    lagen = iter(["tavla-trasig", "tavla"])
    riktig = claude_code.generate

    def vaxla(*a, **k):
        fejk_claude(kassett=next(lagen, "tavla"))
        return riktig(*a, **k)
    import app.llm_client as llm_client
    res = lesson_board.generate_board(
        "Matematik 3c", "NA25", "Derivatans definition", model="",
        llm=lambda model, prompt, **kw: vaxla(prompt, system=kw.get("system")))
    assert res["errors"] == [], res["errors"]
    assert res["rounds"] >= 2, "reparationsrundan kördes aldrig"


def test_provet_ur_kassetten_klarar_balansreglerna(fejk_claude):
    """Den skarpa inspelningen bar tre påhittade toppfält (`totalpoang`,
    `instruktion`, `tid_minuter`) — det modellen gör när grammatiktvånget är
    borta. De städas bort vid parsningen i stället för att kosta en hel
    reparationsrunda, och resten ska hålla balansreglerna."""
    fejk_claude(kassett="prov")
    res = exam_gen.generate_exam("Matematik 3c", "NA25",
                                 ["Derivata", "Gränsvärden"], model="", antal=6)
    # Det FÖRRA bandet bar två nivåfel: en kommunikationspoäng på E-nivå (som
    # nationella provet aldrig delar ut) och en A-poäng på en «Visa att …»-
    # uppgift (som är C-nivå i underlaget). Båda är borta i omspelningen —
    # skelettet ber inte längre om EK, och rubriken i prompten säger vad ett
    # A-innehåll kräver. Det är den enda mätning vi har på att kalibreringen
    # gjorde skillnad i det modellen faktiskt skriver, och därför står den här.
    assert [e for e in res["errors"] if e["code"] == "nivasignal"] == [], \
        "nivåsignalerna tände på ett band inspelat EFTER kalibreringen"
    exam = res["exam"]
    assert exam["uppgifter"] and exam["titel"]
    from app import exam_spec
    doc, fel = exam_spec.validate_exam_json(exam)
    assert doc is not None and fel == []
    # Städningen tar de PÅHITTADE toppnycklarna — och bara dem. `instruktion`
    # står inte längre i listan: fältet blev ett riktigt ExamDoc-fält när
    # instruktionsbandet flyttade in i dokumentet, och modellen skriver det
    # (tomt) på ett prov. Vakten mäter därför mot schemat i stället för mot en
    # handskriven lista som glider ur fas med det.
    assert "totalpoang" not in exam and "tid_minuter" not in exam
    tillatna = set(exam_spec.ExamDoc.model_fields) | {"del"}
    assert set(exam) <= tillatna, sorted(set(exam) - tillatna)
    assert all("del" in u and "poang" in u for u in exam["uppgifter"])


def test_anteckningarna_ur_kassetten_haller_stilkontraktet(fejk_claude):
    """Femte dokumenttypen, skarpt inspelad: en riktig modell fick lärarens
    ruta OCH ett mötestranskript och skrev pappret ur båda.

    Det som prövas är att stilkontraktet HÖLL i en riktig körning — inga
    tankstreck, rubriker som är vägvisare, en sida — utan att en enda
    reparationsrunda behövdes. Faller det här har antingen prompten glidit
    eller taken skruvats, och båda ska märkas här och inte hos läraren."""
    from app import notes_gen
    fejk_claude(kassett="anteckningar")
    res = notes_gen.generate_notes(
        "Matematik 3c", "NA25", "Första lektionen", model="",
        onskemal="Boken, hur vi räknar, provdatumen och räknaren")
    assert res["errors"] == [], res["errors"]
    assert res["rounds"] == 1, "det skarpa svaret behövde en reparationsrunda"
    doc, _fel = notes_gen.validate_notes_json(res["notes"])
    assert doc is not None
    # Innehållet kom ur MÖTET, inte ur luften: bokens namn, provveckorna och
    # räknaren stod i transkriptet och ska ha tagit sig hela vägen till pappret.
    text = json.dumps(res["notes"], ensure_ascii=False)
    for ur_motet in ("5000+", "42", "räknare"):
        assert ur_motet in text, ur_motet
    assert notes_gen.rader(doc) <= notes_gen.RADER_PA_SIDAN


@pytest.mark.parametrize("dokument,domarband", [
    ("prov", "nivadomare"),
    ("arbetsblad", "nivadomare-blad"),
    ("gruppuppgift", "nivadomare-grupp"),
])
def test_nivadomen_ur_kassetten_gar_hela_vagen(fejk_claude, dokument, domarband):
    """Domarbanden genom hela kedjan: CLI → ström → JSON → nivåjämförelse.

    Ett band per dokumenttyp, alla tre SKARPA. Domaren fick uppgifterna utan
    poäng och utan bedömningsanvisningar, och det som prövas här är att domen
    kommer hela vägen tillbaka och går att para ihop med rätt uppgift — inte
    att den håller med.

    Fällningarna räknas om vid varje omspelning. Efter Del F:s våg
    (2026-08-09) fäller den EN av tjugoen enheter — gruppuppgiftens hitta-felet-
    deluppgift, som är poängsatt C och bedöms som E — mot två av tjugosex före
    vågen. Ingen «oklart» i något band, precis som förut: toleransen bärs av
    tystnad, inte av att domaren hedgar (planens C7, punkt 4)."""
    fejk_claude(kassett=domarband)
    exam = exam_gen._parse_exam(json.loads(
        fejk.las_kassett(dokument)["rader"][-1])["result"])
    enheter = exam_gen.domarenheter(exam)
    domar = exam_gen._parse_domar(json.loads(
        fejk.las_kassett(domarband)["rader"][-1])["result"])
    # Varje poängbärande enhet ska ha fått en dom. Tystnad tolkas aldrig som
    # medhåll, så en domare som hoppar över halva provet «godkänner» det —
    # och det är just den tystnaden som inte får smyga sig in.
    assert {e["nr"] for e in enheter} <= set(domar), \
        f"{domarband}: domaren hoppade över uppgifter"
    assert all(d["niva"] in ("E", "C", "A", "OKLART") for d in domar.values())
    # Uppspelningen genom appens egen söm ger samma svar som filen.
    avv = exam_gen.doma_nivaer(exam, model="")
    vantat = exam_gen.avvikelser(enheter, domar)
    assert [a["path"] for a in avv] == [a["path"] for a in vantat]
    for a in avv:                      # en avvikelse ska säga vad som ska GÖRAS
        assert "höj svårigheten" in a["message"] or "sänk svårigheten" in a["message"]


def test_insikterna_ur_den_skarpa_kassetten_bar_inga_namn(fejk_claude):
    """Den riktiga körningen FÖLJDE integritetsregeln — inga fullständiga
    namn kom tillbaka. Det testet vaktar är att det förblir så."""
    fejk_claude(kassett="insikter")
    insikter, innehall = postprocess._extract_one("transkript", "modell")
    assert insikter and innehall
    texter = " ".join(i["text"] + " " + (i["ref"] or "") for i in insikter)
    assert postprocess.initialisera(texter) == texter, \
        "ett fullständigt namn kom tillbaka ur den skarpa inspelningen"
    assert any(i["typ"] == "kalender" for i in insikter)


def test_ett_namn_som_anda_kommer_tillbaka_stoppas(fejk_claude):
    """…och när den INTE följer regeln — det bandet är konstruerat, för det
    ska inte behöva hända på riktigt för att spärren ska vara prövad."""
    fejk_claude(kassett="insikter-med-namn")
    insikter, _ = postprocess._extract_one("transkript", "modell")
    texter = " ".join(i["text"] + " " + (i["ref"] or "") for i in insikter)
    assert "Lindqvist" not in texter and "Svensson" not in texter
    assert "A.L." in texter and "E.S." in texter


def test_auto_laget_lagger_i_bandet_prompten_ber_om(fejk_claude):
    """Auto-läget (Etapp 4) läser vad prompten BER om och väljer band därefter.

    Det är e2e-serverns läge: den lever i en egen process och kan inte byta
    fixtur mellan två klick, men en lärardag skriver tavla, prov, arbetsblad,
    gruppuppgift OCH granskning i samma körning. Valet sker därför i CLI:t, på
    generatorernas egna uppdragsrader — och glider de isär från nyckelorden
    faller det här testet i stället för att en lärardag tyst får fel papper."""
    fejk_claude("auto")
    tavla = lesson_board.generate_board("Matematik, nivå 2c", "NA25",
                                        "Derivator", model="")
    assert tavla["errors"] == [] and tavla["rounds"] == 1
    assert tavla["board"]["title"]

    for profil, antal, grupp in [
            ("prov", 6, None), ("arbetsblad", 6, None),
            ("gruppuppgift", 4, {"elever": 3, "langd_min": 45,
                                 "redovisning": "muntligt"})]:
        res = exam_gen.generate_exam("Matematik, nivå 2c", "NA25",
                                     ["Andragradsekvationer"], model="",
                                     antal=antal, profil=profil, grupp=grupp)
        # Vad som får stå kvar och vad som inte får det.
        #
        # Uppspelningen svarar med SAMMA band varje gång, så en reparation ger
        # tillbaka exakt det dokument som skulle lagas. Balans- och nivåfynd kan
        # därför aldrig repareras bort här — de överlever alla rundor, och det
        # är uppspelningens natur och inte ett fel i kedjan. Så var de blir
        # varningar läraren ser, och det är rätt.
        #
        # Schema- och JSON-fel är något helt annat: de betyder att modellen
        # skrev en form appen inte kan ta emot, och att prompten alltså inte
        # räcker. Två sådana hittades av just den här inspelningen —
        # elevlosningar och innehall inne i en deluppgift — och fixades i
        # INSTRUCTION. Det är den bevakningen som ska stå kvar.
        brott = [e for e in res["errors"] if e["code"] in ("schema", "json")]
        assert brott == [], (profil, brott)
        assert res["exam"]["titel"], profil
        # RÄTT BAND, inte bara ETT band: profilerna har olika balansregler och
        # provets kassett faller igenom arbetsbladets.
        #
        # Kännetecknet var förut titeln («prov» i provets, «arbetsblad» i
        # arbetsbladets). Den bär det inte längre: provets titel ska vara
        # momentets namn KORT och utan ordet «Prov» — mallen sätter själv «Prov
        # <titel> – <kurs>» (exam_gen.INSTRUCTION, exam_latex._provrubrik). Ett
        # test som håller fast vid den gamla titeln hade tvingat tillbaka den
        # långa formen. Formen skiljer banden lika säkert: bara provet har
        # delar, bara gruppuppgiften har `grupp`.
        uppg = res["exam"]["uppgifter"]
        if profil == "prov":
            assert all(u.get("del") for u in uppg), "provbandet saknar delar"
        else:
            assert not any(u.get("del") for u in uppg), profil
            assert (res["exam"].get("grupp") is not None) == \
                (profil == "gruppuppgift"), profil

    # Anteckningarna hör till lärardagen de också — och deras prompt bär ett
    # helt mötestranskript, alltså den text som mest sannolikt råkar innehålla
    # ett annat bands nyckelord. Går valet fel här får läraren ett prov när hon
    # bad om ett stödpapper.
    from app import notes_gen
    ant = notes_gen.generate_notes(
        "Matematik, nivå 2c", "NA25", "Första lektionen", model="",
        onskemal="Boken, rutinerna och provdatumen",
        transkript=notes_gen.build_transkript(
            [("Kursstartsmöte", "vi kopierar upp ett arbetsblad till fredag "
                                "och tar matteprovet i vecka 42")]))
    assert ant["errors"] == [], ant["errors"]
    assert ant["notes"]["sektioner"], "anteckningarna hamnade i fel band"

    insikter, innehall = postprocess._extract_one("transkript", "modell")
    assert insikter and innehall

    # Det som inte är en generator (chatt, sökning) svarar som vanligt.
    assert claude_code.generate("Vad heter huvudstaden?") == "Det här är svaret."


def test_en_kassett_som_inte_finns_ar_ett_tydligt_fel(fejk_claude):
    fejk_claude(kassett="finns-inte")
    with pytest.raises(RuntimeError):
        claude_code.generate("x")
