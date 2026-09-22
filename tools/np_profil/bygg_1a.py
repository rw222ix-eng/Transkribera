# -*- coding: utf-8 -*-
"""Bygger 1a.json ur np-korpus/1a. Maskinellt: ord_stam, max_heltal, decimaler,
steg_per_poang, statistik. För hand (i tabellen nedan): steg, formaga, sanning,
fragverb, meningar_fore_fragan, kontext, representation, innehall m.m.
Ingen provtext skrivs till utdata; skriptet läser radintervall ur korpusen."""
import glob, json, os, re, statistics as st
from collections import Counter, defaultdict

ROOT = r"C:\Users\bolun\Downloads\Skola & kursmaterial\Nationella prov matte (bilder)\np-korpus\1a"
OUT = os.path.dirname(os.path.abspath(__file__))

FILES = {
    ("vt17", "B"): glob.glob(os.path.join(ROOT, "vt17", "*Delprov B.txt"))[0],
    ("vt17", "C"): glob.glob(os.path.join(ROOT, "vt17", "*Delprov C.txt"))[0],
    ("vt17", "D"): glob.glob(os.path.join(ROOT, "vt17", "*Delprov D.txt"))[0],
    ("vt22", "B"): glob.glob(os.path.join(ROOT, "vt22", "*Delprov B_230907.txt"))[0],
    ("vt22", "C"): glob.glob(os.path.join(ROOT, "vt22", "*Delprov C.txt"))[0],
    ("vt22", "D"): glob.glob(os.path.join(ROOT, "vt22", "*Delprov D.txt"))[0],
}
LINES = {k: open(v, encoding="utf-8").read().split("\n") for k, v in FILES.items()}

POANG_RE = re.compile(r"\(\d/\d/\d\)")
SVAR_RE = re.compile(r"^\s*Svar:?\s*(x =|f \(.*\) =|dl|%|kr|°F)?\s*$", re.I)
DIGIT_GROUP = re.compile(r"(?<=\d) (?=\d{3}\b)")  # tusentalsgrupp: «1 200», «800 000»; ej över radbryt


def stam_text(termin, delprov, ranges):
    ls = LINES[(termin, delprov)]
    out = []
    for a, b in ranges:
        for i in range(a, b + 1):
            ln = ls[i - 1]
            ln = POANG_RE.sub("", ln)
            if SVAR_RE.match(ln):
                continue
            ln = re.sub(r"^\s*\d+\.\s*", "", ln)          # uppgiftsnummer i radstart
            ln = re.sub(r"^\s*[a-d]\)\s*", "", ln)          # deluppgiftsbokstav
            ln = re.sub(r"^\s*(I|II|III|IV|V)\.\s*", "", ln)
            out.append(ln.strip())
    # radbryt mellan häftesrader hindrar att alternativrader (30 / 75 / 150) slås ihop till ett tal
    return " \n ".join(x for x in out if x)


def matt(text):
    t = DIGIT_GROUP.sub("", text)
    tokens = [w for w in re.split(r"\s+", t) if re.search(r"[0-9A-Za-zÅÄÖåäö]", w)]
    ints = [int(x) for x in re.findall(r"(?<![\d,])\d+(?![\d,])", t)]
    decs = [len(d) for d in re.findall(r"\d+,(\d+)", t)]
    return len(tokens), (max(ints) if ints else None), (max(decs) if decs else 0)


# ---- handdömda fält -------------------------------------------------------
# nyckel: (termin, delprov, nr, del) -> dict; ranges = radintervall i häftet
U = []

def u(termin, delprov, nr, del_, poang, ranges, **kw):
    d = dict(termin=termin, delprov=delprov, nr=nr, poang=poang, ranges=ranges); d["del"] = del_
    d.update(kw)
    U.append(d)

# ---------------- vt17 delprov B (utan räknare, 60 min) ----------------
u("vt17","B",1,"",[1,0,0],[(73,82)], formaga=["B"], kortsvar=True, flerval=True, mfr=0,
  fragverb="vilken", motivera=False, svarsform="", konst=0, sanning="ej", steg=1,
  kontext="ren", repr=["text","formel"], innehall="aritmetik", metod=False, fortyd=False,
  form="välj bästa närmevärde till ett rotuttryck bland fem tal",
  avg="E: rätt alternativ inringat",
  anm="rotuttrycket är en bild och saknas i textlagret; max_heltal ur alternativen")
u("vt17","B",2,"",[1,0,0],[(88,88)], formaga=["P"], kortsvar=True, flerval=False, mfr=0,
  fragverb="lös", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="ren", repr=["formel"], innehall="ekvationer", metod=False, fortyd=False,
  form="lös linjär ekvation med negativ lösning, kortsvar", avg="E: korrekt svar")
u("vt17","B",3,"a",[1,0,0],[(95,98),(101,104)], formaga=["B","P"], kortsvar=True, flerval=False, mfr=2,
  fragverb="rita", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="naturvetenskap", repr=["text","graf"], innehall="funktioner", metod=False, fortyd=False,
  form="rita linjär graf genom två givna punkter i färdigt koordinatsystem",
  avg="E: godtagbart ritad graf")
u("vt17","B",3,"b",[1,0,0],[(95,98),(107,109)], formaga=["P","M"], kortsvar=True, flerval=False, mfr=2,
  fragverb="avläsa", motivera=False, svarsform="", konst=0, sanning="ej", steg=1,
  kontext="naturvetenskap", repr=["text","graf"], innehall="funktioner", metod=False, fortyd=False,
  form="avläs värde i egen graf, intervall godtas", avg="E: svar inom intervall")
u("vt17","B",4,"",[1,0,0],[(123,126)], formaga=["B","P"], kortsvar=True, flerval=False, mfr=2,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="vardag", repr=["text"], innehall="procent", metod=False, fortyd=True,
  form="andel av blandning i procent ur delförhållande, kortsvar", avg="E: korrekt svar")
