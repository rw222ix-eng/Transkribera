import fitz, glob, json
src = glob.glob("C:/Users/bolun/Downloads/Skola & kursmaterial/Nationella prov matte (bilder)/np-korpus/1c/vt17/*anvisningar*2.pdf")[0]
doc = fitz.open(src)
page = doc[42]
words = page.get_text("words")
names = ["B","P","PL","M","R","K"]
hdrs = sorted([w for w in words if w[4] in ("Begrepp","Procedur","Problemlösning","Modellering","Resonemang","Kommunikation")], key=lambda w: w[0])
print([(w[4][:3], round(w[0]), round(w[2])) for w in hdrs])
# also find 'Uppg.' / 'Nivå' columns to split left/right
splits = sorted([w for w in words if w[4] in ("Uppg.","Nivå","Poäng")], key=lambda w: w[0])
print([(w[4], round(w[0])) for w in splits])
cols = [((w[0]+w[2])/2, names[i % 6]) for i, w in enumerate(hdrs)]
mid = (cols[5][0] + cols[6][0]) / 2 if len(cols) >= 12 else 9999
rows = {}
for w in words:
    y = round((w[1]+w[3])/2)
    rows.setdefault(y, []).append(w)
out = {}
for y in sorted(rows):
    ws = sorted(rows[y], key=lambda w: w[0])
    left = [w for w in ws if (w[0]+w[2])/2 < mid]
    right = [w for w in ws if (w[0]+w[2])/2 >= mid]
    for side in (left, right):
        toks = [w[4] for w in side if w[4] != "X"]
        xs = [w for w in side if w[4] == "X"]
        if not toks or not xs: continue
        labs = []
        for x in xs:
            cx = (x[0]+x[2])/2
            labs.append(min(cols, key=lambda c: abs(c[0]-cx))[1])
        print(toks, labs)
