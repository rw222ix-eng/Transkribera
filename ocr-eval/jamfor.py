"""Bygger resultat/jamfor.html — fotot bredvid varje kandidats utläsning.

Beslutet fattas med ögonen, inte på ett mått. Det finns ingen automatisk poäng
som fångar "figurbeskrivningen duger för en genomgång" eller "den där gissade
på ett index". Sidan är därför gjord för att läsas: originalet till vänster,
utläsningarna sida vid sida, och en rad överst som räknar det som ändå går att
räkna.

Enda måttet som visas automatiskt är [oläsligt]-markörerna, och det är MED
FLIT tvetydigt: många kan betyda en ärlig modell eller en dålig bild, noll kan
betyda perfekt läsning eller en modell som gissar. Siffran ska få dig att titta,
inte att välja.
"""

from __future__ import annotations

import base64
import html
import mimetypes
import re
from pathlib import Path

HAR = Path(__file__).resolve().parent
BILDTYPER = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def bild_som_data_uri(p: Path) -> str:
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def main() -> int:
    ut = HAR / "resultat"
    if not ut.exists():
        print("Inget resultat än — kör python ocr-eval/kor.py först.")
        return 1

    bilder = sorted(p for p in (HAR / "sidor").iterdir()
                    if p.is_file() and p.suffix.lower() in BILDTYPER)

    delar = ["""<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><title>OCR-jämförelse</title>
<style>
  :root { --paper:#F1F2ED; --surface:#fff; --ink:#161A14; --ink2:#4F514D;
          --ink3:#6A6C68; --line:#D9D9D5; --bad:#C8463A; --accent:#2C6E9E; }
  * { box-sizing:border-box }
  body { margin:0; padding:32px; background:var(--paper); color:var(--ink);
         font:16px/1.55 "Inter Tight",system-ui,sans-serif; }
  h1 { font-family:"Instrument Serif",Georgia,serif; font-style:italic;
       font-size:3.2rem; line-height:1.05; color:#000; margin:0 0 8px; }
  .lede { color:var(--ink2); max-width:70ch; margin:0 0 40px; }
  .sida { margin:0 0 64px; }
  .sidrubrik { font-family:ui-monospace,monospace; font-size:.72rem;
       letter-spacing:.08em; text-transform:uppercase; color:var(--ink3);
       padding-bottom:8px; border-bottom:1px solid var(--line); margin:0 0 16px; }
  .rad { display:flex; gap:16px; align-items:flex-start; overflow-x:auto; }
  .foto { flex:0 0 380px; position:sticky; left:0; }
  .foto img { width:100%; border:1px solid var(--line); border-radius:4px; }
  .kort { flex:0 0 460px; background:var(--surface); border:1px solid var(--line);
          border-radius:4px; padding:14px 16px; max-height:70vh; overflow:auto; }
  .namn { font-weight:600; margin:0 0 2px; }
  .meta { font-family:ui-monospace,monospace; font-size:.72rem; color:var(--ink3);
          margin:0 0 10px; }
  .flagga { color:var(--bad); }
  pre { white-space:pre-wrap; word-wrap:break-word; font:13px/1.5 ui-monospace,monospace;
        margin:0; color:var(--ink2); }
  mark { background:#F6E5A8; color:var(--ink); }
</style></head><body>
<h1>Vad ser modellerna?</h1>
<p class="lede">Samma prompt, samma sidor. Originalet ligger kvar till vänster när du
scrollar i sidled. <mark>[oläsligt]</mark> är markerat — men läs siffran försiktigt:
många kan betyda en ärlig modell eller en dålig bild, noll kan betyda perfekt läsning
eller en modell som gissar. Kontrollera alltid matematiken och figurtexten mot fotot.</p>
"""]

    for bild in bilder:
        träffar = sorted(ut.glob(f"{bild.stem}__*.md"))
        if not träffar:
            continue
        delar.append(f'<section class="sida"><p class="sidrubrik">{html.escape(bild.name)}</p><div class="rad">')
        delar.append(f'<div class="foto"><img src="{bild_som_data_uri(bild)}" alt=""></div>')
        for f in träffar:
            kandidat = f.stem.split("__", 1)[1]
            text = f.read_text(encoding="utf-8")
            huvud = re.match(r"<!--(.*?)-->", text, re.S)
            meta = huvud.group(1).strip() if huvud else ""
            kropp = text[huvud.end():].strip() if huvud else text
            olasliga = kropp.count("[oläsligt]")
            esc = html.escape(kropp).replace(
                "[oläsligt]", "<mark>[oläsligt]</mark>")
            flagga = f' · <span class="flagga">{olasliga} × [oläsligt]</span>' if olasliga else ""
            delar.append(
                f'<div class="kort"><p class="namn">{html.escape(kandidat)}</p>'
                f'<p class="meta">{html.escape(meta)}{flagga}</p><pre>{esc}</pre></div>'
            )
        delar.append("</div></section>")

    delar.append("</body></html>")
    mal = ut / "jamfor.html"
    mal.write_text("".join(delar), encoding="utf-8")
    print("Skrev", mal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