u("vt17","B",5,"",[2,0,0],[(138,146)], formaga=["PL","P","K"], kortsvar=False, flerval=False, mfr=3,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=3,
  kontext="vardag", repr=["text","figur"], innehall="geometri", metod=False, fortyd=False,
  form="andel bortklippt area ur figur med mått, redovisning krävs",
  avg="E2: lösning med godtagbart svar (bråk)", anm="måtten står i figuren, inte i texten")
u("vt17","B",6,"",[1,1,0],[(169,180)], formaga=["B"], kortsvar=True, flerval=True, mfr=0,
  fragverb="vilken", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="ren", repr=["text"], innehall="procent", metod=False, fortyd=False,
  form="markera alla alternativ som är lika med en procentsats, promille och ppm",
  avg="C: två rätt och inget fel markerat; E: minst ett rätt och högst ett fel")
u("vt17","B",7,"",[0,1,0],[(192,197),(232,233)], formaga=["B","PL"], kortsvar=True, flerval=False, mfr=4,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="vardag", repr=["text","figur"], innehall="procent", metod=False, fortyd=False,
  form="rabatt i procent på helheten ur erbjudande i ord, kortsvar", avg="C: korrekt svar",
  anm="inga siffror i stammen; erbjudandet står i en ruta")
u("vt17","B",8,"",[1,1,0],[(208,227)], formaga=["PL","M"], kortsvar=True, flerval=False, mfr=4,
  fragverb="fylla", motivera=False, svarsform="", konst=0, sanning="ej", steg=3,
  kontext="vardag", repr=["text","tabell"], innehall="proportionalitet", metod=False, fortyd=True,
  form="fyll i tabell för omvänd proportionalitet ur ordexempel",
  avg="C: hela tabellen rätt; E: minst två värden rätt")
u("vt17","B",9,"",[0,1,0],[(241,242)], formaga=["B","P"], kortsvar=True, flerval=False, mfr=0,
  fragverb="vilken", motivera=False, svarsform="", konst=1, sanning="ej", steg=2,
  kontext="ren", repr=["formel"], innehall="algebra", metod=False, fortyd=False,
  form="värde av linjärt uttryck givet en ekvation i x, kortsvar", avg="C: korrekt svar")
u("vt17","B",10,"",[0,1,0],[(251,259)], formaga=["B"], kortsvar=True, flerval=True, mfr=0,
  fragverb="ringa in", motivera=False, svarsform="", konst=0, sanning="ej", steg=6,
  kontext="ren", repr=["formel"], innehall="potenser", metod=False, fortyd=False,
  form="ringa in de potenser bland sex som har samma värde", avg="C: korrekt svar",
  anm="exponenterna tappade i textlagret (05, 14, 23 ...); steg = sex värderingar")
u("vt17","B",11,"",[0,1,0],[(266,268)], formaga=["B","P"], kortsvar=True, flerval=False, mfr=2,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="vardag", repr=["text"], innehall="procent", metod=False, fortyd=False,
  form="pris före rabatt ur pris efter, kortsvar", avg="C: korrekt svar")
u("vt17","B",12,"",[0,1,1],[(278,279)], formaga=["B","P","K"], kortsvar=False, flerval=False, mfr=1,
  fragverb="skriva", motivera=False, svarsform="", konst=2, sanning="ej", steg=3,
  kontext="ren", repr=["formel"], innehall="algebra", metod=False, fortyd=False,
  form="uttryck procent av ett flerfaldigat värde i annan bokstav, redovisning krävs",
  avg="A: redovisning med korrekt svar; C: något samband mellan bokstäverna i symboler")
u("vt17","B",13,"",[0,0,1],[(300,304)], formaga=["PL"], kortsvar=True, flerval=False, mfr=1,
  fragverb="hitta", motivera=False, svarsform="", konst=2, sanning="ej", steg=2,
  kontext="ren", repr=["formel"], innehall="ekvationer", metod=False, fortyd=True,
  form="hitta lösning till ekvation i två variabler med extra villkor, kortsvar",
  avg="A: korrekt svar (bråk)")
u("vt17","B",14,"",[0,0,1],[(315,318)], formaga=["B","PL"], kortsvar=True, flerval=True, mfr=2,
  fragverb="hur", motivera=False, svarsform="", konst=2, sanning="ej", steg=1,
  kontext="ren", repr=["text","graf"], innehall="funktioner", metod=False, fortyd=False,
  form="välj det diagram som visar sambandet mellan sidor vid konstant area",
  avg="A: rätt diagram markerat")

# ---------------- vt17 delprov C (räknare, 60 min, en stor uppgift, matris) ----------------
u("vt17","C",15,"",[4,4,4],[(89,124)], formaga=["B","P","PL","R","K"], kortsvar=False, flerval=False, mfr=7,
  fragverb="vad", motivera=False, svarsform="", konst=0, sanning="okand", steg=12,
  kontext="vardag", repr=["text","figur"], innehall="sannolikhet", metod=False, fortyd=True,
  form="fem frågor om tärningsspel: enkla sannolikheter, två kast, undersök totalpoäng på sikt",
  avg="A: sannolikhet för två kastomgångar, genomsnittlig poängändring, motiverat resonemang om trenden, lätt följd redovisning",
  anm="matrisbedömd helhet med delfrågor I–V; sista delen är «undersök», inte «motivera»; delprovets anvisning kräver ändå motiveringar")

# ---------------- vt17 delprov D (räknare, 120 min) ----------------
u("vt17","D",16,"",[2,0,0],[(77,78)], formaga=["B","P"], kortsvar=False, flerval=False, mfr=1,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="vardag", repr=["text"], innehall="procent", metod=False, fortyd=False,
  form="månadsränta ur lånebelopp och årsräntesats", avg="E2: lösning med korrekt svar")
u("vt17","D",17,"",[2,0,0],[(84,84)], formaga=["PL","B","K"], kortsvar=False, flerval=False, mfr=1,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="naturvetenskap", repr=["text"], innehall="geometri", metod=False, fortyd=False,
  form="volym i liter ur nederbörd i mm över en yta", avg="E2: lösning med korrekt svar")
