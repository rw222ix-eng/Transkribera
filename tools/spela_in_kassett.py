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

from app import claude_code, exam_gen, lesson_board, postprocess   # noqa: E402
from tests import fejk                                             # noqa: E402

TRANSKRIPT = (
    "Idag tittade vi på derivatans definition. Vi började med ändringskvoten "
    "och lät h gå mot noll. Många fastnade på kedjeregeln från förra veckan, "
    "så vi tar om den på fredag. Kom ihåg att provet är den 12 maj, och jag "
    "ska kopiera upp arbetsbladet till nästa gång."
)

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
            antal=6, tid_min=90),
        "system": lambda: exam_gen.SYSTEM,
        "schema": lambda: None,
    },
    "insikter": {
        "vad": "postprocess.extract — insikter ur ett lektionstranskript",
        "prompt": lambda: postprocess.build_extract_prompt(TRANSKRIPT),
        "system": lambda: postprocess.EXTRACT_SYSTEM,
        "schema": lambda: postprocess.EXTRACT_SCHEMA,
    },
}


def spela_in(namn: str) -> Path:
    s = SCENARIER[namn]
    exe = claude_code.binar()
    if not exe:
        raise SystemExit("claude hittades inte — installera Claude Code först.")
    argv = claude_code._argv(exe, system=s["system"](), schema=s["schema"](),
                             modell="", verktyg="", extra_dirs=[])
    print(f"Spelar in «{namn}» … (riktigt anrop, kostar några ören)")
    proc = subprocess.run(argv, input=s["prompt"](), capture_output=True,
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
