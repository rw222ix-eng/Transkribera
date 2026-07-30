# Product

## Register

product

## Platform

web

## Users

**En användare: ägaren.** En svensk gymnasielärare på sin egen Windows 11-dator
(RTX 4090 / 24 GB-klass). Det här är ett arbetsredskap, inte en produkt — appen får
anta att den som använder den vet vad den gör, men får aldrig slösa hens tid eller
ljuga om vad den kan. Kraven på onboarding och tålighet för ovana användare är
därför låga; kraven på hastighet och ärlighet är höga.

Lektionen spelas in med **annan utrustning** — telefon, diktafon, vad som råkar
finnas — och filen dras in i appen efteråt. Inspelning direkt i appen finns, men är
inte den normala vägen in. Det betyder att appen börjar sitt arbete när lektionen
redan är slut och läraren sitter ner, typiskt mellan två pass eller på
eftermiddagen.

Materialet bär **elevers röster, namn och svårigheter**. Ljudet lämnar aldrig
datorn: transkriberingen körs på det egna grafikkortet, och rättningen mot ljudet
likaså.

**Ägarens beslut 2026-07-30:** *texten* får däremot gå ut. Språkmodellsarbetet —
sammanfattning, extraktion, arkivchatt, tavla, prov — flyttas från den lokala
Qwen3 till Claude Code på ägarens prenumeration. Det betyder att lektionstexten,
med de namn och svårigheter den bär, skickas till Anthropic.

Det är en medveten avvägning och den är hens att göra, men den ska stå skriven
rakt ut i stället för att bo i en kommentar: appen är **inte längre offline i
strikt mening**. Kvar som hård regel är att *ljudfilen* aldrig lämnar maskinen,
och att appen ska vara ärlig i gränssnittet om vilka moment som går ut.

## Product Purpose

**Det enda i läraryrket som ingen annan kan göra åt läraren är att tänka ut vad
lektionen ska innehålla.** Allt runt omkring — komma ihåg vad som sades, hålla reda
på vad som lovades, föra in saker i kalendern, dokumentera vad som hanns med, sätta
ihop ett prov, förbereda en tavla — är arbete som äter tid från just den delen.

Transkribera finns för att absorbera så mycket som möjligt av det arbetet, så att
tiden går till innehållet i stället. **Appen mäts på hur snabbt den gör läraren klar,
inte på hur mycket den kan.** Ett flöde som kräver städning efteråt har misslyckats
även om resultatet är korrekt. Så få steg som möjligt, så rätt som möjligt på första
försöket, och snabb iteration när det inte blev rätt.

Den bärande observationen bakom arkivet: **en lektion innehåller mer än en lärare
hinner fånga medan den pågår.** En elev nämner att hen är borta nästa vecka. Läraren
säger själv att klassen ska samlas någonstans vid något tillfälle. Någon ställer en
fråga som borde följas upp. Det finns ingen lucka mellan meningarna där man hinner ta
fram en anteckningsbok, så det försvinner. Appen finns för att fånga upp det i
efterhand och göra det till konkreta kalenderposter — inte för att arkivera lektioner.

Uppföljningen är **för lärarens egen skull**: se vad som gick tungt, vad som hanns
med, vad som återkommer, och undervisa bättre nästa gång. Ingen rektor, ingen
vårdnadshavare, inget utvecklingssamtal ska behöva se den. Den avgränsningen befriar
appen från exportformat, bevarandepolicy och granskningsbarhet mot tredje part — och
låter den optimeras helt för hastighet.

### Avsett men obyggt (2026-07-28)

Två saker hör till syftet men finns inte i koden än. De står här för att beskrivningen
inte ska läsas som en beskrivning av nuläget:

1. **Automatisk genomgång efter varje transkribering.** Så snart en körning är klar
   ska appen själv leta upp datum, åtaganden och uppföljningar i transkriptet och
   lägga fram dem som granskningsbara förslag. I dag sker extraktionen bara när
   läraren *frågar* — vilket förutsätter att hon kommer ihåg att fråga, och att komma
   ihåg är precis det problem appen finns för att lösa.
2. **Klass, kurs och namn vid inläsning.** De sätts i dag först i efterhand i
   arkivet. Inläsningen är den enda punkten i flödet där läraren säkert vet vilken
   lektion det är; att märka den där tar bort ett städmoment.

## Positioning

Fångar upp det som sades under lektionen och som annars försvinner — åtaganden,
datum, uppföljningar — och gör det till kalenderposter och sökbar kunskap, samtidigt
som det tar över förberedelsearbetet runt nästa lektion. Allt på lärarens egen dator,
aldrig i molnet.

