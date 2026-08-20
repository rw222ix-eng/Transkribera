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
from functools import lru_cache
from pathlib import Path

from app import course_data

SCOPES = ["https://www.googleapis.com/auth/calendar.events",
          # Bara för att kunna LISTA kontots kalendrar i väljaren. Läraren kan
          # ha sin egen kalender inlänkad i jobbkontot vid sidan av dess egen
          # (så här: den personliga Gmail-kalendern är den som har
          # lektionerna), och då måste appen kunna visa vilka som finns.
          "https://www.googleapis.com/auth/calendar.calendarlist.readonly"]
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


# Namnet per token-fil, ändringstid och vald kalender: en nätrunda per
# inloggning, inte per fråga.
_KONTO: dict[tuple[str, float, str], str] = {}


def konto(base_dir: Path) -> str | None:
    """Namnet på kalendern synken läser, eller None. För kontots egen kalender
    är namnet kontots e-postadress; för en inlänkad kalender dess namn.

    Finns för att en synk mot FEL kalender ser precis ut som en lyckad synk:
    appen läste tillbaka sitt eget utskrivna exempelschema ur ett gammalt
    konto och sa «Synkad 19:07» (2026-08-10). Vad veckan kom ur ska stå i
    gränssnittet, inte behöva grävas fram ur google_token.json.

    Namnet läses som ``summary`` i events-svaret — calendars().get svarar 403
    på scopet calendar.events, och ett bredare scope bara för en etikett vore
    fel affär."""
    _, token = _files(base_dir)
    try:
        nyckel = (str(token), token.stat().st_mtime, vald_kalender(base_dir))
    except OSError:
        return None
    if nyckel in _KONTO:
        return _KONTO[nyckel]
    creds = _load_creds(base_dir)
    if creds is None:
        return None
    try:
        from googleapiclient.discovery import build
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        svar = service.events().list(
            calendarId=nyckel[2], maxResults=1,
            timeMin=f"{date.today().isoformat()}T00:00:00Z").execute()
    except Exception:                       # nätfel, indraget medgivande, …
        return None                         # namnlöst är bättre än trasigt
    namn = svar.get("summary") or None
    if namn:
        _KONTO[nyckel] = namn
    return namn


def koppla_bort(base_dir: Path) -> dict:
    """Glöm det anslutna kontot: tokenen raderas, klientfilen ligger kvar.

    Utan den här vägen gick kontot inte att BYTA från appen — connect() svarar
    "redan ansluten" så länge en token finns, och den som råkat logga in med
    fel konto fick redigera filer för hand."""
    _, token = _files(base_dir)
    try:
        token.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        return {"connected": False, "error": f"Kunde inte ta bort {TOKEN_NAME}: {exc}"}
    _KONTO.clear()
    return {"connected": False}


# Vilken kalender i det anslutna kontot appen läser och skriver. "primary" =
# kontots egen. Går att peka om, för den kalender läraren FAKTISKT lever i
# behöver inte vara kontots egen: här ligger den personliga Gmail-kalendern
# inlänkad i jobbkontot, och det är den som har lektionerna (2026-08-10).
KALENDER_NYCKEL = "google_kalender"


def vald_kalender(base_dir: Path) -> str:
    from app import settings_store
    vald = (settings_store.load(Path(base_dir)).get(KALENDER_NYCKEL) or "").strip()
    return vald or "primary"


def satt_kalender(base_dir: Path, kalender_id: str) -> dict:
    """Peka om synken till en annan kalender i samma konto. Tom sträng =
    tillbaka till kontots egen."""
    from app import settings_store
    data = settings_store.load(Path(base_dir))
    vald = (kalender_id or "").strip() or "primary"
    data[KALENDER_NYCKEL] = vald
    settings_store.save(Path(base_dir), data)
    _KONTO.clear()
    return {"kalender": vald}


def kalendrar(base_dir: Path) -> dict:
    """Kontots kalendrar för väljaren: {kalendrar: [{id, namn, egen, skriv}], vald}.

    Kräver scopet calendar.calendarlist.readonly — en token från före det
    scopet svarar 403, och då säger vi det istället för att visa en tom lista
    som såg ut som "du har inga kalendrar"."""
    creds = _load_creds(base_dir)
    if creds is None:
        return {"error": status(base_dir).get("hint")
                or "Inte ansluten till Google Kalender.", "vald": vald_kalender(base_dir)}
    try:
        from googleapiclient.discovery import build
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        svar = service.calendarList().list(maxResults=250).execute()
    except Exception as exc:
        return {"error": f"Kunde inte hämta kalenderlistan: {exc}",
                "vald": vald_kalender(base_dir)}
    lista = [{"id": k.get("id"), "namn": k.get("summaryOverride") or k.get("summary") or k.get("id"),
              "egen": bool(k.get("primary")),
              "skriv": k.get("accessRole") in ("owner", "writer")}
             for k in svar.get("items") or []]
    return {"kalendrar": lista, "vald": vald_kalender(base_dir)}


def status(base_dir: Path) -> dict:
    """Anslutningsstatus för UI:t: {connected, client_ready, konto?, kalender?, hint?}.
    ``client_ready`` = en OAuth-klient finns (inbyggd eller installerad) så det
    som återstår bara är själva Google-inloggningen."""
    try:
        import google_auth_oauthlib  # noqa: F401  (bara närvarokoll)
    except ImportError:
        return {"connected": False, "client_ready": False, "hint": HINT_LIBS}
    if _client_config(base_dir) is None:
        return {"connected": False, "client_ready": False, "hint": _hint_secret(base_dir)}
    if _load_creds(base_dir) is None:
        return {"connected": False, "client_ready": True}
    # `konto` bara när det finns ett — en nyckel med None hade sagt "vet inte"
    # om något som inte ens är anslutet.
    return {"connected": True, "client_ready": True, "konto": konto(base_dir),
            "kalender": vald_kalender(base_dir)}


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
        # Samma kalender som synken läser — annars hamnar det läraren godkänt
        # någon annanstans än veckan det hör hemma i.
        created = service.events().insert(
            calendarId=vald_kalender(base_dir), body=body).execute()
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
# De röda dagarna heter något — de innehåller inte ordet «lov». Utan den här
# listan läste synken tillbaka «Långfredag» och «Kristi himmelsfärd» som
# vanliga heldagsanteckningar och skolan såg öppen ut på en stängd dag.
_HELGDAGAR = ("nyårsdag", "trettondedag", "skärtorsdag", "långfredag",
              "påskafton", "påskdag", "annandag", "valborg", "första maj",
              "kristi himmelsfärd", "pingst", "nationaldag", "midsommar",
              "alla helgons", "julafton", "juldag", "nyårsafton")
_UPPEHALLSORD = ("studiedag", "avslutning", "uppstart", "planeringsdag",
                 "kompetensutveckling", "fortbildning")
_KLASS_MONSTER = re.compile(r"^(?:\d{1,2}[A-Za-zÅÄÖåäö]{1,3}"
                            r"|[A-ZÅÄÖ]{2,4}\d{2}[A-Za-zÅÄÖåäö]?)$")


