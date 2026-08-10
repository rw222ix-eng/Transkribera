"""Manus → undertexter. Ett litet program VID SIDAN av appen.

Bakgrunden: manuset läses in som speaker, och Claude Design ska sedan synka
animationerna mot talet. Då behövs bara en sak av hela Transkribera — ljudet in,
tidsatt text ut — och ingenting av allt det andra appen gör (historik, prov,
lektionstavla, pywebview-fönstret). Därför en egen ingång med två filer i stället
för en flik till i appen: `python manus.py inspelning.wav` skriver .srt och .vtt
bredvid ljudfilen och är klart.

Motorn är däremot exakt appens: app/elevenlabs_asr.py (scribe_v2 i molnet, som
svarar med tid per ord) och transcriber.segmentera_ord (orden till undertext-
rader). Inget av det dupliceras här — går de sönder eller blir bättre följer det
här programmet med.

Manusfilen (`--manus`) accepteras men gör ingenting längre: gpt-transcribe tog
ett fritextprompt som styrde stavningen, Scribe har inget sådant fält (bara
keyterms, mot pristillägg). Flaggan står kvar så att gamla .bat-filer inte går
sönder — den loggar att den ignoreras.

`.ord.json` är den intressanta filen för animationssynk: den bär tid per ORD, och
det är en finare upplösning än en undertextrad. En animation som ska starta på
ordet «derivatan» hittar sin sekund där.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from app import elevenlabs_asr, media as media_mod, transcriber

BASE = Path(__file__).resolve().parent          # nyckelfil och models/ ligger här


# Terminalen skrivs på två sätt: hela rader (_logg) och en rad som skrivs över
# gång på gång (_procent, _strom). Den senare måste brytas innan nästa hela rad,
# annars klistras de ihop. Ingen ANSI-kod används för det — en .bat som startas
# från Utforskaren kan hamna i en konsol som skriver ut «[K» bokstavligt.
_oavslutad = False


def _ny_rad() -> None:
    global _oavslutad
    if _oavslutad:
        print(flush=True)
    _oavslutad = False


def _logg(msg: str) -> None:
    _ny_rad()
    print(msg, flush=True)


def _strom(bit: str) -> None:
    global _oavslutad
    print(bit, end="", flush=True)
    _oavslutad = not bit.endswith("\n")


def _procent(etikett: str):
    """Framsteg på EN rad — tidsättningen och modellhämtningen tar minuter, och
    en tyst terminal under tiden ser ut som en hängning."""
    def cb(p: int) -> None:
        global _oavslutad
        print(f"\r{etikett} {p:3d} %", end="", flush=True)
        _oavslutad = True
    return cb


def kor(media: Path, manus: Path | None, format: list[str], sprak: str,
        ut_mapp: Path | None, *,
        logg: Callable[[str], None] | None = None,
        strom: Callable[[str], None] | None = None,
        pct: Callable[[str, int], None] | None = None) -> list[Path]:
    """Hela vägen: ljud → moln → tider → filer. Returnerar det som skrevs.

    De tre återanropen kom till för manus_studio.py, som ritade framstegen i ett
    fönster i stället för i en terminal. Studion är borttagen — inläsningen görs
    numera av ElevenLabs i E:\\Manusrost — men krokarna får stå kvar: de kostar
    ingenting, och nästa fönster behöver dem igen. Utan dem skrivs framstegen
    till stdout precis som förut."""
    logg = logg or _logg
    strom = strom or _strom
    pct = pct or (lambda etikett, p: _procent(etikett)(p))
    if not media.exists():
        raise SystemExit(f"Filen finns inte: {media}")
    if not elevenlabs_asr.har_nyckel(BASE):
        raise SystemExit(
            f"Ingen ElevenLabs-nyckel. Lägg den i {BASE / elevenlabs_asr.NYCKELFIL} "
            "(eller sätt ELEVENLABS_API_KEY).")

    langd = media_mod.probe_duration(media) or 0.0
    if langd <= 0:
        if not media_mod.ffmpeg_available():
            raise SystemExit("ffmpeg/ffprobe saknas — de behövs för att läsa ljudet.")
        raise SystemExit(f"Kunde inte läsa någon speltid ur {media.name}.")

    if manus:
        logg("Manus som ledtext stöds inte av Scribe — flaggan ignoreras.")

    logg(f"{media.name} — {langd / 60:.1f} min, ca ${elevenlabs_asr.kostnad_usd(langd):.2f}.")
    # Ingen procentmätare för molnet: batch-API:et svarar i ett svep, och hela
    # texten skrivs ut när den kommer (delta_cb anropas en gång).
    moln = elevenlabs_asr.transkribera(
        media, BASE, langd=langd, sprak=sprak,
        log_cb=logg, delta_cb=strom)
    _ny_rad()
    if not moln.text:
        raise SystemExit("Transkriberingen gav ingen text.")

    # Ordtiderna kom med svaret — inget att ladda ner, ingenting på GPU:n.
    segment = transcriber.segmentera_ord(moln.ord)
    if not segment:
        segment = [{"start": 0.0, "end": round(langd, 3),
                    "text": moln.text, "words": []}]

    stam = (ut_mapp / media.stem) if ut_mapp else media.with_suffix("")
    if ut_mapp:
        ut_mapp.mkdir(parents=True, exist_ok=True)
    skrivna: list[Path] = []

    if "json" in format:
        # FÖRE clean_caption_dicts: den grupperar om till undertextrader och
        # tappar `words` på vägen. Ordtiderna är hela poängen med den här filen.
        p = stam.with_suffix(".ord.json")
        p.write_text(json.dumps(
            {"media": media.name, "langd": round(langd, 3), "segment": segment},
            ensure_ascii=False, indent=1), encoding="utf-8")
        skrivna.append(p)

    rader = transcriber.clean_caption_dicts(segment)
    textformat = [f for f in format if f != "json"]
    if textformat:
        skrivna += transcriber.write_outputs(
            [transcriber.Segment(d["start"], d["end"], d["text"]) for d in rader],
            stam, textformat)

    logg(f"Klart — {len(rader)} undertextrader, "
         f"{moln.debiterade_sekunder / 60:.1f} ljudminuter, ${moln.kostnad:.2f}.")
    for p in skrivna:
        logg("  " + str(p))
    return skrivna


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="manus",
        description="Ljud/video → SRT, VTT och ordtider. Motorn är Transkriberas.")
    ap.add_argument("media", type=Path, help="inspelningen (wav, mp3, m4a, mp4 ...)")
    ap.add_argument("-m", "--manus", type=Path,
                    help="accepteras men ignoreras — Scribe tar ingen ledtext")
    ap.add_argument("-f", "--format", default="srt,vtt,json",
                    help="srt, vtt, txt, json (ordtider) — kommaseparerat")
    ap.add_argument("-s", "--sprak", default="sv", help="språkkod, tomt = auto")
    ap.add_argument("-u", "--ut", type=Path, help="målmapp (annars bredvid mediefilen)")
    a = ap.parse_args(argv)

    format = [f.strip().lower() for f in a.format.split(",") if f.strip()]
    okant = [f for f in format if f != "json" and f not in transcriber.WRITERS]
    if okant:
        raise SystemExit(f"Okänt format: {', '.join(okant)}")
    kor(a.media, a.manus, format, a.sprak, a.ut)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Ctrl+C mitt i molnet ska inte spy ut en traceback över terminalen.
        print("\nAvbrutet.", file=sys.stderr)
        sys.exit(130)
