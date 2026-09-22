"""Bygger 2a.json ur handdömda fält + maskinella ordräkningar (stam_<termin>.json).
Handdömt: poang/formaga (ur anvisningen), kortsvar, flerval, meningar_fore_fragan, fragverb,
motivera, svarsform, konstanter, sanning, steg, kontext, representation, max_heltal, decimaler,
innehall, metodforeskrift, fortydligande, form_parafras, avgorande_steg.
Maskinellt: ord_stam (stam2a.py). max_heltal/decimaler maskinellt men handkorrigerat där
tabeller/bilder gjorde maskinen opålitlig."""
import json, os, statistics as st
from collections import Counter, defaultdict
OUT = os.path.dirname(os.path.abspath(__file__))

T, F = True, False
R = []
def r(termin, delprov, nr, del_, poang, formaga, kortsvar, flerval, fore, verb, motivera, svarsform,
      konst, sanning, steg, kontext, repr_, maxh, dec, innehall, metod, fortyd, parafras, avgorande):
    R.append({**dict(termin=termin, delprov=delprov, nr=nr, poang=poang, formaga=formaga,
                  kortsvar=kortsvar, flerval=flerval, meningar_fore_fragan=fore, fragverb=verb,
                  motivera=motivera, svarsform_instruktion=svarsform, konstanter=konst, sanning=sanning,
                  steg=steg, kontext=kontext, representation=repr_, max_heltal=maxh, decimaler=dec,
                  innehall=innehall, metodforeskrift=metod, fortydligande=fortyd,
                  form_parafras=parafras, avgorande_steg=avgorande), "del": del_})

TX, TF, TG, TFG, TFF, TFT, FO = ["text"], ["text","formel"], ["text","graf"], ["text","formel","graf"], ["text","figur"], ["text","formel","figur"], ["formel"]

