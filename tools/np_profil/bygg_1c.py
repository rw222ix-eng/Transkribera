# -*- coding: utf-8 -*-
"""Bygger 1c.json ur häftenas textlager (maskinella mått) + handdomar (M-tabellen).
Ingen provtext skrivs ut; bara mått."""
import re, json, statistics, os
S = os.path.dirname(os.path.abspath(__file__))

NOISE = re.compile(r"^(DIGITALA VERKTYG|NpMa1c|===== PAGE|©|Svar:|Svar :|Endast svar krävs|Redovisa din lösning|Ringa in ditt|Fler uppgifter|Källa:|Figuren är ej|Skissen är inte|Skissen är ej|Borttagen)|^\d+\s*$|^[a-e]\)\s*$|^\(\d/\d/\d\)|^(min|kr|%|°F|dl) \(\d/\d/\d\)")
POANG = re.compile(r"\((\d)/(\d)/(\d)\)")
DELUPP = re.compile(r"^([a-e])\)\s*(.*)$")
TASK = re.compile(r"^(\d{1,2})\.\s*(.*)$")
IMPER = ("Beräkna","Bestäm","Lös","Rita","Skriv","Ange","Undersök","Visa","Förenkla","Faktorisera",
         "Addera","Hitta","Avläs","Använd","Skugga","Motivera","Ringa","Utgå","Fyll")

def words(line):
    return [w for w in re.findall(r"[A-Za-zÅÄÖåäöé]{2,}", line)]

def read_hafte(termin, delprov):
    with open(os.path.join(S, f"h_{termin}_{delprov}.txt"), encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f]
    # klipp bort allt före första uppgiftsraden och efter sista poängraden
    tasks = {}
    cur = None
    for ln in lines:
        m = TASK.match(ln)
        if m and (not cur or int(m.group(1)) == cur + 1 or int(m.group(1)) > cur):
            n = int(m.group(1))
            if n > 40: continue
            cur = n
            tasks[cur] = [m.group(2)] if m.group(2) else []
            continue
        if cur is not None:
            if ln.startswith("Formulär") or ln.startswith("Elevens namn"):
                break
            tasks[cur].append(ln)
    return tasks

def split_units(tlines, nosplit=False):
    """-> dict del -> (textrader, poäng). Ingress = rader före första a)."""
    units = {}
    ingress = []
    seg = None
    bridge = []
    after_poang = False
    for ln in tlines:
        m = DELUPP.match(ln)
        if m and not nosplit:
            seg = m.group(1)
            units[seg] = {"lines": bridge + ([m.group(2)] if m.group(2) else []), "poang": None}
            bridge = []
            after_poang = False
            continue
        pm = POANG.search(ln)
        if pm:
            p = [int(pm.group(i)) for i in (1,2,3)]
            if seg is None:
                units[""] = {"lines": ingress, "poang": p}
                ingress = []
            else:
                units[seg]["poang"] = p
            after_poang = True
            continue
        if seg is None:
            ingress.append(ln)
        elif after_poang:
            bridge.append(ln)
        else:
            units[seg]["lines"].append(ln)
    if "" in units and units[""]["poang"] is None:
        units[""]["poang"] = None
    return ingress if seg else [], units

def measure(text_lines):
    clean = [l for l in text_lines if not NOISE.match(l.strip()) and words(l)]
    text = " ".join(clean)
    ord_stam = len(re.findall(r"[A-Za-zÅÄÖåäö0-9°%‰][A-Za-zÅÄÖåäö0-9°%‰,.:/-]*", text))
    # meningar före frågan
    sents = [s.strip() for s in re.split(r"(?<=[.?!])\s+", text) if s.strip()]
    k = None
    for i, s in enumerate(sents):
        if "?" in s or s.split(" ")[0].rstrip(",") in IMPER or s.startswith("Hur ") or s.startswith("Vilk"):
            k = i; break
    mff = k if k is not None else None
    # tal
    nums = []
    for tok in re.findall(r"\d{1,3}(?: \d{3})+|\d+(?:,\d+)?", text):
        nums.append(tok)
    vals = []
    decs = 0
    for t in nums:
        t2 = t.replace(" ", "")
        if "," in t2:
            decs = max(decs, len(t2.split(",")[1]))
            vals.append(float(t2.replace(",", ".")))
        else:
            vals.append(int(t2))
    max_tal = max(vals) if vals else None
    max_heltal = int(max_tal) if max_tal is not None else None
    return dict(ord_stam=ord_stam, meningar_fore_fragan=mff, max_heltal=max_heltal, decimaler=decs, _sents=len(sents))

