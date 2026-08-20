"""Provgenerering — promptbygge och LLM-loopar (Fas 4).

Samma mönster som app/lesson_board.py: grammatiktvingad JSON
(exam_spec.to_response_format), deterministisk validering
(schema + balans), korrigeringsprompt i upp till :data:`MAX_ROUNDS` rundor.
Därtill :func:`fix_latex` — kompileringsfel från exam_pdf går tillbaka till
modellen som korrigeringsprompt i max :data:`MAX_LATEX_ROUNDS` rundor.

Uppgifterna är ALLTID egenformulerade — endast nationella provets struktur
och poängmodell efterliknas (NP-sekretess/upphovsrätt; inga NP-uppgifter
någonstans i prompterna).
"""
from __future__ import annotations

import copy
import json
import re
from typing import Callable

from app import exam_spec, llm_client, niva_rubrik

MAX_ROUNDS = 3          # generering + balansreparation (delad budget)
MAX_LATEX_ROUNDS = 2    # kompileringsfel → korrigering
EXAM_MAX_TOKENS = 12_000

SYSTEM = (
    "Du är en erfaren svensk matematiklärare som konstruerar prov i "
    "nationella provets anda. Uppgifterna är ALLTID egenformulerade — "
    "aldrig kopierade från nationella prov, läromedel, tidigare papper "
    "eller förlagor. Boken och förlagan är inspiration för begrepp, "
    "notation och nivå — uppgifterna hittar du alltid på själv. Du svarar "
    "ALLTID med giltig JSON enligt schemat, ingenting annat.\n"
    "RÖST: skriv i nationella provets register. Varje uppgift drivs av ett "
    "imperativt verb (Beräkna, Bestäm, Lös, Ange, Visa, Avgör, Förenkla, "
    "Motivera). Tilltala eleven med du, aldrig ni eller man. INGA emoji. "
    "INGA utropstecken. Ingen hedging ('kanske', 'försök gärna'). Använd "
    "decimalkomma och svenska enheter (4{,}0 cm, 15,9 %), med mellanslag "
    "mellan tal och enhet respektive procenttecken.\n"
    "NAMN: påhittade förnamn är välkomna i uppgifterna — de gör sammanhangen "
    "levande (lärarens beslut 2026-08-20). Men aldrig namn ur underlag, "
    "transkript eller klasslistor: riktiga elever ska inte stå på pappret."
)

INSTRUCTION = (
    "Skriv ett matteprov som JSON enligt schemat. Dokumentets egna fält är "
    # Fältet HETER tid_min. Här stod «tid_minuter», och det är inget fält i
    # ExamDoc: _rensa_toppnycklar slängde det som en påhittad toppnyckel, och
    # «ge dem tio minuter till» kunde alltså aldrig fastna i dokumentet —
    # instruktionen bad om ett namn appen själv städar bort.
    "titel, kurs, klass, datum, tid_min, hjalpmedel, instruktion, grupp och "
    "uppgifter — "
    "hjalpmedel KRÄVS (t.ex. \"Formelblad och digitala verktyg\"), och lägg "
    "inte till egna toppnycklar. Fältregler:\n"
    "- tid_min: skrivtiden i minuter som ett heltal. Står på försättsbladet "
    "och i förhandsvisningens provtabell.\n"
    "- hjalpmedel: hjälpmedelsregeln i klartext, EN mening för hela provet — "
    "den står i provtabellen och i OBS-rutan över uppgifterna. Ber läraren om "
    "en ändring av vad som är tillåtet är det HÄR den skrivs.\n"
    # Gruppuppgiftens upplägg ÄR pappersformen: namnraderna räknas ur `elever`,
    # metaraden överst säger alla tre. Utan raden här kunde modellen inte ändra
    # dem i en omskrivning — build_refine_prompt får bara INSTRUCTION med sig —
    # och «gör grupperna om 4» blev ett svar utan verkan.
    "- grupp {elever, langd_min, redovisning}: BARA gruppuppgiften har det. "
    "elever är 2–5 (det är antalet namnrader på pappret), langd_min är "
    "10–180, redovisning är \"muntligt\", \"skriftligt\" eller \"poster\". "
    "Raden överst på pappret läses ur dem; ändrar läraren gruppstorleken, "
    "tiden eller redovisningsformen ändras fältet.\n"
    # Bandet står i INSTRUCTION och inte bara i uppdragsblocken, och det är
    # hela poängen: omskrivningen (build_refine_prompt) får BARA den här texten
    # med sig. Stod regeln i gruppuppgiftens uppdrag kunde modellen skriva
    # rutan när dokumentet föddes men aldrig ändra den efteråt — och det var
    # just det läraren bad om när hon strök en mening ur rutan.
    "- instruktion: instruktionsbandet överst på arbetsbladet, gruppuppgiften "
    "eller diagnosen — den grå rutan som säger HUR eleverna ska arbeta (läsa "
    "tillsammans, skriva svaret på svarsraden, hur det redovisas), aldrig vad "
    "uppgifterna handlar om. Två till tre korta meningar. Är fältet tomt sätter "
    "appen sin egen standardtext; ber läraren om en ändring i rutan skriver du "
    "HELA bandets text i fältet, med hennes ändring införd. Provet har inget "
    "band — där lämnas fältet tomt, dess motsvarighet är hjalpmedel.\n"
    "- del: \"B\" (utan räknare), \"C\" eller \"D\" (med räknare) — eller null "
    "om provet saknar delar.\n"
    "- formaga: primär förmåga per uppgift — B Begrepp, P Procedur, "
    "PL Problemlösning, M Modellering, R Resonemang, K Kommunikation.\n"
    "- typ: rutin (endast svar), redovisning (fullständig lösning), "
    "problem (flersteg) eller resonemang.\n"
    "- poang: [E, C, A] enligt NP-notationen, t.ex. [2, 1, 0]. En uppgift vars "
    "förmåga är K (Kommunikation) får ALDRIG E-poäng — dess poäng ser ut som "
    "[0, 1, 0] eller [0, 1, 1]. Skriftlig kommunikation bedöms inte på E-nivå "
    "för enskilda uppgifter; den som klarar E i övrigt anses redovisa nog.\n"
    "- text: uppgiftstexten. Matematik skrivs inom $…$ (t.ex. "
    "$x^2 - 4x + 3 = 0$); övrig text är vanlig svenska utan LaTeX-kommandon.\n"
    # Facit ska gå att läsa på en armlängds avstånd, och det gör det bara om
    # texten är kort. Modellen skrev annars resonerande meningar om vad ett led
    # betyder («Täljaren är en summa av termerna … Bråkstrecket håller ihop …»)
    # — läraren kallade det «så jävla mycket text och svårläst». Svaret först,
    # sedan tavlans egna rader, och inte ett ord till.
    "- losning: facittexten, och den ska vara KORT: svaret först, sedan högst "
    "ett par räkneled — de rader en lärare skriver på tavlan när hon går "
    "igenom uppgiften. Skriv aldrig resonerande prosa om vad ett led betyder "
    "eller varför notationen ser ut som den gör, och upprepa aldrig "
    "uppgiftstexten: facit läses BREDVID uppgiften, inte i stället för den. En "
    "rutinuppgift klarar sig på svaret ensamt. Har uppgiften deluppgifter bär "
    "DE lösningsgången — förälderns losning lämnas då tom eller är en enda "
    "sammanfattande rad, aldrig samma text en gång till. Samma $-regel som "
    "text.\n"
    "- bedomning: bedömningsanvisning, t.ex. '+1 E korrekt ansats, "
    "+1 C fullständig lösning med motivering'.\n"
    "- innehall: KODERNA för de centrala innehållspunkter uppgiften prövar "
    "(t.ex. [\"G25-M1C-ALG-3\"]) — hämtade ur listan över valt centralt "
    "innehåll nedan, en till tre stycken, aldrig egen text. Står ingen sådan "
    "lista: korta etiketter.\n"
    "Struktur (använd DÄR DET PASSAR pedagogiskt — inte på varje uppgift):\n"
    "- deluppgifter: dela EN uppgift i a/b/c när den naturligt har flera steg "
    "eller frågor. Föräldern bär då stammen i text och poang [0, 0, 0] — "
    "ALLTID [0, 0, 0], summera aldrig deluppgifternas poäng dit; varje "
    "deluppgift har egen poang, text, losning och bedomning (och får ha egen "
    "formaga/typ). Fälten innehall och elevlosningar står BARA på uppgiften, "
    "aldrig på en deluppgift — en deluppgift som bär dem avvisas. Blanda inte "
    "in deluppgifter i rutinuppgifter — de passar "
    "redovisnings-, problem- och resonemangsuppgifter. En nivå djupt.\n"
    "  En deluppgift får BARA bära fälten poang, text, losning, bedomning, "
    "formaga, typ, enhet, notis, alternativ, ratt_alternativ, tabell, "
    "stegtabell och svarsrutor. Fälten del, innehall, sekundara, bild, figur, "
    "elevlosningar och deluppgifter hör till UPPGIFTEN och får aldrig stå inne "
    "i en deluppgift — de gäller hela uppgiften, inte en av dess frågor.\n"
    "- alternativ + ratt_alternativ: gör en uppgift ELLER deluppgift till "
    "flervalsfråga med minst tre alternativ (matte inom $…$) och "
    "ratt_alternativ som 0-baserat index på det rätta — aldrig på en uppgift "
    "som redan har deluppgifter. Använd sparsamt, för begreppskoll; "
    "ratt_alternativ visas bara för läraren.\n"
    "- notis: en kort inramad påminnelse/instruktion på en uppgift eller "
    "deluppgift (t.ex. 'Rita en teckenrad som stöd.'). Valfri, använd sällan.\n"
    "- figur: lägg en matematisk figur på en uppgift genom att välja typ och "
    "sätta talen (aldrig fri kod): linjar {k, m}, andragrad {a, b, c}, "
    "exponential {C, bas}, normalfordelning {mu, sigma}, triangel {a, b, c}, "
    "enhetscirkel {vinkel}, stapeldiagram {kategorier, varden}, ladagram "
    "{min, q1, median, q3, max}. Talen står DIREKT i figurobjektet, bredvid "
    "typ — det finns inget fält som heter parametrar: "
    '"figur": {"typ": "andragrad", "a": 1, "b": -4, "c": 3}. En uppgift kan ha '
    "figur ELLER bild, aldrig både. Använd figur där den prövar avläsning "
    "eller tolkning; referera den i texten (t.ex. 'Figuren visar …').\n"
    "- enhet: enheten svaret ska anges i ('kr', 'laddpunkter/år', 'cm$^2$') "
    "eller ledet det skrivs efter ('$f'(x) =$'). Står på svarsraden. Sätt den "
    "när svaret HAR en enhet — en siffra utan enhet är inget svar.\n"
    "- tabell {rubriker, rader}: mätvärden uppgiften bygger på (årtal, "
    "priser, antal). Rader och rubriker måste ha lika många celler. Använd när "
    "uppgiften ber eleven LÄSA ur data, och hänvisa till den i texten "
    "('Bestäm med hjälp av tabellen ovan …').\n"
    "- svarsrutor {etikett, val, ratt}: ETT objekt (aldrig en lista) — en "
    "ifyllnadsrad där eleven kryssar i "
    "stället för att skriva — 'Sats: ☐ Randvinkelsatsen ☐ Kordasatsen', "
    "'Alltid? ☐ Ja ☐ Nej ☐ Bara ibland'. Två till fem val. `ratt` är 0-baserat "
    "index och visas bara för läraren; utelämna det när flera svar duger. "
    "Skilt från alternativ: det här är en RAD på svarsplatsen, inte en "
    "flervalsfråga.\n"
    "- stegtabell {kolumner, steg, forsta_fel}: en färdig lösning rad för rad "
    "där eleven ska kryssa det FÖRSTA felaktiga steget. En kolumn = en elevs "
    "lösning; två kolumner = två elever som fått olika svar. Tre till åtta "
    "steg. Varje steg är ETT OBJEKT med nyckeln celler: "
    "\"steg\": [{\"celler\": [\"$x^2-6x+5=0$\"]}, {\"celler\": [\"$x=3\\\\pm2$\"]}] "
    "— inte en naken lista. Lika många celler som kolumner. `forsta_fel` är "
    "0-baserat och visas bara för läraren. Den här formen prövar att LÄSA en "
    "lösning — använd den för resonemang och kommunikation, aldrig som "
    "räkneuppgift.\n"
    "- elevlosningar: två eller tre kommenterade elevlösningar på SAMMA "
    "uppgift, i stigande ordning (noll poäng, halva, full). Varje lösning har "
    "etikett och partier; varje parti har rader (lösningens egna rader), poang "
    "och dom (varför partiet gav eller inte gav poäng). Partiets poang är en "
    "TRIPPEL [E, C, A] precis som uppgiftens — [0, 0, 0] för ett parti som "
    "inte gav något, aldrig ett ensamt tal. Summan av partiernas "
    "poäng får inte överstiga uppgiftens. De hör till BEDÖMNINGEN — eleven ser "
    "dem aldrig — och är värda att skriva på den uppgift där gränsen mellan "
    "poängen är svårast att dra. Har uppgiften deluppgifter sätts fältet på "
    "FÖRÄLDERN och lösningarna visar hela uppgiften.\n"
    "Exempel på en uppgift MED deluppgifter (förälderns poang är [0, 0, 0]):\n"
    '{"del": "C", "formaga": "PL", "typ": "problem", "poang": [0, 0, 0], '
    '"text": "En rektangel har omkretsen 24 cm.", "deluppgifter": ['
    '{"poang": [1, 0, 0], "text": "Teckna arean $A$ som funktion av bredden.", '
    '"losning": "$A(b) = b(12 - b)$.", "bedomning": "+1 E korrekt uttryck."}, '
    '{"poang": [0, 1, 1], "text": "Bestäm den största möjliga arean.", '
    '"losning": "Max vid $b = 6$ ger $A = 36$ cm².", '
    '"bedomning": "+1 C ansats, +1 A motiverat maximum."}]}\n'
    "Exempel på en flervalsuppgift:\n"
    '{"del": "B", "formaga": "B", "typ": "rutin", "poang": [1, 0, 0], '
    '"text": "Vilket tal är ett nollställe till $f(x) = x^2 - 9$?", '
    '"alternativ": ["$x = 0$", "$x = 3$", "$x = 9$"], "ratt_alternativ": 1, '
    '"losning": "$f(3) = 0$.", "bedomning": "+1 E för rätt alternativ."}\n'
    "Balans: alla SEX förmågorna ska täckas och väga ungefär lika — var och en "
    "runt en sjättedel av poängen, ingen under en tiondel och ingen över en "
    "fjärdedel. Ha stigande svårighet, blanda "
    "rutinuppgifter med redovisnings- och problemuppgifter, och lägg "
    "E-tyngden tidigt. Varje uppgift ska vara DISTINKT — upprepa aldrig samma "
    "frågeformulering eller kontext; variera moment, tal och situation. "
    "Exempel på EN uppgift:\n"
    '{"del": "B", "formaga": "P", "typ": "rutin", "poang": [1, 0, 0], '
    '"text": "Lös ekvationen $2x + 7 = 19$.", "innehall": ["linjära ekvationer"], '
    '"losning": "$x = 6$ ur $2x = 12$.", '
    '"bedomning": "+1 E för korrekt svar."}\n'
    "Fasta fraser (använd ordagrant där de passar): 'Endast svar krävs.' på "
    "rutinuppgifter, 'Motivera ditt svar.' och 'Fullständiga lösningar "
    "krävs.' på redovisnings- och resonemangsuppgifter, 'Svara exakt.' där "
    "ett exakt värde efterfrågas. Skriv aldrig emoji eller utropstecken.\n"
)


