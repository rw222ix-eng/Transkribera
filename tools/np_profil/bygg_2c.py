# -*- coding: utf-8 -*-
"""Bygger 2c.json ur NP-korpusen. Ordräkning/tal maskinellt ur radintervall i
källfilen; övriga fält dömda för hand (dicten MAN nedan). Ingen provtext
hamnar i utdata."""
import json, re, statistics, collections, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROT = r"C:\Users\bolun\Downloads\Skola & kursmaterial\Nationella prov matte (bilder)\np-korpus\2c"
UT = r"C:\Users\bolun\AppData\Local\Temp\claude\E--Transkribera\1594fbe6-ff9e-479f-b5c8-92d48d37c2a1\scratchpad\np"
FIL = {"vt18": ROT + r"\vt18\Ma2c-vt18.txt", "vt22": ROT + r"\vt22\Ma2c-vt22.txt"}
RAD = {t: open(f, encoding="utf-8").read().split("\n") for t, f in FIL.items()}

def text(termin, spann):
    ut = []
    for a, b in spann:
        ut += RAD[termin][a - 1:b]
    t = " ".join(ut)
    t = re.sub(r"_{3,}", " ", t)
    t = re.sub(r"\(\d/\d/\d\)", " ", t)
    return t

ORD = re.compile(r"[A-Za-zÅÄÖåäöé]{2,}|\b[iå]\b")
def ord_stam(t):
    return len(ORD.findall(t))

def tal(t):
    t2 = re.sub(r"(\d) (\d{3})\b", r"\1\2", t)
    dec = re.findall(r"\d+,\d+", t2)
    heltal = [int(x) for x in re.findall(r"(?<![\d,])\d+(?![\d,])", t2)]
    heltal = [h for h in heltal if h > 1]   # exponent-/index-fragment (1,2) ur formler bort
    return (max(heltal) if heltal else None, max((len(d.split(",")[1]) for d in dec), default=0))

# ---- radintervall per bedömd enhet (häftet) ----
SP = {
 ("vt18",1,""): [(64,75)],
 ("vt18",2,"a"): [(81,92),(94,100)], ("vt18",2,"b"): [(81,92),(103,106)], ("vt18",2,"c"): [(81,92),(109,114)],
 ("vt18",3,"a"): [(126,132)], ("vt18",3,"b"): [(136,142)],
 ("vt18",4,"a"): [(150,150),(152,156)], ("vt18",4,"b"): [(150,150),(159,173)],
 ("vt18",4,"c"): [(150,150),(176,182)], ("vt18",4,"d"): [(150,150),(185,201)],
 ("vt18",5,""): [(207,216)], ("vt18",6,""): [(228,233)], ("vt18",7,""): [(239,260)],
 ("vt18",8,""): [(266,276)], ("vt18",9,""): [(284,305)], ("vt18",10,""): [(317,327)],
 ("vt18",11,"a"): [(333,366),(368,369)], ("vt18",11,"b"): [(333,366),(372,374)],
 ("vt18",12,""): [(380,396)], ("vt18",13,""): [(408,420)], ("vt18",14,""): [(426,446)],
 ("vt18",15,""): [(452,462)], ("vt18",16,""): [(468,485)], ("vt18",17,""): [(553,565)],
 ("vt18",18,""): [(571,576)], ("vt18",19,""): [(586,605)], ("vt18",20,""): [(612,613)],
 ("vt18",21,"a"): [(623,637),(640,645)], ("vt18",21,"b"): [(623,637),(650,652)],
 ("vt18",22,""): [(662,674)], ("vt18",23,""): [(680,694)],
 ("vt18",24,"a"): [(703,751),(756,759)], ("vt18",24,"b"): [(703,751),(762,766)],
 ("vt18",25,""): [(775,790)], ("vt18",26,""): [(796,802)],
 ("vt22",1,"a"): [(64,64),(67,74)], ("vt22",1,"b"): [(64,64),(79,87)],
 ("vt22",2,"a"): [(94,100),(105,117)], ("vt22",2,"b"): [(94,100),(123,124)],
 ("vt22",3,""): [(130,143)], ("vt22",4,"a"): [(154,160)], ("vt22",4,"b"): [(164,170)],
 ("vt22",5,"a"): [(179,184)], ("vt22",5,"b"): [(190,206)],
 ("vt22",6,"a"): [(215,215),(218,220)], ("vt22",6,"b"): [(215,215),(225,232)],
 ("vt22",6,"c"): [(215,215),(237,243)], ("vt22",6,"d"): [(215,215),(248,258)],
 ("vt22",6,"e"): [(215,215),(263,274)],
 ("vt22",7,""): [(281,287)], ("vt22",8,"a"): [(293,296),(300,300)],
 ("vt22",8,"b"): [(293,296),(303,315)],
 ("vt22",9,""): [(329,339)], ("vt22",10,"a"): [(345,360),(363,371)], ("vt22",10,"b"): [(345,360),(375,403)],
 ("vt22",11,""): [(409,415)], ("vt22",12,""): [(424,440)], ("vt22",13,""): [(446,451)],
 ("vt22",14,""): [(457,462)], ("vt22",15,""): [(468,474)], ("vt22",16,""): [(540,546)],
 ("vt22",17,""): [(552,560)], ("vt22",18,""): [(566,583)], ("vt22",19,""): [(589,617)],
 ("vt22",20,""): [(629,636)], ("vt22",21,""): [(642,666)], ("vt22",22,""): [(675,686)],
 ("vt22",23,""): [(692,704)], ("vt22",24,"a"): [(713,734),(737,737)], ("vt22",24,"b"): [(713,734),(740,743)],
 ("vt22",25,""): [(749,756)], ("vt22",26,""): [(765,787)], ("vt22",27,""): [(793,807)],
 ("vt22",28,""): [(813,827)],
}

