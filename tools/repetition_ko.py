"""Kön som skriver NA26F:s repetitionsblad inför prov 86 «Uttryck och olikheter».

Varför den finns: tjugofem arbetsblad (åtta delar × tre rena nivåer + ett
blandat) är fem till tolv timmars modelltid, och lärarens app har EN
LLM-ägare. Panelen kan bara köa ett blad i taget och kön dör med fliken; den
här kön lever i sin egen process, tål att sessionen som startade den tar slut,
och går att starta om utan att skriva om det som redan är klart.

Vad den INTE gör: den rör inga dokument. «Ett utkast i taget» gäller
planeringsdokument, inte exam-rader — raderna ligger kvar och återskapas i
steg 2 (tools/dokument_aterskapa.py). Kön genererar alltså bara exams.

Tre saker den måste göra rätt, och de är alla tre skälet till att den inte är
ett `curl` i en loop:

  * FÖLJA JOBBET, INTE STRÖMMEN. Varje blad tar en halvtimme (nivågrinden) och
    del 8 dessutom bokläsningen à 96 s/sida. En SSE-ström som står öppen så
    länge dör på vägen. Servern skriver därför jobbet till `jobb`/`jobb_events`
    (app/web/sse.py) och strömmen är bara ett fönster mot det: vi läser första
    eventet (jobb-id:t), släpper anslutningen och pollar databasen.
  * VÄNTA UT 409. `_LLM_BUSY` betyder att läraren själv skriver något. Det är
    inte ett fel, det är en kö på ett ställe, och svaret är att sova och fråga
    igen.
  * LAGA VARNINGARNA. Minnesregeln: varningar ska lagas, inte lämnas. Fynden
    kommer med svaret (`efterkontroll`) och meningen som lagar dem är serverns
    egen (`efterkontroll_instruktion`) — samma väg canvasens «Laga fynden» går.
    Högst två varv: två varv i rad på samma lista är två notor och lika gärna
    samma svar, och det tredje är lärarens beslut, inte kvällens.

Användning:
    python -m tools.repetition_ko                 # hela kön, i ordning
    python -m tools.repetition_ko --bara del2-E   # ett blad (testkörningen)
    python -m tools.repetition_ko --lista         # visa kön, kör ingenting

Löskopplat (överlever att sessionen avslutas):
    powershell -NoProfile -Command "Start-Process python
      -ArgumentList '-m','tools.repetition_ko' -WorkingDirectory 'E:\\Transkribera'
      -WindowStyle Hidden"
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import exam_gen                                          # noqa: E402
from app.web.routes_exam import (_ATGARD, _fynd,                  # noqa: E402
                                 efterkontroll_instruktion,
                                 efterkontroll_nummer)

# ── VAR SAKERNA BOR ─────────────────────────────────────────────────────────
# Lägesfilen ligger UTANFÖR repot med flit: den är kvällens arbetsläge och inte
# kod, och repot ska inte bära vare sig data eller .md-filer.
DB = Path(r"E:\Transkribera\transkribera.db")
API = "http://127.0.0.1:18731"
MAPP = Path(r"C:\Users\bolun\.claude\projects\E--Transkribera\repetition-na26f")
LAGE = MAPP / "lage.json"
LOGG = MAPP / "ko.log"
KOFIL = MAPP / "ko.json"
LAS = MAPP / "ko.pid"

PROV_ID = 86                       # «Uttryck och olikheter», NA26F, 2026-10-01
BOK_ID = 5                         # Liber Ma 1c
GROUP_ID, COURSE_ID = 324, 2       # NA26F, Matematik nivå 1c
KLASS, KURS = "NA26F", "Matematik, nivå 1c"
ANTAL = 10                         # uppgifter per blad

# Hur ofta vi frågar databasen hur det går. Femton sekunder är valt mot vad ett
# blad kostar (~30 min): tätare pollning är hundratals förfrågningar för en
# siffra som ändå bara rör sig var tionde minut, glesare gör loggen oläsbar.
POLL_S = 15
# Taket per jobb. Nivågrinden tar ~30 min, och det första bladet i del 8 läser
# dessutom ett trettiotal osedda boksidor à 96 s. Tre timmar är alltså inte
# generöst, det är «något har hängt sig» — och då ska kön gå vidare i stället
# för att stå kvar till morgonen.
TAK_S = 3 * 3600
# 409 = läraren skriver själv just nu. Trettio sekunder är hennes väntetid i
# appen också; kön ska inte tränga sig före.
UPPTAGET_S = 30
# Hur länge vi orkar vänta på en ledig molnplats innan bladet läggs åt sidan.
UPPTAGET_TAK_S = 90 * 60

# ── DELARNA, OCH MAPPNINGEN TILL PROVETS UPPGIFTER ──────────────────────────
# `nummer` är provets egna uppgiftsnummer (GET /api/exams/86/uppgiftstyper),
# och de går in som `infor_nummer`. Servern skickar då SORTEN till modellen —
# typ, förmåga, poäng, nivå, delmoment — aldrig texten (exam_gen.build_infor_prov),
# just för att bladet delas ut en vecka före provdagen.
#
# TRE STÄLLEN DÄR TABELLEN AVVIKER FRÅN PLANENS, och alla tre av samma skäl:
# planens sidspann är skrivna ur kapitlen, provets delmoment ur boken.
#   * Del 3 «Potensekvationer»: planen säger 1.2 / s. 7–21, men boken har
#     potensekvationerna i 2.1 (s. 50–52, bok_avsnitt) och provets uppgift 10
#     står där. Dörren sätts till 50–52; «exponenter som inte är heltal»
#     (s. 16–18) ligger kvar i del 2, där provets uppgift 2 har dem.
#   * Del 4 och 5 delar planens spann 22–41. Provet skiljer dem: uttryck och
#     parenteser 22–30, faktorisering 31–34. Dörrarna delas därefter, annars
#     hade faktoriseringsbladet fått hela 1.3 att välja ur.
#   * Del 8: planen säger 64–99, men 2.5:s uppgiftsmaterial slutar på s. 88
#     (provets delmoment: formler 64–68, modeller 69–72, mönster 85–88).
#     89–99 är olästa blandade kapitelsidor à 96 s och ger ingenting.
DELAR = [
    {"del": 1, "namn": "Kvadrat- och kubikrötter", "avsnitt": "1.1",
     "nummer": [1], "bok": (2, 6), "datum": "2026-09-22"},
    {"del": 2, "namn": "Potenslagarna", "avsnitt": "1.2",
     "nummer": [2, 3], "bok": (7, 21), "datum": "2026-09-22"},
    {"del": 4, "namn": "Utveckla och förenkla uttryck", "avsnitt": "1.3",
     "nummer": [4], "bok": (22, 30), "datum": "2026-09-22"},
    {"del": 5, "namn": "Faktorisera", "avsnitt": "1.3",
     "nummer": [8], "bok": (31, 41), "datum": "2026-09-22"},
    {"del": 6, "namn": "Ekvationer", "avsnitt": "2.1",
     "nummer": [9], "bok": (42, 49), "datum": "2026-09-28"},
    {"del": 3, "namn": "Potensekvationer", "avsnitt": "2.1",
     "nummer": [10], "bok": (50, 52), "datum": "2026-09-28"},
    {"del": 7, "namn": "Olikheter, tecken och intervall", "avsnitt": "2.2–2.4",
     "nummer": [5, 7], "bok": (53, 63), "datum": "2026-09-28"},
    {"del": 8, "namn": "Formler och mönster", "avsnitt": "2.5",
     "nummer": [6, 11, 12], "bok": (64, 88), "datum": "2026-09-28"},
    # Blandat: tom `infor_nummer` ÄR «hela provets bredd» (build_infor_prov
    # läser den så), och nivån lämnas ospecificerad — då gäller arbetsbladets
    # defaultband, precis som en orörd väljare i panelen.
    {"del": 9, "namn": "Blandat inför provet", "avsnitt": "1.1–2.5",
     "nummer": [], "bok": (2, 88), "datum": "2026-09-28", "nivaer": [None]},
]
# Etiketterna är exakt NIVAVAL-nycklarna för arbetsbladsprofilen
# (exam_spec.NIVAVAL["arbetsblad"]). «E» eller «E-nivå» är inte samma sak för
# servern: en okänd etikett tolkas som default, alltså BLANDAT, och bladet hade
# blivit ett blandat blad utan att någon sagt till.
NIVAER = ["E-nivå", "C-nivå", "A-nivå"]


# ── LÄGESFIL OCH LOGG ───────────────────────────────────────────────────────

def nu() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def logga(rad: str) -> None:
    MAPP.mkdir(parents=True, exist_ok=True)
    with LOGG.open("a", encoding="utf-8") as f:
        f.write(f"[{nu()}] {rad}\n")
    # Skrivs också till stdout för förgrundskörningen. Tyst när fönstret är
    # dolt och konsolen saknar kodsida för svenska tecken — en logg som kraschar
    # kön är värre än en logg ingen läser.
    try:
        print(f"[{nu()}] {rad}", flush=True)
    except Exception:
        pass


def las_lage() -> dict:
    if LAGE.exists():
        try:
            return json.loads(LAGE.read_text(encoding="utf-8"))
        except ValueError:
            logga("lage.json gick inte att läsa — börjar om med en tom fil")
    return {"befintliga": [], "mappning": {}, "blad": []}


def skriv_lage(lage: dict) -> None:
    """Atomiskt: filen läses av en annan session medan kön går, och en halv
    JSON är värre än en gammal."""
    MAPP.mkdir(parents=True, exist_ok=True)
    tmp = LAGE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(lage, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, LAGE)


# ── KÖLISTAN ────────────────────────────────────────────────────────────────

def bygg_ko() -> list[dict]:
    """Kön som JSON, i den ordning bladen ska skrivas: kapitel 1 först, sedan
    kapitel 2, blandat sist. Nyckeln är bladets identitet över omstarter."""
    punkter = punkter_per_nummer()
    ko, ordning = [], 0
    for d in DELAR:
        for niva in d.get("nivaer", NIVAER):
            ordning += 1
            kort = {"E-nivå": "E", "C-nivå": "C", "A-nivå": "A"}.get(niva, "B")
            koder = sorted({k for n in (d["nummer"] or punkter) for k in
                            punkter.get(n, [])})
            ko.append({
                "nyckel": f"del{d['del']}-{kort}",
                "del": d["del"], "namn": d["namn"], "avsnitt": d["avsnitt"],
                "niva": niva, "ordning": ordning, "datum": d["datum"],
                "infor_nummer": list(d["nummer"]),
                "bok": {"id": BOK_ID, "fran": d["bok"][0], "till": d["bok"][1]},
                "punkter": koder,
                # Lärarens viktningsruta (app/lararord.build_fokus) är den enda
                # kanal som säger VAD bladet handlar om med ord. Utan den har
                # modellen bara sidorna och sorterna, och ett faktoriseringsblad
                # vars sort är «olikheter; faktorisering» kan då glida iväg åt
                # olikheterna. Meningen är kort med flit: rutan väger tyngst av
                # källorna och ska inte skriva pappret åt modellen.
                "fokus": (f"Bladet övar {d['namn'].lower()} "
                          f"(avsnitt {d['avsnitt']}, s. {d['bok'][0]}–"
                          f"{d['bok'][1]}) och ingenting annat."
                          if d["nummer"] else
                          "Bladet repeterar hela provets bredd, kapitel 1 och 2."),
            })
    return ko


def punkter_per_nummer() -> dict[int, list[str]]:
    """Provets egna innehållspunkter (Gy25-koder), uppgift för uppgift.

    Panelen skickar de koder läraren kryssat i; kön har ingen lärare att fråga
    och tar därför provets egna. Det är samma val hon skulle gjort: bladet
    förbereder just de uppgifterna."""
    doc = provdokument()
    ut: dict[int, list[str]] = {}
    for i, u in enumerate((doc or {}).get("uppgifter") or [], 1):
        ut[i] = [str(k) for k in (u.get("innehall") or []) if k]
    return ut


def provdokument() -> dict | None:
    conn = oppna()
    try:
        rad = conn.execute(
            "SELECT v.exam_json FROM exams e "
            "JOIN exam_versions v ON v.id = e.current_version "
            "WHERE e.id = ?", (PROV_ID,)).fetchone()
    finally:
        conn.close()
    if rad is None or not rad[0]:
        return None
    return json.loads(rad[0])


def las_ko() -> list[dict]:
    """Kön ur ko.json, och den skrivs första gången ur tabellen ovan. Filen är
    sanningen därefter: den som vill köra om ett blad med ett annat spann
    ändrar där och startar om kön, utan att röra koden."""
    if KOFIL.exists():
        return json.loads(KOFIL.read_text(encoding="utf-8"))["blad"]
    ko = bygg_ko()
    MAPP.mkdir(parents=True, exist_ok=True)
    KOFIL.write_text(json.dumps({"blad": ko}, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return ko


# ── DATABASEN (BARA LÄSNING) ────────────────────────────────────────────────

def oppna() -> sqlite3.Connection:
    """Anslutning till lärarens levande databas. `query_only` är inte en
    försiktighetsåtgärd utan en gräns: kön skriver ALDRIG i basen, den ber
    servern göra det. En tools-process som råkar skriva en rad i en bas
    servern har öppen är precis det som gör ett fel omöjligt att hitta."""
    conn = sqlite3.connect(str(DB), timeout=30)
    conn.execute("PRAGMA query_only = ON")
    return conn


def jobbets_slut(jobb_id: int) -> dict | None:
    """Jobbets sista ord, eller None medan det fortfarande går.

    Läses ur `jobb_events` och inte ur `jobb.status`: statusen säger ATT det
    gick bra, händelsen bär SVARET — hela exam-resultatet med efterkontroll,
    nivåfynd och fel."""
    conn = oppna()
    try:
        rader = conn.execute(
            "SELECT payload FROM jobb_events WHERE jobb_id = ? ORDER BY seq DESC "
            "LIMIT 40", (jobb_id,)).fetchall()
        status = conn.execute("SELECT status, fel FROM jobb WHERE id = ?",
                              (jobb_id,)).fetchone()
    finally:
        conn.close()
    for (payload,) in rader:
        try:
            ev = json.loads(payload)
        except ValueError:
            continue
        if ev.get("type") == "done":
            return {"status": "done", "result": ev.get("result")}
        if ev.get("type") == "error":
            return {"status": "error", "fel": ev.get("message") or "okänt fel"}
        if ev.get("type") == "avbrutet":
            return {"status": "avbrutet", "fel": "jobbet avbröts"}
    # Servern som startat om mitt i ett jobb lämnar status `avbrutet` utan
    # någon händelse (db.stada_jobb). Utan den här raden hade kön stått och
    # pollat ett jobb som aldrig kan svara.
    if status is not None and status[0] in ("done", "error", "avbrutet"):
        return {"status": status[0], "fel": status[1] or "jobbet tog slut utan svar"}
    return None


def senaste_raden(jobb_id: int) -> str:
    conn = oppna()
    try:
        rader = conn.execute(
            "SELECT payload FROM jobb_events WHERE jobb_id = ? ORDER BY seq DESC "
            "LIMIT 20", (jobb_id,)).fetchall()
    finally:
        conn.close()
    for (payload,) in rader:
        try:
            ev = json.loads(payload)
        except ValueError:
            continue
        if ev.get("type") in ("log", "progress"):
            return str(ev.get("msg") or ev.get("text") or "")
    return ""


# ── SERVERN ─────────────────────────────────────────────────────────────────

def starta(vag: str, kropp: dict) -> int:
    """POST:a och lämna tillbaka jobb-id:t.

    Vi läser bara första SSE-eventet — handskakningen `{"type":"jobb","id":N}`
    — och stänger sedan anslutningen. Det är inte ett avbrott: jobben som hör
    till dokumenten äger sin egen körning sedan v27 (app/web/sse.py), och en
    stängd ström är precis lärarens stängda flik. Alternativet, att hålla
    strömmen öppen en halvtimme, är det som går sönder.

    409 väntas ut: molnplatsen är lärarens också."""
    data = json.dumps(kropp, ensure_ascii=False).encode("utf-8")
    start = time.time()
    while True:
        req = urllib.request.Request(
            API + vag, data=data,
            headers={"Content-Type": "application/json",
                     "Accept": "text/event-stream"})
        try:
            svar = urllib.request.urlopen(req, timeout=180)
        except urllib.error.HTTPError as e:
            if e.code == 409 and time.time() - start < UPPTAGET_TAK_S:
                logga(f"  409 upptaget — väntar {UPPTAGET_S} s")
                time.sleep(UPPTAGET_S)
                continue
            raise RuntimeError(
                f"{e.code} {e.read().decode('utf-8', 'replace')[:400]}") from e
        try:
            for rad in svar:
                text = rad.decode("utf-8", "replace").strip()
                if not text.startswith("data:"):
                    continue
                ev = json.loads(text[5:].strip())
                if ev.get("type") == "jobb":
                    return int(ev["id"])
                # Ett fel före handskakningen finns inte i dagens server, men
                # om det kommer ska det synas som ett fel och inte som en
                # tystnad.
                if ev.get("type") == "error":
                    raise RuntimeError(str(ev.get("message")))
        finally:
            svar.close()
        # Strömmen tog slut utan handskakning. Att POSTa igen vore att starta
        # ett andra jobb på samma blad — loopen här uppe är till för 409 och
        # ingenting annat.
        raise RuntimeError("servern skickade aldrig något jobb-id")


def vanta(jobb_id: int, vad: str) -> dict:
    """Poll tills jobbet är slut. Returnerar svaret, eller reser felet."""
    start = time.time()
    sagt = ""
    while time.time() - start < TAK_S:
        slut = jobbets_slut(jobb_id)
        if slut is not None:
            if slut["status"] != "done":
                raise RuntimeError(f"{vad}: {slut.get('fel')}")
            return slut["result"] or {}
        rad = senaste_raden(jobb_id)
        if rad and rad != sagt:
            sagt = rad
            logga(f"  · {rad}")
        time.sleep(POLL_S)
    raise RuntimeError(f"{vad}: inget svar på {TAK_S // 60} minuter")


# ── PAYLOADEN ───────────────────────────────────────────────────────────────

def generate_kropp(post: dict) -> dict:
    """Exakt den kropp panelen skickar för ett arbetsblad i «Inför provet»-läget
    (app/web/ui/plan.js JOBB.Arbetsblad), med panelens egen sparsamhet:

      * `niva` följer med BARA när den inte står i defaultläget «Blandat» —
        samma regel som provets nivåmix. En orörd väljare ska ge byte för byte
        den begäran som gick i väg innan fältet fanns (kassettregeln).
      * `infor_prov_id` + `infor_nummer` följer med när ett prov är valt, och
        `infor_nummer` även tomt: tom lista ÄR «blandat», och servern läser
        den så.
      * `bok` är bokdörren som KÄLLA (plan.js bokKalla), och sidorna är bokens
        TRYCKTA nummer — offseten till PDF:en är serverns sak (app/bok.py).
        `remsa`/`bortremsa` utelämnas: de är lärarens uppgiftsurval ur panelen
        och finns inte här.
      * `elev_id`/`syfte` utelämnas: bladen är klassens, inte en elevs.
    """
    kropp = {
        "kurs": KURS, "klass": KLASS,
        "group_id": GROUP_ID, "course_id": COURSE_ID,
        "punkter": list(post.get("punkter") or []),
        "punkter_text": [],
        "antal": ANTAL,
        "delar": False,
        "datum": post["datum"],
        "typ": "arbetsblad",
        "illustration": True,
        "infor_prov_id": PROV_ID,
        "infor_nummer": list(post.get("infor_nummer") or []),
        "bok": dict(post["bok"]),
    }
    if post.get("niva"):
        kropp["niva"] = post["niva"]
    if post.get("fokus"):
        kropp["fokus"] = post["fokus"]
    return kropp


def hamta_exam(exam_id: int) -> dict:
    """Bladet som det ligger. Samma svarsform som genereringen, men UTAN
    kopiefynden: servern räknar dem bara när anroparen pekat ut provet, och
    ett GET gör inte det (routes_exam._kopiefynd, fail-open). Kön räknar dem
    själv i `egna_fynd`."""
    with urllib.request.urlopen(API + f"/api/exams/{int(exam_id)}",
                                timeout=120) as svar:
        return json.loads(svar.read().decode("utf-8"))


def refine_kropp(post: dict, mening: str, nummer: list[int]) -> dict:
    """Omskrivningens kropp, samma väg canvasen går (plan.js iterationsJobb):
    meningen, bokdörren och uppgiftsnumren varvet låses till. Boken måste med
    — utan den byter modellen bok mitt i arbetspasset — men servern läser inga
    nya sidor för en omskrivning (routes_planning.bok_text)."""
    kropp = {"message": mening, "bok": dict(post["bok"])}
    if nummer:
        kropp["nummer"] = nummer
    return kropp


# ── EFTERKONTROLLEN ─────────────────────────────────────────────────────────

def egna_fynd(svar: dict, post: dict) -> list[dict]:
    """De fynd kön måste räkna själv, utöver svarets `efterkontroll`.

    KOPIORNA, därför att servern bara räknar dem när anroparen pekat ut provet,
    och det gör bara genereringen (`_exam_result(..., infor_prov_id=…)`).
    Omskrivningens svar kommer utan dem — fail-open med flit — så ett varv som
    skulle laga en kopia hade aldrig kunnat visa att den försvann. Räkningen är
    serverns egen, ord för ord (exam_gen.variationsflaggor).

    DRILLTÄCKNINGEN av samma skäl: den räknas i genereringens valideringsloop
    och syns i `errors` bara när loopen gav upp. Efter ett omskrivningsvarv kan
    en utbytt uppgift ha tappat sitt `drillar`-märke utan att någon säger det.
    """
    exam = svar.get("exam") or {}
    ut: list[dict] = []
    prov = provdokument()
    texter = exam_gen.uppgiftstexter(prov) if prov else []
    sedda = set()
    for f in (exam_gen.variationsflaggor(exam, texter) if texter else []):
        # Flaggan bär «6a» när det är en deluppgift; uppgiften är 6. Samma
        # läsning som servern gör (routes_exam._kopiefynd), och ett fynd per
        # uppgift: 6a och 6b är samma kopia.
        m = re.match(r"(\d+)", str(f.get("nr") or ""))
        if not m or int(m.group(1)) in sedda:
            continue
        nr = int(m.group(1))
        sedda.add(nr)
        ut.append(_fynd("kopia", f"Uppgift {nr} är provets egen uppgift med nya "
                        f"tal: «{f.get('text') or ''}». Bladet delas ut före "
                        "provdagen, så uppgiften får inte stå här.", nr))
    for fel in exam_gen.drilltackning(exam, post.get("infor_nummer") or []):
        ut.append(_fynd("drilltackning", str(fel.get("message") or fel)))
    return ut


def fynden(svar: dict, post: dict) -> list[dict]:
    """Svarets fynd plus kön's egna, en lista i läsordning. `tid` räknas inte:
    provtiden lagas genom att läraren sätter fler minuter eller tar bort poäng,
    aldrig genom att skriva om pappret (routes_exam._ATGARD saknar den med
    flit)."""
    ut = [f for f in (svar.get("efterkontroll") or [])
          if isinstance(f, dict) and f.get("kod") != "tid"]
    nycklar = {(f.get("kod"), f.get("nr")) for f in ut}
    for f in egna_fynd(svar, post):
        if (f.get("kod"), f.get("nr")) not in nycklar:
            ut.append(f)
    return ut


def mening_for(fynd: list[dict]) -> str:
    """Fynden som EN instruktion. Serverns egen funktion, så att kön och
    canvasens «Laga fynden» skickar ordagrant samma mening — två formuleringar
    av samma sak är två beteenden att hålla i takt."""
    return efterkontroll_instruktion(fynd)


def sammanfatta(fynd: list[dict]) -> list[str]:
    return [f"{f.get('kod')}#{f.get('nr') or '-'}: {(f.get('text') or '')[:160]}"
            for f in fynd]


def drillage(svar: dict, post: dict) -> dict:
    """Vilka av provets valda sorter bladet faktiskt övar, enligt uppgifternas
    egna `drillar`-märken."""
    valda = list(post.get("infor_nummer") or [])
    uppgifter = (svar.get("exam") or {}).get("uppgifter") or []
    markta = [u.get("drillar") for u in uppgifter
              if isinstance(u, dict) and isinstance(u.get("drillar"), int)]
    return {"valda": valda, "markta": markta,
            "saknas": [n for n in valda if n not in set(markta)],
            "omarkta": len(uppgifter) - len(markta)}


# ── ETT BLAD ────────────────────────────────────────────────────────────────

def kor_blad(post: dict, lage: dict, tidigare: dict | None = None) -> dict:
    """Ett blad, från begäran till lagade fynd.

    ÅTERUPPTAR ett halvfärdigt blad. Kön kan dödas mitt i — strömavbrott, en
    session som tar slut, en omstart — men jobbet på servern lever vidare och
    är redan betalt. Står bladet som «kor» i lägesfilen med ett jobb-id tar vi
    alltså upp det jobbet i stället för att POSTa ett andra: ett nytt anrop
    hade gett samma blad två gånger, och det andra hade dessutom fått vänta ut
    det första på molnplatsen."""
    t0 = time.time()
    gammal = tidigare or {}
    pagaende = (gammal.get("jobb_id")
                if gammal.get("status") == "kor" else None)
    rad = {"nyckel": post["nyckel"], "del": post["del"], "namn": post["namn"],
           "niva": post.get("niva") or "Blandat", "ordning": post["ordning"],
           "infor_nummer": post.get("infor_nummer") or [],
           "exam_id": gammal.get("exam_id"), "jobb_id": pagaende,
           "status": "kor",
           "varningar_fore": gammal.get("varningar_fore") or [],
           "varningar_efter": [], "varv": gammal.get("varv") or 0,
           "drillar": gammal.get("drillar"), "tid_s": 0, "fel": None,
           "startad": datetime.now().isoformat(timespec="seconds")}
    skriv_rad(lage, rad)

    try:
        if pagaende and not rad["exam_id"]:
            logga(f"  tar upp pågående jobb {pagaende}")
            jobb_id = pagaende
        elif rad["exam_id"]:
            # Bladet finns redan; ett avbrutet varv tas upp om det går, annars
            # läses pappret som det ligger och fynden räknas om på nytt.
            jobb_id = None
            logga(f"  exam {rad['exam_id']} finns redan — fortsätter på det")
        else:
            jobb_id = starta("/api/exams/generate", generate_kropp(post))
            rad["jobb_id"] = jobb_id
            skriv_rad(lage, rad)
            logga(f"  jobb {jobb_id} startat")
        if jobb_id:
            svar = vanta(jobb_id, "genereringen")
        else:
            svar = hamta_exam(rad["exam_id"])
        if not svar.get("exam"):
            raise RuntimeError("servern skrev inget blad")
        rad["exam_id"] = svar.get("id")
        rad["nivafel"] = svar.get("nivafel") or []
        rad["errors"] = len(svar.get("errors") or [])
        rad["rounds"] = svar.get("rounds")
        fynd = fynden(svar, post)
        if not rad["varningar_fore"]:
            rad["varningar_fore"] = sammanfatta(fynd)
        rad["drillar"] = drillage(svar, post)
        skriv_rad(lage, rad)
        logga(f"  exam {rad['exam_id']} skrivet, {len(fynd)} fynd")

        # ── LAGA, HÖGST TVÅ VARV ────────────────────────────────
        # Varv två körs bara om varv ett faktiskt flyttade något: står samma
        # fynd kvar är det inte en lista som behöver skickas igen, det är
        # något modellen inte kan laga, och då är nästa varv en nota utan
        # värde. Canvasen gör samma bedömning och låter läraren trycka.
        for varv in (1, 2):
            if varv <= (gammal.get("varv") or 0):
                continue               # redan kört före avbrottet
            if not fynd:
                break
            mening = mening_for(fynd)
            if not mening:
                break
            fore = {(f.get("kod"), f.get("nr")) for f in fynd}
            nummer = efterkontroll_nummer(fynd)
            logga(f"  varv {varv}: lagar {len(fynd)} fynd "
                  f"(uppgift {nummer or '–'})")
            jid = starta(f"/api/exams/{rad['exam_id']}/refine",
                         refine_kropp(post, mening, nummer))
            rad["jobb_id"] = jid
            rad["varv"] = varv
            skriv_rad(lage, rad)
            svar = vanta(jid, f"omskrivning {varv}")
            if not svar.get("exam"):
                raise RuntimeError("omskrivningen gav inget blad")
            fynd = fynden(svar, post)
            rad["drillar"] = drillage(svar, post)
            rad["nivafel"] = svar.get("nivafel") or []
            rad["varningar_efter"] = sammanfatta(fynd)
            skriv_rad(lage, rad)
            if {(f.get("kod"), f.get("nr")) for f in fynd} == fore:
                logga("  fynden stod kvar efter varvet — lämnar dem till läraren")
                break

        rad["varningar_efter"] = sammanfatta(fynd)
        rad["status"] = "klar" if not fynd else "klar-med-fynd"
    except Exception as e:                       # noqa: BLE001
        rad["status"] = "fel"
        rad["fel"] = str(e)[:600]
        logga(f"  FEL: {rad['fel']}")
    rad["tid_s"] = int(time.time() - t0)
    skriv_rad(lage, rad)
    logga(f"  {post['nyckel']}: {rad['status']} på {rad['tid_s'] // 60} min")
    return rad


def skriv_rad(lage: dict, rad: dict) -> None:
    """En rad per blad i lägesfilen, uppdaterad på plats. Skrivs efter varje
    steg och inte bara vid slutet: kön går i timmar, och den som läser filen
    under tiden ska se var den står."""
    blad = lage.setdefault("blad", [])
    for i, b in enumerate(blad):
        if b.get("nyckel") == rad["nyckel"]:
            blad[i] = rad
            break
    else:
        blad.append(rad)
    blad.sort(key=lambda b: b.get("ordning") or 0)
    skriv_lage(lage)


# ── BEFINTLIGA BLAD ─────────────────────────────────────────────────────────

def befintliga() -> list[dict]:
    """NA26F:s arbetsblad som de ligger nu. De ERSÄTTS av de nya men raderas
    inte — listan finns för att läraren ska kunna se vilka gamla papper som
    blir överflödiga, inte för att kön ska göra något åt dem.

    Två frågor i en: klassens egna (group 324) och kursens alla (course 2),
    för parallellklassens blad ligger i samma kurs och kan ha skrivits för
    samma avsnitt."""
    conn = oppna()
    try:
        rader = conn.execute(
            "SELECT id, titel, datum, status, nivaval, group_id, created_at "
            "FROM exams WHERE typ = 'arbetsblad' "
            "AND (group_id = ? OR course_id = ?) ORDER BY id",
            (GROUP_ID, COURSE_ID)).fetchall()
    finally:
        conn.close()
    ut = []
    for r in rader:
        titel = r[1] or ""
        ut.append({
            "exam_id": r[0], "titel": titel, "datum": r[2], "status": r[3],
            "niva": r[4], "group_id": r[5], "created_at": r[6],
            "klassens": r[5] == GROUP_ID,
            # Delen läses ur titeln när den går att läsa. Ingen gissning på
            # halva ord: en felaktig delmärkning är värre än ingen alls, för
            # den säger att ett gammalt blad täcker något det inte täcker.
            "del": del_ur_titel(titel),
        })
    return ut


def del_ur_titel(titel: str) -> int | None:
    t = (titel or "").lower()
    for d in DELAR:
        if d["namn"].lower() in t:
            return d["del"]
    # Ordningen är inte alfabetisk utan smalast först: «potensekvation»
    # innehåller «potens», och ett potensekvationsblad är inte ett potensblad.
    for ord_, delnr in (("kubikrötter", 1), ("rötter", 1),
                        ("potensekvation", 3), ("grundpotensform", 2),
                        ("potenslag", 2), ("prefix", 2), ("potens", 2),
                        ("faktorisering", 5), ("parentes", 4), ("uttryck", 4),
                        ("ekvation", 6), ("olikhet", 7), ("intervall", 7),
                        ("formler", 8), ("mönster", 8)):
        if ord_ in t:
            return delnr
    return None


def mappningen() -> dict:
    """Del → provets uppgiftsnummer, som den står i lägesfilen. Skrivs ner för
    att steg 3 (verifieringen) ska kunna pröva rätt sak: «bladet ska öva
    provets uppgift 2 och 3, inget annat»."""
    ut = {}
    for d in DELAR:
        ut[str(d["del"])] = {
            "namn": d["namn"], "avsnitt": d["avsnitt"],
            "infor_nummer": d["nummer"],
            "bok": {"id": BOK_ID, "fran": d["bok"][0], "till": d["bok"][1]},
            "datum": d["datum"],
        }
    return ut


# ── KÖN ─────────────────────────────────────────────────────────────────────

def ta_laset() -> bool:
    """Två köer mot samma server är två blad som slåss om molnplatsen, och
    lägesfilen hade fått två skribenter. Låset är en fil med pid: en död pid
    släpper det, för en kö som kraschade ska inte låsa natten."""
    MAPP.mkdir(parents=True, exist_ok=True)
    if LAS.exists():
        try:
            pid = int(LAS.read_text(encoding="utf-8").strip() or 0)
        except ValueError:
            pid = 0
        if pid and pid != os.getpid() and lever(pid):
            logga(f"en kö kör redan (pid {pid}) — avbryter")
            return False
    LAS.write_text(str(os.getpid()), encoding="utf-8")
    return True


def lever(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    except Exception:
        return True
    return True


def main(argv: list[str]) -> int:
    bara = None
    if "--lista" in argv:
        for p in las_ko():
            print(p["nyckel"], p["niva"], p["namn"], p["infor_nummer"], p["bok"])
        return 0
    if "--bara" in argv:
        bara = argv[argv.index("--bara") + 1]
    if not ta_laset():
        return 1

    lage = las_lage()
    lage["prov_id"] = PROV_ID
    lage["befintliga"] = befintliga()
    lage["mappning"] = mappningen()
    skriv_lage(lage)

    ko = las_ko()
    if bara:
        ko = [p for p in ko if p["nyckel"] == bara]
        if not ko:
            logga(f"okänt blad: {bara}")
            return 1
    logga(f"kön startar: {len(ko)} blad" + (f" (bara {bara})" if bara else ""))

    fore = {b.get("nyckel"): b for b in lage.get("blad", [])}
    for post in ko:
        gammal = fore.get(post["nyckel"]) or {}
        if gammal.get("status") in ("klar", "klar-med-fynd"):
            logga(f"{post['nyckel']} är redan klart — hoppar över")
            continue
        logga(f"{post['nyckel']}: {post['namn']} {post.get('niva') or 'Blandat'}"
              f" · provets uppgift {post['infor_nummer'] or 'alla'}"
              f" · boken s. {post['bok']['fran']}–{post['bok']['till']}")
        kor_blad(post, lage, gammal)
    logga("kön är slut")
    try:
        LAS.unlink()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
