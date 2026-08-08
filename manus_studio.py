"""Studion: spela in manuset och få undertexterna direkt. Systerfil till manus.py.

manus.py tar en färdig inspelning. Det som saknades var steget före — att LÄSA IN
manuset — och det behöver tre saker som en terminal inte kan ge: en mikrofon, ett
manus som rullar medan man läser, och en knapp. Därför ett fönster.

Fönstret är webbläsarens. En liten server på en FAST port (mikrofontillståndet i
Chrome hänger på origin — byter porten mellan körningarna måste läraren godkänna
mikrofonen varje gång) serverar manus_studio.html och tar emot inspelningen som
base64 i en JSON-post. Ingen FastAPI, inget pywebview: stdlib räcker, och en
webbläsares getUserMedia är den enda mikrofonvägen som fungerar likadant varje
gång på Windows.

Själva arbetet är manus.kor() — samma väg som CLI:t, samma filer ut. Det enda som
tillkommer här är att inspelningen skrivs om till Ogg/Opus först (se _remuxa) och
att manuset sparas som .txt bredvid ljudet, så att mappen är fullständig: det som
sades, det som skulle sägas, och tiderna däremellan.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import webbrowser
from base64 import b64decode
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import manus
from app import media as media_mod
from app.paths import safe_name

BASE = Path(__file__).resolve().parent
UT = BASE / "Manus"                 # en mapp per inspelning, alla filer i samma
# 8751 är appens och 8752 tar soakens testserver (tools/soak.py) — studion tar
# nästa lediga i följden. Porten måste vara FAST: mikrofontillståndet i
# webbläsaren hänger på origin, och en ny port betyder en ny fråga varje gång.
PORT = 8753

# Ett jobb i taget — en lärare spelar in en video åt gången, och två samtidiga
# körningar hade slagits om GPU:n i tidsättningen.
_jobb: dict = {"lage": "vilar", "logg": [], "pct": 0, "etikett": "",
               "filer": [], "fel": "", "mapp": ""}
_las = threading.Lock()


def _satt(**nytt) -> None:
    with _las:
        _jobb.update(nytt)


def _logg(rad: str) -> None:
    with _las:
        _jobb["logg"].append(rad)
        del _jobb["logg"][:-200]        # loggen är en svans, inte ett arkiv


def _strom(bit: str) -> None:
    """Molnets text växer fram tecken för tecken. Sista loggraden byggs på i
    stället för att bli hundra rader — i fönstret är det EN rad som blir längre."""
    with _las:
        if _jobb["logg"] and _jobb["logg"][-1].startswith("…"):
            _jobb["logg"][-1] += bit
        else:
            _jobb["logg"].append("…" + bit)


def _remuxa(ra: Path, mal: Path) -> Path:
    """Rå inspelning → Ogg/Opus med läsbar speltid.

    MediaRecorders webm skrivs live och saknar Duration i sin header: ffprobe
    svarar N/A, och manus.kor() hade avbrutit med «Kunde inte läsa någon
    speltid» på en inspelning som är alldeles hel. Ogg bär tiden i sina
    granulepositioner och slipper problemet.

    Strömkopiering först — Chrome spelar redan in i Opus, så det är en
    ompaketering utan kvalitetsförlust och tar bråkdelen av en sekund. Bara om
    codecen är någon annan kodas det om.
    """
    for argv in (["-c:a", "copy"], ["-c:a", "libopus", "-b:a", "48k"]):
        try:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(ra), *argv, str(mal)],
                           check=True, capture_output=True)
            if media_mod.probe_duration(mal):
                ra.unlink(missing_ok=True)
                return mal
        except (OSError, subprocess.SubprocessError):
            continue
    raise RuntimeError("Kunde inte läsa inspelningen — ffmpeg saknas eller "
                       "ljudet blev tomt. Är rätt mikrofon vald?")


def _arbeta(namn: str, manustext: str, ljud: bytes, andelse: str) -> None:
    """Jobbtråden: skriv filerna, kör manus.kor(), lägg resultatet i _jobb."""
    try:
        stam = safe_name(namn.strip() or datetime.now().strftime("Manus %Y-%m-%d %H.%M"),
                         fallback="Manus")
        mapp = UT / stam
        mapp.mkdir(parents=True, exist_ok=True)
        _satt(mapp=str(mapp))
        _logg(f"Sparar i {mapp}")

        ra = mapp / f"_ra{andelse}"
        ra.write_bytes(ljud)
        media = _remuxa(ra, mapp / f"{stam}.ogg")

        manusfil = None
        if manustext.strip():
            # Manuset följer med i mappen: om sex månader är det den enda källan
            # till vad som SKULLE sägas, och undertexten bär bara vad som sades.
            manusfil = mapp / f"{stam}.txt"
            manusfil.write_text(manustext.strip() + "\n", encoding="utf-8")

        filer = manus.kor(media, manusfil, ["srt", "vtt", "json"], "sv", None,
                          logg=_logg, strom=_strom,
                          pct=lambda e, p: _satt(etikett=e, pct=p))
        _satt(lage="klar", filer=[p.name for p in filer], pct=100, etikett="")
    except Exception as fel:                    # noqa: BLE001 — visas för läraren
        _logg(f"Fel: {fel}")
        _satt(lage="fel", fel=str(fel) or fel.__class__.__name__)


class Studio(BaseHTTPRequestHandler):
    def _svara(self, kropp: bytes, typ: str = "application/json") -> None:
        self.send_response(200)
        self.send_header("Content-Type", typ + "; charset=utf-8")
        self.send_header("Content-Length", str(len(kropp)))
        # Ingen cache: sidan redigeras medan studion står öppen.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(kropp)

    @property
    def vag(self) -> str:
        """Sökvägen utan frågesträng. En cachebrytare (`/?cb=2`) gjorde annars
        att startsidan svarade 404 — sökvägen matchades tecken för tecken."""
        return self.path.split("?", 1)[0]

    def do_GET(self) -> None:                   # noqa: N802 — BaseHTTPRequestHandler
        if self.vag == "/lage":
            with _las:
                self._svara(json.dumps(_jobb, ensure_ascii=False).encode("utf-8"))
        elif self.vag == "/oppna":
            mapp = _jobb.get("mapp") or str(UT)
            if Path(mapp).is_dir():
                os.startfile(mapp)              # Utforskaren; bara Windows behövs
            self._svara(b'{"ok":true}')
        elif self.vag in ("/", "/index.html"):
            self._svara((BASE / "manus_studio.html").read_bytes(), "text/html")
        else:
            self.send_error(404)

    def do_POST(self) -> None:                  # noqa: N802
        if self.vag != "/spela":
            return self.send_error(404)
        if _jobb["lage"] == "arbetar":
            return self._svara(b'{"fel":"Ett jobb kors redan."}')
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        _satt(lage="arbetar", logg=[], pct=0, etikett="", filer=[], fel="", mapp="")
        threading.Thread(target=_arbeta, daemon=True, args=(
            data.get("namn") or "", data.get("manus") or "",
            b64decode(data.get("ljud") or ""), data.get("andelse") or ".webm")).start()
        self._svara(b'{"ok":true}')

    def log_message(self, *_a) -> None:
        """Tyst. Konsolen är minimerad och ska bara visa det som betyder något."""


def main() -> None:
    UT.mkdir(exist_ok=True)
    url = f"http://127.0.0.1:{PORT}/"
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Studio)
    except OSError:
        # Andra dubbelklicket på skrivbordsgenvägen. En traceback i en minimerad
        # konsol hade sett ut som att ingenting hände — öppna fönstret i stället,
        # det var ändå det klicket ville.
        print("Studion körs redan — öppnar fönstret.")
        webbrowser.open(url)
        return
    print(f"Studion är igång: {url}\nStäng det här fönstret när du är klar.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
