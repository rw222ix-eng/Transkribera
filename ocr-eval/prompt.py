"""Den gemensamma uppgiften.

ETT ställe, med flit. Jämförelsen är bara meningsfull om varje kandidat får
exakt samma instruktion — skiljer sig prompten mäter vi promptarna, inte
modellerna.

Formuleringen speglar vad tavelgeneratorn faktiskt behöver, inte vad OCR
brukar leverera: Qwen3 som skriver tavlan ser inga bilder, så allt som ska
kunna hamna på tavlan måste finnas i den här texten.
"""

PROMPT = """\
Du läser av en sida ur en svensk gymnasielärobok i matematik. Sidan är fotad med \
mobilkamera och kan vara sned, skuggad eller ojämnt belyst.

Returnera exakt de här sex avsnitten, i den här ordningen:

## RUBRIKER
Avsnittsnummer och rubriker, ordagrant som de står på sidan.

## BRÖDTEXT
All löpande text, ordagrant. Behåll styckeindelningen. Översätt inte, sammanfatta \
inte, förkorta inte.

## MATEMATIK
Varje formel, ekvation och matematiskt uttryck på sidan, i LaTeX. Numrera dem i den \
ordning de förekommer, och skriv efter varje en kort rad om var på sidan den hör \
hemma (t.ex. "i exempel 3", "i regelrutan").

## FIGURER
För varje figur, graf, diagram eller geometrisk skiss: beskriv vad den visar så \
utförligt att någon som INTE ser bilden kan använda den i en genomgång. Vad står på \
axlarna? Vad är utmärkt, namngivet eller skuggat? Vilken poäng illustrerar figuren? \
Finns ingen figur, skriv "Inga figurer".

## EXEMPEL OCH UPPGIFTER
Numrering och innehåll för varje exempel och varje uppgift på sidan.

## OSÄKERT
Lista allt du inte kunde läsa säkert.

REGEL SOM GÄLLER FÖRE ALLA ANDRA: hitta inte på. Kan du inte läsa något — ett \
tecken, en siffra, ett index, en del av en figur — skriv [oläsligt] på den platsen \
och ta upp det under OSÄKERT. En utläsning med tydliga luckor är användbar. En \
utläsning som ser komplett ut men innehåller gissningar är värdelös, eftersom felet \
då upptäcks först framför klassen.
"""