u("vt17","D",18,"a",[1,0,0],[(91,102),(104,105)], formaga=["P","M"], kortsvar=True, flerval=False, mfr=5,
  fragverb="vilken", motivera=False, svarsform="", konst=1, sanning="ej", steg=1,
  kontext="naturvetenskap", repr=["text","formel"], innehall="funktioner", metod=False, fortyd=True,
  form="sätt in givet värde i given formel, endast svar", avg="E: godtagbart svar")
u("vt17","D",18,"b",[1,1,0],[(91,102),(109,110)], formaga=["P","M"], kortsvar=False, flerval=False, mfr=5,
  fragverb="vilken", motivera=False, svarsform="", konst=1, sanning="ej", steg=2,
  kontext="naturvetenskap", repr=["text","formel"], innehall="ekvationer", metod=False, fortyd=True,
  form="lös ut variabel ur given formel med insatt värde", avg="C: lösning med korrekt svar")
u("vt17","D",19,"",[1,2,0],[(118,123)], formaga=["PL","P","K"], kortsvar=False, flerval=False, mfr=3,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=3,
  kontext="vardag", repr=["text"], innehall="procent", metod=False, fortyd=False,
  form="genomsnittligt bidrag per person givet andel som når fram och styckpris",
  avg="C2: lösning med korrekt svar; C1: tar hänsyn till procentandelen")
u("vt17","D",20,"",[1,1,0],[(133,137)], formaga=["PL","B"], kortsvar=False, flerval=False, mfr=3,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=3,
  kontext="naturvetenskap", repr=["text"], innehall="procent", metod=False, fortyd=False,
  form="halt i ppm ur totalmängd, antal och medelvikt", avg="C: lösning med godtagbart svar")
u("vt17","D",21,"a",[2,0,0],[(145,149),(151,151)], formaga=["B","P","K"], kortsvar=False, flerval=False, mfr=4,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=3,
  kontext="vardag", repr=["text"], innehall="aritmetik", metod=False, fortyd=False,
  form="total restid ur två delsträckor med olika medelfart", avg="E2: lösning som motsvarar rätt tid")
u("vt17","D",21,"b",[0,1,0],[(145,149),(155,155)], formaga=["PL"], kortsvar=False, flerval=False, mfr=4,
  fragverb="vad", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="vardag", repr=["text"], innehall="aritmetik", metod=False, fortyd=False,
  form="medelfart för hela sträckan (fällan: inte medelvärdet av farterna)",
  avg="C: lösning med godtagbart svar")
u("vt17","D",22,"a",[1,0,0],[(169,178),(180,180)], formaga=["P"], kortsvar=False, flerval=False, mfr=3,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="vardag", repr=["text"], innehall="aritmetik", metod=False, fortyd=False,
  form="pris för given mängd av två alternativ", avg="E: beräkning med korrekt svar")
u("vt17","D",22,"b",[1,0,0],[(169,178),(183,184)], formaga=["M","K"], kortsvar=False, flerval=False, mfr=3,
  fragverb="ange", motivera=False, svarsform="", konst=0, sanning="ej", steg=1,
  kontext="vardag", repr=["text"], innehall="funktioner", metod=False, fortyd=False,
  form="ange formel för kostnad som funktion av mängd", avg="E: godtagbart uttryck eller formel, även i ord")
u("vt17","D",22,"c",[0,1,1],[(169,178),(188,188)], formaga=["PL","P","K"], kortsvar=False, flerval=False, mfr=3,
  fragverb="vilken", motivera=False, svarsform="", konst=0, sanning="ej", steg=3,
  kontext="vardag", repr=["text"], innehall="ekvationer", metod=False, fortyd=False,
  form="brytpunkt där två prismodeller (en med tröskelrabatt) kostar lika",
  avg="A: effektiv metod (ekvation) med korrekt svar; C: prövning med korrekt svar eller påbörjad effektiv metod")
u("vt17","D",23,"",[1,2,0],[(198,202)], formaga=["PL","M","P","K"], kortsvar=False, flerval=False, mfr=5,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=4,
  kontext="vardag", repr=["text","figur"], innehall="aritmetik", metod=False, fortyd=False,
  form="längd på mönstrad gång inom budget ur bild av mönstret och styckpriser",
  avg="C2: lösning med korrekt svar; C1: antalet rader bestämt")
u("vt17","D",24,"",[1,1,1],[(211,216)], formaga=["B","PL"], kortsvar=False, flerval=False, mfr=3,
  fragverb="hur", motivera=False, svarsform="", konst=1, sanning="ej", steg=3,
  kontext="vardag", repr=["text"], innehall="procent", metod=False, fortyd=False,
  form="procentuell skillnad mellan två belopp som anges relativt ett tredje okänt",
  avg="A: förhållandet visat generellt (algebraiskt), inte bara för ett valt värde")
u("vt17","D",25,"",[1,1,1],[(222,226)], formaga=["B","P","R"], kortsvar=False, flerval=False, mfr=4,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="given", steg=3,
  kontext="vardag", repr=["text"], innehall="procent", metod=False, fortyd=False,
  form="förklara hur ett påstående om lika stora ökningar kan stämma (procent mot procentenheter)",
  avg="A: lösning med godtagbart svar, dvs. båda relativa ökningarna beräknade och slutsats",
  anm="resonemang prövas med «Hur kan X ha resonerat?», inte med «Motivera»")
u("vt17","D",26,"",[1,1,1],[(234,240)], formaga=["PL","M","P"], kortsvar=False, flerval=False, mfr=3,
  fragverb="hur", motivera=False, svarsform="", konst=2, sanning="ej", steg=3,
  kontext="vardag", repr=["text","formel"], innehall="ekvationer", metod=False, fortyd=True,
  form="lös given intäktsformel för x och tolka sedan om till den andra sorten",
  avg="A: tolkningen, dvs. rätt antal av den andra sorten; C: ekvationen löst")
u("vt17","D",27,"",[0,1,2],[(247,250)], formaga=["PL","M","P","K"], kortsvar=False, flerval=False, mfr=3,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=4,
  kontext="vardag", repr=["text"], innehall="geometri", metod=False, fortyd=True,
  form="area av halvcirkel när hela omkretsen (båge plus diameter) är given",
  avg="A2: lösning med godtagbart svar; A1: radie eller diameter bestämd; C: uttryck för omkretsen")