def delprov(termin, nr):
    if termin == "vt18":
        return "B" if nr <= 9 else ("C" if nr <= 16 else "D")
    return "B" if nr <= 8 else ("C" if nr <= 15 else "D")

# ---- handdömda fält ----
# nyckel -> (poang, formaga, kortsvar, flerval, men_fore, fragverb, motivera, svarsform,
#            konstanter, sanning, steg, kontext, representation, innehall, metodforeskrift,
#            fortydligande, form_parafras, avgorande_steg, delad, poang_2a, delad_typ, anm)
MAN = {
("vt18",1,""): ([1,0,0],["P"],True,False,1,"ange",False,"given form",0,"ej",2,"ren",["text","graf"],"linjära funktioner",False,False,
  "läs av k och m ur ritad linje, kortsvar","korrekt avläsning av lutning och skärning",True,[1,0,0],"identisk",""),
("vt18",2,"a"): ([1,0,0],["B"],True,False,1,"fylla i",False,"",0,"ej",1,"ren",["text","graf","formel"],"andragradsfunktioner",False,False,
  "namnge begreppet för två x-värden ur graf, luckmening","rätt term för punkterna där grafen skär x-axeln",True,[1,0,0],"identisk",""),
("vt18",2,"b"): ([1,0,0],["B"],True,False,1,"fylla i",False,"",0,"ej",1,"ren",["text","graf","formel"],"andragradsfunktioner",False,False,
  "namnge begreppet för en lodrät linje ur graf, luckmening","rätt term för den lodräta linjen genom vertex",True,[1,0,0],"identisk",""),
("vt18",2,"c"): ([1,0,0],["B"],True,False,1,"fylla i",False,"",0,"ej",1,"ren",["text","graf","formel"],"andragradsfunktioner",False,False,
  "namnge begreppet för en punkt ur graf, luckmening","rätt term för lägsta punkten, flera synonymer godtas",True,[1,0,0],"identisk",""),
("vt18",3,"a"): ([1,0,0],["B"],True,False,1,"vilken",False,"",0,"ej",1,"ren",["text","graf"],"statistik/normalfördelning",False,False,
  "läs av lägesmått ur normalfördelningskurva, kortsvar","korrekt avläsning av kurvans symmetrilinje",False,None,"",""),
("vt18",3,"b"): ([0,1,0],["B"],True,True,1,"vilken",False,"",0,"ej",1,"ren",["text","graf"],"statistik/normalfördelning",False,False,
  "välj bland fem kurvor den med störst spridning","koppla spridningsmått till kurvans bredd",False,None,"",""),
("vt18",4,"a"): ([1,0,0],["P"],True,False,0,"lös",False,"exakt",0,"ej",2,"ren",["text","formel"],"exponentialekvationer/logaritmer",False,False,
  "lös enkel exponentialekvation, svara exakt med logaritmer","exakt logaritmkvot som svar",True,[1,0,0],"variant","2a har samma form med andra tal"),
("vt18",4,"b"): ([0,1,0],["P"],True,False,0,"lös",False,"exakt",0,"ej",3,"ren",["text","formel"],"algebra/andragradsekvationer",False,False,
  "ekvation med gemensam faktor i båda led, lös exakt","korrekt rot utan att tappa eller dubblera lösning",True,[0,1,0],"identisk",""),
("vt18",4,"c"): ([0,1,0],["B"],True,False,0,"lös",False,"exakt",0,"ej",2,"ren",["text","formel"],"komplexa tal",False,False,
  "andragradsekvation utan reella rötter, komplext svar","båda imaginära rötterna",False,None,"","ekvationens exakta lydelse osäker i textlagret"),
("vt18",4,"d"): ([0,0,1],["P"],True,False,0,"lös",False,"exakt",0,"ej",3,"ren",["text","formel"],"algebra/andragradsekvationer",False,False,
  "ekvation med kvadrat och parentes som förenklas till ren kvadrat","båda rötterna efter fullständig förenkling",True,[0,0,1],"identisk",""),
("vt18",5,""): ([0,1,0],["B"],True,False,0,"ge",False,"",0,"ej",2,"ren",["text","formel"],"logaritmer",False,False,
  "ge eget exempel på två tal som uppfyller logaritmsamband, öppet svar","talpar med rätt differens",False,None,"",""),
("vt18",6,""): ([0,1,0],["B"],True,False,0,"ange",False,"",0,"ej",2,"ren",["text","formel"],"logaritmer",False,False,
  "översätt dubbelolikhet i logaritm till intervall för x","korrekt intervall, ordform godtas",False,None,"",""),
("vt18",7,""): ([0,0,1],["P"],True,False,0,"lös",False,"",0,"ej",3,"ren",["text","formel"],"exponentialekvationer/potenser",False,False,
  "exponentialekvation med samma potens i flera termer, bryt ut","korrekt exponent efter utbrytning",False,None,"","koefficienterna osäkra i textlagret"),
("vt18",8,""): ([0,0,1],["M"],True,False,3,"teckna",False,"",0,"ej",3,"vardag",["text"],"exponentialfunktioner",False,True,
  "teckna exponentialfunktion med byte av tidsenhet, kortsvar","exponenten omräknad till ny tidsenhet, funktionsnamn krävs",True,[0,0,1],"identisk",""),
("vt18",9,""): ([0,0,1],["B"],True,False,1,"bestäm",False,"",2,"ej",3,"ren",["text","formel"],"ekvationssystem",False,False,
  "samband mellan två parametrar för oändligt många lösningar, kortsvar","villkoret att ekvationerna är proportionella",True,[0,0,1],"identisk",""),
("vt18",10,""): ([2,0,0],["P","P"],False,False,0,"lös",False,"",0,"ej",3,"ren",["formel"],"andragradsekvationer",True,False,
  "andragradsekvation i normalform, algebraisk metod föreskriven","teckenrätt insättning i pq-formel eller kvadratkomplettering",True,[2,0,0],"identisk",""),
("vt18",11,"a"): ([1,0,0],["M"],False,False,6,"tolka",False,"",0,"ej",1,"vardag",["text","formel"],"ekvationssystem",False,False,
  "tolka en variabel i givet ekvationssystem ur vardagstext","variabeln kopplad till rätt storhet och rätt vara",True,[1,0,0],"variant","2c har tre variabler, 2a två; poäng lika"),
("vt18",11,"b"): ([2,0,0],["M","M"],False,False,6,"bestäm",False,"",0,"ej",4,"vardag",["text","formel"],"ekvationssystem",False,False,
  "lös givet tre-variabelsystem och svara med enheter","svaret återkopplat till verkligheten, inte bara x y z",True,[2,0,0],"variant","2c tre variabler"),
("vt18",12,""): ([0,2,0],["PL","PL"],False,False,1,"bestäm",False,"",0,"ej",3,"ren",["text","formel"],"linjära funktioner",False,False,
  "bestäm linjär funktion ur lutning och ett funktionsvärde","m ur insättning av villkoret",True,[0,2,0],"identisk",""),
("vt18",13,""): ([0,2,0],["P","R"],False,False,0,"vilken",True,"",0,"ej",3,"ren",["text","formel"],"algebra/andragradsuttryck",False,False,
  "minsta värde av andragradsuttryck efter förenkling, motivera","välgrundat resonemang varför kvadrattermen ger minimum",True,[0,2,0],"identisk","2c-lydelsen lägger till att x är reellt"),
("vt18",14,""): ([0,3,0],["PL","PL","K"],False,False,1,"bestäm",False,"",1,"ej",5,"ren",["text","formel"],"linjära funktioner",False,False,
  "linje genom två punkter med parameter, parallell med given linje","parametern bestämd via lika lutning, sedan m; K-poäng",True,[0,3,0],"identisk",""),
("vt18",15,""): ([0,0,3],["PL","PL","K"],False,False,0,"bestäm",False,"",1,"ej",5,"ren",["text","formel"],"andragradsekvationer/diskriminant",False,False,
  "parametervillkor för att andragradsekvation saknar reella rötter","andragradsolikhet i parametern löst till intervall; K-poäng",True,[0,0,3],"variant","2a frågar efter dubbelrot (likhet), 2c efter intervall (olikhet); poäng lika"),
("vt18",16,""): ([0,0,3],["B","R","R"],False,False,1,"utred",False,"",0,"okand",6,"ren",["text","formel"],"logaritmer/funktioner",True,False,
  "undersök antal skärningar mellan logaritmpotens och rot via funktionsvärden","definitionsmängd utesluts, två skärningar visas var för sig",False,None,"",""),
("vt18",17,""): ([2,0,0],["P","P"],False,False,3,"beräkna",False,"",0,"ej",2,"vardag",["text","figur"],"geometri/likformighet",False,True,
  "höjd via likformiga trianglar ur uppmätta sträckor i figur","korrekt likformighetssamband",False,None,"",""),
("vt18",18,""): ([2,0,0],["PL","PL"],False,False,1,"bestäm",False,"",0,"ej",3,"vardag",["text"],"statistik/normalfördelning",False,False,
  "antal över gräns i normalfördelning ur medelvärde och standardavvikelse","inse att gränsen är två standardavvikelser från medelvärdet",False,None,"",""),
("vt18",19,""): ([2,0,0],["PL","PL"],False,False,3,"bestäm",False,"given form",0,"ej",3,"ren",["text","graf","formel"],"linjära funktioner",False,False,
  "linje förskjuts i x- och y-led, ny ekvation","en punkt flyttad korrekt, sedan m",True,[2,0,0],"identisk",""),
("vt18",20,""): ([2,0,0],["R","R"],False,False,1,"är",True,"",0,"okand",3,"ren",["text"],"geometri/koordinater",False,False,
  "avgör om triangel ur tre koordinater är rätvinklig, motivera","Pythagoras måste gälla, prövas med sidlängder",False,None,"",""),
("vt18",21,"a"): ([1,0,0],["R"],False,True,2,"vilken",True,"",0,"ej",2,"ren",["text","figur","formel"],"andragradsfunktioner",False,False,
  "välj figur som visar kurvans lokala utseende ur symmetri och tecken, motivera","enkelt resonemang: nedåt öppen och läge relativt symmetrilinjen",True,[1,0,0],"identisk",""),
("vt18",21,"b"): ([0,1,0],["R"],False,False,1,"avgöra",True,"",0,"okand",2,"ren",["text","formel"],"andragradsfunktioner",False,False,
  "avgör om antal nollställen kan bestämmas ur given information","insikt att vertexets y-värde saknas",True,[0,1,0],"identisk",""),
("vt18",22,""): ([0,2,0],["P","P"],False,False,0,"bestäm",False,"",0,"ej",3,"ren",["formel"],"andragradsekvationer/funktioner",False,False,
  "skärning mellan parabel och rät linje, x-koordinater","ekvationen löst med tillräcklig noggrannhet (ej zoom)",True,[0,2,0],"identisk",""),
("vt18",23,""): ([0,3,0],["M","M","K"],False,False,4,"bestäm",False,"",0,"ej",4,"naturvetenskap",["text"],"exponentialfunktioner",False,False,
  "år tills utsläpp nått målnivå vid konstant procentuell minskning","ekvation med målvärde och förändringsfaktor; K-poäng",False,None,"",""),
("vt18",24,"a"): ([0,2,0],["M","M"],False,False,4,"bestäm",False,"",0,"ej",3,"samhalle",["text","tabell","graf"],"regression",False,False,
  "linjärt samband ur tabell, regression eller anpassad linje","lutning i godtagbart intervall och redovisad räknarfunktion",False,None,"",""),
("vt18",24,"b"): ([0,0,1],["M"],False,False,1,"ha",True,"",0,"okand",2,"samhalle",["text"],"regression",False,True,
  "bedöm modellens begränsning, motivera","nyanserat omdöme om var modellen slutar gälla",False,None,"",""),
("vt18",25,""): ([0,0,3],["M","M","K"],False,False,4,"bestäm",False,"",0,"ej",4,"yrke",["text","figur"],"andragradsfunktioner",False,False,
  "andragradsfunktion till symmetrisk form med given bredd och höjd","eget koordinatsystem, tre punkter eller symmetri; K-poäng",True,[0,0,3],"identisk",""),
("vt18",26,""): ([0,0,3],["PL","PL","K"],False,False,2,"bestäm",False,"",0,"ej",5,"ren",["text","figur"],"andragradsfunktioner/geometri",False,False,
  "största rektangel inskriven i triangel, likformighet plus maximering","samband bas–höjd via likformighet, sedan maximum; K-poäng",False,None,"",""),
("vt22",1,"a"): ([1,0,0],["P"],True,False,0,"förenkla",False,"",0,"ej",2,"ren",["formel"],"algebra",False,False,
  "förenkla kvadrat på parentes minus term","korrekt kvadreringsregel",True,[1,0,0],"identisk",""),
("vt22",1,"b"): ([1,0,0],["P"],True,False,0,"förenkla",False,"",0,"ej",2,"ren",["formel"],"algebra",False,False,
  "förenkla konjugatprodukt plus konstant","korrekt konjugatregel",True,[1,0,0],"identisk",""),
("vt22",2,"a"): ([1,0,0],["B"],True,False,2,"bestäm",False,"",2,"ej",1,"ren",["text","formel"],"andragradsfunktioner",False,False,
  "konstantterm ur given punkt på y-axeln","c som y-värdet vid x=0",True,[1,0,0],"identisk",""),
("vt22",2,"b"): ([1,0,0],["B"],True,False,2,"bestäm",False,"",0,"ej",1,"ren",["text","formel"],"andragradsfunktioner",False,False,
  "x-koordinat för vertex ur två nollställen","symmetri mitt emellan nollställena",True,[1,0,0],"identisk",""),
("vt22",3,""): ([1,0,0],["B"],True,True,3,"vilken",False,"",0,"ej",1,"vardag",["text"],"logik/implikation",False,True,
  "välj implikationspil mellan två vardagspåståenden","rätt riktning på implikationen",False,None,"",""),
("vt22",4,"a"): ([1,0,0],["B"],True,False,1,"vilken",False,"",0,"ej",1,"ren",["text","graf"],"statistik/normalfördelning",False,False,
  "läs av lägesmått ur normalfördelningskurva, kortsvar","korrekt avläsning av kurvans symmetrilinje",True,[1,0,0],"identisk","samma uppgift som vt18 3a"),
("vt22",4,"b"): ([0,1,0],["B"],True,True,1,"vilken",False,"",0,"ej",1,"ren",["text","graf"],"statistik/normalfördelning",False,False,
  "välj bland fem kurvor den med minst spridning","koppla spridningsmått till kurvans bredd",True,[0,1,0],"identisk","spegling av vt18 3b"),
("vt22",5,"a"): ([1,0,0],["PL"],True,False,1,"ge",False,"",0,"ej",1,"ren",["text"],"koordinatgeometri",False,False,
  "ge exempel på punkt på givet avstånd från given punkt, öppet svar","valfri punkt som uppfyller avståndet",True,[1,0,0],"identisk",""),
("vt22",5,"b"): ([0,1,0],["PL"],True,False,1,"bestäm",False,"",0,"ej",2,"ren",["text"],"koordinatgeometri",False,False,
  "andra ändpunkten ur mittpunkt och ena ändpunkten, bråkkoordinater","mittpunktsformeln baklänges i båda leden",True,[0,1,0],"identisk",""),
("vt22",6,"a"): ([1,0,0],["P"],True,False,0,"lös",False,"exakt",0,"ej",2,"ren",["formel"],"exponentialekvationer/logaritmer",False,False,
  "lös enkel exponentialekvation, exakt logaritmsvar","exakt logaritmkvot",True,[1,0,0],"variant","2a samma form, andra tal"),
("vt22",6,"b"): ([0,1,0],["P"],True,False,0,"lös",False,"exakt",0,"ej",2,"ren",["formel"],"potenser/rotekvationer",False,False,
  "potens- eller rotekvation, exakt svar på enklaste form","exakt rotuttryck",False,None,"","ekvationens lydelse osäker i textlagret"),
("vt22",6,"c"): ([0,1,0],["P"],True,False,0,"lös",False,"exakt",0,"ej",3,"ren",["formel"],"logaritmer",False,False,
  "tiopotensekvation där högerledet förenklas med logaritmlag","logaritmlagen ger ett heltal i högerledet",False,None,"",""),
("vt22",6,"d"): ([0,1,0],["P"],True,False,0,"lös",False,"exakt",0,"ej",3,"ren",["formel"],"algebra/andragradsekvationer",False,False,
  "produkt av två parenteser lika med kvadratterm, kvadrattermer tar ut varandra","inse att ekvationen blir linjär",False,None,"",""),
("vt22",6,"e"): ([0,0,1],["P"],True,False,0,"lös",False,"exakt",0,"ej",3,"ren",["formel"],"algebra/andragradsekvationer",False,False,
  "faktorisera med gemensam parentes i stället för att multiplicera ut","båda rötterna via nollproduktmetoden",True,[0,0,1],"identisk",""),
("vt22",7,""): ([0,1,0],["M"],True,False,3,"teckna",False,"",0,"ej",2,"vardag",["text","figur"],"andragradsfunktioner/modellering",False,False,
  "teckna area som funktion av en sida vid given omkrets, kortsvar","andra sidan uttryckt i x innan produkten",True,[0,1,0],"identisk",""),
("vt22",8,"a"): ([0,1,0],["B"],True,False,1,"ge",False,"",0,"ej",1,"ren",["text","formel"],"andragradsfunktioner",False,False,
  "ge exempel på andragradsfunktion med given symmetrilinje, öppet svar","valfri funktion med rätt symmetrilinje",True,[0,1,0],"identisk",""),
("vt22",8,"b"): ([0,0,1],["B"],True,False,3,"ge",False,"",0,"ej",2,"ren",["text","formel"],"andragradsfunktioner/parabler",False,True,
  "ge exempel på parabel med x som funktion av y, öppet svar","överföra begreppet symmetrilinje till liggande parabel",False,None,"",""),
("vt22",9,""): ([2,0,0],["P","P"],False,False,0,"lös",False,"",0,"ej",3,"ren",["formel"],"andragradsekvationer",True,False,
  "andragradsekvation i normalform, algebraisk metod föreskriven","teckenrätt insättning i pq-formel",True,[2,0,0],"identisk",""),
("vt22",10,"a"): ([1,0,0],["R"],False,False,3,"ha",True,"",0,"okand",2,"ren",["text","formel"],"ekvationssystem",False,True,
  "granska annans omskrivning av ekvationssystem, motivera","slutsats att felet finns plus var",True,[1,0,0],"identisk",""),
("vt22",10,"b"): ([1,0,0],["R"],False,False,2,"ha",True,"",0,"okand",2,"ren",["text","formel"],"ekvationssystem",False,False,
  "pröva påstådd lösning till ekvationssystem, motivera","insättning i båda ekvationerna, inte bara en",True,[1,0,0],"identisk",""),
("vt22",11,""): ([0,2,0],["PL","PL"],False,False,3,"bestäm",False,"",0,"ej",4,"ren",["text","figur"],"geometri/vinklar",False,False,
  "vinkel i triangel ur två bisektriser och deras vinkel","halvvinklarna lika och vinkelsumma i deltriangeln, inte specialfall",False,None,"",""),
("vt22",12,""): ([0,2,0],["P","P"],False,False,0,"lös",False,"",0,"ej",3,"ren",["formel"],"ekvationssystem",True,False,
  "linjärt ekvationssystem med decimalkoefficienter, algebraisk metod","korrekt ekvation i en variabel",True,[0,2,0],"identisk",""),
("vt22",13,""): ([0,2,0],["R","R"],False,False,2,"visa",False,"",0,"given",3,"ren",["text"],"algebra/bevis",False,False,
  "visa allmänt talsamband om kvadrater med differens ett","generell uppställning i variabel, inte exempel",True,[0,2,0],"identisk",""),
("vt22",14,""): ([0,0,2],["P","P"],False,False,1,"bestäm",False,"exakt, förenklat",0,"ej",4,"ren",["text","graf"],"exponentialfunktioner",False,False,
  "startvärde för exponentialfunktion ur två punkter i graf, exakt","ekvationssystem i två okända och eliminering, förenklat svar",True,[0,0,2],"identisk",""),
("vt22",15,""): ([0,0,3],["M","M","K"],False,False,3,"bestäm",False,"",0,"ej",5,"vardag",["text"],"andragradsekvationer/modellering",True,False,
  "pris per meter i två butiker ger andragradsekvation, prövning förbjuden","egen ekvation i en variabel; K-poäng",False,None,"","metodföreskriften är negativ: prövning godtas inte"),
("vt22",16,""): ([1,0,0],["B"],True,False,2,"bestäm",False,"",0,"ej",2,"ren",["text","figur"],"geometri/cirkel",False,False,
  "vinkel i cirkel med medelpunkt, kortsvar","randvinkel- eller likbent-samband ur figuren",False,None,"",""),
("vt22",17,""): ([1,0,0],["P"],True,False,0,"lös",False,"decimaler",0,"ej",1,"ren",["formel"],"ekvationer numeriskt",False,False,
  "lös ekvation numeriskt med digitalt verktyg, decimalsvar","räknarens lösning avrundad rätt",True,[1,0,0],"variant","2a samma form, andra tal; ekvationens lydelse osäker"),
("vt22",18,""): ([1,0,0],["PL"],True,False,1,"ge",False,"",0,"ej",1,"ren",["text","formel"],"andragradsfunktioner",False,False,
  "ge exempel på punkt på given andragradskurva, öppet svar","valfritt x insatt korrekt",True,[1,0,0],"identisk",""),
("vt22",19,""): ([1,0,0],["P"],True,False,2,"bestäm",False,"decimaler",0,"ej",1,"ren",["text","tabell","formel"],"regression",True,False,
  "linjär regression ur värdetabell med räknare, kortsvar","räknarens a och b med rätt antal decimaler",False,None,"",""),
("vt22",20,""): ([2,0,0],["PL","PL"],False,False,3,"hur",False,"",0,"ej",3,"ren",["text","figur"],"geometri/likformighet",False,False,
  "areaförhållande mellan likformiga trianglar med längdskala två","areaskalan är längdskalan i kvadrat, språklig miss godtas",False,None,"",""),
("vt22",21,""): ([2,0,0],["M","M"],True,False,4,"bestäm",False,"",0,"ej",3,"vardag",["text","formel","figur"],"andragradsfunktioner",False,False,
  "bredd och höjd på byggnad ur given parabelfunktion, kortsvar","nollställen ger bredd, vertex ger höjd",True,[2,0,0],"identisk",""),
("vt22",22,""): ([0,3,0],["M","M","K"],False,False,4,"bestäm",False,"",0,"ej",5,"naturvetenskap",["text"],"exponentialfunktioner",False,True,
  "år då population når nivå, förändringsfaktor ur två observationer","förändringsfaktor med tillräckligt många värdesiffror; K-poäng",True,[0,3,0],"identisk",""),
("vt22",23,""): ([0,2,0],["R","R"],False,False,2,"visa",False,"",3,"given",3,"ren",["text","figur"],"geometri/cirkel",False,False,
  "visa allmänt vinkelsamband i fyrhörning med cirkelns medelpunkt","generellt resonemang med randvinkelsats eller likbenta trianglar, motiverat",False,None,"",""),
("vt22",24,"a"): ([1,0,0],["M"],False,False,6,"tolka",False,"",0,"ej",1,"vardag",["text","formel","figur"],"ekvationssystem",False,True,
  "tolka variabeln i påbörjat ekvationssystem ur vardagstext","variabeln som tiden",True,[1,0,0],"identisk",""),
("vt22",24,"b"): ([0,0,2],["M","M"],False,False,7,"beräkna",False,"",0,"ej",4,"vardag",["text","formel","figur"],"ekvationssystem",False,True,
  "komplettera ekvationssystemet, lös och skala upp till hela sträckan","egen andra ekvation, sedan tredubbling",True,[0,0,2],"identisk",""),
("vt22",25,""): ([0,2,0],["B","R"],False,False,1,"undersök",False,"",0,"ej",4,"vardag",["text"],"statistik/lägesmått",False,False,
  "största värde i fyra tal ur medelvärde, median och variationsbredd","alla tre villkoren använda och entydigheten visad",True,[0,2,0],"identisk",""),
("vt22",26,""): ([0,0,3],["R","R","K"],False,False,1,"undersök",False,"",3,"okand",4,"ren",["text","formel"],"algebra/talteori",False,False,
  "undersök om uttryck i tre följande heltal alltid är heltal","generell ansats i en variabel, inte specialfall; K-poäng",False,None,"",""),
("vt22",27,""): ([0,0,2],["PL","PL"],False,False,2,"bestäm",False,"",1,"ej",4,"ren",["text","formel"],"funktioner/koordinatgeometri",False,False,
  "sträcka mellan två punkter på parametriserad parabel, svar i parametern","y-värden i parametern, sedan avståndsformeln",True,[0,0,2],"identisk",""),
("vt22",28,""): ([0,0,3],["PL","PL","K"],False,False,2,"bestäm",False,"",1,"ej",4,"ren",["text","figur"],"geometri/likformighet",False,False,
  "kvot mellan sträckor i rektangel via likformiga trianglar, parametrisk","likformighet motiverad, inte specialfall a=1; K-poäng",False,None,"",""),
}

