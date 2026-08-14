"""Lektionstavlor — promptbygge och LLM-generering med auto-reparation (Fas 1).

Flödet (spec §1, "två försvarslinjer mot layoutfel"):

1. :func:`generate_board` — bygger prompten (kurs/klass/moment +
   tavelkonventioner + few-shots + minneskontext), frågar språkmodellen med
   schemat i prompten (``whiteboard_spec.to_response_format()``) och validerar
   deterministiskt. Schemafel/regelfel skickas tillbaka till modellen som
   korrigeringsprompt i upp till :data:`MAX_ROUNDS` rundor.
2. :func:`repair_board` — samma loop men driven av klientens renderings-
   varningar (``[WB] …`` via POST /api/planning/render-report).
3. :func:`refine_board` — chatt-iteration ("byt exempel 2 …") ovanpå en
   befintlig tavla; resultatet valideras och auto-repareras på samma sätt.

LLM-anropet är injicerbart (``llm=``) så testerna kör med stubb; skarpa
anrop går via :func:`app.llm_client.generate` under GPU-arbitern
(rutterna i app/web/routes_planning.py äger arbiterlåset).
"""
from __future__ import annotations

import copy
import json
import math
import re
from typing import Callable

from app import llm_client
from app import whiteboard_spec as ws

MAX_ROUNDS = 3          # totalt antal LLM-rundor inkl. första genereringen
# Bench Fas 2: en tabelltung tavla trunkerades vid 6k tokens → ogiltig JSON.
BOARD_MAX_TOKENS = 9_000

SYSTEM = (
    "Du är en erfaren svensk matematiklärare som skriver färdiga lektionstavlor "
    "— det läraren annars hade skrivit för hand på tavlan vid lektionens start. "
    "Du svarar ALLTID med giltig JSON enligt schemat (WB-JSON v1), ingenting "
    "annat. All text är på svenska. "
    "INTEGRITET: skriv ALDRIG elevers namn — använd initialer om det behövs."
)