# ---------------------------------------------------------------- handdomar
# formaga: ur provsammanställningen (vt17, PDF-kolumner lästa maskinellt); vt22 saknar tabellen -> None
def M(formaga, kortsvar, flerval, fragverb, motivera, svarsform, konstanter, sanning, steg, kontext, repr_, innehall,
      metod, fortyd, form, avg, delad, poang_1a, **extra):
    d = dict(formaga=formaga, kortsvar=kortsvar, flerval=flerval, fragverb=fragverb, motivera=motivera,
             svarsform_instruktion=svarsform, konstanter=konstanter, sanning=sanning, steg=steg, kontext=kontext,
             representation=repr_, innehall=innehall, metodforeskrift=metod, fortydligande=fortyd,
             form_parafras=form, avgorande_steg=avg, delad_med_1a=delad, poang_1a=poang_1a)
    d.update(extra)
    return d

H = {
# ---------------- vt17 B (utan räknare, 60 min)
"vt17/B/1":  M(["B","P"], True, False, "lös", False, "", 0, "ej", 2, "ren", ["text","formel"], "ekvationer", False, False,
              "lös linjär ekvation med x i båda leden, kortsvar", "korrekt svar", False, None),
"vt17/B/2":  M(["P"], True, False, "addera", False, "", 0, "ej", 1, "ren", ["text","formel"], "vektorer", False, False,
              "addera två vektorer i koordinatform, kortsvar", "korrekt svar", False, None),
"vt17/B/3a": M(["B","P"], True, False, "rita", False, "", 0, "ej", 2, "naturvetenskap", ["text","graf"], "funktioner", False, False,
              "rita graf till linjärt samband ur två givna par", "godtagbart ritad graf", True, [1,0,0]),
"vt17/B/3b": M(["P","M"], True, False, "avläs", False, "", 0, "ej", 1, "naturvetenskap", ["text","graf"], "funktioner", False, False,
              "avläs värde i egen graf, kortsvar", "svar inom intervall", True, [1,0,0]),
"vt17/B/4a": M(["P"], True, False, "beräkna", False, "", 0, "ej", 2, "ren", ["text","formel"], "algebra", False, False,
              "sätt in tal i uttryck med parenteser, kortsvar", "korrekt svar", False, None),
"vt17/B/4b": M(["P","P"], False, False, "bestäm", False, "", 0, "ej", 4, "ren", ["text","formel"], "ekvationer", False, False,
              "sätt uttryck med parenteser lika med tal, lös ekvationen, redovisa", "C: lösning med korrekt svar; E: påbörjad utveckling av parenteser", False, None),
"vt17/B/5":  M(["B","B"], True, True, "vilken", False, "", 0, "ej", 2, "ren", ["text"], "procent", False, False,
              "flerval: vilka enhetsformer (promille, ppm) motsvarar given procentsats", "C: båda rätt och inget fel", True, [1,1,0]),
"vt17/B/6":  M(["P","PL"], True, False, "hur", False, "", 0, "ej", 3, "yrke", ["text","graf"], "funktioner", False, False,
              "läs hastighet ur diagram och räkna om till tid för längre sträcka, kortsvar", "godtagbart svar (tolkning att grafen inte börjar vid ytan)", False, None),
"vt17/B/7":  M(["B"], True, False, "vilken", False, "", 0, "ej", 3, "ren", ["text"], "taluppfattning", False, False,
              "hitta heltal i intervall som uppfyller tre delbarhetsvillkor, kortsvar", "korrekt svar", False, None),
"vt17/B/8":  M(["B"], True, True, "ringa", False, "", 0, "ej", 6, "ren", ["text","formel"], "potenser", False, False,
              "flerval: markera de potenser som har samma värde", "korrekt svar", True, [0,1,0]),
"vt17/B/9":  M(["B"], True, False, "vilken", False, "", 0, "ej", 2, "ren", ["text","formel"], "algebra", False, False,
              "värde av uttryck ur ett givet samband utan att lösa ut x, kortsvar", "korrekt svar", True, [0,1,0]),
"vt17/B/10": M(["B","PL"], True, False, "hur", False, "", 0, "ej", 2, "vardag", ["text","figur"], "taluppfattning", False, False,
              "tolka bild som binärt tal och räkna om till bas tio, kortsvar", "korrekt svar", False, None),
"vt17/B/11": M(["B","B","B","K"], True, False, "rita", False, "", 0, "ej", 3, "ren", ["text","formel","graf"], "funktioner", False, False,
              "rita en graf som uppfyller villkor på definitionsmängd, värdemängd och ett nollställe", "A: alla tre villkor uppfyllda", False, None),
"vt17/B/12": M(["PL"], True, False, "hitta", False, "", 0, "ej", 2, "ren", ["text","formel"], "ekvationer", False, True,
              "hitta lösning till linjär ekvation i två variabler med extra villkor, kortsvar", "korrekt svar", True, [0,0,1]),
"vt17/B/13": M(["PL","PL","K"], False, True, "vilken", True, "", 0, "ej", 3, "ren", ["text","formel"], "trigonometri", False, False,
              "flerval med motivering: sinus för minsta vinkeln ur två kateter", "A: korrekt svar med redovisning tydligt kopplad till triangeln",
              False, None, anm="katetlängderna saknas i textlagret; max_heltal osäkert"),
"vt17/B/14": M(["B","PL","P"], False, False, "rita", False, "", 0, "ej", 3, "ren", ["text","figur","formel"], "vektorer", False, False,
              "rita vektor som uppfyller given linjärkombination i rutnät, redovisa", "A: storlek och riktning framgår tydligt", False, None),
"vt17/B/15": M(["B","P","PL"], False, False, "lös", False, "", 0, "ej", 3, "ren", ["formel","text"], "potenser", False, False,
              "lös ekvation med potenser via potenslagarna, redovisa", "A: lösning med korrekt svar", False, None,
              anm="ekvationen saknas i textlagret; steg uppskattat ur anvisningen"),
# ---------------- vt17 C (räknare tillåten, 60 min, en stor uppgift, matris)
"vt17/C/16": M(["B","P","PL","R","K"], False, False, "vad", False, "", 0, "ej", 8, "vardag", ["text","figur"], "sannolikhet", False, True,
              "spelregler för två tärningar; fem delfrågor från enkel sannolikhet till förväntat värde",
              "A: sannolikhet för summa över två omgångar, genomsnittlig poängökning, resonemang om att totalen växer", True, [4,4,4],
              anm="matris, en rad; förmågor är unionen över tolv poäng; stegen räknade över alla delfrågor"),
# ---------------- vt17 D (räknare, 120 min)
"vt17/D/17": M(["B","P","PL","K"], False, False, "beräkna", False, "", 0, "ej", 2, "yrke", ["text","figur"], "trigonometri", False, False,
              "höjd ur avstånd och vinkel i figur, lägg till instrumenthöjd", "E2: godtagbart svar efter katetberäkning", False, None,
              anm="talen står i figuren, inte i texten; max_heltal saknas"),
"vt17/D/18a": M(["P","M"], True, False, "vilken", False, "", 0, "ej", 1, "naturvetenskap", ["text","formel"], "funktioner", False, False,
              "sätt in tal i given formel, kortsvar", "godtagbart svar", True, [1,0,0]),
"vt17/D/18b": M(["P","M","P"], False, False, "vilken", False, "", 0, "ej", 2, "naturvetenskap", ["text","formel"], "ekvationer", False, False,
              "lös ut variabel ur given formel för givet värde", "C: lösning med korrekt svar", True, [1,1,0]),
"vt17/D/19a": M(["P"], True, False, "vilken", False, "", 0, "ej", 1, "vardag", ["text","graf"], "statistik", False, False,
              "avläs årtal i linjediagram, kortsvar", "godtagbart svar", False, None),
"vt17/D/19b": M(["P","PL","B"], False, False, "hur", False, "", 0, "ej", 3, "vardag", ["text","graf"], "procent", False, False,
              "procentuell förändring mellan två avlästa värden", "C: godtagbart svar efter relevant kvot", False, None),
"vt17/D/19c": M(["M","PL","K"], False, False, "när", False, "", 0, "ej", 3, "vardag", ["text","graf"], "funktioner", False, False,
              "extrapolera linjär ökning ur diagram till givet värde", "C2: godtagbart svar efter årlig ökning", False, None),
"vt17/D/20a": M(["P"], False, False, "hur", False, "", 0, "ej", 2, "vardag", ["text"], "aritmetik", False, False,
              "två priser för given mängd, jämför", "beräkning med korrekt svar", True, [1,0,0]),
"vt17/D/20b": M(["M","K","K"], False, False, "ange", False, "", 0, "ej", 2, "vardag", ["text"], "algebra", False, False,
              "skriv formel för kostnad som funktion av mängd", "C: algebraisk formel med definierade variabler", True, [1,0,0],
              delad_anm="1a ger bara E-poängen (1/0/0); 1c kräver definierade variabler för C"),
"vt17/D/20c": M(["PL","P","K"], False, False, "vilken", False, "", 0, "ej", 3, "vardag", ["text"], "ekvationer", False, False,
              "mängd där två prismodeller (en med rabatt över tröskel) kostar lika", "A: effektiv metod (ekvation) med korrekt svar", True, [0,1,1]),
"vt17/D/21": M(["B","R","B","R"], False, False, "vilken", True, "", 0, "okand", 2, "ren", ["text","figur","formel"], "geometri", False, False,
              "bedöm tre elevlösningar: vilka är bevis av en vinkelsats, motivera", "C2: motiverar både varför den generella är bevis och varför exemplen inte är det", False, None),
"vt17/D/22": M(["B","PL","PL","PL"], False, False, "hur", False, "", 1, "ej", 3, "vardag", ["text"], "procent", False, False,
              "procentuell jämförelse mellan två belopp uttryckta i procent av ett tredje okänt", "A: förhållandet visas generellt (inte bara för ett ansatt värde)", True, [1,1,1]),
"vt17/D/23": M(["B","B","P","R"], False, False, "hur", False, "", 0, "given", 3, "vardag", ["text"], "procent", False, False,
              "förklara hur två ökningar i procentenheter kan vara lika i procent", "A: godtagbart resonemang efter procentuell ökning för båda", True, [1,1,1]),
"vt17/D/24": M(["PL","M","P","PL","M"], False, False, "hur", False, "", 0, "ej", 4, "vardag", ["text","formel"], "ekvationer", False, False,
              "given intäktsformel; lös ekvation och tolka att frågan gäller den andra kvantiteten", "A: rätt tolkning (antalet av den andra sorten)", True, [1,1,1]),
"vt17/D/25": M(["PL","P","R","PL","R","K"], False, False, "undersök", False, "", 0, "okand", 4, "ren", ["text","figur"], "geometri", False, False,
              "undersök ett påstående om att två areor alltid är lika; generell härledning krävs", "A2: visar för alla fall, lätt att följa, godtagbart språk", False, None),
"vt17/D/26a": M(["B","PL","P","K"], False, False, "hur", False, "", 0, "ej", 2, "vardag", ["text","figur"], "procent", False, False,
              "upprepad procentuell minskning, n:te värdet", "C2: godtagbart svar efter förändringsfaktor upprepad", False, None),
"vt17/D/26b": M(["PL","M","P","PL","K"], False, False, "undersök", False, "", 0, "ej", 4, "vardag", ["text","figur"], "procent", False, False,
              "olikhet med exponentiell minskning, antal steg, tolka till total höjd", "A2: rätt antal mellanrum (n-1) och godtagbart svar", False, None),
"vt17/D/27a": M(["M"], False, False, "skriv", False, "", 0, "ej", 1, "vardag", ["text"], "algebra", False, False,
              "översätt tumregel i ord till formel med givna variabelnamn", "korrekt formel", False, None),
"vt17/D/27b": M(["M","P","K"], False, False, "använd", False, "", 0, "ej", 2, "vardag", ["text"], "ekvationer", True, False,
              "sätt in i egen formel och lös ut", "C2: lösning med korrekt svar", False, None),
"vt17/D/27c": M(["M","B","P"], False, False, "använd", False, "två decimaler", 0, "ej", 3, "vardag", ["text"], "potenser", True, False,
              "annan metod än tumregeln: exponentialekvation för fördubbling, svara med decimaler", "A2: korrekt svar efter godtagbar ekvation", False, None),
# ---------------- vt22 B (utan räknare, 60 min, endast svar)
"vt22/B/1":  M(None, True, False, "faktorisera", False, "", 0, "ej", 1, "ren", ["text","formel"], "algebra", True, False,
              "bryt ut största faktor ur tvåtermigt uttryck, kortsvar", "korrekt svar", True, [1,0,0]),
"vt22/B/2":  M(None, True, True, "vilken", False, "", 0, "ej", 2, "ren", ["text","graf","formel"], "funktioner", False, False,
              "flerval: vilken linjär formel hör till graf", "korrekt svar", False, None),
"vt22/B/3":  M(None, True, True, "vilken", False, "", 0, "ej", 2, "vardag", ["text","formel"], "sannolikhet", False, False,
              "flerval: vilken beräkning ger sannolikhet vid två dragningar utan återläggning", "korrekt svar", True, [1,0,0]),
"vt22/B/4":  M(None, True, False, "förenkla", False, "", 1, "ej", 2, "ren", ["formel","text"], "algebra", False, False,
              "förenkla uttryck med bokstav, kortsvar", "korrekt svar", False, None, anm="uttrycket saknas i textlagret"),
"vt22/B/5":  M(None, True, False, "vilken", False, "", 0, "ej", 1, "ren", ["text","graf"], "statistik", False, False,
              "välj spridningsdiagram med starkast korrelation", "korrekt svar", True, [1,0,0]),
"vt22/B/6a": M(None, True, False, "bestäm", False, "", 0, "ej", 1, "ren", ["text","graf","formel"], "funktioner", False, False,
              "avläs funktionsvärde i graf, kortsvar", "korrekt svar", True, [1,0,0]),
"vt22/B/6b": M(None, True, False, "lös", False, "", 0, "ej", 1, "ren", ["text","graf","formel"], "funktioner", False, False,
              "lös f(x)=tal grafiskt, kortsvar", "korrekt svar", True, [0,1,0]),
"vt22/B/7a": M(None, True, False, "skriv", False, "", 0, "ej", 1, "ren", ["text","formel"], "vektorer", False, False,
              "summa av två vektorer i koordinatform, kortsvar", "korrekt svar", False, None),
"vt22/B/7b": M(None, True, False, "bestäm", False, "", 0, "ej", 2, "ren", ["text","formel"], "vektorer", False, False,
              "belopp av vektor, exakt rotuttryck, kortsvar", "korrekt svar (exakt)", False, None),
"vt22/B/8":  M(None, True, True, "ange", False, "", 0, "ej", 4, "vardag", ["text","tabell"], "funktioner", False, False,
              "kryssa modelltyp (linjär, exponentiell, potens) för fyra beskrivna situationer", "C2: samtliga rätt", True, [0,2,0],
              delad_anm="1a har två modelltyper och en annan situation; 1c lägger till potensmodell"),
"vt22/B/9":  M(None, True, True, "vilken", False, "", 0, "ej", 1, "ren", ["text","formel"], "trigonometri", False, False,
              "flerval: vilket trigonometriskt uttryck har samma värde som givet sinusvärde", "korrekt svar", False, None),
"vt22/B/10": M(None, True, False, "skriv", False, "", 0, "ej", 2, "ren", ["formel","text"], "algebra", False, False,
              "fyll i tom parentes så att likhet gäller, kortsvar", "korrekt svar", True, [0,1,0]),
"vt22/B/11": M(None, True, False, "hur", False, "", 0, "ej", 2, "ren", ["text","formel"], "sannolikhet", False, False,
              "baklänges: antal utfall ur given sannolikhet för tre lika i rad", "korrekt svar", False, None),
"vt22/B/12": M(None, True, False, "skriv", False, "", 1, "ej", 2, "ren", ["text","formel"], "algebra", False, False,
              "uttryck en linjärkombination i en variabel via givet samband, förenkla", "korrekt svar", True, [0,0,1]),
"vt22/B/13": M(None, True, False, "bestäm", False, "", 0, "ej", 2, "ren", ["formel","text"], "funktioner", False, False,
              "sammansatt funktion i en punkt, kortsvar", "korrekt svar", True, [0,0,1]),
"vt22/B/14": M(None, True, False, "vilken", False, "", 1, "ej", 3, "ren", ["formel","text"], "potenser", False, False,
              "fyll i tal i rutor så att potens-/rotlikheter stämmer för samma positiva a", "korrekt svar", False, None,
              anm="likheterna saknas i textlagret; steg uppskattat"),
"vt22/B/15": M(None, True, False, "bestäm", False, "", 1, "ej", 2, "ren", ["text","formel"], "olikheter", False, False,
              "bestäm parameter i olikhet så att lösningsmängden blir given", "korrekt svar", False, None),
"vt22/B/16": M(None, True, False, "skugga", False, "", 0, "ej", 2, "ren", ["text","graf","formel"], "funktioner", False, False,
              "skugga område mellan två grafer", "korrekt skuggat område", False, None),
# ---------------- vt22 C (utan räknare, 60 min, redovisning)
"vt22/C/17": M(None, False, False, "beräkna", False, "", 0, "ej", 7, "ren", ["text","figur","formel"], "potenser", False, True,
              "geometriskt mönster: omkretsar, förändringsfaktor, exakt formel, hitta n ur given omkrets",
              "A: exakt formel i redovisningen; basbyte för att bestämma n", True, [3,2,2],
              delad_anm="1a saknar sista delfrågan (hitta n) och har (3/2/2)", anm="matris, en rad; formaga saknas i häftet vt22"),
"vt22/C/18": M(None, False, False, "bestäm", False, "", 0, "ej", 3, "ren", ["text","formel"], "funktioner", False, False,
              "räta linjens ekvation genom två punkter", "E2: lösning med korrekt svar", False, None),
"vt22/C/19": M(None, False, False, "bestäm", False, "", 0, "ej", 3, "ren", ["text","formel"], "ekvationer", False, False,
              "sätt uttryck med parenteser lika med tal, lös (bråksvar)", "C: lösning med korrekt svar", False, None),
"vt22/C/20": M(None, False, False, "lös", False, "", 0, "ej", 3, "ren", ["formel","text"], "ekvationer", False, False,
              "ekvation med produkt av parenteser där kvadrattermerna tar ut varandra", "C2: lösning med korrekt svar", True, [0,2,0]),
"vt22/C/21a": M(None, False, False, "bestäm", False, "", 0, "ej", 2, "yrke", ["text"], "funktioner", False, False,
              "skriv en storhet som funktion av en annan ur areaformel", "lösning med korrekt svar", True, [0,1,0]),
"vt22/C/21b": M(None, False, False, "bestäm", False, "", 0, "ej", 3, "yrke", ["text"], "funktioner", False, False,
              "definitionsmängd ur villkor på funktionsvärdet", "A: intervall med symboler, båda gränser, rätt strikthet", False, None),
# ---------------- vt22 D (räknare, 120 min)
"vt22/D/22a": M(None, True, False, "vilken", False, "", 0, "ej", 1, "vardag", ["text","formel"], "funktioner", False, False,
              "läs av räntesats ur exponentiell formel, kortsvar", "korrekt svar", True, [1,0,0]),
"vt22/D/22b": M(None, True, False, "beräkna", False, "", 0, "ej", 1, "vardag", ["text","formel"], "funktioner", False, False,
              "funktionsvärde ur exponentiell formel, kortsvar", "godtagbart svar", True, [1,0,0]),
"vt22/D/23a": M(None, False, False, "hur", False, "", 0, "ej", 2, "yrke", ["text","figur"], "trigonometri", False, False,
              "hypotenusa ur katet och vinkel", "E2: godtagbart svar efter trigonometriskt samband", False, None),
"vt22/D/23b": M(None, False, False, "hur", False, "", 0, "ej", 2, "yrke", ["text","figur"], "trigonometri", False, False,
              "andra kateten ur vinkel och katet (eller Pythagoras)", "C2: godtagbart svar efter tecknad ekvation", False, None),
"vt22/D/24a": M(None, True, False, "vilken", False, "", 0, "ej", 2, "vardag", ["text","tabell"], "procent", False, False,
              "räkna ut cellvärde i kalkylblad (ränta plus amortering), kortsvar", "korrekt svar", True, [1,0,0]),
"vt22/D/24b": M(None, True, False, "vilken", False, "", 0, "ej", 1, "vardag", ["text","tabell"], "algebra", False, False,
              "skriv kalkylbladsformel med cellreferenser, kortsvar", "fungerande formel", True, [1,0,0]),
"vt22/D/24c": M(None, True, False, "vilken", False, "", 0, "ej", 1, "vardag", ["text","tabell"], "algebra", False, False,
              "skriv kalkylbladsformel med två cellreferenser och produkt, kortsvar", "fungerande formel", True, [0,1,0]),
"vt22/D/25": M(None, False, False, "bestäm", False, "", 0, "ej", 3, "ren", ["text"], "procent", False, False,
              "tre vinklar givna som procent av varandra; ekvation ur vinkelsumma", "C3: korrekt svar efter samband/ekvation", True, [0,3,0]),
"vt22/D/26": M(None, False, False, "hur", False, "", 0, "ej", 3, "naturvetenskap", ["text","formel"], "potenser", False, False,
              "jämför två givna modeller (potens och linjär) i procent för ett värde", "C2: godtagbart svar efter tecknad kvot", False, None),
"vt22/D/27": M(None, False, False, "hur", False, "", 0, "ej", 3, "vardag", ["text"], "procent", False, False,
              "genomsnittlig procentuell förändring per år ur start, slut och antal år", "C2: godtagbart svar efter ekvation/uttryck", False, None),
"vt22/D/28": M(None, None, None, None, None, None, None, None, None, None, None, None, None, None,
              "borttagen på grund av sekretess", None, None, None, anm="uppgiften saknas; poäng ur sammanställningsformuläret"),
"vt22/D/29a": M(None, False, False, "hur", False, "", 0, "ej", 1, "vardag", ["text"], "sannolikhet", False, False,
              "sannolikhet för två oberoende vinster i rad", "lösning med korrekt svar", True, [1,0,0]),
"vt22/D/29b": M(None, False, False, "hur", False, "", 0, "ej", 3, "vardag", ["text"], "sannolikhet", False, False,
              "minst en vinst på n försök via komplementhändelse", "A: godtagbart svar efter komplement", True, [0,2,1]),
"vt22/D/30a": M(None, False, False, "använd", False, "", 0, "ej", 2, "vardag", ["text","formel"], "funktioner", True, False,
              "sätt in tre värden i given formel med bråk", "C: godtagbart svar utifrån formeln", True, [1,1,0],
              anm="formeln saknas i textlagret"),
"vt22/D/30b": M(None, False, False, "vilken", False, "", 0, "ej", 4, "vardag", ["text","formel"], "ekvationer", False, False,
              "given formel; två okända med relation, lös ekvationen i en variabel", "A2: korrekt svar (båda hastigheterna)", True, [0,1,2]),
"vt22/D/31": M(None, False, False, "bestäm", False, "", 1, "ej", 4, "ren", ["text"], "procent", False, False,
              "tal som är p % större än ett tal och p % mindre än ett annat; två ekvationer", "A3: korrekt svar där p används i procentform", True, [0,0,3]),
"vt22/D/32": M(None, False, False, "bestäm", False, "exakt", 1, "ej", 4, "ren", ["text","figur"], "geometri", False, False,
              "exakt uttryck i r för area mellan inskrivna figurer, förenkla", "A3: korrekt förenklat uttryck", False, None),
}

