"""Whiteboard-bench (Fas 2): mäter att Qwen3-14B följer WB-JSON v1-mallen.

Manuell körning med GPU — ingår INTE i pytest (mönster: qwen_korrektur_bench).
Startar en egen llama-server (Qwen3-14B-Q8) — kör inte samtidigt som appen.

    python tests/bench_whiteboard.py kor [N]     # kör benchen (N första uppdragen)
    python tests/bench_whiteboard.py rapport     # markdown-rapport av senaste körningen

Per uppdrag mäts (planens Fas 2-krav):
  * schema-giltig JSON på försök 1 (grammatiktvånget är alltid på)
  * antal regelvalideringsfel på försök 1
  * antal [WB]-renderingsvarningar före/efter reparationsloopen
  * antal LLM-rundor totalt (generering + reparation, delad budget max 3)
  * tid

Rendering sker headless via spec-runnern e2e/render-board.mjs (Playwright) —
samma motor och warn-hook som appen. Resultat + skärmdumpar läggs i
tests/bench_out/whiteboard/ (gitignorerat, återupptagbar körning: uppdrag
med färdig .json hoppas över). Målnivå innan Fas 1 släpps på:
≥ 95 % schema-giltigt försök 1 · 100 % giltig JSON · 0 [WB]-varningar
efter ≤ 3 rundor.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO = Path(__file__).resolve().parent.parent
MODELS = REPO / "models"
OUT_DIR = REPO / "tests" / "bench_out" / "whiteboard"
RUNNER = REPO / "e2e" / "render-board.mjs"

# ~20 uppdrag över algebra, geometri, trigonometri, funktioner och
# statistik/regression (planens Fas 2-spridning).
UPPDRAG: list[tuple[str, str, str]] = [
    # algebra
    ("Ma1b", "EK24A", "Lösa linjära ekvationer med balansmetoden"),
    ("Ma1c", "NA24B", "Förenkla uttryck med parenteser — distributiva lagen"),
    ("Ma2b", "SA23", "Andragradsekvationer med pq-formeln"),
    ("Ma2c", "NA23", "Kvadreringsreglerna och konjugatregeln"),
    # geometri
    ("Ma1b", "BA24", "Pythagoras sats — tillämpningar"),
    ("Ma2c", "NA23", "Likformighet och topptriangelsatsen"),
    ("Ma1c", "TE24", "Vinkelsumman i månghörningar"),
    ("Ma2b", "EK23", "Cirkelns omkrets och area samt cirkelsektor"),
    # trigonometri
    ("Ma3c", "NA22", "Enhetscirkeln och sinus/cosinus för standardvinklar"),
    ("Ma4", "TE22", "Areasatsen och sinussatsen"),
    ("Ma3c", "NA22", "Grafen till sin x och cos x — amplitud och period"),
    ("Ma4", "NA21", "Trigonometriska ettan och enkla identiteter"),
    # funktioner
    ("Ma2b", "SA24", "Räta linjens ekvation y = kx + m"),
    ("Ma3b", "EK22", "Derivatans definition och tangentens lutning"),
    ("Ma3c", "NA22", "Extrempunkter med derivata och teckentabell"),
    ("Ma1b", "HA24", "Exponentiell förändring och förändringsfaktor"),
    # statistik/regression
    ("Ma2b", "SA23", "Lägesmått och spridningsmått"),
    ("Ma2b", "EK24", "Normalfördelningen och tumregeln"),
    ("Ma2c", "NA24", "Linjär regression och korrelation"),
    ("Ma1b", "EK24A", "Sannolikhet med träddiagram"),
]


def _slug(moment: str) -> str:
    s = moment.lower()
    for a, b in (("å", "a"), ("ä", "a"), ("ö", "o"), ("é", "e")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60]


def _node() -> str:
    return shutil.which("node") or "node"


def render_warnings(board_doc: dict, screenshot: Path | None) -> list[str]:
    """Rendera via spec-runnern; returnerar motorns [WB]-varningar."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    spec_file = OUT_DIR / "_tmp_spec.json"
    spec_file.write_text(json.dumps(board_doc, ensure_ascii=False),
                         encoding="utf-8")
    cmd = [_node(), str(RUNNER), str(spec_file)]
    if screenshot is not None:
        cmd += ["--screenshot", str(screenshot)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                          cwd=str(REPO / "e2e"), encoding="utf-8")
    if proc.returncode != 0:
        return [f"[runner-fel] {proc.stderr.strip()[:300]}"]
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])["warnings"]
    except Exception:
        return [f"[runner-fel] oläsbar utdata: {proc.stdout[:200]}"]


