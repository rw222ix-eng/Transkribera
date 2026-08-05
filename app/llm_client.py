"""Språkmodellsanropen — numera Claude Code, inte en modell på datorn.

Filen hette en gång «streaming client for the local llama.cpp server» och bar en
egen HTTP-transport mot en GGUF som appen laddade ner, höll i VRAM och delade med
Whisper via GPU-arbitern. Allt det är borta: språkmodellsarbetet ligger hos Claude
Code (se app/claude_code.py) på lärarens prenumeration.

Vad som finns kvar här är PROMPTERNA — systemtexterna som gör svaren svenska,
källförankrade och renderbara — och de två funktionerna resten av appen redan
anropar (``chat`` och ``generate``). Signaturerna är oförändrade med flit: ett
tjugotal anropsställen i postprocess, chatten, sökningen, provet och planeringen
ska inte behöva veta att modellen bytt hus.

``model``- och ``base_url``-argumenten tas emot och ignoreras. Det finns ingen
modell att välja och ingen adress att peka på — valet är gjort, en gång.
"""
from __future__ import annotations
import json
from datetime import datetime
from typing import Callable

from app import claude_code

# Kvar för de anropsställen som fortfarande SKICKAR med en base_url. Pekar
# ingenstans: servern den pekade på (llama.cpp) finns inte längre, och ingen
# läser värdet.
BASE_URL = ""

# Stil- och formatregler som gör svaren konkreta, tydligt disponerade och med
# renderbar matematik (UI:t renderar Markdown + LaTeX). Delas av alla chattlägen.
_STYLE = (
    " Svara kort, konkret och rakt på sak med ett pragmatiskt språk — undvik "
    "svammel, inledande fraser och upprepningar. Disponera tydligt: korta stycken "
    "(tom rad emellan) och punktlistor när du räknar upp saker, samt **fetstil** "
    "sparsamt för nyckelbegrepp. Skriv ALL matematik i LaTeX — inline mellan "
    "enkla dollartecken $…$ och fristående uttryck mellan dubbla $$…$$ (använd "
    "\\frac, ^, _, \\sqrt, \\pi, \\cdot m.m.). Skriv aldrig matematik som vanlig "
    "text; skriv t.ex. $\\cos^2 x - \\sin^2 x$, inte \"cos^2x - sin^2x\"."
)

_CHAT_SYSTEM = (
    "Du är en hjälpsam svensk assistent som svarar på frågor om ett transkript. "
    "Svara ALLTID på svenska och använd aldrig något annat språk. Grunda dina svar "
    "i transkriptet nedan; säg till om något inte framgår av det." + _STYLE +
    "\n\nTRANSKRIPT:\n"
)

# Källförankrat läge: transkriptet skickas som numrerade segment ("[n] (mm:ss) text")
# och modellen instrueras att avsluta grundade påståenden med segmentnumret i
# hakparentes. UI:t parsar markörerna till klickbara citat med källpanel.
_CHAT_SYSTEM_CITED = (
    "Du är en hjälpsam svensk assistent som svarar på frågor om ett transkript. "
    "Svara ALLTID på svenska och använd aldrig något annat språk. Grunda dina svar "
    "i transkriptet nedan; säg till om något inte framgår av det.\n"
    "Transkriptet är uppdelat i numrerade segment på formen \"[n] (mm:ss) text\". "
    "KÄLLKRAV (obligatoriskt): varje påstående som bygger på transkriptet ska "
    "avslutas med segmentets nummer i hakparentes, t.ex. [3] eller [3, 7]. Det "
    "gäller även varje punkt i en punktlista eller numrerad lista — en punkt utan "
    "källmarkör är ofullständig. Exempel: \"- Formlerna härleds ur "
    "additionsformlerna [4]\". Använd bara nummer som finns i transkriptet, högst "
    "ett par segment per påstående, och skriv aldrig hakparenteser runt något "
    "annat än segmentnummer." + _STYLE +
    "\n\nTRANSKRIPT:\n"
)

# Kalenderförmågan i lektionschatten: modellen skapar/ändrar kalenderförslaget
# genom att avsluta svaret med en maskinläsbar rad som frontenden tolkar och
# döljer. Instruktionen läggs bara på när anroparen skickar calendar=True.
_SV_DAYS = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]