def _lovtyp(namn: str, dagar: int) -> str | None:
    """lov | dag | uppehall | None. `dagar` = periodens längd i dagar."""
    n = (namn or "").lower()
    if any(o in n for o in _UPPEHALLSORD):
        return "uppehall"
    if any(o in n for o in _HELGDAGAR):
        return "lov" if dagar >= 3 else "dag"
    if any(o in n for o in _LOVORD):
        return "lov" if dagar >= 2 else "dag"
    return None


def _klass_och_kurs(titel: str, klasser: list[str],
                    kurser: list[str]) -> tuple[str, str]:
    t = titel or ""
    tl = t.lower()
    # Listorna kommer längdsorterade från tolka_handelser, och det är villkoret
    # för att första träffen är rätt: klasslistan har både «TE26» och «TE26A»,
    # och «TE26A: Kvadratrötter» är TE26A:s lektion — inte TE26:s.
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


def _langd(start: str, slut: str) -> int | None:
    """Längden i minuter, eller None när tiderna inte går att läsa. Slut före
    start betyder att händelsen korsar midnatt — då är den inte kort."""
    try:
        s = int(start[11:13]) * 60 + int(start[14:16])
        e = int(slut[11:13]) * 60 + int(slut[14:16])
    except (TypeError, ValueError, IndexError):
        return None
    return e - s if e >= s else None


def ar_notis(h: dict) -> bool:
    """En NOTIS, inte en händelse: en kort tidsatt punkt som är markerad ledig,
    saknar plats och inte återkommer.

    Andra program skriver sina egna loggrader i kalendern — lärarens
    automatiska synk mellan skol- och privatkalendern lägger «Synk: 7 nytt –
    se beskrivning» som en femminuterspunkt markerad ledig (2026-08-10). Det
    är ingen lektion, inget möte och inget prov, och ska inte bli en post att
    planera runt. Signaturen är formen, inte ordet «synk», så vilket program
    som helst fångas."""
    start, slut = h.get("start") or {}, h.get("end") or {}
    if start.get("date") or h.get("recurringEventId"):
        return False                        # heldagar och serier är inga notiser
    if h.get("transparency") != "transparent" or (h.get("location") or "").strip():
        return False
    langd = _langd(start.get("dateTime") or "", slut.get("dateTime") or "")
    return langd is not None and langd <= 10


# Ett prov i kalendern är en tid som ska HÅLLAS, inte ett möte att gå på:
# appen erbjuder att planera det, terminsvyn räknar det, och läraren vill se
# det i en egen färg. Ordgränserna är hela poängen — «Provteori (Zoom)» är en
# föreläsning och «Prövning» är något helt annat.
#
# Nationella provet skiljs ut som eget slag: det är inte lärarens att skriva,
# och «inte skrivet ännu» vore ett felaktigt påstående om det (klass.js och
# termin.js har alltid gjort samma skillnad, men på ordet «nationell» — och
# skolans egna NP-titlar skriver «NP MAT nivå 1c», inte «nationellt prov»).
_NP_ORD = re.compile(r"\b(np|nationell\w*\s+prov\w*)\b", re.IGNORECASE)
_PROV_ORD = re.compile(r"\b(prov|provet|proven|prover|omprov|delprov|provpass)\b",
                       re.IGNORECASE)
# Diagnosen söks som DEL av ordet, till skillnad från proven: skolan skriver
# «Matematikdiagnos åk 1», inte «diagnos i matematik». Ordgränser hade missat
# den helt.
_DIAGNOS_ORD = re.compile(r"diagnos", re.IGNORECASE)


def provslag(titel: str) -> str | None:
    """'np' | 'diagnos' | 'prov' | None för en kalenderrubrik.

    Diagnosen prövas före provet: «diagnostiskt prov» är en diagnos, och det
    är diagnosen som är det precisa ordet av de två."""
    t = titel or ""
    if _NP_ORD.search(t):
        return "np"
    if _DIAGNOS_ORD.search(t):
        return "diagnos"
    return "prov" if _PROV_ORD.search(t) else None


def _undantagsdagar(fran: str, till: str, veckodag: int, med_lektion: set[str],
                    lov: list[dict]) -> list[str]:
    """Veckodagarna mellan seriens första och sista instans som kalendern INTE
    har någon lektion på — loven borträknade, för de ritas redan som stängda.

    En inställd enstaka lektion är osynlig i ett mönster: appen ritade tre
    lektioner som inte fanns (Kaggdagen 3/9 och gymnasiemässan 9/10,
    2026-08-10). Kalendern visste, mönstret kunde inte bära det.

    Bara fram till sista instansen: efter den vet läsningen ingenting, och en
    tom framtid är inte samma sak som en inställd lektion."""
    if not fran or not till:
        return []
    ut: list[str] = []
    dag = date.fromisoformat(fran)
    stopp = date.fromisoformat(till)
    while dag <= stopp:
        if dag.isoweekday() == veckodag:
            iso = dag.isoformat()
            if iso not in med_lektion and not any(l["fran"] <= iso <= l["till"]
                                                  for l in lov):
                ut.append(iso)
        dag += timedelta(days=1)
    return ut


def _post(datum: str, tid: str, titel: str, klass: str) -> dict:
    """En kalenderpost i frontendens form. `slag` sätts bara när rubriken
    faktiskt säger något — en post utan slag är en post, inget annat."""
    post = {"datum": datum, "tid": tid, "titel": titel, "klass": klass}
    slag = provslag(titel)
    if slag:
        post["slag"] = slag
    return post


# ----------------------------------------------- lektionens eget innehåll --
# Sidorna och uppgifterna står i händelsens BESKRIVNING, och de gäller per
# LEKTIONSTILLFÄLLE: «s. 2–6 · uppg. 1101–1103» är den 17 augusti, inte varje
# måndag hela terminen. Veckoschemat kan inte bära dem — det är en rad per
# serie — så de går sin egen väg ut, se tolka_handelser["innehall"].
#
# INTEGRITET, och det är villkoret för att beskrivningen läses alls: allt
# UNDER avdelaren (———) är lärarens egna anteckningar om enskilda elever.
# Parsern skär bort den delen FÖRST och tittar bara på texten ovanför.
#
# Ovanför avdelaren får sedan 2026-08-18 också RUBRIKEN framför ett sidspann
# läsas och sparas — orden «Kubikrötter» i «Kubikrötter: s. 5–6 · uppg. …».
# Läraren bad om det själv, och skälet är att boken inte kan svara: avsnitt 1.1
# i Liber Ma 1c heter «Kvadratrötter och kubikrötter» och går över s. 2–6, så
# lektionen på s. 2–4 fick en rubrik som lovade dubbelt så mycket som läraren
# skrivit. Hennes egna ord är det enda som vet vilken halva det är.
#
# Gränsen är smal och ska förbli det: bara texten FÖRE ett sidspann på samma
# rad, ovanför avdelaren, kapad vid _RUBRIKTAK tecken. Raderna under avdelaren,
# rader utan sidspann och beskrivningen som helhet lagras aldrig — de är
# fortfarande lärarens anteckningar om enskilda elever.
_AVDELARE = re.compile(r"[—–\-_=]{3,}")
# «s. 2–6», «s 2-6», «sid. 12», «sidorna 40–48» — och den ensamma sidan «s. 7».
_SIDOR = re.compile(r"\bs(?:id(?:a|or|orna)?)?\.?\s*(\d{1,4})"
                    r"(?:\s*[–—-]\s*(\d{1,4}))?", re.IGNORECASE)