NOSPLIT = {("vt17","C",16), ("vt22","C",17)}
PROV = {
 "vt17": {"delprov": [
    {"namn":"A","uppgifter":"muntlig gruppuppgift (ej i korpusen)","poang":[3,4,3],"tid_min":None,"hjalpmedel_raknare":None},
    {"namn":"B","uppgifter":"1-15","poang":[8,10,7],"tid_min":60,"hjalpmedel_raknare":False},
    {"namn":"C","uppgifter":"16","poang":[4,4,4],"tid_min":60,"hjalpmedel_raknare":True},
    {"namn":"D","uppgifter":"17-27","poang":[11,19,10],"tid_min":120,"hjalpmedel_raknare":True}],
   "total":[26,37,24], "kravgranser":{"E":[19,None,None],"D":[32,12,None],"C":[43,22,None],"B":[55,None,7],"A":[66,None,13]}},
 "vt22": {"delprov": [
    {"namn":"B","uppgifter":"1-16","poang":[7,7,5],"tid_min":60,"hjalpmedel_raknare":False},
    {"namn":"C","uppgifter":"17-21","poang":[6,7,5],"tid_min":60,"hjalpmedel_raknare":False},
    {"namn":"D","uppgifter":"22-32 (28 borttagen)","poang":[8,16,9],"tid_min":120,"hjalpmedel_raknare":True}],
   "total":[21,30,19], "kravgranser":{"E":[14,None,None],"D":[27,12,None],"C":[35,18,None],"B":[46,None,6],"A":[55,None,11]}},
}