# Fallgroparna hör hemma i GENERERINGEN, inte i INSTRUCTION: den delas med
# reparations-, refine- och latexfix-prompterna, och där ska kravet inte stå.
# En reparation som får höra «täck vanliga fel» byter uppgifter i stället för
# att laga det som var trasigt.
#
# Blocket kostar inga extra reparationsrundor. Mätt med skarpa körningar
# (2026-08-09): tavla, arbetsblad och gruppuppgift gick på EN runda, provet på
# två — och samma prov utan blocket (FALLGROPAR = "") gav två respektive en.
# Provets extra runda är alltså skelettets vanliga variation, inte det här.
FALLGROPAR = (
    "Vanliga fel — täck dem MEDVETET:\n"
    "- Tänk ut 2–3 fel som elever verkligen gör på det innehåll uppgifterna "
    "prövar: teckenfel vid negativa tal, glömd eller fel enhet, en tappad rot, "
    "fel prioriteringsordning, avrundning för tidigt, förväxlade begrepp.\n"
    "- Fallgropen ligger INUTI en uppgift du ändå skulle ha skrivit — den "
    "kostar ingen egen uppgift och ändrar varken förmåga, typ eller poäng. "
    "Välj talen så att felet blir frestande: en negativ koefficient som ska "
    "kvadreras, ett mått i meter när svaret ska anges i cm, en ekvation vars "
    "andra rot är lätt att tappa. Uppgiftstexten avslöjar aldrig fallgropen "
    "och varnar aldrig för den.\n"
    "- Gör INTE om detta till hitta-felet-uppgifter: en stegtabell eller "
    "elevlosningar är en egen uppgiftsform med egen förmåga och egna poäng, "
    "och använder du dem här faller balansen — proceduruppgifternas poäng går "
    "till resonemang i stället. Skriv dem bara när uppgiftsplanen eller "
    "uppdraget ber om det.\n"
    "- Skriv ut det väntade felet i bedomning där det är relevant, t.ex. "
    "\"+1 E korrekt ansats, +1 C fullständig lösning; vanligt fel: minustecknet "
    "tappas när $-3$ kvadreras\". Läraren ska veta vad hon letar efter."
)

# Gruppuppgiften kan göra mer än att undvika felet: den kan lägga fram det.
# Formerna finns redan i schemat (stegtabell, elevlosningar), så det här är
# ett val av innehåll, inte ett nytt fält.
#
# Blocket står INUTI gruppuppdraget, inte bland de allmänna reglerna, och ber
# om en DELUPPGIFT — inte en uppgift. Båda sakerna är dyrköpta.
#
# I toppen, bland de allmänna reglerna, såg modellen inte PL-kravet i samma
# andetag: PL föll till 12 % och «grupp»-fältet tappades helt. Och som en HEL
# uppgift åt hitta-felet-momentet upp en av bara fyra platser — då fanns ingen
# kvar till rutinuppgiften, blandningsregeln föll och E-tyngden gick till 47 %.
# En gruppuppgift på fyra uppgifter har inte en plats över; en deluppgift
# kostar ingen.
FALLGROPAR_GRUPP = (
    "Här ÄR hitta-felet-formen efterfrågad, men som DELUPPGIFT och inte som en "
    "egen uppgift — platserna är för få. Lägg i uppgiften som bär R eller K en "
    "deluppgift med en STEGTABELL där en påhittad elevs lösning innehåller just "
    "fallgropen: gruppen ska hitta det första felsteget och förklara VARFÖR det "
    "är fel. Det ska vara stegtabell och inte elevlosningar — elevlosningar "
    "finns bara på uppgiften, aldrig på en deluppgift. Ge gärna eleven ett "
    "påhittat förnamn. Lägg den ALDRIG i uppgiften som bär PL, och "
    "låt den aldrig tränga undan rutinuppgiften."
)


# ── Förlagan som mönster (Del F, omskriven 2026-08-20) ───────────────────────
# Läraren satt natten mellan 19 och 20 augusti och slipade en gruppuppgift i
# tjugotvå vändor tills hon var nöjd: «Räkneordning, parenteser och formler»,
# Matematik nivå 1a, byggklass (exams.id 17). Den är hennes mall från och med
# nu, och hennes egna anteckningar på vägen är kravlistan bakom varje rad
# nedan — «talen är för svåra», «svaret ska bli heltal», «korta uppgiftstexten
# rejält», «så mycket text», «ointressant för en byggklass», «ta bort uppgift E
# och F», «prioriteringsreglerna kort som stöd i instruktionsrutan».
#
# Den ersätter den gamla förlagan (exponential- mot potensekvationer, med
# cosinussatsen som handskrivet exempel). Den var ETT bra papper; det här är
# det hon SLIPADE, och skillnaden är kravlistan.
#
# Reglerna beskriver FORMEN och MÅTTEN, inte nivån: hennes klasser är 1a i
# byggklass, 1c och 2c i naturklass, och samma mall ska bära alla tre. Hur
# stora talen och hur abstrakta uttrycken får vara skalas därför ur kursen —
# se _nivastegen — och kontexten ur klassens program. Skrivs 1a:s mått in här
# får 2c ett 1a-papper.
#
# Utdragen nedan är UPPGIFTER UR HENNES PAPPER, inte hela dokumentet
# (promptbudget: formen syns i fyra utdrag lika väl som i fyra hela uppgifter
# med elevlösningar och bedömningsanvisningar). De byggs ur dictar och
# json.dumpas så att LaTeX-snedstrecken inte kan bli fel i en handskriven
# sträng.
_UTDRAG_GRUPP = [
    # Ingången: alla grupper kommer in här. Två uttryck UNDER varandra i en
    # tabell — läraren fällde den första versionen där de stod bredvid
    # varandra på samma rad: «annars blir det så otydligt att utläsa».
    {"formaga": "P", "typ": "rutin", "poang": [2, 0, 0],
     "text": "Räkna var för sig och jämför sedan era svar i gruppen. Beräkna "
             "de två uttrycken i tabellen utan räknare. Endast svar krävs.",
     "tabell": {"rubriker": ["Uppgift", "Uttryck"],
                "rader": [["a)", "$9 + 3 \\cdot 4^2$"],
                          ["b)", "$\\dfrac{48 - 12}{2 + 4}$"]]},
     "svarsfalt": ["Svar a)", "Svar b)"],
     "losning": "a) $57$, ur $9 + 3 \\cdot 16$. b) $6$, ur $\\dfrac{36}{6}$.",
     "bedomning": "+1 E rätt svar i a), +1 E rätt svar i b); vanligt fel: "
                  "$3 \\cdot 4$ kvadreras i a) ($153$)."},
    # Begreppsuppgiften: uttrycket står färdigt i texten, och gruppen ska
    # NAMNGE dess delar innan den räknar. Situationen är verkstaden, alltså
    # klassens egen värld.
    {"formaga": "B", "typ": "redovisning", "poang": [0, 0, 0],
     "text": "I verkstaden finns $86$ skruvar. $14$ av dem är trasiga och "
             "slängs. Resten delas lika i $2$ lådor med $4$ fack i varje låda. "
             "Då blir det $\\dfrac{86 - 14}{2 \\cdot 4}$ skruvar i varje fack. "
             "Fullständiga lösningar krävs.",
     "deluppgifter": [
         {"poang": [1, 1, 0],
          "text": "Vilket tal är täljaren i uttrycket och vilket tal är "
                  "nämnaren? Räkna sedan ut hur många skruvar det blir i "
                  "varje fack. Motivera ditt svar.",
          "svarsfalt": ["Täljare och nämnare", "Antal skruvar per fack"],
          "losning": "Täljaren är $86 - 14 = 72$, nämnaren är "
                     "$2 \\cdot 4 = 8$. Kvoten blir $9$ skruvar per fack."}]},
    # Felsökningen. Utdraget bär medvetet INGEN poang och ingen del: VAR den
    # ligger — som deluppgift i uppgiften som bär R eller K — bestäms av
    # FALLGROPAR_GRUPP ovan, som är uppmätt. Här visas bara formen.
    #
    # Lärarens papper skriver «Ali räknar …» — påhittade förnamn är tillåtna
    # sedan 2026-08-20 (lärarens beslut; gränsen som består är RIKTIGA
    # elevnamn ur underlag och klasslistor). Utdraget behåller «En elev» som
    # neutral form; FALLGROPAR_GRUPP uppmuntrar namnet.
    {"typ": "resonemang",
     "text": "En elev har beräknat $5 + 2 \\cdot (4 - 1)^2$ enligt tabellen. "
             "Markera den första rad som är fel, skriv rätt värde och förklara "
             "hur man ska tänka i stället. Motivera ditt svar.",
     "stegtabell": {"kolumner": ["Elevens lösning"],
                    "steg": [{"celler": ["$5 + 2 \\cdot (4 - 1)^2$"]},
                             {"celler": ["$= 5 + 2 \\cdot 3^2$"]},
                             {"celler": ["$= 5 + 6^2$"]},
                             {"celler": ["$= 5 + 36$"]},
                             {"celler": ["$= 41$"]}],
                    "forsta_fel": 2},
     "svarsfalt": ["Förklaring av felet", "Rätt värde",
                   "Så ska man tänka i stället"],
     "losning": "Första felet är raden $= 5 + 6^2$: potensen $3^2 = 9$ ska "
                "beräknas före multiplikationen. Rätt värde: $23$."},
    # Formeluppgiften: fast avgift plus rörligt pris, tecknas som formel och
    # används sedan baklänges. Läraren strök föregångaren — «hyra en släpvagn
    # till ett skolprojekt» — med orden «ointressant för en byggklass».
    {"formaga": "M", "typ": "problem", "poang": [0, 0, 0],
     "text": "Gruppen hyr en byggställning till ett husbygge. Uthyraren tar "
             "$500$ kr i startavgift och sedan $200$ kr per dag. Fullständiga "
             "lösningar krävs.",
     "deluppgifter": [
         {"poang": [1, 1, 0],
          "text": "Teckna en formel för kostnaden $K$ kr när ställningen hyrs "
                  "$d$ dagar. Hur många dagar räcker $2500$ kr till? Motivera "
                  "ditt svar.",
          "svarsfalt": ["Formel", "Antal dagar"], "enhet": "dagar",
          "losning": "$K = 500 + 200d$. $500 + 200d = 2500$ ger $d = 10$ "
                     "dagar.",
          "bedomning": "+1 E korrekt formel $K = 500 + 200d$, +1 C rätt svar "
                       "$10$ dagar; vanligt fel: startavgiften $500$ "
                       "multipliceras med $d$."}]},
]

