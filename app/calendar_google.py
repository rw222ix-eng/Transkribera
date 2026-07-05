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
from datetime import datetime, timedelta
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
CLIENT_SECRET_NAME = "google_client_secret.json"
TOKEN_NAME = "google_token.json"
TIMEZONE = "Europe/Stockholm"
DEFAULT_DURATION_MIN = 40

HINT_LIBS = ("Google-biblioteken saknas — installera google-api-python-client "
             "och google-auth-oauthlib.")


def _files(base_dir: Path) -> tuple[Path, Path]:
    return Path(base_dir) / CLIENT_SECRET_NAME, Path(base_dir) / TOKEN_NAME


def _hint_secret(base_dir: Path) -> str:
    return (f"Ingen OAuth-klientfil hittades — skapa en \"Desktop app\"-klient i "
            f"Google Cloud Console och lägg den som {CLIENT_SECRET_NAME} i {base_dir}.")


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
    """Anslutningsstatus för UI:t: {connected, hint?}."""
    try:
        import google_auth_oauthlib  # noqa: F401  (bara närvarokoll)
    except ImportError:
        return {"connected": False, "hint": HINT_LIBS}
    secret, _ = _files(base_dir)
    if not secret.exists():
        return {"connected": False, "hint": _hint_secret(base_dir)}
    return {"connected": _load_creds(base_dir) is not None}


def connect(base_dir: Path) -> dict:
    """Kör OAuth-samtyckesflödet i användarens webbläsare (blockerar tills
    callbacken kommit). Returnerar {connected} eller {connected, error}."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        return {"connected": False, "error": HINT_LIBS}
    secret, token = _files(base_dir)
    if not secret.exists():
        return {"connected": False, "error": _hint_secret(base_dir)}
    if _load_creds(base_dir) is not None:
        return {"connected": True}
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
        creds = flow.run_local_server(
            port=0, authorization_prompt_message="",
            success_message="Klart — stäng fliken och gå tillbaka till Transkribera.")
    except Exception as exc:
        return {"connected": False, "error": f"Anslutningen misslyckades: {exc}"}
    token.write_text(creds.to_json(), encoding="utf-8")
    return {"connected": True}


def create_event(base_dir: Path, title: str, start_iso: str,
                 description: str = "",
                 duration_min: int = DEFAULT_DURATION_MIN) -> dict:
    """Skapa en händelse i användarens primära kalender.
    Returnerar {ok, id, link} eller {error}."""
    creds = _load_creds(base_dir)
    if creds is None:
        st = status(base_dir)
        return {"error": st.get("hint")
                or "Inte ansluten till Google Kalender — klicka \"Anslut Google-konto\" först."}
    try:
        start = datetime.fromisoformat((start_iso or "").strip())
    except ValueError:
        return {"error": "Ogiltig starttid för händelsen."}
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
