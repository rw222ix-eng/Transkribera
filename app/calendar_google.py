"""Google Kalender-integration (opt-in) för kalenderförslagen i lektionsoverlayen.

Medvetet undantag från appens offline-princip, aktiverat på ägarens uttryckliga
begäran (2026-07-05): endast händelser som användaren själv godkänner med
"Lägg till" skickas till Google — aldrig transkript, elevdata eller något
annat lektionsinnehåll utöver den titel/anteckning användaren ser och kan
redigera i förslaget.

Aktivering: skapa en OAuth-klient av typen "Desktop app" i Google Cloud
Console (API:t "Google Calendar API" påslaget), ladda ner klientfilen och lägg
den som ``google_client_secret.json`` i appens basmapp. "Anslut Google-konto"
i appen öppnar webbläsarens samtyckesflöde; åtkomsttoken sparas lokalt i
``google_token.json``. Utan google-biblioteken eller klientfilen svarar allt
här med vänliga fel — resten av appen påverkas inte.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
CLIENT_SECRET_NAME = "google_client_secret.json"
TOKEN_NAME = "google_token.json"
TIMEZONE = "Europe/Stockholm"
DEFAULT_DURATION_MIN = 40
# Bygg-/körtidsväg för en inbyggd klient (bakas in vid PyInstaller-bygget eller
# sätts i utvecklingsläge) så slutanvändaren slipper Cloud Console helt: sätt
# variabeln till klientens rå-JSON, så blir kopplingen ett rent "logga in".
ENV_CLIENT = "TRANSKRIBERA_GOOGLE_CLIENT"

HINT_LIBS = ("Google-biblioteken saknas — installera google-api-python-client "
             "och google-auth-oauthlib.")


def _files(base_dir: Path) -> tuple[Path, Path]:
    return Path(base_dir) / CLIENT_SECRET_NAME, Path(base_dir) / TOKEN_NAME


def _hint_secret(base_dir: Path) -> str:
    return (f"Ingen OAuth-klientfil hittades — skapa en \"Desktop app\"-klient i "
            f"Google Cloud Console och lägg den som {CLIENT_SECRET_NAME} i {base_dir}.")


def _looks_like_client(cfg) -> bool:
    """Grov validering: en nedladdad OAuth-klient har {"installed"|"web": {client_id}}."""
    if not isinstance(cfg, dict):
        return False
    root = cfg.get("installed") or cfg.get("web")
    return isinstance(root, dict) and bool(root.get("client_id"))


def _bundled_candidates() -> list[Path]:
    """Platser där en inbyggd klientfil kan ligga i den paketerade appen."""
    out: list[Path] = []
    mei = getattr(sys, "_MEIPASS", None)          # PyInstaller-bundlens temp-rot
    if mei:
        out.append(Path(mei) / CLIENT_SECRET_NAME)
    return out


def _client_config(base_dir: Path):
    """Lös upp OAuth-klienten: env-JSON → inbyggd fil → användarens installerade
    fil i basmappen. Returnerar dict eller None. Ingen hemlighet checkas in."""
    raw = os.environ.get(ENV_CLIENT)
    if raw:
        try:
            cfg = json.loads(raw)
            if _looks_like_client(cfg):
                return cfg
        except (ValueError, json.JSONDecodeError):
            pass
    for cand in _bundled_candidates() + [_files(base_dir)[0]]:
        try:
            if cand.exists():
                cfg = json.loads(cand.read_text(encoding="utf-8"))
                if _looks_like_client(cfg):
                    return cfg
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return None


def client_ready(base_dir: Path) -> bool:
    return _client_config(base_dir) is not None


def install_client_secret(base_dir: Path, raw: str) -> dict:
    """Spara en klient-JSON som användaren valt i appen som ``google_client_secret.json``
    i basmappen (validerad). Gör filplaceringen till ett knapptryck."""
    try:
        cfg = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return {"error": "Filen är inte giltig JSON — välj klient-JSON:en du laddade ner."}
    if not _looks_like_client(cfg):
        return {"error": "Det ser inte ut som en OAuth-klientfil (saknar \"installed\"/client_id). "
                         "Välj filen från en OAuth-klient av typen \"Desktop app\"."}
    secret, _ = _files(base_dir)
    try:
        secret.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        return {"error": f"Kunde inte spara klientfilen: {exc}"}
    return {"ok": True, "client_ready": True}


def _load_creds(base_dir: Path):
    """Läs sparad token och förnya den vid behov. None om inte ansluten."""
    try:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2.credentials import Credentials
    except ImportError:
        return None
    _, token = _files(base_dir)
    if not token.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    except (ValueError, json.JSONDecodeError):
        return None
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleRequest())
        except Exception:
            return None
        token.write_text(creds.to_json(), encoding="utf-8")
        return creds
    return None


def status(base_dir: Path) -> dict:
    """Anslutningsstatus för UI:t: {connected, client_ready, hint?}.
    ``client_ready`` = en OAuth-klient finns (inbyggd eller installerad) så det
    som återstår bara är själva Google-inloggningen."""
    try:
        import google_auth_oauthlib  # noqa: F401  (bara närvarokoll)
    except ImportError:
        return {"connected": False, "client_ready": False, "hint": HINT_LIBS}
    if _client_config(base_dir) is None:
        return {"connected": False, "client_ready": False, "hint": _hint_secret(base_dir)}
    return {"connected": _load_creds(base_dir) is not None, "client_ready": True}


def connect(base_dir: Path) -> dict:
    """Kör OAuth-samtyckesflödet i användarens webbläsare (blockerar tills
    callbacken kommit). Returnerar {connected} eller {connected, error}."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        return {"connected": False, "error": HINT_LIBS}
    cfg = _client_config(base_dir)
    if cfg is None:
        return {"connected": False, "error": _hint_secret(base_dir)}
    if _load_creds(base_dir) is not None:
        return {"connected": True}
    try:
        flow = InstalledAppFlow.from_client_config(cfg, SCOPES)
        creds = flow.run_local_server(
            port=0, authorization_prompt_message="",
            success_message="Klart — stäng fliken och gå tillbaka till Transkribera.")
    except Exception as exc:
        return {"connected": False, "error": f"Anslutningen misslyckades: {exc}"}
    _, token = _files(base_dir)
    token.write_text(creds.to_json(), encoding="utf-8")
    return {"connected": True}