# Svenska tavelkonventioner + motorns invarianter (designprojektets SKILL.md).
INSTRUCTION = (
    "Skriv en lektionstavla som JSON med \"title\" och \"boards\" (exakt två "
    "tavlor: vänster 900×780 för teori/disposition, höger 1800×780 med två "
    "\"columns\" för exempel).\n"
    "Regler:\n"
    "- Decimalkomma i all läsbar text och LaTeX (skriv 4{,}58 — aldrig 4.58).\n"
    "- Matematik skrivs ALLTID i math-sektioner (fältet latex) — aldrig inne "
    "i text-, list- eller tabellsträngar, och aldrig med $-tecken. Kom ihåg "
    "att backslash måste dubbleras i JSON: skriv \\\\frac{1}{2}, \\\\sqrt{2}, "
    "\\\\sin — annars blir kommandona trasiga.\n"
    "- Vinklar heter \\u03b1, \\u03b2, \\u03b3 eller v. Sidor får gemena namn (a, b, c), "
    "hörn versala (A, B, C). Hörnetiketter placeras med points[].outward, som "
    "är en PUNKT [x, y] inne i figuren (oftast dess mitt) — etiketten knuffas "
    "bort från den och hamnar utanför figuren. Aldrig true/false: en skarp "
    "körning skrev outward: true och kostade en hel reparationsrunda.\n"
    "- Färger anges ENDAST med namnen black, blue, red, green, orange, purple.\n"
    "- Grafkurvor skrivs som uttryckssträngar i plots[].expr, t.ex. "
    "\"x^2 - 2*x + 1\" eller \"sin(x)\" (tillåtet: tal, x, + - * / ^, "
    "parenteser, sin cos tan sqrt log ln exp abs, pi, e). Decimalpunkt är ok "
    "ENDAST inuti expr.\n"
    "- En vinkelbåge (arcs) i ett polygonhörn MÅSTE ha interior: en punkt "
    "inuti figuren.\n"
    "- Vektorer ritas med arrows, aldrig som polygoner.\n"
    "- Geometriska cirklar (t.ex. enhetscirkeln) ritas ALLTID som polygon med "
    "minst 48 parametriska punkter — aldrig med plots — och grafen måste vara "
    "kvadratisk: width = height och lika stora xRange/yRange, annars blir "
    "cirkeln en ellips.\n"
    "- Håll alla punkter/texter inom grafens xRange/yRange.\n"
    "- Breddgränser (viktigt — annars ryms inte innehållet): grafer, figurer "
    "och tabeller högst 650 px breda på vänstertavlan och högst 800 px i en "
    "kolumn på högertavlan. Hörnetiketter på figurer sätts med "
    "shape.labels, som ENDAST har nycklarna top, left, right, bottom, inside.\n"
    "- Var koncis: högst ~7 sektioner per tavla/kolumn (vänstertavlan får bli "
    "~9 när agendan och dividern räknas med), korta math-rader "
    "(dela långa uträkningar på flera math-sektioner), tabeller högst "
    "4 kolumner × 5 rader. Text-sektioner max ~80 tecken och listpunkter "
    "max ~70 — dela längre resonemang i flera sektioner. Hellre färre, "
    "tydliga steg än trängsel — motorn skalar innehållet automatiskt.\n"
    # DRAMATURGIN. Läraren pekade ut Professor Leonards genomgång av räta
    # linjen (Calculus 1, Lecture 0.1, 0:00–17:30) som förebild för hur ett
    # pass ska kännas: han öppnar med dagens resa, VÄCKER begreppet med en
    # fråga till klassen ("what do you know about lines?"), säger vad det är
    # på vardagsspråk EN gång, ritar en generisk linje med två generiska
    # punkter och UPPFINNER lutningsformeln ur figuren — exemplen kommer
    # först därefter, och eleverna prövar innan han löser dem.
    #
    # Ordningen är alltså inte pynt: den är det som gör tavlan möjlig att
    # PEKA på medan man pratar. Kraven nedan är den ordningen, inget mer.
    "Dramaturgi — tavlan ska gå att gå igenom uppifrån och ned som en "
    "berättelse där varje del föder nästa; den är det läraren pekar på medan "
    "hen pratar, inte ett manus.\n"
    "Vänstertavlans ordning är obligatorisk:\n"
    "1. Rubriken.\n"
    "2. Agenda: en list med 3–4 punkter, högst ~5 ord per punkt, vardaglig "
    "svenska — vad klassen ska GÖRA i dag, inte facktermer.\n"
    "3. En divider-sektion (strecket under agendan).\n"
    "4. Öppningsfrågan: en callout med EN rad, ställd till klassen och riktad "
    "mot det de redan kan (\"Vad vet ni om …?\"). Begreppet ska väckas, inte "
    "presenteras.\n"
    "5. Högst EN mening vardagsspråk om vad begreppet är — sedan inga fler "
    "meningar.\n"
    "6. En generisk figur: shape eller graph med bokstäver som beteckningar "
    "(a, b, c, x_1, y_1), aldrig konkreta tal, gärna med arrows och korta "
    "etiketter att peka på. Saknar momentet naturlig figur skrivs den "
    "generiska uppställningen i stället — bokstäver, inte siffror.\n"
    "7. Formeln — EFTER figuren, aldrig före. Formeln ska se ut att komma ur "
    "figuren. Står flera formler på tavlan ska de stå i den ordning de "
    "härleds, så att läraren kan peka sig fram genom kedjan; ingenting får "
    "dyka upp från ingenstans.\n"
    "8. \"Vanligt fel:\"-callouten sist.\n"
    "Skriv INTE något klockslag på tavlan — tiden lägger systemet dit.\n"
    "Högertavlan är antingen EXEMPEL (huvudregeln) eller ett FALLGALLERI:\n"
    "- Exempel: 1–2 stycken (\"Exempel 1\", \"Exempel 2\"), situationsraden "
    "högst två rader, lösningen i korta math-steg, svaret i en ruta. Exempel "
    "hör hemma här — aldrig på vänstertavlan.\n"
    "- Fallgalleri (när momentet är en sats med klassiska fall, t.ex. "
    "randvinkelsatsen): 3–4 färdiga figurer, var och en med fallets namn och "
    "EN kort rad om vad det säger. Inga uträkningar — läraren pratar och "
    "pekar.\n"
    # TEXTBUDGETEN. Läraren körde en lektion med två egengjorda tavlor och sa
    # efteråt att den ena var fylld med text hon aldrig skrev upp på plats: det
    # är för mycket att skriva. Tavlan ska bära det som FAKTISKT SKRIVS under
    # lektionen — inte allt som sägs. Regeln ovan säger hur långt ett stycke får
    # vara; den här säger hur mycket det får vara.
    "Textbudget — tavlan visar det som SKRIVS, inte allt som sägs:\n"
    "- En text-sektion är EN rad, ~60 tecken. Skriv aldrig löpande prosa på en "
    "tavla: ingen lärare hinner skriva upp den, och ingen elev hinner av.\n"
    "- Hellre math, tabell och figur än text. Ett steg som går att skriva som "
    "en formel skrivs som en formel.\n"
    "- Har lektionen flera exempel eller fall som ska jämföras: samla dem i EN "
    "table-sektion, en rad per fall, med de korta kolumnerna kontext, uttryck, "
    "typ → metod och svar. Den tabellen är genomgångens samlingspunkt — den "
    "fylls i tillsammans med klassen. Håll cellerna korta (~25 tecken) och sätt "
    "INTE cellW: motorn ger varje kolumn bredden ur dess innehåll.\n"
    # Innehållskravet, inte ett motorkrav. Det står sist och för sig: en tavla
    # kan vara felfri mot schemat och ändå tiga om det eleverna faktiskt gör
    # fel. Kravet är att felet SKRIVS UT, inte att det undviks.
    "Vanliga fel (innehåll, inte form):\n"
    "- Tänk ut 2–3 fel som elever verkligen gör på just det här momentet — "
    "teckenfel vid negativa tal, glömd eller fel enhet, en tappad rot, fel "
    "prioriteringsordning, avrundning för tidigt, förväxlade begrepp. Ett "
    "moment där eleven inte kan göra fel finns inte.\n"
    "- Vänstertavlan SKA ha en callout i rött som inleds med texten "
    "\"Vanligt fel:\" och visar felet konkret — helst det felaktiga ledet i en "
    "math-sektion — och säger med en kort mening varför det blir fel. En "
    "förmaning räcker inte: eleven ska känna igen sitt eget misstag.\n"
    "- Välj exemplen så att MINST ETT går rakt genom en av fallgroparna. Är "
    "teckenfel fallgropen ska ett exempel ha en negativ koefficient; är "
    "enheter fallgropen ska ett exempel byta enhet på vägen.\n"
)

# Åtgärdsråd som följer med reparationsprompten — motorns varningstexter
# säger VAD som är fel, det här säger HUR modellen brukar kunna rätta det.
REPAIR_HINTS = (
    "Så åtgärdar du vanliga problem:\n"
    "- 'innehållet ryms inte (bredd …)': korta de längsta text- och "
    "math-raderna i den tavlan/kolumnen, minska width på grafer/figurer/"
    "tabeller (högst 650 px på vänstertavlan), eller flytta en sektion till "
    "den andra kolumnen.\n"
    "- 'innehållet ryms inte (höjd …)': ta bort eller korta sektioner — "
    "hellre färre, tydliga steg.\n"
    # Vänstertavlan bär sedan dramaturgin både agenda och divider, och då är
    # den första utvägen ur trängsel att stryka det som gör ordningen läsbar.
    # Den utvägen är stängd: agendan och öppningsfrågan är genomgångens ingång.
    "- ryms inte på VÄNSTERTAVLAN: korta agendan (färre och kortare punkter) "
    "och begreppsdelen — färre formler, mindre figur, kortare vanligt "
    "fel-callout. Stryk aldrig dividern eller öppningsfrågan, och flytta "
    "aldrig exempel dit.\n"
    "- 'element-överlapp': öka gapAfter på sektionen före, korta texterna, "
    "eller ta bort annotations som ligger ovanpå annat innehåll.\n"
    "- 'tavlan bär N tecken löpande text': stryk meningar som bara ska SÄGAS, "
    "skriv om räknesteg som math-sektioner, och slå ihop flera exempel eller "
    "fall till EN table-sektion med korta celler. Ta bort hela stycken hellre "
    "än att korta varje mening — det är mängden som är felet, inte längden.\n"
)