# manuella överstyrningar av maskinräknade tal där formelfragment stör
TAL_OVR = {("vt18",4,"b"):(5,0), ("vt18",4,"c"):(5,0), ("vt18",4,"d"):(9,0), ("vt18",5,""):(8,0),
           ("vt18",6,""):(3,0), ("vt18",7,""):(None,0), ("vt18",9,""):(9,0), ("vt18",10,""):(16,0),
           ("vt18",12,""):(9,0), ("vt18",13,""):(4,0), ("vt18",14,""):(6,0), ("vt18",15,""):(3,0),
           ("vt18",16,""):(100,0), ("vt18",19,""):(3,0), ("vt18",22,""):(4,0), ("vt18",1,""):(None,0),
           ("vt22",1,"a"):(10,0), ("vt22",1,"b"):(9,0), ("vt22",2,"a"):(4,0), ("vt22",2,"b"):(4,0),
           ("vt22",5,"b"):(4,0), ("vt22",6,"a"):(7,0), ("vt22",6,"b"):(None,0), ("vt22",6,"c"):(200,0),
           ("vt22",6,"d"):(9,0), ("vt22",6,"e"):(5987,0), ("vt22",9,""):(12,0), ("vt22",10,"a"):(5,1),
           ("vt22",10,"b"):(5,1), ("vt22",12,""):(6,1), ("vt22",14,""):(None,0), ("vt22",17,""):(5,2),
           ("vt22",18,""):(7,0), ("vt22",21,""):(None,2), ("vt22",26,""):(3,0), ("vt22",27,""):(2,0),
           ("vt22",28,""):(3,0), ("vt18",8,""):(32997,0), ("vt18",25,""):(None,1), ("vt18",26,""):(None,1),
           ("vt18",20,""):(10,0), ("vt18",23,""):(2020,2), ("vt18",24,"a"):(1903,1), ("vt18",24,"b"):(1903,1),
           ("vt22",20,""):(None,1), ("vt18",11,"a"):(105,1), ("vt18",11,"b"):(105,1)}