FORLAGA_GRUPP = (
    "MÖNSTRET (lärarens egen gruppuppgift, den hon slipade i tjugotvå vändor "
    "tills hon var nöjd — följ dess form och dess mått, aldrig dess "
    "innehåll):\n"
    "- KORT UPPGIFTSTEXT. Två eller tre meningar, vardagliga ord, korta "
    "huvudsatser. Uppgiften ställer FRÅGAN och ingenting annat: hur gruppen "
    "ska arbeta med hela pappret står i instruktionsrutan, inte i uppgiften. "
    "Gäller en arbetsform bara EN uppgift («Räkna var för sig och jämför sedan "
    "era svar i gruppen») får den stå kort först i just den. Lärarens dom på "
    "de långa versionerna var «så mycket text» och «alldeles för omfattande» — "
    "en uppgiftstext som måste läsas två gånger är fel skriven.\n"
    "- SMÅ TAL, ENKLA MELLANLED. Välj talen så att VARJE mellanled blir ett "
    "enkelt tal som går att räkna i huvudet, och så att svaret går att känna "
    "igen som rätt. Läraren strök $16^2$ ur ett uttryck — inte för att "
    "kvadrater är svåra att förstå utan för att räknandet då tar över tanken. "
    "Hur stora talen får vara står under NIVÅN nedan; att mellanleden ska bli "
    "enkla gäller på alla nivåer.\n"
    "- KONTEXTEN ÄR KLASSENS. Uppdraget säger vilken klass pappret skrivs "
    "till, och klassbeteckningen bär programmet (bygg och anläggning, natur, "
    "teknik, ekonomi, vård …). Hämta situationerna DÄR: byggklassen räknar på "
    "verkstaden, materialet, maskinhyran och måtten på ritningen; naturklassen "
    "på mätvärden, koncentrationer och samband; teknikklassen på komponenter "
    "och toleranser. Ett påhittat «skolprojekt» är ingens värld — läraren strök "
    "en sådan uppgift med orden «ointressant för en byggklass». Säger "
    "beteckningen dig ingenting: välj en vardagssituation som gäller alla, "
    "aldrig en skoluppgift om en skoluppgift.\n"
    "- FYRA UPPGIFTER ÄR PAPPRETS FORM. Uppdraget säger antalet och det är "
    "exakt; blir de fler får de aldrig betalas med längre uppgiftstexter. "
    "Läraren strök två uppgifter ur ett papper på sex med orden «ta bort "
    "uppgift E och F helt» — hellre fyra uppgifter som hinns med och pratas "
    "igenom än sex som gruppen rusar förbi.\n"
    "- FORMERNA SOM BAR PAPPRET, en per förmåga i uppgiftsplanen:\n"
    "  * rutin-raden blir INGÅNGEN: två korta uttryck i en \"tabell\" med "
    "kolumnerna «Uppgift» och «Uttryck» och raderna a) och b), ett svarsfält "
    "per rad. Uttrycken står UNDER varandra, aldrig bredvid varandra på samma "
    "rad — läraren fällde den formen: «annars blir det så otydligt att "
    "utläsa».\n"
    "  * begreppsraden (B): en kort situation där uttrycket redan står "
    "färdigskrivet i texten, och gruppen ska NAMNGE dess delar (täljare, "
    "nämnare, term, faktor) innan den räknar ut det.\n"
    "  * resonemangs- och kommunikationsraderna (R, K): felsökningen — en "
    "\"stegtabell\" med en påhittad elevs lösning där gruppen ska hitta den "
    "FÖRSTA raden som är fel, skriva rätt värde och säga hur man ska tänka i "
    "stället. Be aldrig om den färdiga åtgärden («sätt in en parentes här») — "
    "det är svaret, och gruppen ska hitta det själv.\n"
    "  * modellerings- och problemraderna (M, PL): en verklig kostnad eller "
    "ett verkligt samband med ett fast och ett rörligt led, som gruppen först "
    "tecknar som formel och sedan använder baklänges — $K = 500 + 200d$; hur "
    "länge räcker $2500$ kr?\n"
    "  Minst en uppgift ska ändå BRYTA mönstret: ställer alla fyra samma sorts "
    "fråga gissar gruppen sig till metoden utan att välja den.\n"
    "- NYCKELFRÅGAN: momentets ENA avgörande fråga, skriven i dokumentets fält "
    "\"nyckelfraga\". Lärarens egen var fyra ord — «Vad ska räknas först?» — "
    "och så kort ska den vara; följ den med vägarna den öppnar bara när "
    "momentet har två metoder att välja mellan, och aldrig längre än en rad "
    "(~160 tecken). Den sätts fet i en liten ruta överst och är det gruppen "
    "läser när de fastnar; tre frågor i rad läses inte alls. Nyckelfrågan är i "
    "regel momentets vanligaste fallgrop vänd till ett beslut.\n"
    "- BESLUTEN PÅ PAPPRET, RÄKNINGEN PÅ LÖSBLAD: ge uppgiften fältet "
    "\"svarsfalt\" med de rader gruppen ska fylla i — det som ska BESVARAS, "
    "kort och namngivet ([\"Svar a)\", \"Svar b)\"], [\"Täljare och nämnare\", "
    "\"Antal skruvar per fack\"], [\"Formel\", \"Antal dagar\"]). Räknetunga "
    "led görs på lösblad, inte på pappret. Fältet hör till den fråga som ska "
    "besvaras: har uppgiften deluppgifter sätts det på DELUPPGIFTEN, inte på "
    "föräldern — annars står raden före frågan den gäller, och deluppgiften "
    "får en tom skrivyta i stället.\n"
    "- INGA TYP-KRYSSRUTOR. Klassificeringen är ett tankesteg, inte ett svar "
    "att kryssa: nyckelfrågan tvingar fram den, och den REDOVISAS genom "
    "uppställningen. Använd inte svarsrutor för att låta gruppen kryssa vilken "
    "sorts uppgift det är.\n"
    "- HJÄLPMEDLET STYRS PER UPPGIFT. Skriv i \"hjalpmedel\" vilka uppgifter "
    "räknaren får användas på och vilka som ska göras utan — huvudräkningen är "
    "halva poängen med ett moment som räkneordning, medan tillämpningen gärna "
    "får ha räknaren. Uppgifterna heter sina SIFFROR där (\"… på uppgift 4, "
    "men inte på uppgift 1, 2 och 3\").\n"
    "- BRICKORNA SÄTTER ARKET. Skriv aldrig uppgiftens eget nummer eller "
    "bokstav i texten och aldrig deluppgiftens a)/b) — mallen sätter dem. "
    "Bokstäverna i en rutinuppgifts tabell är något annat: de är radernas "
    "etiketter och paras med svarsfältens «Svar a)» och «Svar b)».\n"
    "Utdrag ur lärarens papper — formen, inte innehållet. Skriv aldrig av dess "
    "tal, kontexter eller formuleringar; möter du samma moment igen ska "
    "situationen och talen vara nya:\n"
    + "\n".join(json.dumps(u, ensure_ascii=False) for u in _UTDRAG_GRUPP)
)


# Nivåskalningen: samma mall, olika klasser. Lärarens papper är slipat för
# nivå 1a — små heltal, konkret kontext — och hennes andra klasser läser 1c
# och 2c. Skrivs 1a:s mått in i MÖNSTRET som siffror får naturettan och
# tvåan ett byggpapper, och det är precis vad hon INTE bad om: «olika nivåer
# för olika elever».
#
# Måtten hämtas därför ur kursnamnet. Det här är en ANNAN axel än nivåskalan i
# niva_rubrik/bok: den säger var E, C och A ligger INOM pappret (golv, tak,
# stegring), den här säger hur stora talen och hur abstrakta uttrycken får
# vara i kursen över huvud taget.
#
# Gy25 skriver kursen som «Matematik, nivå 1a» och fortsättningskurserna som
# «Matematik – fortsättning, nivå 1c» (gamla Ma3c). Steget räknas därför upp
# två för fortsättningen och fyra för fördjupningen, så att Ma3c hamnar på
# steg 3 och Ma5 på steg 5. Spåret (a, b, c) är sista bokstaven; saknas den
# (Ma4, Ma5) är kursen c-spårets fortsättning.
_KURSNIVA = re.compile(r"niv[åa]\s*([1-5])\s*([abc])?|(?<![0-9])([1-5])([abc])",
                       re.IGNORECASE)


def _kursniva(kurs: str) -> tuple[int, str] | None:
    """(steg, spår) ur kursnamnet, eller None när namnet inte säger något."""
    m = _KURSNIVA.search(kurs or "")
    if not m:
        return None
    steg = int(m.group(1) or m.group(3))
    spar = (m.group(2) or m.group(4) or "c").lower()
    lag = (kurs or "").lower()
    if "fortsättning" in lag:
        steg += 2
    elif "fördjupning" in lag:
        steg += 4
    return min(steg, 5), spar


_TALRUM = {
    1: "Talen är små: hela tal, i regel under hundra. Varje mellanled blir ett "
       "enkelt heltal och SVARET är ett heltal — läraren skrev «svaret ska bli "
       "heltal» och «använd mindre tal så alla mellanled blir enkla heltal». "
       "En kvadrat som $16^2$ hör inte hemma på den här nivån.",
    2: "Talrummet är större, och bråk, procent och negativa tal hör hemma här. "
       "Mellanleden ska ändå bli enkla, och svaret är i regel ett heltal eller "
       "ett kort exakt uttryck — inte ett decimaltal med fyra siffror.",
    3: "Talen är underordnade: här bär uttrycken. Potenser, rötter och exakta "
       "svar ($2\\sqrt{3}$, $\\ln 5$) är normalfallet och svaret behöver inte "
       "vara ett heltal — men talen ska ändå väljas så att räkningen inte "
       "skymmer tanken.",
}
_SPAR = {
    "a": "Spåret är a, yrkesprogrammens matematik: konkret språk och en "
         "situation eleverna känner igen från sitt program. Bokstäver "
         "förekommer i en enkel formel av typen $K = 500 + 200d$ — ett fast "
         "belopp plus ett rörligt — inte som uttryck att förenkla för sin egen "
         "skull.",
    "b": "Spåret är b, samhälls- och ekonomiprogrammens matematik: formellt "
         "matematiskt språk, tabeller, diagram, procent och förändring, och "
         "uttryck med bokstäver får stå för sig själva.",
    "c": "Spåret är c, natur- och teknikprogrammens matematik: formellt "
         "matematiskt språk och algebraiska uttryck som står för sig själva. "
         "En uppgift får kräva att gruppen skriver om ett uttryck innan den "
         "räknar, och exakta former är att föredra framför avrundade.",
}


def _nivastegen(kurs: str) -> str:
    """Talens storlek och uttryckens abstraktion — skalade ur KURSEN.

    Mönstret ovan är hämtat ur ett 1a-papper. Utan det här blocket ärver
    naturklassens 2c byggettans mått."""
    niva = _kursniva(kurs)
    if not niva:
        return ("NIVÅN: kursnamnet säger inte vilken nivå det gäller. Håll "
                "talen små och mellanleden enkla, som i mönstrets utdrag, och "
                "låt uppgifternas innehåll avgöra abstraktionen.")
    steg, spar = niva
    return (f"NIVÅN — måtten skalas ur kursen, inte ur mönstrets utdrag (de är "
            f"skrivna för nivå 1a). Kursen här är {kurs}, alltså steg {steg} i "
            f"spår {spar}:\n"
            f"- {_TALRUM[min(steg, 3)]}\n"
            f"- {_SPAR[spar]}\n"
            "- Mellanleden ska på ALLA nivåer gå att räkna utan räknare. "
            "«Talen är för svåra» var lärarens dom, och den gällde tanken som "
            "drunknade i räknandet — inte nybörjarkursen.")


def build_referens(items: list[str]) -> str:
    """Referensläget (Fas 5): tidigare provs uppgifter in i prompten med
    instruktion att skriva helt nya, likvärdiga uppgifter — aldrig kopiera."""
    numrerade = "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))
    return ("Utgå från det tidigare provets uppgifter nedan: behåll samma "
            "moment och samma svårighetsnivå men skriv HELT NYA uppgifter "
            "med nya kontexter och nya siffror. Kopiera ALDRIG en uppgift "
            "rakt av.\n"
            f"{numrerade}")


