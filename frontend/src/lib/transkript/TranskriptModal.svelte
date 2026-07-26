<script>
  import { tk } from './stores.svelte.js';
  import { stangTranskript } from './actions.js';
  import Spelare from './Spelare.svelte';
  import Transkriptlista from './Transkriptlista.svelte';

  let ruta = $state(null);

  // Villkoret bär MEDVETET inte nav.tab, till skillnad från B1:s dialoger
  // (InspelningarView.svelte:41-55). Deras bor inuti en panel som göms med
  // hidden, och en förfader med display:none gör att dialogen inte RITAS men
  // lämnar den `open` — showModal() håller då fortfarande hela dokumentet
  // inert, och appen slutar svara utan att något på skärmen förklarar varför.
  //
  // Den här är monterad utanför panelerna (App.svelte) och har ingen sådan
  // förfader. Dessutom är fliklisten inert medan showModal() är aktiv, så ett
  // flikbyte kan inte ske medan rutan är öppen. Fällan finns alltså inte här,
  // och att lägga in villkoret ändå vore kult utan orsak.
  $effect(() => {
    if (!ruta) return;
    if (tk.open) {
      if (!ruta.open) {
        ruta.showModal();
        // Rutan själv, inte en knapp: då läses rubriken innan fokus står på
        // något som går att trycka på. Samma val som B1:s bekräftelseruta.
        ruta.focus();
      }
    } else if (ruta.open) {
      ruta.close();
    }
  });

  // Escape stängs av webbläsaren och når aldrig en egen hanterare. onclose
  // nollställer därför storen — utan den vore dialogen stängd medan tk.open
  // fortfarande vore true, och en ny öppning av SAMMA kort hade inte ändrat
  // tillståndet och alltså inte utlöst effekten ovan. Rutan hade aldrig gått
  // att öppna igen.
  function paClose() {
    if (tk.open) stangTranskript();
  }
</script>

<!-- Alltid monterad, aldrig {#if}-grindad: avmonteras komponenten i
     stängningsögonblicket hinner close() aldrig köras, och då uteblir
     webbläsarens återställning av fokus till knappen som öppnade. Stängd är
     ett <dialog> display:none och alltså borta ur både layout och
     tillgänglighetsträd; den kostar ingenting att låta stå. -->
<dialog
  class="ruta"
  aria-label="Transkript"
  tabindex="-1"
  bind:this={ruta}
  onclose={paClose}
>
  <header class="topp">
    <h2 class="titel">{tk.namn || 'Transkript'}</h2>
    <button type="button" class="ghost" onclick={stangTranskript}>Stäng</button>
  </header>

  <!-- Live-regionen. Permanent nod, aldrig {#if}-grindad, bara visuellt
       klippt. En öppen modal gör resten av dokumentet inert, så den kan inte
       konkurrera med vyernas egna regioner. -->
  <p class="besked-sr" role="status">{tk.besked}</p>
  <p
    class="besked"
    class:info={tk.beskedArt === 'info'}
    aria-hidden="true"
    data-testid="transkript-statusrad"
  >{tk.besked}</p>

  {#if tk.laddar}
    <p class="laddar">Hämtar transkriptet …</p>
  {/if}

  <Spelare />
  <Transkriptlista />
</dialog>

<style>
  /* Ingen egen skärm, inget z-index och ingen centrering: showModal() lyfter
     rutan till top-layer och webbläsarens <dialog>-regel centrerar den.
     color sätts UTTRYCKLIGEN — webbläsarens regel sätter color: CanvasText,
     som bryter arvet från body. */
  .ruta {
    width: min(94vw, 860px);
    max-height: 90vh;
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line);
    border-radius: 5px;
    box-shadow: var(--shadow);
    padding: 14px 16px;
  }
  /* display:flex hör HÄR, inte i .ruta ovan: en författarregel (authors origin)
     slår webbläsarens dialog:not([open]) { display: none } OAVSETT specificitet
     — ursprung går före specificitet i cascade-ordningen. .ruta { display: flex }
     hade alltså tvingat rutan synlig (fast layoutlös/inert) även EFTER close(),
     eftersom [open] försvinner men klassen .ruta finns kvar. Bekräftat med
     getComputedStyle: display stod kvar på "flex" trots dialog.open === false.
     RedigeraLektion.svelte/InspelningarView.svelte:s rutor sätter av samma skäl
     ALDRIG display alls och får sin block-layout gratis av webbläsaren. */
  .ruta[open] {
    display: flex;
    flex-direction: column;
  }
  /* Samma dimning och samma 42 % som B1:s dialoger. */
  .ruta::backdrop { background: color-mix(in srgb, var(--ink) 42%, transparent); }
  .ruta:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

  .topp {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }
  .titel {
    font-family: var(--sans);
    font-size: 1.125rem;
    font-weight: 600;
    line-height: 1.3;
    margin: 0;
    overflow-wrap: anywhere;
  }
  /* Identisk med .ghost i frontend/src/lib/transkribera/Korning.svelte:284-293. */
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 9px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }

  /* Identisk med .fel-sr i frontend/src/lib/inspelningar/InspelningarView.svelte:316-323.
     Klippande teknik — noden finns kvar i tillgänglighetsträdet men upptar
     ingen synlig plats, till skillnad från display:none. */
  .besked-sr {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  /* Den SYNLIGA raden. :empty-regeln hör hemma här och ingen annanstans —
     se kommentaren vid noden. Speglar .fel i InspelningarView.svelte:330-333,
     men med dialogens egen marginal i stället för vyns. */
  .besked { color: var(--bad); margin: 10px 0 0; }
  .besked.info { color: var(--ink-2); }
  .besked:empty { display: none; }

  .laddar { color: var(--ink-3); margin: 10px 0 0; }
</style>
