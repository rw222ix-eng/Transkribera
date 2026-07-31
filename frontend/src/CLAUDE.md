# Svelte-komponenternas konventioner (dyrköpta — bryt dem inte av misstag)

Varje regel nedan kommer ur ett fel som faktiskt inträffade under migrationen
(planerna A1–A4, B1). De är billiga att följa och dyra att återupptäcka.

Detta är komponentnära regler och laddas när du arbetar med filer under
`frontend/src/`. E2E-reglerna och plan-regeln ligger kvar i rotens `CLAUDE.md`,
eftersom de gäller utanför komponenterna.

**Live-regioner och statusbesked**

- En `role="status"` får **aldrig** ligga i ett `{#if}`-grindat block. En region
  som monteras in samtidigt som sin text annonseras inte pålitligt. Noden ska
  vara permanent och bara visuellt klippt (`clip-path: inset(50%)`) — **aldrig**
  `display: none`, som tar bort den ur tillgänglighetsträdet. Underkänt fyra
  gånger; `e2e/transkribera-kalla.spec.mjs` har en spärr som vaktar både
  nodidentiteten och antalet.
- **En annonserande nod per renderingskontext.** Varje vy har sin egen
  permanenta region, och en öppen `<dialog>` har sin — de kan aldrig konkurrera,
  eftersom en dold panel är `display: none` och en öppen modal gör resten inert.
  Principen håller bara vid **äkta** modalitet: byter någon till `dialog.show()`
  eller en icke-modal overlay blir båda regionerna levande samtidigt.
- Varje steg/vy renderar dessutom en **synlig** kopia av samma text, märkt
  `aria-hidden="true"` och utan egen roll. Bara live-regionen annonseras.

**Modaler**

- Native `<dialog>` + `showModal()`. Det ger fokusfälla, Escape, backdrop och
  top-layer gratis — allt annat blir handskriven kod för det webbläsaren redan gör.
- Komponenten hålls **alltid monterad** (utan `{#if}`), annars hinner `close()`
  aldrig köras och webbläsarens fokusåterställning uteblir. `onclose` nollställer
  storen. Stäng dialogen vid flikbyte: en öppen dialog i en `hidden` panel ritas
  inte men blockerar dokumentet.

**Reaktivitet**

- Föredra **explicita actions** framför implicita `$effect`-kedjor. En `$effect`
  som råkar spåra ett fält för att en anropad funktion läser det synkront före
  sitt första `await` är ett beroende som försvinner tyst så fort någon lägger
  dit ett `await` — och den gör samtidigt tandkontroller tandlösa.
- Monteringseffekter: grinda på det de faktiskt beror på och kör hämtningarna i
  `untrack`. Sveltes spårning är **dynamisk, inte lexikal**.
- Allt som kan överlappa behöver en **generationsvakt** (`korToken`-mönstret i
  `frontend/src/lib/transkribera/actions.js`). Ge varje hämtning en **egen**
  räknare — en delad låter den ena ogiltigförklara den andra.

**Filändelser**

- Runes utanför komponenter kräver `.svelte.js`. Rena moduler utan reaktiv state
  (`week.js`, `kursfarg.js`, `korning.js`) ska **inte** ha den ändelsen.
