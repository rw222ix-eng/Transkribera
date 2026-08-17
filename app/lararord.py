"""Lärarens egna ord — två rutor i steg 3 som ingen modell fick se.

Appen har byggt hela sitt källbygge på SPÅR: transkriptet säger vad klassen
frågade om, det rättade provet vad den föll på, boken vad som står på sidorna.
Det är starka källor, men de har ett hål: spelades lektionen inte in finns
ingen svårighet att följa upp, och då står tavlan utan det viktigaste läraren
vet. Hon var där. Hon såg kvadratkompletteringen inte sätta sig. Ingenstans i
appen fanns en plats att SÄGA det — «Vad ska väga tyngst?» var det närmaste,
och den rutan sparades på pappret utan att någonsin skickas med begäran.

Två block, samma regel: ett tomt fält får inte lämna ett spår i prompten. Står
det ingenting i rutan ska prompten vara ORD FÖR ORD den som gick i väg i går —
annars är varje inspelad kassett omspelningsmogen, och det kostar två vändor.
Därför returnerar båda funktionerna tom sträng på tomt fält, och anroparen
lägger bara till blocket när det finns något att lägga till.

Mönstret är förlagans (app/forlaga.py): en ren funktion som tar fältet som
frontenden lagrar det och skriver svensk prompttext, med ett tak så att en
lärare som klistrar in en hel lektionsanteckning inte äter kontexten.
"""
from __future__ import annotations

# Rutorna är enradiga i UI:t men ingenting hindrar en inklistrad uppsats. Taket
# är satt så att ett par meningar alltid ryms hela — det är den formen fälten
# är gjorda för — utan att ett misstag kan tränga ut boken och förlagan.
MAX_TECKEN = 900


def _ren(x) -> str:
    """En rad, normaliserade blanksteg. Fälten kommer från klienten och kan
    bära radbrytningar, dubbla mellanslag och None."""
    return " ".join(str(x or "").split())


def _kapa(text: str, tak: int = MAX_TECKEN) -> str:
    if len(text) <= tak:
        return text
    return text[:tak].rsplit(" ", 1)[0] + " […]"


def build_svart(text) -> str:
    """«Vad var svårt?» — lärarens egen iakttagelse ur lektionen som gick.

    Avsändaren står först och uttryckligen. Modellen möter samma fråga från
    flera håll — transkriptets svårigheter, provets utfall — och måste kunna
    skilja på ett maskinellt spår och läraren som säger vad hon såg. Det andra
    väger tyngre, och blocket säger det rent ut i stället för att hoppas på
    att ordningen räcker.
    """
    t = _kapa(_ren(text))
    if not t:
        return ""
    return (
        "LÄRARENS EGNA ORD OM VAD KLASSEN HADE SVÅRT FÖR — hon var där och såg "
        "det. Det här är inte en gissning ur ett transkript eller en siffra ur "
        "en rättning utan förstahandsuppgiften, och den väger tyngst av "
        "svårighetskällorna:\n"
        f"{t}\n"
        "Låt det styra VAD som tas upp och hur mycket plats det får: det som "
        "var svårt ska få tid, ett eget exempel och en väg in — inte en rad i "
        "förbifarten. Skriv ingenting om att läraren har sagt det; pappret är "
        "till eleverna."
    )


def build_fokus(text) -> str:
    """«Vad ska väga tyngst?» — viktningen mellan de valda källorna.

    Rutan har funnits i steg 3 hela tiden och sparats på dokumentet, men aldrig
    nått servern: samma tomma löfte som förlagan var före app/forlaga.py, och
    planen skrev till och med «Väger källorna» om den. Blocket står SIST bland
    källorna, närmast uppdraget — det är en dom över allt som står ovanför och
    kan inte fällas innan källorna är lästa.
    """
    t = _kapa(_ren(text))
    if not t:
        return ""
    return (
        "LÄRAREN OM VAD SOM SKA VÄGA TYNGST — hennes egen viktning av källorna "
        "ovan. Följ den framför din egen känsla för balans:\n"
        f"{t}"
    )