def create_event(base_dir: Path, title: str, start_iso: str,
                 description: str = "",
                 duration_min: int = DEFAULT_DURATION_MIN,
                 end_date: str = "") -> dict:
    """Skapa en händelse i användarens primära kalender.
    Med `end_date` (YYYY-MM-DD, senare än startdagen) skapas i stället en
    heldagshändelse som sträcker sig från startdagen till och med slutdagen
    ("pågå till fredag" i förslagets chatt). Returnerar {ok, id, link} eller {error}."""
    creds = _load_creds(base_dir)
    if creds is None:
        st = status(base_dir)
        return {"error": st.get("hint")
                or "Inte ansluten till Google Kalender — klicka \"Anslut Google-konto\" först."}
    try:
        start = datetime.fromisoformat((start_iso or "").strip())
    except ValueError:
        return {"error": "Ogiltig starttid för händelsen."}
    span_end = None
    if end_date:
        try:
            span_end = datetime.fromisoformat(end_date.strip()).date()
        except ValueError:
            return {"error": "Ogiltigt slutdatum för händelsen."}
    if span_end and span_end > start.date():
        # Google räknar heldagshändelsers slutdatum exklusivt.
        body = {
            "summary": (title or "").strip() or "Händelse från Transkribera",
            "description": description or "",
            "start": {"date": start.date().isoformat()},
            "end": {"date": (span_end + timedelta(days=1)).isoformat()},
        }
    else:
        end = start + timedelta(minutes=max(5, int(duration_min or DEFAULT_DURATION_MIN)))
        body = {
            "summary": (title or "").strip() or "Händelse från Transkribera",
            "description": description or "",
            "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
            "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
        }
    try:
        from googleapiclient.discovery import build
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        created = service.events().insert(calendarId="primary", body=body).execute()
    except Exception as exc:
        return {"error": f"Kunde inte skapa händelsen: {exc}"}
    return {"ok": True, "id": created.get("id"), "link": created.get("htmlLink")}


