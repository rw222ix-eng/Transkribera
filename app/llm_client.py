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

# ── Elementet läraren pekade på ──────────────────────────────────────────────
# Granskningen låter läraren klicka på en ruta i tavlan, en uppgift på bladet
# eller en rad i anteckningarna och sedan skriva vad som ska ändras. Klicket
# fastnade förr i webbläsaren: bara meningen gick till modellen, som fick gissa
# vilken av tjugo rutor «gör den kortare» handlade om — och ändrade en annan.
#
# Namnet är lärarens etikett («Formel 3», «Uppgift B») och finns inte i
# dokumentets JSON. Innehållet gör det, och det är därför innehållet som pekar
# ut elementet. Delas av tavlan, provet och anteckningarna: alla tre skriver om
# ett helt JSON-dokument och behöver samma mening om vad som ska röras.

# Taket på hur många element ett önskemål får gälla. Sex ryms i prompten utan
# att tränga ut dokumentet den ska skrivas om; fler mål än så är dessutom
# sällan ETT önskemål, utan flera som borde skickas var för sig.
MAX_MALEN = 6


def _malbit(mal) -> tuple[str, str, str] | None:
    """Ett måls tre delar — namn, JSON-innehåll, skärmtext — kapade som
    prompten ändå kapar dem. ``None`` när målet inte säger något alls.

    `text` läses som ett andra namn på `innehall`: canvasens lager har hetat
    båda, och ett mål som tappar sitt innehåll på vägen blir bara ett namn i
    prompten. Ett mål med `innehall` går exakt som förut."""
    if not isinstance(mal, dict):
        return None
    namn = str(mal.get("namn") or "").strip()
    innehall = " ".join(str(mal.get("innehall") or mal.get("text")
                            or "").split())[:300].strip()
    renderat = " ".join(str(mal.get("renderat") or "").split())[:600].strip()
    if not namn and not innehall and not renderat:
        return None
    return namn, innehall, renderat


def flera_mal(malen) -> list[dict]:
    """Målen när läraren markerat FLER ÄN ETT element — annars tom lista.

    Ett ensamt mål är inte flerval: då gäller enkelmålsvägen, och den ska bli
    byte för byte som förut hela vägen ut i prompten (testsvitens inspelade
    band är nycklade på promptens text). Därför är tröskeln två, och därför är
    den samma funktion i rutterna som i prompterna — ett andra ställe att
    räkna på hade glidit isär från det första."""
    if not isinstance(malen, (list, tuple)):
        return []
    ut = []
    for m in malen:
        if not isinstance(m, dict):
            continue
        bit = _malbit(m)
        if bit is None and not str(m.get("el") or "").strip():
            continue
        namn, innehall, renderat = bit or ("", "", "")
        ut.append({"el": str(m.get("el") or "").strip()[:60],
                   "namn": namn[:120], "innehall": innehall,
                   "renderat": renderat})
        if len(ut) >= MAX_MALEN:
            break
    return ut if len(ut) >= 2 else []


def uppradning(delar) -> str:
    """«a», «a och b», «a, b och c» — svensk uppräkning, inte en JSON-lista.
    Modellen läser en mening, och en mening med kommatecken och «och» i sig
    säger tydligare att det är FLERA saker som ska ändras."""
    delar = [d for d in delar if d]
    if len(delar) <= 1:
        return delar[0] if delar else ""
    return ", ".join(delar[:-1]) + " och " + delar[-1]


# Skärmtextens förklaring står EN gång även när målen är flera: den handlar om
# sättningen, inte om det enskilda elementet, och sex kopior av samma stycke är
# sex gånger promptutrymme för samma upplysning.
_SKARMEN_FLERA = (
    "Skärmtexten är rutan så som den STÅR PÅ SKÄRMEN. Det är den bilden läraren "
    "beskriver. Sättningen kan upprepa matematiken — en gång satt och en gång "
    "som LaTeX-källa — så dubbla formler och lösa dollartecken där behöver inte "
    "finnas i JSON-fältet.\n")