# ---------------- vt17 ----------------
v="vt17"
r(v,"B",1,"a",[1,0,0],["B"],T,F,1,"bestäm",F,"",0,"ej",1,"ren",TG,None,0,"andragradsfunktioner",F,F,"läs av nollställen ur given parabelgraf, kortsvar","korrekt avläsning av båda nollställena")
r(v,"B",1,"b",[1,0,0],["B"],T,F,1,"bestäm",F,"",0,"ej",1,"ren",TG,None,0,"andragradsfunktioner",F,F,"läs av största värde ur parabelgraf, kortsvar","korrekt avläst maximum ur grafen")
r(v,"B",2,"a",[1,0,0],["P"],T,F,0,"lös",F,"exakt",0,"ej",1,"ren",TF,21,0,"potensekvationer",F,F,"potensekvation x^n = tal, exakt svar, kortsvar","korrekt exakt svar")
r(v,"B",2,"b",[1,0,0],["P"],T,F,0,"lös",F,"exakt",0,"ej",1,"ren",TF,10,0,"potensekvationer",F,F,"ekvation med rationell exponent, exakt svar, kortsvar","korrekt exakt svar")
r(v,"B",3,"a",[1,0,0],["P"],T,T,2,"vilken",F,"",0,"ej",1,"ren",TFG,3,0,"ekvationssystem",F,F,"para ihop ekvationssystem med rätt graf bland sex, kortsvar","rätt koordinatsystem valt")
r(v,"B",3,"b",[1,0,0],["B"],T,F,1,"markera",F,"",0,"ej",1,"ren",TFG,3,0,"ekvationssystem",F,F,"markera lösningen som skärningspunkt i valt koordinatsystem","godtagbar markering av skärningspunkten, även i fel valt system")
r(v,"B",4,"a",[0,1,0],["P"],T,F,0,"fyll",F,"",0,"ej",2,"ren",TF,49,0,"algebra",F,F,"fyll i saknade termer så att kvadreringsregeln stämmer, kortsvar","korrekt ifylld parentes")
r(v,"B",4,"b",[0,1,0],["P"],T,F,0,"fyll",F,"",0,"ej",1,"ren",TF,25,0,"algebra",F,F,"faktorisera differens av kvadrater baklänges, kortsvar","korrekt faktorisering")
r(v,"B",5,"",[0,1,0],["B"],T,F,1,"bestäm",F,"",0,"ej",1,"ren",TFG,1,0,"funktioner",T,F,"läs av x ur grafen givet funktionsvärdet, kortsvar","korrekt avläsning baklänges")
r(v,"B",6,"",[0,2,0],["B","B"],T,F,1,"skissa",F,"",0,"ej",2,"ren",TF,2,0,"andragradsfunktioner",F,F,"skissa parabel som uppfyller två symboliska villkor (ett med 'för alla x')","graf som uppfyller båda villkoren och har parabelform")
r(v,"B",7,"",[0,1,0],["M"],T,F,6,"ställ",F,"",0,"ej",2,"vardag",["text","figur","tabell"],138,0,"linjära funktioner",F,T,"ställ upp linjär funktion ur tabell med konstant differens, kortsvar","korrekt linjär funktion y = kx + m")
r(v,"B",8,"",[0,1,0],["PL"],T,F,0,"beräkna",F,"",0,"ej",2,"ren",TF,4444,0,"algebra",T,T,"differens av två stora kvadrater utan räknare, ledtråd om konjugatregeln, kortsvar","korrekt värde")
r(v,"B",9,"a",[0,0,1],["B"],T,F,1,"bestäm",F,"",0,"ej",2,"ren",TG,None,0,"andragradsfunktioner",F,F,"ange en andragradsfunktion vars graf inte skär given parabel, kortsvar","godtagbar funktion, t.ex. nedåtvänd parabel helt under den givna")
r(v,"B",9,"b",[0,0,1],["B"],T,F,1,"ange",F,"",0,"ej",1,"ren",TG,None,0,"andragradsfunktioner",F,F,"ange värdemängd för egen funktion från a), kortsvar","korrekt värdemängd som olikhet")
r(v,"C",10,"a",[1,0,0],["M"],F,T,3,"ange",T,"",0,"ej",2,"vardag",TG,700000,1,"exponentialfunktioner",F,F,"välj graf som visar konstant procentuell förändring, motivera","rätt graf med motivering som utesluter de andra graferna")
r(v,"C",10,"b",[1,0,0],["M"],T,F,3,"bestäm",F,"",0,"ej",2,"vardag",TG,700000,1,"exponentialfunktioner",T,T,"extrapolera värde två år framåt ur vald graf, kortsvar","godtagbart avläst värde")
r(v,"C",11,"a",[1,0,0],["R"],F,F,1,"förklara",F,"",0,"ej",1,"ren",TFT,5,0,"andragradsekvationer",F,F,"välj en av tre påbörjade lösningsmetoder och beskriv vad som gjorts","förklaring i egna ord som går utöver att läsa av symbolerna")
r(v,"C",11,"b",[1,0,0],["P"],F,F,1,"lös",F,"",0,"ej",2,"ren",TFT,5,0,"andragradsekvationer",T,F,"slutför lösning av andragradsekvation med vald algebraisk metod","korrekt slutförd lösning med båda rötterna")
r(v,"C",12,"",[1,0,0],["R"],F,F,3,"förklara",F,"",0,"given",1,"ren",TX,2,0,"logik",F,F,"förklara varför ekvivalens inte gäller mellan två geometriska utsagor","förklaring knuten till uppgiften, i praktiken ett motexempel")
r(v,"C",13,"",[1,2,0],["B","PL","PL"],F,F,2,"bestäm",F,"",3,"ej",4,"ren",TF,18,0,"andragradsfunktioner",F,F,"bestäm tre koefficienter i andragradsfunktion ur ett nollställe och maximipunkten","alla koefficienter via ekvation för nollstället; E-poängen bara för konstanttermen")
r(v,"C",14,"",[0,0,3],["R","R","K"],F,F,1,"undersök",F,"",3,"okand",4,"ren",TF,3,0,"algebra",F,F,"undersök om uttryck i tre på varandra följande heltal alltid är heltal","generellt resonemang i en variabel med korrekt slutsats, plus A-kommunikation; specialfall ger noll")
r(v,"C",15,"",[0,0,2],["P","P"],F,F,0,"lös",F,"",0,"ej",3,"ren",TF,15,0,"potenser",F,F,"exponentialekvation som kräver två potenslagar, utan räknare","korrekt lösning efter omskrivning med två potenslagar")
r(v,"D",16,"a",[2,0,0],["P","P"],F,F,1,"bestäm",F,"",0,"ej",2,"ren",TX,227,0,"linjära funktioner",F,F,"räta linjens ekvation genom två givna punkter","korrekt ekvation efter beräknad riktningskoefficient")
r(v,"D",16,"b",[1,0,0],["R"],F,F,1,"avgör",F,"",0,"okand",2,"ren",TX,1000,0,"linjära funktioner",F,F,"avgör om en tredje punkt ligger på linjen","enkelt resonemang med korrekt slutsats, följdfel från a) tillåts")
r(v,"D",17,"a",[1,0,0],["PL"],F,F,2,"bestäm",F,"",0,"ej",2,"ren",TFG,12,0,"geometri",F,F,"skärningspunkt mellan två räta linjer i figur","korrekta koordinater för skärningspunkten")
r(v,"D",17,"b",[2,0,0],["PL","PL"],F,F,2,"avgör",F,"",0,"okand",4,"ren",TFG,12,0,"geometri",F,F,"jämför areor av två trianglar bildade av linjerna och axlarna","x-koordinat för hörnet bestämd, areor beräknade och jämförda")
r(v,"D",18,"",[2,1,0],["PL","PL","K"],F,F,4,"bestäm",F,"",0,"ej",4,"vardag",TFF,10985,0,"ekvationssystem",F,F,"ställ upp och lös ekvationssystem ur två köp med rabatt","båda priserna korrekt; C-kommunikation kräver definierade variabler")
r(v,"D",19,"a",[2,0,0],["M","M"],F,F,7,"bestäm",F,"",0,"ej",2,"vardag",TFT,2522000,0,"exponentialfunktioner",F,T,"lös given exponentialekvation för förändringsfaktorn och tolka som procent","korrekt procentsats ur förändringsfaktorn")
r(v,"D",19,"b",[0,2,0],["P","P"],F,F,7,"bestäm",F,"",0,"ej",3,"vardag",TFT,2522000,0,"exponentialfunktioner",F,T,"ställ upp ny exponentialekvation för tiden och tolka som årtal","ekvation uppställd och löst med redovisad räknaranvändning")
r(v,"D",20,"a",[1,0,0],["M"],F,F,6,"förklara",F,"",0,"ej",1,"yrke",TFT,320,0,"andragradsfunktioner",F,F,"tolka variabeln i given intäktsfunktion","korrekt tolkning av x som prishöjning")
r(v,"D",20,"b",[0,3,0],["M","M","K"],F,F,9,"bestäm",F,"",0,"ej",4,"yrke",TFT,320,0,"andragradsfunktioner",F,T,"maximera vinst = intäkt minus kostnad, bestäm optimalt pris","vinstfunktion uppställd, maximum bestämt med motivering, pris tolkat; C-kommunikation")
r(v,"D",21,"",[0,2,0],["P","P"],F,F,0,"lös",F,"",0,"ej",3,"ren",TF,714,0,"andragradsekvationer",F,F,"andragradsekvation på faktorform som måste utvecklas före lösning","pq-formeln uppställd och båda rötterna")
r(v,"D",22,"",[0,2,0],["R","R"],F,T,2,"ange",T,"",2,"ej",4,"ren",TF,12,0,"linjära funktioner",F,F,"avgör vilka av sex informationsalternativ som räcker för att bestämma k och m","insikt att två punkter krävs och prövning av samtliga alternativ")
r(v,"D",23,"",[0,0,2],["PL","PL"],F,F,0,"beräkna",F,"exakt",0,"ej",3,"ren",FO,13,0,"algebra",F,F,"beräkna kvadratsumma exakt givet summan av tal och dess invers, via kvadrering","kvadrering av givet uttryck och förenklat exakt svar")
r(v,"D",24,"",[0,0,4],["M","M","M","K"],F,F,12,"beräkna",F,"",0,"ej",5,"vardag",["text","figur","tabell","formel"],402,2,"ekvationssystem",F,T,"ekvationssystem i två okända ur pristabell, leder till andragradsekvation, tolka mått","system uppställt, förenklat till produkt, löst, mått tolkade; A-kommunikation")

