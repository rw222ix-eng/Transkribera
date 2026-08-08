"""Volym: hur appen känns i maj, inte i augusti.

Soaken (tools/soak.py) kör matrisen varv efter varv och letar LÄCKOR — sådant
som växer utan att någon lagt något nytt i huset. Det här verktyget frågar
tvärtom: när huset ÄR fullt, hur lång tid tar det att öppna dörren?

Skillnaden spelar roll. Soaken hinner ett par hundra varv på en natt och lämnar
en bas med tusen papper — men den mäter aldrig svarstiden på en enskild rutt,
och den kommer aldrig upp i ett läsårs LEKTIONER (700 transkript à 60 KB). Sviten
gör det ännu mindre: varje körning startar mot ett tomt hus.

Så här fylls huset (ett läsår, `--ar` multiplicerar):

* **700 lektioner** — fyra om dagen i 180 skoldagar, var och en med ett äkta
  transkript på ~60 KB och tre insikter. `lessons.transcript_text` är den enda
  riktigt stora kolumnen i basen, och FTS5-indexet lägger nästan lika mycket till.
* **400 papper med fyra versioner var** — `/api/dokument` hämtar ALLA papper med
  ALLA sina versioner i ETT svar, plus en fråga per papper (db.list_dokument →
  _dokument_view). Frontenden hämtar den vid sidladdning. Det är den rutt som
  misstänks mest.
* **60 prov, 40 rättningar, 700 planerade lektioner** — högarna bakom
  källdörrarna.

Innehållet är inte påhittat: tavlan och provet läses ur kassetterna
(tests/kassetter/), alltså exakt den JSON modellen faktiskt producerar. Ett
uppdiktat papper på 200 byte hade mätt fel sak.

Sedan startas servern mot den fyllda basen och varje läsrutt tas på tiden tre
gånger (medianen räknas, den första körningen värmer cachen). En rad per rutt:

    rutt  ms  MB  rader

Larmet: en rutt över taket (1 s) ger exit 1. En lärare som väntar en sekund på
att appen ska öppna sig i maj har en app som gått sönder över läsåret, även om
varje enskild rad i basen är riktig.

Kör:
    python -m tools.volym                     # ett läsår
    python -m tools.volym --ar 3              # tre läsår (appen byts inte varje år)
    python -m tools.volym --ar 1 --behall     # låt basen ligga kvar och titta i den
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
PORT = 8753                      # inte 8751 (sviten), inte 8752 (soaken)
BAS = Path(tempfile.gettempdir()) / "transkribera-volym"

# Ett läsår, i det som faktiskt hamnar i basen. `--ar` multiplicerar allt.
PER_AR = {"lektioner": 700, "papper": 400, "prov": 60, "rattningar": 40,
          "planerade": 700}
VERSIONER = 4                    # ett papper skrivs om några gånger innan det duger

# Läsrutterna appen öppnar sig med. Frågetecknet är rutter som tar en parameter.
RUTTER = [
    "/api/schema",               # kontroll: liten och konstant, ska aldrig växa
    "/api/dokument",
    "/api/lessons",
    "/api/history",
    "/api/agenda",
    "/api/planning/archive",
    "/api/exams",
    "/api/rattningar",
    "/api/trends?group_id=1",     # klassens termin — utan grupp svarar den 422
    "/api/next-prep?group_id=1",
    "/api/search?q=derivatan",
]

TAK_S = 1.0                      # över detta känns appen trög i handen


# --------------------------------------------------------------- innehållet --

def ur_kassett(namn: str) -> dict:
    """Den JSON modellen faktiskt svarade med, ur ett inspelat band.

    Kassetten är strömmen rad för rad; sista raden med ett `result`-fält bär
    hela dokumentet. Faller läsningen tillbaka på {} mäter vi fel sak — därför
    kastar den hellre."""
    bandet = json.loads((ROT / "tests" / "kassetter" / f"{namn}.json")
                        .read_text(encoding="utf-8"))
    for rad in reversed(bandet.get("rader") or []):
        try:
            o = json.loads(rad)
        except (TypeError, ValueError):
            continue
        if isinstance(o, dict) and isinstance(o.get("result"), str):
            try:
                return json.loads(o["result"])
            except ValueError:
                continue
    raise RuntimeError(f"kassetten {namn} bär inget dokument")


# Ett transkript är det tyngsta appen lagrar. 60 KB ≈ en timmes tal (~9000 ord).
_STYCKE = (
    "Då tittar vi på derivatans definition. Vi tar ändringskvoten mellan två "
    "punkter och låter avståndet h gå mot noll. Om ni tittar på tavlan så ser "
    "ni att sekanten närmar sig tangenten. Ja, precis — och då är gränsvärdet "
    "lutningen i punkten. Vi räknar ett exempel: f av x är x i kvadrat. "
    "Frågan var om det gäller för alla funktioner, och svaret är nej, den "
    "måste vara kontinuerlig i punkten. Vi tar en till på tavlan. "
)


def transkript(ordval: int, tecken: int = 60_000) -> str:
    """~60 KB tal. Texten varieras per lektion — ett identiskt transkript i
    varje rad gör FTS-indexet orealistiskt litet och sökningen orimligt snabb."""
    krydda = f"Lektion {ordval}. Vi fortsätter på kapitel {ordval % 9 + 1}. "
    return (krydda + _STYCKE * (tecken // len(_STYCKE) + 1))[:tecken]


def papper(nr: int, tavla: dict, prov: dict) -> dict:
    """Formen frontenden faktiskt sparar (plan.js), med ett äkta dokument i
    `resultat` — vartannat en tavla, vartannat ett prov."""
    ar_prov = nr % 2 == 0
    return {
        "typ": "Prov" if ar_prov else "Tavla",
        "moment": f"moment {nr % 40}", "klass": f"NA{24 + nr % 3}",
        "kurs": "Matematik 3c", "datum": str(date(2026, 8, 24) + timedelta(days=nr % 300)),
        "tid": "08:15–09:45", "lektionsdatum": None, "lektionstid": None,
        "gy": ["Deriveringsregler"], "kalla": True, "kallor": ["Produktregeln"],
        "sidor": "204–208", "bokuppg": None,
        "inst": {"antal": 8, "nivamix": "Balanserat", "delprov": "Del A + Del B",
                 "losningar": True, "formelblad": True, "provtid": "120 min"},
        "bilder": {}, "referenser": [], "forlaga": None,
        "resultat": prov if ar_prov else tavla,
        "fokus": "", "kontext": "start", "niva": False, "svarighet": 0,
        "andrat": [], "anteckning": f"Utkast {nr}",
    }


def fyll(bas: Path, ar: float, *, tyst: bool = False) -> None:
    """Fyll basen med ett läsårs arbete (gånger `ar`).

    `synchronous=OFF` gäller BARA seedningen: db-funktionerna committar en gång
    per rad, och 30 000 fsync tar tio minuter utan att mäta något. Basen slängs
    ändå efteråt."""
    sys.path.insert(0, str(ROT))
    from app import db

    tavla, prov = ur_kassett("tavla"), ur_kassett("prov")
    conn = db.connect(bas / "transkribera.db")
    conn.execute("PRAGMA synchronous=OFF")
    n = {k: max(1, int(v * ar)) for k, v in PER_AR.items()}

    def spar(vad: str, i: int, av: int) -> None:
        if not tyst and (i % 50 == 0 or i == av):
            print(f"  {vad}: {i}/{av}", end="\r", flush=True)

    for namn in ("NA24", "NA25", "TE24"):
        conn.execute("INSERT OR IGNORE INTO groups (namn) VALUES (?)", (namn,))
    for namn in ("Matematik 3c", "Matematik 4"):
        conn.execute("INSERT OR IGNORE INTO courses (namn) VALUES (?)", (namn,))
    conn.commit()
    grupper = [r["id"] for r in conn.execute("SELECT id FROM groups").fetchall()]
    kurser = [r["id"] for r in conn.execute("SELECT id FROM courses").fetchall()]

    start = date(2025, 8, 18)
    for i in range(n["lektioner"]):
        d = str(start + timedelta(days=i // 4))
        les = db.create_lesson(
            conn, history_id=f"h{i}", ts=f"{d}T09:00:00", datum=d,
            starttid="09:00", name=f"NA25 {d} 09.00.m4a", source="inspelning",
            dur="01:12:04", model="gpt-transcribe", lang="sv",
            formats=["SRT", "TXT"], words=9000,
            group_id=grupper[i % len(grupper)], course_id=kurser[i % len(kurser)],
            transcript_text=transkript(i), created_at=f"{d}T10:14:00")
        # Bara den daterade insikten syns i /api/agenda — den rutten hämtar
        # varje daterad insikt i HELA basen, alltså en per lektion här.
        for typ, text, forfaller in (
                ("svårighet", "Kedjeregeln sitter inte.", None),
                ("åtgärd", "Repetera på fredag.", None),
                ("kalender", "Prov om två veckor.",
                 str(start + timedelta(days=i // 4 + 14)))):
            db.add_insight(conn, les["id"], typ, text, due_date=forfaller,
                           source="llm")
        spar("lektioner", i + 1, n["lektioner"])

    for i in range(n["papper"]):
        v = papper(i, tavla, prov)
        d = db.create_dokument(conn, dokument=v,
                               status="godkant" if i % 4 else "utkast")
        for k in range(VERSIONER - 1):
            db.add_dokument_version(conn, d["id"], dokument=dict(v, anteckning=f"v{k + 2}"))
        spar("papper", i + 1, n["papper"])

    for i in range(n["prov"]):
        db.create_exam(conn, exam=prov, typ="prov" if i % 3 else "arbetsblad",
                       titel=f"Prov {i}", datum=str(start + timedelta(days=i * 3)),
                       group_id=grupper[i % len(grupper)],
                       course_id=kurser[i % len(kurser)])
    for i in range(n["planerade"]):
        db.create_planned_lesson(
            conn, titel=f"Lektion {i}", moment=f"moment {i % 40}",
            board_json=json.dumps(tavla, ensure_ascii=False),
            datum=str(start + timedelta(days=i // 4)), starttid="09:00",
            group_id=grupper[i % len(grupper)], course_id=kurser[i % len(kurser)])

    dok = [r["id"] for r in conn.execute(
        "SELECT id FROM dokument ORDER BY id LIMIT ?", (n["rattningar"],)).fetchall()]
    for i, did in enumerate(dok):
        db.save_rattning(conn, did, elever=28, andel=0.72, klass="NA25",
                         kurs="Matematik 3c", datum=str(start + timedelta(days=i * 5)),
                         rader=[{"nyckel": f"{j}", "kod": "E", "text": "Uppgift",
                                 "p": 2, "formaga": "P", "varde": 1.4, "andel": 0.7}
                                for j in range(12)])
    conn.close()

    # history.json är TAKAT till 200 poster (history_store.MAX_ENTRIES) — den
    # växer alltså inte med läsåret. Den fylls ändå, till taket, så att rutten
    # mäts med det största den kan bli.
    #
    # Posterna måste vara lektioner som FINNS: servern lyfter in okända
    # history_id i lessons vid start, och en historik med hittepå-id gav 200
    # lektioner i en bas som skulle ha 21.
    from app import history_store
    poster = [{"id": f"h{i}", "ts": f"2026-05-{i % 28 + 1:02d}T09:00:00",
               "name": f"NA25 lektion {i}.m4a", "dur": "01:12:04",
               "model": "gpt-transcribe", "lang": "sv", "formats": ["SRT", "TXT"],
               "words": 9000, "text": transkript(i, 4000)}
              for i in range(min(history_store.MAX_ENTRIES, n["lektioner"]))]
    (bas / "history.json").write_text(
        json.dumps(poster, ensure_ascii=False, indent=2), encoding="utf-8")
    if not tyst:
        print(" " * 40, end="\r")


# ------------------------------------------------------------------ mätning --

def starta_server(bas: Path) -> subprocess.Popen:
    """Samma start som soaken, med molnet fejkat: ingen rutt som mäts här ringer
    ut, men servern vägrar starta utan en CLI att peka på."""
    sys.path.insert(0, str(ROT))
    from tests import fejk

    miljo = os.environ.copy()
    miljo["CLAUDE_CODE_BIN"] = str(fejk.skriv_claude(bas / "fejkbin"))
    miljo["FEJK_CLAUDE"] = "auto"
    miljo["FEJK_KASSETTER"] = str(fejk.KASSETTER)
    miljo.pop("OPENAI_API_KEY", None)
    miljo["VOLYM_BAS"] = str(bas)
    miljo["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.Popen(
        [sys.executable, "-c",
         "import os, uvicorn; from pathlib import Path; from app.web import server; "
         "uvicorn.run(server.create_app(base_dir=Path(os.environ['VOLYM_BAS'])), "
         f"host='127.0.0.1', port={PORT}, log_level='warning')"],
        cwd=str(ROT), env=miljo,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/var-kors", timeout=2)
            return p
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    p.kill()
    raise RuntimeError("servern startade inte")


def ta_tid(rutt: str, varv: int = 3) -> dict:
    """Medianen av `varv` hämtningar. Första hämtningen värmer sidcachen och
    får inte bestämma resultatet — men den räknas med i `forsta`, för det är
    den läraren möter när appen just startat."""
    tider, storlek, rader = [], 0, 0
    for _ in range(varv):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}{rutt}", timeout=120) as r:
                kropp = r.read()
        except Exception as e:                       # en rutt som faller ska synas
            return {"rutt": rutt, "ms": -1, "mb": 0.0, "rader": 0, "fel": str(e)[:60]}
        tider.append(time.perf_counter() - t0)
        storlek = len(kropp)
        try:
            d = json.loads(kropp.decode())
            rader = (len(d) if isinstance(d, list)
                     else max((len(v) for v in d.values() if isinstance(v, list)),
                              default=0))
        except ValueError:
            rader = 0
    return {"rutt": rutt, "ms": round(statistics.median(tider) * 1000),
            "forsta_ms": round(tider[0] * 1000), "mb": round(storlek / 1e6, 2),
            "rader": rader, "fel": ""}


def main() -> int:
    ap = argparse.ArgumentParser(description="Volymmätning: appen efter ett läsår")
    ap.add_argument("--ar", type=float, default=1.0, help="antal läsår att fylla")
    ap.add_argument("--tak", type=float, default=TAK_S, help="sekunder per rutt")
    ap.add_argument("--logg", default=str(ROT / "volym.log"))
    ap.add_argument("--behall", action="store_true", help="behåll basen efteråt")
    a = ap.parse_args()

    if BAS.exists():
        shutil.rmtree(BAS, ignore_errors=True)
    BAS.mkdir(parents=True, exist_ok=True)

    n = {k: max(1, int(v * a.ar)) for k, v in PER_AR.items()}
    print(f"volym: {a.ar} läsår — {n['lektioner']} lektioner, {n['papper']} papper "
          f"× {VERSIONER} versioner, {n['prov']} prov, {n['planerade']} planerade",
          flush=True)
    t0 = time.time()
    fyll(BAS, a.ar)
    db_mb = (BAS / "transkribera.db").stat().st_size / 1e6
    wal = BAS / "transkribera.db-wal"
    print(f"fylld på {time.time() - t0:.0f} s — basen är {db_mb:.0f} MB"
          f"{f' (+{wal.stat().st_size / 1e6:.0f} MB WAL)' if wal.exists() else ''}",
          flush=True)

    server = starta_server(BAS)
    try:
        import psutil
        rss_fore = psutil.Process(server.pid).memory_info().rss / 1e6
        rader = [ta_tid(r) for r in RUTTER]
        rss_efter = psutil.Process(server.pid).memory_info().rss / 1e6
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        if not a.behall:
            shutil.rmtree(BAS, ignore_errors=True)

    print(f"\n{'rutt':<26} {'ms':>7} {'första':>7} {'MB':>6} {'rader':>6}", flush=True)
    for r in rader:
        if r["fel"]:
            print(f"{r['rutt']:<26} {'FEL':>7}   {r['fel']}", flush=True)
            continue
        print(f"{r['rutt']:<26} {r['ms']:>7} {r['forsta_ms']:>7} "
              f"{r['mb']:>6} {r['rader']:>6}", flush=True)
    print(f"\nserverns minne: {rss_fore:.0f} → {rss_efter:.0f} MB "
          f"(basen {db_mb:.0f} MB)", flush=True)

    Path(a.logg).write_text(json.dumps(
        {"ar": a.ar, "antal": n, "db_mb": round(db_mb, 1),
         "rss_mb": [round(rss_fore, 1), round(rss_efter, 1)], "rutter": rader},
        ensure_ascii=False, indent=1), encoding="utf-8")

    larm = [f"{r['rutt']} tog {r['ms']} ms" for r in rader
            if r["ms"] > a.tak * 1000]
    larm += [f"{r['rutt']}: {r['fel']}" for r in rader if r["fel"]]
    print("\n" + ("\n".join("LARM: " + x for x in larm) if larm
                  else f"inget larm — varje rutt under {a.tak:.0f} s"), flush=True)
    print(f"loggen: {a.logg}", flush=True)
    return 1 if larm else 0


if __name__ == "__main__":
    raise SystemExit(main())
