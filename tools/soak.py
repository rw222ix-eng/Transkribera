"""Soak: kör lärardagarna varv efter varv och mät om appen växer (Etapp 4.2).

En lokal app för EN lärare får aldrig hundratals samtidiga användare — men den
får hundratals SESSIONER. Den startas i augusti och stängs i juni, och det som
läcker en aning per lektion blir en gigabyte i februari. Sviten fångar inte
det: varje `npx playwright test` startar en färsk server, mäter mot ett tomt
hus och river det efteråt.

Den här körningen gör motsatsen. EN serverprocess startas här, med en bas som
INTE töms mellan varven, och matrisen (e2e/larardagar.spec.mjs) körs mot den om
och om igen. Efter varje varv skrivs en rad:

    varv  sek  rss_mb  tradar  filer  tempkat  db_mb  papper  gpu

* **rss_mb / tradar** — de två som misstänks: `app/web/sse.py` startar en tråd
  per jobb (daemon, men en tråd som aldrig avslutas syns här) och
  `app/gpu_arbiter.py` håller låset.
* **filer** — öppna filhandtag. SQLite-anslutningar som inte stängs syns här
  innan de blir «database is locked».
* **tempkat** — föräldralösa `transkribera-moln-*` i systemets temp. Varje
  transkribering styckar ljudet i en egen katalog; en körning som dör mitt i
  ska inte lämna den kvar.
* **db_mb / papper** — basen SKA växa (varje varv godkänner papper). Det som
  granskas är takten: växer den linjärt är det arbete, växer den snabbare än
  antalet papper är det något annat.
* **gpu** — «fri» eller «LÅST». Ett jobb som dör utan att släppa låset gör
  appen obrukbar tills den startas om, och det är den värsta av alla läckor:
  läraren märker den när hon ska skriva morgondagens tavla.

Kör:
    python -m tools.soak --varv 3                # ett snabbt bevis (~3 min)
    python -m tools.soak --timmar 8              # över natten
    python -m tools.soak --varv 20 --spec zz-apan.spec.mjs

Larmet: RSS eller trådar som ökar över gränsen mellan första och sista varvet
ger exit 1 — och raderna ligger kvar i soak-loggen att titta på.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
PORT = 8752                      # inte 8751: sviten ska kunna köras samtidigt
BAS = Path(tempfile.gettempdir()) / "transkribera-soak"

# Gränser för larmet. Servern växer en del under första varvet (moduler som
# importeras lat, cachar som fylls), så jämförelsen görs mot varv 2.
MAX_RSS_VAXT_MB = 120
MAX_TRAD_VAXT = 8
MAX_FIL_VAXT = 40


def starta_server(bas: Path, minne: bool = False) -> subprocess.Popen:
    """Servern som ALLA varv kör mot — poängen är att den lever kvar.

    `minne` startar tracemalloc i processen och hänger på mätrutten (se
    tools/soakserver.py). Den kostar: varje allokering får en anropskedja på
    tjugofem rutor, så servern blir långsammare och tyngre. Ett varvs siffror
    är alltså INTE jämförbara mellan en körning med och en utan."""
    sys.path.insert(0, str(ROT))
    from tests import fejk

    bas.mkdir(parents=True, exist_ok=True)
    miljo = os.environ.copy()
    miljo["CLAUDE_CODE_BIN"] = str(fejk.skriv_claude(bas / "fejkbin"))
    miljo["FEJK_CLAUDE"] = "auto"
    miljo["FEJK_KASSETTER"] = str(fejk.KASSETTER)
    miljo.pop("OPENAI_API_KEY", None)
    miljo["SOAK_BAS"] = str(bas)
    miljo["SOAK_PORT"] = str(PORT)
    miljo["PYTHONIOENCODING"] = "utf-8"
    if minne:
        miljo["SOAK_MINNE"] = "1"
    p = subprocess.Popen(
        [sys.executable, "-m", "tools.soakserver"],
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


def matt(p, bas: Path) -> dict:
    """Ett varvs mätvärden. Allt som kan läsas utan att röra appen."""
    import psutil

    pr = psutil.Process(p.pid)
    with pr.oneshot():
        rss = pr.memory_info().rss / 1e6
        tradar = pr.num_threads()
    try:
        filer = len(pr.open_files())
    except (psutil.AccessDenied, OSError):
        filer = -1
    temp = Path(tempfile.gettempdir())
    tempkat = len(list(temp.glob("transkribera-moln-*")))
    db = bas / "transkribera.db"
    return {
        "rss_mb": round(rss, 1),
        "tradar": tradar,
        "filer": filer,
        "tempkat": tempkat,
        "db_mb": round(db.stat().st_size / 1e6, 2) if db.exists() else 0.0,
        "papper": papper(),
        "gpu": gpu_fri(),
    }


def _json(vag: str, kropp: dict | None = None):
    data = json.dumps(kropp).encode() if kropp is not None else None
    beg = urllib.request.Request(f"http://127.0.0.1:{PORT}{vag}", data=data,
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(beg, timeout=20) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception:
        return 0, {}


def papper() -> int:
    _s, d = _json("/api/dokument")
    return len(d.get("sparade") or []) if isinstance(d, dict) else -1


def gpu_fri() -> str:
    """Är GPU-låset fritt? Frågan finns inte som endpoint — men 409 betyder
    upptagen, och när ingenting körs är 409 detsamma som «låset läckte»."""
    status, _d = _json("/api/planning/generate", {"moment": ""})
    # Tom moment ger 400 FÖRE låset tas; 409 betyder att någon annan håller det.
    return "LÅST" if status == 409 else "fri"


def skriv_minne(d: dict) -> None:
    """En minnesbild: vad OS:et ser, vad Python vet om, och vad som växer.

    Läsordningen är viktig. Står `spårat` stilla medan `rss` klättrar är läckan
    inte i Python-kod — då är det en C-allokering eller fragmentering, och
    `topp` kommer att se oskyldig ut hur länge man än stirrar på den."""
    if not d:
        return
    print(f"    minne: rss {d.get('rss_mb')} MB | spårat {d.get('sparat_mb')} MB "
          f"(topp {d.get('sparat_topp_mb')}) | {d.get('objekt')} objekt | "
          f"{d.get('block')} block", flush=True)
    for r in (d.get("topp") or [])[:8]:
        plats = r["plats"]
        if len(plats) > 62:
            plats = "…" + plats[-61:]
        print(f"      +{r['mb']:>6.2f} MB  {r['antal']:>7} st  {plats}", flush=True)
    fler = [t for t in (d.get("typer") or []) if t["fler"] > 0][:5]
    if fler:
        print("      fler objekt: "
              + ", ".join(f"{t['typ']} +{t['fler']}" for t in fler), flush=True)


def kor_varv(spec: str, grep: str = "") -> tuple[bool, float]:
    t0 = time.time()
    miljo = os.environ.copy()
    miljo["SOAK"] = "1"                  # playwright.config.ts återanvänder servern
    miljo["SOAK_PORT"] = str(PORT)
    cmd = ["npx", "playwright", "test", spec, "--reporter=line"]
    if grep:
        cmd += ["--grep", grep]
    r = subprocess.run(cmd,
                       cwd=str(ROT / "e2e"), env=miljo, shell=(os.name == "nt"),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        print(r.stdout[-3000:] if r.stdout else "", flush=True)
    return r.returncode == 0, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser(description="Soak-körning av lärardagarna")
    ap.add_argument("--varv", type=int, default=3)
    ap.add_argument("--timmar", type=float, default=0.0,
                    help="kör tills tiden gått i stället för ett antal varv")
    ap.add_argument("--spec", default="larardagar.spec.mjs")
    ap.add_argument("--grep", default="",
                    help="kör bara dagarna som matchar (som playwright --grep)")
    ap.add_argument("--logg", default=str(ROT / "soak.log"))
    ap.add_argument("--behall", action="store_true",
                    help="behåll basen efteråt (för att titta i den)")
    ap.add_argument("--minne", action="store_true",
                    help="starta tracemalloc i servern och skriv vad som växer")
    ap.add_argument("--minne-var", type=int, default=10,
                    help="skriv minnesbilden vart N:e varv (med --minne)")
    a = ap.parse_args()

    if BAS.exists():
        shutil.rmtree(BAS, ignore_errors=True)
    server = starta_server(BAS, minne=a.minne)
    logg = Path(a.logg)
    rader: list[dict] = []
    slut = time.time() + a.timmar * 3600 if a.timmar else 0
    print(f"soak: bas {BAS}, port {PORT}, spec {a.spec}", flush=True)
    print("varv  sek   rss_mb  trådar  filer  tempkat  db_mb  papper  gpu", flush=True)
    try:
        varv = 0
        while True:
            varv += 1
            if slut and time.time() > slut:
                break
            if not slut and varv > a.varv:
                break
            ok, sek = kor_varv(a.spec, a.grep)
            m = matt(server, BAS)
            m["varv"], m["sek"], m["ok"] = varv, round(sek, 1), ok
            rader.append(m)
            print(f"{varv:<5} {m['sek']:<5} {m['rss_mb']:<7} {m['tradar']:<7} "
                  f"{m['filer']:<6} {m['tempkat']:<8} {m['db_mb']:<6} "
                  f"{m['papper']:<7} {m['gpu']}{'' if ok else '  ← SVITEN FÖLL'}",
                  flush=True)
            logg.write_text(json.dumps(rader, ensure_ascii=False, indent=1),
                            encoding="utf-8")
            # Jämförelsepunkten sätts efter varv 2, av samma skäl som larmet
            # räknar därifrån: varv 1 importerar moduler och fyller cachar, och
            # allt det ser ut som en läcka om man mäter från noll.
            if a.minne and varv == 2:
                _json("/__minne?bas=1")
            elif a.minne and varv > 2 and varv % a.minne_var == 0:
                skriv_minne(_json("/__minne")[1])
        if a.minne and len(rader) > 2:
            print("\nsista minnesbilden (mot varv 2):", flush=True)
            skriv_minne(_json("/__minne")[1])
    except KeyboardInterrupt:
        print("\navbrutet", flush=True)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        if not a.behall:
            shutil.rmtree(BAS, ignore_errors=True)

    if len(rader) < 2:
        print("för få varv att jämföra", flush=True)
        return 0 if rader and rader[0]["ok"] else 1

    # Jämför mot varv 2: första varvet importerar moduler och fyller cachar.
    bas_rad, sista = rader[1], rader[-1]
    larm = []
    if sista["rss_mb"] - bas_rad["rss_mb"] > MAX_RSS_VAXT_MB:
        larm.append(f"minnet växte {sista['rss_mb'] - bas_rad['rss_mb']:.0f} MB "
                    f"({bas_rad['rss_mb']} → {sista['rss_mb']})")
    if sista["tradar"] - bas_rad["tradar"] > MAX_TRAD_VAXT:
        larm.append(f"trådarna växte {sista['tradar'] - bas_rad['tradar']} "
                    f"({bas_rad['tradar']} → {sista['tradar']}) — SSE-jobb som "
                    f"aldrig avslutas")
    if bas_rad["filer"] >= 0 and sista["filer"] - bas_rad["filer"] > MAX_FIL_VAXT:
        larm.append(f"öppna filer växte {sista['filer'] - bas_rad['filer']} "
                    f"— db-anslutningar som inte stängs")
    if sista["tempkat"] > 0:
        larm.append(f"{sista['tempkat']} föräldralösa transkribera-moln-kataloger")
    if sista["gpu"] != "fri":
        larm.append("GPU-låset släpptes aldrig")
    if any(not r["ok"] for r in rader):
        larm.append(f"{sum(1 for r in rader if not r['ok'])} varv där sviten föll")

    print("\n" + ("\n".join("LARM: " + x for x in larm) if larm
                  else "inget larm — appen står stilla i vikt"), flush=True)
    print(f"loggen: {logg}", flush=True)
    return 1 if larm else 0


if __name__ == "__main__":
    raise SystemExit(main())