# ---------------- vt22 delprov B (utan räknare, 60 min, endast svar) ----------------
u("vt22","B",1,"",[1,0,0],[(74,83)], formaga=None, kortsvar=True, flerval=False, mfr=1,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=3,
  kontext="vardag", repr=["text","tabell"], innehall="aritmetik", metod=False, fortyd=False,
  form="volym i dl ur måttabell och antal, kortsvar", avg="E: korrekt svar")
u("vt22","B",2,"",[1,0,0],[(100,101)], formaga=None, kortsvar=True, flerval=False, mfr=0,
  fragverb="förenkla", motivera=False, svarsform="förenkla så långt som möjligt", konst=1, sanning="ej", steg=2,
  kontext="ren", repr=["formel"], innehall="algebra", metod=False, fortyd=False,
  form="förenkla linjärt uttryck med parentes, kortsvar", avg="E: korrekt svar")
u("vt22","B",3,"",[1,0,0],[(114,115)], formaga=None, kortsvar=True, flerval=False, mfr=0,
  fragverb="faktorisera", motivera=False, svarsform="", konst=1, sanning="ej", steg=1,
  kontext="ren", repr=["formel"], innehall="algebra", metod=True, fortyd=False,
  form="bryt ut största faktor ur binom, kortsvar", avg="E: korrekt svar")
u("vt22","B",4,"",[1,0,0],[(128,142)], formaga=None, kortsvar=True, flerval=True, mfr=3,
  fragverb="vilken", motivera=False, svarsform="", konst=2, sanning="ej", steg=1,
  kontext="vardag", repr=["text","formel"], innehall="funktioner", metod=False, fortyd=False,
  form="välj rätt linjär formel bland fem för fast plus rörlig kostnad", avg="E: korrekt svar")
u("vt22","B",5,"",[1,0,0],[(153,157)], formaga=None, kortsvar=True, flerval=True, mfr=2,
  fragverb="vilken", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="vardag", repr=["text","formel"], innehall="sannolikhet", metod=False, fortyd=False,
  form="välj rätt beräkning för sannolikhet utan återläggning i två steg",
  avg="E: korrekt svar", anm="svarsalternativen är bilder och saknas i textlagret")
u("vt22","B",6,"",[1,0,0],[(178,181)], formaga=None, kortsvar=True, flerval=False, mfr=2,
  fragverb="skriva", motivera=False, svarsform="", konst=2, sanning="ej", steg=2,
  kontext="vardag", repr=["text"], innehall="funktioner", metod=False, fortyd=False,
  form="skriv exponentiell avtagande funktion ur startvärde och procent per år", avg="E: korrekt svar")
u("vt22","B",7,"",[1,0,0],[(196,197)], formaga=None, kortsvar=True, flerval=True, mfr=1,
  fragverb="vilken", motivera=False, svarsform="", konst=0, sanning="ej", steg=1,
  kontext="ren", repr=["text","graf"], innehall="statistik", metod=False, fortyd=False,
  form="välj det spridningsdiagram av sex som visar starkast korrelation", avg="E: korrekt svar")
u("vt22","B",8,"a",[1,0,0],[(209,209),(212,212)], formaga=None, kortsvar=True, flerval=False, mfr=1,
  fragverb="bestämma", motivera=False, svarsform="", konst=2, sanning="ej", steg=1,
  kontext="ren", repr=["graf","formel"], innehall="funktioner", metod=False, fortyd=False,
  form="avläs funktionsvärde i given graf", avg="E: korrekt svar")
u("vt22","B",8,"b",[0,1,0],[(209,209),(216,216)], formaga=None, kortsvar=True, flerval=False, mfr=1,
  fragverb="lös", motivera=False, svarsform="", konst=1, sanning="ej", steg=1,
  kontext="ren", repr=["graf","formel"], innehall="funktioner", metod=False, fortyd=False,
  form="lös ekvation f(x)=k grafiskt (avläs x ur given graf)", avg="C: korrekt svar")
u("vt22","B",9,"",[0,1,0],[(226,233)], formaga=None, kortsvar=True, flerval=False, mfr=3,
  fragverb="ange", motivera=False, svarsform="", konst=2, sanning="ej", steg=2,
  kontext="vardag", repr=["text","figur"], innehall="funktioner", metod=False, fortyd=False,
  form="ange linjär formel för antal delar i mönster ur bild av ett exemplar", avg="C: korrekt formel")
u("vt22","B",10,"",[0,2,0],[(244,281)], formaga=None, kortsvar=True, flerval=True, mfr=1,
  fragverb="ange", motivera=False, svarsform="", konst=0, sanning="ej", steg=4,
  kontext="vardag", repr=["text","tabell"], innehall="funktioner", metod=False, fortyd=False,
  form="kryssa linjär eller exponentiell modell för fyra beskrivna situationer",
  avg="C2: alla fyra rätt; C1: minst tre rätt")
u("vt22","B",11,"",[0,1,0],[(296,297)], formaga=None, kortsvar=True, flerval=False, mfr=0,
  fragverb="skriva", motivera=False, svarsform="", konst=1, sanning="ej", steg=2,
  kontext="ren", repr=["formel"], innehall="algebra", metod=False, fortyd=False,
  form="fyll i tom parentes så att två faktoriserade uttryck blir lika", avg="C: korrekt svar")
u("vt22","B",12,"",[0,1,0],[], formaga=None, kortsvar=None, flerval=None, mfr=None,
  fragverb=None, motivera=None, svarsform=None, konst=None, sanning=None, steg=None,
  kontext=None, repr=None, innehall=None, metod=None, fortyd=None,
  form=None, avg=None,
  anm="borttagen ur häftet p.g.a. sekretess; poängen (0/1/0) härledd ur delprovets maxpoäng 8/7/4")
