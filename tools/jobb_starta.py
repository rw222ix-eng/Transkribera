"""Starta ett SSE-jobb mot appen och skriv jobb-id:t.

Läser bara handskakningen `{"type":"jobb","id":N}` och stänger strömmen:
jobbet lever vidare i `jobb`/`jobb_events` (app/web/sse.py) och följs där.
409 (molnplatsen upptagen) väntas ut i upp till en timme.

    python -m tools.jobb_starta api/planning/generate kropp.json
    python -m tools.jobb_starta api/exams/generate kropp.json
    python -m tools.jobb_starta api/exams/115/refine kropp.json

Skriv vägen UTAN inledande snedstreck i Git Bash, annars gör MSYS om den till
en Windows-sökväg (/Program Files/Git/api/…); skriptet lägger på strecket.
"""
import json, sys, time, urllib.request, urllib.error
API = "http://127.0.0.1:18731"
vag, kropp = "/" + sys.argv[1].lstrip("/"), json.loads(open(sys.argv[2], encoding="utf-8").read())
data = json.dumps(kropp, ensure_ascii=False).encode("utf-8")
start = time.time()
while True:
    req = urllib.request.Request(API + vag, data=data, headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
    try:
        svar = urllib.request.urlopen(req, timeout=180)
    except urllib.error.HTTPError as e:
        if e.code == 409 and time.time() - start < 3600:
            print("409 upptaget, väntar 30 s", flush=True); time.sleep(30); continue
        raise SystemExit(f"{e.code} {e.read().decode('utf-8','replace')[:400]}")
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