rows = []
for termin in ("vt17","vt22"):
    for dp in ("B","C","D"):
        tasks = read_hafte(termin, dp)
        for nr, tl in sorted(tasks.items()):
            ns = (termin, dp, nr) in NOSPLIT
            ingress, units = split_units(tl, nosplit=ns)
            if ns:
                # allt är en enhet; poängraden ligger tidigt (rubrikraden)
                units = {"": {"lines": tl, "poang": next([int(POANG.search(l).group(i)) for i in (1,2,3)] for l in tl if POANG.search(l))}}
                ingress = []
            for del_, u in units.items():
                key = f"{termin}/{dp}/{nr}{del_}"
                h = H.get(key)
                if h is None:
                    print("SAKNAR HANDDOM", key); continue
                m = measure(ingress + u["lines"])
                p = u["poang"]
                if key == "vt22/D/28":
                    p = [0,2,0]; m = dict(ord_stam=None, meningar_fore_fragan=None, max_heltal=None, decimaler=None)
                if p is None:
                    print("SAKNAR POÄNG", key)
                niva = "A" if p[2] else ("C" if p[1] else "E")
                r = dict(termin=termin, delprov=dp, nr=nr, del_=del_, poang=p, niva=niva)
                r.update({k: v for k, v in h.items()})
                r["ord_stam"] = m["ord_stam"]; r["meningar_fore_fragan"] = m["meningar_fore_fragan"]
                r["max_heltal"] = m["max_heltal"]; r["decimaler"] = m["decimaler"]
                if h.get("steg") is not None:
                    r["steg_per_poang"] = round(h["steg"] / sum(p), 2)
                else:
                    r["steg_per_poang"] = None
                rows.append(r)