def build_riktat(elev: str, syfte: str, punkter: list[dict]) -> str:
    """Promptblocket för ett arbetsblad som hör till EN elev (Etapp 4).

    Två syften och de är varandras motsatser. «Stötta» skriver bladet på det
    hon INTE kan, med ingångar hon klarar; «utmana» skriver det på det hon
    redan kan, med krav hon ännu inte mött. Punkterna kommer ur hennes CI-profil
    (app/ci_profil.py) och bär sin andel — modellen ska veta skillnaden mellan
    «12 %» och «48 %», för det är två helt olika blad.

    Namnet står med. Bladet är hennes, och ett papper som är skrivet till en
    elev ska säga det."""
    rader = "\n".join(
        f"- {p.get('kort') or p.get('kod')}: "
        f"{round((p.get('andel') or 0) * 100)} % av poängen"
        for p in punkter or [])
    if syfte == "utmana":
        uppdrag = (
            f"Det här arbetsbladet skrivs till EN elev, {elev}, som redan kan "
            "de här punkterna och ska UTMANAS. Skriv uppgifter som går bortom "
            "standardfallet: fler steg, egna antaganden, motiveringar som "
            "kräver att hon vet VARFÖR metoden fungerar. Tyngdpunkten ligger "
            "på C- och A-nivå, och den första uppgiften får gärna vara den "
            "svåraste — hon behöver ingen uppvärmning på det hon kan.")
    else:
        uppdrag = (
            f"Det här arbetsbladet skrivs till EN elev, {elev}, som INTE "
            "behärskar punkterna nedan och ska STÖTTAS. Börja på en nivå hon "
            "säkert klarar och bygg uppåt i små steg: en igenkännbar "
            "standarduppgift först, sedan samma sak med en variation, sedan en "
            "tillämpning. Tyngdpunkten ligger på E- och C-nivå. Skriv ut "
            "metoden i uppgiftens notis när ett steg är lätt att fastna på — "
            "hon sitter ensam med bladet, utan lärare bredvid sig.")
    return (uppdrag + "\n"
            "Punkterna, med hur stor andel av poängen hon tagit på dem "
            "tidigare:\n" + (rader or "- (ingen mätning ännu)") + "\n"
            "Skriv INTE om andra moment än de här, och nämn aldrig procenttalen "
            "på pappret — de är lärarens underlag, inte elevens.")


def build_bilder(beskrivningar: list[str]) -> str:
    """Bildunderlagets promptblock: numrerade beskrivningar + regler för
    bild-fältet (1-baserat index; en uppgift per bild; null annars)."""
    rader = "\n".join(f"Bild {i}: {t or '(ingen beskrivning)'}"
                      for i, t in enumerate(beskrivningar, 1))
    return ("Läraren har laddat upp bilder som ska ingå i provet. "
            "Beskrivningar:\n" + rader + "\n"
            'Skriv för VARJE bild exakt EN uppgift som bygger på bilden och '
            'sätt uppgiftens fält "bild" till bildens nummer (1-baserat). '
            'Referera bilden i uppgiftstexten (t.ex. "Figuren visar …"). '
            'Alla andra uppgifter har "bild": null.')


def _skelett_plan(skeleton: list[dict], last: bool = True) -> str:
    """Läsbar uppgiftsplan ur det balanserade skelettet — talar om för modellen
    vilket innehåll varje rad ska ha.

    `last=True` när grammatiken låser raderna (prov och arbetsblad): då är
    planen en beskrivning av något modellen ändå inte kan ändra.
    `last=False` för gruppuppgiften, som INTE grammatiklåses — se
    build_prompt om varför — och där planen alltså är en instruktion."""
    rader = []
    for i, s in enumerate(skeleton, 1):
        del_txt = f"Del {s['del']}, " if s.get("del") else ""
        # Diagnosens rader bär sitt centrala innehåll: raden ÄR punkten, och
        # utan koden i planen vet modellen inte vilken uppgift som ska handla
        # om vad — grammatiken låser fältet men säger ingenting om texten.
        ci_txt = (f", centralt innehåll {', '.join(s['ci'])}"
                  if s.get("ci") else "")
        rader.append(f"{i}. {del_txt}{exam_spec.FORMAGA_NAMN[s['formaga']]} "
                     f"({s['formaga']}), {s['typ']}, poäng {s['poang']}{ci_txt}")
    huvud = ("Uppgiftsplan — del, förmåga, typ och poäng är LÅSTA per uppgift "
             "(ändra dem inte); skriv en uppgift vars INNEHÅLL matchar varje rad: "
             if last else
             "Uppgiftsplan — förmåga, typ och poäng per uppgift. Följ den: den "
             "är räknad så att alla sex förmågor väger lika och nivåerna "
             "fördelas rätt. Har en uppgift deluppgifter ska DERAS poäng summera "
             "till radens, och de ska ärva radens förmåga (utelämna formaga på "
             "dem). Skriv en uppgift vars innehåll matchar varje rad: ")
    return (huvud +
            "en R-rad avgör/motiverar ('Avgör om … Motivera.'), en K-rad "
            "förklarar med ord och representation ('Förklara/Redogör med ord och "
            "graf …'), en rutin-rad kräver bara svar.\n" + "\n".join(rader))