def _cirkel(cx: float, cy: float, r: float, n: int = 48) -> list[list[float]]:
    """Parametrisk cirkel till fallgalleriets figurer. Motorn ritar cirklar som
    polygon med minst 48 punkter — aldrig med plots — och grafen måste vara
    kvadratisk (width = height, lika stora xRange/yRange), annars blir cirkeln
    en ellips. Punkterna räknas här i stället för att skrivas ut för hand:
    few-shoten ska visa mönstret, och 48 handskrivna decimaltal visar inget."""
    return [[round(cx + r * math.cos(2 * math.pi * i / n), 3),
             round(cy + r * math.sin(2 * math.pi * i / n), 3)]
            for i in range(n)]


# Few-shots — kompletta, validerade WB-JSON v1-dokument (testerna kör dem
# genom validate_board_json). En utan graf, en med graf/expr, en med
# sammanfattningstabell och en med fallgalleri, så modellen ser alla mönstren.
# ALLA fyra har samma vänstertavla i formen: rubrik → agenda → divider →
# öppningsfråga → en mening → figur → formel → vanligt fel. Prompttext utan
# few-shot-stöd följs dåligt; det är shotarna som lär ut dramaturgin.
FEW_SHOTS: list[tuple[str, dict]] = [
    (
        "Ma1b, klass 9A — Pythagoras sats (introduktion)",
        {
            "title": "Pythagoras sats",
            "boards": [
                {
                    "width": 900, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 40},
                    "chrome": "aluminium", "tray": True, "name": "vanster",
                    "sections": [
                        {"kind": "heading", "text": "Pythagoras sats", "size": 34,
                         "underline": {"color": "red", "amplitude": 2, "thickness": 3,
                                       "reserve": 14}, "gapAfter": 16},
                        # Agendan: dagens resa i vardagliga ord, inte facktermer.
                        {"kind": "list", "bullet": "–", "size": 19, "gap": 4,
                         "indent": 22, "items": [
                             "Vad vi vet om trianglar",
                             "Vi bygger formeln själva",
                             "Två exempel att räkna"],
                         "gapAfter": 12},
                        {"kind": "divider", "width": 620, "gapAfter": 16},
                        # Öppningsfrågan: begreppet väcks ur klassen, det
                        # presenteras inte.
                        {"kind": "callout", "color": "blue", "fillOpacity": 0.06,
                         "padding": 12, "children": [
                             {"kind": "text",
                              "text": "Vad vet ni om rätvinkliga trianglar?",
                              "size": 21, "color": "blue", "weight": 700}],
                         "gapAfter": 14},
                        {"kind": "text",
                         "text": "Längsta sidan ligger mitt emot räta vinkeln.",
                         "size": 20, "gapAfter": 12},
                        # Figuren står FÖRE formeln och bär bara bokstäver:
                        # formeln ska se ut att komma ur den (Leonard-principen).
                        {"kind": "shape", "type": "right-triangle",
                         "width": 250, "height": 175,
                         "labels": {"left": "a", "bottom": "b", "right": "c",
                                    "inside": "v"}, "gapAfter": 14},
                        {"kind": "math", "latex": "a^2 + b^2 = c^2", "size": 30,
                         "color": "blue", "gapAfter": 16},
                        {"kind": "callout", "color": "red", "fillOpacity": 0.06,
                         "padding": 12, "children": [
                             {"kind": "text", "text": "Vanligt fel:", "size": 18,
                              "color": "red", "gapAfter": 4},
                             {"kind": "math",
                              "latex": "c^2 = a^2 + b^2 \\Rightarrow c = a + b",
                              "size": 19, "color": "red", "gapAfter": 4},
                             {"kind": "text",
                              "text": "Roten ur en summa är inte summan av rötterna.",
                              "size": 17, "color": "red"}]},
                    ],
                },
                {
                    "width": 1800, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 30},
                    "chrome": "aluminium", "tray": True, "name": "hoger",
                    "columns": [
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Exempel 1", "size": 28,
                             "underline": {"color": "blue"}, "gapAfter": 14},
                            {"kind": "text",
                             "text": "Beräkna hypotenusan c om a = 3 och b = 4.",
                             "size": 20, "gapAfter": 12},
                            {"kind": "math", "latex": "c^2 = 3^2 + 4^2",
                             "size": 22, "gapAfter": 6},
                            {"kind": "math", "latex": "c^2 = 9 + 16 = 25",
                             "size": 22, "gapAfter": 6},
                            {"kind": "math", "latex": "c = \\sqrt{25} = 5",
                             "size": 24, "color": "green", "gapAfter": 18},
                            {"kind": "shape", "type": "right-triangle",
                             "width": 220, "height": 170,
                             "labels": {"left": "a = 3", "bottom": "b = 4",
                                        "right": "c = 5"}},
                        ]},
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Exempel 2", "size": 28,
                             "underline": {"color": "blue"}, "gapAfter": 14},
                            {"kind": "text",
                             "text": "En stege på 5 m lutar mot en vägg. Foten är "
                                     "2 m från väggen. Hur högt når stegen?",
                             "size": 19, "gapAfter": 12},
                            {"kind": "math", "latex": "h^2 + 2^2 = 5^2",
                             "size": 22, "gapAfter": 6},
                            {"kind": "math", "latex": "h^2 = 25 - 4 = 21",
                             "size": 22, "gapAfter": 6},
                            {"kind": "math",
                             "latex": "h = \\sqrt{21} \\approx 4{,}58 \\text{ m}",
                             "size": 22, "color": "green", "gapAfter": 14},
                            {"kind": "callout", "color": "blue",
                             "fillOpacity": 0.06, "padding": 10, "children": [
                                 {"kind": "text",
                                  "text": "Svar: stegen når ca 4,58 m upp.",
                                  "size": 18, "color": "blue"}]},
                        ]},
                    ],
                },
            ],
        },
    ),
    (
        "Ma2b, klass NA23 — Andragradsfunktioner: graf och minimipunkt",
        {
            "title": "Andragradsfunktioner",
            "boards": [
                {
                    "width": 900, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 40},
                    "chrome": "aluminium", "tray": True, "name": "vanster",
                    "sections": [
                        {"kind": "heading", "text": "Andragradsfunktioner", "size": 32,
                         "underline": {"color": "red"}, "gapAfter": 14},
                        {"kind": "list", "bullet": "–", "size": 19, "gap": 4,
                         "items": [
                             "Vad grafen berättar",
                             "Var kurvan vänder",
                             "Vi skissar en kurva"],
                         "gapAfter": 12},
                        {"kind": "divider", "width": 620, "gapAfter": 14},
                        {"kind": "callout", "color": "blue", "fillOpacity": 0.06,
                         "padding": 12, "children": [
                             {"kind": "text",
                              "text": "Vad vet ni om grafen till x²?",
                              "size": 21, "color": "blue", "weight": 700}],
                         "gapAfter": 12},
                        {"kind": "text",
                         "text": "Kurvan vänder i en punkt och är symmetrisk.",
                         "size": 20, "gapAfter": 10},
                        # Figuren först: symmetrilinjen SYNS innan den skrivs
                        # som formel. Generisk kurva — exemplets tal står till
                        # höger, aldrig här.
                        {"kind": "graph", "width": 300, "height": 300,
                         "xRange": [-4, 2], "yRange": [-3, 3],
                         "grid": False, "axes": True, "gridStep": 1,
                         "xLabel": "x", "yLabel": "y",
                         "plots": [{"expr": "0.5*(x + 1)^2 - 2", "color": "red",
                                    "thickness": 2}],
                         "arrows": [{"from": [-1, -3], "to": [-1, 3],
                                     "color": "blue", "dashed": True,
                                     "headSize": 0}],
                         "texts": [{"x": -0.8, "y": 2.2, "text": "symmetrilinje",
                                    "size": 15, "color": "blue",
                                    "anchor": "start"}],
                         "points": [{"x": -1, "y": -2, "color": "green"}],
                         "gapAfter": 12},
                        {"kind": "math", "latex": "f(x) = ax^2 + bx + c", "size": 24,
                         "color": "blue", "gapAfter": 8},
                        {"kind": "math", "latex": "x = -\\frac{b}{2a}", "size": 24,
                         "color": "blue", "gapAfter": 14},
                        {"kind": "callout", "color": "red", "fillOpacity": 0.06,
                         "padding": 12, "children": [
                             {"kind": "text", "text": "Vanligt fel:", "size": 18,
                              "color": "red", "gapAfter": 4},
                             {"kind": "text",
                              "text": "x = 2 är symmetrilinjen, inte minimipunkten.",
                              "size": 17, "color": "red", "gapAfter": 4},
                             {"kind": "text",
                              "text": "Sätt in x i f(x) — punkten har två tal.",
                              "size": 17, "color": "red"}]},
                    ],
                },
                {
                    "width": 1800, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 30},
                    "chrome": "aluminium", "tray": True, "name": "hoger",
                    "columns": [
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Exempel", "size": 28,
                             "underline": {"color": "blue"}, "gapAfter": 14},
                            {"kind": "text",
                             "text": "Skissa f(x) = x² − 4x + 3 och ange minimipunkten.",
                             "size": 20, "gapAfter": 10},
                            {"kind": "math", "latex": "x = -\\frac{-4}{2} = 2",
                             "size": 22, "gapAfter": 6},
                            {"kind": "math", "latex": "f(2) = 4 - 8 + 3 = -1",
                             "size": 22, "gapAfter": 6},
                            {"kind": "math",
                             "latex": "\\text{Minimipunkt } (2, -1)",
                             "size": 22, "color": "green"},
                        ]},
                        {"weight": 1, "sections": [
                            {"kind": "graph", "width": 520, "height": 380,
                             "xRange": [-1, 5], "yRange": [-2, 4],
                             "grid": True, "axes": True, "gridStep": 1,
                             "xLabel": "x", "yLabel": "y",
                             "plots": [{"expr": "x^2 - 4*x + 3", "color": "red",
                                        "thickness": 2}],
                             "points": [{"x": 2, "y": -1, "color": "green",
                                         "label": "(2, -1)", "labelGap": 18}],
                             "ticks": [{"axis": "x", "at": 1, "label": "1"},
                                       {"axis": "x", "at": 3, "label": "3"}]},
                        ]},
                    ],
                },
            ],
        },
    ),
    # ── Destillat ur lärarens egen tavla (docs/forlagor/ ─────────────────────
    # activity_text_to_equation.html, HÖGRA tavlan). Formen, inte innehållet:
    # situationsruta på högst två rader → uppställning i få steg →
    # klassificeringsfrågan med ETT svar på en rad → lösningen i tre mattesteg →
    # svarsruta → SAMMANFATTNINGSTABELLEN.
    #
    # Tabellen är själva poängen. Grupperna löser först var för sig, sedan löser
    # klassen uppgifterna tillsammans på tavlan och tabellen fylls i gemensamt —
    # det är lektionens samlingspunkt, och den läraren är stoltast över.
    #
    # Momentet är MEDVETET ett annat än förlagans (som handlar om exponential-
    # mot potensekvationer): modellen ska härma formen, inte skriva av
    # innehållet. Vänstra tavlan är destillerad ur ingenting — förlagans var
    # fylld med text läraren aldrig skrev upp, och den är kort här med flit.
    (
        "Ma3c, klass NA25 — Derivera: vilken regel gäller?",
        {
            "title": "Vilken deriveringsregel?",
            "boards": [
                {
                    "width": 900, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 40},
                    "chrome": "aluminium", "tray": True, "name": "vanster",
                    "sections": [
                        {"kind": "heading", "text": "Vilken regel?", "size": 32,
                         "underline": {"color": "red", "amplitude": 2,
                                       "thickness": 3, "reserve": 16},
                         "gapAfter": 14},
                        {"kind": "list", "bullet": "–", "size": 19, "gap": 4,
                         "items": ["Reglerna vi redan kan",
                                   "Se hur uttrycket är byggt",
                                   "Ett exempel tillsammans"],
                         "gapAfter": 12},
                        {"kind": "divider", "width": 620, "gapAfter": 14},
                        # Öppningsfrågan: ett beslut som ska väckas ur klassen,
                        # inte en förklaring som ska tas emot.
                        {"kind": "callout", "color": "blue", "fillOpacity": 0.06,
                         "padding": 12, "children": [
                             {"kind": "text",
                              "text": "Vilka deriveringsregler minns ni?",
                              "size": 21, "color": "blue", "weight": 700}],
                         "gapAfter": 12},
                        {"kind": "text",
                         "text": "Regeln väljs efter hur uttrycket är byggt.",
                         "size": 20, "gapAfter": 10},
                        # Momentet har ingen naturlig figur — då är den
                        # generiska UPPSTÄLLNINGEN figuren, och formlerna
                        # kommer ur den.
                        {"kind": "list", "bullet": "–", "size": 19, "gap": 6,
                         "items": ["Ren potens → potensregeln",
                                   "Två faktorer → produktregeln",
                                   "Funktion i funktion → kedjeregeln"],
                         "gapAfter": 16},
                        {"kind": "math", "latex": "(uv)' = u'v + uv'",
                         "size": 24, "color": "blue", "gapAfter": 8},
                        {"kind": "math", "latex": "f(g(x))' = f'(g)\\cdot g'",
                         "size": 24, "color": "blue", "gapAfter": 18},
                        {"kind": "callout", "color": "red", "fillOpacity": 0.06,
                         "padding": 12, "children": [
                             {"kind": "text", "text": "Vanligt fel:", "size": 18,
                              "color": "red", "gapAfter": 4},
                             {"kind": "math",
                              "latex": "(x^2\\sin x)' = 2x\\cos x",
                              "size": 19, "color": "red", "gapAfter": 4},
                             {"kind": "text",
                              "text": "Faktorerna deriveras var för sig.",
                              "size": 17, "color": "red"}]},
                    ],
                },
                {
                    "width": 1800, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 30},
                    "chrome": "aluminium", "tray": True, "name": "hoger",
                    "columns": [
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Exempel A", "size": 28,
                             "underline": {"color": "blue"}, "gapAfter": 12},
                            # Situationsrutan: två rader, aldrig fler.
                            {"kind": "callout", "color": "black",
                             "fillOpacity": 0.03, "padding": 10, "children": [
                                 {"kind": "text",
                                  "text": "Derivera funktionen nedan.",
                                  "size": 20}], "gapAfter": 14},
                            {"kind": "math", "latex": "f(x) = x^2\\sin x",
                             "size": 26, "gapAfter": 14},
                            # Klassificeringsfrågan — och svaret på EN rad.
                            {"kind": "text", "text": "Hur är den byggd?",
                             "size": 21, "weight": 700, "gapAfter": 4},
                            {"kind": "text",
                             "text": "Två faktorer → produktregeln",
                             "size": 20, "gapAfter": 14},
                            {"kind": "math", "latex": "u = x^2 \\qquad v = \\sin x",
                             "size": 22},
                        ]},
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Lösning", "size": 28,
                             "underline": {"color": "blue"}, "gapAfter": 12},
                            {"kind": "math", "latex": "u' = 2x \\qquad v' = \\cos x",
                             "size": 22, "gapAfter": 8},
                            {"kind": "math",
                             "latex": "f' = 2x\\sin x + x^2\\cos x",
                             "size": 24, "color": "green", "gapAfter": 14},
                            {"kind": "callout", "color": "red",
                             "fillOpacity": 0.06, "padding": 10, "children": [
                                 {"kind": "text",
                                  "text": "Svar: f' = 2x sin x + x² cos x",
                                  "size": 19, "color": "red"}], "gapAfter": 18},
                            # SAMMANFATTNINGEN: en rad per fall, fylls i
                            # tillsammans med klassen. Korta celler, ingen
                            # cellW — motorn ger varje kolumn sin egen bredd.
                            {"kind": "text", "text": "Sammanfattning",
                             "size": 22, "weight": 700, "gapAfter": 8},
                            {"kind": "table",
                             "headers": ["Uttryck", "Byggt av", "Regel", "Svar"],
                             "rows": [
                                 ["x² sin x", "två faktorer", "produkt",
                                  "2x sin x + x² cos x"],
                                 ["(3x + 1)⁵", "funktion i funktion",
                                  "kedja", "15(3x + 1)⁴"],
                                 ["4x³", "ren potens", "potens", "12x²"]]},
                        ]},
                    ],
                },
            ],
        },
    ),
    # ── Fallgalleriet ───────────────────────────────────────────────────────
    # Högertavlans andra form. Är momentet en SATS med klassiska fall är det
    # inte uträkningar klassen behöver se utan FIGURERNA: läraren pratar och
    # pekar, och varje fall bär bara sitt namn och en rad om vad det säger.
    # Vänstertavlan är densamma som i de andra shotarna — dramaturgin ändras
    # inte av att högertavlan byter form.
    (
        "Ma2c, klass TE24 — Randvinkelsatsen (genomgång med fallgalleri)",
        {
            "title": "Randvinkelsatsen",
            "boards": [
                {
                    "width": 900, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 40},
                    "chrome": "aluminium", "tray": True, "name": "vanster",
                    "sections": [
                        {"kind": "heading", "text": "Randvinkelsatsen", "size": 32,
                         "underline": {"color": "red"}, "gapAfter": 14},
                        {"kind": "list", "bullet": "–", "size": 19, "gap": 4,
                         "items": ["Vinklar inne i en cirkel",
                                   "Vi jämför två vinklar",
                                   "Tre fall att känna igen"],
                         "gapAfter": 12},
                        {"kind": "divider", "width": 620, "gapAfter": 14},
                        {"kind": "callout", "color": "blue", "fillOpacity": 0.06,
                         "padding": 12, "children": [
                             {"kind": "text",
                              "text": "Vad vet ni om vinklar i en cirkel?",
                              "size": 21, "color": "blue", "weight": 700}],
                         "gapAfter": 12},
                        {"kind": "text",
                         "text": "En randvinkel har sitt hörn på cirkeln.",
                         "size": 20, "gapAfter": 10},
                        # Bokstäver, inga gradtal: figuren är generisk och
                        # satsen läses av ur den. Talen hör hemma i galleriet.
                        {"kind": "graph", "width": 280, "height": 280,
                         "xRange": [-1.35, 1.35], "yRange": [-1.35, 1.35],
                         "grid": False, "axes": False,
                         "polygons": [
                             {"pts": _cirkel(0, 0, 1), "fillOpacity": 0,
                              "stroke": "black", "strokeWidth": 2},
                             {"pts": [[-0.94, -0.342], [0, 0], [0.94, -0.342]],
                              "fill": "blue", "fillOpacity": 0.1,
                              "stroke": "blue", "strokeWidth": 2},
                             {"pts": [[-0.94, -0.342], [0, 1], [0.94, -0.342]],
                              "fill": "red", "fillOpacity": 0.08,
                              "stroke": "red", "strokeWidth": 2}],
                         "points": [{"x": 0, "y": 0, "color": "black", "size": 5}],
                         "texts": [
                             {"x": 0, "y": -0.33, "text": "u", "size": 18,
                              "color": "blue", "anchor": "middle", "italic": True},
                             {"x": 0, "y": 0.64, "text": "v", "size": 18,
                              "color": "red", "anchor": "middle", "italic": True},
                             {"x": -1.05, "y": -0.52, "text": "A", "size": 16,
                              "anchor": "end"},
                             {"x": 1.05, "y": -0.52, "text": "B", "size": 16,
                              "anchor": "start"},
                             {"x": 0, "y": 1.2, "text": "C", "size": 16,
                              "anchor": "middle"}],
                         "gapAfter": 12},
                        {"kind": "math", "latex": "u = 2v", "size": 28,
                         "color": "blue", "gapAfter": 14},
                        {"kind": "callout", "color": "red", "fillOpacity": 0.06,
                         "padding": 12, "children": [
                             {"kind": "text", "text": "Vanligt fel:", "size": 18,
                              "color": "red", "gapAfter": 4},
                             {"kind": "math", "latex": "v = 2u", "size": 19,
                              "color": "red", "gapAfter": 4},
                             {"kind": "text",
                              "text": "Randvinkeln är den halva, inte den dubbla.",
                              "size": 17, "color": "red"}]},
                    ],
                },
                {
                    "width": 1800, "height": 780,
                    "padding": {"top": 30, "right": 30, "bottom": 30, "left": 30},
                    "chrome": "aluminium", "tray": True, "name": "hoger",
                    "columns": [
                        {"weight": 1, "sections": [
                            {"kind": "heading", "text": "Tre fall", "size": 28,
                             "underline": {"color": "blue"}, "gapAfter": 12},
                            {"kind": "text", "text": "Medelpunktsvinkeln",
                             "size": 22, "weight": 700, "gapAfter": 6},
                            {"kind": "graph", "width": 380, "height": 380,
                             "xRange": [-1.35, 1.35], "yRange": [-1.35, 1.35],
                             "grid": False, "axes": False,
                             "polygons": [
                                 {"pts": _cirkel(0, 0, 1), "fillOpacity": 0,
                                  "stroke": "black", "strokeWidth": 2},
                                 {"pts": [[-0.94, -0.342], [0, 0], [0.94, -0.342]],
                                  "fill": "blue", "fillOpacity": 0.1,
                                  "stroke": "blue", "strokeWidth": 2},
                                 {"pts": [[-0.94, -0.342], [0, 1], [0.94, -0.342]],
                                  "fill": "red", "fillOpacity": 0.08,
                                  "stroke": "red", "strokeWidth": 2}],
                             "texts": [
                                 {"x": 0, "y": -0.33, "text": "140°", "size": 17,
                                  "color": "blue", "anchor": "middle"},
                                 {"x": 0, "y": 0.64, "text": "70°", "size": 17,
                                  "color": "red", "anchor": "middle"}],
                             "gapAfter": 10},
                            {"kind": "text",
                             "text": "Vinkeln från centrum är dubbelt så stor.",
                             "size": 19, "gapAfter": 12},
                            {"kind": "math", "latex": "u = 2v", "size": 24,
                             "color": "blue"},
                        ]},
                        {"weight": 1, "sections": [
                            {"kind": "text", "text": "Samma båge", "size": 22,
                             "weight": 700, "gapAfter": 6},
                            {"kind": "graph", "width": 260, "height": 260,
                             "xRange": [-1.35, 1.35], "yRange": [-1.35, 1.35],
                             "grid": False, "axes": False,
                             "polygons": [
                                 {"pts": _cirkel(0, 0, 1), "fillOpacity": 0,
                                  "stroke": "black", "strokeWidth": 2},
                                 {"pts": [[-0.94, -0.342], [-0.5, 0.866],
                                          [0.94, -0.342]],
                                  "fill": "red", "fillOpacity": 0.08,
                                  "stroke": "red", "strokeWidth": 2},
                                 {"pts": [[-0.94, -0.342], [0.5, 0.866],
                                          [0.94, -0.342]],
                                  "fill": "blue", "fillOpacity": 0.08,
                                  "stroke": "blue", "strokeWidth": 2}],
                             "texts": [
                                 {"x": -0.36, "y": 0.52, "text": "v", "size": 17,
                                  "color": "red", "anchor": "middle",
                                  "italic": True},
                                 {"x": 0.36, "y": 0.52, "text": "v", "size": 17,
                                  "color": "blue", "anchor": "middle",
                                  "italic": True}],
                             "gapAfter": 10},
                            {"kind": "text",
                             "text": "Vinklar på samma båge är lika stora.",
                             "size": 19, "gapAfter": 18},
                            {"kind": "text", "text": "Thales sats", "size": 22,
                             "weight": 700, "gapAfter": 6},
                            {"kind": "graph", "width": 260, "height": 260,
                             "xRange": [-1.35, 1.35], "yRange": [-1.35, 1.35],
                             "grid": False, "axes": False,
                             "polygons": [
                                 {"pts": _cirkel(0, 0, 1), "fillOpacity": 0,
                                  "stroke": "black", "strokeWidth": 2},
                                 {"pts": [[-1, 0], [0, 1], [1, 0]],
                                  "fill": "blue", "fillOpacity": 0.08,
                                  "stroke": "blue", "strokeWidth": 2}],
                             "rightAngles": [
                                 {"x": 0, "y": 1, "leg1": [-1, -1],
                                  "leg2": [1, -1], "size": 12, "color": "red"}],
                             "gapAfter": 10},
                            {"kind": "text",
                             "text": "Står vinkeln på diametern är den rät.",
                             "size": 19},
                        ]},
                    ],
                },
            ],
        },
    ),
]