def _cal_instr(cal_event: dict | None) -> str:
    today = datetime.now()
    s = (
        "\n\nKALENDER: Användaren kan be dig föreslå eller ändra en kalenderhändelse "
        "(prov, läxförhör, inlämning, möte, påminnelse …). Du kan INTE själv lägga in "
        "något i kalendern — du lämnar bara ett FÖRSLAG som användaren måste godkänna "
        "med Lägg till-knappen. Påstå därför ALDRIG att något är inlagt, bokat eller "
        "klart. Arbetsgången har TVÅ steg. Välj steg så här: finns inget AKTUELLT "
        "FÖRSLAG nedan, och användaren har inte just besvarat dina frågor eller bett "
        "dig skapa direkt → STEG 1. Annars → STEG 2. Hoppa ALDRIG över STEG 1 för en "
        "ny händelse — även när önskemålet verkar tydligt.\n"
        "STEG 1 — FRÅGOR FÖRST (obligatoriskt före varje NY händelse): ställ 1–3 korta "
        "klargörande frågor som gör händelsen träffsäker och detaljerad (t.ex. vilken "
        "dag/tid som passar, exakt vad anteckningen ska innehålla, om den ska pågå "
        "flera dagar). Skriv en kort mening i löptext (t.ex. ”Ett par snabba frågor "
        "först, så blir påminnelsen rätt.”) och avsluta HELA svaret med exakt en rad:\n"
        '[KALENDERFRÅGOR] {"fragor": [{"q": "...", "alternativ": ["...", "..."]}]}\n'
        "2–4 korta alternativ per fråga, giltig JSON på en enda rad. Ett STEG 1-svar "
        "får ALDRIG innehålla en [KALENDERFÖRSLAG]-rad.\n"
        "STEG 2 — FÖRSLAGET: skriv först en kort mening i vanlig löptext som "
        "presenterar förslaget (t.ex. ”Här är ett förslag på en påminnelse "
        "tisdag–onsdag kl 15 — godkänn det nedan så läggs det in.”), och avsluta "
        "därefter HELA svaret med exakt en rad:\n"
        '[KALENDERFÖRSLAG] {"title": "...", "date": "YYYY-MM-DD", "time": "HH:MM", '
        '"end_date": null, "desc": "..."}\n'
        f"Idag är {_SV_DAYS[today.weekday()]} {today:%Y-%m-%d}. Datumet får ALDRIG "
        "ligga före idag — önskas en veckodag väljer du nästa kommande förekomst. "
        "Alla fält ska alltid med: "
        "vid en ändring, utgå från det aktuella förslaget nedan och behåll oförändrade "
        "fälts värden. end_date (YYYY-MM-DD) anges bara när händelsen sträcker sig över "
        "flera dagar, annars null. Anteckningen (desc) ska vara DETALJERAD och väva in "
        "användarens svar och önskemål ordentligt.\n"
        "För båda stegen gäller: raden ska ligga allra sist, vara giltig JSON på en "
        "enda rad, och du får inte nämna eller citera den i löptexten. Skriv någon av "
        "raderna ENDAST när användaren vill skapa eller ändra en händelse — aldrig "
        "annars."
    )
    if cal_event:
        s += ("\nAKTUELLT FÖRSLAG: " + json.dumps(cal_event, ensure_ascii=False) +
              "\nEtt aktuellt förslag finns alltså redan — ställ INGA nya frågor "
              "(aldrig STEG 1); tillämpa användarens ändringar direkt på förslaget.")
    return s


# Bildfrågor (inlästa boksidor, fotograferade uppgifter). Transkriptet är sällan
# relevant för en bildfråga, så systemtexten hålls kort.
_VISION_SYSTEM = (
    "Du är en hjälpsam svensk assistent som beskriver och svarar på frågor om "
    "bifogade bilder. Svara ALLTID på svenska och använd aldrig något annat språk." +
    _STYLE)


def is_running(base_url: str | None = None) -> bool:
    """Går det att fråga språkmodellen just nu?

    Förr: svarar llama-servern på /health. Nu: är Claude Code installerat OCH
    inloggat. Samma fråga för anroparen, ett annat hus.
    """
    s = claude_code.status()
    return bool(s["finns"] and s["inloggad"])


def _schema_ur(response_format: dict | None) -> dict | None:
    """{"type": "json_schema", "json_schema": {"schema": …}} → själva schemat.
    Formen kommer från llama-serverns grammatiktvång och används fortfarande av
    provet, tavlan och extraktionen."""
    if not response_format:
        return None
    return (response_format.get("json_schema") or {}).get("schema") or None


def chat(model: str, messages: list[dict], transcript: str = "",
         token_cb: Callable[[str], None] | None = None,
         base_url: str | None = None, think: bool = False,
         images: list[str] | None = None,
         reason_cb: Callable[[str], None] | None = None,
         cite: bool = False,
         calendar: bool = False, cal_event: dict | None = None) -> str:
    if images:
        return claude_code.chat(
            [{"role": m.get("role", "user"), "content": m.get("content", "")}
             for m in messages] or [{"role": "user", "content": "Beskriv bilden."}],
            system=_VISION_SYSTEM, token_cb=token_cb, bilder=images)
    system = (_CHAT_SYSTEM_CITED if cite else _CHAT_SYSTEM) + (transcript or "(tomt)")
    if calendar:
        system += _cal_instr(cal_event)
    return claude_code.chat(messages, system=system, token_cb=token_cb,
                            reason_cb=reason_cb)


def generate(model: str, prompt: str,
             token_cb: Callable[[str], None] | None = None,
             base_url: str | None = None, system: str | None = None,
             options: dict | None = None, think: bool = False,
             response_format: dict | None = None,
             max_tokens: int | None = None) -> str:
    """En fråga, ett svar.

    ``options`` (temperatur) och ``max_tokens`` hörde till llama-serverns
    samplingsparametrar och har ingen motsvarighet i Claude Code — de tas emot
    och ignoreras hellre än att tvinga fram en ändring på tjugo anropsställen.
    """
    return claude_code.generate(prompt, system=system, token_cb=token_cb,
                                schema=_schema_ur(response_format))