def build_prompt(kurs: str, klass: str, punkter: list[str], *,
                 antal: int = 10, tid_min: int = 120, delar: bool = True,
                 memory: str = "", teman: str = "",
                 referens: str = "", bilder: str = "", utfall: str = "",
                 bok: str = "", boknivaer: str = "", forlaga: str = "",
                 svart: str = "", fokus: str = "",
                 profil: str = "prov", koder: list[str] | None = None,
                 grupp: dict | None = None, riktat: str = "",
                 skeleton: list[dict] | None = None) -> str:
    """Genereringsprompt: instruktion + valda innehållspunkter +
    minneskontext + tidigare provs teman (undvik upprepning som default).
    `profil` växlar mellan prov och arbetsblad (Fas 5). `utfall` är ett rättat
    provs resultat (Etapp 0.7, app/rattning.build_utfall) — det står näst
    intill minnet därför att det är samma sak sagt med siffror: vad klassen
    kunde, inte vad den gick igenom.

    `boknivaer` är bokens EGEN nivåskala för det uppslag läraren slagit upp
    (app/bok.build_niva_block, Del C:s C2). Den gäller arbetsblad och
    gruppuppgift: läromedlet nivåmärker sina uppgifter, och för just den klassen
    ÄR boken skalan. Provet förankras i stället i NP-rubriken — det är lärarens
    uttryckliga krav att provet ska hålla nationell nivå, inte bokens."""
    # Skelettet räknas för ALLA tre profilerna (Del D1b): jämn förmågetäckning
    # ska vara garanterad by construction och inte bero på att modellen råkar
    # sprida poängen rätt. Bara delarna skiljer — arbetsbladet och
    # gruppuppgiften är platta papper.
    if skeleton is None and profil in ("arbetsblad", "gruppuppgift"):
        skeleton = exam_spec.balanced_skeleton(antal, profil, delar=False)
    # Diagnosen får sitt skelett utifrån (exam_spec.diagnosplan): det räknas ur
    # innehållet och lektionens längd, inte ur ett antal, så det går inte att
    # bygga här av `antal` allena.
    block = [INSTRUCTION]
    if punkter:
        # Med koder står punkterna som «KOD — text», och koden är det modellen
        # ska skriva i innehall. Utan koder (fritextpunkter från ett äldre
        # dokument) står de som förut och innehall lämnas fritt.
        block.append(
            ("Uppgifterna ska pröva följande centrala innehåll. Koden först på "
             "raden är punktens namn — det är DEN som ska stå i uppgiftens "
             "fält \"innehall\", aldrig en egen formulering:\n- "
             if koder else
             "Uppgifterna ska pröva följande centrala innehåll:\n- ")
            + "\n- ".join(punkter))
    # Direkt efter innehållet: fallgroparna är innehållets fallgropar, och
    # kravet ska läsas i samma andetag som punkterna det gäller.
    block.append(FALLGROPAR)
    # Lärarens egna ord om vad klassen hade svårt för står FÖRE minnet och
    # utfallet: de säger samma sak sett utifrån — vad klassen gick igenom, vad
    # den föll på — medan det här är hon som var i rummet. Blocket finns bara
    # när rutan är ifylld; ett tomt fält lämnar inget spår i prompten.
    if svart:
        block.append(svart)
    if memory:
        block.append(f"Ur lektionsminnet (vad klassen arbetat med):\n{memory}")
    if utfall:
        block.append(utfall)
    # Lärobokens uppslag (Etapp 0.8): uppgifterna ska ansluta till de sidor
    # klassen faktiskt arbetar med — samma begrepp och notation, men alltid
    # egenskrivna uppgifter (blocket självt förbjuder avskrift).
    if bok:
        block.append(bok)
    # Förlagan (källdörr 4, pardokumentets andra hand) står närmast uppdraget:
    # «gör som det här pappret» är det starkaste önskemålet läraren kan ge, och
    # det ska inte tappas bakom minnet, boken eller undvik-listan.
    if forlaga:
        block.append(forlaga)
    if teman:
        block.append("Tidigare provs uppgiftsteman — UNDVIK att upprepa dessa:\n"
                     + teman)
    if referens:
        block.append(referens)
    if bilder:
        block.append(bilder)
    # Det riktade bladet (Etapp 4) står SIST bland källorna och närmast
    # uppdraget: det är den starkaste ordern på pappret — inte «ett arbetsblad
    # om derivator» utan «ett arbetsblad till Alva om det Alva inte kan».
    if riktat:
        block.append(riktat)
    # Viktningen sist av källorna: «mest ur provet, lite ur boken» är en dom
    # över dem alla och går inte att läsa innan de står där.
    if fokus:
        block.append(fokus)
    if profil == "gruppuppgift":
        g = grupp or {}
        REDOV = {
            "muntligt": "Redovisas muntligt: två minuter per grupp, och alla i "
                        "gruppen ska kunna säga något.",
            "skriftligt": "Redovisas skriftligt: ett gemensamt svar per grupp "
                          "lämnas in vid lektionens slut.",
            "poster": "Redovisas som poster: lösningen skrivs stort på ett blad "
                      "som sätts upp i salen.",
        }
        n = int(g.get("elever") or 3)
        min_ = int(g.get("langd_min") or 45)
        red = str(g.get("redovisning") or "muntligt")
        block.append(
            f"Uppdrag: skriv en GRUPPUPPGIFT för {kurs}, klass {klass}, med "
            f"EXAKT {antal} uppgifter (varken fler eller färre). {n} elever per "
            f"grupp arbetar tillsammans i {min_} minuter. {REDOV.get(red, REDOV['muntligt'])}\n"
            # STEGRINGEN (Del F, lärarens första dom). Här stod förut att
            # uppgifterna är «fyra ingångar till samma sak, inte en trappa, så
            # de behöver inte bli svårare nedåt». Lärarens skarpa lektion sa
            # emot: stegringen var det som fungerade. ALLA klarade den första
            # uppgiften, bara några få grupper den sista — men någon klarade
            # den. Det är målprofilen, och den vinner över formuleringen.
            #
            # Kravet ligger i PROMPTEN, inte i valideringen: PROFILER har
            # fortfarande stigande=False för gruppuppgift. Ordningsvalidatorn
            # mäter svårighet i poängtripplar, och en gruppuppgift på fyra
            # uppgifter har för få steg för att det måttet ska säga något om
            # just den här stegringen. Mät i kassetterna innan den slås på.
            "Uppgifterna ska KRÄVA att man pratar. Formen bär samtalet — en "
            "uppgift som är öppen, som kan angripas "
            "på flera sätt eller som ber gruppen enas om ett svar kräver "
            "samtal oavsett vilken förmåga den prövar. Kravet ligger alltså "
            "INTE på förmågefördelningen: en begrepps- eller procedurpoäng är "
            "fullt legitim här när den är ingången till resonemanget.\n"
            "Balansen räknas på de poängbärande enheterna, alltså på "
            "DELUPPGIFTERNA när uppgiften har sådana. Sätter du egen formaga "
            "på en deluppgift är det den som räknas, inte förälderns — så "
            "deluppgifterna ska ÄRVA uppgiftens förmåga (utelämna formaga på "
            "dem). Annars står förmågan i uppgiften men bär noll poäng.\n"
            f"{FALLGROPAR_GRUPP}\n"
            "Bygg in ställningen i uppgiften: en uppgift som ska diskuteras "
            "delas i deluppgifter som leder samtalet framåt (undersök, "
            "formulera, motivera). MINST EN av uppgifterna ska ändå vara en "
            "rutinuppgift där endast svar krävs — utan den saknar upplägget "
            "ingången för den som inte kommer igång, och E-tyngden blir för "
            "stor.\n"
            "STEGRING: ordna uppgifterna så att den FÖRSTA är ingången varenda "
            "grupp klarar och den SISTA utmanar de starkaste. Målet är mätt i "
            "en riktig klass: alla klarar den första, och några få grupper — "
            "men inte noll — klarar den sista. Är den sista så svår att ingen "
            "kommer i mål är den fel skriven, och är den lika lätt som den "
            "första finns ingen stegring.\n"
            f"{FORLAGA_GRUPP}\n"
            # Nivån står EFTER mönstret och inte före: utdragen är ett
            # 1a-papper, och raden här är den som säger att måtten i dem gäller
            # 1a och ingen annan kurs. Läses den först är den en abstraktion
            # utan något att korrigera.
            f"{_nivastegen(kurs)}\n"
            # Bandet är dokumentets från och med nu (exam_spec.instruktion).
            # Skrivs det inte här får pappret appens mall, och då är rutan
            # oåtkomlig för läraren: hon kan peka på den i granskningen, men
            # det finns ingen text i JSON:en att skriva om.
            #
            # MINNESREGELN är lärarens egen begäran, skriven tre gånger samma
            # natt: «prioriteringsreglerna ska stå kort här i den här
            # instruktionsrutan». Rutan är det gruppen har framför sig när den
            # fastnar, och en rad om momentet där är billigare än en lärare som
            # går runt och säger samma sak fyra gånger.
            "Skriv instruktionsbandet i fältet \"instruktion\": arbetsregeln "
            "först — läs uppgiften tillsammans, bestäm vem som skriver, alla i "
            "gruppen ska kunna förklara lösningen efteråt — sedan "
            f"redovisningslöftet ordagrant: \"{REDOV.get(red, REDOV['muntligt'])}\" "
            "och sist EN kort minnesregel för momentet, den lärarens egen röst "
            "skulle säga vid tavlan («Kom ihåg räkneordningen: parenteser "
            "först, sedan potenser, sedan gånger och delat, sist plus och "
            "minus.»). Korta meningar, vardagliga ord, inga tankstreck — "
            "läraren strök den första versionen med orden «skriv mycket "
            "kortare och mycket enklare». "
            "Skriv inte nyckelfrågan där; den har ett eget fält.\n"
            "Inga delar (del: null på alla uppgifter). Fyll fältet \"grupp\" "
            f"med elever={n}, langd_min={min_}, redovisning=\"{red}\". "
            # Inspelningen skrev «tid_minuter» bredvid grupp — ett fält som
            # inte finns, och hela dokumentet föll på extra=forbid. Tiden HAR
            # två hem i schemat (grupp.langd_min och tid_min), så säg vilka.
            f"Provtiden hör hemma i tid_min={min_} och ingen annanstans — "
            "hitta inte på egna fält (tid_minuter, tidsatgang …), de avvisas. "
            "Svara med enbart JSON.")
        # Gruppuppgiften får sin uppgiftsplan som TEXT, inte som grammatik.
        # Grammatiklåsningen (to_response_format med skeleton) tvingar varje
        # uppgift att bära poäng själv, och en uppgift med poäng får per schemat
        # inga deluppgifter — men det är just deluppgifterna som är gruppens
        # ställning («undersök, formulera, motivera»). Låsningen skulle alltså
        # köpa jämnhet för priset av formen. Planen räknas därför fram på samma
        # sätt som för de andra profilerna, men lämnas som en instruktion, och
        # balansvalideringen får fälla om modellen frångår den.
        if skeleton:
            block.append(_skelett_plan(skeleton, last=False))
        # Nivåförankringen (C2): gruppuppgiften är inte en trappa, så bokens
        # skala används som GOLV och TAK i stället för som stigning.
        block.append(boknivaer or niva_rubrik.build_skala_utan_bok(profil))
    elif profil == "diagnos":
        if skeleton:
            block.append(_skelett_plan(skeleton))
        block.append(
            f"Uppdrag: skriv en DIAGNOS för {kurs}, klass {klass} — ett brett "
            f"och grunt sållningspapper på {tid_min} minuter, med EXAKT "
            f"{antal} uppgifter (varken fler eller färre). Inga delar "
            "(del: null på alla uppgifter).\n"
            "Diagnosen är inte ett prov och inte ett arbetsblad. Den ställer "
            "EN fråga per innehållspunkt — «sitter det här?» — och går sedan "
            "vidare. Därför:\n"
            "- Varje uppgift hör till sin punkt i uppgiftsplanen och ska pröva "
            "just DEN, inte en blandning av kursen.\n"
            "- Håll uppgifterna KORTA och entydiga. En elev som kan punkten ska "
            "vara klar på några minuter; en som inte kan den ska fastna direkt, "
            "så att tomrummet syns.\n"
            "- Inga flerstegsproblem och inga uppgifter som kräver en lång "
            "redovisning — läraren ska kunna rätta hela klassens diagnos på en "
            "håltimme.\n"
            "- Bedömningsanvisningen ska säga vad ett SVAGT svar på just den "
            "punkten ser ut som, inte bara var poängen sitter. Det är den "
            "läraren läser när hon letar efter hålet.\n"
            "Lösningsförslagen blir facit, och facit ska vara kort: svaret och på sin höjd ett par led. Svara med enbart JSON.")
        block.append(niva_rubrik.build_skala_utan_bok("diagnos"))
    elif profil == "arbetsblad":
        if skeleton:
            block.append(_skelett_plan(skeleton))
        block.append(
            f"Uppdrag: skriv ett ARBETSBLAD (övningsblad, inte prov) för "
            f"{kurs}, klass {klass}, med EXAKT {antal} uppgifter (varken fler "
            f"eller färre). Tyngden ligger på övning och rutin — men det är "
            "uppgifternas FORM som ska vara övande, inte förmågefördelningen: "
            "alla sex förmågor ska vägas lika, och en kommunikationsuppgift på "
            "ett arbetsblad är «förklara med ord varför …» i drillformat, inte "
            "en uppsats. Inga delar behövs (del: null på alla uppgifter). "
            # Samma skäl som på gruppuppgiften: rutan måste stå i dokumentet
            # för att kunna ändras (exam_spec.instruktion).
            "Skriv instruktionsbandet i fältet \"instruktion\": svaret skrivs "
            "på svarsraden, de uppgifter som ska redovisas är märkta och "
            "uppgiftens bokstav skrivs överst på lösbladet, och räkningen ska "
            "visas — inte bara svaret. "
            "Lösningsförslagen blir facit, och facit ska vara kort: svaret och på sin höjd ett par led. Svara med enbart JSON.")
        # «Stigande svårighet» stod här förut, och det är en instruktion utan
        # skala: svårare ÄN VAD? Nu följer skalan med — bokens egen när läraren
        # slagit upp ett uppslag, annars NP-rubriken.
        block.append(boknivaer or niva_rubrik.build_skala_utan_bok(profil))
    else:
        # Balanserat skelett: modellen klarar inte den flerdimensionella
        # balansen (förmåga × nivå) själv, så appen låser del/förmåga/typ/poäng
        # per uppgift (grammatik) och ger planen här så innehållet matchar.
        if skeleton is None:
            skeleton = exam_spec.balanced_skeleton(antal, profil, delar=delar)
        if skeleton is not None:
            block.append(_skelett_plan(skeleton))
        # Nivårubriken står omedelbart efter uppgiftsplanen (C3). Planen säger
        # att uppgift 4 är värd (0, 2, 0); rubriken säger vad de två C-poängen
        # KRÄVER av innehållet. Var för sig är de en siffra och en abstraktion.
        block.append(niva_rubrik.build_niva_block(
            sorted({s["typ"] for s in skeleton}) if skeleton else None,
            sorted({s["formaga"] for s in skeleton}) if skeleton else None))
        delar_txt = ("Dela provet i Del B (utan räknare) och Del C (med räknare)."
                     if delar else "Provet har inga delar (del: null på alla uppgifter).")
        block.append(
            f"Uppdrag: skriv ett prov för {kurs}, klass {klass}, med EXAKT "
            f"{antal} uppgifter (varken fler eller färre) för {tid_min} "
            f"minuters provtid. {delar_txt} Svara med enbart JSON.")
    return "\n\n".join(block)


# ─────────────────────────────────────────────────────── nivådomaren (C4) ──
# Prompten kan BEGÄRA rätt nivå; bara en kontroll kan garantera den. Domaren är
# ett eget modellanrop som får uppgifterna utan poäng, utan bedömnings-
# anvisningar och utan elevlösningar — allt tre avslöjar facit — och klassar dem
# blint. Avviker domen från poängsättningen går skillnaden in i den BEFINTLIGA
# reparationsloopen som ett problem bland andra.

DOMAR_MAX_TOKENS = 4_000
# Hur många hela nivåsteg domen måste skilja sig för att fälla. 1 = E mot C
# fäller. Höj till 2 om mätningen visar att domaren bråkar om gränsfall.
#
# MÄTT (planens C7, punkt 4) över de skarpa kassetterna, två inspelnings-
# omgångar av samma tre dokument:
#
#     omgång 1:  prov 1/8    arbetsblad 0/6   gruppuppgift 1/12   =  2/26  (8 %)
#     omgång 2:  prov 2/11   arbetsblad 0/7   gruppuppgift 6/11   =  8/29  (28 %)
#
# Spridningen mellan omgångarna är alltså större än skillnaden en toleranshöjning
# skulle göra, och underlaget är ett dokument per typ och omgång. Därför står
# toleransen kvar på 1: att skruva på den här siffran utifrån n=2 vore att
# kalibrera mot brus. Två saker är ändå värda att veta innan någon rör den:
# arbetsbladet föll ALDRIG (dess uppgifter är rutin, och där är domaren och
# poängsättningen enkelt eniga), och gruppuppgiften står för nästan hela
# utfallet. Det är väntat — gruppuppgiften är den enda profilen utan
# balanserat skelett, så poängen är modellens eget påstående och ingen
# grammatik håller emot. Domaren är därför mest värd där.
#
# Domaren svarade «oklart» noll gånger i båda omgångarna. Toleransen bärs i
# praktiken av tystnad (en enhet domaren inte nämner fälls aldrig), inte av
# att den hedgar.
TOLERANS_STEG = 1
# Taket på hur många nivåproblem som får gå in i EN reparationsprompt. Fler än
# så är inte en lista fel utan ett underkänt prov, och då är det bättre att
# rätta de tyngsta och visa resten för läraren än att be om allt på en gång.
MAX_DOMAR_PROBLEM = 6

_NIVA_ORD = {"E": 0, "C": 1, "A": 2}


def _err(path: str, code: str, message: str) -> dict:
    """Samma maskinläsbara felform som exam_spec använder — reparationsloopen
    läser nivåfynden med samma _format_problems som balansfelen."""
    return {"path": path, "code": code, "message": message}

DOMAR_SYSTEM = (
    "Du är en erfaren bedömare av svenska nationella prov i matematik. Du får "
    "uppgifter UTAN poängsättning och ska avgöra vilken nivå var och en "
    "faktiskt ligger på. Du svarar ALLTID med giltig JSON enligt schemat, "
    "ingenting annat."
)

DOMAR_SCHEMA = {
    "type": "object",
    "properties": {
        "domar": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nr": {"type": "string"},
                    # "oklart" är inte en artighet utan toleransen själv: en
                    # uppgift som ärligt ligger mellan två nivåer ska inte
                    # kosta en reparationsrunda.
                    "niva": {"type": "string",
                             "enum": ["E", "C", "A", "oklart"]},
                    "motivering": {"type": "string"},
                },
                "required": ["nr", "niva"],
            },
        },
    },
    "required": ["domar"],
}


def _niva_ur_poang(poang) -> str | None:
    """Enhetens PÅSTÅDDA nivå = den högsta nivå den ger poäng på.

    En enhet med (1, 1, 0) kräver E-färdighet för första poängen och
    C-färdighet för den andra; taket är C, och det är taket domaren prövar —
    det är där en felskriven uppgift blir fel."""
    try:
        e, c, a = (int(x) for x in poang)
    except (TypeError, ValueError):
        return None
    if a > 0:
        return "A"
    if c > 0:
        return "C"
    return "E" if e > 0 else None


