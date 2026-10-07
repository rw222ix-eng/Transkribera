# Transkribera

En lokal-först-app för en gymnasielärare i matematik. Utifrån schemat,
läroboken och det hon redan gjort planerar hon lektionerna och skriver tavlor,
prov, arbetsblad och gruppuppgifter. Namnet är kvar från början, då appen
transkriberade inspelade lektioner. Den delen är borta ur appen och lever bara
i manusstudion (`manus.py`), ett eget litet program bredvid.

Allt annat står i koden, i kommentarer vid raden de handlar om. Nya .md-filer
skapas inte. De få som finns har var sin snäv uppgift.

## Så här hänger den ihop

**Servern** är FastAPI (`app/web/server.py` + routers för planering, prov, bok
och utskrift). Den binder 127.0.0.1 och startas antingen som skrivbordsfönster
(pywebview, `app/web/desktop.py`) eller som ren server via `transkribera_web.py`.

**Språkmodellen är Claude Code CLI**, headless (`app/claude_code.py`). Ingen
API-nyckel: appen kör på lärarens egen inloggning. Verktygen är avstängda utom
`Read`, som tänds när bilder skickas (boksidorna). `app/llm_client.py` är
promptlagret.

**Läroboken** (`app/bok.py`, `app/bok_ocr.py`) läses ur en PDF: importen läser
innehållsförteckningen och bygger registret, och sidornas innehåll läses först
när ett uppslag faktiskt används — en sida kostar ungefär en minut och en bok är
tre hundra sidor.

**Persistensen** är SQLite (`app/db.py`) och mappen `Transkriberingar/` för
tavlor, prov, bokens sidbilder och utskriftspaket.

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

Kraven ligger i `requirements.txt`. `claude` ska vara installerat och inloggat
för allt som skriver text. Manusstudion (`manus.bat`, dra en ljudfil på den)
vill dessutom ha `ffmpeg` på PATH och en ElevenLabs-nyckel
(`elevenlabs_key.txt` eller `ELEVENLABS_API_KEY`).

## Testa

```bash
python -m pytest -q
```

```bash
cd e2e && npx playwright test
```

E2E-sviten kör mot en riktig server på port 18751 och kräver Chrome
(`channel: "chrome"`). Det viktigaste testet är `offline.spec.mjs`: appen får
inte göra ett enda anrop utanför datorn.

`ocr-eval/` är en egen rigg som avgör vilken modell som ska läsa boksidor. Den
kostar riktiga pengar och körs för hand — se dess egen README.
