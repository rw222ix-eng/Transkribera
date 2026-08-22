"""Spela in ett riktigt Claude Code-svar som kassett (Etapp 3).

En kassett är ETT svar, sparat rad för rad som CLI:t skrev det. Spelas den upp
i testsviten körs allt EFTER svaret på riktigt — strömtolkningen, JSON-parsningen,
schemat, balansreglerna och reparationsrundorna. Det är den delen av kedjan som
en vanlig stubb hoppar över, och den som brukar gå sönder.

Banden i tests/kassetter/ är från början KONSTRUERADE ur appens egna exempel
(`inspelad: false`): rätt form, men ingen modell har skrivit dem. Kör det här
skriptet en gång för att byta ut dem mot riktiga svar:

    python -m tools.spela_in_kassett            # alla scenarier
    python -m tools.spela_in_kassett tavla      # ett

Det KRÄVER lärarens egen inloggning (`claude login`) och kostar några ören per
scenario — därför körs det aldrig av sviten, bara för hand. Prompterna byggs av
appens egna promptfunktioner, så en kassett speglar exakt det appen frågar om.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROT))

from app import (claude_code, exam_gen, exam_spec, lesson_board,   # noqa: E402
                 llm_client, notes_gen, postprocess)
from tests import fejk                                             # noqa: E402

TRANSKRIPT = (
    "Idag tittade vi på derivatans definition. Vi började med ändringskvoten "
    "och lät h gå mot noll. Många fastnade på kedjeregeln från förra veckan, "
    "så vi tar om den på fredag. Kom ihåg att provet är den 12 maj, och jag "
    "ska kopiera upp arbetsbladet till nästa gång."
)

# Anteckningarnas underlag är ett MÖTE, inte en lektion — det är därför typen
# finns. Talspråket, avbrotten och det som beslutas i förbifarten hör till:
# ett städat referat hade gjort inspelningen lättare än verkligheten, och det
# är just röran modellen ska klara att plocka ur.
MOTESTRANSKRIPT = (
    "Okej, då kör vi. Först boken. Vi landade i att alla treor kör Matematik "
    "5000+ 3c, samma som förra året, och de får den utdelad på första "
    "lektionen. Säg åt dem att skriva bokens nummer på insidan, annars blir "
    "det rörigt vid inlämningen i juni. Sen provdatumen. Första provet ligger "
    "i vecka 42, det andra i vecka 48, och nationella provet i maj men "
    "datumet är inte spikat än. Ja, och en sak till, vi bestämde i lagen att "
    "de ska ha med egen räknare från och med andra veckan. Skolan har några "
    "att låna ut men inte till alla. Räknaren behövs alltså inte första "
    "veckan. Hur gör vi med dem som inte har? De får låna, men bara under "
    "lektionen. Och läxhjälpen är tisdagar klockan tre i sal 214, samma som i "
    "våras. Sista punkten: mobilerna ligger i lådan vid dörren. Ta det på "
    "första lektionen så slipper ni diskussionen resten av terminen."
)

# Provets skelett räknas EN gång och delas av prompten och grammatiken. Två
# anrop till balanced_skeleton ger visserligen samma svar (den är
# deterministisk), men planen i prompten och const-låsningen i schemat MÅSTE
# vara samma rader — annars ber bandet om en uppgift och tvingar en annan.
_PROVSKELETT = exam_spec.balanced_skeleton(6, "prov")

SCENARIER = {
    "tavla": {
        "vad": "lesson_board.generate_board — en lektionstavla i wb-json-v1",
        "prompt": lambda: lesson_board.build_prompt(
            "Matematik 3c", "NA25", "Derivatans definition"),
        "system": lambda: lesson_board.SYSTEM,
        "schema": lambda: None,
    },
    "prov": {
        "vad": "exam_gen.generate_exam — ett prov med balanserat skelett",
        "prompt": lambda: exam_gen.build_prompt(
            "Matematik 3c", "NA25", ["Derivata", "Gränsvärden"],
            antal=6, tid_min=90, skeleton=_PROVSKELETT),
        "system": lambda: exam_gen.SYSTEM,
        # GRAMMATIKEN MED. Bandet spelades förut in utan schema, och då mätte
        # det bara om modellen följde prompten. Provets form bärs numera lika
        # mycket av grammatiken — deluppgifternas antal och poäng är const-låsta
        # (exam_spec.to_response_format) — så ett band utan schema är ett band
        # av något annat än det appen gör.
        "schema": lambda: exam_spec.to_response_format(skeleton=_PROVSKELETT),
    },
    # Arbetsbladet och gruppuppgiften. Parametrarna speglar de konstruerade
    # band de ersätter (Matematik nivå 2c, NA25, sex respektive fyra uppgifter)
    # — annars byter kassetten form samtidigt som den byter innehåll, och de
    # test som läser den mäter två ändringar på en gång.
    #
    # `profil` är det som avgör: fejk-CLI:ts auto-läge väljer band på fraserna
    # «skriv ett ARBETSBLAD» och «skriv en GRUPPUPPGIFT», som build_prompt
    # skriver först när profilen är satt (tests/fejk.py _VAL).
    "arbetsblad": {
        "vad": "exam_gen.generate_exam (profil arbetsblad) — ett arbetsblad med facit",
        "prompt": lambda: exam_gen.build_prompt(
            "Matematik, nivå 2c", "NA25", ["Andragradsekvationer"],
            antal=6, tid_min=60, delar=False, profil="arbetsblad"),
        "system": lambda: exam_gen.SYSTEM,
        "schema": lambda: None,
    },
    "gruppuppgift": {
        # «Fyra ingångar» stod här förut. Lärarens skarpa lektion (Del F, dom 1)
        # gjorde gruppuppgiften till en stegring i stället.
        "vad": ("exam_gen.generate_exam (profil gruppuppgift) — en stegring "
                "och ett upplägg"),
        "prompt": lambda: exam_gen.build_prompt(
            "Matematik, nivå 2c", "NA25", ["Andragradsfunktioner"],
            antal=4, tid_min=45, delar=False, profil="gruppuppgift",
            grupp={"elever": 3, "langd_min": 45, "redovisning": "muntligt"}),
        "system": lambda: exam_gen.SYSTEM,
        "schema": lambda: None,
    },
    # Anteckningarna (femte dokumenttypen). Scenariot är typfallet ur planen:
    # kursens första lektion, innehållet är information och underlaget ett
    # transkriberat möte. Båda källorna är med — lärarens ruta OCH mötet — för
    # det är den kombinationen som avgör om prompten rangordnar dem rätt.
    "anteckningar": {
        "vad": ("notes_gen.generate_notes — lärarens stödpapper till en första "
                "lektion, byggt på ett möte"),
        "prompt": lambda: notes_gen.build_prompt(
            "Matematik 3c", "NA25", "Första lektionen",
            onskemal=("Vilken bok vi har och att de får den idag. Hur vi "
                      "räknar på lektionerna. Provdatumen i höst. Att de ska "
                      "ta med räknare på fredag."),
            transkript=notes_gen.build_transkript([
                ("Ämneslagets kursstartsmöte · 2026-08-12", MOTESTRANSKRIPT)]),
            datum="2026-08-18"),
        "system": lambda: notes_gen.SYSTEM,
        "schema": lambda: None,
    },
    "insikter": {
        "vad": "postprocess.extract — insikter ur ett lektionstranskript",
        "prompt": lambda: postprocess.build_extract_prompt(TRANSKRIPT),
        "system": lambda: postprocess.EXTRACT_SYSTEM,
        "schema": lambda: postprocess.EXTRACT_SCHEMA,
    },
    # Nivådomaren (Del C) bedöms mot ett FÄRDIGT dokument, inte mot en tom
    # sida. Därför läses respektive band in och döms — samma dokument som
    # resten av sviten arbetar med, så en avvikelse i domen går att slå upp i
    # uppgifterna.
    #
    # ETT band per dokumenttyp, och det är inte överdrift: uppspelningen har en
    # fil per scenario, och uppgiftsnumren betyder olika saker i olika band
    # (uppgift 2a är C i gruppuppgiften och E i provet). Med ett gemensamt band
    # dömer provets dom gruppuppgiftens uppgifter, och fällningen säger då mer
    # om kassetten än om dokumentet. Domarna skiljs åt på skalan de fick — se
    # _DOMAR_VAL i tests/fejk.py.
    "nivadomare": {
        "vad": "exam_gen.doma_nivaer — blind nivåbedömning av provbandet",
        "prompt": lambda: _domarprompt("prov"),
        "system": lambda: exam_gen.DOMAR_SYSTEM,
        "schema": lambda: exam_gen.DOMAR_SCHEMA,
    },
    "nivadomare-blad": {
        "vad": "exam_gen.doma_nivaer — blind nivåbedömning av arbetsbladsbandet",
        "prompt": lambda: _domarprompt("arbetsblad"),
        "system": lambda: exam_gen.DOMAR_SYSTEM,
        "schema": lambda: exam_gen.DOMAR_SCHEMA,
    },
    "nivadomare-grupp": {
        "vad": "exam_gen.doma_nivaer — blind nivåbedömning av gruppuppgiftsbandet",
        "prompt": lambda: _domarprompt("gruppuppgift"),
        "system": lambda: exam_gen.DOMAR_SYSTEM,
        "schema": lambda: exam_gen.DOMAR_SCHEMA,
    },
}

# Vilket band varje domare läser, och hur många uppgifter dokumentet har. Det
# senare bara för att provets skelett ska bli detsamma som när bandet spelades
# in: skalan i domarprompten måste vara den dokumentet faktiskt skrevs mot.
_DOMARENS_BAND = {"prov": ("prov", 6), "arbetsblad": ("arbetsblad", 6),
                  "gruppuppgift": ("gruppuppgift", 4)}


def _bandets_dokument(namn: str) -> dict:
    """Dokumentet ur ett band — result-raden är hela svaret."""
    band = fejk.las_kassett(namn)
    return exam_gen._parse_exam(json.loads(band["rader"][-1])["result"])


def _domarprompt(profil: str) -> str:
    bandnamn, antal = _DOMARENS_BAND[profil]
    # Provets skala måste vara SAMMA rader som bandet skrevs mot — därför
    # _PROVSKELETT och inte ett nytt anrop med samma argument.
    skelett = _PROVSKELETT if profil == "prov" else None
    return exam_gen.build_domar_prompt(
        exam_gen.domarenheter(_bandets_dokument(bandnamn)),
        skala=exam_gen._skala(profil, "", skelett))


def spela_in(namn: str) -> Path:
    s = SCENARIER[namn]
    exe = claude_code.binar()
    if not exe:
        raise SystemExit("claude hittades inte — installera Claude Code först.")
    prompt = s["prompt"]()
    schema = s["schema"]()
    # Scenarier som lämnar ett helt response_format-objekt (provet) packas upp
    # som llm_client gör: CLI:n vill ha själva schemat, inte omslaget.
    if isinstance(schema, dict) and "json_schema" in schema:
        schema = llm_client._schema_ur(schema)
    # SAMMA FÖRBEHANDLING SOM APPEN. claude_code.generate lägger tillbaka
    # schemats beskrivningar i prompten och minifierar schemat innan det går på
    # kommandoraden; ett band inspelat utan de två stegen är inspelat mot en
    # annan fråga än den appen ställer.
    if schema is not None:
        prompt += claude_code._formatsammanfattning(schema)
        schema = claude_code._minifiera(schema)
    argv = claude_code._argv(exe, system=s["system"](), schema=schema,
                             modell="", verktyg="", extra_dirs=[])
    print(f"Spelar in «{namn}» … (riktigt anrop, kostar några ören)")
    proc = subprocess.run(argv, input=prompt, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          cwd=claude_code._neutral_cwd())
    rader = [r for r in (proc.stdout or "").splitlines() if r.strip()]
    if not rader:
        raise SystemExit(f"inget svar: {(proc.stderr or '')[:400]}")
    fil = fejk.skriv_kassett(
        namn, vad=s["vad"], svar="", inspelad=True, rader=rader,
        extra={"inspelad_datum": date.today().isoformat()})
    print(f"KLART: {fil} ({len(rader)} rader)")
    return fil


def main() -> int:
    namn = sys.argv[1:] or list(SCENARIER)
    for n in namn:
        if n not in SCENARIER:
            print(f"okänt scenario: {n} (finns: {', '.join(SCENARIER)})",
                  file=sys.stderr)
            return 1
        spela_in(n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