def domarenheter(exam: dict) -> list[dict]:
    """En rad per poängbärande enhet: numret läraren ser, uppgiftstypen, den
    påstådda nivån och det BLINDA kortet domaren får se.

    Numreringen är uppgiftsplanens (1-baserad i uppgiftslistan) med bokstav för
    deluppgift — «4» och «4b» — så att domarens svar går att para ihop igen och
    reparationsprompten pekar på samma uppgift som skelettet gjorde."""
    ut: list[dict] = []
    for i, u in enumerate(exam.get("uppgifter") or [], 1):
        if not isinstance(u, dict):
            continue
        delar = [d for d in (u.get("deluppgifter") or []) if isinstance(d, dict)]
        if delar:
            for j, d in enumerate(delar):
                niva = _niva_ur_poang(d.get("poang"))
                if niva is None:
                    continue
                ut.append({
                    "nr": f"{i}{chr(ord('a') + j)}",
                    "typ": d.get("typ") or u.get("typ") or "",
                    "formaga": d.get("formaga") or u.get("formaga") or "",
                    "poang": d.get("poang"),
                    "niva": niva,
                    # Stammen följer med — utan den är deluppgiften obegriplig.
                    "kort": {"stam": u.get("text") or "",
                             "text": d.get("text") or "",
                             "losning": d.get("losning") or "",
                             "typ": d.get("typ") or u.get("typ") or "",
                             "formaga": d.get("formaga") or u.get("formaga") or ""},
                })
            continue
        niva = _niva_ur_poang(u.get("poang"))
        if niva is None:
            continue
        ut.append({
            "nr": str(i),
            "typ": u.get("typ") or "",
            "formaga": u.get("formaga") or "",
            "poang": u.get("poang"),
            "niva": niva,
            "kort": {"text": u.get("text") or "",
                     "losning": u.get("losning") or "",
                     "typ": u.get("typ") or "",
                     "formaga": u.get("formaga") or ""},
        })
    return ut


def build_domar_prompt(enheter: list[dict], *, skala: str = "") -> str:
    """Domarprompten. `skala` är den nivåskala dokumentet skrevs mot — bokens
    egen för arbetsblad och gruppuppgift, NP-rubriken för prov — och den ska
    vara SAMMA text som genereringen fick. Bedöms dokumentet mot en annan skala
    än den skrevs mot mäter domaren fel sak."""
    kort = [{"nr": e["nr"], **e["kort"]} for e in enheter]
    return (
        (skala or niva_rubrik.build_niva_block()) + "\n\n"
        "Nedan står uppgifterna ur ett dokument, UTAN poäng och utan "
        "bedömningsanvisningar. Avgör för var och en vilken nivå den faktiskt "
        "ligger på — E, C eller A enligt beskrivningarna ovan.\n"
        f"{json.dumps(kort, ensure_ascii=False)}\n\n"
        "Svara med JSON: en post per uppgift med nr (exakt som ovan), niva och "
        "en kort motivering på en mening. Döm på vad uppgiften KRÄVER av "
        "eleven, inte på hur den låter. Ligger en uppgift ärligt mitt emellan "
        "två nivåer svarar du \"oklart\" — det är ett riktigt svar, och bättre "
        "än en gissning. Svara med enbart JSON."
    )


def _parse_domar(raw: str) -> dict[str, dict]:
    """Domarsvaret → {nr: {niva, motivering}}. Ett svar som inte går att tolka
    ger en tom dom, och då fäller domaren ingenting: en trasig kontroll ska
    aldrig kunna underkänna ett prov som är rätt.

    Går INTE genom _parse_exam. Den städar bort toppnycklar som inte hör till
    ExamDoc, och `domar` är en av dem — hela svaret hade försvunnit tyst."""
    data = _json_objekt(raw)
    if not isinstance(data, dict):
        return {}
    ut: dict[str, dict] = {}
    for d in data.get("domar") or []:
        if not isinstance(d, dict):
            continue
        nr = str(d.get("nr") or "").strip()
        niva = str(d.get("niva") or "").strip().upper()
        if not nr:
            continue
        ut[nr] = {"niva": niva if niva in _NIVA_ORD else "OKLART",
                  "motivering": str(d.get("motivering") or "").strip()}
    return ut


def _niva_problem(enhet: dict, dom: dict) -> dict:
    """Avvikelsen formulerad som en ÅTGÄRD. En rad som bara konstaterar att
    nivåerna skiljer sig ger modellen inget att göra; den här säger vad som ska
    ändras och enligt vilken beskrivning."""
    pastadd, domd = enhet["niva"], dom["niva"]
    riktning = "höj" if _NIVA_ORD[domd] < _NIVA_ORD[pastadd] else "sänk"
    krav = niva_rubrik.RUBRIK_PER_TYP.get(enhet["typ"], {}).get(pastadd, "")
    steget = niva_rubrik.STEGET_UPP.get(f"{domd}→{pastadd}", "")
    text = (f"uppgift {enhet['nr']} är poängsatt {pastadd} men bedöms som "
            f"{domd} — {riktning} svårigheten så innehållet motsvarar "
            f"{pastadd}.")
    if dom.get("motivering"):
        text += f" Bedömarens skäl: {dom['motivering']}"
    if krav:
        text += f" {pastadd} för en {enhet['typ']}suppgift: {krav}"
    if riktning == "höj" and steget:
        text += f" Steget {domd}→{pastadd}: {steget}"
    return _err(f"uppgift {enhet['nr']}", "niva", text)


def avvikelser(enheter: list[dict], domar: dict[str, dict]) -> list[dict]:
    """Domen mot poängsättningen. Enheter domaren inte nämnde, eller svarade
    «oklart» om, passerar — toleransen ligger i att INTE tolka tystnad."""
    ut = []
    for e in enheter:
        dom = domar.get(e["nr"])
        if not dom or dom["niva"] not in _NIVA_ORD:
            continue
        if abs(_NIVA_ORD[dom["niva"]] - _NIVA_ORD[e["niva"]]) < TOLERANS_STEG:
            continue
        ut.append(_niva_problem(e, dom))
    return ut[:MAX_DOMAR_PROBLEM]


def doma_nivaer(exam: dict, *, model: str, llm=llm_client.generate,
                skala: str = "",
                log_cb: Callable[[str], None] | None = None) -> list[dict]:
    """Ett blint domaranrop → avvikelser mot poängsättningen."""
    log = log_cb or (lambda _m: None)
    enheter = domarenheter(exam)
    if not enheter:
        return []
    log("Kontrollerar uppgifternas nivå …")
    try:
        raw = llm(
            model, build_domar_prompt(enheter, skala=skala),
            system=DOMAR_SYSTEM,
            options={"temperature": 0.0},
            response_format={"type": "json_schema",
                             "json_schema": {"name": "nivadom",
                                             "schema": DOMAR_SCHEMA}},
            max_tokens=DOMAR_MAX_TOKENS,
            token_cb=None,
        )
    except Exception as e:                          # noqa: BLE001
        # Domaren är en EXTRA kontroll. Faller anropet — modellen borta, kvoten
        # slut, nätet nere — ska provet ändå levereras: det är färdigt och
        # validerat, och att kasta bort det för att en frivillig kvalitetskoll
        # inte gick igenom vore att straffa läraren för fel sak.
        log(f"Nivåkontrollen kunde inte köras ({e}) — provet levereras ändå.")
        return []
    return avvikelser(enheter, _parse_domar(raw))


# ── Deterministiska nivåsignaler ──────────────────────────────────────────
# Billiga, körs alltid, och de AVGÖR ALDRIG ensamma — de blir varningar läraren
# ser, inte problem som skickas till reparationsloopen.
#
# Varje signal nedan är RÄKNAD i underlaget (app/niva_rubrik.ANALYSERADE_PROV),
# inte gissad. Det är en viktig skillnad: den första versionen av den här
# funktionen flaggade «A-poäng på en rutinuppgift» och «A-poäng utan orden visa
# eller motivera», och materialet fällde båda. Nationella provet ger A-poäng på
# kortsvarsuppgifter i alla fyra proven, och flera av dem innehåller inte ett
# enda av de orden. En signal som fäller riktiga NP-uppgifter är värdelös.

# Öppen formulering: sanningsvärdet är inte givet på förhand. Förekommer i
# underlaget bara på C- och A-uppgifter, aldrig på E.
_OPPEN_RE = re.compile(r"\b(undersök|utred|går det att avgöra|för vilka värden)",
                       re.I)
# Givet sanningsvärde: eleven ska bekräfta ett påstående som redan är sant. I
# underlaget är sådana uppgifter C-nivå när verktyget är en standardregel.
_GIVET_RE = re.compile(r"\b(visa att|bevisa att)", re.I)


def nivasignaler(exam: dict) -> list[dict]:
    """Deterministiska varningar om innehåll som säger emot poängsättningen."""
    ut: list[dict] = []
    for e in domarenheter(exam):
        nr, text = e["nr"], e["kort"].get("text", "")
        poang = e.get("poang") or (0, 0, 0)
        # 1. Kommunikationspoäng på E-nivå. Räknat i underlaget: CK 1–3 och
        #    AK 0–3 per prov, EK noll gånger i alla fyra — bedömnings-
        #    anvisningarna säger rent ut att skriftlig kommunikation inte bedöms
        #    särskilt på E-nivå för enskilda uppgifter.
        if e.get("formaga") == "K" and poang[0]:
            ut.append(_err(f"uppgift {nr}", "nivasignal",
                           f"uppgift {nr} ger {poang[0]} E-poäng i "
                           "kommunikation — nationella provet delar aldrig ut "
                           "kommunikationspoäng på E-nivå."))
        # 2. «Visa att …» med A-poäng. Sanningsvärdet är givet och verktyget är
        #    normalt en standardregel; i underlaget är sådana uppgifter C.
        if e["niva"] == "A" and _GIVET_RE.search(text):
            ut.append(_err(f"uppgift {nr}", "nivasignal",
                           f"uppgift {nr} ger A-poäng men ber eleven visa ett "
                           "påstående som redan sägs vara sant — i underlaget "
                           "är den formen C. A kräver att sanningsvärdet är "
                           "okänt («undersök om …») eller att alla fall täcks."))
        # 3. Öppen formulering med bara E-poäng. Motsatt fel, samma mätning.
        if e["niva"] == "E" and _OPPEN_RE.search(text):
            ut.append(_err(f"uppgift {nr}", "nivasignal",
                           f"uppgift {nr} är formulerad som en utredning men "
                           "ger bara E-poäng — den formen förekommer inte på "
                           "E-nivå i underlaget."))
    return ut


def _format_problems(problems: list) -> str:
    lines = []
    for p in problems:
        if isinstance(p, dict):
            lines.append(f"- {p.get('path', '?')}: {p.get('message', p)}")
        else:
            lines.append(f"- {p}")
    return "\n".join(lines)


# Vad dokumentet HETER i reparationsprompten. Prompten sa «Ditt förra prov»
# oavsett vad som skrevs, och det är fel på två sätt: modellen får höra att ett
# arbetsblad är ett prov mitt i en rättning (och arbetsbladet har varken delar
# eller kravgränser), och uppspelningen kunde inte se vilket dokument
# reparationen gällde — den lade i provets band när en gruppuppgift skulle
# lagas, så gruppuppgiften «lagades» till ett prov (tests/fejk.py _VAL).
# Versalerna är avsiktliga och delas med uppdragsraderna i build_prompt.
_DOKUMENTNAMN = {
    "arbetsblad": ("ditt förra ARBETSBLAD", "arbetsbladet"),
    "gruppuppgift": ("din förra GRUPPUPPGIFT", "gruppuppgiften"),
    "diagnos": ("din förra DIAGNOS", "diagnosen"),
}


def build_repair_prompt(exam: dict, problems: list, profil: str = "prov") -> str:
    vems, det = _DOKUMENTNAMN.get(profil, ("ditt förra prov", "provet"))
    return (
        f"{INSTRUCTION}\n"
        f"Det finns problem i {vems} som måste rättas. Här är {det}:\n"
        f"{json.dumps(exam, ensure_ascii=False)}\n\n"
        "Problem att åtgärda:\n"
        f"{_format_problems(problems)}\n\n"
        f"Skriv om HELA {det} som JSON med problemen åtgärdade — justera "
        "poäng eller byt enstaka uppgifter, ändra så lite som möjligt i "
        "övrigt. Svara med enbart JSON."
    )