# ---------------- vt18 ----------------
v="vt18"
r(v,"B",1,"",[1,0,0],["P"],T,F,1,"ange",F,"",2,"ej",2,"ren",TG,None,0,"linjära funktioner",F,F,"läs av k och m ur ritad linje, kortsvar","korrekt ekvation ur avläsning")
r(v,"B",2,"a",[1,0,0],["B"],T,F,2,"fyll",F,"",0,"ej",1,"ren",TG,4,0,"andragradsfunktioner",F,F,"fyll i rätt term (nollställen) för markerade punkter, kortsvar","exakt rätt term")
r(v,"B",2,"b",[1,0,0],["B"],T,F,2,"fyll",F,"",0,"ej",1,"ren",TG,4,0,"andragradsfunktioner",F,F,"fyll i rätt term (symmetrilinje), kortsvar","exakt rätt term")
r(v,"B",2,"c",[1,0,0],["B"],T,F,2,"fyll",F,"",0,"ej",1,"ren",TG,4,0,"andragradsfunktioner",F,F,"fyll i rätt term (minimipunkt), kortsvar","rätt term, synonymer godtas")
r(v,"B",3,"a",[1,0,0],["P"],T,F,1,"lös",F,"",0,"ej",1,"ren",TFG,3,1,"exponentialfunktioner",T,F,"lös exponentialekvation grafiskt ur ritad kurva, kortsvar","avläsning inom tolerans")
r(v,"B",3,"b",[1,0,0],["PL"],T,F,1,"lös",F,"",0,"ej",2,"ren",TFG,3,0,"exponentialfunktioner",T,F,"skriv om ekvation och lös grafiskt, kortsvar","avläsning inom tolerans efter omskrivning")
r(v,"B",4,"a",[1,0,0],["P"],T,F,0,"lös",F,"exakt",0,"ej",1,"ren",TF,17,0,"potensekvationer",F,F,"potensekvation x^n = tal, exakt svar, kortsvar","korrekt exakt svar")
r(v,"B",4,"b",[0,1,0],["P"],T,F,0,"lös",F,"exakt",0,"ej",3,"ren",TF,5,0,"algebra",F,F,"ekvation med konjugat- och kvadreringsuttryck som förenklas till linjär, kortsvar","korrekt lösning")
r(v,"B",4,"c",[0,0,1],["P"],T,F,0,"lös",F,"exakt",0,"ej",3,"ren",TF,9,0,"algebra",F,F,"ekvation med produkter av binom som förenklas till x² = tal, kortsvar","båda rötterna med plus-minus")
r(v,"B",5,"a",[0,1,0],["B"],T,T,2,"vilken",F,"",0,"ej",2,"ren",TG,3,0,"funktioner",F,F,"välj två av sex grafer som uppfyller definitions- och värdemängd givna i ord, kortsvar","båda rätt grafer")
r(v,"B",5,"b",[0,1,0],["K"],T,F,1,"ange",F,"",0,"ej",1,"ren",TG,3,0,"funktioner",F,F,"översätt villkor i ord till olikheter med symboler, kortsvar","korrekt symbolisk skrivning av båda villkoren")
r(v,"B",6,"",[0,1,0],["B"],T,T,1,"vilken",F,"",0,"ej",2,"ren",TF,2,0,"andragradsfunktioner",F,F,"välj de funktionsuttryck av fem som har givna nollställen, kortsvar","exakt rätt delmängd av alternativen")
r(v,"B",7,"",[0,0,1],["P"],T,F,0,"beräkna",F,"",0,"ej",3,"ren",FO,9,0,"potenser",F,F,"beräkna uttryck med rationella exponenter utan räknare, kortsvar","korrekt värde")
r(v,"B",8,"",[0,0,1],["M"],T,F,3,"teckna",F,"",0,"ej",3,"vardag",TFF,32997,0,"exponentialfunktioner",F,T,"teckna exponentialfunktion med byte av tidsenhet månad till år, kortsvar","korrekt funktion med exponent 12t och funktionsnamn")
r(v,"B",9,"",[0,0,1],["B"],T,F,1,"lös",F,"",0,"ej",3,"ren",TFG,6,0,"funktioner",T,F,"lös ekvation med sammansatt funktionsargument grafiskt, kortsvar","avläsning inom tolerans efter omskrivning av ekvationen")
r(v,"B",10,"",[0,0,1],["B"],T,F,1,"bestäm",F,"",2,"ej",3,"ren",TF,9,0,"ekvationssystem",F,F,"villkor på två parametrar för oändligt många lösningar, kortsvar","korrekt samband mellan parametrarna")
r(v,"C",11,"",[2,0,0],["P","P"],F,F,0,"lös",F,"",0,"ej",2,"ren",FO,16,0,"andragradsekvationer",T,F,"lös andragradsekvation med algebraisk metod","korrekt insättning i pq-formeln eller kvadratkomplettering, båda rötterna")
r(v,"C",12,"a",[1,0,0],["M"],F,F,5,"tolka",F,"",0,"ej",1,"vardag",TFF,85,1,"ekvationssystem",F,F,"tolka variabeln i givet ekvationssystem","tolkning som anger vilken vara och att det är kilopris")
r(v,"C",12,"b",[2,0,0],["M","M"],F,F,5,"bestäm",F,"",0,"ej",3,"vardag",TFF,85,1,"ekvationssystem",F,F,"lös givet ekvationssystem och svara med verklighetskoppling","båda priserna med koppling till varorna; rent talpar ger inte sista poängen")
r(v,"C",13,"",[0,2,0],["PL","PL"],F,F,1,"bestäm",F,"",0,"ej",2,"ren",TX,9,0,"linjära funktioner",F,F,"linjär funktion ur riktningskoefficient och ett funktionsvärde","m bestämt ur insättning, redovisat")
r(v,"C",14,"",[0,2,0],["P","R"],F,F,0,"vilken",T,"",0,"ej",3,"ren",FO,4,0,"algebra",F,F,"minsta värde av uttryck som förenklas till x² plus konstant, motivera","resonemang varför x² ≥ 0 ger minsta värdet")
r(v,"C",15,"",[0,3,0],["PL","PL","K"],F,F,1,"bestäm",F,"",1,"ej",4,"ren",TF,6,0,"linjära funktioner",F,F,"linje genom punkter med parameter, parallell med given linje","parallellitet använd för att bestämma parametern, sedan m; C-kommunikation")
r(v,"C",16,"",[0,0,3],["PL","PL","K"],F,F,0,"bestäm",F,"",1,"ej",4,"ren",FO,3,0,"andragradsekvationer",F,F,"för vilka parametervärden har andragradsekvation dubbelrot","diskriminant lika med noll uppställd och löst som andragradsekvation i parametern; A-kommunikation")
r(v,"D",17,"a",[1,0,0],["M"],F,T,4,"vilken",T,"",0,"ej",2,"vardag",TFG,2013,3,"exponentialfunktioner",F,F,"välj graf som matchar given exponentialfunktion, motivera","rätt graf med motivering via startvärde eller funktionsvärde")
r(v,"D",17,"b",[1,0,0],["M"],T,F,4,"vilken",F,"",0,"ej",2,"vardag",TFG,2013,3,"exponentialfunktioner",F,F,"läs av när funktionen når givet värde, årtal, kortsvar","korrekt årtal ur avläsning, följdfel tillåts")
r(v,"D",18,"",[1,0,0],["R"],F,F,2,"stämmer",T,"",0,"okand",2,"ren",TX,45,0,"logik",F,F,"pröva påstådd ekvivalens mellan två geometriska utsagor","resonemang som visar att ekvivalens inte gäller, korrekt slutsats med fel motivering ger noll")
r(v,"D",19,"",[2,0,0],["PL","PL"],F,F,3,"bestäm",F,"",2,"ej",3,"ren",TFG,3,0,"linjära funktioner",F,F,"ekvation för linje efter parallellförflyttning i x- och y-led","ny punkt bestämd, m redovisat")
r(v,"D",20,"",[2,0,0],["PL","PL"],F,F,1,"bestäm",F,"",0,"ej",3,"ren",TX,80,0,"andragradsekvationer",F,F,"rektangelsidor ur area, andragradsekvation","ekvation uppställd och positiv rot vald")
r(v,"D",21,"a",[1,0,0],["P"],F,F,1,"beräkna",F,"",0,"ej",2,"ren",TX,16,0,"geometri",F,F,"avstånd mellan två punkter","korrekt avstånd, enhet krävs inte")
r(v,"D",21,"b",[1,0,0],["R"],F,F,4,"avgör",T,"",0,"okand",2,"ren",TG,16,0,"geometri",F,F,"avgör punktens läge relativt cirkel via jämförelse med radien","jämförelse med radien måste ingå i motiveringen")
r(v,"D",22,"a",[1,0,0],["R"],F,T,2,"vilken",T,"",0,"ej",2,"ren",TFF,5,0,"andragradsfunktioner",F,F,"välj lokal grafbild vid en punkt ur symmetrilinje och teckenvillkor, motivera","rätt figur med motivering om nedåtvänd parabel vänster om symmetrilinjen")
r(v,"D",22,"b",[0,1,0],["R"],F,F,1,"går",T,"",0,"okand",2,"ren",TFF,5,0,"andragradsfunktioner",F,F,"avgör om antal nollställen kan bestämmas ur given information","välgrundat resonemang om att extrempunktens y-värde saknas")
r(v,"D",23,"",[0,2,0],["P","P"],F,F,0,"bestäm",F,"",0,"ej",3,"ren",FO,4,0,"andragradsekvationer",F,F,"skärningspunkter mellan parabel och rät linje","andragradsekvation uppställd och löst med redovisad räknarmetod, zoomning duger inte")
r(v,"D",24,"",[0,4,0],["M","M","M","K"],F,F,3,"beräkna",F,"",0,"ej",4,"vardag",TFF,86,0,"ekvationssystem",F,F,"ekvationssystem ur två menypriser med volymer i figur, pris på ny meny","system, lösning, ny kombination beräknad; C-kommunikation")
r(v,"D",25,"",[0,2,0],["P","P"],F,F,0,"lös",F,"decimaler",0,"ej",3,"ren",FO,3,1,"exponentialfunktioner",F,F,"exponentialekvation med potenstermer på båda sidor, två decimaler","förenkling till en potensterm och redovisad lösning")
r(v,"D",26,"",[0,0,3],["M","M","K"],F,F,5,"bestäm",F,"",0,"ej",4,"yrke",TFF,None,1,"andragradsfunktioner",F,T,"andragradsfunktion för symmetrisk kant med given bredd och höjd, eget koordinatsystem","koordinatsystem definierat, tre punkter eller symmetri, funktion; A-kommunikation")
r(v,"D",27,"",[0,0,2],["R","R"],F,F,1,"bestäm",T,"",1,"ej",3,"ren",TF,10,1,"exponentialfunktioner",F,F,"villkor på konstant så att exponentialfunktion aldrig når given linje, motivera","resonemang om att potensen alltid är positiv och olikhet för konstanten med slutsats")

