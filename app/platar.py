"""Plåtkatalogen — lärarens målade bakgrunder, matchade mot en uppgift.

LÄRARENS DOM, och den är hela modulens skäl att finnas: «Skit i nyckeln, ingen
API. Prompt bara, så skapar jag bilden med min prenumeration.» Appen anropar
alltså ALDRIG något bild-API. Den gör två saker i stället:

1. **Katalogträffen.** Finns redan en målad plåt för uppgiftens begrepp läggs
   DEN på uppgiften. Trettiosex plåtar är redan gjorda och betalda; att be
   läraren måla en trettiosjunde av samma äng är slöseri med hennes kväll.
2. **SCENE-stycket.** Finns ingen plåt skriver provgeneratorn ett SCENE-stycke
   (app/exam_gen, fältet ``scen``) som läraren klistrar in i sitt eget
   ChatGPT-projekt. Projektet lägger själv basprompten framför — därför
   kopieras BARA scenstycket, aldrig något vi hittat på runt det.

TVÅLAGERSPRINCIPEN (lärarens projektinstruktion) gäller åt båda hållen: plåten
är bara målning. Ingen text, inga siffror, inga pilar, inga axlar. Det är en
riktighetsfråga — en bildmodell ritar en vinkelbåge som dekor, på fel sida om
lodlinjen, och felet upptäcks först av en elev mitt i ett prov.

VAR PLÅTARNA BOR. Skarpt i ``E:\\Bildstil`` (``resultat/platar/*.png`` och
``designsystem/platar/*.txt``). Roten är konfigurerbar — miljövariabeln
``TRANSKRIBERA_BILDSTIL`` eller ``bildstil_dir`` i settings.json — och saknas
katalogen fungerar allt utom just katalogträffen: SCENE-vägen är oberoende av
filerna. Plåtarna kopieras ALDRIG in i repot; de är lärarens material.

KATALOGEN ÄR SPEGLAD SOM DATA här nere (``SPEGEL``) med DESIGNSYSTEM.md som
källa, och berikas ur scenfilernas ``Intended use:``-rader när de går att läsa.
Utan spegeln vore matchningen beroende av att en katalog på en annan disk är
monterad; med bara spegeln skulle den missa de begrepp läraren skrivit in i
scenfilerna efteråt. Båda behövs, och spegeln är den som får appen att fungera
på en maskin där E: inte finns.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# Standardroten är lärarens egen disk. Den står här och inte i en inställning
# därför att den är SANN på hennes maskin — inställningen finns för de andra.
ROT_STANDARD = Path(r"E:\Bildstil")
MILJOVARIABEL = "TRANSKRIBERA_BILDSTIL"

# ── SPEGELN ────────────────────────────────────────────────────────────
# Källa: E:\Bildstil\designsystem\DESIGNSYSTEM.md, avsnittet «Plåtkatalog»
# (läst 2026-08-22). Formen är (namn, motiv, begrepp) — samma tre kolumner som
# tabellen.
#
# Begreppen är tabellens PLUS en handfull ord ur scenfilernas «Intended use:»
# («kastbanan» i a-01, «inhägnad» i a-19, «rabatt» i a-24). De står här därför
# att spegeln ska räcka ENSAM: en maskin utan E: ska matcha likadant som
# lärarens. `katalog()` lägger till resten av scenfilernas begrepp när de går
# att läsa.
#
# SPÅR A är målade scener: ett motiv ur verkligheten, rakt från sidan, med en
# lugn yta att rita notationen på. SPÅR B är målade PAPPER med en liten vinjett
# i hörnet — tomma ark att bygga matematik på i kod.
SPEGEL_A: list[tuple[str, str, str]] = [
    ("a-01-kastparabel", "kastare på äng, boll i toppen av banan",
     "andragradsfunktion, maximipunkt, derivatans nollställe, kastbanan"),
    ("a-02-aker-diagonal", "rektangulär åker med diagonal stig",
     "Pythagoras sats, avstånd, area och omkrets"),
    ("a-03-tall-skugga", "tall och människa med långa skuggor",
     "likformighet, skala, tangens, höjdbestämning"),
    ("a-04-pariserhjul", "pariserhjul rakt från sidan",
     "cirkeln, radianer, vinkelhastighet, sinus och cosinus"),
    ("a-05-hav-dyning", "regelbunden dyning mot horisonten",
     "sinuskurva, amplitud, period, våglängd, fas"),
    ("a-06-backe-vag", "grusväg över en rundad kulle",
     "derivata som lutning, tangent, växande och avtagande"),
    ("a-07-flod-bat", "roddbåt i en flod med synlig ström",
     "vektorer, komposanter, resultant"),
    ("a-08-silo", "cylindrisk silo med kon-tak",
     "volym, begränsningsarea, cylinder och kon"),
    ("a-09-jarnvag", "rakt spår med tåg över slätten",
     "linjär funktion, sträcka–tid, k-värde och m-värde"),
    ("a-10-solrosfalt", "rad solrosor på olika höjd",
     "medelvärde, median, spridning, histogram"),
    ("a-11-akrar-andelar", "åkerlapptäcke uppifrån",
     "bråk och andelar, procent, area, rutnät och koordinater"),
    ("a-12-sjo-spegling", "spegelblank sjö i skymning",
     "symmetri och spegling, transformationer, jämna och udda funktioner"),
    ("a-13-alle-transversal", "allé korsad av ett staket",
     "parallella linjer och transversal, vinkelpar, riktningskoefficient"),
    ("a-14-fyr-bat", "fyr och båt i kvällsmörker",
     "sinussatsen och cosinussatsen, elevationsvinkel, två observatörer"),
    ("a-15-tre-hostackar", "tre höstackar i en triangel",
     "triangelgeometri, vinkelsumma, avstånd mellan punkter"),
    ("a-16-nackrosdamm", "damm halvtäckt av näckrosor",
     "exponentiell tillväxt, fördubbling, förändringsfaktor"),
    ("a-17-gardesgard-vinter", "staketstolpar i snö, ojämnt avstånd",
     "talföljder, aritmetisk och geometrisk följd, rekursion"),
    ("a-18-sjo-uppifran-host", "oregelbunden skogssjö, höstfärger",
     "area av oregelbunden form, integral, approximation"),
    ("a-19-hage-flod", "inhägnad rektangel mot en flod",
     "optimering, största area vid given omkrets, extremvärden, inhägnad"),
    ("a-20-kyrktorn", "kyrka med spetsig pyramidspira",
     "pyramid och kon, volym, höjd och lutning"),
    ("a-21-stjarnhimmel", "natthimmel över en äng",
     "tiopotenser och prefix, stora tal, logaritmisk skala"),
    ("a-22-tva-batar", "två båtar på kollisionskurs, uppifrån",
     "relaterade förändringshastigheter, vektorer, ekvationssystem"),
    ("a-23-brygga-tallinje", "brygga med jämnt spridda stolpar",
     "tallinjen, negativa tal, intervall, skala och enheter"),
    ("a-24-marknadsstand", "marknadsstånd med lådor frukt",
     "proportionalitet och enhetspris, procent, rabatt, kombinatorik"),
]

SPEGEL_B: list[tuple[str, str, str]] = [
    ("b-01-integral", "ängsremsa under moln",
     "integral som area, primitiv funktion, Riemannsummor"),
    ("b-02-ekvationssystem", "två stigar som korsas",
     "ekvationssystem, skärningspunkt, substitution"),
    ("b-03-exponentiell", "ung tall",
     "exponentialfunktioner, logaritmer, förändringsfaktor"),
    ("b-04-enhetscirkel", "väderkvarn med korsande vingar",
     "enhetscirkeln, radianer, trigonometriska ekvationer"),
    ("b-05-sannolikhet", "stig som grenar sig",
     "sannolikhet, träddiagram, beroende händelser"),
    ("b-06-normalfordelning", "blomsteräng på olika höjd",
     "normalfördelning, standardavvikelse, spridningsmått"),
    ("b-07-komplexa-tal", "vindflöjel med kompassros",
     "komplexa tal, absolutbelopp och argument, polär form"),
    ("b-08-talfoljder", "staketstolpar i snö",
     "talföljder, summor, rekursion, induktion"),
    ("b-09-geometriska-bevis", "kallmurad stenmur",
     "geometriska bevis, kongruens och likformighet, satser"),
    ("b-10-procent-index", "fruktlådor på ett marknadsstånd",
     "procent och procentenheter, index och ränta, överslag"),
    ("b-11-kombinatorik", "fågelflock i formation",
     "permutationer och kombinationer, multiplikationsprincipen"),
    ("b-12-gransvarden", "rak väg mot horisonten",
     "gränsvärden, asymptoter, kontinuitet, derivatans definition"),
]

# ── VILKA PLÅTAR SOM FÅR HAMNA PÅ ETT PROV ────────────────────────────
# Bara spår A. En b-plåt är ett målat PAPPER med en vinjett i hörnet — en tom
# yta som notationen ritas på i kod — och tryckt ovanför en provuppgift är den
# ett tomt ark mitt i provet. Uppgiftens `scen` är dessutom spår A per
# definition (lärarens instruktion: «SPÅR A när begreppet har en verklig
# situation»), så det är samma dom sagd två gånger. B står kvar i katalogen
# därför att katalogen ska vara hel: den som listar plåtarna ska se alla.
MATCHBARA_SPAR = ("a",)


def spegel() -> list[dict]:
    """Katalogen som ren data, utan att någon disk behöver finnas."""
    ut = []
    for spar, rader in (("a", SPEGEL_A), ("b", SPEGEL_B)):
        for namn, motiv, begrepp in rader:
            ut.append({"namn": namn, "spar": spar, "motiv": motiv,
                       "begrepp": begrepp})
    return ut


# ── ROTEN ──────────────────────────────────────────────────────────────

def rot(base: Path | None = None) -> Path:
    """Var plåtarna ligger. Miljövariabel först (den är testernas och
    flyttarens väg), sedan appens inställning, sist lärarens egen disk."""
    miljo = (os.environ.get(MILJOVARIABEL) or "").strip()
    if miljo:
        return Path(miljo)
    if base is not None:
        try:
            from app import settings_store
            val = (settings_store.load(Path(base)).get("bildstil_dir") or "")
        except Exception:                     # inställningsfilen är aldrig kritisk
            val = ""
        if str(val).strip():
            return Path(str(val).strip())
    return ROT_STANDARD


def scen_dir(base: Path | None = None) -> Path:
    return rot(base) / "designsystem" / "platar"


def bild_dir(base: Path | None = None) -> Path:
    return rot(base) / "resultat" / "platar"


def bildfil(namn: str, base: Path | None = None) -> Path | None:
    """PNG:en för en plåt, eller None när den inte ligger på disk."""
    if not _NAMN_RE.match(str(namn or "")):
        return None
    p = bild_dir(base) / f"{namn}.png"
    return p if p.is_file() else None


# Plåtnamnets form är systemets egen: spår, tvåsiffrigt nummer, slug. Den
# används både som validering av lärarens val (en sträng ur ett anrop får
# aldrig bli en sökväg) och som filnamnsförslag i SCENE-stycket.
_NAMN_RE = re.compile(r"^[abh]-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")
_INTENDED_RE = re.compile(r"intended use\s*:\s*(.+)", re.I | re.S)


def _scenbegrepp(namn: str, base: Path | None = None) -> str:
    """«Intended use:»-raden ur plåtens scenfil, eller tomt.

    Raden är lärarens egen sammanfattning av vad plåten DUGER TILL, skriven i
    samma stund som plåten målades — den är alltid färskare än tabellen."""
    try:
        text = (scen_dir(base) / f"{namn}.txt").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""
    m = _INTENDED_RE.search(text)
    if not m:
        return ""
    # Stycket kan radbrytas mitt i uppräkningen; punkten avslutar den.
    rad = " ".join(m.group(1).split())
    return rad.split(". ")[0].rstrip(". ")


def katalog(base: Path | None = None) -> list[dict]:
    """Spegeln, berikad med scenfilernas begrepp och med `fil` satt för de
    plåtar som faktiskt ligger på disk."""
    ut = []
    for p in spegel():
        extra = _scenbegrepp(p["namn"], base)
        rad = dict(p)
        if extra:
            rad["begrepp"] = f"{p['begrepp']}, {extra}"
        fil = bildfil(p["namn"], base)
        rad["fil"] = str(fil) if fil else None
        ut.append(rad)
    return ut


# ── MATCHNINGEN ────────────────────────────────────────────────────────
# INGET LLM-ANROP. Matchningen är ordmatchning och ska förbli det: den körs på
# varje uppgift i varje prov, och en modell som får gissa vilken äng som passar
# skulle både kosta en runda och kunna svara «a-31» om en plåt som inte finns.

_SKILJETECKEN = re.compile(r"[^a-zåäö0-9]+")
# Ord som står i nästan varje begreppslista och därför inte skiljer plåtarna
# åt. Listan är kort med flit — resten sköts av viktningen nedan, som räknar
# hur många plåtar ett ord förekommer i.
_STOPP = frozenset("""
och som i av med en ett den det de vid till per mellan två tre för på under
över där när om att är kan ska sin sina dess samt eller inte mot ur
""".split())

# Synonymer: lärarens och modellens ord på vänster sida, KATALOGENS ord på
# höger. Nyckeln till att listan är ofarlig är att högerledet alltid är ett ord
# som faktiskt står i katalogen — annars köper synonymen bara en prefixträff
# med okänd vikt.
#
# Listan är kort med flit. Varje rad är ett ord som är för kort för
# prefixregeln («kast» och «kastbanan» delar fyra bokstäver) eller som läraren
# skriver på ett annat sätt än katalogen. Ord som blir tvetydiga när
# diakriterna faller (våg/väg → «vag») står INTE här: den raden skulle dra ett
# vägbygge till havsdyningen.
_SYNONYM = {
    "kast": "kastbanan", "kastet": "kastbanan", "kastar": "kastbanan",
    "kastas": "kastbanan", "kastbana": "kastbanan",
    "hage": "inhagnad", "rastgard": "inhagnad", "stangsel": "inhagnad",
    "optimera": "optimering", "optimerar": "optimering",
    "maximum": "maximipunkt", "maxpunkt": "maximipunkt",
    "minimipunkt": "extremvarden", "extrempunkt": "extremvarden",
    "extremvarde": "extremvarden", "extrempunkter": "extremvarden",
    "vaxer": "tillvaxt", "fordubblas": "fordubbling",
    "amortering": "ranta", "index": "index",
    "genomsnitt": "medelvarde", "medel": "medelvarde",
    "skuggan": "skugga", "skuggor": "skugga",
    "sannolikt": "sannolikhet", "chans": "sannolikhet",
}


def _tokens(text: str) -> list[str]:
    """Ord, normaliserade så att lärarens «tillväxt» och scenfilens «tillvaxt»
    är samma ord. Scenfilerna på disk är skrivna utan diakriter (bildmodellen
    fick engelsk prompt), och den skillnaden får inte avgöra en träff."""
    rå = _SKILJETECKEN.split((text or "").lower())
    ut = []
    for ord_ in rå:
        o = ord_.replace("å", "a").replace("ä", "a").replace("ö", "o")
        if len(o) < 3 or o in _STOPP:
            continue
        ut.append(_SYNONYM.get(o, o))
    return ut


# Hur många begynnelsebokstäver två ord måste dela för att räknas som samma
# ord, och hur mycket en sådan träff är värd mot en exakt.
#
# SJU är mätt mot katalogen, inte gissat. Böjningsparen ska hålla ihop —
# «derivata»/«derivatans» delar åtta, «talföljd»/«talföljder» nio,
# «exponentiell»/«exponentialfunktioner» nio — medan de par som INTE är samma
# sak ska falla: «vinkelsumma» och «vinkelhastighet» delar precis sex, och vid
# gränsen sex blev de samma ord.
_PREFIX_MIN = 7
# Tre fjärdedelar och inte hälften: en böjning är nästan lika mycket värd som
# ordet självt. Vid en halv föll «talföljd» mot a-17 på 3,0 av 4,0 nödvändiga —
# alltså skrevs ett SCENE-stycke till en plåt som redan fanns målad.
_PREFIX_VARDE = 0.75


def _prefixlangd(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _vikter(poster: list[dict]) -> dict[str, int]:
    """Ordvikt = hur SÄLLSYNT ordet är i katalogen.

    «optimering» står hos EN plåt och pekar därför entydigt; «area» står hos
    fem och pekar ingenstans. Utan den här viktningen räckte ordet «area» i en
    uppgiftstext för att slumpvis dra dit en åker.
    """
    rakning: dict[str, int] = {}
    for p in poster:
        for t in set(_tokens(p["begrepp"])):
            rakning[t] = rakning.get(t, 0) + 1
    return {t: (3 if n == 1 else 2 if n == 2 else 1)
            for t, n in rakning.items()}


# Lägsta poäng för att en plåt ska läggas på en uppgift. Tre är exakt ETT
# entydigt begreppsord (vikt 3, begreppsvikt … se nedan) och inte mer: hellre
# ett SCENE-stycke läraren själv får måla än en äng som inte hör hemma.
MIN_POANG = 4.0
# Begreppsfältet väger dubbelt mot uppgiftstexten. `scen.begrepp` är modellens
# egen nyckel — «optimering inhägnad» — medan texten är en berättelse där
# orden råkar dyka upp.
_VIKT_BEGREPP = 2.0
_VIKT_TEXT = 1.0
# Hela begreppssträngen ordagrant i katalogens rad: det är inte en slump.
_FRASBONUS = 6.0


def poang(post: dict, begrepp: str, text: str = "",
          vikter: dict[str, int] | None = None) -> float:
    """Hur väl en plåt passar. Öppen för test — matchningen ska gå att mäta,
    inte bara att lita på."""
    vikter = vikter or _vikter([post])
    kat = _tokens(post["begrepp"])
    kat_set = set(kat)
    summa = 0.0
    for kalla, vikt in ((begrepp, _VIKT_BEGREPP), (text, _VIKT_TEXT)):
        for t in set(_tokens(kalla)):
            if t in kat_set:
                summa += vikter.get(t, 1) * vikt
                continue
            # Prefixträff räknas halvt: «derivata» mot «derivatans» är samma
            # sak, men gränsen är trubbig och ska inte ensam fälla avgörandet.
            #
            # VIKTEN TAS UR KATALOGENS ord, inte ur vårt. Vårt ord finns per
            # definition inte i katalogen (annars hade det varit en exakt
            # träff) och skulle alltid få defaultvikten 1 — då spelade det
            # ingen roll om «andragradsekvation» pekade på en plåt eller på
            # fem.
            traff = [vikter.get(k, 1) for k in kat_set
                     if _prefixlangd(t, k) >= _PREFIX_MIN]
            if traff:
                summa += max(traff) * vikt * _PREFIX_VARDE
    # HELA begreppssträngen ordagrant i katalogens rad — «exponentiell
    # tillväxt» mot a-16 — är ingen slump. Minst två ord krävs: ett ensamt
    # ord är ingen fras, och utan den regeln räckte ordet «area» i ett
    # begreppsfält för att dra dit en åker på sex bonuspoäng.
    nycklar = _tokens(begrepp)
    if len(nycklar) >= 2:
        nyckel = " ".join(nycklar)
        if f" {nyckel} " in f" {' '.join(kat)} ":
            summa += _FRASBONUS
    return summa


def matcha(begrepp: str, text: str = "", *, base: Path | None = None,
           poster: list[dict] | None = None,
           tagna: set[str] | frozenset[str] | None = None) -> dict | None:
    """Bästa plåten för ett begrepp, eller None när ingen passar.

    `poster` går att skicka in i test; annars läses katalogen (spegel +
    scenfiler). Bara spår A matchas — se MATCHBARA_SPAR.

    `tagna` är plåtar som redan ligger på ett annat uppslag i SAMMA prov. De
    tas ur kandidatlistan, så andra träffen får näst bästa plåt i stället för
    samma äng en gång till: två identiska bilder på ett prov läser som ett
    tryckfel. Finns ingen annan som når över MIN_POANG blir det ingen bild —
    då står SCENE-stycket framme och läraren målar en ny."""
    alla = poster if poster is not None else katalog(base)
    kandidater = [p for p in alla if p.get("spar") in MATCHBARA_SPAR
                  and p.get("namn") not in (tagna or ())]
    if not kandidater:
        return None
    vikter = _vikter(kandidater)
    bast, bast_p = None, 0.0
    for p in kandidater:
        v = poang(p, begrepp, text, vikter)
        # Strikt >: står två plåtar lika vinner den FÖRSTA i katalogen, och
        # katalogordningen är lärarens egen. Ett godtyckligt val mellan två
        # likvärdiga ängar ska åtminstone vara samma godtyckliga val i morgon.
        if v > bast_p:
            bast, bast_p = p, v
    if bast is None or bast_p < MIN_POANG:
        return None
    return dict(bast, poang=round(bast_p, 2))


def matcha_exam(exam: dict, *, base: Path | None = None) -> int:
    """Sätt ``scen.plat`` på varje uppgift som har en scen och en träff.

    Fältet är APPENS, aldrig modellens (det poppas ur grammatiken i
    exam_spec.to_response_format) — och den som redan bär ett värde rörs inte:
    läraren kan ha bytt plåt i canvas, och hennes val är senare än vårt.
    Returnerar antalet uppgifter som fick en plåt."""
    if not isinstance(exam, dict):
        return 0
    poster = katalog(base)
    traffar = 0
    # Plåtar som redan ligger på pappret — lärarens egna val medräknade. Ingen
    # plåt sätts två gånger i samma prov (se `tagna` i matcha).
    tagna = {str(u["scen"]["plat"]) for u in exam.get("uppgifter") or []
             if isinstance(u, dict) and isinstance(u.get("scen"), dict)
             and u["scen"].get("plat")}
    for u in exam.get("uppgifter") or []:
        scen = u.get("scen") if isinstance(u, dict) else None
        if not isinstance(scen, dict) or scen.get("plat"):
            continue
        träff = matcha(str(scen.get("begrepp") or ""),
                       str(u.get("text") or ""), poster=poster, tagna=tagna)
        if träff:
            scen["plat"] = träff["namn"]
            tagna.add(träff["namn"])
            traffar += 1
    return traffar


# ── TRYCKVÄGEN ────────────────────────────────────────────────────────
# Plåtarna är 2048×1152 PNG på omkring fyra megabyte styck. Tre av dem rått i
# en provPDF ger en fil på tiotals megabyte som ingen skolskrivare vill ha och
# ingen mejlbilaga rymmer. Bilden trycks dessutom i 0,7·textbredd ≈ 11 cm; vid
# 300 dpi räcker 1300 px, och 1600 är marginal nog för en 2× kopiator.
#
# ORIGINALET RÖRS ALDRIG. Nedskalningen skriver en NY fil i provets utkatalog;
# lärarens plåt ligger kvar i E:\Bildstil precis som den målades.
TRYCK_BREDD = 1600
TRYCK_KVALITET = 85
# Canvasens förhandsvisning. Bilden står i en ruta som är några hundra pixlar
# bred på en skärm som kan vara 2×; 900 räcker och laddar direkt.
FORHANDS_BREDD = 900


def tryckbild(namn: str, ut_dir: Path, *, base: Path | None = None,
              bredd: int = TRYCK_BREDD, stam: str = "plat") -> str | None:
    """Skala plåten till tryckstorlek i `ut_dir` och returnera FILNAMNET.

    Filnamnet, inte sökvägen: Tectonic kompilerar med utkatalogen som
    arbetskatalog (samma kontrakt som tryck.spara_egna_bilder). Saknas plåten,
    eller går den inte att läsa, returneras None — mallen sätter då uppgiften
    utan bild, vilket är bättre än ett prov som inte kompilerar."""
    källa = bildfil(namn, base)
    if källa is None:
        return None
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:                       # pillow saknas → ingen bild
        return None
    try:
        with Image.open(källa) as bild:
            bild.load()
            if bild.width > bredd:
                höjd = round(bild.height * bredd / bild.width)
                bild = bild.resize((bredd, höjd), Image.LANCZOS)
            # JPEG kan inte bära alfa, och en plåt har ingen — men en
            # konverterad PNG med palett kan ha det, och `save` skulle då
            # kasta OSError mitt i ett godkännande.
            if bild.mode != "RGB":
                bild = bild.convert("RGB")
            ut_dir = Path(ut_dir)
            ut_dir.mkdir(parents=True, exist_ok=True)
            filnamn = f"{stam}-{namn}.jpg"
            bild.save(ut_dir / filnamn, format="JPEG",
                      quality=TRYCK_KVALITET, optimize=True)
    except (OSError, ValueError, UnidentifiedImageError,
            Image.DecompressionBombError):
        return None
    return filnamn


def forhandsbild(namn: str, cache_dir: Path, *,
                 base: Path | None = None) -> Path | None:
    """Plåten i skärmstorlek, cachad. Canvas visar den i en ruta som är några
    hundra pixlar bred — en 4 MB PNG per uppgift skulle göra granskningen trög
    utan att synas. Filen skrivs en gång och återanvänds."""
    cache_dir = Path(cache_dir)
    fil = cache_dir / f"forhands-{namn}.jpg"
    if fil.is_file():
        return fil
    namn_ut = tryckbild(namn, cache_dir, base=base, bredd=FORHANDS_BREDD,
                        stam="forhands")
    return cache_dir / namn_ut if namn_ut else None


def plat_bilder(exam: dict, val, ut_dir: Path, *,
                base: Path | None = None) -> dict[int, str]:
    """Uppgiftsnummer → filnamn för de plåtar som ska tryckas.

    Två källor, och lärarens vinner: `exam` bär appens egen matchning
    (``scen.plat``), medan `val` är väljaren i canvas — ``{"7": "a-19-hage-flod"}``
    för ett byte och ``{"7": ""}`` för «ingen plåt på den här uppgiften».
    Numreringen är papprets löpande uppgiftsnummer, samma nyckel som
    tryck.egna_bilder använder, för det är den nyckeln skärmen sätter."""
    valt: dict[int, str] = {}
    if isinstance(val, dict):
        for nyckel, v in val.items():
            try:
                nr = int(str(nyckel).removeprefix("uppg"))
            except (TypeError, ValueError):
                continue
            valt[nr] = str(v or "")
    ut: dict[int, str] = {}
    for nr, u in enumerate(((exam or {}).get("uppgifter") or []), 1):
        scen = u.get("scen") if isinstance(u, dict) else None
        namn = (scen or {}).get("plat") or ""
        if nr in valt:
            namn = valt[nr]
        if not namn:
            continue
        fil = tryckbild(namn, ut_dir, base=base)
        if fil:
            ut[nr] = fil
    return ut