# --------------------------------------------------------------- läsa in --
# Synken åt andra hållet (Etapp 0.1): schemat, salarna och loven kommer FRÅN
# Google. Appen skriver aldrig i dem — den läser dem och ritar veckan ur dem.
#
# Tolkningen är medvetet enkel och beskrivbar i en mening per regel, för en
# gissning som ser ut som fakta är värre än ett tomt schema:
#
#   · heldagshändelse med lovord i titeln  → lov
#   · ÅTERKOMMANDE tidsatt händelse        → en rad i veckoschemat
#   · allt annat tidsatt                   → en kalenderpost
#
# Klass och kurs plockas ur titeln: känt klass-/kursnamn ur databasen först,
# annars ett ord som ser ut som en klassbeteckning (9A, NA22, TE21a). Hittas
# ingen klass blir händelsen en post, inte en lektion — hellre en post för
# mycket i kalendern än en påhittad lektion i schemat.

_LOVORD = ("lov", "ledig", "helgdag", "röd dag", "klämdag")
_UPPEHALLSORD = ("studiedag", "avslutning", "uppstart", "planeringsdag",
                 "kompetensutveckling", "fortbildning")
_KLASS_MONSTER = re.compile(r"^(?:\d{1,2}[A-Za-zÅÄÖåäö]{1,3}"
                            r"|[A-ZÅÄÖ]{2,4}\d{2}[A-Za-zÅÄÖåäö]?)$")


def _lovtyp(namn: str, dagar: int) -> str | None:
    """lov | dag | uppehall | None. `dagar` = periodens längd i dagar."""
    n = (namn or "").lower()
    if any(o in n for o in _UPPEHALLSORD):
        return "uppehall"
    if any(o in n for o in _LOVORD):
        return "lov" if dagar >= 2 else "dag"
    return None


def _klass_och_kurs(titel: str, klasser: list[str],
                    kurser: list[str]) -> tuple[str, str]:
    t = titel or ""
    tl = t.lower()
    klass = next((k for k in klasser if k and k.lower() in tl), "")
    kurs = next((k for k in kurser if k and k.lower() in tl), "")
    if not klass:
        # Kvar står orden i titeln: det som SER UT som en klassbeteckning vinner,
        # och det sista av dem — "Matematik 3c 9A" har klassen sist.
        for ord_ in reversed(re.split(r"[\s,·/]+", t.strip())):
            if _KLASS_MONSTER.match(ord_) and ord_.lower() not in (kurs or "").lower():
                klass = ord_
                break
    if not kurs and klass:
        kurs = re.sub(r"[\s,·/]*" + re.escape(klass) + r"\s*$", "", t).strip()
    return klass, kurs


def _tid(start: str, slut: str) -> str:
    """"08:15–09:00" ur två ISO-tidsstämplar. Tankestreck, som schemat skriver."""
    return f"{(start or '')[11:16]}–{(slut or '')[11:16]}"