rader = []
for nyckel, sp in SP.items():
    termin, nr, del_ = nyckel
    m = MAN[nyckel]
    (poang, formaga, kortsvar, flerval, men, verb, motiv, svarsform, konst, sanning, steg, kontext,
     repr_, innehall, metod, fort, parafras, avg, delad, p2a, dtyp, anm) = m
    t = text(termin, sp)
    mh, dec = tal(t)
    if nyckel in TAL_OVR:
        mh, dec = TAL_OVR[nyckel]
    s = sum(poang)
    niva = "A" if poang[2] else ("C" if poang[1] else "E")
    rader.append(collections.OrderedDict([
        ("termin", termin), ("delprov", delprov(termin, nr)), ("nr", nr), ("del", del_),
        ("poang", poang), ("niva", niva), ("formaga", formaga), ("kortsvar", kortsvar), ("flerval", flerval),
        ("ord_stam", ord_stam(t)), ("meningar_fore_fragan", men), ("fragverb", verb), ("motivera", motiv),
        ("svarsform_instruktion", svarsform), ("konstanter", konst), ("sanning", sanning),
        ("steg", steg), ("steg_per_poang", round(steg / s, 2)), ("kontext", kontext),
        ("representation", repr_), ("max_heltal", mh), ("decimaler", dec), ("innehall", innehall),
        ("metodforeskrift", metod), ("fortydligande", fort), ("form_parafras", parafras),
        ("avgorande_steg", avg), ("delad_med_2a", delad), ("poang_2a", p2a), ("delad_typ", dtyp),
        ("anm", anm),
    ]))