u("vt22","B",13,"",[0,1,1],[(302,316)], formaga=None, kortsvar=True, flerval=True, mfr=1,
  fragverb="vilken", motivera=False, svarsform="", konst=2, sanning="ej", steg=2,
  kontext="vardag", repr=["text","formel"], innehall="procent", metod=False, fortyd=False,
  form="markera alla påståenden i ord som alltid följer ur ett givet samband mellan två bokstäver",
  avg="A: båda rätt och inget fel markerat; C: minst ett rätt och inget fel",
  anm="«stämmer alltid» = påståendeprövning i flervalsform; sanning satt till ej eftersom eleven inte redovisar")
u("vt22","B",14,"",[0,0,1],[(325,329)], formaga=None, kortsvar=True, flerval=False, mfr=0,
  fragverb="skriva", motivera=False, svarsform="förenkla så långt som möjligt", konst=2, sanning="ej", steg=2,
  kontext="ren", repr=["formel"], innehall="algebra", metod=False, fortyd=False,
  form="uttryck i en bokstav ur samband mellan två, kortsvar", avg="A: korrekt svar")
u("vt22","B",15,"",[0,0,1],[(341,345),(350,351)], formaga=None, kortsvar=True, flerval=False, mfr=2,
  fragverb="bestämma", motivera=False, svarsform="procent", konst=0, sanning="ej", steg=2,
  kontext="vardag", repr=["text"], innehall="procent", metod=False, fortyd=False,
  form="andel i procent ur gränsvärde i mg per kg, kortsvar", avg="A: korrekt svar",
  anm="källhänvisningens årtal uteslutet ur stammen")
u("vt22","B",16,"",[0,0,1],[(362,364)], formaga=None, kortsvar=True, flerval=False, mfr=1,
  fragverb="bestämma", motivera=False, svarsform="", konst=1, sanning="ej", steg=2,
  kontext="ren", repr=["formel"], innehall="funktioner", metod=False, fortyd=False,
  form="värde av sammansatt funktion f(g(k)) för två givna linjära funktioner", avg="A: korrekt svar")

# ---------------- vt22 delprov C (utan räknare, 60 min, redovisning) ----------------
u("vt22","C",17,"",[3,2,2],[(63,63),(65,66),(72,72),(76,79),(84,85),(89,98)],
  formaga=["B","P","PL","R","K"], kortsvar=False, flerval=False, mfr=7,
  fragverb="beräkna", motivera=False, svarsform="exakt", konst=2, sanning="ej", steg=5,
  kontext="ren", repr=["text","figur"], innehall="funktioner", metod=False, fortyd=True,
  form="fraktalmönster: omkrets steg 1 och 2, förändringsfaktor, exakt formel för steg n",
  avg="A: uttryck för omkretsen i steg n (även utan exakt faktor); A-redovisning: lätt att följa med exakt formel",
  anm="matrisbedömd; a–d bedöms som helhet; förmågorna ur matrisens aspektrubriker")
u("vt22","C",18,"a",[2,0,0],[(117,117)], formaga=None, kortsvar=False, flerval=False, mfr=0,
  fragverb="lös", motivera=False, svarsform="", konst=0, sanning="ej", steg=3,
  kontext="ren", repr=["formel"], innehall="ekvationer", metod=False, fortyd=False,
  form="lös linjär ekvation med parentes, x på båda sidor, lösning ej heltal",
  avg="E2: lösning med korrekt svar; E1: parentesen upplöst")
u("vt22","C",18,"b",[0,2,0],[(124,124)], formaga=None, kortsvar=False, flerval=False, mfr=0,
  fragverb="lös", motivera=False, svarsform="", konst=0, sanning="ej", steg=4,
  kontext="ren", repr=["formel"], innehall="ekvationer", metod=False, fortyd=False,
  form="lös ekvation med produkt av två binom där kvadrattermerna tar ut varandra",
  avg="C2: lösning med korrekt svar; C1: parenteserna multiplicerade")
u("vt22","C",19,"",[0,1,0],[(133,133),(136,138),(141,142),(144,144),(146,146),(152,153)],
  formaga=None, kortsvar=False, flerval=False, mfr=3,
  fragverb="förklara", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="vardag", repr=["text","formel","tabell"], innehall="aritmetik", metod=False, fortyd=False,
  form="förklara vad en given beräkning med prislistans tal betyder",
  avg="C: resonemang som beskriver skillnaden i pris per gång (inte per tio gånger)",
  anm="resonemang/tolkning utan «Motivera»; en poäng, allt eller inget")
u("vt22","C",20,"",[0,1,0],[(162,166)], formaga=None, kortsvar=False, flerval=False, mfr=3,
  fragverb="bestämma", motivera=False, svarsform="", konst=2, sanning="ej", steg=2,
  kontext="yrke", repr=["text"], innehall="funktioner", metod=False, fortyd=False,
  form="ställ upp funktion b(h) ur konstant triangelarea", avg="C: lösning med korrekt svar")
u("vt22","C",21,"",[0,0,2],[(176,176),(179,181),(187,190)], formaga=None, kortsvar=False, flerval=False, mfr=2,
  fragverb="visa", motivera=False, svarsform="", konst=0, sanning="given", steg=3,
  kontext="vardag", repr=["text","formel"], innehall="geometri", metod=False, fortyd=False,
  form="visa att halverat ark behåller sidförhållandet 1 mot roten ur 2",
  avg="A2: visar att kvoten kan skrivas om till den givna formen; A1: bestämmer det nya förhållandet",
  anm="rottecknet saknas i textlagret; enda «visa att» i korpusen")

# ---------------- vt22 delprov D (räknare, 120 min) ----------------
u("vt22","D",22,"a",[1,0,0],[(66,71),(73,74)], formaga=None, kortsvar=True, flerval=False, mfr=2,
  fragverb="vilken", motivera=False, svarsform="", konst=1, sanning="ej", steg=1,
  kontext="vardag", repr=["text","formel"], innehall="funktioner", metod=False, fortyd=True,
  form="läs av räntesatsen ur given exponentialfunktion, endast svar", avg="E: korrekt svar")
u("vt22","D",22,"b",[1,0,0],[(66,71),(78,79)], formaga=None, kortsvar=True, flerval=False, mfr=2,
  fragverb="beräkna", motivera=False, svarsform="", konst=1, sanning="ej", steg=1,
  kontext="vardag", repr=["text","formel"], innehall="funktioner", metod=False, fortyd=True,
  form="beräkna funktionsvärde i given exponentialfunktion, endast svar", avg="E: godtagbart svar")
