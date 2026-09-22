import json, statistics, collections
d = json.load(open("1c.json", encoding="utf-8"))
U = [r for r in d["uppgifter"] if r["ord_stam"] is not None]
def p90(xs):
    xs = sorted(xs); 
    if not xs: return None
    k = 0.9*(len(xs)-1); i = int(k); 
    return round(xs[i] + (xs[min(i+1,len(xs)-1)]-xs[i])*(k-i), 1)
def med(xs): return statistics.median(xs) if xs else None
print("== per (niva, kortsvar): n, median/p90 ord_stam, mff, konstanter, steg, steg_per_poang")
for niva in "ECA":
    for ks in (True, False):
        g = [r for r in U if r["niva"]==niva and r["kortsvar"]==ks]
        if not g: continue
        f = lambda k: [r[k] for r in g if r[k] is not None]
        print(niva, "kortsvar" if ks else "lösning", "n=%d"%len(g),
              "ord %s/%s"%(med(f("ord_stam")), p90(f("ord_stam"))),
              "mff %s/%s"%(med(f("meningar_fore_fragan")), p90(f("meningar_fore_fragan"))),
              "konst %s/%s"%(med(f("konstanter")), p90(f("konstanter"))),
              "steg %s/%s"%(med(f("steg")), p90(f("steg"))),
              "spp %s/%s"%(med(f("steg_per_poang")), p90(f("steg_per_poang"))))
print("== per niva (alla)")
for niva in "ECA":
    g = [r for r in U if r["niva"]==niva]
    f = lambda k: [r[k] for r in g if r[k] is not None]
    print(niva, "n=%d"%len(g), "ord %s/%s"%(med(f("ord_stam")), p90(f("ord_stam"))), "steg %s/%s"%(med(f("steg")), p90(f("steg"))),
          "spp %s/%s"%(med(f("steg_per_poang")), p90(f("steg_per_poang"))), "kortsvar", sum(r["kortsvar"] for r in g), "flerval", sum(r["flerval"] for r in g))
print("== fragverb per niva")
for niva in "ECA":
    c = collections.Counter(r["fragverb"] for r in U if r["niva"]==niva)
    print(niva, dict(c.most_common()))
print("== motivera per termin/niva")
for t in ("vt17","vt22"):
    g=[r for r in U if r["termin"]==t]
    print(t, "motivera", [(r["delprov"],r["nr"],r["niva"]) for r in g if r["motivera"]], "sanning!=ej", [(r["delprov"],r["nr"],r["niva"],r["sanning"]) for r in g if r["sanning"]!="ej"])
print("== fortydligande per niva", {n: (sum(r["fortydligande"] for r in U if r["niva"]==n), len([r for r in U if r["niva"]==n])) for n in "ECA"})
print("== metodforeskrift", [(r["termin"],r["delprov"],r["nr"],r["del"],r["niva"]) for r in U if r["metodforeskrift"]])
print("== svarsform", [(r["termin"],r["delprov"],r["nr"],r["niva"],r["svarsform_instruktion"]) for r in U if r["svarsform_instruktion"]])
print("== konstanter>0", [(r["termin"],r["delprov"],r["nr"],r["niva"],r["konstanter"]) for r in U if r["konstanter"]])
print("== kontext per niva")
for niva in "ECA":
    print(niva, dict(collections.Counter(r["kontext"] for r in U if r["niva"]==niva)))
print("== innehall per niva")
for niva in "ECA":
    print(niva, dict(collections.Counter(r["innehall"] for r in U if r["niva"]==niva).most_common()))
print("== representation")
for niva in "ECA":
    c = collections.Counter()
    for r in U:
        if r["niva"]==niva:
            for x in r["representation"]: c[x]+=1
    print(niva, dict(c))
print("== tal: max_heltal utan/med räknare per termin")
for t in ("vt17","vt22"):
    for calc in (False, True):
        dps = [dp["namn"] for dp in next(p for p in d["prov"] if p["termin"]==t)["delprov"] if dp["hjalpmedel_raknare"]==calc]
        g = [r for r in U if r["termin"]==t and r["delprov"] in dps and r["max_heltal"] is not None]
        xs = sorted(r["max_heltal"] for r in g)
        decs = [r["decimaler"] for r in U if r["termin"]==t and r["delprov"] in dps]
        print(t, "räknare" if calc else "utan", dps, "n=%d"%len(g), "min/med/max", xs[0] if xs else None, med(xs), xs[-1] if xs else None, "decimaler max", max(decs) if decs else None, "andel med decimaler", sum(1 for x in decs if x)/len(decs) if decs else None)
print("== per delprov: poäng, andel, enheter, enheter per 10 min, uppgiftsnummer per 10 min")
for p in d["prov"]:
    for dp in p["delprov"]:
        if dp["tid_min"] is None: continue
        g = [r for r in d["uppgifter"] if r["termin"]==p["termin"] and r["delprov"]==dp["namn"]]
        tot = sum(dp["poang"])
        nrs = len(set(r["nr"] for r in g))
        print(p["termin"], dp["namn"], dp["poang"], "andel E/C/A", [round(x/tot,2) for x in dp["poang"]], "enheter", len(g), "per10min", round(len(g)/dp["tid_min"]*10,2), "uppg", nrs, "per10min", round(nrs/dp["tid_min"]*10,2), "poäng/10min", round(tot/dp["tid_min"]*10,2))
print("== delade med 1a")
sh = [r for r in d["uppgifter"] if r["delad_med_1a"]]
only = [r for r in d["uppgifter"] if r["delad_med_1a"] is False]
def psum(rows): 
    s=[0,0,0]
    for r in rows:
        for i in range(3): s[i]+=r["poang"][i]
    return s
print("delade n=%d poäng %s ; bara 1c n=%d poäng %s"%(len(sh), psum(sh), len(only), psum(only)))
for t in ("vt17","vt22"):
    print(t, "delade", psum([r for r in sh if r["termin"]==t]), "bara1c", psum([r for r in only if r["termin"]==t]))
print("delade niva", dict(collections.Counter(r["niva"] for r in sh)), "bara1c niva", dict(collections.Counter(r["niva"] for r in only)))
print("delade innehall", dict(collections.Counter(r["innehall"] for r in sh).most_common()))
print("bara1c innehall", dict(collections.Counter(r["innehall"] for r in only).most_common()))
print("delade kontext", dict(collections.Counter(r["kontext"] for r in sh)), "bara1c kontext", dict(collections.Counter(r["kontext"] for r in only)))
print("delade konst>0", sum(1 for r in sh if r["konstanter"]), "bara1c konst>0", sum(1 for r in only if r["konstanter"]))
print("delade repr formel", sum(1 for r in sh if "formel" in r["representation"]), len(sh), "bara1c", sum(1 for r in only if "formel" in r["representation"]), len(only))
print("delade ord med", med([r["ord_stam"] for r in sh if r["ord_stam"]]), "bara1c", med([r["ord_stam"] for r in only if r["ord_stam"]]))
print("delade steg med", med([r["steg"] for r in sh if r["steg"]]), "bara1c", med([r["steg"] for r in only if r["steg"]]))
print("olika poäng", [(r["termin"],r["delprov"],r["nr"],r["del"],r["poang"],r["poang_1a"]) for r in sh if r["poang"]!=r["poang_1a"]])
print("bara1c lista", [(r["termin"],r["delprov"],r["nr"],r["del"],r["niva"],r["innehall"]) for r in only])