prov = [
 {"termin": "vt18", "delprov": [
   {"namn": "B", "uppgifter": "1–9", "poang": [6,5,4], "tid_min": 120, "tid_delad_med": "C", "hjalpmedel_raknare": False},
   {"namn": "C", "uppgifter": "10–16", "poang": [5,7,6], "tid_min": 120, "tid_delad_med": "B", "hjalpmedel_raknare": False},
   {"namn": "D", "uppgifter": "17–26", "poang": [9,8,7], "tid_min": 120, "hjalpmedel_raknare": True}],
  "total": [20,20,17], "total_haftet": [20,20,17], "granser": {"E":13,"D":22,"C":29,"B":37,"A":44},
  "delad_med_2a_rader": None},
 {"termin": "vt22", "delprov": [
   {"namn": "B", "uppgifter": "1–8", "poang": [8,7,2], "tid_min": 120, "tid_delad_med": "C", "hjalpmedel_raknare": False},
   {"namn": "C", "uppgifter": "9–15", "poang": [4,6,5], "tid_min": 120, "tid_delad_med": "B", "hjalpmedel_raknare": False},
   {"namn": "D", "uppgifter": "16–28", "poang": [9,7,10], "tid_min": 120, "hjalpmedel_raknare": True}],
  "total": [21,20,17], "total_haftet": [21,20,17], "granser": {"E":14,"D":22,"C":29,"B":38,"A":45},
  "delad_med_2a_rader": None},
]
# avstämning
for p in prov:
    summa = [0,0,0]
    for r in rader:
        if r["termin"] == p["termin"]:
            for i in range(3): summa[i] += r["poang"][i]
    p["total_ur_rader"] = summa
    p["avstamning_ok"] = summa == p["total_haftet"]
    p["delad_med_2a_rader"] = sum(1 for r in rader if r["termin"] == p["termin"] and r["delad_med_2a"])
    for d in p["delprov"]:
        s = [0,0,0]
        for r in rader:
            if r["termin"] == p["termin"] and r["delprov"] == d["namn"]:
                for i in range(3): s[i] += r["poang"][i]
        assert s == d["poang"], (p["termin"], d["namn"], s, d["poang"])

