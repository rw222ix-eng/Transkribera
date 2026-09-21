"""Steg 1 av godkännandet via API: PATCH:a ett utkast till godkant.

Steg 2 är appens egen knapp — `cd e2e && node godkann-avritat.mjs <id>` för
arbetsblad/gruppuppgift (skärmens PDF) eller `node godkann-tavla.mjs <id>`
för tavlan (approve + PNG-export). Båda skripten kräver att dokumentet
ligger i Dokument.sparade(), alltså är godkänt — därför det här steget.
Knappen lägger också kalenderposten (Kalender.lagg), som ingen serverväg gör.
OBS (2026-09-21): «Fortsätt ändra → Godkänn» lägger en ANDRA kopia av
dokumentet i högen utan pdf; radera kopian (DELETE /api/dokument/{id}) och
behåll originalet, som bär pdf-sökvägen.

    python -m tools.dokument_godkant <dokument_id>
"""
import json, sqlite3, sys, urllib.request
DB = r"E:\Transkribera\transkribera.db"; API = "http://127.0.0.1:18731"
dok_id = int(sys.argv[1])
c = sqlite3.connect(DB)
v = json.loads(c.execute("select data from dokument_versioner where dokument_id=? order by version desc limit 1", (dok_id,)).fetchone()[0])
v["id"] = dok_id
req = urllib.request.Request(f"{API}/api/dokument/{dok_id}", data=json.dumps({"status": "godkant", "dokument": v, "foljd": None, "stada": True}, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"}, method="PATCH")
with urllib.request.urlopen(req, timeout=120) as r: print("PATCH:", r.read().decode("utf-8")[:200])
