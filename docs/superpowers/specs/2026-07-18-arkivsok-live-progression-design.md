# Arkivsökets live-progression — "Kartotek → läsbord"

*Design godkänd 2026-07-18. Gäller båda AI-söken: inspelningssidans "Fråga ditt
arkiv" (`/api/search/ask`) och planeringsarkivets tavlor/prov-sök
(`/api/planning/ask`).*

## Problem

Dagens skannings-UI (korten "I kö / Läser … / Läst ✓ / Träff ●") är ren
koreografi: en frontend-timer tickar fram en kosmetisk läsposition, och
"Träff ●" sätts av en klientmatchning som räknar *alla* ord i frågan — även
"var", "jag", "och". Frågan "Var förklarar jag täljare och nämnare?" markerar
därför irrelevanta inspelningar som träffar. Värre: samma OR-matchning styr den
riktiga RAG-hämtningen, så irrelevanta transkriptioner skickas faktiskt till
LLM:en som underlag.

## Mål

1. Progressionen ska visa **riktiga händelser** ur backend — vilka
   transkriptioner som genomsöks, vilka som faktiskt matchar, och vilka
   AI:n läser djupt.
2. Träff = match på frågans **innehållsord**, inte småord.
3. Snygg, tydlig tvåfas-animation i pappers+bläck-språket (DESIGN.md).
4. En **delad komponent** för båda söken.

## 1. Backend — riktiga händelser i samma SSE-ström

`/api/search/ask` och `/api/planning/ask` behåller sina endpoints och
`token`/`done`/`error`-kontrakt, men skickar nya eventtyper först:

- `scan_plan` — `{type, total, items: [{key, name}]}`: alla objekt som
  genomsöks, i genomsökningsordning (nyaste först). `key` är `lesson_id`
  resp. `typ-id`.
- `scan_result` — ett per objekt: `{type, key, hits}` där `hits` är verkligt
  antal förekomster av frågans innehållsord i texten.
- `deep_read` — `{type, sources: [...]}`: de ≤5 källor vars utdrag faktiskt
  skickas till LLM:en (samma form som `done`-eventets `sources`).

Ärlighetsprincip: FTS/skanningen är klar på millisekunder, så alla
`scan_result` skickas direkt — **frontend pacar avslöjandet** (~60–150 ms/kort,
tak ~3,5 s totalt). Det som visas är äkta data i äkta ordning; bara
utrullningstakten är styrd. Fas 2 visar de ≤5 källorna samlat med en gemensam
läsindikator — LLM:en läser dem i ett svep, så vi fejkar inte "en i taget".

## 2. Äkta relevans — innehållsord, inte småord

- Svensk stoppordslista i `app/db.py` (`_STOPWORDS_SV`) + `content_terms(q)`
  som filtrerar frågan till innehållsord; faller tillbaka till alla ord om
  inget återstår.
- AI-frågans retrieval (`search_transcripts(match_all=False)`,
  `lessons_excerpts_for`, `_score_archive`) använder innehållsorden.
- Träff (`scan_result.hits`) = förekomster av innehållsord. Objekt utan
  innehållsordsmatch blir "Läst ✓" och skickas **inte** till LLM:en.
- Om inget objekt matchar → 404 med samma felmeddelande som idag.
- Vanliga ordsökningen ("Sök ord" / arkivets fritextsök) rörs inte.

## 3. Frontend — delad komponent, två faser

En gemensam renderfunktion `scanTheater(m)` i `app.js` används av båda söken.
Den gamla timer-koreografin (`_scanTimer`, `_arkScanTimer`, `askScanIdx`,
`arkScanIdx`) tas bort.

**Fas 1 — genomsökningen (kartoteket).** Korten ligger i rutnätet. Ett kort i
taget tänds ("Läser …", accentram + svag lyftskugga), stämplas sedan
"Läst ✓" (nedtonat) eller "● n träffar" (bläckaccent, förblir tänt).
Statusraden visar "Söker igenom N inspelningar — [namn]" med en tunn
progresslinje och räknaren "n träffar hittills". Max 24 kort visas; resten
summeras i ett "+ N fler"-kort (räknare/totaler täcker alla).

**Fas 2 — läsbordet.** När alla kort avslöjats och `deep_read` kommit görs en
omläggning: träffkällorna animeras in på en egen rad överst ("AI:n läser nu
dessa X") med lyft + stagger; övriga kort kollapsar till en summeringsrad
("… och la N åt sidan"). Läsbordskorten har en långsam skimmer-understrykning
medan svaret streamas; vid `done` stannar skimret och korten blir klickbara
källor (samma öppning som idag).

**Motion.** CSS-transitions/keyframes på `transform`/`opacity`
(morphdom-vänligt). `prefers-reduced-motion` stänger av skimmer/stagger och
hoppar till slutlägen. Om svaret börjar streama innan utrullningen är klar
visas svaret som idag — panelerna är oberoende.

## 4. Felhantering & kanter

- 409 (GPU) / 404 (inga träffar): kartoteket visas aldrig; samma fel som idag.
- `error` mitt i strömmen: utrullningen stoppas, kort fryser, felrad som idag.
- Esc/"Ny fråga": befintliga `_askRun`/`_arkRun`-vakter nollställer allt.
- `done` innan utrullningen hunnit klart → resterande kort snappas fram.

## 5. Test

- Pytest: SSE-strömmen innehåller `scan_plan` → `scan_result`(×N) →
  `deep_read` → tokens; irrelevant inspelning (bara småordsmatch) får
  `hits: 0` och blir inte källa; stoppordsfiltret och fallbacken testas på
  db-nivå.
- `node --check app/web/static/app.js` efter JS-ändringar.
- Playwright-harnessen (fake-läget) för visuell verifiering.