def _few_shot_block() -> str:
    parts = []
    for i, (uppdrag, doc) in enumerate(FEW_SHOTS, 1):
        parts.append(
            f"Exempel {i} — uppdrag: {uppdrag}\n"
            f"JSON:\n{json.dumps(doc, ensure_ascii=False)}\n")
    return "\n".join(parts)


def build_prompt(course: str, group: str, moment: str, memory: str = "",
                 underlag: str = "", utfall: str = "", bok: str = "",
                 forlaga: str = "") -> str:
    """Genereringsprompt: instruktion + few-shots + minneskontext + ev.
    uppladdat underlag (bokssidor/uppgifter) + ev. rättat provs utfall
    (Etapp 0.7) + ev. lärobokens uppslag (Etapp 0.8) + ev. förlaga (källdörr 4)
    + uppdraget."""
    mem = f"\nUr lektionsminnet (senaste lektionerna med klassen):\n{memory}\n" if memory else ""
    utf = f"\n{utfall}\n" if utfall else ""
    # Förlagan står NÄRMAST uppdraget av källorna: den är det starkaste
    # önskemålet läraren kan ge — «gör som det här pappret» — och den ska inte
    # tappas bakom minnet eller boken.
    forl = f"\n{forlaga}\n" if forlaga else ""
    # Boken står SIST bland källorna och närmast uppdraget: läraren slog upp
    # just de här sidorna, och det är dem klassen har framför sig.
    bk = f"\n{bok}\n" if bok else ""
    und = (
        "\nUNDERLAG — läraren har laddat upp sidor ur läroboken/uppgifter som "
        "lektionen SKA bygga på. Utgå från dessa: använd samma begrepp och "
        "samma notation, och låt tavlans exempel ansluta till underlaget. Men "
        "skriv HELT EGNA exempel och uppgifter — skriv aldrig av underlagets, "
        "inte ens med utbytta tal; de visar nivå och typ, inget mer:\n"
        f"{underlag}\n" if underlag else "")
    return (
        f"{INSTRUCTION}\n{_few_shot_block()}\n{mem}{utf}{und}{bk}{forl}\n"
        f"Uppdrag: skriv lektionstavlan för {course}, klass {group} — {moment}.\n"
        "Svara med enbart JSON."
    )