u("vt22","D",23,"a",[1,0,0],[(90,92),(95,138),(141,143)], formaga=None, kortsvar=True, flerval=False, mfr=2,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="naturvetenskap", repr=["text","tabell"], innehall="statistik", metod=False, fortyd=False,
  form="skillnad mellan två avlästa värden i tabell, endast svar", avg="E: korrekt svar",
  anm="tabellens 30 tal räknas in i ord_stam")
u("vt22","D",23,"b",[1,1,0],[(90,92),(95,138),(147,149)], formaga=None, kortsvar=False, flerval=False, mfr=2,
  fragverb="är", motivera=True, svarsform="", konst=0, sanning="okand", steg=2,
  kontext="naturvetenskap", repr=["text","tabell"], innehall="funktioner", metod=False, fortyd=False,
  form="avgör om tabellsamband är linjärt, motivera ur tabellvärden",
  avg="C: rätt slutsats med hänvisning till specifika tabellvärden; E: rätt slutsats utan värden, eller fel slutsats med värden",
  anm="enda «Motivera» i korpusen; fel slutsats kan ändå ge E om värden anförs")
u("vt22","D",24,"a",[2,0,0],[(161,175),(178,179)], formaga=None, kortsvar=False, flerval=False, mfr=3,
  fragverb="beräkna", motivera=False, svarsform="", konst=0, sanning="ej", steg=4,
  kontext="vardag", repr=["text","tabell"], innehall="aritmetik", metod=False, fortyd=False,
  form="årslön för två alternativ ur tabell med grundlön och tillägg", avg="E2: båda årslönerna beräknade")
u("vt22","D",24,"b",[2,1,0],[(161,175),(182,185)], formaga=None, kortsvar=False, flerval=False, mfr=4,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=3,
  kontext="vardag", repr=["text","tabell"], innehall="ekvationer", metod=False, fortyd=True,
  form="minsta heltal månader där ena lönemodellen passerar den andra",
  avg="C: lösning med korrekt heltalssvar; E2: brytpunkt visad i rätt intervall; prövning godtas")
u("vt22","D",25,"a",[1,0,0],[(192,193),(197,198)], formaga=None, kortsvar=True, flerval=False, mfr=2,
  fragverb="vilken", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="vardag", repr=["text","tabell"], innehall="kalkylblad", metod=False, fortyd=False,
  form="beräkna värdet i en cell (ränta plus amortering), endast svar", avg="E: korrekt svar",
  anm="kalkylbladet är en bild och saknas i textlagret")
u("vt22","D",25,"b",[1,0,0],[(192,193),(203,204),(206,207)], formaga=None, kortsvar=True, flerval=False, mfr=3,
  fragverb="vilken", motivera=False, svarsform="", konst=0, sanning="ej", steg=1,
  kontext="vardag", repr=["text","tabell"], innehall="kalkylblad", metod=False, fortyd=True,
  form="skriv cellformel för kvarvarande skuld, endast svar", avg="E: fungerande formel, med eller utan likhetstecken")
u("vt22","D",25,"c",[0,1,0],[(192,193),(203,204),(211,212)], formaga=None, kortsvar=True, flerval=False, mfr=3,
  fragverb="vilken", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="vardag", repr=["text","tabell"], innehall="kalkylblad", metod=False, fortyd=True,
  form="skriv cellformel som kombinerar tre celler för månadsbetalning, endast svar",
  avg="C: fungerande formel")
u("vt22","D",26,"",[0,3,0],[(223,226)], formaga=None, kortsvar=False, flerval=False, mfr=3,
  fragverb="bestämma", motivera=False, svarsform="", konst=3, sanning="ej", steg=5,
  kontext="ren", repr=["text"], innehall="ekvationer", metod=False, fortyd=False,
  form="tre vinklar givna som procentuella avvikelser från en okänd, vinkelsumma",
  avg="C3: lösning med korrekt svar; C2: samband/ekvation uppställd eller avslutad prövning; C1: vinklarna uttryckta som andel av den okända")
u("vt22","D",27,"",[0,2,0],[(236,238)], formaga=None, kortsvar=False, flerval=False, mfr=2,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=2,
  kontext="vardag", repr=["text"], innehall="procent", metod=False, fortyd=False,
  form="ursprungligt pris när total inklusive procentpåslag är given",
  avg="C2: lösning med godtagbart svar; C1: ekvation eller kvot uppställd")
u("vt22","D",28,"a",[1,0,0],[(252,255),(257,258)], formaga=None, kortsvar=False, flerval=False, mfr=2,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=1,
  kontext="vardag", repr=["text","figur"], innehall="sannolikhet", metod=False, fortyd=False,
  form="sannolikhet för två oberoende vinster i rad", avg="E: lösning med korrekt svar")
u("vt22","D",28,"b",[0,2,1],[(252,255),(262,263)], formaga=None, kortsvar=False, flerval=False, mfr=2,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=3,
  kontext="vardag", repr=["text","figur"], innehall="sannolikhet", metod=False, fortyd=False,
  form="sannolikhet för minst en vinst på flera försök (komplementhändelse)",
  avg="A: lösning med godtagbart svar; C2: komplementets sannolikhet tecknad; C1: komplementet identifierat")
u("vt22","D",29,"a",[1,1,0],[(277,278),(282,287),(290,290),(292,294)], formaga=None, kortsvar=False, flerval=False, mfr=4,
  fragverb="använda", motivera=False, svarsform="", konst=3, sanning="ej", steg=2,
  kontext="vardag", repr=["text","formel"], innehall="funktioner", metod=True, fortyd=True,
  form="sätt in tre värden i given formel med tre parametrar",
  avg="C: godtagbart svar utifrån den givna formeln; E: värden insatta, eller rätt svar utan formeln",
  anm="formeln är en bild och saknas i textlagret; enda «använd formeln» i korpusen")