def malrad(mal: dict | None = None, malen=None) -> str:
    """En rad om elementet läraren pekade på, eller "" när hon inte pekade.

    `renderat` är rutans text SÅ SOM DEN STÅR PÅ SKÄRMEN. Den behövs för att
    läraren beskriver det hon SER, och skärmen och JSON:en är inte samma sak:
    KaTeX lämnar kvar sin egen källa i en MathML-annotation, så en formel står
    där två gånger — en gång satt och en gång som «x^2». «Det står ett
    dollartecken mitt i raden» gäller alltså något som inte finns i fältet, och
    utan den här raden letade modellen efter ett tecken som aldrig fanns.

    `malen` är flervalets lista: läraren kan markera flera element i canvasen
    och skicka ETT önskemål för dem alla. Först vid två mål byter raden form —
    ett ensamt mål ger exakt samma text som förut, byte för byte."""
    flera = flera_mal(malen)
    if flera:
        return _flera_malrader([_malbit(m) or ("", "", "") for m in flera])
    # Ett mål: kom det i listan (och `mal` saknas) duger det lika bra.
    en = _malbit(mal)
    if en is None and isinstance(malen, (list, tuple)):
        for m in malen:
            en = _malbit(m)
            if en is not None:
                break
    if en is None:
        return ""
    namn, innehall, renderat = en
    vad = f"«{namn}»" if namn else "ett element"
    om = f' — som innehåller: "{innehall}"' if innehall else ""
    # Bara när den säger något NYTT: är skärmtexten densamma som innehållet är
    # en andra kopia av den bara promptutrymme.
    sett = ""
    if renderat and renderat != innehall:
        sett = (f'\nSå här ser rutan ut på skärmen: "{renderat}". Det är den bilden '
                "läraren beskriver. Sättningen kan upprepa matematiken — en gång "
                "satt och en gång som LaTeX-källa — så dubbla formler och lösa "
                "dollartecken där behöver inte finnas i JSON-fältet.")
    return (f"Läraren PEKADE PÅ {vad}{om}.{sett} Önskemålet gäller det elementet: "
            "ändra det och låt allt annat i dokumentet stå oförändrat.\n")


def _flera_malrader(bitar) -> str:
    """Flervalets form: målen räknas upp i en mening och står sedan var för sig
    med sitt innehåll.

    En enda hopklistrad rad om fem element gick inte att läsa — modellen tog det
    första och lämnade resten. Numrerade rader är samma sak som listan läraren
    ser i canvasen, och löftet på slutet är HÅRT av samma skäl som i
    enkelmålsformen: prompten säger «låt allt annat stå», och provets väg håller
    det dessutom på riktigt (exam_gen.sammanfoga_riktat)."""
    namnen = uppradning([f"«{namn}»" if namn else "ett element"
                          for namn, _i, _r in bitar])
    rader = []
    skarm = False
    for i, (namn, innehall, renderat) in enumerate(bitar, 1):
        vad = f"«{namn}»" if namn else "ett element"
        om = f' — som innehåller: "{innehall}"' if innehall else ""
        sett = ""
        if renderat and renderat != innehall:
            sett = f' På skärmen: "{renderat}".'
            skarm = True
        rader.append(f"{i}. {vad}{om}.{sett}")
    return (f"Läraren PEKADE PÅ {namnen} — flera element på en gång:\n"
            + "\n".join(rader) + "\n"
            + (_SKARMEN_FLERA if skarm else "")
            + "Önskemålet gäller ALLA de elementen: genomför det i vart och ett "
              "av dem, och låt allt annat i dokumentet stå oförändrat.\n")


# Varvhistoriken — vad läraren redan bett om för DET HÄR utkastet.
#
# Omskrivningen fick förr en enda mening och inget minne. Tredje varvet
# «kortare än så» hade ingen «som så» att gå efter, och «lite mer som förra
# förslaget» var obegripligt — modellen såg bara dokumentet som det blev, inte
# vägen dit. Varje varv skrev därför om samma sak från noll, och läraren fick
# upprepa villkor hon redan ställt.
#
# Historiken är LÄRARENS EGNA meningar, i ordning, och inget annat: modellens
# svar står redan i dokumentet. Taket är satt för att ett långt arbetspass inte
# ska tränga ut själva dokumentet ur prompten.
MAX_VARV = 8
MAX_VARVTECKEN = 200


def varvrad(historik) -> str:
    """Rader om tidigare önskemål för utkastet, eller "" när det är första varvet."""
    if not isinstance(historik, (list, tuple)):
        return ""
    rader = []
    for post in historik:
        text = " ".join(str(post or "").split())[:MAX_VARVTECKEN].strip()
        if text:
            rader.append(text)
    if not rader:
        return ""
    rader = rader[-MAX_VARV:]           # de senaste — de äldsta är oftast avklarade
    punkter = "\n".join(f"{i}. {t}" for i, t in enumerate(rader, 1))
    return ("Läraren har redan bett om detta för det här utkastet, i ordning:\n"
            f"{punkter}\n"
            "De är genomförda i dokumentet ovan och ska INTE göras om — de står här "
            "för att det nya önskemålet kan bygga vidare på dem («kortare än så», "
            "«samma sak för nästa uppgift»). Bryt inte något av dem.\n\n")


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
         base_url: str | None = None,
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
             options: dict | None = None,
             response_format: dict | None = None,
             max_tokens: int | None = None) -> str:
    """En fråga, ett svar.

    ``options`` (temperatur) och ``max_tokens`` hörde till llama-serverns
    samplingsparametrar och har ingen motsvarighet i Claude Code — de tas emot
    och ignoreras hellre än att tvinga fram en ändring på tjugo anropsställen.
    """
    return claude_code.generate(prompt, system=system, token_cb=token_cb,
                                schema=_schema_ur(response_format))
