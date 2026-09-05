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

Larmet: minnets TAKT (MB per varv, minsta kvadrat med standardfel) över
gränsen, eller trådar/filer som växer, ger exit 1 — och raderna ligger kvar i
soak-loggen att titta på. Takten larmar bara när hela konfidensintervallet
ligger över gränsen; ligger bara halva säger körningen OAVGJORT i stället för
att tiga, för en kort körning kan fälla minnet men aldrig fria det.

Ett varv som faller sparar Playwrights spår under `soak-fall/varv-NNNN/` —
`e2e/test-results/` skrivs annars över av nästa varv, en minut senare.
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
sys.path.insert(0, str(ROT))            # portkällan, app/web/port.py

from app.web import port as port_kalla   # noqa: E402  (efter sys.path)

PORT = port_kalla.SOAK           # inte E2E: sviten ska kunna köras samtidigt
BAS = Path(tempfile.gettempdir()) / "transkribera-soak"

# Gränser för larmet. Servern växer en del under första varvet (moduler som
# importeras lat, cachar som fylls), så jämförelsen görs mot varv 2.
#
# Minnet mäts som TAKT, inte som total växt. En absolut gräns säger olika saker
# om samma app beroende på hur länge man råkade köra: facit-körningen 2026-08-09
# landade på 106,7 MB mot en gräns på 120 och slapp larm — en timme längre hade
# larmat, utan att något var annorlunda. Takten är appens egenskap; totalen är
# klockans.
#
# Gränsen ligger i ett smalt band, och det är värt att veta varför. Bakgrunden
# efter fixarna är 0,313 MB/varv (C-sidans allokeringar, inte Pythons — se
# planens DEL X), och `plannings`-läckan som soaken FAKTISKT hittade låg på
# 0,425. En gräns som inte fäller den buggen är ett instrument utan värde, så
# den måste ligga däremellan. 0,40 friar dagens app med marginal (övre
# konfidensgräns 0,317) och fäller den gamla läckan (undre 0,424).
#
# Bandet är alltså smalt med flit, och siffran gäller den här maskinen. Byter
# maskin, Python-bygge eller matrisen innehåll: mät om bakgrunden först, annars
# larmar soaken på sig själv.
MAX_RSS_PER_VARV = 0.40
MAX_TRAD_VAXT = 8
MAX_FIL_VAXT = 40


def starta_server(bas: Path, minne=False) -> subprocess.Popen:
    """Servern som ALLA varv kör mot — poängen är att den lever kvar.

    `minne=True` hänger på mätrutten (tools/soakserver.py): RSS, antal levande
    Python-block och objekt per typ. Den kostar nästan ingenting och får därför
    läsas i en körning vars siffror ska jämföras med andra.

    `minne="sparning"` startar dessutom tracemalloc, som säger VAR objekten
    skapades — men bokför en anropskedja per allokering. Processen blir ~50 MB
    tyngre och varven ~50 % längre, så en sådan körnings RSS-tal är INTE
    jämförbara med en ren körnings."""
    sys.path.insert(0, str(ROT))
    from tests import fejk

    bas.mkdir(parents=True, exist_ok=True)
    miljo = os.environ.copy()
    miljo["CLAUDE_CODE_BIN"] = str(fejk.skriv_claude(bas / "fejkbin"))
    miljo["FEJK_CLAUDE"] = "auto"
    miljo["FEJK_KASSETTER"] = str(fejk.KASSETTER)
    miljo.pop("ELEVENLABS_API_KEY", None)
    miljo["SOAK_BAS"] = str(bas)
    miljo["SOAK_PORT"] = str(PORT)
    miljo["PYTHONIOENCODING"] = "utf-8"
    if minne:
        miljo["SOAK_MINNE"] = "1"
    if minne == "sparning":
        miljo["SOAK_SPARNING"] = "1"
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
    print(f"      hållare: {d.get('koer')} köer, {d.get('tradobjekt')} trådobjekt, "
          + ", ".join(f"{n}×{a}" for n, a in (d.get("levande_generatorer") or [])),
          flush=True)
    for k in (d.get("kedjor") or []):
        print(f"      kedja +{k['mb']:.2f} MB ({k['antal']} st):", flush=True)
        for rad in (k["egna"] or k["hela"]):
            print(f"        {rad}", flush=True)


def spara_fallet(varv: int, utskrift: str) -> Path | None:
    """Rädda undan Playwrights spår från ett varv som föll.

    `e2e/test-results/` skrivs över av NÄSTA varv, och i en åtta timmars
    körning är nästa varv en minut bort. Varv 320 i facit-körningen
    2026-08-09 föll på en timeout som aldrig gick att obducera av just det
    skälet — spåret, felkontexten och skärmbilderna var borta innan någon
    tittade."""
    kalla = ROT / "e2e" / "test-results"
    mal = ROT / "soak-fall" / f"varv-{varv:04d}"
    try:
        mal.mkdir(parents=True, exist_ok=True)
        (mal / "utskrift.txt").write_text(utskrift or "", encoding="utf-8")
        if kalla.is_dir():
            shutil.copytree(kalla, mal / "test-results", dirs_exist_ok=True)
        return mal
    except OSError as e:                 # full disk ska inte fälla soaken
        print(f"    (kunde inte spara fallet: {e})", flush=True)
        return None