u("vt22","D",29,"b",[0,1,2],[(277,278),(282,287),(290,290),(297,300)], formaga=None, kortsvar=False, flerval=False, mfr=7,
  fragverb="vilken", motivera=False, svarsform="", konst=2, sanning="ej", steg=4,
  kontext="vardag", repr=["text","formel"], innehall="ekvationer", metod=False, fortyd=False,
  form="lös given formel baklänges när två parametrar är kopplade (den ena dubbla den andra)",
  avg="A2: lösning med korrekt svar; A1: en hastighet bestämd via ekvationslösning; C: prövning med rätt svar eller uttrycker båda i samma variabel")
u("vt22","D",30,"",[0,0,2],[(309,311)], formaga=None, kortsvar=False, flerval=False, mfr=1,
  fragverb="hur", motivera=False, svarsform="", konst=0, sanning="ej", steg=3,
  kontext="naturvetenskap", repr=["text"], innehall="procent", metod=False, fortyd=False,
  form="tillsatt mängd så att en andel sjunker till given procent (utspädning)",
  avg="A2: lösning med korrekt svar; A1: uttryck eller ekvation för total eller tillsatt mängd")
u("vt22","D",31,"",[0,0,3],[(322,324)], formaga=None, kortsvar=False, flerval=False, mfr=2,
  fragverb="bestämma", motivera=False, svarsform="", konst=1, sanning="ej", steg=4,
  kontext="ren", repr=["text"], innehall="ekvationer", metod=False, fortyd=False,
  form="tal som ligger samma procent över ett tal och under ett annat",
  avg="A3: korrekt svar med p använt i procentform; A2: p bestämd eller ekvation i en variabel; A1: samband mellan p och x tecknat",
  anm="enda uppgiften med tre A-poäng i korpusen")

# ---- bygg raderna ----------------------------------------------------------
NIVA = {0: "E", 1: "C", 2: "A"}
rows = []
for d in U:
    e, c, a = d["poang"]
    niva = "A" if a else ("C" if c else "E")
    if d["ranges"]:
        text = stam_text(d["termin"], d["delprov"], d["ranges"])
        ord_stam, max_heltal, decimaler = matt(text)
    else:
        ord_stam = max_heltal = decimaler = None
    steg = d["steg"]
    rows.append(dict(
        termin=d["termin"], delprov=d["delprov"], nr=d["nr"], del_=d["del"],
        poang=d["poang"], niva=niva, formaga=d["formaga"], kortsvar=d["kortsvar"],
        flerval=d["flerval"], ord_stam=ord_stam, meningar_fore_fragan=d["mfr"],
        fragverb=d["fragverb"], motivera=d["motivera"], svarsform_instruktion=d["svarsform"],
        konstanter=d["konst"], sanning=d["sanning"], steg=steg,
        steg_per_poang=(round(steg / sum(d["poang"]), 2) if steg is not None else None),
        kontext=d["kontext"], representation=d["repr"], max_heltal=max_heltal,
        decimaler=decimaler, innehall=d["innehall"], metodforeskrift=d["metod"],
        fortydligande=d["fortyd"], form_parafras=d["form"], avgorande_steg=d["avg"],
        anm=d.get("anm", ""),
    ))
for r in rows:
    r["del"] = r.pop("del_")
    # ordna fälten
    order = ["termin","delprov","nr","del","poang","niva","formaga","kortsvar","flerval",
             "ord_stam","meningar_fore_fragan","fragverb","motivera","svarsform_instruktion",
             "konstanter","sanning","steg","steg_per_poang","kontext","representation",
             "max_heltal","decimaler","innehall","metodforeskrift","fortydligande",
             "form_parafras","avgorande_steg","anm"]
    r2 = {k: r[k] for k in order}
    r.clear(); r.update(r2)

def dsum(termin, delprov):
    s = [0, 0, 0]
    for r in rows:
        if r["termin"] == termin and r["delprov"] == delprov:
            s = [x + y for x, y in zip(s, r["poang"])]
    return s

prov = [
    dict(termin="vt17", delprov=[
        dict(namn="A", uppgifter=[], poang=[4,4,3], tid_min=None, hjalpmedel_raknare=None,
             anm="muntligt delprov, egen bedömningsanvisning (häfte 1); ingår i totalen men inte i uppgiftsraderna"),
        dict(namn="B", uppgifter=list(range(1,15)), poang=dsum("vt17","B"), tid_min=60, hjalpmedel_raknare=False,
             haftets_max=[9,7,3]),
        dict(namn="C", uppgifter=[15], poang=dsum("vt17","C"), tid_min=60, hjalpmedel_raknare=True,
             haftets_max=[4,4,4]),
        dict(namn="D", uppgifter=list(range(16,28)), poang=dsum("vt17","D"), tid_min=120, hjalpmedel_raknare=True,
             haftets_max=[16,12,6]),
    ], total=[33,27,16], total_summa=76,
       kravgranser=dict(E=[18,None,None], D=[30,8,None], C=[40,15,None], B=[51,None,5], A=[60,None,9])),
    dict(termin="vt22", delprov=[
        dict(namn="B", uppgifter=list(range(1,17)), poang=dsum("vt22","B"), tid_min=60, hjalpmedel_raknare=False,
             haftets_max=[8,7,4], anm="uppgift 12 borttagen ur häftet; (0/1/0) härledd"),
        dict(namn="C", uppgifter=list(range(17,22)), poang=dsum("vt22","C"), tid_min=60, hjalpmedel_raknare=False,
             haftets_max=[5,6,4]),
        dict(namn="D", uppgifter=list(range(22,32)), poang=dsum("vt22","D"), tid_min=120, hjalpmedel_raknare=True,
             haftets_max=[12,12,8]),
    ], total=[25,25,16], total_summa=66,
       kravgranser=dict(E=[14,None,None], D=[26,9,None], C=[34,14,None], B=[44,None,4], A=[51,None,8])),
]

