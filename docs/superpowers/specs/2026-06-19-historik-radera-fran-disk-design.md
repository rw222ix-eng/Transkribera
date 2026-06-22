# Design: Radera transkribering även från disk (Historik)

- **Datum:** 2026-06-19
- **App:** Transkribera (E:\Transkribera)
- **Status:** Godkänd design, klar för implementationsplan
- **Del:** A av tre (A: diskradering · B: rikare historik/spelare · C: LLM-autonamn)
- **Relaterad:** [2026-06-18-video-spara-historik-mapp-och-inbaddning-design.md](2026-06-18-video-spara-historik-mapp-och-inbaddning-design.md) (skapade resultatmapparna som nu ska kunna raderas)

## Bakgrund

När man transkriberar skapas en resultatmapp `Transkriberingar/{datum · namn}/` med median (video/ljud) + `.srt` (se den relaterade designen). Historik-posten i `history.json` pekar på mappen via fältet `folder`.

Idag tar `DELETE /api/history/{id}` (→ `history_store.delete_history`) **endast** bort JSON-posten. Mappen och alla filer blir kvar på disk. Bekräftelsedialogen säger till och med uttryckligen *"Filer du redan sparat på disken påverkas inte."*

Vid läget **"Spara separat"** med en lokal fil **flyttas originalfilen in** i resultatmappen — mappen är då ofta den *enda* kopian av användarens media.

## Mål

1. När en transkribering raderas från historiken ska dess resultatmapp **raderas permanent från disken**.
2. Raderingen ska vara säker: bara mappar **under `base_dir/Transkriberingar/`** får tas bort.
3. Bekräftelsedialogen ska tydligt varna att det är permanent och oåterkalleligt.

## Icke-mål

- Ingen papperskorg/ångerfunktion (beslut: **permanent radering** via `shutil.rmtree`).
- Ingen massradering ("rensa allt") — en post i taget, som idag.
- Ingen ändring av hur mappar *skapas* (det gör `output_store` redan).

## Bekräftade beslut (från brainstorm)

| Fråga | Beslut |
|-------|--------|
| Papperskorg eller permanent? | **Permanent** (`shutil.rmtree`) |
| Vad raderas? | Hela resultatmappen (`folder`) — media + SRT + ev. cachefiler (`.preview.m4a`, `_burnsubs.srt`) ligger alla i mappen |
| Låst fil (media öppen i spelaren) | **Allt-eller-inget:** misslyckas raderingen behålls posten + felmeddelande visas; frontend stoppar uppspelning före DELETE för att undvika låsningen |
| Poster utan `folder` (äldre/seed) | Bara JSON-posten tas bort, som idag |

## Backend-arkitektur

### `app/output_store.py` (ny funktion)

`output_store` äger redan mapp-livscykeln (skapar `Transkriberingar/...`), så raderingen hör hemma här:

```
delete_result_folder(base_dir: Path, folder: str | Path | None) -> bool
```

- Returnerar `False` (utan att röra disken) om `folder` är tomt/None.
- Resolver både `folder` och `base_dir / "Transkriberingar"` till absoluta sökvägar och kontrollerar att `folder` ligger **under** rot-mappen. Om inte → returnerar `False` (ingen radering) — skydd mot att råka radera fel katalog vid manipulerad/felaktig sökväg.
- Saknad mapp räknas som lyckad (inget kvar att radera) → `True`.
- Kör `shutil.rmtree(folder)`. Om det kastar (t.ex. låst fil) → låt undantaget propagera (anroparen avgör hur det hanteras).

### `app/web/server.py` — `DELETE /api/history/{id}`

Ändras från "ta bort JSON" till:

1. Ladda historiken, hitta posten med `id`.
2. Om posten har `folder`: försök `output_store.delete_result_folder(base, entry["folder"])`.
   - Lyckas (eller mapp saknas/utanför base) → fortsätt.
   - Kastar (`OSError`, t.ex. låst fil) → **behåll posten**, returnera `409` med `{ "error": "kunde inte radera mappen — en fil kan vara öppen" }`. JSON-posten tas alltså **inte** bort.
3. Ta bort JSON-posten via `history_store.delete_history(history_file, id)`.
4. Returnera `{ "ok": True, "folder_removed": bool }`.

`history_store.py` är oförändrad (fortsätter äga endast JSON-skrivning).

## Frontend (`app/web/static/app.js`)

- **`askDeleteHistory(id, name)`** — ny `body`-text som varnar att hela mappen raderas permanent. Förslag:
  *"'{name}' och hela dess mapp (video/ljud + undertexter) raderas permanent från disken. Det går inte att ångra."*
  (`danger: true` behålls → röd knapp.)
- **`confirmYes`** (kind `history`):
  - Anropa `stopAudio()` **före** DELETE (släpper ev. filhandtag från spelaren, undviker låsning).
  - `fetch DELETE /api/history/{id}` → vid `ok` `loadHistory()`; vid felsvar (t.ex. `409`) visa en toast/notis i stället för att tyst lyckas. (Återanvänd befintligt toast-mönster.)
- Poster utan `folder`: backend tar bara bort JSON-posten; ingen frontend-skillnad.

## Edge-cases

- **Låst mediafil:** frontend stoppar uppspelning först; om radering ändå misslyckas behålls posten + notis ("stäng och försök igen").
- **Mapp redan borttagen manuellt:** räknas som lyckad radering, posten tas bort.
- **`folder` pekar utanför `Transkriberingar/`:** ingen radering (säkerhetsvägran), men JSON-posten tas ändå bort (posten ska bort ur listan; ingen disk rörs).
- **Post utan `folder`:** bara JSON-posten tas bort.
- **Delvis raderad mapp:** `rmtree` är inte transaktionell; vid fel mitt i kan enstaka filer ligga kvar. Posten behålls (409) så användaren kan försöka igen efter att ha stängt det som låser.

## Filer som berörs

- `app/output_store.py` — ny `delete_result_folder(base_dir, folder)`.
- `app/web/server.py` — `DELETE /api/history/{id}` raderar mappen (validerat) före JSON-posten; 409 vid låst fil.
- `app/web/static/app.js` — ny varningstext i `askDeleteHistory`; `stopAudio()` + felhantering i `confirmYes`.
- `tests/test_output_store.py` — enhetstester för `delete_result_folder`.
- `tests/test_web_server.py` — endpoint-test för radering.

## Verifiering

- **pytest** (`test_output_store.py`): `delete_result_folder` raderar en giltig mapp under `Transkriberingar/`; vägrar (returnerar `False`, raderar inget) en sökväg utanför base; tål saknad mapp (`True`); tom/None → `False`.
- **pytest** (`test_web_server.py`): post med riktig temp-mapp → `DELETE` → både mapp och post borta, svar `folder_removed: true`; post utan `folder` → bara posten bort; post med `folder` utanför base → posten bort, ingen disk rörd.
- **Live-preview:** transkribera en kort fil → radera i historiken → bekräfta att mappen i `Transkriberingar/` är borta och att posten försvann ur listan.
