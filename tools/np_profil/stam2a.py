"""Maskinell ordräkning av uppgiftsstammar i NP Ma2a (vt17, vt18, vt22).
Skriver stam_<termin>.json med {nyckel: {ord, meningar_fore, max_heltal, decimaler, text}}.
text används bara för egen kontroll, aldrig i utdata."""
import re, json, sys, os
BASE = r"C:\Users\bolun\Downloads\Skola & kursmaterial\Nationella prov matte (bilder)\np-korpus\2a"
OUT = os.path.dirname(os.path.abspath(__file__))
FILES = {"vt17": "vt17/Ma2a-vt17.txt", "vt18": "vt18/Ma2a-vt18.txt", "vt22": "vt22/Ma2a-vt22.txt"}

SKIP = re.compile(r"^(NpMa2a|=====|Delprov [BCD]:|elevhäftet|Endast svar krävs|_+|\d{1,2}\s*$|Provtid|Hjälpmedel|Skriv dina)")
UPPG = re.compile(r"^(\d{1,2})\.\s*$")
DEL = re.compile(r"^([a-d])\)\s*$")
POANG = re.compile(r"\((\d)/(\d)/(\d)\)")
VERB = re.compile(r"\b(Bestäm|Beräkna|Lös|Ange|Visa|Undersök|Avgör|Förklara|Rita|Skissa|Markera|Fyll|Ställ|Teckna|Tolka|Ge |Utred|Förenkla|Vilket|Vilken|Vilka|Har |Stämmer|Går det|Välj|Fortsätt|Använd grafen)")

def words(t):
    toks = re.findall(r"[A-Za-zÅÄÖåäöÉé]+(?:-[A-Za-zÅÄÖåäö]+)?", t)
    return [w for w in toks if len(w) >= 2 or w in ("i", "å")]

def sentences(t):
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"(\d)[.,](\d)", r"\1_\2", t)
    t = t.replace("t.ex.", "tex").replace("d.v.s.", "dvs").replace("kr/m2", "kr per m2")
    parts = [p.strip() for p in re.split(r"(?<=[.?!:])\s+(?=[A-ZÅÄÖ•])", t) if p.strip()]
    return parts

def numbers(t):
    t2 = re.sub(r"(\d) (\d{3})\b", r"\1\2", t)
    ints = [int(x) for x in re.findall(r"(?<![\d,])\d+(?![\d,])", t2)]
    ints = [x for x in ints if x < 3000 or x >= 1000]  # behåll allt
    decs = [len(d) for d in re.findall(r"\d+,(\d+)", t2)]
    return (max(ints) if ints else None), (max(decs) if decs else 0)

def parse(path):
    lines = open(path, encoding="utf-8").read().split("\n")
    end = next(i for i, l in enumerate(lines) if l.startswith("Innehållsförteckning"))
    lines = lines[:end]
    units = {}
    cur = None; ingress = []; seg = []; part = None; in_ingress = False; cover = False
    for raw in lines:
        l = raw.strip()
        if not l or (SKIP.match(l) and not POANG.search(l)):
            continue
        if re.match(r"^Delprov D\s*$", l):
            cover = True
        m = UPPG.match(l)
        if m and int(m.group(1)) == (1 if cur is None else cur + 1):
            cur = int(m.group(1)); ingress = []; seg = []; part = None; in_ingress = True; cover = False
            continue
        if cover:
            continue
        if cur is None:
            continue
        d = DEL.match(l)
        if d:
            part = d.group(1); in_ingress = False
            continue
        p = POANG.search(l)
        if p:
            pre = POANG.sub("", l).replace("_", "").strip()
            if pre:
                seg.append(pre)
            key = f"{cur}{part or ''}"
            text = " ".join(ingress + seg)
            units[key] = text
            seg = []
            continue
        if in_ingress:
            ingress.append(l)
        else:
            seg.append(l)
    return units

def fore(text):
    s = sentences(text)
    for i, p in enumerate(s):
        if VERB.search(p):
            return i, len(s)
    return None, len(s)

if __name__ == "__main__":
    for termin, rel in FILES.items():
        units = parse(os.path.join(BASE, rel))
        out = {}
        for k, t in units.items():
            mh, dec = numbers(t)
            f, n = fore(t)
            out[k] = {"ord": len(words(t)), "meningar_fore": f, "meningar_tot": n,
                      "max_heltal": mh, "decimaler": dec, "text": t}
        json.dump(out, open(os.path.join(OUT, f"stam_{termin}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(termin, len(out), "enheter")
        for k, v in out.items():
            print(f"  {k:4} ord={v['ord']:3} fore={v['meningar_fore']} tot={v['meningar_tot']} max={v['max_heltal']} dec={v['decimaler']}")
