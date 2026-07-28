<script>
  import { chatt } from './stores.svelte.js';
  import { stangLektionschatt, oppnaTranskriptet } from './actions.js';
  import Meddelandelista from './Meddelandelista.svelte';
  import Skrivrad from './Skrivrad.svelte';
  import Kallpanel from './Kallpanel.svelte';

  let ruta = $state(null);

  // Villkoret bär MEDVETET inte nav.tab, av samma skäl som B2:s
  // TranskriptModal: komponenten monteras utanför flikpanelerna i App.svelte
  // och har ingen hidden förfader, och fliklisten är inert medan showModal()
  // är aktiv — ett flikbyte kan alltså inte ske medan rutan är öppen.
  $effect(() => {
    if (!ruta) return;
    if (chatt.open) {
      if (!ruta.open) {
        ruta.showModal();
        // Rutan själv, inte en knapp: då läses rubriken innan fokus står på
        // något som går att trycka på.
        ruta.focus();
      }
    } else if (ruta.open) {
      ruta.close();
    }
  });

  // Escape stängs av webbläsaren och når aldrig en egen hanterare. onclose
  // sparar därför samtalet och nollställer storen — utan den vore dialogen
  // stängd medan chatt.open var sant, och en ny öppning av samma lektion hade
  // inte ändrat tillståndet och alltså inte utlöst effekten ovan.
  function paClose() {
    if (chatt.open) stangLektionschatt();
  }
</script>

<!-- Alltid monterad, aldrig {#if}-grindad: avmonteras komponenten i
     stängningsögonblicket hinner close() aldrig köras, och webbläsarens
     återställning av fokus till knappen som öppnade uteblir. -->
<dialog
  class="ruta"
  aria-label="Lektionschatt"
  tabindex="-1"
  bind:this={ruta}
  onclose={paClose}
>
  <header class="topp">
    <h2 class="titel">{chatt.namn || 'Lektionschatt'}</h2>
    <div class="toppknappar">
      <!-- Öppnar B2:s transkriptvy OVANPÅ chatten. Gamla appen stänger
           chatten först (app.js:4162) och kastar hela samtalet. -->
      <button type="button" class="ghost" onclick={oppnaTranskriptet}>Transkript</button>
      <button type="button" class="ghost" onclick={stangLektionschatt}>Stäng</button>
    </div>
  </header>

  <!-- Live-regionen. Permanent nod, aldrig {#if}-grindad, bara visuellt
       klippt. Den bär `annons`, INTE `besked`: ett svar som växer sub-word
       för sub-word vore oanvändbart att lyssna på, så tokens annonseras
       aldrig — bara "Svarar …" och det färdiga svaret. -->
  <p class="annons-sr" role="status">{chatt.annons}</p>
  <p
    class={['besked', { info: chatt.beskedArt === 'info' }]}
    aria-hidden="true"
    data-testid="chatt-statusrad"
  >{chatt.besked}</p>

  {#if chatt.laddar}
    <p class="laddar">Hämtar lektionens transkript …</p>
  {/if}

  <div class="kropp">
    <div class="samtal">
      <Meddelandelista />
      <Skrivrad />
    </div>
    <Kallpanel />
  </div>
</dialog>

<style>
  /* Ingen egen skärm, inget z-index och ingen centrering: showModal() lyfter
     rutan till top-layer och webbläsarens <dialog>-regel centrerar den.
     color sätts UTTRYCKLIGEN — webbläsarens regel sätter color: CanvasText,
     som bryter arvet från body. */
  .ruta {
    width: min(96vw, 1000px);
    height: min(88vh, 880px);
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line);
    border-radius: 5px;
    box-shadow: var(--shadow);
    padding: 14px 16px;
  }
  /* display hör HÄR, inte i .ruta ovan: en författarregel slår webbläsarens
     dialog:not([open]) { display: none } OAVSETT specificitet — ursprung går
     före specificitet i cascade-ordningen. .ruta { display: flex } hade
     tvingat rutan synlig även efter close(). Mätt i plan B2. */
  .ruta[open] {
    display: flex;
    flex-direction: column;
  }
  /* Samma dimning och samma 42 % som B1:s och B2:s rutor. */
  .ruta::backdrop { background: color-mix(in srgb, var(--ink) 42%, transparent); }
  .ruta:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

  .topp {
    flex: 0 0 auto;
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
  .toppknappar { display: flex; gap: 8px; }
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
  .annons-sr {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  /* Den SYNLIGA raden. :empty-regeln hör hemma här och ingen annanstans. */
  .besked { flex: 0 0 auto; color: var(--bad); margin: 10px 0 0; }
  .besked.info { color: var(--ink-2); }
  .besked:empty { display: none; }
  .laddar { flex: 0 0 auto; color: var(--ink-3); margin: 10px 0 0; }

  .kropp {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    gap: 14px;
    margin-top: 12px;
  }
  .samtal {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
</style>