def _format_problems(problems: list) -> str:
    lines = []
    for p in problems:
        if isinstance(p, dict):
            lines.append(f"- {p.get('path', '?')}: {p.get('message', p)}")
        else:
            lines.append(f"- {p}")
    return "\n".join(lines)


def build_repair_prompt(board_json: dict, problems: list) -> str:
    """Korrigeringsprompt: förra JSON:en + maskinläsbara fel/varningar."""
    return (
        f"{INSTRUCTION}\n"
        "Din förra lektionstavla har problem som måste rättas. Här är tavlan:\n"
        f"{json.dumps(board_json, ensure_ascii=False)}\n\n"
        "Problem att åtgärda:\n"
        f"{_format_problems(problems)}\n\n"
        f"{REPAIR_HINTS}\n"
        "Skriv om HELA tavlan som JSON med problemen åtgärdade. Ändra så lite "
        "som möjligt i övrigt. Svara med enbart JSON."
    )


def build_refine_prompt(board_json: dict, instruction: str) -> str:
    """Chatt-iteration: lärarens ändringsönskemål ovanpå befintlig tavla."""
    return (
        f"{INSTRUCTION}\n"
        "Här är den nuvarande lektionstavlan:\n"
        f"{json.dumps(board_json, ensure_ascii=False)}\n\n"
        f"Lärarens önskemål: {instruction}\n\n"
        "Skriv om HELA tavlan som JSON med önskemålet genomfört. Ändra så "
        "lite som möjligt i övrigt. Svara med enbart JSON."
    )