# Uppgiftslistan skrivs som den står i boken: «1101–1103, 1105–1119». Radslut
# avslutar den — nästa rad är en annan sorts anteckning («OBS! miniräknare»).
_UPPGIFTER = re.compile(r"\buppg(?:ift(?:er(?:na)?)?)?\.?[ \t]*(\d[\d ,;.\t–—-]*)",
                        re.IGNORECASE)


# Rubriken är en etikett, inte en anteckning. Taket finns för att en rad som
# svämmar över inte ska bli en väg att smuggla ut hela beskrivningen: det som
# står före sidspannet på en rad är i praktiken ett par ord.
_RUBRIKTAK = 60
# Ledtecknen läraren skiljer rubrik från sidor med. Tas bort från slutet, så att
# «Kubikrötter:» och «Kubikrötter –» båda blir «Kubikrötter».
_RUBRIKSKRAP = " 	:–—-·•,;."


def _rubrik(text: str) -> str:
    """Orden framför sidspannet på raden, städade — eller tom sträng.

    Bara sista raden räknas: står rubriken tre rader upp hör den till något
    annat. Ett inledande listtecken eller avsnittsnummer får stå kvar; det är
    lärarens sätt att skriva och säger något."""
    rad = str(text or "").splitlines()[-1] if str(text or "").strip() else ""
    # Uppgiftslistan och ett tidigare sidspann på samma rad är inte rubriker —
    # «s. 2–4 · uppg. 1101–1103 · s. 7–9» har en rubrik för det första spannet
    # (ingen) och ingen för det andra, inte «uppg. 1101–1103».
    rad = _SIDOR.sub(" ", _UPPGIFTER.sub(" ", rad))
    rubrik = rad.strip().strip(_RUBRIKSKRAP).strip()
    # En rubrik som bara är siffror eller skiljetecken är ingen rubrik — det är
    # resten av föregående spann («… 1116–1119 ·»).
    if not re.search(r"[^\W\d_]", rubrik, re.UNICODE):
        return ""
    return rubrik[:_RUBRIKTAK].strip(_RUBRIKSKRAP).strip()


def sidor_ur_beskrivning(description: str | None) -> dict:
    """{fran, till, uppg, delar} ur beskrivningens FÖRSTA del, eller {} när det
    inte står några sidor där. Ingen gissning: står det ingenting säger
    funktionen ingenting, och då gäller appens vanliga förval (klassprofilen).

    ALLA spann räknas, inte bara det första: en lektion som avslutar ett
    avsnitt och börjar nästa skrivs som två rader — «Kubikrötter: s. 5–6 ·
    uppg. 1116–1119» och «Potenser: s. 7–9 · uppg. 1201–1212» — och lektionens
    sidor är hela sträckan, uppgifterna båda listorna.

    `delar` bär spannen var för sig med lärarens egen rubrik framför var och
    ett. Sammanslagningen till fran/till står kvar: allt som räknar sidor
    (provets underlag, klassprofilens takt) ska fortsätta se lektionen som en
    sträcka."""
    text = _AVDELARE.split(str(description or ""), 1)[0]
    traffar = list(_SIDOR.finditer(text))
    if not traffar:
        return {}                       # ingen sida → inget innehåll, punkt
    delar = []
    for n, m in enumerate(traffar):
        f = int(m.group(1))
        t = int(m.group(2)) if m.group(2) else f
        # Uppgifterna som står EFTER det här spannet men före nästa hör till det.
        slut = traffar[n + 1].start() if n + 1 < len(traffar) else len(text)
        del_uppg = _uppgifterna(text[m.end():slut])
        d = {"fran": f, "till": max(f, t)}
        rubrik = _rubrik(text[traffar[n - 1].end() if n else 0:m.start()])
        if rubrik:
            d["rubrik"] = rubrik
        if del_uppg:
            d["uppg"] = del_uppg
        delar.append(d)
    fran = min(d["fran"] for d in delar)
    ut = {"fran": fran, "till": max(fran, max(d["till"] for d in delar)),
          "delar": delar}
    listor = [d["uppg"] for d in delar if d.get("uppg")]
    if listor:
        ut["uppg"] = ", ".join(listor)
    return ut


def _uppgifterna(text: str) -> str:
    """Uppgiftslistorna i en textbit, i appens form. Tom sträng när ingen står."""
    listor = []
    for u in _UPPGIFTER.finditer(text):
        # En form på spannen, samma som resten av appen skriver dem.
        lista = re.sub(r"\s*[–—-]\s*", "–", u.group(1).strip())
        lista = re.sub(r"\s*,\s*", ", ", lista).strip(" ,;.–")
        if lista:
            listor.append(lista)
    return ", ".join(listor)


# Verktygen som avgör provets upplägg. «Del B + Del C» finns för att det finns
# en gräns mellan det som ska gå utan hjälpmedel och det som får göras med dem —
# och vilken sida klassen har arbetat på står ofta i lektionens beskrivning
# («ta med datorn», «GeoGebra-övning», «miniräknare behövs»).
#
# Två lägen och inte fem: 'dator' väger tyngst (dator och GeoGebra öppnar hela
# verktygslådan), 'raknare' är den lättare varianten. Tom sträng betyder att
# raden ÄR läst och inget nämndes — se _HJALPMEDEL_MIGRATION i app/db.py om
# varför tomt och osynkat måste vara två olika svar.
#
# Böjningarna är svenska och gemena: «datorn», «datorer», «miniräknaren»,
# «räknare». Ordstammarna räcker, och ordgränsen framför hindrar att
# «kalkylatorn» blir en dator. GeoGebra fångas separat: programnamnet säger
# «dator» utan att ordet dator står där.
_DATORORD = re.compile(r"\b(dator\w*|geogebra|laptop\w*|chromebook\w*)",
                       re.IGNORECASE)
_RAKNARORD = re.compile(r"\b(mini)?r[aä]knar\w*", re.IGNORECASE)


def hjalpmedel_ur_text(description: str | None, titel: str | None = None) -> str:
    """'dator' | 'raknare' | '' — vilka verktyg lektionen nämner.

    Läser SAMMA första del av beskrivningen som sidor_ur_beskrivning: allt under
    avdelaren är lärarens anteckningar om enskilda elever och rörs aldrig.
    Rubriken läses också — «Ma1c NA26F · GeoGebra» säger saken i titeln.

    Det som kommer ut är en av tre konstanter. Ingen fri text lämnar den här
    funktionen, och det är villkoret för att beskrivningen läses alls."""
    text = _AVDELARE.split(str(description or ""), 1)[0] + " " + str(titel or "")
    if _DATORORD.search(text):
        return "dator"
    if _RAKNARORD.search(text):
        return "raknare"
    return ""