ut = {"kurs": "2c", "kallor": ["np-korpus/2c/vt18/Ma2c-vt18.txt", "np-korpus/2c/vt22/Ma2c-vt22.txt"],
      "metod": {"maskinellt": ["ord_stam", "max_heltal", "decimaler", "steg_per_poang", "niva"],
                "for_hand": ["poang", "formaga", "kortsvar", "flerval", "meningar_fore_fragan", "fragverb", "motivera",
                             "svarsform_instruktion", "konstanter", "sanning", "steg", "kontext", "representation",
                             "innehall", "metodforeskrift", "fortydligande", "form_parafras", "avgorande_steg",
                             "delad_med_2a", "poang_2a", "delad_typ"],
                "ord_stam_def": "tokens med minst två bokstäver (plus i/å) i häftets textlager för enheten inkl. gemensam ingress; formelfragment och tal räknas inte",
                "max_heltal_def": "största heltal >1 i stammen, tusentalsmellanslag ihopslaget; null om inget heltal; handjusterat där formelfragment störde",
                "steg_def": "räknesteg i anvisningens modellösning; för kortsvar egen uppskattning",
                "kontext_extra": "samhalle används utöver briefens fyra för historisk/samhällelig data"},
      "prov": prov, "uppgifter": rader}
with open(UT + r"\2c.json", "w", encoding="utf-8") as f:
    json.dump(ut, f, ensure_ascii=False, indent=1)