# ---------------- vt22 ----------------
v="vt22"
r(v,"B",1,"a",[1,0,0],["B"],T,F,1,"vilken",F,"",0,"ej",1,"ren",TF,6,0,"linjära funktioner",F,F,"y-skärning ur given linjeekvation, kortsvar","korrekt värde")
r(v,"B",1,"b",[1,0,0],["PL"],T,F,1,"vilken",F,"",0,"ej",1,"ren",TF,6,0,"linjära funktioner",F,F,"x-skärning ur given linjeekvation, kortsvar","korrekt värde")
r(v,"B",1,"c",[1,0,0],["B"],T,F,1,"ge",F,"",0,"ej",1,"ren",TF,6,0,"linjära funktioner",F,F,"ge exempel på parallell linje, kortsvar","linje med samma riktningskoefficient")
r(v,"B",2,"a",[1,0,0],["B"],T,F,2,"bestäm",F,"",3,"ej",1,"ren",TF,4,0,"andragradsfunktioner",F,F,"konstantterm ur y-skärningspunkt, kortsvar","korrekt c")
r(v,"B",2,"b",[1,0,0],["B"],T,F,2,"bestäm",F,"",3,"ej",1,"ren",TF,4,0,"andragradsfunktioner",F,F,"symmetrilinje ur två nollställen, kortsvar","korrekt x-koordinat")
r(v,"B",3,"a",[1,0,0],["P"],T,F,0,"förenkla",F,"",0,"ej",2,"ren",FO,10,0,"algebra",F,F,"förenkla kvadreringsuttryck minus term, kortsvar","korrekt förenklat")
r(v,"B",3,"b",[1,0,0],["P"],T,F,0,"förenkla",F,"",0,"ej",2,"ren",FO,9,0,"algebra",F,F,"förenkla konjugatprodukt plus konstant, kortsvar","korrekt förenklat")
r(v,"B",3,"c",[1,0,0],["P"],T,F,0,"förenkla",F,"",0,"ej",1,"ren",FO,5,0,"potenser",F,F,"förenkla potensprodukt, kortsvar","korrekt förenklat")
r(v,"B",4,"a",[1,0,0],["B"],T,F,1,"vilken",F,"",0,"ej",1,"ren",TG,None,0,"statistik",F,F,"läs av medelvärde ur normalfördelningskurva, kortsvar","korrekt avläsning")
r(v,"B",4,"b",[0,1,0],["B"],T,T,1,"vilken",F,"",0,"ej",1,"ren",TG,None,0,"statistik",F,F,"välj kurvan med minst standardavvikelse av fem, kortsvar","rätt kurva")
r(v,"B",5,"a",[1,0,0],["PL"],T,F,1,"ge",F,"",0,"ej",2,"ren",TX,5,0,"geometri",F,F,"ge exempel på punkt på givet avstånd från en punkt, kortsvar","godtagbar punkt")
r(v,"B",5,"b",[0,1,0],["PL"],T,F,1,"bestäm",F,"",0,"ej",2,"ren",TF,4,0,"geometri",F,F,"bestäm ändpunkt ur mittpunkt och andra ändpunkten, bråkkoordinater, kortsvar","korrekta koordinater, oförkortat godtas")
r(v,"B",6,"a",[1,0,0],["P"],T,F,0,"lös",F,"exakt",0,"ej",1,"ren",TF,21,0,"potensekvationer",F,F,"potensekvation x^n = tal, exakt svar, kortsvar","korrekt exakt svar")
r(v,"B",6,"b",[0,1,0],["P"],T,F,0,"lös",F,"exakt",0,"ej",2,"ren",TF,5,0,"potensekvationer",F,F,"potensekvation som kräver potenslag före lösning, exakt, kortsvar","korrekt exakt svar")
r(v,"B",6,"c",[0,1,0],["P"],T,F,0,"lös",F,"exakt",0,"ej",2,"ren",TF,6,0,"potensekvationer",F,F,"ekvation med rationell exponent på ett binom, exakt, kortsvar","korrekt svar")
r(v,"B",6,"d",[0,0,1],["P"],T,F,0,"lös",F,"exakt",0,"ej",3,"ren",TF,5987,0,"andragradsekvationer",F,F,"andragradsekvation i ett sammansatt uttryck med stort tal, faktorisering, kortsvar","båda rötterna")
r(v,"B",7,"",[0,1,0],["M"],T,F,3,"teckna",F,"",0,"ej",2,"vardag",TFF,120,0,"andragradsfunktioner",F,F,"teckna rektangelarea med given omkrets som funktion av en sida, kortsvar","korrekt funktionsuttryck")
r(v,"B",8,"",[0,1,0],["B"],T,F,1,"ge",F,"",0,"ej",2,"ren",TF,3,0,"andragradsfunktioner",F,F,"ge exempel på andragradsfunktion med given symmetrilinje, kortsvar","funktion med rätt symmetrilinje")
r(v,"B",9,"",[0,0,1],["B"],T,F,1,"ange",F,"",0,"ej",2,"ren",TX,7,0,"andragradsfunktioner",F,F,"nollställe för parabel med dubbelrot ur två punkter med samma y, kortsvar","korrekt nollställe via symmetri")
r(v,"B",10,"",[0,0,1],["B"],T,F,1,"lös",F,"",0,"ej",3,"ren",TFG,3,1,"funktioner",T,F,"lös ekvation med sammansatt argument och kvot grafiskt, kortsvar","avläsning inom tolerans efter omskrivning")
r(v,"B",11,"",[0,0,1],["PL"],T,T,8,"vilken",F,"",0,"okand",4,"vardag",TG,35,0,"statistik",F,T,"avgör vilka av fyra påståenden om ett sammanslaget lådagram som säkert följer, kortsvar","exakt rätt delmängd av påståendena")
r(v,"C",12,"",[2,0,0],["P","P"],F,F,0,"lös",F,"",0,"ej",2,"ren",FO,12,0,"andragradsekvationer",T,F,"lös andragradsekvation med algebraisk metod","korrekt insättning och båda rötterna; teckenfel vid insättning ger noll")
r(v,"C",13,"a",[1,0,0],["R"],F,F,3,"har",T,"",0,"okand",2,"ren",TFT,2,1,"ekvationssystem",F,F,"granska en påbörjad omskrivning av ekvationssystem, är den korrekt, motivera","felet pekat ut och slutsats angiven")
r(v,"C",13,"b",[1,0,0],["R"],F,F,2,"har",T,"",0,"okand",2,"ren",TFT,2,1,"ekvationssystem",F,F,"pröva om föreslaget talpar löser systemet, motivera","prövning i ekvationen med slutsats; rätt slutsats ur fel lösning ger noll")
r(v,"C",14,"",[0,2,0],["P","P"],F,F,0,"lös",F,"",0,"ej",3,"ren",FO,6,1,"ekvationssystem",T,F,"lös ekvationssystem med decimalkoefficienter algebraiskt","ekvation i en variabel och båda värdena")
r(v,"C",15,"",[0,2,0],["R","R"],F,F,2,"visa",F,"",0,"given",3,"ren",TX,1,0,"algebra",F,F,"visa allmänt påstående om kvadrater av två tal med differens 1","generell uppställning i en variabel och slutfört resonemang; exempel räknas inte")
r(v,"C",16,"",[0,3,0],["PL","PL","K"],F,F,3,"bestäm",F,"",0,"ej",4,"ren",TFG,36,1,"geometri",F,F,"hörn på linje så att triangel med bas på x-axeln får given area","bas eller höjd uttryckt, ekvation löst, koordinater; C-kommunikation")
r(v,"C",17,"",[0,0,2],["P","P"],F,F,1,"bestäm",F,"exakt",0,"ej",4,"ren",TG,None,0,"exponentialfunktioner",F,T,"exponentialfunktion ur två grafpunkter, exakt förenklat startvärde","eget system i startvärde och bas, eliminering, förenklat exakt svar")
r(v,"D",18,"",[1,0,0],["P"],F,F,1,"bestäm",F,"decimaler",2,"ej",1,"ren",TF,157,0,"linjära funktioner",F,F,"riktningskoefficient ur två punkter, decimalsvar","korrekt k")
r(v,"D",19,"",[1,0,0],["P"],T,F,0,"lös",F,"decimaler",0,"ej",1,"ren",FO,7,1,"exponentialfunktioner",F,F,"exponentialekvation med räknare, kortsvar","korrekt värde")
r(v,"D",20,"",[1,0,0],["PL"],T,F,1,"ge",F,"",0,"ej",1,"ren",TF,7,0,"andragradsfunktioner",F,F,"ge exempel på punkt på given parabel, kortsvar","godtagbar punkt")
r(v,"D",21,"",[2,0,0],["M","M"],T,F,4,"bestäm",F,"",0,"ej",2,"vardag",TFT,None,2,"andragradsfunktioner",F,F,"bredd och höjd av byggnad ur andragradsmodell (nollställen och maximum), kortsvar","båda måtten")
r(v,"D",22,"",[2,0,0],["M","M"],F,F,5,"beräkna",F,"heltal",1,"ej",2,"naturvetenskap",TFT,2019,4,"potensekvationer",F,T,"lös potensekvation med decimalexponent ur given formel, avrunda till heltal","rätt ekvation identifierad och löst")
r(v,"D",23,"",[0,3,0],["M","M","K"],F,F,4,"bestäm",F,"",0,"ej",4,"vardag",TFF,5000,0,"exponentialfunktioner",F,T,"förändringsfaktor ur två värden, sedan år då givet värde nås","faktor-ekvation, tillräckligt många värdesiffror, årtal; C-kommunikation")
r(v,"D",24,"a",[1,0,0],["M"],F,F,6,"tolka",F,"",0,"ej",1,"vardag",TFT,81,0,"ekvationssystem",F,F,"tolka variabeln i påbörjat ekvationssystem","korrekt tolkning som tid")
r(v,"D",24,"b",[0,0,2],["M","M"],F,F,7,"beräkna",F,"",0,"ej",4,"vardag",TFT,81,0,"ekvationssystem",F,F,"fullborda ekvationssystemet, lös, skala upp till hela sträckan","system fullbordat, tid bestämd, total sträcka")
r(v,"D",25,"",[0,2,0],["B","R"],F,F,1,"undersök",F,"",0,"ej",3,"vardag",TX,210,0,"statistik",F,F,"bestäm högsta värde ur medelvärde, median och variationsbredd för fyra tal","alla tre villkor använda och entydigt svar motiverat")
r(v,"D",26,"",[0,2,0],["P","P"],F,F,1,"lös",F,"decimaler",0,"ej",3,"ren",FO,6,0,"andragradsekvationer",F,F,"lös f(x+3) = tal för given andragradsfunktion, decimaler","korrekt tolkning av det sammansatta argumentet och båda rötterna")
r(v,"D",27,"",[0,0,2],["R","R"],F,F,2,"utred",F,"",0,"ej",3,"ren",TX,11,0,"linjära funktioner",F,F,"utred möjliga riktningskoefficienter ur olikhetsvillkor på tre punkter","resonemang som täcker både negativa värden och noll")
r(v,"D",28,"",[0,0,2],["PL","PL"],F,F,2,"bestäm",F,"",1,"ej",3,"ren",TF,2,0,"funktioner",F,F,"avstånd mellan två punkter på parabel uttryckt i parameter","y-koordinater i parametern, avståndsformel, förenklat uttryck")