# ── Tiden ────────────────────────────────────────────────────────────────────
# Läraren vill ha klockslaget litet uppe till vänster på vänstertavlan. Det
# skrivs INTE av modellen (som gärna hittar på ett klockslag) utan sätts här,
# efter validering och normalisering, ur planeringens `starttid`. Injektionen
# är idempotent så att den kan göras om efter varje refine/repair — modellen
# ser tiden i tavlan den ska skriva om och kan stryka den.
_TID_RE = re.compile(r"^\d{1,2}[:.]\d{2}$")


def _tidsflode(board: dict) -> list | None:
    """Sektionsflödet som renderas ÖVERST på vänstertavlan. Motorn ritar
    `sections` bara när tavlan saknar `columns` (layout.js) — har vänstertavlan
    kolumner hör tiden hemma först i den vänstra."""
    tavlor = board.get("boards")
    if not isinstance(tavlor, list) or not tavlor \
            or not isinstance(tavlor[0], dict):
        return None
    forsta = tavlor[0]
    kolumner = forsta.get("columns")
    if isinstance(kolumner, list) and kolumner \
            and isinstance(kolumner[0], dict) \
            and isinstance(kolumner[0].get("sections"), list):
        return kolumner[0]["sections"]
    if isinstance(forsta.get("sections"), list):
        return forsta["sections"]
    return None