# ------------------------------------------ provets centrala innehåll (v22) --
# Läraren skriver i PROVETS beskrivning vilket centralt innehåll provet berör.
# Det är samma punkter som gy-väljaren i planeringen håller (Gy25), och när hon
# sedan skapar provet i appen ska de redan vara ikryssade — hon har ju redan
# svarat på frågan, i kalendern, en gång.
#
# INTEGRITETSREGELN GÄLLER OFÖRÄNDRAD (se raden ~505): bara texten ÖVER
# avdelaren läses, och det som lagras är en lista KODER ur en känd punktlista —
# aldrig lärarens egna ord. En rad som inte känns igen lämnar inget spår mer än
# att den räknas.
#
# INGEN MODELL i synken. Synken körs varje gång läraren trycker på knappen, ska
# vara gratis och fungera utan nät; en språkmodell här hade gjort kalenderns
# innehåll till en kostnad per läsning. Textmatchning räcker, och gränsen sätts
# hellre för högt: ett förval med FÄRRE punkter rättar läraren med ett klick,
# ett förval med FEL punkter kan hon inte se att hon behöver rätta.
_CI_KOD = re.compile(r"\bG25-[A-Z0-9]{2,8}-[A-ZÅÄÖ]{2,6}-\d{1,2}\b", re.IGNORECASE)
# Radens administrativa svans skalas bort innan den vägs: «Kap 3 · s. 40–48 ·
# uppg. 3101–3130» säger ingenting om centralt innehåll, och en rad som bara
# består av sådant ska inte räknas som «kändes inte igen».
_KAPITEL = re.compile(r"\bkap(?:itel)?\.?\s*[\d.]+\s*(?:och\s*[\d.]+)?", re.IGNORECASE)
_PUNKTLISTA = re.compile(r"^\s*[-*•·–—>•]+\s*")
# En rad som är kortare än så säger för lite för att vägas mot en punktlista.
_MINSTA_RAD = 6
# … och en rad som ska matchas mot Skolverkets ORDAGRANNA text måste vara lång
# nog att inte råka ligga i den: läraren som klistrar in punkten skriver hela
# meningen, den som skriver «samband» gör det inte.
_MINSTA_TEXTRAD = 30


def _normalisera(text: str | None) -> str:
    """Gemener, siffror och bokstäver, ett mellanslag mellan orden. Allt annat
    är skiljetecken läraren och Skolverket sätter olika."""
    return " ".join(re.sub(r"[^0-9a-zåäöéèü]+", " ", str(text or "").lower()).split())


def _fras_i(kort: str, lang: str) -> bool:
    """Står `kort` som en HEL ordföljd i `lang`? Ordgränserna är hela poängen:
    «linjära ekvationer» får inte hittas i «linjära ekvationssystem», som är en
    annan punkt på en annan nivå."""
    if not kort or not lang:
        return False
    return f" {lang} ".find(f" {kort} ") >= 0


@lru_cache(maxsize=1)
def _gy25_nivaer() -> tuple[tuple[str, tuple[str, ...], tuple[tuple[str, str, str], ...]], ...]:
    """Gy25-nivåerna som matchningen behöver dem:
    (niva_id, kursens namnformer normaliserade, ((kod, kort, text) …)).

    Punkterna kommer ur app/data/centralt_innehall/gy25_*.json via course_data —
    SAMMA källa som seedas in i `course_content` och som gy.js speglas ur. Aldrig
    ur gy.js: den filen är en generad kopia för webbläsaren, och att läsa en
    spegel är att skaffa sig en andra sanning."""
    ut = []
    for n in course_data.gy_nivaer():
        # Kursen står i lärarens schema i vilken som helst av sina former —
        # «Ma2c» på en handskriven rad, «Matematik 2c» på en gammal, «Matematik,
        # nivå 2c» ur kursregistret, kurskoden i en importfil.
        namn = tuple(sorted({_normalisera(x) for x in (
            n["kurs"], n["kurskod"], n["fullnamn"], n["gammal"],
            f'{n["amne"]} {n["niva"]}') if x}))
        punkter = tuple((p["kod"], _normalisera(p["kort"]), _normalisera(p["text"]))
                        for o in n["omraden"] for p in o["punkter"])
        ut.append((n["niva_id"], namn, punkter))
    return tuple(ut)


@lru_cache(maxsize=64)
def _kursens_former(kurs: str) -> tuple[str, ...]:
    """Namnformerna en kurs skrivs i — «Ma1c», «Matematik 1c», kurskoden — ur
    Gy25-registret, plus varianten med mellanslag före nivån («Ma 1c»), som
    skolans kalender skriver den. Tom när kursen inte finns i registret."""
    sokt = _normalisera(kurs)
    for _, namn, _ in _gy25_nivaer():
        if sokt in namn:
            return tuple(sorted(set(namn) | {
                re.sub(r"(?<=[a-zåäö])(?=\d)", " ", f) for f in namn}))
    return ()


def ar_rubrik_inte_kurs(namn: str, klasser) -> bool:
    """Ar "TE26A: Genomgang av prov 4" en KURS? Nej - det ar rubriken pa en
    lektion, och den hamnade i kursfaltet for att Claudes bedomning av en omdopt
    instans togs rakt av (se kursarvet nedan).

    Det gjorde felet sjalvforstarkande: kursen skrevs in i courses, kom tillbaka
    i `kurser` vid nasta synk, och da matchade `_kurs_i_titeln` rubriken mot sig
    sjalv - alltsa steg ETT i arvet, det som ska vara lararens egna ord. En hel
    termins fredagar for TE26A stod som kursen "TE26A: Genomgang av prov 4".

    Formen ar lararens egen: klassens namn, kolon, vad timmen ar. Riktiga kurser
    heter "Matematik, niva 1c" och kan inte borja med ett klassnamn och kolon."""
    n = (namn or "").strip().lower()
    return bool(n) and any(n.startswith(f"{k.strip().lower()}:")
                           for k in (klasser or []) if (k or "").strip())


@lru_cache(maxsize=4096)
def _kurs_i_titeln(titel: str, kurser: tuple[str, ...]) -> str:
    """Kursen som RUBRIKEN själv bär, i vilken som helst av sina namnformer:
    «Ma 1c · TE26A · B203» bär Matematik, nivå 1c fast appens kursnamn aldrig
    står där. Tom när rubriken inte säger något — det här är lärarens egna ord,
    inte en gissning, och skiljer sig därmed från ett kalenderbeslut."""
    tl = (titel or "").lower()
    ntitel = f" {_normalisera(titel)} "
    for k in kurser:
        if k and (k.lower() in tl
                  or any(f" {f} " in ntitel for f in _kursens_former(k))):
            return k
    return ""


def _nivaer_for(kurser) -> list[tuple[str, tuple[tuple[str, str, str], ...]]]:
    """Nivåerna gruppen faktiskt läser. Utan kurser blir listan tom och
    ingenting matchas — appen gissar hellre ingen nivå än fel nivå."""
    sokta = {_normalisera(k) for k in (kurser or []) if str(k or "").strip()}
    return [(niva_id, punkter) for niva_id, namn, punkter in _gy25_nivaer()
            if sokta & set(namn)]


def _radens_karna(rad: str) -> str:
    """Raden utan sidhänvisningar, uppgiftslistor, kapitelnummer och
    listprickar — det som är kvar är det raden PÅSTÅR."""
    kvar = _PUNKTLISTA.sub("", str(rad or ""))
    kvar = _SIDOR.sub(" ", _UPPGIFTER.sub(" ", _KAPITEL.sub(" ", kvar)))
    return _normalisera(kvar)