# ---- ord_stam ur maskinfil, niva, steg_per_poang ----
stam = {t: json.load(open(os.path.join(OUT, f"stam_{t}.json"), encoding="utf-8")) for t in ("vt17","vt18","vt22")}
for u in R:
    key = f"{u['nr']}{u['del']}"
    u["ord_stam"] = stam[u["termin"]][key]["ord"]
    p = u["poang"]
    u["niva"] = "A" if p[2] else ("C" if p[1] else "E")
    u["steg_per_poang"] = round(u["steg"] / sum(p), 2)
    assert len(u["formaga"]) == sum(p), key

ORDER = ["termin","delprov","nr","del","poang","niva","formaga","kortsvar","flerval","ord_stam",
         "meningar_fore_fragan","fragverb","motivera","svarsform_instruktion","konstanter","sanning",
         "steg","steg_per_poang","kontext","representation","max_heltal","decimaler","innehall",
         "metodforeskrift","fortydligande","form_parafras","avgorande_steg"]
upp = [{k: u[k] for k in ORDER} for u in R]

# ---- prov-tabellen ----
def summa(t, d):
    s = [0,0,0]
    for u in R:
        if u["termin"] == t and u["delprov"] == d:
            s = [a+b for a, b in zip(s, u["poang"])]
    return s
