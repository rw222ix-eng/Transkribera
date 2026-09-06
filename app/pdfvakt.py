"""Ett pdfium i taget i processen.

FYNDET (2026-09-06). Läraren startade skrivbordsappen, valde en sida i boken
och fick ingenting: `bok.las_spann → rendera → _oppna` föll med «Failed to load
document (PDFium: Data format error)» på en fil som samma sekund gick att öppna
i en vanlig python-process (304 sidor). Felet såg processberoende ut, och det
ÄR det — men det är inte pywebview, WebView2 eller pythonw som är skillnaden.
Alla tre är utredda och friade: appen startad på riktigt i app-läge (pywebview
+ WebView2 + uvicorn under pythonw.exe) öppnar samma PDF felfritt, och ingen
främmande `pdfium.dll` finns i processen.

Skillnaden är att appen använder pdfium från FLERA TRÅDAR SAMTIDIGT. pdfium är
inte trådsäkert. Två trådar som öppnar och renderar samma bok samtidigt river
sönder bibliotekets globala tillstånd, och skadan är BESTÅENDE: efter
kapplöpningen misslyckas varje öppning i den processen, även när den är ensam,
och även efter FPDF_DestroyLibrary + FPDF_InitLibrary. Bara en ny process
läker. Mätt: sex trådar × åtta varv över `Liber Ma 1c komplett.pdf` gav 50 fel
(«Data format error», «Failed to load page», helvita sidor) på 16,9 s; samma
arbete genom det här låset gav noll fel på 5,7 s — serialiseringen är alltså
inte ens dyrare, för trådarna slogs om samma fil.

Det förklarar tre gamla gåtor i loggen: de tretton vita 9 kB-PNG:erna
(2026-08-31), «tre inläsningar i rad föll» (2026-08-30) och att VARJE
«Data format error» i transkribera.log kom ur ett läge=app-pass medan
läge=webb aldrig råkade ut för det. Appen är den som kör två pdfium-vägar mot
samma bok samtidigt: SSE-jobbet (`routes_bok.las` → `bok.rendera`) medan
uppslagets båda blad hämtas (`routes_bok.sidbild` → `bok.rendera`, en tråd per
begäran ur FastAPI:s trådpool), och dessutom tryckpaketet (`app/tryck.py`) och
underlagets sidbilder (`routes_planning`).

Därför: ALLA vägar in i pdfium går genom `ensam()`. Låset är en RLock så att
nästlade anrop (tryck.foga_ihop → _sidor) inte låser sig själva. Håll aldrig
ett LLM-anrop eller annan lång väntan innanför — bara pdfium-arbetet.
"""
from __future__ import annotations

import contextlib
import threading

_LAS = threading.RLock()


@contextlib.contextmanager
def ensam():
    """Kör pdfium-arbetet ensamt i processen.

    Hela användningen ska ligga innanför, inte bara öppningen: dokumentet,
    sidorna och renderingen delar samma globala tillstånd, och en tråd som
    renderar medan en annan öppnar är precis kapplöpningen ovan.
    """
    with _LAS:
        yield