def tolka_handelser(handelser: list[dict], klasser: list[str] | None = None,
                    kurser: list[str] | None = None) -> dict:
    """Ren funktion: Google-händelser in, {schema, lov, poster} ut i exakt de
    former frontendens window.Kalender håller. Testbar utan Google."""
    klasser = sorted(klasser or [], key=len, reverse=True)
    kurser = sorted(kurser or [], key=len, reverse=True)
    schema: list[dict] = []
    sedda: set[tuple] = set()
    lov: list[dict] = []
    poster: list[dict] = []
    for h in handelser or []:
        titel = (h.get("summary") or "").strip()
        if not titel:
            continue
        start, slut = h.get("start") or {}, h.get("end") or {}
        if start.get("date"):                       # heldag
            fran = start["date"]
            # Google räknar heldagars slutdatum exklusivt.
            try:
                till = (date.fromisoformat(slut.get("date") or fran)
                        - timedelta(days=1)).isoformat()
            except ValueError:
                till = fran
            if till < fran:
                till = fran
            langd = (date.fromisoformat(till) - date.fromisoformat(fran)).days + 1
            typ = _lovtyp(titel, langd)
            if typ:
                lov.append({"fran": fran, "till": till, "namn": titel, "typ": typ})
            continue
        s, e = start.get("dateTime") or "", slut.get("dateTime") or ""
        if not s:
            continue
        datum = s[:10]
        klass, kurs = _klass_och_kurs(titel, klasser, kurser)
        if h.get("recurringEventId") and klass:
            try:
                dag = date.fromisoformat(datum).isoweekday()
            except ValueError:
                continue
            rad = {"dag": dag, "tid": _tid(s, e), "kurs": kurs, "klass": klass,
                   "sal": (h.get("location") or "").strip()}
            nyckel = (rad["dag"], rad["tid"], rad["klass"], rad["kurs"], rad["sal"])
            if nyckel not in sedda:                 # samma vecka, många instanser
                sedda.add(nyckel)
                schema.append(rad)
            continue
        poster.append({"datum": datum, "tid": _tid(s, e), "titel": titel,
                       "klass": klass})
    schema.sort(key=lambda r: (r["dag"], r["tid"], r["klass"]))
    lov.sort(key=lambda p: (p["fran"], p["till"]))
    poster.sort(key=lambda p: (p["datum"], p["tid"]))
    return {"schema": schema, "lov": lov, "poster": poster}


def list_events(base_dir: Path, fran: str, till: str) -> list[dict]:
    """Händelser i primärkalendern mellan två ISO-datum. singleEvents=True gör
    att återkommande serier expanderas till instanser — varje instans bär
    recurringEventId, som är det som avslöjar veckoschemat."""
    creds = _load_creds(base_dir)
    if creds is None:
        raise RuntimeError(
            status(base_dir).get("hint")
            or "Inte ansluten till Google Kalender — klicka \"Anslut Google-konto\" först.")
    from googleapiclient.discovery import build
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    ut: list[dict] = []
    sida = None
    while True:
        svar = service.events().list(
            calendarId="primary", singleEvents=True, orderBy="startTime",
            timeMin=f"{fran}T00:00:00Z", timeMax=f"{till}T00:00:00Z",
            maxResults=2500, pageToken=sida).execute()
        ut.extend(svar.get("items") or [])
        sida = svar.get("nextPageToken")
        if not sida:
            break
    return ut


# ------------------------------------------------------------- skriva ut --
# Motsatsen till read_schema, och den enda vägen dit appen skriver LEKTIONER:
# att lägga ut ett schema i lärarens egen kalender så att synken har något att
# läsa. Används för exempelschemat och för att prova kedjan hela vägen runt —
# aldrig av sig själv, alltid på uttrycklig begäran.
#
# Serierna skapas som ÅTERKOMMANDE händelser, för det är återkommandet som gör
# en händelse till en lektion när schemat läses tillbaka (se tolka_handelser).
# Lovdagarna undantas med EXDATE: en lektion mitt i sportlovet är fel i
# kalendern även om appen själv aldrig ritar den.

def _forsta_dagen(fran: str, veckodag: int) -> date:
    d = date.fromisoformat(fran)
    return d + timedelta(days=(int(veckodag) - d.isoweekday()) % 7)


def _klockslag(tid: str) -> tuple[str, str]:
    delar = [b.strip() for b in str(tid or "").replace("-", "–").split("–")]
    return (delar[0] if delar else "08:00"), (delar[1] if len(delar) > 1 else "")


def _exdates(start: date, till: date, starttid: str, lov: list[dict]) -> list[str]:
    """Instanserna som ligger på en stängd dag, i EXDATE-form."""
    ut, d = [], start
    while d <= till:
        iso = d.isoformat()
        if any(p["fran"] <= iso <= p["till"] for p in lov or []):
            ut.append(f"{iso.replace('-', '')}T{starttid.replace(':', '')}00")
        d += timedelta(days=7)
    return ut