prov = []
for t, spann, tot_hafte in (("vt17", {"B":"1–9","C":"10–15","D":"16–24"}, [23,19,13]),
                            ("vt18", {"B":"1–10","C":"11–16","D":"17–27"}, [22,20,13]),
                            ("vt22", {"B":"1–11","C":"12–17","D":"18–28"}, [23,20,12])):
    dp = []
    for d in "BCD":
        dp.append({"namn": d, "uppgifter": spann[d], "poang": summa(t, d),
                   "tid_min": 120 if d == "D" else None, "tid_kommentar": None if d == "D" else "120 min för B och C tillsammans",
                   "hjalpmedel_raknare": d == "D"})
    tot = [sum(x[i] for x in (summa(t,"B"),summa(t,"C"),summa(t,"D"))) for i in range(3)]
    prov.append({"termin": t, "delprov": dp, "total": tot, "total_enligt_hafte": tot_hafte, "avstamning_ok": tot == tot_hafte})

json.dump({"kurs": "2a", "prov": prov, "uppgifter": upp}, open(os.path.join(OUT, "2a.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("rader:", len(upp))
for p in prov:
    print(p["termin"], [(d["namn"], d["poang"]) for d in p["delprov"]], p["total"], p["avstamning_ok"])

# ---- statistik för tvärsnittet ----
def q(xs, p):
    xs = sorted(xs)
    if not xs: return None
    k = (len(xs)-1) * p
    f = int(k); c = min(f+1, len(xs)-1)
    return round(xs[f] + (xs[c]-xs[f])*(k-f), 1)
def blk(rows, name):
    print(f"\n{name} n={len(rows)}")
    for fld in ("ord_stam","meningar_fore_fragan","konstanter","steg","steg_per_poang"):
        xs = [u[fld] for u in rows if u[fld] is not None]
        print(f"  {fld:22} median={st.median(xs):5} p90={q(xs,0.9):5} min={min(xs)} max={max(xs)}")
for niva in "ECA":
    for ks in (True, False):
        blk([u for u in R if u["niva"]==niva and u["kortsvar"]==ks], f"niva={niva} kortsvar={ks}")
    blk([u for u in R if u["niva"]==niva], f"niva={niva} ALLA")
print("\nfragverb per niva")
for niva in "ECA":
    print(niva, Counter(u["fragverb"] for u in R if u["niva"]==niva).most_common())
print("\nmotivera per termin/niva")
for t in ("vt17","vt18","vt22"):
    rows=[u for u in R if u["termin"]==t]
    print(t, "motivera:", sum(u["motivera"] for u in rows), "/", len(rows), Counter(u["niva"] for u in rows if u["motivera"]))
print("\nfortydligande per niva")
for niva in "ECA":
    rows=[u for u in R if u["niva"]==niva]; print(niva, sum(u["fortydligande"] for u in rows), "/", len(rows))
print("\nmetodforeskrift:", [(u["termin"],u["nr"],u["del"],u["niva"]) for u in R if u["metodforeskrift"]])
print("sanning:", Counter((u["niva"],u["sanning"]) for u in R))
print("svarsform:", Counter((u["niva"],u["svarsform_instruktion"]) for u in R if u["svarsform_instruktion"]))
print("flerval:", Counter(u["niva"] for u in R if u["flerval"]))
print("konstanter>0:", [(u["termin"],u["nr"],u["del"],u["niva"],u["konstanter"]) for u in R if u["konstanter"]])
print("kontext:", Counter((u["niva"],u["kontext"]) for u in R))
print("formaga per niva:")
for niva in "ECA":
    c=Counter();
    for u in R:
        if u["niva"]==niva:
            for f in u["formaga"]: c[f]+=1
    print(" ", niva, c.most_common())
print("innehall per niva:")
for niva in "ECA":
    print(" ", niva, Counter(u["innehall"] for u in R if u["niva"]==niva).most_common())
print("\ntal utan raknare (B+C):")
for niva in "ECA":
    xs=[u["max_heltal"] for u in R if u["delprov"] in "BC" and u["niva"]==niva and u["max_heltal"] is not None]
    ds=[u["decimaler"] for u in R if u["delprov"] in "BC" and u["niva"]==niva]
    print(" ", niva, "max_heltal:", sorted(xs), "decimaler:", Counter(ds))
print("tal med raknare (D):")
for niva in "ECA":
    xs=[u["max_heltal"] for u in R if u["delprov"]=="D" and u["niva"]==niva and u["max_heltal"] is not None]
    ds=[u["decimaler"] for u in R if u["delprov"]=="D" and u["niva"]==niva]
    print(" ", niva, "max_heltal:", sorted(xs), "decimaler:", Counter(ds))
print("\nper delprov: andel E/C/A och enheter per 10 min")
for t in ("vt17","vt18","vt22"):
    nBC = len([u for u in R if u["termin"]==t and u["delprov"] in "BC"])
    for d in "BCD":
        rows=[u for u in R if u["termin"]==t and u["delprov"]==d]
        s=summa(t,d); tot=sum(s)
        print(f"  {t} {d}: enheter={len(rows)} poäng={s} andel={[round(x/tot,2) for x in s]}", end="")
        if d=="D": print(f" per10min={round(len(rows)/12,2)} poäng/10min={round(tot/12,2)}")
        else: print(f" (B+C tillsammans {nBC} enheter, {round(nBC/12,2)} per 10 min)")
print("\nrepresentation per niva:")
for niva in "ECA":
    c=Counter()
    for u in R:
        if u["niva"]==niva:
            for x in u["representation"]: c[x]+=1
    print(" ", niva, c.most_common())
print("\nkortsvar per niva:", Counter((u["niva"],u["kortsvar"]) for u in R))
print("K-poang per niva:", Counter(u["niva"] for u in R if "K" in u["formaga"]))