r28 = dict(termin="vt22", delprov="D", nr=28, del_="", poang=[0,2,0], niva="C")
r28.update(H["vt22/D/28"]); r28.update(dict(ord_stam=None, meningar_fore_fragan=None, max_heltal=None, decimaler=None, steg_per_poang=None))
rows.insert([i for i,r in enumerate(rows) if r["termin"]=="vt22" and r["delprov"]=="D" and r["nr"]==29][0], r28)
# manuella justeringar av maskinmått där textlagret tappat tal
ADJ = {"vt17/B/13": {"max_heltal": None}, "vt17/B/8": {"max_heltal": 5},
       "vt17/B/4a": {"meningar_fore_fragan": 1}, "vt17/B/4b": {"meningar_fore_fragan": 1}, "vt17/B/14": {"meningar_fore_fragan": 1},
       "vt22/B/6a": {"meningar_fore_fragan": 1}, "vt22/B/6b": {"meningar_fore_fragan": 1},
       "vt22/B/7a": {"meningar_fore_fragan": 1, "max_heltal": 3}, "vt22/B/7b": {"meningar_fore_fragan": 1, "max_heltal": 3},
       "vt22/B/10": {"max_heltal": 10}, "vt22/B/11": {"meningar_fore_fragan": 3, "max_heltal": 64},
       "vt22/B/13": {"meningar_fore_fragan": 1}, "vt22/B/14": {"max_heltal": 9},
       "vt22/C/17": {"meningar_fore_fragan": 7}, "vt22/C/19": {"meningar_fore_fragan": 1},
       "vt22/D/22a": {"max_heltal": 10000, "decimaler": 2}, "vt22/D/22b": {"max_heltal": 10000, "decimaler": 2},
       "vt22/D/24c": {"meningar_fore_fragan": 4}, "vt22/D/30a": {"meningar_fore_fragan": 4}, "vt22/D/30b": {"meningar_fore_fragan": 7},
       "vt17/B/13": {"max_heltal": None}, "vt17/D/17": {"max_heltal": None}, "vt22/B/4": {"max_heltal": None},
       "vt22/B/16": {"max_heltal": None}, "vt17/D/25": {"max_heltal": None}, "vt22/D/32": {"max_heltal": None},
       "vt17/B/14": {"max_heltal": 2}, "vt17/B/15": {"max_heltal": 36}}
