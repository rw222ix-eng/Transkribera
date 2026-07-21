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

TikZ och pgfplots används ännu inte av mallarna (kommer i ett senare
steg) och dras därför fortfarande in via en egen PROBE_TEX, som nu även
laddar \\usetikzlibrary{angles,quotes} och kompilerar en \\pic angle-figur
samt en exp-kurva, så att biblioteksglyferna hamnar i cachen innan
recepten (kommande tasks) behöver dem under --only-cached.

    python -m tools.seed_tectonic_cache
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

from app import exam_latex, exam_pdf, exam_spec

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
\colorbox{ink700}{\textcolor{white}{Band}}
\begin{tabularx}{\linewidth}{@{}lX@{}}A & B \\\end{tabularx}
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
    bedömningens "Rätt: X"-rad kompileras) och en uppgift med notis (så
    \\notisruta kompileras) — annars seedas aldrig de paket/fontmetriker
    dessa kodvägar kräver. Problemuppgiften har dessutom en
    bokstavsexponent ($a^{t}$) och en nedsänkning ($N_0$) i sitt text-fält,
    och en av deluppgifterna har en EGEN bokstavsexponent ($a^n$) i sitt
    text-fält, så att \\small-fontmetrikerna (ntxmi7/ntxmi5) för
    exponentialmodeller — vanliga i riktiga Ma2/Ma3-prov — verkligen dras
    in i cachen både i uppgift- och deluppgift-miljön."""
    return exam_spec.ExamDoc(
        titel="Sondprov — cacheseedning",
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
                text=r"En population modelleras av $N(t) = N_0 \cdot a^{t}$. "
                     r"Undersök hur populationen växer.",
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
        ],
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
    jobb = (
        ("prov", exam_latex.render_prov(doc, bilder=bilder)),
        ("arbetsblad", exam_latex.render_arbetsblad(doc, bilder=bilder)),
        ("bedomning", exam_latex.render_bedomning(doc, bilder=bilder)),
        ("sond", PROBE_TEX),
    )

    for jobname, tex in jobb:
        pdf, logg = compile_fn(tex, out_dir, jobname, timeout=900)
        if pdf is None:
            return False, (f"{jobname}: "
                           f"{logg or 'kompileringen misslyckades utan felmeddelande'}")

    markor.parent.mkdir(parents=True, exist_ok=True)
    markor.write_text("", encoding="utf-8")
    return True, "cachen är seedad (prov, arbetsblad, bedömning, tikz/pgfplots)"


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
