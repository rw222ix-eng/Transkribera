# Att sätta upp ett worktree som faktiskt fungerar

Migrationen körs i **parallella strömmar**, en per git-worktree, så flera chattar
kan arbeta samtidigt utan att skriva över varandra. Den här filen beskriver vad
som krävs för att ett nytt worktree ska bli körbart — och varför, eftersom de
flesta stegen inte är uppenbara.

## Skapa

```bash
git worktree add -b <gren> "E:/Transkribera-worktrees/<namn>" HEAD
```

**Lägg det utanför repot**, inte under `.claude/worktrees/`. Vite-roten är
repo-roten och `server.fs.allow` är en säkerhets-allowlist; ett worktree inne i
trädet blandar sig i den ytan i onödan.

## Fyra saker som inte följer med, och som alla behövs

Git kopierar bara spårade filer. Det här är gitignorerat och saknas alltså i ett
färskt worktree — varje punkt ger fallerande tester tills den är åtgärdad.

**1. Beroenden.** Både roten och `e2e/` har egna `package.json`:

```bash
npm ci && cd e2e && npm ci
```

**2. Demofilen `Mamma waw isolerad.wav`.** Gitignorerad via `*.wav`. Utan den
faller varje spec som rör `/api/sample` — vilket är fem av åtta i
`next-foundation`. Kopiera den:

```bash
cp "E:/Transkribera/Mamma waw isolerad.wav" .
```

Felet är åtminstone läsbart: specarnas förkontroll ger *"Saknad testfixtur:
'Mamma waw isolerad.wav' i repo-roten"* efter ~47 ms.

**3. `models/`.** Gitignorerad. `/api/models` gör en **riktig** hårdvaru- och
modellskanning, och transkriberingsguidens startknapp aktiveras bara när en
installerad modell matchar det valda språket — KB-Whisper large är den enda på
den här maskinen. Modellerna är flera GB, så kopiera dem inte: gör en junction
som delar samma filer.

```bash
rmdir models 2>/dev/null
cmd //c mklink //J models "E:\Transkribera\models"
```

(Katalogen kan redan finnas tom — servern skapar den. Därför `rmdir` först.)

**4. Arbetsloggen `.superpowers/sdd/progress.md`.** Gitignorerad, alltså tom i
ett nytt worktree. Det är **avsiktligt** — loggen är per ström. Men det betyder
också att en färsk chatt inte känner till vad tidigare planer lärt sig. Det som
gäller alla strömmar står därför i `CLAUDE.md` under *"Svelte-frontendens
konventioner"*; läs det avsnittet innan du skriver kod.

## E2E-porten sköter sig själv

`e2e/playwright.config.ts` härleder porten ur worktreets sökväg (8760–8799), så
två worktrees inte kan återanvända varandras fejkserver. Det är viktigt:
`reuseExistingServer` är på och basmappen är per worktree, så en delad port
serverar **fel bygge mot fel data** utan att något syns. Rör inte härledningen.

Manuella verktyg som `e2e/explore.mjs` och `npm run codegen` pekar fortfarande
på 8731 — de måste få porten härifrån i ett worktree.

## Verifiera innan du börjar

```bash
python -m pytest                          # 803 passed
npm run check                             # 0 ERRORS 0 WARNINGS
npm run build                             # exit 0
cd e2e && npm run test:next-foundation    # 32 passed
```

Går inte alla fyra igenom är worktreet inte klart — leta i listan ovan innan du
letar i koden.

`npm run build` MÅSTE köras före Playwright. `npx playwright test` bygger inte
frontenden, och det har gett falsk grön två gånger i den här migrationen.

## Dela upp arbetet efter delad fil, inte efter funktion

Det är vad som avgör om två strömmar krockar. Varje delad vy-fil ska ha **exakt
en ägare**:

| Ström | Planer | Äger |
|---|---|---|
| A | B2 → B4 → plan C | `Korning.svelte`, `Lektionskort.svelte`, `App.svelte` |
| B | B5 → B3 | `InspelningarView.svelte` |

Behöver du något ur en fil du inte äger — säg det i stället för att ändra.

Enda filen alla strömmar rör är `e2e/playwright.config.ts`, där var och en lägger
till en `testMatch`-rad. Trivial konflikt vid merge.

## Merge

Merge till `main` är **ägarens grind**. Pusha gärna grenen; merga inte.