def build_refine_prompt(exam: dict, instruction: str,
                        nummer: int | None = None,
                        mal: dict | None = None, bok: str = "",
                        historik=None) -> str:
    """Riktad omgenerering: 'byt uppgift 4', 'gör 7 svårare' …

    `nummer` är uppgiften önskemålet gäller. `mal` är det läraren PEKADE PÅ i
    granskningen när det inte är en uppgift — sidhuvudet, instruktionen,
    namnraderna, en post i facit (llm_client.malrad). `bok` är bokdörrens block:
    genereringen har alltid fått det, iterationen fick det inte, och därför
    kunde ett önskemål om bokens uppgifter bara besvaras allmänt. `historik` är
    lärarens tidigare önskemål för utkastet (llm_client.varvrad)."""
    onskemal = (f"Lärarens önskemål gäller uppgift {nummer}: {instruction}"
                if nummer else f"Lärarens önskemål: {instruction}")
    kallor = f"{bok.strip()}\n\n" if bok and bok.strip() else ""
    return (
        f"{INSTRUCTION}\n"
        f"{kallor}"
        "Här är det nuvarande provet:\n"
        f"{json.dumps(exam, ensure_ascii=False)}\n\n"
        f"{llm_client.varvrad(historik)}"
        f"{'' if nummer else llm_client.malrad(mal)}{onskemal}\n\n"
        "Skriv om HELA provet som JSON med önskemålet genomfört. Övriga "
        "uppgifter lämnas oförändrade. Ändrar du en uppgifts text eller tal "
        "ska uppgiftens losning, bedomning och deluppgifternas lösningar "
        "skrivas om så att de stämmer med den nya lydelsen — facit får aldrig "
        "beskriva en tidigare version av uppgiften. "
        # Och åt ANDRA hållet, som är lärarens egna ord: «Om jag ändrar något i
        # facit så ska uppgiften också ändras. Exempelvis om jag efterfrågar
        # att det ska vara enklare, mindre tal, och svaret ska bli ett heltal —
        # då bör uppgiften också reflektera det.» Hon pekar på facitposten och
        # beskriver SVARET, för det är svaret hon har framför sig; men det som
        # bestämmer svaret är uppgiftens tal. Skrevs bara facit om räknade det
        # på andra tal än uppgiften, och då är facit värre än inget.
        "Det gäller åt BÅDA håll: gäller önskemålet lösningen eller facit "
        "(enklare tal, ett heltal som svar, en annan metod) ska uppgiftens "
        "text och TAL ändras så att de ger just det — uppgift och facit är "
        "samma sak sedd från två håll, och ett facit som räknar på andra tal "
        "än uppgiften är värre än inget facit alls. Svara med enbart JSON."
    )


def build_latexfix_prompt(exam: dict, error_log: str) -> str:
    return (
        f"{INSTRUCTION}\n"
        "PDF-kompileringen av provet misslyckades. Här är provet:\n"
        f"{json.dumps(exam, ensure_ascii=False)}\n\n"
        "Kompilatorns felmeddelande:\n"
        f"{error_log}\n\n"
        "Felet beror nästan alltid på trasig LaTeX-matte i något text-, "
        "losning- eller bedomning-fält (obalanserade $, klamrar eller "
        "okända kommandon). Rätta fälten och skriv om HELA provet som JSON. "
        "Svara med enbart JSON."
    )


# Modellen skriver ofta LaTeX oescapat i JSON-strängar ("$2 \times 3$").
# json.loads tolkar då \t, \n, \b, \f, \r som kontrolltecken och äter
# backslashen — kvar blir "2 <TAB>imes 3". Reparationen körs enbart inuti
# $…$-segment och enbart när kontrolltecknet följs av en bokstav, så
# äkta radbrytningar i löptext lämnas orörda.
_CTRL_TO_LETTER = {"\t": "t", "\n": "n", "\r": "r", "\f": "f", "\b": "b"}
_MATH_SEG = re.compile(r"\$[^$]*\$")
_CTRL_CMD = re.compile(r"[\t\n\r\f\b](?=[A-Za-z])")


def _fix_math_escapes(s: str) -> str:
    return _MATH_SEG.sub(
        lambda m: _CTRL_CMD.sub(
            lambda c: "\\" + _CTRL_TO_LETTER[c.group(0)], m.group(0)),
        s)


def _repair_ctrl_chars(x):
    if isinstance(x, str):
        return _fix_math_escapes(x)
    if isinstance(x, list):
        return [_repair_ctrl_chars(i) for i in x]
    if isinstance(x, dict):
        return {k: _repair_ctrl_chars(v) for k, v in x.items()}
    return x


def _rensa_toppnycklar(exam: dict | None) -> dict | None:
    """Släng toppnycklar som inte hör till dokumentet.

    Sedan schemat flyttade in i PROMPTEN (app/claude_code.SCHEMA_TAK — det får
    inte plats på kommandoraden) finns inget grammatiktvång kvar, och modellen
    lägger gärna till fält den tycker hör hemma på ett prov: `totalpoang`,
    `tid_minuter`. (`instruktion` stod i den listan och städades bort — då ägde
    appen instruktionsbandet. Nu är det ett riktigt fält i ExamDoc och
    passerar.) Schemat förbjuder extra fält, så ETT sådant
    ord kostade en hel reparationsrunda — en ny 12 000-token-generering för att
    ta bort tre rader appen ändå räknar ut själv (observerat i en skarp
    inspelning, tests/kassetter/prov.json).

    Bara TOPPNIVÅN städas. Ett extra fält inne i en uppgift betyder att
    modellen missförstått uppgiftens form, och det ska fortfarande gå tillbaka
    som ett fel att rätta."""
    if not isinstance(exam, dict):
        return exam
    tillatna = set(exam_spec.ExamDoc.model_fields)
    return {k: v for k, v in exam.items() if k in tillatna}


