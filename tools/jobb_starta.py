"""Starta ett SSE-jobb mot appen och skriv jobb-id:t.

Läser bara handskakningen `{"type":"jobb","id":N}` och stänger strömmen:
jobbet lever vidare i `jobb`/`jobb_events` (app/web/sse.py) och följs där.
409 «upptaget» väntas ut i upp till en timme, 409 «godkant» avbryter direkt.

    python -m tools.jobb_starta api/planning/generate kropp.json
    python -m tools.jobb_starta api/exams/generate kropp.json
    python -m tools.jobb_starta api/exams/115/refine kropp.json

Skriv vägen UTAN inledande snedstreck i Git Bash, annars gör MSYS om den till
en Windows-sökväg (/Program Files/Git/api/…); skriptet lägger på strecket.
"""
import json, os, sys, time, urllib.request, urllib.error
# TRANSKRIBERA_API pekar på en annan server, t.ex. en med ny kod bredvid appen.
API = os.environ.get("TRANSKRIBERA_API", "http://127.0.0.1:18731")
vag, kropp = "/" + sys.argv[1].lstrip("/"), json.loads(open(sys.argv[2], encoding="utf-8").read())
data = json.dumps(kropp, ensure_ascii=False).encode("utf-8")
start = time.time()
while True:
    req = urllib.request.Request(API + vag, data=data, headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
    try:
        svar = urllib.request.urlopen(req, timeout=180)
    except urllib.error.HTTPError as e:
        kropp_fel = e.read().decode("utf-8", "replace")
        try: kod = json.loads(kropp_fel).get("kod")
        except (ValueError, AttributeError): kod = None
        # Bara «upptaget» väntas ut. Ett godkänt papper blir aldrig ledigt av
        # sig självt: 24/9 väntade ett skript 47 minuter och 110 anrop på det.
        if e.code == 409 and kod != "godkant" and time.time() - start < 3600:
            print("409 upptaget, väntar 30 s", flush=True); time.sleep(30); continue
        # 503 «gammal_kod»: servern under vakten byter till ny kod (app/web/kodvakt.py)
        # och startar om när pågående jobb är klara. Vänta in den nya koden.
        if e.code == 503 and kod == "gammal_kod" and time.time() - start < 3600:
            print("503 gammal kod, servern startar om, väntar 15 s", flush=True); time.sleep(15); continue
        raise SystemExit(f"{e.code} {kropp_fel[:400]}")
    except (urllib.error.URLError, ConnectionError) as e:
        # Några sekunder utan svar medan vakten startar om servern. Den gamla
        # servern kan också stänga anslutningen mitt i svaret (WinError 10053,
        # 2026-10-23: fem väntande anrop dog när vakten bytte kod).
        if time.time() - start < 3600:
            print(f"ingen server ({getattr(e, 'reason', e)}), väntar 5 s", flush=True); time.sleep(5); continue
        raise
    try:
        for rad in svar:
            t = rad.decode("utf-8", "replace").strip()
            if not t.startswith("data:"): continue
            ev = json.loads(t[5:].strip())
            if ev.get("type") == "jobb": print("JOBB", ev["id"]); raise SystemExit(0)
            if ev.get("type") == "error": raise SystemExit("fel: " + str(ev.get("message")))
    finally:
        svar.close()
    raise SystemExit("inget jobb-id")