# ---- statistik för tvärsnittet ----
def p90(xs):
    xs = sorted(xs); k = 0.9 * (len(xs) - 1); lo = int(k); hi = min(lo + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 1)
def med(xs): return statistics.median(xs)

print("RADER", len(rader))
for p in prov: print(p["termin"], "ur rader", p["total_ur_rader"], "häftet", p["total_haftet"], "delade", p["delad_med_2a_rader"])
print("\nPER (niva, kortsvar): n | median/p90 ord | men | konst | steg | steg/p")
for niva in "ECA":
    for ks in (True, False):
        g = [r for r in rader if r["niva"] == niva and r["kortsvar"] == ks]
        if not g: continue
        def mp(f): v=[r[f] for r in g]; return f"{med(v)}/{p90(v)}"
        print(niva, "kortsvar" if ks else "lösning", len(g), "|", mp("ord_stam"), "|", mp("meningar_fore_fragan"), "|", mp("konstanter"), "|", mp("steg"), "|", mp("steg_per_poang"))
print("\nFRÅGEVERB per nivå")
for niva in "ECA":
    c = collections.Counter(r["fragverb"] for r in rader if r["niva"] == niva)
    print(niva, dict(c.most_common()))
print("\nMOTIVERA per prov/nivå")
for t in ("vt18","vt22"):
    c = collections.Counter(r["niva"] for r in rader if r["termin"] == t and r["motivera"])
    n = sum(1 for r in rader if r["termin"] == t)
    print(t, dict(c), "av", n, "rader; uppgiftsnummer:", sorted({(r["nr"]) for r in rader if r["termin"]==t and r["motivera"]}))