def kor(n: int | None = None) -> None:
    from app import lesson_board, llama_server, llm_client, llm_manager
    from app import whiteboard_spec as ws

    uppdrag = UPPDRAG[: n or len(UPPDRAG)]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    spec = llm_manager.ACTIVE_LLM
    port = llama_server.find_free_port()
    srv = llama_server.LlamaServer(llm_manager.model_path_for(spec, MODELS),
                                   port=port)
    print("startar llama-server (Qwen3-14B) ...", flush=True)
    srv.start()
    llm_client.BASE_URL = srv.base_url
    try:
        for kurs, klass, moment in uppdrag:
            slug = _slug(moment)
            res_file = OUT_DIR / f"{slug}.json"
            if res_file.exists():
                print(f"{slug}: redan klar — hoppar över", flush=True)
                continue
            print(f"\n=== {kurs} {klass} — {moment}", flush=True)

            raws: list[str] = []

            def rec_llm(model, prompt, **kw):
                raw = llm_client.generate(model, prompt, **kw)
                raws.append(raw)
                return raw

            t0 = time.time()
            try:
                gen = lesson_board.generate_board(
                    kurs, klass, moment, model=spec.filename, llm=rec_llm,
                    log_cb=lambda m: print("  " + m, flush=True))
            except Exception as e:
                print(f"  FEL under generering: {e} — hoppar över", flush=True)
                res_file.write_text(json.dumps({
                    "kurs": kurs, "klass": klass, "moment": moment,
                    "krasch": str(e)}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
                continue

            # Försök 1-mätning: validera modellens FÖRSTA råa svar separat.
            first = lesson_board._parse_board(raws[0]) if raws else None
            if first is None:
                schema_f1, regelfel_f1 = False, None
            else:
                doc1, errors1 = ws.validate_board_json(first)
                schema_f1 = doc1 is not None
                regelfel_f1 = len([e for e in errors1 if e["code"] != "schema"]) \
                    if doc1 is not None else None

            board = gen["board"]
            rounds = gen["rounds"]
            wb_fore: list[str] = []
            wb_efter: list[str] = []
            if board is not None:
                wb_fore = render_warnings(board, OUT_DIR / f"{slug}-fore.png")
                wb_efter = list(wb_fore)
                # Renderingsreparation — samma loop som appen kör via
                # render-report (delad rundbudget, max 3 totalt).
                while wb_efter and rounds < lesson_board.MAX_ROUNDS:
                    rep = lesson_board.repair_board(
                        board, wb_efter, model=spec.filename, llm=rec_llm,
                        rounds_used=rounds,
                        log_cb=lambda m: print("  " + m, flush=True))
                    board = rep["board"] or board
                    rounds = rep["rounds"]
                    wb_efter = render_warnings(
                        board, OUT_DIR / f"{slug}-efter.png")

            resultat = {
                "kurs": kurs, "klass": klass, "moment": moment,
                "schema_forsok1": schema_f1,
                "regelfel_forsok1": regelfel_f1,
                "giltig_json_forsok1": first is not None,
                "gen_rundor": gen["rounds"],
                "kvarvarande_valfel": gen["errors"],
                "wb_fore": wb_fore,
                "wb_efter": wb_efter,
                "rundor_totalt": rounds,
                "tid_s": round(time.time() - t0, 1),
            }
            res_file.write_text(json.dumps(resultat, ensure_ascii=False,
                                           indent=2), encoding="utf-8")
            (OUT_DIR / f"{slug}-board.json").write_text(
                json.dumps(board, ensure_ascii=False, indent=2),
                encoding="utf-8")
            print(f"  klart: schema1={schema_f1} regelfel1={regelfel_f1} "
                  f"wb {len(wb_fore)}->{len(wb_efter)} rundor={rounds} "
                  f"({resultat['tid_s']}s)", flush=True)
    finally:
        srv.stop()


def rapport() -> None:
    rows = []
    for f in sorted(OUT_DIR.glob("*.json")):
        if f.name.startswith("_tmp") or f.name.endswith("-board.json"):
            continue
        rows.append(json.loads(f.read_text(encoding="utf-8")))
    krascher = [r for r in rows if "krasch" in r]
    rows = [r for r in rows if "krasch" not in r]
    if not rows:
        print("inga resultat i", OUT_DIR)
        return

    n = len(rows)
    schema1 = sum(1 for r in rows if r["schema_forsok1"])
    json1 = sum(1 for r in rows if r["giltig_json_forsok1"])
    rena = sum(1 for r in rows if not r["wb_efter"] and not r["kvarvarande_valfel"])
    overlapp_efter = sum(1 for r in rows
                         if any("överlapp" in w for w in r["wb_efter"]))

    print("| uppdrag | schema F1 | regelfel F1 | WB före → efter | rundor | tid |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['kurs']} — {r['moment'][:44]} "
              f"| {'ja' if r['schema_forsok1'] else 'NEJ'} "
              f"| {r['regelfel_forsok1'] if r['regelfel_forsok1'] is not None else '—'} "
              f"| {len(r['wb_fore'])} → {len(r['wb_efter'])} "
              f"| {r['rundor_totalt']} | {r['tid_s']}s |")
    print()
    print(f"**Totalt ({n} uppdrag):**")
    print(f"- giltig JSON försök 1: {json1}/{n} ({100 * json1 / n:.0f} %) — mål 100 %")
    print(f"- schema-giltigt försök 1: {schema1}/{n} ({100 * schema1 / n:.0f} %) — mål ≥ 95 %")
    print(f"- helt rena efter ≤ 3 rundor (0 WB-varningar, 0 valideringsfel): "
          f"{rena}/{n} ({100 * rena / n:.0f} %)")
    print(f"- uppdrag med kvarvarande överlappsvarningar: {overlapp_efter} — mål 0")
    if krascher:
        print(f"- KRASCHER: {len(krascher)}")


if __name__ == "__main__":
    # Windows-konsolen är cp1252 — rapporten innehåller → m.m.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    if sys.argv[1] == "kor":
        kor(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif sys.argv[1] == "rapport":
        rapport()
    else:
        print(__doc__)
        raise SystemExit(1)