## Flödet

**1 · Transkribera.** Filen dras in, märks med namn/klass/kurs, får språk och format,
och ett valfritt andra pass som rättar texten mot vad som faktiskt sägs (räddar
främst namn och ämnesord). Körningen startar och läraren går ifrån — lektionen landar
i arkivet av sig själv. KB-Whisper på det egna grafikkortet, och ljudrättningen
likaså; appen serialiserar dem så de aldrig konkurrerar om minnet.

**2 · Inspelningar.** Lektionerna grupperas per vecka, filtrerbara på klass, kurs och
månad. Varje lektion kan öppnas som transkript med ljudet synkat mot texten, så ett
ställe går att hoppa till och höra. Hela arkivet är frågbart — svaren bygger på vad
som verkligen sades och bär källhänvisningar tillbaka till stället i transkriptet, så
de går att kontrollera. Kalenderförslag granskas alltid av läraren innan något
skickas; det som godkänns kan läggas i Google Kalender, eftersom kalendern ändå är
där lärarens dag bor.

**3 · Planering.** Vänder på riktningen och tar över förberedelsearbetet.
En **lektionstavla** är ett förberedelsedokument: läraren beskriver momentet, får ett
strukturerat utkast och tänker igenom lektionen med det. Tavlan projiceras *inte* —
läraren skriver själv på whiteboarden, bättre förberedd. **Prov och arbetsblad** går
hela vägen till papper: byggda mot Gy25:s centrala innehåll med poäng och förmågor
fördelade, ändringsbara genom att skriva vad som ska bli annorlunda, och satta som
färdig PDF med facit avsedd att skrivas ut.

## Brand Personality

Calm, editorial, and quietly confident — in three words, **calm, editorial,
unobtrusive**. The voice is Swedish, plain, and respectful of the teacher's time and
expertise; never chirpy, salesy, or hyped. The emotional goal is that the teacher
feels **in control and unhurried**, with the software receding into the background
like good paper so that the *lesson content* — not the interface — is the subject.

## Anti-references

Three looks the owner has explicitly ruled out:

- **Generic AI / SaaS dashboard** — card grids, hero-metric tiles, gradient text,
  glassmorphism, cyan-on-dark neon. The "AI slop" look.
- **Dense corporate / enterprise admin UI** — cramped, cold, bureaucratic,
  Bootstrap-gray.
- **Anything that reads as a cloud or online service** — no accounts, no sync
  status, no "connected"-badges, no service chrome. Att en del av arbetet numera
  går ut ändrar inte det här: undantagen redovisas **där de sker**, i lugn
  svenska på det ställe momentet startar, aldrig som en molnprodukts skyltning.

## Design Principles

1. **Recede, don't perform.** The UI is quiet scaffolding; the lesson content —
   transcript, sources, answers — is the subject. Prefer whitespace and hairlines over
   boxes and chrome.
2. **Editorial, not dashboard.** Compose like print: a mono eyebrow, a serif-italic
   display title, a lede, asymmetric grids, hairline rules. Never card-grid or
   hero-metric slop; never dense admin tables.
3. **Ärlighet om var arbetet sker.** Ljudet stannar på maskinen, alltid. Det som
   går ut — språkmodellsarbetet och kalenderposterna — ska synas där det sker,
   en gång, i lugn text. Aldrig molnspråk eller molnikonografi, aldrig
   kontokänsla, men heller aldrig ett tyst "lokalt" som inte längre är sant.
4. **Swedish, plain, unhurried.** All user-facing text is natural Swedish, calm and
   respectful of the teacher's time — no hype, no chirp.
5. **Restrained motion; accessibility as a floor.** Purposeful mask-reveal and
   fade-up with expo-out easing, and reduced motion always honored.
6. **Färdig slår fullständig.** Appen finns för att ge tillbaka tid. Ett steg som
   kan tas bort ska tas bort; ett värde appen kan gissa rätt på ska den gissa på; ett
   moment som måste städas efteråt är ett designfel även när resultatet blir rätt.
   Vid val mellan en funktion till och ett kortare flöde vinner det kortare flödet.

## Accessibility & Inclusion

Accessibility is **best-effort with no formal WCAG target**, but real and
load-bearing: keyboard-operable controls, visible focus, honest labels, and live
regions for asynchronous status. Reduced motion is fully honored throughout. A
hardening pass in July 2026 brought the interface close to AA in practice.
