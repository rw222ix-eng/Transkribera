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

import re

# Rutorna är enradiga i UI:t men ingenting hindrar en inklistrad uppsats. Taket
# är satt så att ett par meningar alltid ryms hela — det är den formen fälten
# är gjorda för — utan att ett misstag kan tränga ut boken och förlagan.
MAX_TECKEN = 900
# Viktningsrutan bär sedan 2026-10-15 hela bladets plan («uppgift 1–5 är 4.1 i
# ordningen E, E, C, C, A, uppgift 6–10 …» med vad varje nivå övar), och NA26F:s
# 16/10 var 1 150 tecken: taket 900 kapade «Utan räknare: talen ska gå jämnt
# upp» och halva andra delen. En plan är fortfarande ett par meningar per del.
MAX_FOKUS = 1800


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
    t = _kapa(_ren(text), MAX_FOKUS)
    if not t:
        return ""
    return (
        "LÄRAREN OM VAD SOM SKA VÄGA TYNGST — hennes egen viktning av källorna "
        "ovan. Följ den framför din egen känsla för balans:\n"
        f"{t}"
    )


# ── PLANEN I VIKTNINGSRUTAN (NA26F 16/10, exam 260) ─────────────────────────
# Rickard skrev «Uppgift 1–5 repeterar 4.1 Koordinatsystemet …, ordning E, E,
# C, C, A. … Uppgift 6–10 är dagens nya avsnitt 4.2 …, ordning E, E, C, C, A».
# Rutan gick in i prompten som text, men skelettet var redan låst i
# grammatiken: E, E, E, E, E, E, C, E/C, C, C/A, och avsnittet var fritt. Jobb
# 1919 gav 4.2 som uppgift 4. En uttrycklig ordning är en PLAN och ska bli
# skelettet, inte en önskan bredvid det. Tolkningen nedan är medvetet snäv:
# bara det som går att läsa entydigt blir plan, allt annat står kvar som text.
_UPPG_RE = re.compile(
    r"\b[Uu]ppgift(?:erna)?\s+(\d{1,2})(?!\d)"
    r"(?:\s*(?:–|—|-|till)\s*(\d{1,2})(?!\d))?")
_AVSNITT_RE = re.compile(r"(?<![\d.,])(\d{1,2}\.\d{1,2})(?![\d.,]\d)")
_ORDNING_RE = re.compile(
    r"\bordning(?:en)?\s*:?\s*([ECA](?:\s*(?:,|och|→|->|–|-)\s*[ECA])*)"
    r"(?![A-Za-zÅÄÖåäö])")


def _nivaer(t: str) -> list[str]:
    m = _ORDNING_RE.search(t)
    return re.findall(r"[ECA]", m.group(1)) if m else []


def fokusplan(text, antal: int) -> list[dict] | None:
    """Lärarens plan per uppgift ur viktningsrutan: en lista med `antal`
    poster {"avsnitt": "4.1" | None, "niva": "E" | "C" | "A" | None}, eller
    None när rutan inte säger något om ordningen.

    Läses: «uppgift 1–5 …», «uppgifterna 6 till 10 …» och «uppgift 3 …» som
    början på en del som räcker till nästa sådan; i delen bokens första
    avsnittsnummer («4.1») och «ordning(en) E, E, C, C, A». Nivåerna gäller
    bara när de är lika många som uppgifterna i delen, annars är det en
    annan sorts mening. Utan någon del gäller en ensam «ordning …» hela
    bladet om den räcker precis till det."""
    t = _ren(text)
    if not t or antal < 1:
        return None
    plan = [{"avsnitt": None, "niva": None} for _ in range(antal)]
    traffar = list(_UPPG_RE.finditer(t))
    delar = []
    for i, m in enumerate(traffar):
        fran = int(m.group(1))
        till = int(m.group(2) or fran)
        slut = traffar[i + 1].start() if i + 1 < len(traffar) else len(t)
        if 1 <= fran <= till <= antal:
            delar.append((fran, till, t[m.end():slut]))
    if not delar:
        nv = _nivaer(t)
        if len(nv) != antal:
            return None
        for p, n in zip(plan, nv):
            p["niva"] = n
        return plan
    for fran, till, bit in delar:
        avs = _AVSNITT_RE.search(bit)
        nv = _nivaer(bit)
        if len(nv) != till - fran + 1:
            nv = [None] * (till - fran + 1)
        for j, n in zip(range(fran - 1, till), nv):
            if avs:
                plan[j]["avsnitt"] = avs.group(1)
            if n:
                plan[j]["niva"] = n
    if not any(p["avsnitt"] or p["niva"] for p in plan):
        return None
    return plan