def centralt_innehall_ur_text(description: str | None, titel: str | None,
                              kurser) -> tuple[list[str], int]:
    """(koder, okända rader) — vilka Gy25-punkter provets beskrivning nämner.

    Tre vägar in, i fallande säkerhet:
      1. KODEN själv (G25-M2C-ALG-4) — identitet, ingen tolkning alls. Läses
         också ur rubriken, som är en rad läraren skriver lika medvetet.
      2. Punktens KORTA etikett som en hel ordföljd, åt endera hållet:
         «Andragradsekvationer» i raden, eller raden i «Potenser och
         potensekvationer». Det är etiketten läraren själv ser i väljaren.
      3. Skolverkets ORDAGRANNA punkttext, när raden ligger inuti den. Den som
         klistrar in ämnesplanen ska bli förstådd.

    Tvetydighet tystar — men BESKRIVNINGEN får avgöra först. En grupp läser ofta
    två nivåer samma läsår (NA26F har både 1c och 2c i schemat), och fem punkter
    heter likadant på båda: «Programmering», «Problemlösning», «Digitala
    verktyg», «Matematiska modeller», «Matematikens historia». En sådan rad kan
    inte avgöras för sig. Har provets ÖVRIGA rader entydigt pekat ut EN nivå är
    den däremot avgjord av texten själv, och då läses den tvetydiga raden i den
    nivån. Pekar de åt olika håll, eller åt inget håll alls, räknas raden som
    okänd i stället för att gissas.

    Okända rader räknas bara när NÅGOT kändes igen. En beskrivning där ingenting
    matchar handlar om något annat än centralt innehåll («Sal E107, ta med
    räknare»), och att rapportera den som «5 rader kändes inte igen» hade varit
    att klaga på en text som aldrig lovade något."""
    nivaer = _nivaer_for(kurser)
    if not nivaer:
        return [], 0
    text = _AVDELARE.split(str(description or ""), 1)[0]
    kodens_niva = {kod: niva_id for niva_id, punkter in nivaer for kod, _, _ in punkter}

    def ur_koder(rad: str) -> list[str]:
        return [m.group(0).upper() for m in _CI_KOD.finditer(str(rad or ""))
                if m.group(0).upper() in kodens_niva]

    # Raderna vägs var för sig först: {niva_id: [kod, …]} per rad. Sedan — och
    # först då — avgörs de tvetydiga, för det är hela beskrivningen som vet
    # vilken nivå provet ligger på.
    rader: list[dict[str, list[str]]] = []
    # Rubriken bidrar med koder men räknas aldrig som en okänd rad: den är en
    # rubrik («NA26F: PROV 1 (kap 1 och 2)»), inte ett påstående om innehåll.
    for kod in ur_koder(titel):
        rader.append({kodens_niva[kod]: [kod]})
    for rad in text.splitlines():
        traffar = ur_koder(rad)
        if traffar:                     # koden bär sin nivå i sig — aldrig tvetydig
            for kod in traffar:
                rader.append({kodens_niva[kod]: [kod]})
            continue
        karna = _radens_karna(rad)
        if len(karna) < _MINSTA_RAD:
            continue                    # sidor, uppgifter, en ensam kapitelsiffra
        # «Ta med räknaren» är en fråga synken redan besvarar på annat håll
        # (hjalpmedel_ur_text) och inget påstående om centralt innehåll — raden
        # ska varken matchas eller anmälas som obegriplig.
        if hjalpmedel_ur_text(rad):
            continue
        per_niva: dict[str, list[str]] = {}
        for niva_id, punkter in nivaer:
            for kod, kort, ptext in punkter:
                if (_fras_i(kort, karna) or _fras_i(karna, kort)
                        or (len(karna) >= _MINSTA_TEXTRAD and _fras_i(karna, ptext))):
                    per_niva.setdefault(niva_id, []).append(kod)
        rader.append(per_niva)

    # Nivån beskrivningen SJÄLV pekat ut: den som entydiga rader gav träff i. Är
    # de fler än en vet vi bara att provet spänner över två nivåer, och då är
    # ingen tvetydig rad avgjord av något.
    sakra = {next(iter(p)) for p in rader if len(p) == 1}
    avgorande = next(iter(sakra)) if len(sakra) == 1 else None

    koder: list[str] = []
    okanda = 0
    for per_niva in rader:
        valda = (next(iter(per_niva.values())) if len(per_niva) == 1
                 else per_niva.get(avgorande) if avgorande else None)
        if not valda:
            okanda += 1                 # inget alls, eller flera nivåer på en gång
            continue
        for kod in valda:
            if kod not in koder:
                koder.append(kod)
    return koder, (okanda if koder else 0)


def serienyckel(h: dict) -> str:
    """Identiteten på en SERIE, inte på en instans: samma titel, samma slag av
    händelse. Mentorstiden varje måndag hela läsåret är en nyckel, inte
    fyrtio — det är den som bedömningen cachas på."""
    titel = " ".join((h.get("summary") or "").lower().split())
    heldag = "heldag" if (h.get("start") or {}).get("date") else "tid"
    ater = "serie" if h.get("recurringEventId") else "enstaka"
    return f"{titel}|{heldag}|{ater}"


