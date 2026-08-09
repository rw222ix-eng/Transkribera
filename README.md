# Transkribera

En lokal-först-app för en gymnasielärare i matematik. Hon spelar in sina
lektioner, appen transkriberar dem, och utifrån transkriptionerna, läroboken och
det hon redan gjort planerar hon nästa lektion och skriver tavlor, prov,
arbetsblad och gruppuppgifter.

Allt annat står i koden, i kommentarer vid raden de handlar om. Det här är den
enda .md-filen i repot och den ska förbli det.

## Så här hänger den ihop

**Servern** är FastAPI (`app/web/server.py` + routers för planering, prov, bok
och utskrift). Den binder 127.0.0.1 och startas antingen som skrivbordsfönster
(pywebview, `app/web/desktop.py`) eller som ren server via `transkribera_web.py`.

**Transkriberingen** styckar ljudet vid tystnader (ffmpeg), skickar bitarna till
OpenAI `gpt-transcribe` (`app/openai_asr.py`) och sätter tidsstämplarna **lokalt**
med forced alignment (`app/alignment.py`, KBLab wav2vec2). Kostnaden räknas ur
svarets `usage.seconds` — aldrig ur filens längd.

**Språkmodellen är Claude Code CLI**, headless (`app/claude_code.py`). Ingen
API-nyckel: appen kör på lärarens egen inloggning. Verktygen är avstängda utom
`Read`, som tänds när bilder skickas (boksidorna). `app/llm_client.py` är
promptlagret.

**Läroboken** (`app/bok.py`, `app/bok_ocr.py`) läses ur en PDF: importen läser
innehållsförteckningen och bygger registret, och sidornas innehåll läses först
när ett uppslag faktiskt används — en sida kostar ungefär en minut och en bok är
tre hundra sidor.

**Persistensen** är SQLite (`app/db.py`) plus `history.json` — enda stället
segmenttiderna ligger utöver SRT-filen — och mappen `Transkriberingar/` för
resultat, tavlor, prov, bokens sidbilder och utskriftspaket.

**PDF:er** byggs av en bundlad Tectonic (`bin/tectonic/`) ur LaTeX-mallarna i
`app/templates/`. Kompileringsfel går tillbaka till modellen som
korrigeringsprompt, högst två rundor.

**Frontenden** (`app/web/ui/`) är ramverkslös: `app.html` laddar ett fyrtiotal
vanliga skript i bestämd ordning, utan byggsteg. Den är en byte-för-byte-kopia
av Claude Design-projektet «Transkribera Design System» med fyra dokumenterade
avvikelser, alla för offline-drift (lokala typsnitt, vendorerad KaTeX, borttagen
React-UMD och borttagna Matteprov-tokens). Varje ändring här synkas tillbaka
till designprojektet — repo och design ska vara identiska.

Utan server kör frontenden vidare på sin prototypdata. Det är inte en reservplan
utan ett krav: designprojektet har ingen server, och appen ska gå att rita mot.

## Köra

```bash
python transkribera_web.py
```

Kraven ligger i `requirements.txt`. `ffmpeg` och `ffprobe` ska finnas på PATH,
och `claude` ska vara installerat och inloggat för allt som skriver text.

## Testa

```bash
python -m pytest -q
```

```bash
cd e2e && npx playwright test
```

E2E-sviten kör mot en riktig server på port 8751 och kräver Chrome
(`channel: "chrome"`). Det viktigaste testet är `offline.spec.mjs`: appen får
inte göra ett enda anrop utanför datorn.

`ocr-eval/` är en egen rigg som avgör vilken modell som ska läsa boksidor. Den
kostar riktiga pengar och körs för hand — se dess egen README.