for r in rows:
    key = f"{r['termin']}/{r['delprov']}/{r['nr']}{r['del_']}"
    for k, v in ADJ.get(key, {}).items():
        r[k] = v
    r["del"] = r.pop("del_")

# avstämning
for termin in ("vt17","vt22"):
    for dp in ("B","C","D"):
        s = [0,0,0]
        for r in rows:
            if r["termin"] == termin and r["delprov"] == dp:
                for i in range(3): s[i] += r["poang"][i]
        exp = next(d["poang"] for d in PROV[termin]["delprov"] if d["namn"] == dp)
        print(termin, dp, "summa", s, "häftet", exp, "OK" if s == exp else "AVVIKER")

order = ["termin","delprov","nr","del","poang","niva","formaga","kortsvar","flerval","ord_stam","meningar_fore_fragan",
         "fragverb","motivera","svarsform_instruktion","konstanter","sanning","steg","steg_per_poang","kontext",
         "representation","max_heltal","decimaler","innehall","metodforeskrift","fortydligande","form_parafras",
         "avgorande_steg","delad_med_1a","poang_1a","delad_anm","anm"]
out_rows = []
for r in rows:
    o = {k: r[k] for k in order if k in r}
    out_rows.append(o)
with open(os.path.join(S, "1c.json"), "w", encoding="utf-8") as f:
    json.dump({"kurs":"1c","prov":[{"termin":t, **PROV[t]} for t in PROV],"uppgifter":out_rows}, f, ensure_ascii=False, indent=1)
print("rader", len(out_rows))