def tolka_handelser(handelser: list[dict], klasser: list[str] | None = None,
                    kurser: list[str] | None = None,
                    beslut: dict[str, dict] | None = None,
                    idag: str | None = None,
                    fonster_till: str | None = None,
                    schema_nu: list[dict] | None = None) -> dict:
    """Ren funktion: Google-händelser in, {schema, lov, poster, innehall,
    osakra} ut i exakt de former frontendens window.Kalender håller. Testbar
    utan Google.

    `innehall` är sidorna och uppgifterna som står på EN lektion en viss dag
    (sidor_ur_beskrivning) — schemaraden är serien och kan inte bära dem.

    `osakra` är de händelser reglerna PLACERADE men inte är säkra på — en
    heldag utan lovord, en återkommande lektionstid utan igenkänd kurs. De
    ligger kvar där reglerna satte dem (inget försvinner om ingen frågar
    vidare) och skickas till Claude i ett andra steg, se app/kalender_ai.py.

    `schema_nu` är schemat appen redan har. Det används för att känna igen
    lektioner vars rubrik säger ämnet i stället för kursen — se rutorna nedan —
    och som kurskälla när ett kalenderbeslut bara gissat kursen. Aldrig för att
    hitta på rader: en ruta som inte har någon händelse i kalendern längre
    försvinner ur svaret precis som förut."""
    klasser = sorted(klasser or [], key=len, reverse=True)
    # Rubriker som en gang skrivits in som kurser far aldrig rakna som kurser
    # igen - varken har, i ankarserierna eller i rutorna (ar_rubrik_inte_kurs).
    kurser = sorted((k for k in (kurser or []) if not ar_rubrik_inte_kurs(k, klasser)),
                    key=len, reverse=True)
    # Rutorna i lärarens schema: (veckodag, klockslag, klass) → raderna som
    # står där, med sina datumintervall. Samma ruta kan bära FLERA serier —
    # skolans kalender lägger nästa läsårs kurs i samma tid (TE26A läser 1c nu
    # och 2c från 2027, schema_lektioner har båda raderna) — och då är det
    # intervallet som avgör vilken serie en lektion faktiskt träffar. En platt
    # ruta → kurs hade låtit sista raden vinna, och varje 1c-lektion fick 2c.
    # Tomma rutor hoppas över — en rad utan kurs säger ingenting.
    rutor: dict[tuple, list[dict]] = {}
    for r in (schema_nu or []):
        if ((r.get("kurs") or "").strip()
                and not ar_rubrik_inte_kurs(r.get("kurs"), klasser)):
            rutor.setdefault((int(r.get("dag") or 0), (r.get("tid") or "").strip(),
                              (r.get("klass") or "").strip()), []).append(r)

    def tacker(r: dict, datum: str) -> bool:
        """Ligger datumet i radens intervall? Tomt fran/till är öppet åt det
        hållet — ett handskrivet schema har inga datum alls (db.list_schema)."""
        return ((r.get("fran") or "") <= datum
                and (not (r.get("till") or "") or datum <= r["till"]))

    def rutans_kurs(dag: int, tid: str, klass: str, datum: str) -> str:
        """Kursen i rutan DEN dagen: första raden vars intervall täcker datumet,
        i schemats egen ordning."""
        return next(((r.get("kurs") or "").strip()
                     for r in rutor.get((dag, tid, klass), []) if tacker(r, datum)),
                    "")

    # ANKARSERIERNA: rubriker som SJÄLVA bär kursen — «Ma 1c · TE26A · B203»,
    # skolschemats egen serie — lägger fast vilken kurs som läses i en ruta
    # under vilka veckor. Det är dem de omdöpta instanserna («TE26A: Räkna
    # ifatt» — samma serie, ny rubrik varje vecka och därmed en egen serienyckel)
    # ärver sin kurs av: Claudes bedömning av en sådan rubrik är en gissning,
    # och den gissade «nivå 2c» på klasser som läser 1c (2026-08-17). Kursen i
    # titeln räknas, aldrig beslutet — annars vore ankaret sin egen cirkel.
    ankare: dict[tuple, dict[str, list[str]]] = {}
    ankare_klass: dict[str, dict[str, list[str]]] = {}
    kurstupel = tuple(kurser)
    for h in handelser or []:
        s0 = ((h.get("start") or {}).get("dateTime") or "")
        if not h.get("recurringEventId") or not s0:
            continue
        titel0 = (h.get("summary") or "").strip()
        kurs0 = _kurs_i_titeln(titel0, kurstupel)
        klass0 = _klass_och_kurs(titel0, klasser, kurser)[0] if kurs0 else ""
        if not kurs0 or not klass0:
            continue
        try:
            dag0 = date.fromisoformat(s0[:10]).isoweekday()
        except ValueError:
            continue
        tid0 = _tid(s0, (h.get("end") or {}).get("dateTime") or "")
        ankare.setdefault((dag0, tid0, klass0), {}).setdefault(kurs0, []).append(s0[:10])
        ankare_klass.setdefault(klass0, {}).setdefault(kurs0, []).append(s0[:10])

    def _tackande(kandidater: dict[str, list[str]], datum: str) -> str:
        """Kursen vars ankarinstanser omsluter datumet. Omsluter två
        (läsårsskarven, där nästa kurs börjar innan repetitionen tagit slut)
        avgör den närmaste instansen."""
        traff = {k: d for k, d in kandidater.items() if min(d) <= datum <= max(d)}
        if len(traff) <= 1:
            return next(iter(traff), "")
        dat = date.fromisoformat(datum)
        return min(traff, key=lambda k: min(
            abs((dat - date.fromisoformat(x)).days) for x in traff[k]))

    def ankarkurs(dag: int, tid: str, klass: str, datum: str) -> str:
        """Rutans egna ankare först; annars klassens som helhet — rutan kan stå
        utan ankare när varenda instans i den är omdöpt, men klassen läser en
        kurs i taget och de andra rutornas ankare vet vilken."""
        return (_tackande(ankare.get((dag, tid, klass)) or {}, datum)
                or _tackande(ankare_klass.get(klass) or {}, datum))
    schema: list[dict] = []
    sedda: set[tuple] = set()
    # FÖRSTA och SISTA instansen per schemarad. Ett veckoschema utan datum är
    # ett påstående om alla veckor som finns, och det stämmer aldrig: serierna
    # börjar när terminen börjar och slutar när kursen slutar. Utan det här
    # ritade appen höstens lektioner på uppstartsveckan i augusti — läraren
    # hade möten, inte lektioner — och vårterminens serier hamnade i höstens
    # vecka bara för att läsfönstret går 240 dagar bakåt (read_schema).
    forst: dict[tuple, str] = {}
    sist: dict[tuple, str] = {}
    # Varje dag serien FAKTISKT ligger på. Skillnaden mot veckodagarna i
    # spannet är de inställda lektionerna (_undantagsdagar).
    dagar_med: dict[tuple, set[str]] = {}
    idag = idag or date.today().isoformat()
    lov: list[dict] = []
    poster: list[dict] = []
    osakra: dict[str, dict] = {}
    # Sidorna och uppgifterna PER LEKTIONSTILLFÄLLE, nyckel (datum, tid, klass,
    # kurs). Skild från schemat med flit: schemaraden är serien, den här är
    # dagen. Bara lektioner hamnar här, och bara de som faktiskt bär sidor.
    innehall: dict[tuple, dict] = {}
    # Räknas och rapporteras — den som undrar vart notiserna tog vägen ska få
    # svar av synken i stället för att leta.
    notiser = 0
    # Provens beskrivningar, i minnet och bara under den här funktionen: det
    # centrala innehållet kan inte avgöras förrän vi vet vilka KURSER klassen
    # läser, och det vet vi först när schemat är genomgånget. Posten själv (en
    # muterbar dict som redan ligger i `poster`) fylls i efterhand, se nedan.
    provrader: list[tuple[dict, str, str, str]] = []
    # Klassens kurser, som de kommer ur veckoschemat. Motsvarar group_id →
    # course_id i basen. Rutorna räknas in först vid uppslag, per DATUM —
    # 2c-serien som börjar nästa läsår ska inte ge höstens 1c-prov 2c-punkter.
    kurser_per_klass: dict[str, set[str]] = {}

    def klassens_kurser(klass: str, datum: str) -> set[str]:
        ur_rutorna = {(r.get("kurs") or "").strip()
                      for (_, _, k), rader in rutor.items() if k == klass
                      for r in rader if tacker(r, datum)}
        return (kurser_per_klass.get(klass) or set()) | ur_rutorna

    def notera_post(h: dict, datum: str, tid: str, titel: str, klass: str) -> None:
        """Lägg posten i listan och kom ihåg provens beskrivningar."""
        p = _post(datum, tid, titel, klass)
        poster.append(p)
        # Nationella provet är inte lärarens att skriva och får inget förval.
        if p.get("slag") in ("prov", "diagnos"):
            provrader.append((p, h.get("description") or "", titel, klass))

    def notera_innehall(h: dict, datum: str, tid: str, klass: str, kurs: str) -> None:
        sidor = sidor_ur_beskrivning(h.get("description"))
        if not sidor:
            return                          # ingen sida skriven → inget att bära
        # Flaggan sätts ALLTID när raden skapas, också när den blir tom: tom
        # sträng är svaret «läst, inget nämndes», och det är ett annat svar än
        # NULL (raden har aldrig lästs med hjälpmedelsögon). Provets förval
        # skiljer på dem, se kalender.js planeringen.
        innehall[(datum, tid, klass, kurs)] = dict(
            {"datum": datum, "tid": tid, "klass": klass, "kurs": kurs,
             "hjalpmedel": hjalpmedel_ur_text(h.get("description"),
                                              h.get("summary"))},
            **sidor)

    def osaker(h: dict, titel: str, varfor: str, **extra) -> None:
        nyckel = serienyckel(h)
        if nyckel in osakra:
            return                          # en serie frågas en gång
        start, slut = h.get("start") or {}, h.get("end") or {}
        osakra[nyckel] = dict({
            "nyckel": nyckel, "titel": titel, "varfor": varfor,
            "heldag": bool(start.get("date")),
            "aterkommande": bool(h.get("recurringEventId")),
            "fran": start.get("date") or (start.get("dateTime") or "")[:10],
            "till": slut.get("date") or (slut.get("dateTime") or "")[:10],
            "tid": "" if start.get("date") else _tid(start.get("dateTime") or "",
                                                    slut.get("dateTime") or ""),
            "plats": (h.get("location") or "").strip(),
        }, **extra)

    for h in handelser or []:
        titel = (h.get("summary") or "").strip()
        if not titel:
            continue
        if ar_notis(h):
            notiser += 1
            continue
        start, slut = h.get("start") or {}, h.get("end") or {}
        # Ett fattat beslut går före reglerna. Det är ANDRA passet: samma rena
        # funktion körs om med Claudes svar på de osäkra serierna, så det finns
        # bara EN väg som placerar en händelse i veckan.
        b = (beslut or {}).get(serienyckel(h))
        if b:
            slag = b.get("slag")
            if slag == "ignorera":
                continue
            if slag in ("lov", "dag", "uppehall"):
                fran = start.get("date") or (start.get("dateTime") or "")[:10]
                if not fran:
                    continue
                rat = slut.get("date")
                try:
                    till = ((date.fromisoformat(rat) - timedelta(days=1)).isoformat()
                            if rat else (slut.get("dateTime") or fran)[:10])
                except ValueError:
                    till = fran
                lov.append({"fran": fran, "till": max(fran, till),
                            "namn": b.get("namn") or titel, "typ": slag})
                continue
            if slag == "lektion" and h.get("recurringEventId") and start.get("dateTime"):
                s2, e2 = start["dateTime"], slut.get("dateTime") or ""
                try:
                    dag = date.fromisoformat(s2[:10]).isoweekday()
                except ValueError:
                    continue
                bklass = (b.get("klass") or "").strip()
                # Beslutets KURS är en gissning när rubriken inte bär den själv
                # («TE26A: Räkna ifatt» säger ingen kurs, och Claude gissade
                # 2c på en klass som läser 1c). Lektionen ärver därför kursen i
                # fallande säkerhet: lärarens egen rubrik, ankarserien som
                # täcker instansens datum, schemarutan som täcker det — och
                # först när ingen av dem vet något står gissningen kvar.
                # Sista steget ar Claudes gissning, och den far bara vara en
                # KAND kurs. Svarade han med handelsens egen rubrik skrevs den
                # in i courses och blev en kurs - se ar_rubrik_inte_kurs.
                bgissning = (b.get("kurs") or "").strip()
                bkurs = (_kurs_i_titeln(titel, kurstupel)
                         or ankarkurs(dag, _tid(s2, e2), bklass, s2[:10])
                         or rutans_kurs(dag, _tid(s2, e2), bklass, s2[:10])
                         or (bgissning if bgissning in kurstupel else ""))
                rad = {"dag": dag, "tid": _tid(s2, e2), "kurs": bkurs,
                       "klass": bklass,
                       "sal": (h.get("location") or "").strip()}
                if not rad["klass"] or not rad["kurs"]:
                    continue               # en lektion utan klass och kurs är ingen
                nyckel = (rad["dag"], rad["tid"], rad["klass"], rad["kurs"], rad["sal"])
                forst[nyckel] = min(forst.get(nyckel, "9999"), s2[:10])
                sist[nyckel] = max(sist.get(nyckel, ""), s2[:10])
                dagar_med.setdefault(nyckel, set()).add(s2[:10])
                notera_innehall(h, s2[:10], rad["tid"], rad["klass"], rad["kurs"])
                kurser_per_klass.setdefault(rad["klass"], set()).add(rad["kurs"])
                if nyckel not in sedda:
                    sedda.add(nyckel)
                    schema.append(rad)
                continue
            # En post kan vara heldag: «Öppet hus» stänger inte skolan men står
            # i kalendern. Utan den här grenen tappades den helt — gränssnittet
            # skriver «Hela dagen» när tiden är tom (klass.js).
            datum = start.get("date") or (start.get("dateTime") or "")[:10]
            if datum:
                notera_post(
                    h, datum,
                    "" if start.get("date")
                    else _tid(start["dateTime"], slut.get("dateTime") or ""),
                    titel, _klass_och_kurs(titel, klasser, kurser)[0])
            continue
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
            else:
                # «APL-vecka», «Skolavslutning åk 3», «Friluftsdag» — heldagar
                # som KAN stänga skolan men inte säger det med ett ord vi känner.
                # Reglerna låter dem vara; Claude får titta.
                osaker(h, titel, "heldag utan känt lovord")
            continue
        s, e = start.get("dateTime") or "", slut.get("dateTime") or ""
        if not s:
            continue
        datum = s[:10]
        klass, kurs = _klass_och_kurs(titel, klasser, kurser)
        # En återkommande händelse med en klass i titeln är en lektion — MEN
        # bara om det också står en kurs appen känner igen. Mentorstiden och
        # klassens utvecklingssamtal återkommer varje vecka och bär klassens
        # namn, och de är inte lektioner att planera. Utan en kurslista att
        # jämföra mot (tester, en tom installation) räcker klassen.
        lektion = bool(h.get("recurringEventId") and klass
                       and (not kurser or any(k.lower() in titel.lower() for k in kurser)))
        try:
            veckodag = date.fromisoformat(datum).isoweekday()
        except ValueError:
            veckodag = 0
        # Läraren som skriver ämnet i rubriken — «NA26F: Kvadratrötter och
        # kubikrötter» — får aldrig med kursnamnet, och föll därför ut som
        # osäker: en fråga till modellen per lektion, varje synk, och aldrig en
        # cacheträff eftersom rubriken byts varje vecka. Men platsen är känd.
        # Ligger händelsen på en tid som REDAN står i lärarens schema (samma
        # veckodag, samma klockslag, samma klass) och beskrivningen bär sidor,
        # då är den lektionen i den rutan och kursen är rutans kurs. Bägge
        # villkoren behövs: mentorstiden ligger också i schemat hos den som lagt
        # in den, men den har inga sidor.
        if not lektion and h.get("recurringEventId") and klass and veckodag:
            rutan = (ankarkurs(veckodag, _tid(s, e), klass, datum)
                     or rutans_kurs(veckodag, _tid(s, e), klass, datum))
            if rutan and sidor_ur_beskrivning(h.get("description")):
                lektion, kurs = True, rutan
        if lektion:
            dag = veckodag
            if not dag:
                continue
            rad = {"dag": dag, "tid": _tid(s, e), "kurs": kurs, "klass": klass,
                   "sal": (h.get("location") or "").strip()}
            nyckel = (rad["dag"], rad["tid"], rad["klass"], rad["kurs"], rad["sal"])
            forst[nyckel] = min(forst.get(nyckel, "9999"), datum)
            sist[nyckel] = max(sist.get(nyckel, ""), datum)
            dagar_med.setdefault(nyckel, set()).add(datum)
            notera_innehall(h, datum, rad["tid"], rad["klass"], rad["kurs"])
            kurser_per_klass.setdefault(rad["klass"], set()).add(rad["kurs"])
            if nyckel not in sedda:                 # samma vecka, många instanser
                sedda.add(nyckel)
                schema.append(rad)
            continue
        notera_post(h, datum, _tid(s, e), titel, klass)
        # En återkommande tidsatt händelse som INTE blev en lektion är den
        # osäkraste sortens gissning: «Ma2c NA25 halvklass A» är en lektion med
        # en kursstavning vi inte känner, «Mentorstid NA25» är det inte.
        if h.get("recurringEventId"):
            osaker(h, titel, "återkommande men ingen igenkänd kurs",
                   klass=klass, kurs=kurs)
    # Bara serier som fortfarande pågår: sista instansen i läsfönstret ligger
    # idag eller senare.
    schema = [r for r in schema
              if sist.get((r["dag"], r["tid"], r["klass"], r["kurs"], r["sal"]), "") >= idag]
    # Serien vars sista instans ligger vid fönstrets kant fortsätter bortom det
    # vi läst — då är slutet OKÄNT och inte satt. Annars hade veckovyn tömt sig
    # själv sju månader fram bara för att läsningen tog slut där.
    kant = ((date.fromisoformat(fonster_till) - timedelta(days=14)).isoformat()
            if fonster_till else "")
    for r in schema:
        n = (r["dag"], r["tid"], r["klass"], r["kurs"], r["sal"])
        dagar = dagar_med.get(n) or set()
        r["fran"] = forst.get(n, "")
        slut = sist.get(n, "")
        # Öppet slut bara för en RIKTIG serie. En enstaka flyttad lektion som
        # råkar landa vid fönstrets kant är ingen serie, och skulle annars
        # ritas varje vecka därefter.
        r["till"] = "" if kant and slut >= kant and len(dagar) > 1 else slut
        r["undantag"] = _undantagsdagar(r["fran"], slut, r["dag"], dagar, lov)
    schema.sort(key=lambda r: (r["dag"], r["tid"], r["klass"]))
    lov.sort(key=lambda p: (p["fran"], p["till"]))
    # Provens centrala innehåll, sist av allt: först nu vet vi vilka kurser
    # klassen läser, och punktlistan hör till NIVÅN — ett prov i 2c ska aldrig
    # kunna förvälja en punkt ur 1c bara för att orden liknar varandra.
    #
    # `ci` sätts på VARJE prov och diagnos, också när ingenting kändes igen: tom
    # lista är svaret «beskrivningen är läst, den nämnde inget centralt
    # innehåll», och det är ett annat svar än att posten aldrig lästs alls (se
    # _PROVETS_CI_MIGRATION i app/db.py — samma NULL/''-skillnad som
    # hjälpmedlen).
    for post, beskrivning, provtitel, klass in provrader:
        koder, okanda = centralt_innehall_ur_text(
            beskrivning, provtitel, klassens_kurser(klass, post["datum"]))
        post["ci"] = koder
        if okanda:
            post["ci_okant"] = okanda
    poster.sort(key=lambda p: (p["datum"], p["tid"]))
    return {"schema": schema, "lov": lov, "poster": poster, "notiser": notiser,
            "innehall": sorted(innehall.values(),
                               key=lambda i: (i["datum"], i["tid"], i["klass"])),
            "osakra": sorted(osakra.values(), key=lambda o: o["titel"])}