def _json_objekt(raw: str):
    """JSON ur ett modellsvar — hela objektet, ostädat. Modellen ramar ofta in
    svaret i en mening eller ett kodstaket, så den yttersta klammern får
    plockas ut."""
    try:
        return _repair_ctrl_chars(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if m:
            try:
                return _repair_ctrl_chars(json.loads(m.group(0)))
            except json.JSONDecodeError:
                return None
    return None


def _parse_exam(raw: str) -> dict | None:
    data = _json_objekt(raw)
    return _rensa_toppnycklar(data) if data is not None else None


def _validate(exam: dict, profil: str, koder: list[str] | None = None,
              niva_mal: dict | None = None):
    """validate_exam_json + variationskontroll (BARA prov) + CI-taggningen.
    Repetition matas in i reparationsloopen precis som balansfel; arbetsbladet
    undantas (det får drilla samma frågetyp med flit, jfr antiklumpningen).

    `niva_mal` är lärarens nivåval (exam_spec.NIVAVAL) — samma band som
    skelettet söktes mot. Utan dem hade reparationsloopen mätt ett «Bara
    E»-prov mot NP-banden och slagits med skelettet varv efter varv.

    CI-kontrollen behövs vid sidan av grammatiken därför att gruppuppgiften
    genereras UTAN grammatiklås — se generate_exam. Diagnosen prövas dessutom
    på TÄCKNINGEN: en punkt utan uppgift gör hela pappret oläsbart som
    diagnos."""
    doc, errors = exam_spec.validate_exam_json(exam, profil, niva_mal)
    if doc is not None and profil == "prov":
        errors = errors + exam_spec.validate_variation(doc)
    if doc is not None:
        errors = errors + exam_spec.validate_ci(doc, koder)
    if doc is not None and profil == "diagnos":
        errors = errors + exam_spec.validate_tackning(doc, koder)
    return doc, errors


def _llm_round(prompt: str, model: str, llm, antal: int | None = None,
               skeleton: list[dict] | None = None,
               koder: list[str] | None = None) -> dict | None:
    raw = llm(
        model, prompt,
        system=SYSTEM,
        options={"temperature": 0.3},
        # antal → grammatik-tak; skeleton → låst del/förmåga/typ/poäng per
        # uppgift (balans garanterad); koder → innehall låst till lärarens valda
        # CI-punkter. Gäller även reparationsrundorna.
        response_format=exam_spec.to_response_format(antal, skeleton, koder),
        max_tokens=EXAM_MAX_TOKENS,
        token_cb=None,
    )
    return _parse_exam(raw)


# ── Riktad omskrivning: målet är spelplanen ────────────────────────────────
#
# Prompten lovar «Övriga uppgifter lämnas oförändrade», och ett löfte som bara
# står i en prompt är inget löfte. Läraren pekade på uppgift D och bad att
# deluppgift b) skulle bort. Modellen skrev om ALLA fyra uppgifterna och bytte
# hela sammanhanget — bygg blev pizza — och hon fick ångra varvet. Servern
# håller löftet i stället för att be om det: pekade hon på något avgränsat
# byggs svaret som ORIGINALET plus kandidatens ändring av just det målet, och
# resten tas ordagrant ur originalet. Kandidatens övriga påhitt slängs.
#
# Utan mål är hela dokumentet spelplanen som förut — «gör hela provet lättare»
# ska få röra allt, och det är då läraren VET att allt kan ändras.
#
# Nycklarna är klientens element-id (blad.js markera(), samma schema som
# dokumentdiff läser) och kommer in som `mal.el`.
_MALETS_FALT = {
    # Sidhuvudet: bara titeln är modellens. Kurs, klass, elev och datum är
    # lärarens val och skrivs av routen — modellen ska inte kunna döpa om
    # klassen för att den bad om en ny rubrik.
    "rubrik": ("titel",),
    # Instruktionsbandet: bandtexten och nyckelfrågan. Hjälpmedelsregeln står
    # visserligen också i bandet på provet, men den ÄR provtabellens fält och
    # ändras genom den — två mål som äger samma rad drar den fram och tillbaka.
    "instr": ("instruktion", "nyckelfraga"),
    # Metaraden och namnraderna läses båda ur gruppupplägget.
    "meta": ("grupp", "tid_min", "hjalpmedel"),
    "namn": ("grupp",),
    # Provtabellen: skrivtiden och hjälpmedelsregeln.
    "avtal0": ("tid_min", "hjalpmedel"),
    # avtal1 (betygsgränserna) står INTE här, och ska inte göra det: gränserna
    # RÄKNAS ur poängen (exam_spec.kravgranser) och går bara att flytta genom
    # att uppgifternas poäng ändras. Målet är alltså hela dokumentet, inte ett
    # fält, och då gäller den fria vägen nedan.
}


def riktat_mal(nummer: int | None, mal: dict | None):
    """Vad omskrivningen får röra.

    ``("uppgift", n)`` — bara uppgift n. ``("falt", nycklar)`` — bara de
    toppnycklarna. ``None`` — hela dokumentet, som förut. Numret vinner över
    elementet: det är precisare, och klienten skickar båda när läraren pekat
    på en uppgift."""
    if nummer:
        return ("uppgift", int(nummer))
    falt = _MALETS_FALT.get(str((mal or {}).get("el") or "").strip())
    return ("falt", falt) if falt else None


def sammanfoga_riktat(original: dict, kandidat: dict,
                      riktning) -> tuple[dict | None, str]:
    """Originalet med kandidatens MÅL inskrivet. ``(dokument, "")`` eller
    ``(None, skäl)`` när kandidaten inte bär målet alls."""
    sort, vad = riktning
    ihop = copy.deepcopy(original)
    if sort == "uppgift":
        kandidatens = kandidat.get("uppgifter")
        egna = ihop.get("uppgifter")
        if not isinstance(kandidatens, list) or not isinstance(egna, list):
            return None, "svaret bar inga uppgifter"
        if not 1 <= vad <= len(kandidatens) or vad > len(egna):
            return None, f"svaret bar ingen uppgift {vad}"
        # HELA uppgiften följer med: texten, poängen, deluppgifterna, lösningen
        # och bedömningen är samma sak sedd från olika håll och hör ihop med
        # målet. Härledda tal (gränser, summor) räknas om ur poängen där de
        # visas (exam_spec.kravgranser/poangsummor) och behöver inget eget
        # bokföringssteg här.
        egna[vad - 1] = copy.deepcopy(kandidatens[vad - 1])
        return ihop, ""
    for nyckel in vad:
        # Bara fält kandidaten FAKTISKT skickade skrivs över. Utelämnar den ett
        # fält är det inget beslut om att ta bort det — och `hjalpmedel` är
        # obligatoriskt, så en utelämning hade gjort dokumentet ogiltigt för att
        # modellen råkade tiga. Ett uttalat null tas däremot på orden.
        if nyckel in kandidat:
            ihop[nyckel] = copy.deepcopy(kandidat[nyckel])
    return ihop, ""


def _repair_until_valid(exam: dict | None, errors: list, *, model: str, llm,
                        rounds_used: int, max_rounds: int, profil: str = "prov",
                        antal: int | None = None, skeleton: list[dict] | None = None,
                        koder: list[str] | None = None,
                        niva_mal: dict | None = None,
                        riktning=None,
                        log_cb: Callable[[str], None] | None = None) -> dict:
    log = log_cb or (lambda _m: None)
    while errors and rounds_used < max_rounds and exam is not None:
        rounds_used += 1
        log(f"Justerar provet (runda {rounds_used} av {max_rounds}) — "
            f"{len(errors)} problem …")
        candidate = _llm_round(build_repair_prompt(exam, errors, profil),
                               model, llm, antal, skeleton, koder)
        if candidate is None:
            errors = [{"path": "svar", "code": "json",
                       "message": "modellen svarade inte med giltig JSON"}]
            continue
        # Reparationen är också en omskrivning av HELA dokumentet, och därför
        # samma grind: har omskrivningen ett mål får rättningsrundan bara röra
        # målet den med. Annars smiter det förbjudna in genom bakdörren i runda
        # två — och det är just den rundan läraren aldrig ser.
        if riktning is not None:
            candidate, skal = sammanfoga_riktat(exam, candidate, riktning)
            if candidate is None:
                errors = [{"path": "mal", "code": "mal", "message": skal}]
                continue
        _doc, new_errors = _validate(candidate, profil, koder, niva_mal)
        exam = candidate
        errors = new_errors
    return {"exam": exam, "errors": errors, "rounds": rounds_used}


def _skala(profil: str, boknivaer: str, skeleton: list[dict] | None) -> str:
    """Den nivåskala dokumentet skrevs mot — exakt samma text som prompten
    fick. Domaren måste mäta mot den och inte mot en annan."""
    if profil == "diagnos":
        # Diagnosen förankras aldrig i boken: den ska mäta kursen, inte det
        # uppslag klassen råkar ha framme.
        return niva_rubrik.build_skala_utan_bok(profil)
    if profil in ("arbetsblad", "gruppuppgift"):
        return boknivaer or niva_rubrik.build_skala_utan_bok(profil)
    return niva_rubrik.build_niva_block(
        sorted({s["typ"] for s in skeleton}) if skeleton else None,
        sorted({s["formaga"] for s in skeleton}) if skeleton else None)


def _niva_pass(exam: dict, errors: list, *, model: str, llm, profil: str,
               skala: str, antal: int | None, skeleton: list[dict] | None,
               rounds_used: int, max_rounds: int, koder: list[str] | None = None,
               niva_mal: dict | None = None,
               log_cb: Callable[[str], None] | None = None) -> dict:
    """Domarrunda + högst EN reparationsrunda på dess fynd (C4).

    Ligger efter balansreparationen med flit: domaren ska läsa det dokument
    läraren annars hade fått, inte ett halvfärdigt mellanläge.

    EN runda, och passet körs bara en gång — domen prövas alltså aldrig om.
    Det är avsiktligt: en andra runda kan kosta ännu en generering, och en loop
    som får spinna på nivåbedömningar spinner på subjektiva gränsdragningar.
    Skruva inte upp det innan fällfrekvensen är MÄTT över kassetterna (planens
    C7, punkt 4)."""
    log = log_cb or (lambda _m: None)
    signaler = nivasignaler(exam)
    avv = doma_nivaer(exam, model=model, llm=llm, skala=skala, log_cb=log_cb)
    if not avv:
        return {"exam": exam, "errors": errors + signaler, "rounds": rounds_used}
    if rounds_used >= max_rounds:
        # Budgeten slut. Avvikelserna visas för läraren i stället — läraren är
        # sista domare (planens C5), och en tyst nivåmiss är värre än en synlig.
        return {"exam": exam, "errors": errors + avv + signaler,
                "rounds": rounds_used}
    log(f"Justerar nivån på {len(avv)} uppgift(er) …")
    kandidat = _llm_round(build_repair_prompt(exam, avv, profil), model, llm,
                          antal, skeleton, koder)
    rounds_used += 1
    if kandidat is None:
        return {"exam": exam, "errors": errors + avv + signaler,
                "rounds": rounds_used}
    _doc, fel = _validate(kandidat, profil, koder, niva_mal)
    res = _repair_until_valid(kandidat, fel, model=model, llm=llm,
                              rounds_used=rounds_used, max_rounds=max_rounds,
                              profil=profil, antal=antal, skeleton=skeleton,
                              koder=koder, niva_mal=niva_mal, log_cb=log_cb)
    # Nivåhöjningen får inte kosta strukturen. Var dokumentet rent före domaren
    # och trasigt efter är omskrivningen en försämring: behåll det gamla och
    # visa nivåfynden som varningar i stället.
    if res["errors"] and not errors:
        return {"exam": exam, "errors": avv + signaler, "rounds": res["rounds"]}
    return {"exam": res["exam"], "rounds": res["rounds"],
            "errors": res["errors"] + nivasignaler(res["exam"] or exam)}


def generate_exam(kurs: str, klass: str, punkter: list[str], *, model: str,
                  antal: int = 10, tid_min: int = 120, delar: bool = True,
                  memory: str = "", teman: str = "", referens: str = "",
                  bilder: str = "", utfall: str = "", bok: str = "",
                  boknivaer: str = "", forlaga: str = "",
                  svart: str = "", fokus: str = "", profil: str = "prov",
                  koder: list[str] | None = None, riktat: str = "",
                  skeleton: list[dict] | None = None,
                  niva_mal: dict | None = None,
                  grupp: dict | None = None, doma: bool = True,
                  llm=llm_client.generate, max_rounds: int = MAX_ROUNDS,
                  log_cb: Callable[[str], None] | None = None) -> dict:
    """Generera ett prov/arbetsblad/gruppuppgift och reparera schema- och
    balansfel inom rundbudgeten. `grupp` är gruppuppgiftens upplägg (elever,
    langd_min, redovisning) och ignoreras för de andra profilerna.
    Returnerar {"exam": dict|None, "errors": [...], "rounds": int}.

    `skeleton` låter anroparen lämna ett färdigt skelett i stället för att
    låta antalet bestämma. Diagnosen gör det: dess platser räknas ur kursens
    innehåll och lektionens längd (exam_spec.diagnosplan). Lärarens nivåval
    gör det också (routes_exam): skelettet byggs då med NIVAVAL-mixen, och
    `niva_mal` MÅSTE följa med som samma vals band — validering och
    reparation mäter annars mot profilens defaultband och river upp det
    skelettet garanterade.

    `doma=False` stänger av nivådomaren (C4). Den kostar ett modellanrop och
    körs annars alltid — nivån är inget som bara ska begäras i prompten.

    `koder` är de centrala innehållspunkter läraren kryssade, som koder. De
    låser `innehall` per uppgift (grammatik + validering) så att varje uppgift
    säger vad den prövar med kursplanens egen identitet. Utan dem faller
    fältet tillbaka på fritext, som förut."""
    log = log_cb or (lambda _m: None)
    log({"arbetsblad": "Skriver arbetsbladet …",
         "gruppuppgift": "Skriver gruppuppgiften …"}.get(profil, "Skriver provet …"))
    ogenomforbart = exam_spec.genomforbarhet(antal, profil)
    if ogenomforbart:
        return {"exam": None, "errors": ogenomforbart, "rounds": 0}
    # Balanserat skelett: appen äger balansen, modellen skriver innehållet.
    # Alla profilerna får ett (Del D1b) — prov med delar, arbetsblad,
    # gruppuppgift och diagnos platta. Diagnosens kommer utifrån
    # (exam_spec.diagnosplan): dess platser är innehållspunkter, inte ett
    # antal, och den dimensionen kan bara räknas där punkterna är kända.
    if skeleton is None:
        skeleton = exam_spec.balanced_skeleton(
            antal, profil, delar=(profil == "prov" and delar))
    antal = len(skeleton) or antal
    # … men bara två av dem GRAMMATIKLÅSES. En låst rad måste bära sina poäng
    # själv, och en uppgift med poäng får inga deluppgifter (exam_spec:
    # föräldern ska ha [0, 0, 0]) — och deluppgifterna ÄR gruppuppgiftens
    # ställning. Där går planen in i prompten i stället, och balansreglerna
    # fäller om modellen frångår den. Provet levde redan med den kostnaden, och
    # arbetsbladet betalar den gärna: en drilluppgift behöver sällan a/b/c.
    grammatik = None if profil == "gruppuppgift" else skeleton
    prompt = build_prompt(kurs, klass, punkter, antal=antal, tid_min=tid_min,
                          delar=delar, memory=memory, teman=teman,
                          referens=referens, bilder=bilder, utfall=utfall,
                          bok=bok, boknivaer=boknivaer, forlaga=forlaga,
                          svart=svart, fokus=fokus,
                          profil=profil, koder=koder, grupp=grupp,
                          riktat=riktat, skeleton=skeleton)
    exam = _llm_round(prompt, model, llm, antal, grammatik, koder)
    rounds = 1
    while exam is None and rounds < max_rounds:
        rounds += 1
        log(f"Modellen svarade inte med giltig JSON — försöker igen "
            f"(runda {rounds} av {max_rounds}) …")
        exam = _llm_round(prompt, model, llm, antal, grammatik, koder)
    if exam is None:
        return {"exam": None,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": rounds}
    _doc, errors = _validate(exam, profil, koder, niva_mal)
    res = _repair_until_valid(exam, errors, model=model, llm=llm,
                              rounds_used=rounds, max_rounds=max_rounds,
                              profil=profil, antal=antal, skeleton=grammatik,
                              koder=koder, niva_mal=niva_mal, log_cb=log_cb)
    if not doma or res["exam"] is None:
        return res
    return _niva_pass(res["exam"], res["errors"], model=model, llm=llm,
                      profil=profil, skala=_skala(profil, boknivaer, skeleton),
                      antal=antal, skeleton=grammatik, koder=koder,
                      niva_mal=niva_mal,
                      rounds_used=res["rounds"], max_rounds=max_rounds,
                      log_cb=log_cb)


def refine_exam(exam: dict, instruction: str, *, model: str,
                nummer: int | None = None, profil: str = "prov",
                mal: dict | None = None, bok: str = "", historik=None,
                niva_mal: dict | None = None,
                llm=llm_client.generate,
                max_rounds: int = MAX_ROUNDS,
                log_cb: Callable[[str], None] | None = None) -> dict:
    """Riktad omgenerering (per-uppgift-chatt); validera + auto-reparera.

    `niva_mal` är dokumentets PERSISTERADE nivåval (exams.nivaval →
    exam_spec.NIVAVAL) — utan det mäts ett «Bara E»-prov mot NP-banden i
    varje varv: nivabalansfel jämt, och riktade ändringar vägras med
    «ingenting ändrades» fast pappret är precis som läraren bad om det."""
    log = log_cb or (lambda _m: None)
    log("Uppdaterar provet …")
    candidate = _llm_round(
        build_refine_prompt(exam, instruction, nummer, mal, bok, historik),
        model, llm)
    if candidate is None:
        return {"exam": exam,
                "errors": [{"path": "svar", "code": "json",
                            "message": "modellen svarade inte med giltig JSON"}],
                "rounds": 1}
    # Är önskemålet riktat är det bara målet som får resa med tillbaka —
    # se _MALETS_FALT. Valideringen körs på SAMMANFOGNINGEN, för det är den
    # som blir papper.
    riktning = riktat_mal(nummer, mal)
    if riktning is not None:
        candidate, skal = sammanfoga_riktat(exam, candidate, riktning)
        if candidate is None:
            return {"exam": exam,
                    "errors": [{"path": "mal", "code": "mal", "message": skal}],
                    "rounds": 1}
    _doc, errors = _validate(candidate, profil, niva_mal=niva_mal)
    res = _repair_until_valid(candidate, errors, model=model, llm=llm,
                              rounds_used=1, max_rounds=max_rounds,
                              profil=profil, niva_mal=niva_mal,
                              riktning=riktning, log_cb=log_cb)
    # Gick målets ändring inte igenom grinden ens efter reparation lämnas
    # ORIGINALET tillbaka, med felen kvar i svaret. Ett halvt genomfört
    # önskemål på ett papper läraren tror är helt är värre än ett önskemål som
    # inte gick igenom: det senare syns (klienten säger det när `andrade` är
    # tom), det förra upptäcks framför klassen.
    if riktning is not None and res["errors"]:
        res["exam"] = exam
    return res


def fix_latex(exam: dict, error_log: str, *, model: str,
              profil: str = "prov",
              llm=llm_client.generate,
              max_rounds: int = MAX_LATEX_ROUNDS,
              log_cb: Callable[[str], None] | None = None,
              rounds_used: int = 0) -> dict:
    """Kompileringsfel → korrigeringsrunda (max 2). Returnerar nytt prov
    (schema-/balansvaliderat) eller det gamla med felen redovisade.

    `profil` styr balansmålen: ett arbetsblad som föll på kompilering ska
    inte få sin korrigering prövad mot PROVETS mix — kandidaten överlevde
    (bara schemafel förkastar den), men fellistan som returnerades var fel
    dokuments."""
    log = log_cb or (lambda _m: None)
    if rounds_used >= max_rounds:
        return {"exam": exam, "errors": [{"path": "latex", "code": "kompilering",
                                          "message": error_log}],
                "rounds": rounds_used}
    log("Rättar LaTeX-fel i provet …")
    candidate = _llm_round(build_latexfix_prompt(exam, error_log), model, llm)
    if candidate is None:
        return {"exam": exam, "errors": [{"path": "svar", "code": "json",
                                          "message": "modellen svarade inte med giltig JSON"}],
                "rounds": rounds_used + 1}
    _doc, errors = exam_spec.validate_exam_json(candidate, profil)
    return {"exam": candidate if _doc is not None else exam,
            "errors": errors, "rounds": rounds_used + 1}