json.dump(dict(kurs="1a", kallor=["vt17 (Delprov B, C, D, Bedömningsanvisningar 2; häfte 1 = muntligt delprov A)",
                                  "vt22 (Delprov B, C, D, Bedömningsanvisningar)"],
               regler=dict(
                   ord_stam="whitespace-tokens med minst ett alfanumeriskt tecken; poängmarkering, «Svar:»-rader, uppgiftsnummer och deluppgiftsbokstav borttagna; tusentalsgrupper (1 200) räknas som ett ord; tabell- och alternativtext ingår",
                   konstanter="antal distinkta bokstavssymboler i stammen minus den som efterfrågas; funktionsnamn f/g räknas inte",
                   steg="handdömt antal operationer i anvisningens lösningsväg; uppställning, omskrivning, lösning och tolkning var för sig",
                   formaga="vt17 ur Kopieringsunderlag 4 (förmågor per poäng), union över enhetens poäng; vt22 saknar tabellen i häftet -> null utom delprov C-matrisen",
                   max_heltal="största heltalstoken i stammen; null om inga heltal",
               ),
               prov=prov, uppgifter=rows),
          open(os.path.join(OUT, "1a.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---- statistik till tvärsnittet -----------------------------------------------
def p90(xs):
    xs = sorted(xs)
    if not xs: return None
    k = 0.9 * (len(xs) - 1)
    f = int(k); c = min(f + 1, len(xs) - 1)
    return round(xs[f] + (xs[c] - xs[f]) * (k - f), 1)

R = [r for r in rows if r["steg"] is not None]
print("RADER", len(rows), "varav bedömbara", len(R))
for t in ("vt17", "vt22"):
    for dp in "BCD":
        print(t, dp, "summa", dsum(t, dp))
print("\n== per (niva, kortsvar) median / p90 ==")
for niva in "ECA":
    for ks in (True, False):
        g = [r for r in R if r["niva"] == niva and r["kortsvar"] == ks]
        if not g: continue
        print(f"{niva} {'kortsvar' if ks else 'lösning'} n={len(g)}")
        for f in ("ord_stam", "meningar_fore_fragan", "konstanter", "steg", "steg_per_poang"):
            xs = [r[f] for r in g if r[f] is not None]
            print(f"   {f:22s} median {st.median(xs):5.2f}  p90 {p90(xs)}")
print("\n== per niva (alla) ==")
for niva in "ECA":
    g = [r for r in R if r["niva"] == niva]
    print(f"{niva} n={len(g)}")
    for f in ("ord_stam", "meningar_fore_fragan", "konstanter", "steg", "steg_per_poang", "max_heltal", "decimaler"):
        xs = [r[f] for r in g if r[f] is not None]
        print(f"   {f:22s} median {st.median(xs):7.2f}  p90 {p90(xs)}  min {min(xs)} max {max(xs)}")
    print("   fragverb", Counter(r["fragverb"] for r in g).most_common())
    print("   kontext", Counter(r["kontext"] for r in g).most_common())
    print("   innehall", Counter(r["innehall"] for r in g).most_common())
    print("   fortyd", sum(r["fortydligande"] for r in g), "/", len(g))
    print("   flerval", sum(r["flerval"] for r in g), " kortsvar", sum(r["kortsvar"] for r in g))
    print("   repr", Counter(x for r in g for x in r["representation"]).most_common())
    print("   sanning", Counter(r["sanning"] for r in g).most_common(), " metod", sum(r["metodforeskrift"] for r in g),
          " motivera", sum(r["motivera"] for r in g))
print("\n== per delprov ==")
for t in ("vt17", "vt22"):
    for dp in "BCD":
        g = [r for r in rows if r["termin"] == t and r["delprov"] == dp]
        s = dsum(t, dp); tot = sum(s)
        tid = {"B": 60, "C": 60, "D": 120}[dp]
        nrs = len({r["nr"] for r in g})
        print(f"{t} {dp}: enheter {len(g)}, uppgiftsnummer {nrs}, poäng {s} andel E/C/A "
              f"{[round(x/tot,2) for x in s]}, enheter/10 min {round(len(g)/tid*10,2)}, nummer/10 min {round(nrs/tid*10,2)}, poäng/10 min {round(tot/tid*10,2)}")
        gg = [r for r in g if r["steg"] is not None]
        print("    ord_stam median", st.median([r["ord_stam"] for r in gg]), " steg summa", sum(r["steg"] for r in gg),
              " kortsvar", sum(r["kortsvar"] for r in gg), "/", len(gg))
print("\n== tal per räknare ==")
for rk in (False, True):
    g = [r for r in R if ((r["delprov"] == "D") or (r["termin"] == "vt17" and r["delprov"] == "C")) == rk]
    xs = [r["max_heltal"] for r in g if r["max_heltal"] is not None]
    ds = [r["decimaler"] for r in g]
    print("räknare" if rk else "utan", "n", len(g), "max_heltal min/median/max", min(xs), st.median(xs), max(xs),
          "decimaler max", max(ds), "andel med decimaltal", round(sum(1 for d in ds if d > 0) / len(ds), 2))
    print("   heltal sorterade", sorted(xs))
print("\n== formaga (vt17) ==")
for niva in "ECA":
    g = [r for r in R if r["termin"] == "vt17" and r["niva"] == niva]
    print(niva, Counter(x for r in g for x in (r["formaga"] or [])).most_common())
print("\n== fortydligande per niva/kortsvar ==")
for niva in "ECA":
    for ks in (True, False):
        g = [r for r in R if r["niva"] == niva and r["kortsvar"] == ks]
        if g: print(niva, ks, sum(r["fortydligande"] for r in g), "/", len(g))
print("\n== steg per poäng per delprov-typ ==")
for ks in (True, False):
    g = [r for r in R if r["kortsvar"] == ks]
    print("kortsvar" if ks else "lösning", "steg/poäng median", st.median([r["steg_per_poang"] for r in g]))
print("\nord_stam per rad:")
for r in R:
    print(f"  {r['termin']} {r['delprov']}{r['nr']}{r['del']:1s} {r['niva']} ord={r['ord_stam']:3d} mfr={r['meningar_fore_fragan']} steg={r['steg']:2d} spp={r['steg_per_poang']} max={r['max_heltal']} dec={r['decimaler']} {r['fragverb']}")