def list_events(base_dir: Path, fran: str, till: str) -> list[dict]:
    """Händelser i den valda kalendern mellan två ISO-datum (vald_kalender).
    singleEvents=True gör att återkommande serier expanderas till instanser —
    varje instans bär recurringEventId, som är det som avslöjar veckoschemat."""
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
            calendarId=vald_kalender(base_dir), singleEvents=True, orderBy="startTime",
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
    """Lägg ut veckoschemat, de återkommande posterna och loven i den valda
    kalendern — samma som synken läser. Returnerar {skapade, fel} eller
    {error}."""
    creds = _load_creds(base_dir)
    if creds is None:
        return {"error": status(base_dir).get("hint")
                or "Inte ansluten till Google Kalender."}
    kalender = vald_kalender(base_dir)
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
            service.events().insert(calendarId=kalender, body=body).execute()
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
            service.events().insert(calendarId=kalender, body={
                "summary": p.get("namn") or "Lov",
                "start": {"date": p["fran"]}, "end": {"date": slut},
            }).execute()
            skapade += 1
        except Exception as exc:
            fel.append(f"{p.get('namn')}: {exc}")
    return {"skapade": skapade, "fel": fel}


def read_schema(base_dir: Path, dagar: int = 330,
                klasser: list[str] | None = None,
                kurser: list[str] | None = None,
                bedomare=None,
                schema_nu: list[dict] | None = None) -> dict:
    """{schema, lov, poster, innehall, fran, till} ur Google Kalender, eller
    {error} när kopplingen saknas.

    Fönstret spänner ett helt läsår åt båda håll: arkivets lovband ritar
    terminen som den VAR, och planeringen behöver loven som kommer. `fran` och
    `till` följer med i svaret eftersom den som skriver in resultatet bara får
    ersätta det som ligger INOM fönstret — annars raderar en synk i augusti
    påsklovet nästa vår bara för att det låg utanför läsningen."""
    idag = date.today()
    fran = (idag - timedelta(days=240)).isoformat()
    till = (idag + timedelta(days=max(1, int(dagar or 330)))).isoformat()
    try:
        handelser = list_events(base_dir, fran, till)
    except RuntimeError as e:
        return {"error": str(e)}
    ut = tolka_handelser(handelser, klasser, kurser, fonster_till=till,
                         schema_nu=schema_nu)
    # Andra passet: `bedomare` får de osäkra serierna och svarar med beslut
    # (cache + Claude, se app/kalender_ai.py). Samma rena funktion körs om med
    # besluten, så det finns bara EN väg som placerar en händelse i veckan.
    if bedomare and ut.get("osakra"):
        beslut = bedomare(ut["osakra"]) or {}
        if beslut:
            ut = dict(tolka_handelser(handelser, klasser, kurser, beslut=beslut,
                                      fonster_till=till, schema_nu=schema_nu),
                      beslut=beslut)
    return dict(ut, fran=fran, till=till)
