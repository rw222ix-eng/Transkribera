"""Mäter Qwen-korrekturläsningens roll: försiktig städning vs kontextreparation.

Kör två promptvarianter på pass 1-transkripten från referensklippen (facit
finns) och jämför WER mot facit:

  A  dagens app-prompt (postprocess "cleanup": rätta stavfel/interpunktion,
     skriv inte om i onödan)
  B  kontextreparation: får ersätta felhörda/osannolika ord och meningar med
     det mest sannolika utifrån sammanhanget före och efter

Körs på originalklippen (avslöjar om B förstör redan korrekt text) och på de
degraderade nivåerna (latt/medel/svar) där riktiga hörfel finns.

    python tests/qwen_korrektur_bench.py kor <katalog> [fler ...]   # .qwenA/.qwenB.txt
    python tests/qwen_korrektur_bench.py rapport <katalog>

Startar en egen llama-server (Qwen3-14B) — kör inte samtidigt som appen/Gemma.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MODELS = Path(__file__).resolve().parent.parent / "models"

PROMPT_B = (
    "Du får ett rått transkript från taligenkänning av svenskt tal. Enstaka ord "
    "eller meningar kan vara felhörda och blir då osannolika i sitt sammanhang. "
    "Rätta felhörda ord och meningar så att texten blir det mest sannolika som "
    "faktiskt sades, med hjälp av sammanhanget både före och efter varje mening. "
    "Behåll ordföljd, stil och talspråk där de redan är rimliga. Lägg inte till "
    "ny information, ta inte bort innehåll och sammanfatta inte. "
    "Svara med ENBART den rättade texten, på svenska:"
)


def steg_kor(kataloger: list[Path]) -> None:
    from app import llama_server, llm_client, llm_manager, postprocess

    spec = llm_manager.ACTIVE_LLM
    port = llama_server.find_free_port()
    srv = llama_server.LlamaServer(
        llm_manager.model_path_for(spec, MODELS), port=port)
    print("startar llama-server (Qwen3-14B) ...", flush=True)
    srv.start()
    llm_client.BASE_URL = srv.base_url
    try:
        for klipp_dir in kataloger:
            t0 = time.time()
            for txt_fil in sorted(klipp_dir.glob("*.txt")):
                if txt_fil.name.endswith((".korr.txt", ".qwenA.txt", ".qwenB.txt")):
                    continue
                pass1 = txt_fil.read_text(encoding="utf-8").strip()
                # A: appens riktiga kodväg (postprocess cleanup, inkl. map-reduce)
                a = postprocess.run("cleanup", pass1, spec.filename)
                # B: kontextreparation — samma system-prompt och temperatur som appen
                b = llm_client.generate(
                    spec.filename, f"{PROMPT_B}\n\n{pass1}",
                    system=postprocess.SYSTEM_SV,
                    options={"temperature": 0.2})
                txt_fil.with_name(txt_fil.stem + ".qwenA.txt").write_text(
                    a.strip() + "\n", encoding="utf-8")
                txt_fil.with_name(txt_fil.stem + ".qwenB.txt").write_text(
                    b.strip() + "\n", encoding="utf-8")
            print(f"{klipp_dir.name}: klart på {time.time() - t0:.0f}s", flush=True)
    finally:
        srv.stop()


def steg_rapport(klipp_dir: Path) -> None:
    from tests.wer_eval import normalisera, wer

    referenser = json.loads((klipp_dir / "referens.json").read_text(encoding="utf-8"))
    tot = {"ord": 0, "p1": 0, "a": 0, "b": 0}
    print("| fil | pass 1 | Qwen A (städa) | Qwen B (kontext) |")
    print("|---|---|---|---|")
    for post in sorted(referenser, key=lambda p: p["file"]):
        stam = klipp_dir / Path(post["file"]).stem
        h1 = Path(f"{stam}.txt").read_text(encoding="utf-8")
        ha = Path(f"{stam}.qwenA.txt").read_text(encoding="utf-8")
        hb = Path(f"{stam}.qwenB.txt").read_text(encoding="utf-8")
        w1, wa, wb = (wer(post["text"], h) for h in (h1, ha, hb))
        n = len(normalisera(post["text"]).split())
        tot["ord"] += n
        tot["p1"] += round(w1 * n)
        tot["a"] += round(wa * n)
        tot["b"] += round(wb * n)
        print(f"| {post['file']} | {100 * w1:.1f} % | {100 * wa:.1f} % | {100 * wb:.1f} % |")
    o = tot["ord"]
    print(f"\n**Totalt: pass 1 {100 * tot['p1'] / o:.1f} %  |  "
          f"Qwen A {100 * tot['a'] / o:.1f} %  |  Qwen B {100 * tot['b'] / o:.1f} %**  "
          f"({o} ord)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    steg = sys.argv[1]
    if steg == "kor":
        steg_kor([Path(p).resolve() for p in sys.argv[2:]])
    elif steg == "rapport":
        steg_rapport(Path(sys.argv[2]).resolve())
    else:
        print(__doc__)
        raise SystemExit(1)