def skriv_schema(base_dir: Path, *, schema: list[dict], termin: dict,
                 aterkommande: list[dict] | None = None,
                 lov: list[dict] | None = None) -> dict:
    """Lägg ut veckoschemat, de återkommande posterna och loven i användarens
    primära kalender. Returnerar {skapade, fel} eller {error}."""
    creds = _load_creds(base_dir)
    if creds is None:
        return {"error": status(base_dir).get("hint")
                or "Inte ansluten till Google Kalender."}
    fran, till = (termin or {}).get("fran"), (termin or {}).get("till")
    if not fran or not till:
        return {"error": "Terminens start- och slutdatum krävs."}
    try:
        from googleapiclient.discovery import build
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception as exc:
        return {"error": f"Kunde inte nå Google Kalender: {exc}"}

    slut_rrule = date.fromisoformat(till).strftime("%Y%m%dT235959Z")
    skapade, fel = 0, []

    def serie(titel: str, veckodag: int, tid: str, sal: str = "") -> None:
        nonlocal skapade
        start_dag = _forsta_dagen(fran, veckodag)
        if start_dag > date.fromisoformat(till):
            return
        t0, t1 = _klockslag(tid)
        if not t1:
            return
        recurrence = [f"RRULE:FREQ=WEEKLY;UNTIL={slut_rrule}"]
        undantag = _exdates(start_dag, date.fromisoformat(till), t0, lov or [])
        if undantag:
            recurrence.append(f"EXDATE;TZID={TIMEZONE}:" + ",".join(undantag))
        body = {
            "summary": titel, "location": sal or "",
            "start": {"dateTime": f"{start_dag.isoformat()}T{t0}:00", "timeZone": TIMEZONE},
            "end": {"dateTime": f"{start_dag.isoformat()}T{t1}:00", "timeZone": TIMEZONE},
            "recurrence": recurrence,
        }
        try:
            service.events().insert(calendarId="primary", body=body).execute()
            skapade += 1
        except Exception as exc:
            fel.append(f"{titel}: {exc}")

    for rad in schema or []:
        # Titeln är den synken läser tillbaka: kursen först, klassen sist.
        namn = " ".join(x for x in [(rad.get("kurs") or "").strip(),
                                    (rad.get("klass") or "").strip()] if x)
        serie(namn, rad.get("dag"), rad.get("tid"), rad.get("sal") or "")
    for p in aterkommande or []:
        titel = (p.get("titel") or "").strip()
        klass = (p.get("klass") or "").strip()
        serie(f"{titel} {klass}".strip(), p.get("dag"), p.get("tid"))
    for p in lov or []:
        try:
            slut = (date.fromisoformat(p["till"]) + timedelta(days=1)).isoformat()
        except (KeyError, TypeError, ValueError):
            continue
        try:
            service.events().insert(calendarId="primary", body={
                "summary": p.get("namn") or "Lov",
                "start": {"date": p["fran"]}, "end": {"date": slut},
            }).execute()
            skapade += 1
        except Exception as exc:
            fel.append(f"{p.get('namn')}: {exc}")
    return {"skapade": skapade, "fel": fel}


def read_schema(base_dir: Path, dagar: int = 210,
                klasser: list[str] | None = None,
                kurser: list[str] | None = None) -> dict:
    """{schema, lov, poster} ur Google Kalender, eller {error} när kopplingen
    saknas. Läser även bakåt: arkivets lovband ritar terminen som den VAR."""
    idag = date.today()
    fran = (idag - timedelta(days=120)).isoformat()
    till = (idag + timedelta(days=max(1, int(dagar or 210)))).isoformat()
    try:
        handelser = list_events(base_dir, fran, till)
    except RuntimeError as e:
        return {"error": str(e)}
    return tolka_handelser(handelser, klasser, kurser)