print("\nFÖRTYDLIGANDE per nivå")
for niva in "ECA":
    g = [r for r in rader if r["niva"] == niva]
    print(niva, sum(r["fortydligande"] for r in g), "/", len(g))
print("\nMETODFÖRESKRIFT:", [(r["termin"], r["nr"], r["del"], r["niva"]) for r in rader if r["metodforeskrift"]])
print("SANNING:", collections.Counter((r["sanning"], r["niva"]) for r in rader))
print("KONSTANTER>0:", [(r["termin"], r["nr"], r["del"], r["niva"], r["konstanter"]) for r in rader if r["konstanter"]])
print("FLERVAL:", [(r["termin"], r["nr"], r["del"], r["niva"]) for r in rader if r["flerval"]])
print("\nKONTEXT per nivå")
for niva in "ECA":
    print(niva, dict(collections.Counter(r["kontext"] for r in rader if r["niva"] == niva)))
print("\nFÖRMÅGA per nivå (poängvis)")
for niva in "ECA":
    c = collections.Counter()
    for r in rader:
        if r["niva"] == niva:
            for f in r["formaga"]: c[f] += 1
    print(niva, dict(c.most_common()))
print("\nDELPROV: rader, poäng, andel, per 10 min")
for t in ("vt18","vt22"):
    for d in "BCD":
        g = [r for r in rader if r["termin"] == t and r["delprov"] == d]
        s = [sum(r["poang"][i] for r in g) for i in range(3)]
        nr = len({r["nr"] for r in g})
        print(t, d, "rader", len(g), "uppg", nr, "poäng", s, "andel", [round(x/sum(s),2) for x in s])
print("\nTAL utan räknare (B+C):", sorted({r["max_heltal"] for r in rader if r["delprov"] in "BC" and r["max_heltal"]}),
      "dec", collections.Counter(r["decimaler"] for r in rader if r["delprov"] in "BC"))
print("TAL med räknare (D):", sorted({r["max_heltal"] for r in rader if r["delprov"] == "D" and r["max_heltal"]}),
      "dec", collections.Counter(r["decimaler"] for r in rader if r["delprov"] == "D"))
print("\nDELAD: ", collections.Counter((r["delad_typ"] or "ej") for r in rader))
print("Poängskillnad delade:", [(r["termin"], r["nr"], r["del"]) for r in rader if r["delad_med_2a"] and r["poang"] != r["poang_2a"]])
print("BARA 2c per nivå:", dict(collections.Counter(r["niva"] for r in rader if not r["delad_med_2a"])))
print("BARA 2c innehåll:", collections.Counter(r["innehall"] for r in rader if not r["delad_med_2a"]))
print("DELADE innehåll:", collections.Counter(r["innehall"] for r in rader if r["delad_med_2a"]))
print("\nORD per rad:", [(r["termin"], r["nr"], r["del"], r["ord_stam"]) for r in rader])
for f in ("steg","meningar_fore_fragan","ord_stam"):
    print(f, "bara2c med/p90", med([r[f] for r in rader if not r["delad_med_2a"]]), p90([r[f] for r in rader if not r["delad_med_2a"]]),
          "| delade", med([r[f] for r in rader if r["delad_med_2a"]]), p90([r[f] for r in rader if r["delad_med_2a"]]))