def satt_tid(board: dict | None, starttid: str | None) -> dict | None:
    """Lägg lektionens klockslag först på vänstertavlan — liten, svart text.

    En tid som redan står först byts ut eller tas bort, så att upprepade
    rundor aldrig ger dubbletter. Ingen starttid → ingen tidssektion, och
    inget fel. Klockslaget skrivs alltid med kolon: '9.10' hade fällts av
    decimalkommaregeln i whiteboard_spec."""
    if not isinstance(board, dict):
        return board
    board = copy.deepcopy(board)
    flode = _tidsflode(board)
    if flode is None:
        return board
    if flode and isinstance(flode[0], dict) and flode[0].get("kind") == "text" \
            and _TID_RE.match(str(flode[0].get("text") or "").strip()):
        flode.pop(0)
    tid = (starttid or "").strip()
    if tid and _TID_RE.match(tid):
        flode.insert(0, {"kind": "text", "text": tid.replace(".", ":"),
                         "size": 16, "color": "black", "gapAfter": 10})
    return board


def _rensa_toppnycklar(board: dict | None) -> dict | None:
    """Samma städning som i exam_gen: toppnycklar utanför dokumentet slängs.
    Utan grammatiktvång (schemat ligger i prompten — se claude_code.SCHEMA_TAK)
    kostar ett påhittat toppfält annars en hel reparationsrunda. Sektionerna
    städas INTE: ett extra fält där betyder att formen missförståtts."""
    if not isinstance(board, dict):
        return board
    tillatna = set(ws.BoardDoc.model_fields)
    return {k: v for k, v in board.items() if k in tillatna}