# Uppvärmningen. Varv 1 importerar moduler, men det slutar inte där: lat
# importerade moduler dök upp i tracemalloc ända till varv åtta. Mätningen
# börjar därför vid varv fem — en sexvarvskörning larmade annars på 0,72
# MB/varv när det den såg var cachar som fylldes.
VARM_VARV = 5
# Färre än så säger ingenting. Fem punkter med ±1 MB brus kan varken fälla
# eller fria, och då ska soaken säga just det i stället för att gissa.
MIN_MATVARV = 15


def lutning(rader: list[dict]) -> tuple[float | None, float]:
    """Minnets TAKT i MB per varv, med standardfel — minsta kvadrat över RSS.

    Standardfelet är inte pynt. Bruset mellan varv är ±1 MB, och på tjugofem
    varv kunde en körning inte skilja 0,30 från 0,42 MB/varv (det tog 344 varv
    att göra det 2026-08-09). Larmet frågar därför om HELA
    konfidensintervallet ligger över gränsen, inte om punktskattningen gör det."""
    matbara = [r for r in rader if r["varv"] >= VARM_VARV]
    if len(matbara) < MIN_MATVARV:
        return None, 0.0
    x = [float(r["varv"]) for r in matbara]
    y = [float(r["rss_mb"]) for r in matbara]
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((t - mx) ** 2 for t in x)
    if sxx == 0:
        return None, 0.0
    k = sum((t - mx) * (u - my) for t, u in zip(x, y)) / sxx
    m = my - k * mx
    s2 = sum((u - (k * t + m)) ** 2 for t, u in zip(x, y)) / (n - 2)
    return k, (s2 ** 0.5) / (sxx ** 0.5)


def kor_varv(spec: str, grep: str = "", varv: int = 0) -> tuple[bool, float]:
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
        mal = spara_fallet(varv, r.stdout)
        if mal:
            print(f"    spåret sparat: {mal}", flush=True)
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
                    help="skriv minnesbilden (RSS, block, objekt) — billig, "
                         "påverkar inte mätningen")
    ap.add_argument("--sparning", action="store_true",
                    help="som --minne, plus tracemalloc: säger VAR objekten "
                         "skapades, men kostar ~50 MB och ~50 %% längre varv")
    ap.add_argument("--minne-var", type=int, default=10,
                    help="skriv minnesbilden vart N:e varv (med --minne)")
    a = ap.parse_args()

    bild = a.minne or a.sparning
    if BAS.exists():
        shutil.rmtree(BAS, ignore_errors=True)
    server = starta_server(BAS, minne='sparning' if a.sparning
                           else bool(a.minne))
    logg = Path(a.logg)
    # Förra körningen sparas ett steg bakåt. En åtta timmars mätning är det
    # dyraste den här filen innehåller, och den skrevs över av en sexvarvs
    # provkörning som råkade använda samma standardlogg (2026-08-09). Rådata
    # som kostat en natt ska inte kunna försvinna på ett kommando utan flaggor.
    if logg.exists():
        try:
            logg.replace(logg.with_suffix(logg.suffix + ".forra"))
        except OSError:
            pass
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
            ok, sek = kor_varv(a.spec, a.grep, varv)
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
            if bild and varv == 2:
                _json("/__minne?bas=1")
            elif bild and varv > 2 and varv % a.minne_var == 0:
                skriv_minne(_json("/__minne")[1])
        if bild and len(rader) > 2:
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
    k, se = lutning(rader)
    if k is None:
        print(f"\nför få varv för att mäta minnets takt — mätningen börjar vid "
              f"varv {VARM_VARV} och behöver {MIN_MATVARV} till", flush=True)
    else:
        print(f"\nminnets takt: {k:+.3f} MB/varv (standardfel {se:.3f}) — "
              f"{bas_rad['rss_mb']} → {sista['rss_mb']} MB på "
              f"{sista['varv'] - bas_rad['varv']} varv", flush=True)
        if k - 2 * se > MAX_RSS_PER_VARV:
            larm.append(f"minnet växer {k:.3f} MB/varv (gräns {MAX_RSS_PER_VARV})")
        elif k + 2 * se > MAX_RSS_PER_VARV:
            # Varken fällt eller friat. Att tiga här vore att låta en kort
            # körning se ut som ett godkännande — och det är precis det den
            # inte kan vara.
            print(f"  OAVGJORT: takten kan vara upp till {k + 2 * se:.3f} MB/varv. "
                  f"Kör längre innan minnet fris.", flush=True)
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
