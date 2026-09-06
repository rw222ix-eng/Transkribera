"""Seedar Tectonic-cachen med paketen Matteprov Design System kräver.

Körs EN gång med internet på, därefter är kompileringen strikt offline
igen. Skriptet återanvänder app.exam_pdf.compile_pdf: eftersom .seeded
tas bort först utelämnar compile_pdf automatiskt --only-cached, så vi
motionerar den riktiga kodvägen i stället för att duplicera den.

Sonden kompilerar appens FAKTISKA utdata — ett representativt
exam_spec.ExamDoc renderat genom app.exam_latex.render_prov/
render_arbetsblad/render_bedomning — i stället för en handskriven
approximation. Anledningen: en tidigare, handskriven PROBE_TEX täckte
inte matte i \\small-kontext (bedömningsanvisningens uppgiftstext), så
fontmetrikerna för \\small-matte hämtades aldrig ner. Med --only-cached
kunde Tectonic då inte hämta dem i efterhand och kraschade (access
violation) i stället för att ge ett läsbart LaTeX-fel. Genom att
kompilera de riktiga mallarna kan sonden och mallarna aldrig glida isär
tyst igen — vad mallarna faktiskt producerar är vad som seedas.

TikZ används numera av mallarna: figurrecepten (app.exam_figures) bygger
ren tikz som renderas genom de riktiga mallarna, och det representativa
dokumentet nedan har en figur (enhetscirkel) som seedar tikz-vägen via
render_prov/render_arbetsblad/render_bedomning. pgfplots laddas också av
provmallen (det är lärarens förlaga som drar in det) och PROBE_TEX drar in
det separat (plus \\usetikzlibrary{angles,quotes}, en \\pic angle-figur och
en exp-kurva) så att glyferna finns cachade om en framtida figurtyp behöver
dem under --only-cached.

PROVET GÅR NUMERA GENOM exam-KLASSEN. Mallen är en reproduktion av lärarens
eget Overleaf-prov: ``\\documentclass{exam}`` med ``addpoints``, booktabs och
25 mm marginaler. Klassen och paketen finns inte i cachen förrän provmallen
kompilerats HÄR — och en klass som saknas ger under ``--only-cached`` samma
tysta krasch som en saknad fontmetrik. Provets jobb nedan är alltså inte en
formalitet; det är det enda som seedar exam.cls.

    python -m tools.seed_tectonic_cache
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

from app import exam_latex, exam_pdf, exam_spec, notes_gen

# Minimal giltig 1×1-pixels PNG (RGB, okomprimerad enda scanline), bäddad
# som base64 så vi varken hittar på ett eget filformat eller behöver
# Pillow installerat för att skriva en bildfil till seedkatalogen.
_MINIMAL_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mM4YaMBAAL8"
    "AS3Bfun7AAAAAElFTkSuQmCC"
)

# Sonden måste dra in VARJE paket mallarna kommer att använda — annars
# saknas det i cachen och --only-cached faller på skarp körning.
# amssymb laddas FÖRE newtxmath: omvänd ordning ger
# "Command \openbox already defined".
PROBE_TEX = r"""
\documentclass[12pt,a4paper]{article}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb}
\usepackage{newtxtext,newtxmath}
\usepackage[margin=17mm,bottom=22mm]{geometry}
\usepackage{xcolor}
\usepackage{graphicx}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{tabularx}
\usepackage{enumitem}
% booktabs kom in med provmallen (lärarens förlaga sätter både betygstabellen
% och datatabellen med \toprule/\midrule/\bottomrule). Provets eget jobb drar
% in det ändå, men sonden ska nämna VARJE paket mallarna använder —
% tests/test_tectonic_seed.py håller den regeln, och den finns för att ett
% paket som bara ett jobb råkar dra in försvinner tyst den dagen jobbet ändras.
\usepackage{booktabs}
\usepackage{tikz}
\usetikzlibrary{angles,quotes}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usepackage[swedish]{babel}
% Svensk babel gör " till ett aktivt genvägstecken, vilket krockar med
% tikz-biblioteket quotes (" i \pic-etiketter nedan) och ger felet
% "Argument of \language@active@arg" has an extra }". \shorthandoff i
% preambeln räcker INTE — babel återaktiverar genvägarna vid
% \begin{document} — så anropet skjuts upp med \AtBeginDocument (se
% motsvarande vakt i _preamble.tex.j2).
\AtBeginDocument{\shorthandoff{"}}
\definecolor{ink700}{HTML}{3A3835}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[C]{\small Sond}
\fancyhead[R]{\small \thepage\ av \pageref{LastPage}}
\begin{document}
Sond för cacheseedning. Matematik: $x^2 - 4x + 3 = 0$,
$\frac{a}{b} \geq \sqrt{c} \neq \pm\infty$, $\alpha \cdot \beta \leq \Sigma$.
Storleksstege (text → script → scriptscript, glyf på varje nivå):
$x^{a \cdot \sqrt{b}}$ och $y^{\frac{c \cdot d}{e}}$.
Familj 3 (utökningsfamiljen; stor operator, extensibel parentes, stor rot):
$\sum_{i=1}^{n} i^2$ och $\int_0^1 f(x)\,dx$ samt
$\left(\frac{n(n+1)}{2}\right)$ och $\sqrt{\frac{x}{2}}$.
\begin{tikzpicture}[scale=0.6]
  \draw[->] (-1,0) -- (4,0); \draw[->] (0,-1) -- (0,4);
  \draw[very thick,domain=-0.5:3.2,smooth,samples=40] plot(\x,{(\x-1)*(\x-3)+2});
  \draw (2,2) circle (0.6);
\end{tikzpicture}
\begin{tikzpicture}
  \begin{axis}[width=6cm,height=4cm]
    \addplot[domain=-2:2,samples=30]{exp(x)};
  \end{axis}
\end{tikzpicture}
\begin{tikzpicture}[scale=1]
  \coordinate (O) at (0,0); \coordinate (X) at (1,0);
  \coordinate (P) at ({cos(40)},{sin(40)});
  \draw (0,0) circle (1); \draw (O)--(X); \draw (O)--(P);
  \pic["$v$",draw,angle radius=8mm,angle eccentricity=1.35]{angle=X--O--P};
  \draw[domain=-2:2,smooth,samples=40] plot(\x,{exp(\x*ln(2))});
\end{tikzpicture}
% ── TS1-GLYFERNA I VARJE GRAD OCH VARJE SNITT ────────────────────────────
% Tankstreck, typografiska citattecken och den centrerade punkten ligger i
% TS1-kodningen, inte i T1 — och TS1 har EGNA fontfiler per grad och snitt
% (ts1-lmbx12, ts1-lmr10 …). app/exam_latex escapar dem ur modellens och
% lärarens text, så de kan dyka upp var som helst på pappret: i titeln
% (\LARGE\bfseries), i delrubriken (\Large\bfseries), i löptexten, i kursiven.
% En titel som «Prov · former» fällde --only-cached på exakt det: «Font
% TS1/lmr/bx/n/20.74=ts1-lmbx12 at 20.74pt not loadable». Alla grader och
% snitt mallarna använder måste därför kompileras HÄR en gång.
% Gradtecknet och dess syskon kom till 2026-08-22 (app/exam_latex escapar dem
% numera i stället för att låta XeTeX slå upp kodpunkten och trycka ř för °).
% De ligger i TS1 precis som tankstrecket och måste därför stå här, i varje
% grad och varje snitt.
\newcommand{\tsprov}{\textendash{} \textemdash{} \textperiodcentered{}
  \textquotedblleft x\textquotedblright{} \textquoteleft x\textquoteright{}
  \textquotedbl{} \guillemotleft x\guillemotright{} \ldots
  \textdegree{} \textpm{} \texttimes{} \textdiv{} \textmu{}
  \textperthousand{} \texteuro{} \textonehalf{} \textonequarter{}
  \textthreequarters{} \textsuperscript{2}\textsuperscript{3}}
{\LARGE\bfseries\tsprov}\par {\LARGE\tsprov}\par
{\Large\bfseries\tsprov}\par {\Large\tsprov}\par
{\large\bfseries\tsprov}\par {\large\tsprov}\par
{\bfseries\tsprov}\par {\itshape\tsprov}\par \tsprov\par
{\small\tsprov}\par {\small\bfseries\tsprov}\par {\small\itshape\tsprov}\par
{\footnotesize\tsprov}\par {\tiny\tsprov}\par
\colorbox{ink700}{\textcolor{white}{Band}}
\begin{tabularx}{\linewidth}{@{}lX@{}}A & B \\\end{tabularx}
\begin{tabular}{lc}\toprule \textbf{Betyg} & \textbf{Poäng} \\ \midrule
F & 0--8 \\ A & 29--37 \\ \bottomrule\end{tabular}
\end{document}
"""


def _representative_doc() -> exam_spec.ExamDoc:
    """Ett representativt prov, byggt direkt i kod (inte via LLM), som
    täcker det mallarna faktiskt kan producera: matte i uppgiftstext,
    lösning OCH bedömning (bedömningsanvisningen visar uppgiftstexten i
    \\small-kontext — det var just den kombinationen den handskrivna
    sonden tidigare missade), en rutinuppgift som ger svarsrad, en
    problemuppgift, uppgifter i både Del B och Del C, en uppgift med
    bild (``bild=1``) så att \\includegraphics-kodvägen i
    prov.tex.j2/arbetsblad.tex.j2 verkligen motioneras, en uppgift med
    deluppgifter (så att \\begin{deluppgift}-miljön kompileras på riktigt
    i alla tre mallarna), en flervalsuppgift (så \\kryssruta samt
    bedömningens "Rätt: X"-rad kompileras), en uppgift med notis (så
    \\notisruta kompileras) och en uppgift med figur (``figur``, en
    enhetscirkel — det tyngsta figurfallet eftersom det renderas via
    tikz-biblioteket angles/quotes, \\pic angle) — annars seedas aldrig de
    paket/fontmetriker dessa kodvägar kräver. Figuren renderas genom
    exam_figures.render_figur och de RIKTIGA mallarna, inte bara via
    PROBE_TEX:s handskrivna \\pic-exempel, så att sonden aldrig kan glida
    isär från vad figurmallarna faktiskt producerar. Problemuppgiften har
    dessutom en
    bokstavsexponent ($a^{t}$) och en nedsänkning ($N_0$) i sitt text-fält,
    och en av deluppgifterna har en EGEN bokstavsexponent ($a^n$) i sitt
    text-fält, så att \\small-fontmetrikerna (ntxmi7/ntxmi5) för
    exponentialmodeller — vanliga i riktiga Ma2/Ma3-prov — verkligen dras
    in i cachen både i uppgift- och deluppgift-miljön."""
    return exam_spec.ExamDoc(
        # Titeln bär med FLIT de tecken som escapas till TS1-kommandon
        # (tankstreck, centrerad punkt, citattecken). Den sätts i \LARGE\bfseries
        # på försättsbladet och i \normalsize i sidhuvudet, alltså precis de
        # två grader som en lärartitel med ett tankstreck i skulle kräva — och
        # som fällde --only-cached innan sonden kompilerade dem.
        titel="Sondprov — «cacheseedning» · del 1–2",
        kurs="Matematik 1c",
        klass="Sond",
        datum="2026-07-20",
        tid_min=60,
        hjalpmedel="Del B utan räknare. Del C med räknare.",
        uppgifter=[
            exam_spec.ExamItem(
                del_="B", formaga="P", typ="rutin", poang=(1, 0, 0),
                text=r"Lös ekvationen $x^2 - 4x + 3 = 0$ och ange svaret "
                     r"som $x_1$ och $x_2$.",
                bild=1,
                losning=r"$x = 1$ eller $x = 3$, ty $\frac{a}{b} \geq "
                        r"\sqrt{c}$ ger reella rötter.",
                bedomning=r"+1 E om båda rötterna anges, annars 0 p "
                          r"(jämför $\alpha \neq \beta$).",
            ),
            exam_spec.ExamItem(
                # Flervalsuppgift: \kryssruta på arbetsblad/prov, och
                # \textbf{Rätt: ...} i bedömningsanvisningen — facit får
                # bara finnas DÄR, aldrig på elevens papper.
                del_="B", formaga="B", typ="rutin", poang=(1, 0, 0),
                text=r"Vilket är ett nollställe till $f(x) = x^2 - 4x + 3$?",
                alternativ=[r"$x = 0$", r"$x = 1$", r"$x = 2$", r"$x = 4$"],
                ratt_alternativ=1,
                losning=r"$x = 1$ ger $f(1) = 0$.",
                bedomning=r"+1 E för rätt alternativ (B).",
            ),
            exam_spec.ExamItem(
                del_="C", formaga="PL", typ="problem", poang=(0, 0, 0),
                # Bokstavsexponent ($a^{t}$) och nedsänkning ($N_0$) här är
                # avsiktliga: bedomning.tex.j2 renderar text-fältet i
                # \small-kontext, och en exponent som är en BOKSTAV (till
                # skillnad från t.ex. $x^2$) kräver fonten ntxmi7 (newtx
                # matte-kursiv, 7 pt) — den dras annars aldrig in i cachen.
                # Riktiga Ma2/Ma3-prov är fulla av just sådana
                # exponentialmodeller (a^x, 2^n), så utan denna rad seedas
                # aldrig fonten och --only-cached kraschar på skarpa prov.
                # Uppgiften är nu en FÖRÄLDER med deluppgifter — poängen
                # [0,0,0] ligger på föräldern, barnen bär poäng/lösning/
                # bedömning (samma mönster som _exam_med_deluppgifter i
                # tests/test_exam.py).
                # STORLEKSSTEGE: fontfilerna slås upp på NAMN (ntxsy7), inte
                # på skalad storlek, så det räcker att varje mattestil träffas
                # en gång — men den måste träffas av en riktig GLYF.
                #   x^{a \cdot \sqrt{b}} → script: bokstav (ntxmi7) OCH symbol
                #                          (\cdot, \sqrt → familj 2 = ntxsy7)
                #   y^{\frac{c \cdot d}{e}} → bråket ligger i script, så
                #                          täljare/nämnare faller till
                #                          scriptscript: ntxmi5 + ntxsy5
                # Utan detta hämtades bara .tfm-metriken och --only-cached
                # kraschade på skarpa prov med "Could not locate a virtual/
                # physical font for TFM ntxsy7" (skarp körning 2026-07-25).
                #
                # FAMILJ 3 (newtxmaths utökningsfamilj, ntxexx/ntxexa) nås
                # INTE av stegen ovan — den är inte en storlek utan en EGEN
                # matematisk familj. \sum och \int är familj 3 direkt (\sum
                # är \mathchar"1350, \int är \mathchar"1352), och en
                # extensibel parentes (\left(...\right)) liksom en stor
                # \sqrt över ett bråk når familj 3 genom att delimiter- och
                # rottecknets charlist byggs av staplade familj 3-glyfer.
                # Sådana uttryck är vanliga i riktiga Ma3/Ma4-prov, minst
                # lika vanliga som storlekskraschen ovan, så utan raden
                # nedan seedas familj 3 aldrig och --only-cached kraschar på
                # samma sätt fast på "ntxexx" i stället för "ntxsy7".
                text=r"En population modelleras av $N(t) = N_0 \cdot a^{t}$. "
                     r"Undersök hur populationen växer. Förenkla också "
                     r"$x^{a \cdot \sqrt{b}}$ och $y^{\frac{c \cdot d}{e}}$. "
                     r"Beräkna även $\sum_{i=1}^{n} i^2$ och "
                     r"$\int_0^1 f(x)\,dx$ samt förenkla "
                     r"$\left(\frac{n(n+1)}{2}\right)$ och "
                     r"$\sqrt{\frac{x}{2}}$. "
                     # SIFFROR OCH BOKSTÄVER PÅ SCRIPTSCRIPT-NIVÅ, i CM.
                     # Provmallen sätts i Computer Modern (lärarens förlaga),
                     # inte i newtx som PROBE_TEX — och CM slår upp sina
                     # matematikfonter på NAMN med storleken i namnet: cmr12,
                     # cmr8, cmr6. Stegen ovan når scriptscript med SYMBOLER
                     # (\cdot, \frac) men aldrig med en siffra, så cmr6 hämtades
                     # aldrig. Ett skarpt prov med $2^{3^{4}}$-liknande
                     # uttryck — eller bara ett gränsvärde med ett tal i ett
                     # dubbelt index — fällde då --only-cached med «Could not
                     # locate a virtual/physical font for TFM cmr6».
                     r"Kontrollera slutligen $2^{3^{4}}$, $x^{y^{z}}$ och "
                     r"$\left(1 + \frac{1}{n}\right)^{n^{2}}$.",
                losning="", bedomning="",
                deluppgifter=[
                    exam_spec.SubItem(
                        poang=(0, 1, 0),
                        # Egen bokstavsexponent ($a^n$) i DELUPPGIFTENS eget
                        # text-fält — deluppgift-miljön har sin egen inre
                        # list-miljö (se _preamble.tex.j2), så \small-matte
                        # måste motioneras där också, inte bara på föräldern.
                        text=r"Ange ett uttryck för populationen efter $n$ "
                             r"år, skrivet som $a^n$ multiplicerat med $N_0$.",
                        losning=r"$N(n) = N_0 \cdot a^n$, ty tillväxtfaktorn "
                                r"$a$ upprepas $n$ gånger.",
                        bedomning=r"+1 C om uttrycket $a^n$ används korrekt.",
                    ),
                    exam_spec.SubItem(
                        poang=(0, 0, 1),
                        # FIGUR PÅ EN DELUPPGIFT. Förlagans 1(a) har grafen
                        # inne i deluppgiften, och mallens gren för det
                        # (prov.tex.j2, inuti \begin{parts}) är en egen
                        # kodväg — den kompilerades aldrig under seedningen så
                        # länge figurerna bara satt på uppgifter. Typen är en
                        # FUNKTIONSGRAF och inte enhetscirkeln nedan: graferna
                        # ritar rutnät och \footnotesize-siffror på axlarna,
                        # och det är den vanligaste figuren på ett riktigt
                        # prov.
                        figur={"typ": "andragrad", "a": -1, "b": 6, "c": -5},
                        text=r"Visa att $\alpha \cdot \beta \leq \Sigma$ "
                             r"gäller även då $x \to \pm\infty$.",
                        losning=r"Gränsvärdet $\pm\infty$ hanteras separat "
                                r"och $\sqrt{c} \geq 0$ används i sista "
                                r"steget.",
                        bedomning=r"+1 A för fullständig motivering av "
                                  r"gränsvärdet.",
                    ),
                ],
            ),
            exam_spec.ExamItem(
                # Notis (inramad instruktionsruta) — kompilerar \notisruta.
                del_="C", formaga="R", typ="resonemang", poang=(0, 1, 1),
                text=r"Avgör om påståendet stämmer: en andragradsfunktion "
                     r"med $a < 0$ saknar minsta värde. Motivera.",
                notis=r"Rita gärna en skiss av grafen som stöd för "
                      r"resonemanget.",
                losning=r"Sant — grafen är en nedåtriktad parabel.",
                bedomning=r"+1 C ställningstagande, +1 A stringens.",
            ),
            exam_spec.ExamItem(
                # DE FEM FORMERNA i en uppgift: datatabellen (\begin{tabular}
                # med \tabrubrik), enheten på svarsraden (\svarsradmed),
                # kryssruteraden (\svarsrutor + \svarsruteval), stegtabellen
                # (\begin{tabularx} med \kryssruta i varje rad) och de
                # kommenterade elevlösningarna (\begin{elevparti}, som bygger
                # på \lrbox + \fcolorbox). Ingen av dem fanns i seeden när de
                # kom, och en form som aldrig kompilerats under seedningen
                # kraschar --only-cached FÖRSTA gången läraren godkänner ett
                # papper som råkar bära den.
                del_="C", formaga="M", typ="problem", poang=(1, 1, 0),
                text=r"Tabellen visar antalet laddpunkter. Bestäm den "
                     r"genomsnittliga förändringshastigheten $\frac{\Delta y}"
                     r"{\Delta x}$ mellan 2020 och 2023.",
                enhet=r"laddpunkter/år",
                tabell=exam_spec.Tabell(
                    rubriker=["År", "2020", "2021", "2023"],
                    rader=[["Antal", "5 400", "7 100", "12 600"]]),
                svarsrutor=exam_spec.Svarsrutor(
                    etikett="Metod", val=[r"Sekant genom $(x_1, y_1)$",
                                          r"Derivata i punkten"], ratt=0),
                stegtabell=exam_spec.Stegtabell(
                    kolumner=["Alvas lösning", "Bilals lösning"],
                    steg=[exam_spec.Steg(celler=[r"$3^{x+1} = 7 \cdot 3^{x-2}$",
                                                 r"$\lg(3^{x+1}) = \lg 7$"]),
                          exam_spec.Steg(celler=[r"$3^{3} = 7$",
                                                 r"$(x+1)\lg 3 = \lg 7$"]),
                          exam_spec.Steg(celler=[r"$27 = 7$",
                                                 r"$x \approx 0{,}77$"])],
                    forsta_fel=1),
                # TS1-TECKNEN I BEDÖMNINGSTABELLENS BÅDA SPALTER. Sedan
                # 2026-08-23 sätts lösningen i \small i vänsterspalten och
                # trappan i \small i högerspalten (bedomning.tex.j2,
                # \bedrad), och elevens rader i normalgrad. Var och en av dem
                # kan bära ett gradtecken — «temperaturen sjunker med 1,86
                # °C/minut» är ett helt vanligt facit — och TS1 har en
                # fontfil per grad. Preamblen sätter numera alla TS1-tecken
                # magert och upprätt (\normalfont-vakten), så det som måste
                # ligga i cachen är ts1-lmr i de grader mallarna använder.
                # Raderna här är det som får dem dit.
                losning=r"$\frac{12\,600 - 5\,400}{3} = 2\,400$ per år "
                        r"(≈ 3,5 °C ± 0,2 per ‰).",
                bedomning="+1 E korrekt kvot i laddpunkter/år\n"
                          "+1 C tolkning i sammanhanget (± 2 °C godtas)",
                elevlosningar=[
                    exam_spec.Elevlosning(
                        etikett="0 p", partier=[exam_spec.Parti(
                            rader=[r"$f'(x) = 3x^2$ vid 20 °C"], poang=(0, 0, 0),
                            dom=r"Derivatan är fel — termen $3x$ deriveras inte.")]),
                    exam_spec.Elevlosning(
                        etikett="1 p", partier=[
                            exam_spec.Parti(rader=[r"$f'(x) = 3x^2 + 3 = 0$"],
                                            poang=(1, 0, 0),
                                            dom=r"Godtagbar ansats: ekvationen tecknas."),
                            exam_spec.Parti(
                                rader=[r"$x^2 = -1$ saknar reell lösning, ty "
                                       r"$x^2 \geq 0$."], poang=(0, 1, 0),
                                dom=r"Godtagbart resonemang med motivering.")]),
                ],
            ),
            exam_spec.ExamItem(
                # Figur (enhetscirkel) — kompilerar exam_figures.render_figur
                # och \pic angle genom den RIKTIGA mallkedjan (inte bara
                # PROBE_TEX ovan). figur och bild utesluter varandra i
                # schemat, så uppgiften får INTE ha bild=... samtidigt.
                del_="C", formaga="B", typ="rutin", poang=(1, 0, 0),
                # TS1-TECKNEN GENOM PROVMALLEN, alltså i Computer Modern.
                # PROBE_TEX:s \tsprov kompileras i newtx och seedar därför
                # ts1-ntx*, inte ts1-lmr* — och provet är lärarens förlaga och
                # sätts i CM. «T mäts i 20 °C» på ett skarpt prov hade fällt
                # --only-cached på ts1-lmr12 om escapningen kommit utan den här
                # raden.
                text=r"Figuren visar vinkeln $v$ i enhetscirkeln. "
                     "Temperaturen är 20 °C ± 2 °C, arean 3 cm² och "
                     "andelen ½ ‰ (µm, 4 × 5 ÷ 2, 3 m³, ¼, ¾, 5 €).",
                figur={"typ": "enhetscirkel", "vinkel": 40},
                losning=r"Vinkeln är $v = 40^\circ$.",
                bedomning=r"+1 E för korrekt avläsning av vinkeln.",
            ),
        ],
    )


def _representativa_anteckningar() -> notes_gen.NoteDoc:
    """Ett representativt stödpapper: rubriker, löptext, EN punktlista och
    kom ihåg-rutan. Alla tre formerna måste med — punktlistan drar in
    enumitem-miljön och rutan \\fcolorbox på en xcolor-blandning, och en form
    som aldrig kompilerats under seedningen kraschar --only-cached första
    gången läraren godkänner ett papper som råkar bära den (samma läxa som
    gruppuppgiftsmallen och de fem formerna gav).

    Matten i sista stycket är avsiktlig: anteckningar är sällan matematik, men
    fältet TILLÅTER $…$ och då ska fontmetrikerna finnas i cachen."""
    return notes_gen.NoteDoc(
        # Ingen tankstreck ens här: stilregeln i notes_gen gäller pappret, och
        # ett sondpapper som bryter mot den är ett dåligt facit att mäta mot.
        titel="Sondanteckningar för cacheseedning",
        datum="2026-08-18",
        klass="Sond",
        sektioner=[
            notes_gen.Sektion(
                rubrik="Boken",
                stycken=["Vi arbetar i kursboken hela terminen. Alla får ett "
                         "eget exemplar idag och skriver numret på insidan."]),
            notes_gen.Sektion(
                rubrik="Så räknar vi",
                stycken=["Du räknar i din egen takt. Jag går runt och hjälper."],
                punkter=["Blå uppgifter först", "Röda när du känner dig säker"]),
            notes_gen.Sektion(
                rubrik="Prov och rättning",
                stycken=["Provet ligger i vecka 42. Formeln vi använder mest "
                         "är $a^2 + b^2 = c^2$, och den står på formelbladet."]),
        ],
        kom_ihag=["Ta med boken på fredag", "Lämna in blanketten till mentorn"],
    )


def seed(out_dir: Path, *, compile_fn=exam_pdf.compile_pdf) -> tuple[bool, str]:
    """Seeda cachen. Returnerar (lyckades, meddelande).

    Markören tas bort FÖRE kompileringen och skrivs tillbaka först om
    SAMTLIGA kompileringar (prov, arbetsblad, bedömningsanvisning samt
    tikz/pgfplots-sonden) lyckas — annars kan en halvfärdig cache låsa
    --only-cached för gott."""
    markor = exam_pdf.engine_dir() / "cache" / ".seeded"
    if markor.exists():
        markor.unlink()

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Bildvägen (\includegraphics i prov.tex.j2/arbetsblad.tex.j2) motioneras
    # bara om en riktig bildfil ligger i utkatalogen — Tectonic kompilerar
    # med out_dir som arbetskatalog, så bilder-mappningen pekar på FILNAMNET
    # (se exam_latex._build_view), inte hela sökvägen.
    bild_fil = "bild-01.png"
    (out_dir / bild_fil).write_bytes(base64.b64decode(_MINIMAL_PNG_B64))
    bilder = {1: bild_fil}

    doc = _representative_doc()
    # Gruppuppgiften (Fas 0.6) har en EGEN mall: namnrader (\rule på 86 % av
    # raden), rubriken i \LARGE\bfseries och metaraden i \small — sättningar
    # de andra mallarna inte har. Kompilerades den inte här saknades dess
    # fontmetriker i cachen, och första skarpa godkännandet under
    # --only-cached kraschade i stället för att ge ett läsbart LaTeX-fel.
    # Regeln som gäller: varje render_*-funktion i exam_latex ska ha ett jobb
    # här (tests/test_tectonic_seed.py håller den).
    grupp_doc = doc.model_copy(update={
        "grupp": exam_spec.GruppUpplagg(elever=4, langd_min=45,
                                        redovisning="poster")})
    jobb = (
        ("prov", exam_latex.render_prov(doc, bilder=bilder)),
        ("arbetsblad", exam_latex.render_arbetsblad(doc, bilder=bilder)),
        # Det separata facit (Etapp 2) är samma mall med elevernas del släckt,
        # så det borde inte kräva något nytt — men «borde» är just det ordet
        # gruppuppgiften och de fem formerna också stod bakom när de kraschade
        # --only-cached första gången läraren godkände ett sådant papper. Ett
        # dokument som börjar med \delprovband och inte har en enda \svarsrad
        # är en egen sättning, och den kostar en kompilering här.
        ("arbetsblad-facit",
         exam_latex.render_arbetsblad(doc, bilder=bilder, only_facit=True)),
        ("bedomning", exam_latex.render_bedomning(doc, bilder=bilder)),
        ("gruppuppgift", exam_latex.render_gruppuppgift(grupp_doc, bilder=bilder)),
        # Anteckningarna har en EGEN mall med egna sättningar: 22 mm marginal,
        # \linespread, itemize (enumitem) och en tonad ruta byggd med
        # \fcolorbox på en xcolor-blandning. Ingen av dem finns i de andra
        # mallarna, och en mall cachen aldrig sett kraschar --only-cached TYST
        # första gången läraren godkänner ett papper av den sorten.
        ("anteckningar", exam_latex.render_anteckningar(_representativa_anteckningar())),
        ("sond", PROBE_TEX),
    )

    for jobname, tex in jobb:
        pdf, logg = compile_fn(tex, out_dir, jobname, timeout=900)
        if pdf is None:
            return False, (f"{jobname}: "
                           f"{logg or 'kompileringen misslyckades utan felmeddelande'}")

    markor.parent.mkdir(parents=True, exist_ok=True)
    markor.write_text("", encoding="utf-8")
    return True, ("cachen är seedad (prov, arbetsblad, bedömning, "
                  "gruppuppgift, anteckningar, tikz/pgfplots)")


def main() -> int:
    print("Seedar Tectonic-cachen (kräver internet) …")
    ok, meddelande = seed(exam_pdf.engine_dir() / "_seed")
    if not ok:
        print(f"MISSLYCKADES: {meddelande}", file=sys.stderr)
        print("Cachen är nu OMARKERAD — kör om skriptet med nät på.",
              file=sys.stderr)
        return 1
    print(f"KLART: {meddelande}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
