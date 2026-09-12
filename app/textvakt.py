"""Tankstrecksvakten — EN regel, fyra papper.

Läraren har bett om det sex gånger på fyra papper under en enda vecka
(spårdata 1–6 sep 2026, spardata/forslag/2026-09-06.md): «skriv kortare utan
em dash», «kort och utan em dash». Varje gång kostade det ett omskrivningsvarv
som aldrig skulle ha behövts — prompten BAD redan om det, på tre ställen i
exam_gen och ett i lesson_board, och en prompt driver.

Anteckningarna löste det i augusti genom att MÄTA kravet i stället
(app/notes_gen: felkoden gick in i reparationsrundan som ett schemafel), och
det höll: den skarpa inspelningen bär inte ett enda tankstreck. Den här modulen
är samma vakt, bruten ur notes_gen så att provet, arbetsbladet, gruppuppgiften
och tavlan får den också. Felformen är den gemensamma ({path, code, message})
och felkoden är densamma på alla fyra papper, så reparationsrundan i
exam_gen/lesson_board/notes_gen tar emot den utan att veta var den kom ifrån.

VAD SOM INTE ÄR ETT TANKSTRECK:

* Bindestrecket (``-``, U+002D). «kurs-PM» och «e-post» rörs aldrig, och
  matematikens minus är samma tecken — därför kan vakten gå på uppgiftstexter
  och lösningar utan att bråka om räkningen.
* Sifferspannet «s. 27–30», «uppg. 1218–1227». Det är INTE lärarens em dash
  utan svenskt intervalltecken, och på tavlan skriver modellen det för att
  prompten uttryckligen ber om det («Boken s. 27–30, uppg. 1218–1227»,
  lesson_board regel 2 och few-shot-exemplen). Fälldes det skulle vakten slåss
  med prompten varv efter varv. Undantaget är smalt med flit: bara en en dash
  KLÄMD MELLAN TVÅ SIFFROR, aldrig med mellanslag omkring och aldrig em dash.
  Anropare som inte har några sidhänvisningar (anteckningarna) låter bli att
  be om det, och får den gamla stränga regeln.
"""
from __future__ import annotations

import re

# Felkoden. Samma sträng i hela appen: reparationsprompten i exam_gen förklarar
# den vid namn, och klienten färgar den som vilket annat fynd som helst.
KOD = "tankstreck"

_NAMN = {"–": "en dash (–)", "—": "em dash (—)"}
_TANKSTRECK_RE = re.compile("[–—]")
# Sifferspannet, se modulens docstring. Lookaround i stället för grupper: det
# som klipps bort ska inte kunna äta upp en siffra som ett NÄSTA spann behöver.
_SPANN_RE = re.compile(r"(?<=\d)–(?=\d)")


def finn(text: str | None, *, tillat_spann: bool = False) -> str | None:
    """Första tankstrecket i `text`, eller None. Ett fynd per sträng räcker
    som besked — modellen ska skriva om meningen, inte byta ut ett tecken."""
    t = text or ""
    if tillat_spann:
        t = _SPANN_RE.sub(" ", t)
    m = _TANKSTRECK_RE.search(t)
    return m.group(0) if m else None


def meddelande(path: str, tecken: str) -> str:
    """Beskedet till modellen. Det säger vad som ska GÖRAS, inte bara vad som
    är fel — en reparationsrunda som bara får veta att något är förbjudet
    byter gärna ut tecknet mot ett annat tankstreck."""
    return (f"{path} innehåller ett {_NAMN[tecken]}. "
            "Skriv om meningen utan tankstreck — dela den i "
            "två, eller använd punkt eller kolon.")


def granska(texter, *, tillat_spann: bool = False) -> list[dict]:
    """(sökväg, text)-par → fellista i appens gemensamma felform.

    Anroparen äger sökvägarna: de ska peka ut fältet i DOKUMENTETS språk
    («uppgift 3.bedomning», «boards[1].columns[0].sections[7].text»), för det
    är den sökvägen modellen ska hitta i JSON:en den får tillbaka."""
    fel: list[dict] = []
    for path, text in texter:
        tkn = finn(text, tillat_spann=tillat_spann)
        if tkn:
            fel.append({"path": path, "code": KOD,
                        "message": meddelande(path, tkn)})
    return fel