def _parse_board(raw: str) -> dict | None:
    """Robust JSON-parse (jfr _parse_extract i postprocess.py): modellen kan
    lämna skräp runt JSON-objektet trots grammatiktvånget i skarp drift."""
    try:
        return _rensa_toppnycklar(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if m:
            try:
                return _rensa_toppnycklar(json.loads(m.group(0)))
            except json.JSONDecodeError:
                return None
    return None


def _llm_round(prompt: str, model: str, llm, token_cb=None) -> dict | None:
    raw = llm(
        model, prompt,
        system=SYSTEM,
        options={"temperature": 0.2},
        response_format=ws.to_response_format(),
        max_tokens=BOARD_MAX_TOKENS,
        token_cb=token_cb,
    )
    board = _parse_board(raw)
    # Deterministisk normalisering (radbryt långa texter, dedupa dubbletter)
    # innan validering — se ws.normalize_board. Kostar inga LLM-rundor.
    return ws.normalize_board(board) if board is not None else None


def _repair_until_valid(board: dict | None, errors: list, *, model: str, llm,
                        rounds_used: int, max_rounds: int,
                        log_cb: Callable[[str], None] | None = None,
                        token_cb: Callable[[str], None] | None = None) -> dict:
    """Kör korrigeringsrundor tills fellistan är tom eller rundorna är slut.
    Returnerar {"board", "errors", "rounds"} — kvarstående fel redovisas
    ärligt (UI:t visar dem i stället för att dölja dem)."""
    log = log_cb or (lambda _m: None)
    while errors and rounds_used < max_rounds and board is not None:
        rounds_used += 1
        log(f"Rättar tavlan (runda {rounds_used} av {max_rounds}) — "
            f"{len(errors)} problem …")
        candidate = _llm_round(build_repair_prompt(board, errors), model, llm,
                               token_cb=token_cb)
        if candidate is None:
            errors = [{"path": "svar", "code": "json",
                       "message": "modellen svarade inte med giltig JSON"}]
            continue
        doc, new_errors = ws.validate_board_json(candidate)
        board = candidate
        errors = new_errors
    return {"board": board, "errors": errors, "rounds": rounds_used}


def generate_board(course: str, group: str, moment: str, *, model: str,
                   memory: str = "", underlag: str = "", utfall: str = "",
                   bok: str = "", forlaga: str = "",
                   llm=llm_client.generate,
                   max_rounds: int = MAX_ROUNDS,
                   log_cb: Callable[[str], None] | None = None,
                   token_cb: Callable[[str], None] | None = None) -> dict:
    """Generera en tavla och auto-reparera valideringsfel.

    Returnerar {"board": dict|None, "errors": [...], "rounds": int}.
    Anroparen (rutterna) äger GPU-arbiterlåset. `token_cb` får modellens
    råa tokens medan den skriver — UI:t bygger upp tavlan live ur dem."""
    log = log_cb or (lambda _m: None)
    log("Genererar lektionstavlan …")
    prompt = build_prompt(course, group, moment, memory, underlag, utfall, bok,
                          forlaga)
    board = _llm_round(prompt, model, llm, token_cb=token_cb)
    rounds = 1
    # Ogiltig JSON (t.ex. trunkerat svar) → kör om från början inom budgeten
    # i stället för att ge upp (bench Fas 2: tabelltung tavla).
    while board is None and rounds < max_rounds:
        rounds += 1
        log(f"Modellen svarade inte med giltig JSON — försöker igen "
            f"(runda {rounds} av {max_rounds}) …")
        board = _llm_round(prompt, model, llm, token_cb=token_cb)
    if board is None:
        return {"board": None,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": rounds}
    _doc, errors = ws.validate_board_json(board)
    return _repair_until_valid(board, errors, model=model, llm=llm,
                               rounds_used=rounds, max_rounds=max_rounds,
                               log_cb=log_cb, token_cb=token_cb)


def repair_board(board: dict, warnings: list[str], *, model: str,
                 llm=llm_client.generate, rounds_used: int = 1,
                 max_rounds: int = MAX_ROUNDS,
                 log_cb: Callable[[str], None] | None = None,
                 token_cb: Callable[[str], None] | None = None) -> dict:
    """Reparera utifrån klientens renderingsvarningar ([WB] …).

    `rounds_used` är antalet LLM-rundor som redan förbrukats för tavlan så
    att generering + renderingsreparation delar samma budget (max 3)."""
    problems: list = list(warnings)
    return _repair_until_valid(board, problems, model=model, llm=llm,
                               rounds_used=rounds_used, max_rounds=max_rounds,
                               log_cb=log_cb, token_cb=token_cb)


def refine_board(board: dict, instruction: str, *, model: str,
                 llm=llm_client.generate,
                 max_rounds: int = MAX_ROUNDS,
                 log_cb: Callable[[str], None] | None = None,
                 token_cb: Callable[[str], None] | None = None) -> dict:
    """Chatt-iteration: genomför lärarens önskemål, validera, auto-reparera."""
    log = log_cb or (lambda _m: None)
    log("Uppdaterar tavlan …")
    candidate = _llm_round(build_refine_prompt(board, instruction), model, llm,
                           token_cb=token_cb)
    if candidate is None:
        return {"board": board,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": 1}
    _doc, errors = ws.validate_board_json(candidate)
    return _repair_until_valid(candidate, errors, model=model, llm=llm,
                               rounds_used=1, max_rounds=max_rounds,
                               log_cb=log_cb, token_cb=token_cb)
